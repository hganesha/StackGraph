from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping
from uuid import UUID

import psycopg
from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .evidence_store import EvidenceStore
from .github_installation import OWNER_NAME, REPOSITORY_NAME
from .github_installation_store import EXTERNAL_ACCOUNT_PREFIX, revoke_installation_connection
from .github_webhook import VerifiedGitHubWebhook


GIT_REVISION = re.compile(r"^[a-f0-9]{40,64}$")


@dataclass(frozen=True, slots=True)
class WebhookProcessingResult:
    delivery_id: str
    status: str
    replayed: bool
    target_id: str | None
    run_id: str | None
    reason: str | None


@dataclass(frozen=True, slots=True)
class _ConnectorContext:
    tenant_id: UUID
    tenant_key: str
    source_system_id: UUID
    connector_account_id: UUID
    connector_status: str


def process_github_webhook(
    database_url: str,
    webhook: VerifiedGitHubWebhook,
    *,
    evidence_store: EvidenceStore,
) -> WebhookProcessingResult:
    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        return process_github_webhook_connection(
            connection, webhook, evidence_store=evidence_store,
        )


def process_github_webhook_connection(
    connection: Connection[dict[str, Any]],
    webhook: VerifiedGitHubWebhook,
    *,
    evidence_store: EvidenceStore,
) -> WebhookProcessingResult:
    if webhook.installation_id is None:
        raise ValueError("GitHub webhook event cannot be routed without an installation")
    context = _connector_context(connection, webhook.installation_id)
    stored = evidence_store.put_bytes(
        context.tenant_key,
        webhook.raw_body,
        media_type="application/vnd.github.webhook+json",
        expected_hash=webhook.body_hash,
    )
    inserted = connection.execute(
        """
        INSERT INTO webhook_delivery(
          tenant_id,source_system_id,provider_delivery_id,event_type,event_action,
          signature_verified,headers,body_hash,blob_uri,status
        ) VALUES (%s,%s,%s,%s,%s,true,%s,%s,%s,'PROCESSING')
        ON CONFLICT(source_system_id,provider_delivery_id) DO NOTHING
        RETURNING id
        """,
        (
            context.tenant_id,
            context.source_system_id,
            webhook.delivery_id,
            webhook.event_type,
            webhook.event_action,
            Jsonb(dict(webhook.safe_headers)),
            webhook.body_hash,
            stored.uri,
        ),
    ).fetchone()
    if inserted is None:
        existing = connection.execute(
            """
            SELECT status,event_type,event_action,body_hash,blob_uri
            FROM webhook_delivery
            WHERE source_system_id=%s AND provider_delivery_id=%s
            FOR UPDATE
            """,
            (context.source_system_id, webhook.delivery_id),
        ).fetchone()
        if existing is None:
            raise RuntimeError("webhook delivery replay could not be resolved")
        if (
            existing["event_type"] != webhook.event_type
            or existing["event_action"] != webhook.event_action
            or existing["body_hash"] != webhook.body_hash
            or existing["blob_uri"] != stored.uri
        ):
            raise ValueError("GitHub delivery ID conflicts with different webhook content")
        if existing["status"] in {"PROCESSED", "IGNORED"}:
            return WebhookProcessingResult(
                webhook.delivery_id,
                existing["status"],
                True,
                None,
                None,
                "duplicate delivery",
            )

    target_id: UUID | None = None
    run_id: UUID | None = None
    reason: str | None = None
    status = "PROCESSED"
    if context.connector_status != "ACTIVE" and webhook.event_type != "installation":
        status = "IGNORED"
        reason = f"connector is {context.connector_status.lower()}"
    elif webhook.event_type == "push":
        target_id, run_id, reason = _route_push(connection, context, webhook)
        if target_id is None:
            status = "IGNORED"
    elif webhook.event_type == "installation_repositories":
        _route_installation_repositories(connection, context, webhook)
    elif webhook.event_type == "repository":
        target_id = _route_repository(connection, context, webhook)
    elif webhook.event_type == "installation":
        if webhook.event_action == "deleted":
            revoke_installation_connection(
                connection,
                tenant_key=context.tenant_key,
                installation_id=webhook.installation_id,
            )
        elif webhook.event_action == "suspend" and context.connector_status == "ACTIVE":
            _suspend_installation(connection, context)
        elif (
            webhook.event_action == "unsuspend"
            and context.connector_status in {"ACTIVE", "DISABLED"}
        ):
            _activate_installation(connection, context)
        elif (
            webhook.event_action in {"created", "new_permissions_accepted"}
            and context.connector_status == "ACTIVE"
        ):
            _schedule_installation_reconciliation(connection, context)
        else:
            status = "IGNORED"
            reason = "installation action requires active registration"
    else:
        status = "IGNORED"
        reason = "event type is not routed"
    connection.execute(
        """
        UPDATE webhook_delivery
        SET status=%s,processed_at=now(),error=NULL
        WHERE source_system_id=%s AND provider_delivery_id=%s
        """,
        (status, context.source_system_id, webhook.delivery_id),
    )
    return WebhookProcessingResult(
        delivery_id=webhook.delivery_id,
        status=status,
        replayed=False,
        target_id=str(target_id) if target_id is not None else None,
        run_id=str(run_id) if run_id is not None else None,
        reason=reason,
    )


def _connector_context(
    connection: Connection[dict[str, Any]], installation_id: str,
) -> _ConnectorContext:
    rows = connection.execute(
        """
        SELECT tenant.id tenant_id,tenant.tenant_key,source.id source_system_id,
               connector.id connector_account_id,connector.status connector_status
        FROM connector_account connector
        JOIN tenant ON tenant.id=connector.tenant_id
        JOIN source_system source ON source.id=connector.source_system_id
        WHERE connector.external_account_key=%s AND tenant.status='ACTIVE'
        FOR UPDATE OF connector
        """,
        (f"{EXTERNAL_ACCOUNT_PREFIX}{installation_id}",),
    ).fetchall()
    if not rows:
        raise ValueError("GitHub webhook installation is not registered")
    if len(rows) != 1:
        raise ValueError("GitHub webhook installation is ambiguously registered")
    row = rows[0]
    return _ConnectorContext(
        tenant_id=row["tenant_id"],
        tenant_key=row["tenant_key"],
        source_system_id=row["source_system_id"],
        connector_account_id=row["connector_account_id"],
        connector_status=row["connector_status"],
    )


def _route_push(
    connection: Connection[dict[str, Any]],
    context: _ConnectorContext,
    webhook: VerifiedGitHubWebhook,
) -> tuple[UUID | None, UUID | None, str | None]:
    repository_id, policy = _repository_policy(webhook.payload, webhook.installation_id)
    default_branch = policy["default_branch"]
    if webhook.payload.get("ref") != f"refs/heads/{default_branch}":
        return None, None, "push is not for the default branch"
    source_revision = webhook.payload.get("after")
    if not isinstance(source_revision, str) or not GIT_REVISION.fullmatch(source_revision):
        raise ValueError("GitHub push webhook has an invalid after revision")
    target_key = f"github:repo:{webhook.installation_id}/{repository_id}"
    target = connection.execute(
        """
        INSERT INTO ingest_target(
          tenant_id,source_system_id,connector_account_id,target_kind,target_key,
          priority,enabled,refresh_policy,desired_source_revision,next_due_at
        ) VALUES (%s,%s,%s,'REPOSITORY',%s,'HOT',true,%s,%s,now())
        ON CONFLICT(tenant_id,source_system_id,target_kind,target_key)
        DO UPDATE SET connector_account_id=EXCLUDED.connector_account_id,
                      priority='HOT',enabled=true,
                      refresh_policy=ingest_target.refresh_policy || EXCLUDED.refresh_policy,
                      desired_source_revision=EXCLUDED.desired_source_revision,
                      next_due_at=now(),updated_at=now()
        RETURNING id
        """,
        (
            context.tenant_id,
            context.source_system_id,
            context.connector_account_id,
            target_key,
            Jsonb(policy),
            source_revision,
        ),
    ).fetchone()
    assert target is not None
    connection.execute(
        """
        UPDATE ingest_run
        SET status='CANCELLED',completed_at=now(),
            error_class='SUPERSEDED_GITHUB_REVISION',
            error_detail=jsonb_build_object('superseded_by',%s::text)
        WHERE ingest_target_id=%s AND status='PENDING'
          AND requested_source_revision IS DISTINCT FROM %s
        """,
        (source_revision, target["id"], source_revision),
    )
    existing = connection.execute(
        """
        SELECT id FROM ingest_run
        WHERE ingest_target_id=%s AND requested_source_revision=%s
          AND status IN ('PENDING','RUNNING','SUCCEEDED','PARTIAL')
        ORDER BY created_at DESC LIMIT 1
        """,
        (target["id"], source_revision),
    ).fetchone()
    if existing is not None:
        return target["id"], existing["id"], "revision already scheduled"
    run = connection.execute(
        """
        INSERT INTO ingest_run(
          tenant_id,ingest_target_id,trigger_kind,requested_source_revision,status
        ) VALUES (%s,%s,'WEBHOOK',%s,'PENDING') RETURNING id
        """,
        (context.tenant_id, target["id"], source_revision),
    ).fetchone()
    assert run is not None
    return target["id"], run["id"], None


def _route_installation_repositories(
    connection: Connection[dict[str, Any]],
    context: _ConnectorContext,
    webhook: VerifiedGitHubWebhook,
) -> None:
    for key, enabled in (("repositories_added", True), ("repositories_removed", False)):
        repositories = webhook.payload.get(key, [])
        if not isinstance(repositories, list):
            raise ValueError(f"GitHub webhook {key} must be an array")
        for repository in repositories:
            repository_id = _repository_id(repository)
            target_key = f"github:repo:{webhook.installation_id}/{repository_id}"
            if enabled:
                _, policy = _repository_policy(
                    {"repository": repository}, webhook.installation_id,
                )
                connection.execute(
                    """
                    INSERT INTO ingest_target(
                      tenant_id,source_system_id,connector_account_id,target_kind,target_key,
                      priority,enabled,refresh_policy,next_due_at
                    ) VALUES (%s,%s,%s,'REPOSITORY',%s,'HOT',true,%s,now())
                    ON CONFLICT(tenant_id,source_system_id,target_kind,target_key)
                    DO UPDATE SET connector_account_id=EXCLUDED.connector_account_id,
                                  enabled=true,refresh_policy=ingest_target.refresh_policy || EXCLUDED.refresh_policy,
                                  next_due_at=now(),updated_at=now()
                    """,
                    (
                        context.tenant_id,
                        context.source_system_id,
                        context.connector_account_id,
                        target_key,
                        Jsonb(policy),
                    ),
                )
            else:
                removed = connection.execute(
                    """
                    UPDATE ingest_target
                    SET enabled=false,next_due_at=NULL,
                        refresh_policy=refresh_policy || jsonb_build_object(
                          'removed_from_installation',true,'removed_at',now()
                        ),updated_at=now()
                    WHERE tenant_id=%s AND source_system_id=%s
                      AND connector_account_id=%s AND target_key=%s
                    RETURNING id
                    """,
                    (
                        context.tenant_id,
                        context.source_system_id,
                        context.connector_account_id,
                        target_key,
                    ),
                ).fetchone()
                if removed is not None:
                    _cancel_pending_for_target(
                        connection,
                        removed["id"],
                        error_class="INSTALLATION_REPOSITORY_REMOVED",
                    )
    _schedule_installation_reconciliation(connection, context)


def _route_repository(
    connection: Connection[dict[str, Any]],
    context: _ConnectorContext,
    webhook: VerifiedGitHubWebhook,
) -> UUID | None:
    repository_id = _repository_id(webhook.payload.get("repository"))
    target_key = f"github:repo:{webhook.installation_id}/{repository_id}"
    target = None
    if webhook.event_action in {"deleted", "transferred"}:
        target = connection.execute(
            """
            UPDATE ingest_target
            SET enabled=false,next_due_at=NULL,
                refresh_policy=refresh_policy || jsonb_build_object(
                  'repository_event_action',%s::text,'repository_event_at',now()
                ),updated_at=now()
            WHERE tenant_id=%s AND source_system_id=%s
              AND connector_account_id=%s AND target_key=%s
            RETURNING id
            """,
            (
                webhook.event_action,
                context.tenant_id,
                context.source_system_id,
                context.connector_account_id,
                target_key,
            ),
        ).fetchone()
        if target is not None:
            _cancel_pending_for_target(
                connection,
                target["id"],
                error_class="GITHUB_REPOSITORY_REMOVED",
            )
    _schedule_installation_reconciliation(connection, context)
    return target["id"] if target is not None else None


def _schedule_installation_reconciliation(
    connection: Connection[dict[str, Any]], context: _ConnectorContext,
) -> None:
    connection.execute(
        """
        UPDATE ingest_target
        SET enabled=true,next_due_at=now(),updated_at=now()
        WHERE connector_account_id=%s AND target_kind='GITHUB_INSTALLATION'
        """,
        (context.connector_account_id,),
    )


def _suspend_installation(
    connection: Connection[dict[str, Any]], context: _ConnectorContext,
) -> None:
    targets = connection.execute(
        """
        UPDATE ingest_target
        SET enabled=false,next_due_at=NULL,
            refresh_policy=refresh_policy || jsonb_build_object(
              'installation_suspended',true,'suspended_at',now()
            ),updated_at=now()
        WHERE connector_account_id=%s AND enabled
        RETURNING id
        """,
        (context.connector_account_id,),
    ).fetchall()
    for target in targets:
        _cancel_pending_for_target(
            connection, target["id"], error_class="INSTALLATION_SUSPENDED",
        )
    connection.execute(
        "UPDATE connector_account SET status='DISABLED',updated_at=now() WHERE id=%s",
        (context.connector_account_id,),
    )


def _activate_installation(
    connection: Connection[dict[str, Any]], context: _ConnectorContext,
) -> None:
    connection.execute(
        "UPDATE connector_account SET status='ACTIVE',updated_at=now() WHERE id=%s",
        (context.connector_account_id,),
    )
    connection.execute(
        """
        UPDATE ingest_target
        SET enabled=true,next_due_at=now(),
            refresh_policy=refresh_policy || jsonb_build_object(
              'installation_suspended',false,'unsuspended_at',now()
            ),updated_at=now()
        WHERE connector_account_id=%s AND target_kind='GITHUB_INSTALLATION'
        """,
        (context.connector_account_id,),
    )


def _cancel_pending_for_target(
    connection: Connection[dict[str, Any]],
    target_id: UUID,
    *,
    error_class: str,
) -> None:
    connection.execute(
        """
        UPDATE ingest_run
        SET status='CANCELLED',completed_at=now(),lease_owner=NULL,lease_expires_at=NULL,
            error_class=%s,error_detail='{}'
        WHERE ingest_target_id=%s AND status='PENDING'
        """,
        (error_class, target_id),
    )


def _repository_policy(
    payload: Mapping[str, Any], installation_id: str,
) -> tuple[str, dict[str, Any]]:
    repository = payload.get("repository")
    if not isinstance(repository, Mapping):
        raise ValueError("GitHub webhook has no repository object")
    repository_id = _repository_id(repository)
    name = repository.get("name")
    full_name = repository.get("full_name")
    owner = repository.get("owner")
    default_branch = repository.get("default_branch")
    if not isinstance(name, str) or not REPOSITORY_NAME.fullmatch(name):
        raise ValueError("GitHub webhook repository has no name")
    if (
        not isinstance(owner, Mapping)
        or not isinstance(owner.get("login"), str)
        or not OWNER_NAME.fullmatch(owner["login"])
    ):
        raise ValueError("GitHub webhook repository has no owner")
    if full_name != f"{owner['login']}/{name}":
        raise ValueError("GitHub webhook repository full_name does not match owner/name")
    if not isinstance(default_branch, str) or not default_branch:
        raise ValueError("GitHub webhook repository has no default branch")
    visibility = repository.get("visibility", "private" if repository.get("private") else "public")
    if visibility not in {"public", "private", "internal"}:
        raise ValueError("GitHub webhook repository has invalid visibility")
    return repository_id, {
        "provider": "github",
        "installation_id": installation_id,
        "repository_id": repository_id,
        "owner": owner["login"],
        "name": name,
        "full_name": full_name,
        "default_branch": default_branch,
        "visibility": str(visibility).upper(),
        "archived": bool(repository.get("archived", False)),
        "disabled": bool(repository.get("disabled", False)),
        "removed_from_installation": False,
        "installation_revoked": False,
        "cadence_seconds": 3600,
    }


def _repository_id(repository: object) -> str:
    if not isinstance(repository, Mapping):
        raise ValueError("GitHub webhook has no repository object")
    repository_id = str(repository.get("id") or "")
    if not repository_id.isdigit() or repository_id.startswith("0"):
        raise ValueError("GitHub webhook repository has an invalid ID")
    return repository_id
