from __future__ import annotations

import os
import re
from dataclasses import asdict, dataclass
from typing import Any, Mapping
from urllib.parse import urlsplit
from uuid import UUID

import psycopg
from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .github_installation import InstallationRepositorySnapshot, validate_installation_id


SOURCE_KEY = "github-app"
EXTERNAL_ACCOUNT_PREFIX = "github:installation:"
PERMISSION = re.compile(r"^[a-z][a-z0-9_-]*:(?:read|write)$")
ENVIRONMENT_NAME = re.compile(r"^[A-Z][A-Z0-9_]{0,126}$")
REFERENCE_SCHEMES = {
    "env",
    "github-app",
    "vault",
    "aws-secrets",
    "gcp-secrets",
    "azure-key-vault",
}
REQUIRED_PERMISSIONS = {"contents:read", "metadata:read"}


@dataclass(frozen=True, slots=True)
class ConnectorBinding:
    tenant_id: UUID
    tenant_key: str
    source_system_id: UUID
    connector_account_id: UUID
    installation_id: str
    credential_reference: str
    connector_status: str


@dataclass(frozen=True, slots=True)
class RegistrationResult:
    tenant_id: str
    source_system_id: str
    connector_account_id: str
    installation_target_id: str
    installation_id: str
    created: bool


@dataclass(frozen=True, slots=True)
class ReconciliationResult:
    connector_account_id: str
    installation_id: str
    source_revision: str
    repository_count: int
    created_count: int
    updated_count: int
    removed_count: int
    cancelled_run_count: int


@dataclass(frozen=True, slots=True)
class RevocationResult:
    connector_account_id: str
    installation_id: str
    disabled_target_count: int
    cancelled_run_count: int


def register_installation(
    database_url: str,
    *,
    tenant_key: str,
    installation_id: str,
    credential_reference: str,
    permissions: list[str],
) -> RegistrationResult:
    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        return register_installation_connection(
            connection,
            tenant_key=tenant_key,
            installation_id=installation_id,
            credential_reference=credential_reference,
            permissions=permissions,
        )


def register_installation_connection(
    connection: Connection[dict[str, Any]],
    *,
    tenant_key: str,
    installation_id: str,
    credential_reference: str,
    permissions: list[str],
) -> RegistrationResult:
    validate_installation_id(installation_id)
    validate_credential_reference(credential_reference)
    normalized_permissions = validate_permissions(permissions)
    tenant = connection.execute(
        "SELECT id FROM tenant WHERE tenant_key=%s AND status='ACTIVE' FOR UPDATE",
        (tenant_key,),
    ).fetchone()
    if tenant is None:
        raise ValueError(f"unknown active tenant: {tenant_key}")
    external_key = _external_account_key(installation_id)
    conflict = connection.execute(
        """
        SELECT tenant_id FROM connector_account
        WHERE external_account_key=%s AND tenant_id<>%s
        LIMIT 1
        """,
        (external_key, tenant["id"]),
    ).fetchone()
    if conflict is not None:
        raise ValueError("GitHub installation is already registered to another tenant")
    source = connection.execute(
        """
        INSERT INTO source_system(tenant_id,source_key,kind,base_uri,metadata)
        VALUES (%s,%s,'GITHUB','https://api.github.com',%s)
        ON CONFLICT(tenant_id,source_key)
        DO UPDATE SET base_uri=EXCLUDED.base_uri,metadata=EXCLUDED.metadata
        RETURNING id
        """,
        (
            tenant["id"],
            SOURCE_KEY,
            Jsonb({"provider": "github", "authentication": "GITHUB_APP_INSTALLATION"}),
        ),
    ).fetchone()
    assert source is not None
    existing = connection.execute(
        """
        SELECT id FROM connector_account
        WHERE tenant_id=%s AND source_system_id=%s AND external_account_key=%s
        """,
        (tenant["id"], source["id"], external_key),
    ).fetchone()
    connector = connection.execute(
        """
        INSERT INTO connector_account(
          tenant_id,source_system_id,external_account_key,credential_reference,
          permissions,status
        ) VALUES (%s,%s,%s,%s,%s,'ACTIVE')
        ON CONFLICT(tenant_id,source_system_id,external_account_key)
        DO UPDATE SET credential_reference=EXCLUDED.credential_reference,
                      permissions=EXCLUDED.permissions,status='ACTIVE',updated_at=now()
        RETURNING id
        """,
        (
            tenant["id"],
            source["id"],
            external_key,
            credential_reference,
            Jsonb(normalized_permissions),
        ),
    ).fetchone()
    assert connector is not None
    installation_target = connection.execute(
        """
        INSERT INTO ingest_target(
          tenant_id,source_system_id,connector_account_id,target_kind,target_key,
          priority,enabled,refresh_policy,next_due_at
        ) VALUES (%s,%s,%s,'GITHUB_INSTALLATION',%s,'HOT',true,%s,now())
        ON CONFLICT(tenant_id,source_system_id,target_kind,target_key)
        DO UPDATE SET connector_account_id=EXCLUDED.connector_account_id,
                      enabled=true,refresh_policy=EXCLUDED.refresh_policy,
                      next_due_at=now(),updated_at=now()
        RETURNING id
        """,
        (
            tenant["id"],
            source["id"],
            connector["id"],
            _external_account_key(installation_id),
            Jsonb(
                {
                    "provider": "github",
                    "installation_id": installation_id,
                    "operation": "RECONCILE_REPOSITORIES",
                    "cadence_seconds": 3600,
                }
            ),
        ),
    ).fetchone()
    assert installation_target is not None
    return RegistrationResult(
        tenant_id=str(tenant["id"]),
        source_system_id=str(source["id"]),
        connector_account_id=str(connector["id"]),
        installation_target_id=str(installation_target["id"]),
        installation_id=installation_id,
        created=existing is None,
    )


def connector_binding(
    database_url: str,
    *,
    tenant_key: str,
    installation_id: str,
) -> ConnectorBinding:
    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        return connector_binding_connection(
            connection, tenant_key=tenant_key, installation_id=installation_id,
        )


def connector_binding_connection(
    connection: Connection[dict[str, Any]],
    *,
    tenant_key: str,
    installation_id: str,
    for_update: bool = False,
    require_active: bool = True,
) -> ConnectorBinding:
    validate_installation_id(installation_id)
    row = connection.execute(
        f"""
        SELECT tenant.id tenant_id,tenant.tenant_key,source.id source_system_id,
               connector.id connector_account_id,connector.credential_reference,
               connector.status connector_status
        FROM tenant
        JOIN source_system source ON source.tenant_id=tenant.id AND source.source_key=%s
        JOIN connector_account connector
          ON connector.tenant_id=tenant.id AND connector.source_system_id=source.id
        WHERE tenant.tenant_key=%s AND tenant.status='ACTIVE'
          AND connector.external_account_key=%s
          {"AND connector.status='ACTIVE'" if require_active else ""}
        {"FOR UPDATE OF connector" if for_update else ""}
        """,
        (SOURCE_KEY, tenant_key, _external_account_key(installation_id)),
    ).fetchone()
    if row is None:
        qualifier = "active " if require_active else ""
        raise ValueError(f"{qualifier}GitHub installation connector was not found")
    return ConnectorBinding(
        tenant_id=row["tenant_id"],
        tenant_key=row["tenant_key"],
        source_system_id=row["source_system_id"],
        connector_account_id=row["connector_account_id"],
        installation_id=installation_id,
        credential_reference=row["credential_reference"],
        connector_status=row["connector_status"],
    )


def reconcile_installation(
    database_url: str,
    *,
    tenant_key: str,
    snapshot: InstallationRepositorySnapshot,
) -> ReconciliationResult:
    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        return reconcile_installation_connection(
            connection, tenant_key=tenant_key, snapshot=snapshot,
        )


def reconcile_installation_connection(
    connection: Connection[dict[str, Any]],
    *,
    tenant_key: str,
    snapshot: InstallationRepositorySnapshot,
) -> ReconciliationResult:
    if snapshot.observed_total != len(snapshot.repositories):
        raise ValueError("installation repository snapshot total does not match its entries")
    target_key_set = {
        repository.target_key(snapshot.installation_id)
        for repository in snapshot.repositories
    }
    if len(target_key_set) != len(snapshot.repositories):
        raise ValueError("installation repository snapshot contains duplicate repositories")
    binding = connector_binding_connection(
        connection,
        tenant_key=tenant_key,
        installation_id=snapshot.installation_id,
        for_update=True,
    )
    existing_rows = connection.execute(
        """
        SELECT target_key FROM ingest_target
        WHERE tenant_id=%s AND source_system_id=%s AND connector_account_id=%s
          AND target_kind='REPOSITORY'
        """,
        (binding.tenant_id, binding.source_system_id, binding.connector_account_id),
    ).fetchall()
    existing_keys = {row["target_key"] for row in existing_rows}
    target_keys: list[str] = []
    for repository in snapshot.repositories:
        target_key = repository.target_key(snapshot.installation_id)
        target_keys.append(target_key)
        enabled = not repository.disabled
        connection.execute(
            """
            INSERT INTO ingest_target(
              tenant_id,source_system_id,connector_account_id,target_kind,target_key,
              priority,enabled,refresh_policy,next_due_at
            ) VALUES (%s,%s,%s,'REPOSITORY',%s,'HOT',%s,%s,
                      CASE WHEN %s THEN now() ELSE NULL END)
            ON CONFLICT(tenant_id,source_system_id,target_kind,target_key)
            DO UPDATE SET connector_account_id=EXCLUDED.connector_account_id,
                          priority='HOT',enabled=EXCLUDED.enabled,
                          refresh_policy=ingest_target.refresh_policy || EXCLUDED.refresh_policy,
                          next_due_at=CASE WHEN EXCLUDED.enabled THEN now() ELSE NULL END,
                          updated_at=now()
            """,
            (
                binding.tenant_id,
                binding.source_system_id,
                binding.connector_account_id,
                target_key,
                enabled,
                Jsonb(repository.refresh_policy(snapshot.installation_id)),
                enabled,
            ),
        )
    removed = connection.execute(
        """
        UPDATE ingest_target
        SET enabled=false,next_due_at=NULL,
            refresh_policy=refresh_policy || jsonb_build_object(
              'removed_from_installation',true,'removed_at',now()
            ),updated_at=now()
        WHERE tenant_id=%s AND source_system_id=%s AND connector_account_id=%s
          AND target_kind='REPOSITORY' AND enabled
          AND NOT (target_key=ANY(%s::text[]))
        RETURNING id
        """,
        (
            binding.tenant_id,
            binding.source_system_id,
            binding.connector_account_id,
            target_keys,
        ),
    ).fetchall()
    removed_ids = [row["id"] for row in removed]
    cancelled = []
    if removed_ids:
        cancelled = connection.execute(
            """
            UPDATE ingest_run
            SET status='CANCELLED',completed_at=now(),lease_owner=NULL,lease_expires_at=NULL,
                error_class='INSTALLATION_REPOSITORY_REMOVED',
                error_detail=jsonb_build_object('installation_id',%s::text)
            WHERE ingest_target_id=ANY(%s::uuid[]) AND status='PENDING'
            RETURNING id
            """,
            (snapshot.installation_id, removed_ids),
        ).fetchall()
    connection.execute(
        """
        INSERT INTO ingest_cursor(
          tenant_id,ingest_target_id,cursor_kind,cursor_value,source_revision
        )
        SELECT %s,id,'GITHUB_INSTALLATION_RECONCILIATION',%s,%s
        FROM ingest_target
        WHERE tenant_id=%s AND source_system_id=%s AND connector_account_id=%s
          AND target_kind='GITHUB_INSTALLATION' AND target_key=%s
        ON CONFLICT(ingest_target_id,cursor_kind)
        DO UPDATE SET cursor_value=EXCLUDED.cursor_value,
                      source_revision=EXCLUDED.source_revision,updated_at=now()
        """,
        (
            binding.tenant_id,
            Jsonb(
                {
                    "installation_id": snapshot.installation_id,
                    "repository_count": snapshot.observed_total,
                    "page_count": snapshot.page_count,
                    "response_etag": snapshot.response_etag,
                }
            ),
            snapshot.source_revision,
            binding.tenant_id,
            binding.source_system_id,
            binding.connector_account_id,
            _external_account_key(snapshot.installation_id),
        ),
    )
    connection.execute(
        "UPDATE connector_account SET updated_at=now() WHERE id=%s",
        (binding.connector_account_id,),
    )
    created_count = sum(key not in existing_keys for key in target_keys)
    return ReconciliationResult(
        connector_account_id=str(binding.connector_account_id),
        installation_id=snapshot.installation_id,
        source_revision=snapshot.source_revision,
        repository_count=len(target_keys),
        created_count=created_count,
        updated_count=len(target_keys) - created_count,
        removed_count=len(removed_ids),
        cancelled_run_count=len(cancelled),
    )


def revoke_installation(
    database_url: str,
    *,
    tenant_key: str,
    installation_id: str,
) -> RevocationResult:
    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        return revoke_installation_connection(
            connection, tenant_key=tenant_key, installation_id=installation_id,
        )


def revoke_installation_connection(
    connection: Connection[dict[str, Any]],
    *,
    tenant_key: str,
    installation_id: str,
) -> RevocationResult:
    binding = connector_binding_connection(
        connection,
        tenant_key=tenant_key,
        installation_id=installation_id,
        for_update=True,
        require_active=False,
    )
    targets = connection.execute(
        """
        UPDATE ingest_target
        SET enabled=false,next_due_at=NULL,
            refresh_policy=refresh_policy || jsonb_build_object(
              'installation_revoked',true,'revoked_at',now()
            ),updated_at=now()
        WHERE connector_account_id=%s AND enabled
        RETURNING id
        """,
        (binding.connector_account_id,),
    ).fetchall()
    target_ids = [row["id"] for row in targets]
    cancelled = []
    if target_ids:
        cancelled = connection.execute(
            """
            UPDATE ingest_run
            SET status='CANCELLED',completed_at=now(),lease_owner=NULL,lease_expires_at=NULL,
                error_class='INSTALLATION_REVOKED',
                error_detail=jsonb_build_object('installation_id',%s::text)
            WHERE ingest_target_id=ANY(%s::uuid[]) AND status='PENDING'
            RETURNING id
            """,
            (installation_id, target_ids),
        ).fetchall()
    connection.execute(
        "UPDATE connector_account SET status='REVOKED',updated_at=now() WHERE id=%s",
        (binding.connector_account_id,),
    )
    return RevocationResult(
        connector_account_id=str(binding.connector_account_id),
        installation_id=installation_id,
        disabled_target_count=len(targets),
        cancelled_run_count=len(cancelled),
    )


def validate_credential_reference(value: str) -> None:
    if not isinstance(value, str) or len(value) > 1024 or any(character.isspace() for character in value):
        raise ValueError("credential_reference must be a non-secret provider reference")
    parsed = urlsplit(value)
    if (
        parsed.scheme not in REFERENCE_SCHEMES
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or not (parsed.netloc or parsed.path.strip("/"))
    ):
        raise ValueError("credential_reference must use an approved secret-provider URI")


def validate_permissions(values: list[str]) -> list[str]:
    if not isinstance(values, list) or not values:
        raise ValueError("GitHub App permissions are required")
    if any(not isinstance(value, str) or not PERMISSION.fullmatch(value) for value in values):
        raise ValueError("GitHub App permissions must use name:read or name:write")
    normalized = sorted(set(values))
    missing = REQUIRED_PERMISSIONS - set(normalized)
    if missing:
        raise ValueError(f"GitHub App permissions are missing: {', '.join(sorted(missing))}")
    return normalized


def resolve_environment_credential(
    credential_reference: str,
    environment: Mapping[str, str] | None = None,
) -> str:
    validate_credential_reference(credential_reference)
    parsed = urlsplit(credential_reference)
    if parsed.scheme != "env" or parsed.path not in {"", "/"}:
        raise ValueError("this runtime can resolve only env:// credential references")
    variable = parsed.netloc
    if not ENVIRONMENT_NAME.fullmatch(variable):
        raise ValueError("env credential reference contains an invalid variable name")
    source = environment if environment is not None else os.environ
    value = source.get(variable)
    if value is None or not value.strip():
        raise ValueError(f"credential reference is not available in the runtime: {variable}")
    return value.strip()


def as_json(value: object) -> dict[str, Any]:
    return asdict(value)


def _external_account_key(installation_id: str) -> str:
    validate_installation_id(installation_id)
    return f"{EXTERNAL_ACCOUNT_PREFIX}{installation_id}"
