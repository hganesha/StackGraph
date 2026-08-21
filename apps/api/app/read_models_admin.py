from __future__ import annotations

import base64
import hashlib
import json
import os
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

import httpx
from psycopg.errors import UniqueViolation

from app.errors import APIError
from app.models import (
    AIProviderConfiguration,
    AIProviderConfigurationUpdateRequest,
    AIProviderConnectionTest,
    Citation,
    Connector,
    ConnectorList,
    ConnectorRegisterRequest,
    ConnectorUpdateRequest,
    GitHubInstallationConnectRequest,
    GitHubRepositoryConnectRequest,
    GitHubRepositoryOption,
    GitHubRepositoryOptionList,
    MemberInviteRequest,
    MemberUpdateRequest,
    PageInfo,
    ProviderQuota,
    RescanJob,
    RescanJobList,
    RescanRequest,
    ReviewQueue,
    ReviewQueueItem,
    ReviewQueueItemType,
    ScanPolicy,
    ScanPolicyUpdateRequest,
    ScanStatus,
    ServiceControlRequest,
    ServiceStatus,
    ServiceStatusList,
    TenantMember,
    TenantMemberList,
)


_REVIEW_PATHS: dict[str, str] = {
    "IDENTITY_ASSERTION": "/identity-assertions/{id}/review",
    "CAPABILITY_INFERENCE": "/capability-inferences/{id}/review",
    "DUPLICATE_CAPABILITY": "/duplicate-capability-candidates/{id}/review",
    "MODERNIZATION_CANDIDATE": "/modernization-candidates/{id}/review",
    "MODERNIZATION_RECOMMENDATION": "/modernization-recommendations/{id}/review",
}

_RAW_SECRET_MARKERS: tuple[str, ...] = (
    "ghp_", "gho_", "ghu_", "ghs_", "ghr_", "github_pat_", "xox", "-----BEGIN", "AKIA",
)

_CONTROLLABLE_SERVICES = frozenset({
    "github-webhook", "github-control-loop", "projection", "intelligence",
})

_OPENROUTER_INTELLIGENCE_REQUIRED_PARAMETERS = frozenset({"max_tokens", "response_format"})


def _github_api_base_url() -> str:
    base_url = os.getenv("STACKGRAPH_GITHUB_API_URL", "https://api.github.com").rstrip("/")
    parsed = urlsplit(base_url)
    is_local = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    allow_insecure_local = os.getenv("STACKGRAPH_GITHUB_ALLOW_INSECURE_LOCALHOST") == "true"
    if parsed.query or parsed.fragment or parsed.username or parsed.password:
        raise ValueError("GitHub API URL cannot contain credentials, a query, or a fragment")
    if parsed.scheme != "https" and not (
        parsed.scheme == "http" and is_local and allow_insecure_local
    ):
        raise ValueError("GitHub API URL must use HTTPS")
    if not parsed.hostname:
        raise ValueError("GitHub API URL must include a host")
    return base_url


def _number(value: Decimal | float | int | None, default: float = 0.0) -> float:
    return float(value) if value is not None else default


def _confidence_label(value: Decimal | float) -> str:
    confidence = float(value)
    if confidence >= 0.85:
        return "HIGH"
    if confidence >= 0.6:
        return "MEDIUM"
    return "LOW"


def _encode_cursor(kind: str, **values: Any) -> str:
    payload = json.dumps(
        {"v": 1, "kind": kind, **values},
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def _decode_cursor(cursor: str | None, kind: str) -> dict[str, Any] | None:
    if cursor is None:
        return None
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded).decode())
        if not isinstance(payload, dict) or payload.get("v") != 1 or payload.get("kind") != kind:
            raise ValueError
        return payload
    except (ValueError, TypeError, json.JSONDecodeError, UnicodeDecodeError) as error:
        raise APIError(400, "INVALID_CURSOR", "The pagination cursor is invalid.") from error


class AdminReadModelsMixin:
    database: Any
    credential_encryption_key: str
    # --- Review queue ------------------------------------------------------
    # A read-only aggregation over the five reviewable sources. Each source is filtered to its
    # pending state, projected to a common shape, then keyset-paginated newest-first. Submitting
    # a decision still goes to each source's own /review route (carried on `review_path`).

    async def review_queue(
        self,
        *,
        tenant_id: UUID | None,
        item_types: list[ReviewQueueItemType] | None,
        repository_id: UUID | None,
        cursor: str | None,
        limit: int,
    ) -> ReviewQueue:
        if tenant_id is None:
            raise APIError(400, "TENANT_REQUIRED", "A tenant ID is required to read the review queue.")
        decoded = _decode_cursor(cursor, "review-queue")
        rows = await self.database.fetch_all(
            """
            WITH queue AS (
              SELECT ia.id AS item_id, 'IDENTITY_ASSERTION' AS item_type, ia.review_state,
                     NULL::uuid AS repository_id, ia.confidence, ia.version, ia.created_at,
                     concat(le.name, ' ↔ ', re.name) AS title,
                     concat('Identity bridge via ', ia.method) AS summary
              FROM identity_assertion ia
              JOIN entity le ON le.id = ia.left_entity_id
              JOIN entity re ON re.id = ia.right_entity_id
              WHERE ia.review_state = 'POSSIBLE'
              UNION ALL
              SELECT ci.id, 'CAPABILITY_INFERENCE', ci.review_state, ci.repository_entity_id,
                     ci.confidence, ci.version, ci.created_at, cd.name, ci.rationale
              FROM capability_inference ci
              JOIN capability_definition cd ON cd.id = ci.capability_definition_id
              WHERE ci.review_state = 'UNREVIEWED'
              UNION ALL
              SELECT dc.id, 'DUPLICATE_CAPABILITY', dc.review_state, dc.repository_entity_id,
                     dc.confidence, dc.version, dc.created_at,
                     concat('Duplicate capability: ', cd.name), dc.summary
              FROM duplicate_capability_candidate dc
              JOIN capability_definition cd ON cd.id = dc.capability_definition_id
              WHERE dc.review_state = 'UNREVIEWED'
              UNION ALL
              SELECT mc.id, 'MODERNIZATION_CANDIDATE', mc.review_state, mc.repository_entity_id,
                     mc.confidence, mc.version, mc.created_at, mc.candidate_kind, mc.summary
              FROM modernization_candidate mc
              WHERE mc.review_state = 'UNREVIEWED'
              UNION ALL
              SELECT mr.id, 'MODERNIZATION_RECOMMENDATION', mr.review_state, mr.repository_entity_id,
                     mr.confidence, mr.version, mr.created_at, mr.title, mr.objective
              FROM modernization_recommendation mr
              WHERE mr.review_state = 'UNREVIEWED'
            )
            SELECT * FROM queue
            WHERE (%(types)s::text[] IS NULL OR item_type = ANY(%(types)s))
              AND (%(repository_id)s::uuid IS NULL OR repository_id = %(repository_id)s)
              AND (%(created_before)s::timestamptz IS NULL
                   OR created_at < %(created_before)s
                   OR (created_at = %(created_before)s AND item_id < %(id_before)s))
            ORDER BY created_at DESC, item_id DESC
            LIMIT %(limit)s
            """,
            {
                "types": list(item_types) if item_types else None,
                "repository_id": repository_id,
                "created_before": decoded["created_before"] if decoded else None,
                "id_before": decoded["id_before"] if decoded else None,
                "limit": limit + 1,
            },
            tenant_id=tenant_id,
        )
        has_next = len(rows) > limit
        page = rows[:limit]
        next_cursor = None
        if has_next and page:
            last = page[-1]
            next_cursor = _encode_cursor(
                "review-queue",
                created_before=last["created_at"].isoformat(),
                id_before=str(last["item_id"]),
            )
        count_rows = await self.database.fetch_all(
            """
            SELECT 'IDENTITY_ASSERTION' AS item_type, count(*) AS n
              FROM identity_assertion WHERE review_state = 'POSSIBLE'
            UNION ALL SELECT 'CAPABILITY_INFERENCE', count(*)
              FROM capability_inference WHERE review_state = 'UNREVIEWED'
            UNION ALL SELECT 'DUPLICATE_CAPABILITY', count(*)
              FROM duplicate_capability_candidate WHERE review_state = 'UNREVIEWED'
            UNION ALL SELECT 'MODERNIZATION_CANDIDATE', count(*)
              FROM modernization_candidate WHERE review_state = 'UNREVIEWED'
            UNION ALL SELECT 'MODERNIZATION_RECOMMENDATION', count(*)
              FROM modernization_recommendation WHERE review_state = 'UNREVIEWED'
            """,
            tenant_id=tenant_id,
        )
        counts = {row["item_type"]: int(row["n"]) for row in count_rows}
        return ReviewQueue(
            as_of=datetime.now(UTC),
            counts=counts,
            items=[
                ReviewQueueItem(
                    item_id=row["item_id"],
                    item_type=row["item_type"],
                    review_state=row["review_state"],
                    title=row["title"],
                    summary=row["summary"] or None,
                    confidence=_number(row["confidence"]),
                    confidence_band=_confidence_label(row["confidence"]),
                    repository_id=row["repository_id"],
                    version=row["version"],
                    created_at=row["created_at"],
                    review_path=_REVIEW_PATHS[row["item_type"]].format(id=row["item_id"]),
                )
                for row in page
            ],
            page_info=PageInfo(has_next_page=has_next, next_cursor=next_cursor),
        )

    # --- Admin: members & roles -------------------------------------------
    # The workspace roster and RBAC-management surface. Every mutation writes an admin_audit_log
    # row inside the same transaction. Role/status changes refuse to strand a tenant without an
    # active admin.

    async def list_tenant_members(self, *, tenant_id: UUID | None) -> TenantMemberList:
        if tenant_id is None:
            raise APIError(400, "TENANT_REQUIRED", "A tenant ID is required to list members.")
        rows = await self.database.fetch_all(
            "SELECT * FROM tenant_member ORDER BY display_name, actor_key",
            tenant_id=tenant_id,
        )
        return TenantMemberList(members=[self._tenant_member(row) for row in rows])

    async def invite_tenant_member(
        self, request: MemberInviteRequest, *, tenant_id: UUID | None, actor_key: str,
    ) -> TenantMember:
        if tenant_id is None:
            raise APIError(400, "TENANT_REQUIRED", "A tenant ID is required to invite a member.")
        async with self.database.session(tenant_id) as connection:
            existing = await connection.execute(
                "SELECT 1 FROM tenant_member WHERE actor_key = %s", (request.actor_key,),
            )
            if await existing.fetchone() is not None:
                raise APIError(
                    409, "MEMBER_EXISTS", "A member with this actor key already exists.",
                    {"actor_key": request.actor_key},
                )
            cursor = await connection.execute(
                """
                INSERT INTO tenant_member
                  (tenant_id, actor_key, display_name, email, role, status, created_by)
                VALUES (%s, %s, %s, %s, %s, 'INVITED', %s)
                RETURNING *
                """,
                (tenant_id, request.actor_key, request.display_name, request.email,
                 request.role, actor_key),
            )
            row = await cursor.fetchone()
            assert row is not None
            await self._write_admin_audit(
                connection, tenant_id=tenant_id, actor_key=actor_key, action="member.invite",
                target_kind="tenant_member", target_id=row["id"],
                detail={"actor_key": request.actor_key, "role": request.role},
            )
        return self._tenant_member(row)

    async def update_tenant_member(
        self, member_id: UUID, request: MemberUpdateRequest, *, tenant_id: UUID | None, actor_key: str,
    ) -> TenantMember:
        if tenant_id is None:
            raise APIError(400, "TENANT_REQUIRED", "A tenant ID is required to update a member.")
        async with self.database.session(tenant_id) as connection:
            cursor = await connection.execute(
                "SELECT * FROM tenant_member WHERE id = %s FOR UPDATE", (member_id,),
            )
            member = await cursor.fetchone()
            if member is None:
                raise APIError(404, "MEMBER_NOT_FOUND", "The member was not found.")
            new_role = request.role or member["role"]
            new_status = request.status or member["status"]
            demotes_admin = member["role"] == "admin" and member["status"] == "ACTIVE" and (
                new_role != "admin" or new_status != "ACTIVE"
            )
            if demotes_admin:
                await self._guard_last_admin(connection, exclude_id=member_id)
            await connection.execute(
                "UPDATE tenant_member SET role = %s, status = %s, updated_at = now() WHERE id = %s",
                (new_role, new_status, member_id),
            )
            await self._write_admin_audit(
                connection, tenant_id=tenant_id, actor_key=actor_key, action="member.update",
                target_kind="tenant_member", target_id=member_id,
                detail={"role": new_role, "status": new_status},
            )
            cursor = await connection.execute("SELECT * FROM tenant_member WHERE id = %s", (member_id,))
            row = await cursor.fetchone()
        return self._tenant_member(row)

    async def remove_tenant_member(
        self, member_id: UUID, *, tenant_id: UUID | None, actor_key: str,
    ) -> TenantMember:
        if tenant_id is None:
            raise APIError(400, "TENANT_REQUIRED", "A tenant ID is required to remove a member.")
        async with self.database.session(tenant_id) as connection:
            cursor = await connection.execute(
                "SELECT * FROM tenant_member WHERE id = %s FOR UPDATE", (member_id,),
            )
            member = await cursor.fetchone()
            if member is None:
                raise APIError(404, "MEMBER_NOT_FOUND", "The member was not found.")
            if member["role"] == "admin" and member["status"] == "ACTIVE":
                await self._guard_last_admin(connection, exclude_id=member_id)
            await connection.execute("DELETE FROM tenant_member WHERE id = %s", (member_id,))
            await self._write_admin_audit(
                connection, tenant_id=tenant_id, actor_key=actor_key, action="member.remove",
                target_kind="tenant_member", target_id=member_id,
                detail={"actor_key": member["actor_key"]},
            )
        return self._tenant_member(member)

    @staticmethod
    async def _guard_last_admin(connection: Any, *, exclude_id: UUID) -> None:
        cursor = await connection.execute(
            "SELECT count(*) AS n FROM tenant_member WHERE role = 'admin' AND status = 'ACTIVE' AND id <> %s",
            (exclude_id,),
        )
        if (await cursor.fetchone())["n"] == 0:
            raise APIError(
                409, "LAST_ADMIN",
                "The workspace must keep at least one active admin.",
            )

    @staticmethod
    def _tenant_member(row: dict[str, Any]) -> TenantMember:
        return TenantMember(
            id=row["id"], actor_key=row["actor_key"], display_name=row["display_name"],
            email=row["email"], role=row["role"], status=row["status"],
            created_at=row["created_at"], updated_at=row["updated_at"],
        )

    # --- Admin: connectors -------------------------------------------------

    async def list_connectors(self, *, tenant_id: UUID | None) -> ConnectorList:
        if tenant_id is None:
            raise APIError(400, "TENANT_REQUIRED", "A tenant ID is required to list connectors.")
        rows = await self.database.fetch_all(
            """
            SELECT connector.*,
                   coalesce(connector.last_synced_at,target.last_success_at) effective_last_synced_at,
                   coalesce(connector.last_error,latest_run.error_detail->>'message') effective_last_error
            FROM connector
            LEFT JOIN ingest_target target
              ON target.id::text=connector.metadata->>'ingest_target_id'
            LEFT JOIN LATERAL (
              SELECT run.error_detail
              FROM ingest_run run
              WHERE run.ingest_target_id=target.id AND run.status='FAILED'
                AND (target.last_success_at IS NULL OR run.completed_at>target.last_success_at)
              ORDER BY run.completed_at DESC NULLS LAST,run.created_at DESC,run.id DESC
              LIMIT 1
            ) latest_run ON true
            ORDER BY connector.updated_at DESC,connector.id DESC
            """,
            tenant_id=tenant_id,
        )
        return ConnectorList(connectors=[self._connector(row) for row in rows])

    async def register_connector(
        self, request: ConnectorRegisterRequest, *, tenant_id: UUID | None, actor_key: str,
    ) -> Connector:
        if tenant_id is None:
            raise APIError(400, "TENANT_REQUIRED", "A tenant ID is required to register a connector.")
        self._reject_raw_secret(request.credential_reference)
        async with self.database.session(tenant_id) as connection:
            existing = await connection.execute(
                "SELECT 1 FROM connector WHERE provider = %s AND external_account_key = %s",
                (request.provider, request.external_account_key),
            )
            if await existing.fetchone() is not None:
                raise APIError(
                    409, "CONNECTOR_EXISTS", "A connector for this provider account already exists.",
                    {"provider": request.provider, "external_account_key": request.external_account_key},
                )
            cursor = await connection.execute(
                """
                INSERT INTO connector
                  (tenant_id, provider, display_name, external_account_key, credential_reference,
                   scopes, created_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (tenant_id, request.provider, request.display_name, request.external_account_key,
                 request.credential_reference, request.scopes, actor_key),
            )
            row = await cursor.fetchone()
            assert row is not None
            await self._write_admin_audit(
                connection, tenant_id=tenant_id, actor_key=actor_key, action="connector.register",
                target_kind="connector", target_id=row["id"], detail={"provider": request.provider},
            )
        return self._connector(row)

    async def connect_github_repository(
        self,
        request: GitHubRepositoryConnectRequest,
        *,
        tenant_id: UUID | None,
        actor_key: str,
    ) -> Connector:
        if tenant_id is None:
            raise APIError(400, "TENANT_REQUIRED", "A tenant ID is required to connect GitHub.")
        self._reject_raw_secret(request.credential_reference)
        owner, name = request.repository.split("/", 1)
        full_name = f"{owner}/{name}"
        normalized_name = full_name.lower()
        external_account_key = f"github:repository:{normalized_name}"
        pending_target_key = f"github:repo-name:{normalized_name}"
        scopes = ["contents:read", "metadata:read"]

        async with self.database.session(tenant_id) as connection:
            existing = await connection.execute(
                "SELECT 1 FROM connector WHERE provider='GITHUB_APP' AND external_account_key=%s",
                (external_account_key,),
            )
            if await existing.fetchone() is not None:
                raise APIError(
                    409,
                    "CONNECTOR_EXISTS",
                    "This GitHub repository is already connected.",
                    {"repository": full_name},
                )

            policy_cursor = await connection.execute(
                "SELECT cadence,enabled FROM scan_policy WHERE tenant_id=%s",
                (tenant_id,),
            )
            policy = await policy_cursor.fetchone()
            cadence = policy["cadence"] if policy is not None else "DAILY"
            schedule_enabled = bool(policy["enabled"] if policy is not None else True) and cadence != "MANUAL"
            cadence_seconds = {
                "HOURLY": 3600,
                "DAILY": 86400,
                "WEEKLY": 604800,
                "MANUAL": 86400,
            }[cadence]

            source_cursor = await connection.execute(
                """
                INSERT INTO source_system(tenant_id,source_key,kind,base_uri,metadata)
                VALUES (%s,'github-app','GITHUB','https://api.github.com',%s::jsonb)
                ON CONFLICT(tenant_id,source_key) DO UPDATE
                  SET base_uri=EXCLUDED.base_uri,
                      metadata=source_system.metadata || EXCLUDED.metadata
                RETURNING id
                """,
                (tenant_id, json.dumps({"provider": "github", "direct_repository": True})),
            )
            source = await source_cursor.fetchone()
            assert source is not None
            account_cursor = await connection.execute(
                """
                INSERT INTO connector_account(
                  tenant_id,source_system_id,external_account_key,credential_reference,
                  permissions,status
                ) VALUES (%s,%s,%s,%s,%s::jsonb,'ACTIVE')
                ON CONFLICT(tenant_id,source_system_id,external_account_key) DO UPDATE
                  SET credential_reference=EXCLUDED.credential_reference,
                      permissions=EXCLUDED.permissions,status='ACTIVE',updated_at=now()
                RETURNING id
                """,
                (
                    tenant_id,
                    source["id"],
                    external_account_key,
                    request.credential_reference,
                    json.dumps(scopes),
                ),
            )
            account = await account_cursor.fetchone()
            assert account is not None
            target_cursor = await connection.execute(
                """
                INSERT INTO ingest_target(
                  tenant_id,source_system_id,connector_account_id,target_kind,target_key,
                  priority,enabled,refresh_policy,next_due_at
                ) VALUES (%s,%s,%s,'REPOSITORY',%s,'HOT',true,%s::jsonb,
                          CASE WHEN %s THEN now() ELSE NULL END)
                ON CONFLICT(tenant_id,source_system_id,target_kind,target_key) DO UPDATE
                  SET connector_account_id=EXCLUDED.connector_account_id,enabled=true,
                      refresh_policy=EXCLUDED.refresh_policy,
                      next_due_at=EXCLUDED.next_due_at,updated_at=now()
                RETURNING id
                """,
                (
                    tenant_id,
                    source["id"],
                    account["id"],
                    pending_target_key,
                    json.dumps({
                        "provider": "github",
                        "direct_repository": True,
                        "owner": owner,
                        "name": name,
                        "full_name": full_name,
                        "cadence_seconds": cadence_seconds,
                        "schedule_enabled": schedule_enabled,
                    }),
                    schedule_enabled,
                ),
            )
            target = await target_cursor.fetchone()
            assert target is not None
            connector_cursor = await connection.execute(
                """
                INSERT INTO connector(
                  tenant_id,provider,display_name,external_account_key,credential_reference,
                  scopes,metadata,created_by
                ) VALUES (%s,'GITHUB_APP',%s,%s,%s,%s,%s::jsonb,%s)
                RETURNING *
                """,
                (
                    tenant_id,
                    full_name,
                    external_account_key,
                    request.credential_reference,
                    scopes,
                    json.dumps({
                        "connection_mode": "DIRECT_REPOSITORY",
                        "ingest_target_id": str(target["id"]),
                    }),
                    actor_key,
                ),
            )
            row = await connector_cursor.fetchone()
            assert row is not None
            # The first sync is explicit, including when the recurring policy is MANUAL.
            await connection.execute(
                """
                INSERT INTO ingest_run(tenant_id,ingest_target_id,trigger_kind,stats)
                SELECT %s,%s,'MANUAL',jsonb_build_object('connector_id',%s::text)
                WHERE NOT EXISTS (
                  SELECT 1 FROM ingest_run
                  WHERE ingest_target_id=%s AND status IN ('PENDING','RUNNING')
                )
                """,
                (tenant_id, target["id"], str(row["id"]), target["id"]),
            )
            await self._write_admin_audit(
                connection,
                tenant_id=tenant_id,
                actor_key=actor_key,
                action="github_repository.connect",
                target_kind="connector",
                target_id=row["id"],
                detail={"repository": full_name, "ingest_target_id": str(target["id"])},
            )
        return self._connector(row)

    async def list_available_github_repositories(
        self, *, tenant_id: UUID | None,
    ) -> GitHubRepositoryOptionList:
        if tenant_id is None:
            raise APIError(400, "TENANT_REQUIRED", "A tenant ID is required to list GitHub repositories.")
        token = os.getenv("GITHUB_TOKEN", "").strip()
        if not token:
            return GitHubRepositoryOptionList(token_configured=False, repositories=[])

        existing_rows = await self.database.fetch_all(
            """
            SELECT DISTINCT lower(repository_name) repository_name
            FROM (
              SELECT replace(connector.external_account_key,'github:repository:','') repository_name
              FROM connector
              WHERE connector.tenant_id=%s AND connector.provider='GITHUB_APP'
                AND connector.status='CONNECTED'
                AND connector.external_account_key LIKE 'github:repository:%%'
              UNION ALL
              SELECT target.refresh_policy->>'full_name' repository_name
              FROM ingest_target target
              JOIN source_system source ON source.id=target.source_system_id
              WHERE target.tenant_id=%s AND source.source_key='github-app'
                AND target.target_kind='REPOSITORY' AND target.enabled
            ) connected
            WHERE nullif(repository_name,'') IS NOT NULL
            """,
            (tenant_id, tenant_id),
            tenant_id=tenant_id,
        )
        existing = {row["repository_name"] for row in existing_rows}
        repositories: dict[str, GitHubRepositoryOption] = {}
        truncated = False
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "StackGraph-admin/1.0",
            "X-GitHub-Api-Version": "2026-03-10",
        }
        try:
            base_url = _github_api_base_url()
            async with httpx.AsyncClient(
                headers=headers,
                timeout=20.0,
                follow_redirects=False,
            ) as client:
                for page in range(1, 101):
                    response = await client.get(
                        f"{base_url}/user/repos",
                        params={
                            "affiliation": "owner,collaborator,organization_member",
                            "sort": "full_name",
                            "direction": "asc",
                            "per_page": "100",
                            "page": str(page),
                        },
                    )
                    if response.status_code in {401, 403}:
                        raise APIError(
                            502,
                            "GITHUB_TOKEN_REJECTED",
                            "GitHub rejected the configured token or its repository-list request.",
                        )
                    response.raise_for_status()
                    payload = response.json()
                    if not isinstance(payload, list):
                        raise ValueError("GitHub repository response is not a list")
                    for item in payload:
                        if not isinstance(item, dict) or not isinstance(item.get("full_name"), str):
                            continue
                        full_name = item["full_name"]
                        normalized_name = full_name.lower()
                        if normalized_name in existing or normalized_name in repositories:
                            continue
                        raw_visibility = item.get("visibility")
                        visibility = (
                            raw_visibility
                            if raw_visibility in {"public", "private", "internal"}
                            else "private" if item.get("private") is True else "public"
                        )
                        default_branch = item.get("default_branch")
                        repositories[normalized_name] = GitHubRepositoryOption(
                            full_name=full_name,
                            visibility=visibility,
                            archived=item.get("archived") is True,
                            default_branch=(
                                default_branch[:255] if isinstance(default_branch, str) else None
                            ),
                        )
                    if len(payload) < 100:
                        break
                else:
                    truncated = True
        except APIError:
            raise
        except (httpx.HTTPError, ValueError) as error:
            raise APIError(
                502,
                "GITHUB_REPOSITORY_DISCOVERY_FAILED",
                "GitHub repositories could not be loaded from the configured token.",
            ) from error

        return GitHubRepositoryOptionList(
            token_configured=True,
            repositories=sorted(repositories.values(), key=lambda repository: repository.full_name.lower()),
            truncated=truncated,
        )

    async def connect_github_installation(
        self,
        request: GitHubInstallationConnectRequest,
        *,
        tenant_id: UUID | None,
        actor_key: str,
    ) -> Connector:
        if tenant_id is None:
            raise APIError(400, "TENANT_REQUIRED", "A tenant ID is required to connect GitHub.")
        installation_id = request.installation_id
        external_account_key = f"github:installation:{installation_id}"
        credential_reference = f"github-app://installation/{installation_id}"
        display_name = request.display_name or f"GitHub installation {installation_id}"
        scopes = ["contents:read", "metadata:read"]

        async with self.database.session(tenant_id) as connection:
            existing = await connection.execute(
                "SELECT 1 FROM connector WHERE provider='GITHUB_APP' AND external_account_key=%s",
                (external_account_key,),
            )
            if await existing.fetchone() is not None:
                raise APIError(
                    409, "CONNECTOR_EXISTS", "This GitHub App installation is already connected.",
                    {"installation_id": installation_id},
                )
            policy_cursor = await connection.execute(
                "SELECT cadence,enabled FROM scan_policy WHERE tenant_id=%s", (tenant_id,),
            )
            policy = await policy_cursor.fetchone()
            cadence = policy["cadence"] if policy is not None else "DAILY"
            schedule_enabled = bool(policy["enabled"] if policy is not None else True) and cadence != "MANUAL"
            cadence_seconds = {
                "HOURLY": 3600, "DAILY": 86400, "WEEKLY": 604800, "MANUAL": 86400,
            }[cadence]
            source_cursor = await connection.execute(
                """
                INSERT INTO source_system(tenant_id,source_key,kind,base_uri,metadata)
                VALUES (%s,'github-app','GITHUB','https://api.github.com',%s::jsonb)
                ON CONFLICT(tenant_id,source_key) DO UPDATE
                  SET base_uri=EXCLUDED.base_uri,metadata=source_system.metadata || EXCLUDED.metadata
                RETURNING id
                """,
                (tenant_id, json.dumps({"provider": "github", "authentication": "GITHUB_APP_INSTALLATION"})),
            )
            source = await source_cursor.fetchone()
            assert source is not None
            try:
                account_cursor = await connection.execute(
                    """
                    INSERT INTO connector_account(
                      tenant_id,source_system_id,external_account_key,credential_reference,
                      permissions,status
                    ) VALUES (%s,%s,%s,%s,%s::jsonb,'ACTIVE')
                    ON CONFLICT(tenant_id,source_system_id,external_account_key) DO UPDATE
                      SET credential_reference=EXCLUDED.credential_reference,
                          permissions=EXCLUDED.permissions,status='ACTIVE',updated_at=now()
                    RETURNING id
                    """,
                    (tenant_id, source["id"], external_account_key, credential_reference, json.dumps(scopes)),
                )
            except UniqueViolation as error:
                if error.diag.constraint_name == "uq_github_installation_tenant":
                    raise APIError(
                        409, "GITHUB_INSTALLATION_IN_USE",
                        "This GitHub App installation is already bound to another workspace.",
                    ) from error
                raise
            account = await account_cursor.fetchone()
            assert account is not None
            target_cursor = await connection.execute(
                """
                INSERT INTO ingest_target(
                  tenant_id,source_system_id,connector_account_id,target_kind,target_key,
                  priority,enabled,refresh_policy,next_due_at
                ) VALUES (%s,%s,%s,'GITHUB_INSTALLATION',%s,'HOT',true,%s::jsonb,now())
                ON CONFLICT(tenant_id,source_system_id,target_kind,target_key) DO UPDATE
                  SET connector_account_id=EXCLUDED.connector_account_id,enabled=true,
                      refresh_policy=EXCLUDED.refresh_policy,next_due_at=now(),updated_at=now()
                RETURNING id
                """,
                (
                    tenant_id, source["id"], account["id"], external_account_key,
                    json.dumps({
                        "provider": "github", "installation_id": installation_id,
                        "cadence_seconds": cadence_seconds, "schedule_enabled": schedule_enabled,
                    }),
                ),
            )
            target = await target_cursor.fetchone()
            assert target is not None
            connector_cursor = await connection.execute(
                """
                INSERT INTO connector(
                  tenant_id,provider,display_name,external_account_key,credential_reference,
                  scopes,metadata,created_by
                ) VALUES (%s,'GITHUB_APP',%s,%s,%s,%s,%s::jsonb,%s)
                RETURNING *
                """,
                (
                    tenant_id, display_name, external_account_key, credential_reference, scopes,
                    json.dumps({
                        "connection_mode": "GITHUB_APP_INSTALLATION",
                        "installation_id": installation_id,
                        "ingest_target_id": str(target["id"]),
                    }),
                    actor_key,
                ),
            )
            row = await connector_cursor.fetchone()
            assert row is not None
            await connection.execute(
                """
                INSERT INTO ingest_run(tenant_id,ingest_target_id,trigger_kind,stats)
                SELECT %s,%s,'MANUAL',jsonb_build_object('connector_id',%s::text)
                WHERE NOT EXISTS (
                  SELECT 1 FROM ingest_run
                  WHERE ingest_target_id=%s AND status IN ('PENDING','RUNNING')
                )
                """,
                (tenant_id, target["id"], str(row["id"]), target["id"]),
            )
            await self._write_admin_audit(
                connection, tenant_id=tenant_id, actor_key=actor_key,
                action="github_installation.connect", target_kind="connector", target_id=row["id"],
                detail={"installation_id": installation_id, "ingest_target_id": str(target["id"])},
            )
        return self._connector(row)

    async def update_connector(
        self, connector_id: UUID, request: ConnectorUpdateRequest, *, tenant_id: UUID | None, actor_key: str,
    ) -> Connector:
        if tenant_id is None:
            raise APIError(400, "TENANT_REQUIRED", "A tenant ID is required to update a connector.")
        if request.credential_reference is not None:
            self._reject_raw_secret(request.credential_reference)
        async with self.database.session(tenant_id) as connection:
            cursor = await connection.execute(
                "SELECT * FROM connector WHERE id = %s FOR UPDATE", (connector_id,),
            )
            if await cursor.fetchone() is None:
                raise APIError(404, "CONNECTOR_NOT_FOUND", "The connector was not found.")
            sets: list[str] = []
            values: list[Any] = []
            if request.display_name is not None:
                sets.append("display_name = %s")
                values.append(request.display_name)
            if request.status is not None:
                sets.append("status = %s")
                values.append(request.status)
            if request.scopes is not None:
                sets.append("scopes = %s")
                values.append(request.scopes)
            if request.credential_reference is not None:
                sets.append("credential_reference = %s")
                values.append(request.credential_reference)
            sets.append("updated_at = now()")
            values.append(connector_id)
            await connection.execute(
                f"UPDATE connector SET {', '.join(sets)} WHERE id = %s", tuple(values),
            )
            await self._write_admin_audit(
                connection, tenant_id=tenant_id, actor_key=actor_key, action="connector.update",
                target_kind="connector", target_id=connector_id,
                detail={"status": request.status} if request.status else {},
            )
            cursor = await connection.execute("SELECT * FROM connector WHERE id = %s", (connector_id,))
            row = await cursor.fetchone()
        return self._connector(row)

    async def remove_connector(
        self, connector_id: UUID, *, tenant_id: UUID | None, actor_key: str,
    ) -> Connector:
        if tenant_id is None:
            raise APIError(400, "TENANT_REQUIRED", "A tenant ID is required to remove a connector.")
        async with self.database.session(tenant_id) as connection:
            cursor = await connection.execute(
                "SELECT * FROM connector WHERE id = %s FOR UPDATE", (connector_id,),
            )
            row = await cursor.fetchone()
            if row is None:
                raise APIError(404, "CONNECTOR_NOT_FOUND", "The connector was not found.")
            target_id = row["metadata"].get("ingest_target_id") if row.get("metadata") else None
            if target_id:
                await connection.execute(
                    """
                    UPDATE connector_account account
                    SET status='DISABLED',updated_at=now()
                    FROM ingest_target target
                    WHERE target.id=%s AND account.id=target.connector_account_id
                    """,
                    (target_id,),
                )
                await connection.execute(
                    """
                    UPDATE ingest_target target
                    SET enabled=false,next_due_at=NULL,updated_at=now()
                    FROM ingest_target root
                    WHERE root.id=%s AND (
                      target.id=root.id OR target.connector_account_id=root.connector_account_id
                    )
                    """,
                    (target_id,),
                )
                await connection.execute(
                    """
                    UPDATE ingest_run SET status='CANCELLED',completed_at=now(),
                      lease_owner=NULL,lease_expires_at=NULL
                    WHERE ingest_target_id IN (
                      SELECT target.id FROM ingest_target target
                      JOIN ingest_target root ON root.id=%s
                      WHERE target.id=root.id OR target.connector_account_id=root.connector_account_id
                    ) AND status='PENDING'
                    """,
                    (target_id,),
                )
            await connection.execute("DELETE FROM connector WHERE id=%s", (connector_id,))
            await self._write_admin_audit(
                connection, tenant_id=tenant_id, actor_key=actor_key, action="connector.remove",
                target_kind="connector", target_id=connector_id, detail={"provider": row["provider"]},
            )
        return self._connector(row)

    @staticmethod
    def _reject_raw_secret(value: str) -> None:
        candidate = value.strip()
        if candidate and any(candidate.startswith(marker) for marker in _RAW_SECRET_MARKERS):
            raise APIError(
                422, "CREDENTIAL_LOOKS_RAW",
                "credential_reference must be a secret-store reference, not a raw token.",
            )

    @staticmethod
    def _connector(row: dict[str, Any]) -> Connector:
        return Connector(
            id=row["id"], provider=row["provider"], display_name=row["display_name"],
            external_account_key=row["external_account_key"], scopes=list(row["scopes"]),
            status=row["status"],
            last_synced_at=row.get("effective_last_synced_at", row.get("last_synced_at")),
            last_error=row.get("effective_last_error", row.get("last_error")),
            created_at=row["created_at"], updated_at=row["updated_at"],
        )

    # --- Admin: AI provider configuration --------------------------------

    async def get_ai_provider_configuration(
        self, *, tenant_id: UUID | None,
    ) -> AIProviderConfiguration:
        if tenant_id is None:
            raise APIError(400, "TENANT_REQUIRED", "A tenant ID is required to read AI configuration.")
        row = await self.database.fetch_one(
            """
            SELECT c.*, s.fingerprint AS key_fingerprint
            FROM tenant_ai_configuration c
            LEFT JOIN tenant_secret s ON s.id=c.credential_secret_id
            """,
            tenant_id=tenant_id,
        )
        return await self._ai_provider_configuration_with_status(row, tenant_id=tenant_id)

    async def update_ai_provider_configuration(
        self,
        request: AIProviderConfigurationUpdateRequest,
        *,
        tenant_id: UUID | None,
        actor_key: str,
    ) -> AIProviderConfiguration:
        if tenant_id is None:
            raise APIError(400, "TENANT_REQUIRED", "A tenant ID is required to update AI configuration.")
        api_key = request.api_key.strip() if request.api_key is not None else None
        if request.api_key is not None and not api_key:
            raise APIError(422, "AI_KEY_EMPTY", "The provider API key cannot be empty.")

        async with self.database.session(tenant_id) as connection:
            cursor = await connection.execute(
                "SELECT * FROM tenant_ai_configuration WHERE tenant_id=%s FOR UPDATE",
                (tenant_id,),
            )
            existing = await cursor.fetchone()
            if (
                existing is not None
                and existing["credential_secret_id"] is not None
                and existing["provider"] != request.provider
                and api_key is None
            ):
                raise APIError(
                    422,
                    "AI_KEY_ROTATION_REQUIRED",
                    "Enter a new API key when changing AI providers.",
                )

            secret_id = existing["credential_secret_id"] if existing is not None else None
            old_secret_id = secret_id
            if api_key is not None:
                secret_cursor = await connection.execute(
                    """
                    INSERT INTO tenant_secret(
                      tenant_id,secret_kind,ciphertext,fingerprint,created_by
                    ) VALUES (
                      %s,'AI_PROVIDER_KEY',
                      pgp_sym_encrypt(%s,%s,'cipher-algo=aes256'),%s,%s
                    ) RETURNING id
                    """,
                    (tenant_id, api_key, self.credential_encryption_key, api_key[-4:], actor_key),
                )
                secret = await secret_cursor.fetchone()
                assert secret is not None
                secret_id = secret["id"]

            cursor = await connection.execute(
                """
                INSERT INTO tenant_ai_configuration(
                  tenant_id,provider,model,credential_secret_id,enabled,updated_by
                ) VALUES (%s,%s,%s,%s,%s,%s)
                ON CONFLICT(tenant_id) DO UPDATE SET
                  provider=EXCLUDED.provider,
                  model=EXCLUDED.model,
                  credential_secret_id=EXCLUDED.credential_secret_id,
                  enabled=EXCLUDED.enabled,
                  test_status='NOT_TESTED',tested_at=NULL,last_error=NULL,
                  updated_by=EXCLUDED.updated_by,updated_at=now()
                RETURNING *
                """,
                (tenant_id, request.provider, request.model.strip(), secret_id, request.enabled, actor_key),
            )
            row = await cursor.fetchone()
            assert row is not None
            if api_key is not None and old_secret_id is not None and old_secret_id != secret_id:
                await connection.execute("DELETE FROM tenant_secret WHERE id=%s", (old_secret_id,))
            await self._write_admin_audit(
                connection,
                tenant_id=tenant_id,
                actor_key=actor_key,
                action="ai_configuration.update",
                target_kind="tenant_ai_configuration",
                target_id=tenant_id,
                detail={
                    "provider": request.provider,
                    "model": request.model.strip(),
                    "key_rotated": api_key is not None,
                    "enabled": request.enabled,
                },
            )
            if (
                existing is not None
                and existing["credential_secret_id"] is not None
                and existing["model"]
            ):
                previous_fingerprint = self._tenant_ai_configuration_fingerprint(
                    existing["provider"], existing["model"], existing["credential_secret_id"],
                )
                current_fingerprint = (
                    self._tenant_ai_configuration_fingerprint(
                        request.provider, request.model.strip(), secret_id,
                    )
                    if request.enabled and secret_id is not None and request.model.strip()
                    else None
                )
                if previous_fingerprint != current_fingerprint:
                    await connection.execute(
                        """
                        DELETE FROM intelligence_job
                        WHERE tenant_id=%s AND configuration_fingerprint=%s
                          AND status='PENDING'
                        """,
                        (tenant_id, previous_fingerprint),
                    )
            if request.enabled and secret_id is not None and request.model.strip():
                await self._enqueue_tenant_ai_reanalysis(
                    connection,
                    tenant_id=tenant_id,
                    provider=request.provider,
                    model=request.model.strip(),
                    secret_id=secret_id,
                )
            fingerprint_cursor = await connection.execute(
                "SELECT fingerprint FROM tenant_secret WHERE id=%s", (secret_id,),
            ) if secret_id is not None else None
            fingerprint_row = await fingerprint_cursor.fetchone() if fingerprint_cursor is not None else None
        row["key_fingerprint"] = fingerprint_row["fingerprint"] if fingerprint_row else None
        return await self._ai_provider_configuration_with_status(row, tenant_id=tenant_id)

    async def remove_ai_provider_key(
        self, *, tenant_id: UUID | None, actor_key: str,
    ) -> AIProviderConfiguration:
        if tenant_id is None:
            raise APIError(400, "TENANT_REQUIRED", "A tenant ID is required to remove an AI key.")
        async with self.database.session(tenant_id) as connection:
            cursor = await connection.execute(
                "SELECT * FROM tenant_ai_configuration WHERE tenant_id=%s FOR UPDATE", (tenant_id,),
            )
            row = await cursor.fetchone()
            if row is None:
                return self._ai_provider_configuration(None)
            secret_id = row["credential_secret_id"]
            cursor = await connection.execute(
                """
                UPDATE tenant_ai_configuration SET credential_secret_id=NULL,
                  test_status='NOT_TESTED',tested_at=NULL,last_error=NULL,
                  updated_by=%s,updated_at=now()
                WHERE tenant_id=%s RETURNING *
                """,
                (actor_key, tenant_id),
            )
            row = await cursor.fetchone()
            assert row is not None
            if secret_id is not None:
                await connection.execute("DELETE FROM tenant_secret WHERE id=%s", (secret_id,))
            await self._write_admin_audit(
                connection, tenant_id=tenant_id, actor_key=actor_key,
                action="ai_configuration.key_remove", target_kind="tenant_ai_configuration",
                target_id=tenant_id, detail={"provider": row["provider"]},
            )
        row["key_fingerprint"] = None
        return await self._ai_provider_configuration_with_status(row, tenant_id=tenant_id)

    async def test_ai_provider_connection(
        self, *, tenant_id: UUID | None, actor_key: str,
    ) -> AIProviderConnectionTest:
        if tenant_id is None:
            raise APIError(400, "TENANT_REQUIRED", "A tenant ID is required to test AI configuration.")
        row = await self.database.fetch_one(
            """
            SELECT c.provider,c.model,
              pgp_sym_decrypt(s.ciphertext,%s)::text AS api_key
            FROM tenant_ai_configuration c
            JOIN tenant_secret s ON s.id=c.credential_secret_id
            """,
            (self.credential_encryption_key,), tenant_id=tenant_id,
        )
        if row is None:
            raise APIError(422, "AI_KEY_REQUIRED", "Save a provider API key before testing the connection.")
        provider = row["provider"]
        api_key = row["api_key"]
        url, headers = self._ai_models_request(provider, api_key)
        openrouter_zdr_endpoints: Any = None
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                if provider == "openrouter":
                    authentication = await client.get(
                        "https://openrouter.ai/api/v1/auth/key", headers=headers,
                    )
                    authentication.raise_for_status()
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                payload = response.json()
                if provider == "openrouter":
                    endpoints = await client.get(
                        "https://openrouter.ai/api/v1/endpoints/zdr", headers=headers,
                    )
                    endpoints.raise_for_status()
                    openrouter_zdr_endpoints = endpoints.json()
            available_models = self._ai_model_ids(payload)
            models = available_models[:100]
        except (httpx.HTTPError, ValueError, TypeError) as error:
            message = "Provider authentication or model discovery failed."
            await self.database.fetch_one(
                """
                UPDATE tenant_ai_configuration SET test_status='FAILED',tested_at=now(),
                  last_error=%s,updated_by=%s,updated_at=now() RETURNING tenant_id
                """,
                (message, actor_key), tenant_id=tenant_id,
            )
            raise APIError(502, "AI_CONNECTION_FAILED", message) from error
        if available_models and row["model"] not in available_models:
            message = f"The selected model {row['model']!r} is not available to this provider key."
            await self.database.fetch_one(
                """
                UPDATE tenant_ai_configuration SET test_status='FAILED',tested_at=now(),
                  last_error=%s,updated_by=%s,updated_at=now() RETURNING tenant_id
                """,
                (message, actor_key), tenant_id=tenant_id,
            )
            raise APIError(422, "AI_MODEL_UNAVAILABLE", message)
        if (
            provider == "openrouter"
            and not self._openrouter_model_supports_intelligence(
                openrouter_zdr_endpoints, row["model"],
            )
        ):
            required = ", ".join(sorted(_OPENROUTER_INTELLIGENCE_REQUIRED_PARAMETERS))
            message = (
                f"The selected model {row['model']!r} has no zero-data-retention endpoint "
                f"that supports StackGraph's required parameters: {required}."
            )
            await self.database.fetch_one(
                """
                UPDATE tenant_ai_configuration SET test_status='FAILED',tested_at=now(),
                  last_error=%s,updated_by=%s,updated_at=now() RETURNING tenant_id
                """,
                (message, actor_key), tenant_id=tenant_id,
            )
            raise APIError(422, "AI_MODEL_INCOMPATIBLE", message)
        await self.database.fetch_one(
            """
            UPDATE tenant_ai_configuration SET test_status='SUCCEEDED',tested_at=now(),
              last_error=NULL,updated_by=%s,updated_at=now() RETURNING tenant_id
            """,
            (actor_key,), tenant_id=tenant_id,
        )
        return AIProviderConnectionTest(provider=provider, models=models)

    @staticmethod
    def _ai_models_request(provider: str, api_key: str) -> tuple[str, dict[str, str]]:
        if provider == "anthropic":
            return (
                "https://api.anthropic.com/v1/models",
                {"x-api-key": api_key, "anthropic-version": "2023-06-01"},
            )
        base = "https://openrouter.ai/api/v1" if provider == "openrouter" else "https://api.openai.com/v1"
        return f"{base}/models", {"Authorization": f"Bearer {api_key}"}

    @staticmethod
    def _ai_model_ids(payload: Any) -> list[str]:
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
            return []
        return sorted(
            str(item["id"]) for item in payload["data"]
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        )

    @staticmethod
    def _openrouter_model_supports_intelligence(payload: Any, model: str) -> bool:
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
            return False
        return any(
            isinstance(endpoint, dict)
            and endpoint.get("model_id") == model
            and isinstance(endpoint.get("supported_parameters"), list)
            and _OPENROUTER_INTELLIGENCE_REQUIRED_PARAMETERS.issubset(
                {
                    parameter
                    for parameter in endpoint["supported_parameters"]
                    if isinstance(parameter, str)
                }
            )
            for endpoint in payload["data"]
        )

    async def _ai_provider_configuration_with_status(
        self,
        row: dict[str, Any] | None,
        *,
        tenant_id: UUID,
    ) -> AIProviderConfiguration:
        configuration = self._ai_provider_configuration(row)
        if (
            row is None
            or not row["enabled"]
            or not row["model"]
            or row["credential_secret_id"] is None
        ):
            return configuration
        configuration_fingerprint = self._tenant_ai_configuration_fingerprint(
            row["provider"], row["model"], row["credential_secret_id"],
        )
        stats = await self.database.fetch_one(
            """
            SELECT
              count(*) FILTER (WHERE status='PENDING') pending_jobs,
              count(*) FILTER (WHERE status='RUNNING') running_jobs,
              count(*) FILTER (WHERE status='FAILED') failed_jobs,
              count(*) FILTER (WHERE status='SUCCEEDED') succeeded_jobs,
              max(completed_at) FILTER (WHERE status='SUCCEEDED') last_enrichment_at
            FROM intelligence_job
            WHERE configuration_fingerprint=%s
            """,
            (configuration_fingerprint,),
            tenant_id=tenant_id,
        )
        pending = int(stats["pending_jobs"] or 0) if stats else 0
        running = int(stats["running_jobs"] or 0) if stats else 0
        failed = int(stats["failed_jobs"] or 0) if stats else 0
        succeeded = int(stats["succeeded_jobs"] or 0) if stats else 0
        status = (
            "DEGRADED" if failed
            else "RUNNING" if running
            else "QUEUED" if pending
            else "ACTIVE" if succeeded
            else "READY"
        )
        return configuration.model_copy(update={
            "enrichment_status": status,
            "pending_enrichment_jobs": pending,
            "running_enrichment_jobs": running,
            "failed_enrichment_jobs": failed,
            "last_enrichment_at": stats["last_enrichment_at"] if stats else None,
        })

    async def _enqueue_tenant_ai_reanalysis(
        self,
        connection: Any,
        *,
        tenant_id: UUID,
        provider: str,
        model: str,
        secret_id: UUID,
    ) -> None:
        configuration_fingerprint = self._tenant_ai_configuration_fingerprint(
            provider, model, secret_id,
        )
        await connection.execute(
            """
            WITH latest_snapshot AS (
              SELECT DISTINCT ON (repository.id)
                repository.id repository_id,snapshot.id snapshot_id,snapshot.source_revision
              FROM entity repository
              JOIN ingest_target target
                ON target.tenant_id=repository.tenant_id
               AND target.target_kind='REPOSITORY'
               AND target.target_key=repository.canonical_key
              JOIN source_snapshot snapshot ON snapshot.ingest_target_id=target.id
              WHERE repository.tenant_id=%s
                AND repository.namespace='ENTERPRISE'
                AND repository.entity_type='Repository'
                AND snapshot.status='PUBLISHED'
                AND snapshot.completeness='COMPLETE'
                AND snapshot.extractor_key='repository-dependency-usage'
              ORDER BY repository.id,snapshot.observed_at DESC,
                       snapshot.published_at DESC,snapshot.id DESC
            )
            INSERT INTO intelligence_job(
              tenant_id,repository_entity_id,source_snapshot_id,source_revision,
              job_kind,configuration_fingerprint
            )
            SELECT %s,repository_id,snapshot_id,source_revision,
                   'REPOSITORY_MODERNIZATION',%s
            FROM latest_snapshot
            ON CONFLICT DO NOTHING
            """,
            (tenant_id, tenant_id, configuration_fingerprint),
        )

    @staticmethod
    def _tenant_ai_configuration_fingerprint(
        provider: str,
        model: str,
        secret_id: UUID,
    ) -> str:
        payload = f"tenant-ai-v1\x1f{provider}\x1f{model}\x1f{secret_id}".encode()
        return "sha256:" + hashlib.sha256(payload).hexdigest()

    @staticmethod
    def _ai_provider_configuration(row: dict[str, Any] | None) -> AIProviderConfiguration:
        if row is None:
            return AIProviderConfiguration(provider="anthropic")
        fingerprint = row.get("key_fingerprint")
        return AIProviderConfiguration(
            provider=row["provider"], model=row["model"], enabled=row["enabled"],
            key_configured=fingerprint is not None, key_fingerprint=fingerprint,
            test_status=row["test_status"], tested_at=row["tested_at"],
            last_error=row["last_error"], updated_by=row["updated_by"], updated_at=row["updated_at"],
        )

    # --- Admin: scan policy, rescans, and quota ----------------------------

    async def get_scan_policy(self, *, tenant_id: UUID | None) -> ScanPolicy:
        if tenant_id is None:
            raise APIError(400, "TENANT_REQUIRED", "A tenant ID is required to read the scan policy.")
        row = await self.database.fetch_one("SELECT * FROM scan_policy", tenant_id=tenant_id)
        if row is None:
            # A tenant with no explicit policy runs on the documented default.
            return ScanPolicy(cadence="DAILY", enabled=True)
        return self._scan_policy(row)

    async def update_scan_policy(
        self, request: ScanPolicyUpdateRequest, *, tenant_id: UUID | None, actor_key: str,
    ) -> ScanPolicy:
        if tenant_id is None:
            raise APIError(400, "TENANT_REQUIRED", "A tenant ID is required to update the scan policy.")
        async with self.database.session(tenant_id) as connection:
            cursor = await connection.execute(
                """
                INSERT INTO scan_policy (tenant_id, cadence, enabled, updated_by)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (tenant_id) DO UPDATE
                  SET cadence = EXCLUDED.cadence, enabled = EXCLUDED.enabled,
                      updated_by = EXCLUDED.updated_by, updated_at = now()
                RETURNING *
                """,
                (tenant_id, request.cadence, request.enabled, actor_key),
            )
            row = await cursor.fetchone()
            assert row is not None
            cadence_seconds = {
                "HOURLY": 3600,
                "DAILY": 86400,
                "WEEKLY": 604800,
                "MANUAL": 86400,
            }[request.cadence]
            schedule_enabled = request.enabled and request.cadence != "MANUAL"
            await connection.execute(
                """
                UPDATE ingest_target target
                SET refresh_policy=jsonb_set(
                      jsonb_set(target.refresh_policy,'{cadence_seconds}',to_jsonb(%s::integer),true),
                      '{schedule_enabled}',to_jsonb(%s::boolean),true
                    ),
                    next_due_at=CASE
                      WHEN %s THEN coalesce(target.next_due_at,now()) ELSE NULL
                    END,
                    updated_at=now()
                FROM connector admin_connector
                JOIN ingest_target root
                  ON admin_connector.metadata->>'ingest_target_id'=root.id::text
                WHERE admin_connector.tenant_id=%s
                  AND (target.id=root.id OR target.connector_account_id=root.connector_account_id)
                """,
                (cadence_seconds, schedule_enabled, schedule_enabled, tenant_id),
            )
            await self._write_admin_audit(
                connection, tenant_id=tenant_id, actor_key=actor_key, action="scan_policy.update",
                target_kind="scan_policy", target_id=tenant_id,
                detail={"cadence": request.cadence, "enabled": request.enabled},
            )
        return self._scan_policy(row)

    async def request_rescan(
        self, request: RescanRequest, *, tenant_id: UUID | None, actor_key: str,
    ) -> tuple[RescanJob, bool]:
        if tenant_id is None:
            raise APIError(400, "TENANT_REQUIRED", "A tenant ID is required to request a rescan.")
        async with self.database.session(tenant_id) as connection:
            if request.connector_id is not None:
                probe = await connection.execute(
                    "SELECT 1 FROM connector WHERE id = %s", (request.connector_id,),
                )
                if await probe.fetchone() is None:
                    raise APIError(404, "CONNECTOR_NOT_FOUND", "The connector was not found.")
            cursor = await connection.execute(
                """
                INSERT INTO rescan_job (tenant_id, connector_id, idempotency_key, reason, requested_by)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (tenant_id, idempotency_key) DO NOTHING
                RETURNING *
                """,
                (tenant_id, request.connector_id, request.idempotency_key, request.reason, actor_key),
            )
            row = await cursor.fetchone()
            if row is None:
                # Idempotent replay: the key already produced a job; return it unchanged.
                cursor = await connection.execute(
                    "SELECT * FROM rescan_job WHERE idempotency_key = %s", (request.idempotency_key,),
                )
                row = await cursor.fetchone()
                assert row is not None
                return self._rescan_job(row), False
            targets_cursor = await connection.execute(
                """
                SELECT target.id
                FROM connector admin_connector
                JOIN ingest_target root
                  ON admin_connector.metadata->>'ingest_target_id'=root.id::text
                JOIN ingest_target target
                  ON target.id=root.id OR target.connector_account_id=root.connector_account_id
                WHERE admin_connector.tenant_id=%s AND target.enabled
                  AND (%s::uuid IS NULL OR admin_connector.id=%s)
                FOR UPDATE OF target
                """,
                (tenant_id, request.connector_id, request.connector_id),
            )
            targets = list(await targets_cursor.fetchall())
            queued = 0
            linked = 0
            for target in targets:
                run_cursor = await connection.execute(
                    """
                    SELECT id FROM ingest_run
                    WHERE ingest_target_id=%s AND status IN ('PENDING','RUNNING')
                    ORDER BY created_at DESC,id DESC LIMIT 1 FOR UPDATE
                    """,
                    (target["id"],),
                )
                run = await run_cursor.fetchone()
                if run is None:
                    run_cursor = await connection.execute(
                        """
                        INSERT INTO ingest_run(
                          tenant_id,ingest_target_id,trigger_kind,stats
                        ) VALUES (%s,%s,'MANUAL',jsonb_build_object(
                          'rescan_job_ids',jsonb_build_array(%s::text),
                          'connector_id',%s::text
                        )) RETURNING id
                        """,
                        (
                            tenant_id,
                            target["id"],
                            str(row["id"]),
                            str(request.connector_id) if request.connector_id else "",
                        ),
                    )
                    run = await run_cursor.fetchone()
                    assert run is not None
                    queued += 1
                else:
                    await connection.execute(
                        """
                        UPDATE ingest_run SET stats=jsonb_set(
                          coalesce(stats,'{}'::jsonb),'{rescan_job_ids}',
                          coalesce(stats->'rescan_job_ids','[]'::jsonb)
                            || jsonb_build_array(%s::text),true
                        ) || jsonb_build_object('connector_id',%s::text)
                        WHERE id=%s
                        """,
                        (
                            str(row["id"]),
                            str(request.connector_id) if request.connector_id else "",
                            run["id"],
                        ),
                    )
                linked += 1
            if linked == 0:
                completed_cursor = await connection.execute(
                    """
                    UPDATE rescan_job SET status='SUCCEEDED',started_at=now(),
                      completed_at=now(),updated_at=now()
                    WHERE id=%s RETURNING *
                    """,
                    (row["id"],),
                )
                row = await completed_cursor.fetchone()
                assert row is not None
            await self._write_admin_audit(
                connection, tenant_id=tenant_id, actor_key=actor_key, action="rescan.request",
                target_kind="rescan_job", target_id=row["id"],
                detail={
                    "connector_id": str(request.connector_id) if request.connector_id else None,
                    "ingest_runs_linked": linked,
                    "ingest_runs_queued": queued,
                },
            )
        return self._rescan_job(row), True

    async def list_rescan_jobs(
        self, *, tenant_id: UUID | None, cursor: str | None, limit: int,
    ) -> RescanJobList:
        if tenant_id is None:
            raise APIError(400, "TENANT_REQUIRED", "A tenant ID is required to list rescan jobs.")
        decoded = _decode_cursor(cursor, "rescan-job")
        rows = await self.database.fetch_all(
            """
            SELECT * FROM rescan_job
            WHERE (%(created_before)s::timestamptz IS NULL
                   OR created_at < %(created_before)s
                   OR (created_at = %(created_before)s AND id < %(id_before)s))
            ORDER BY created_at DESC, id DESC
            LIMIT %(limit)s
            """,
            {
                "created_before": decoded["created_before"] if decoded else None,
                "id_before": decoded["id_before"] if decoded else None,
                "limit": limit + 1,
            },
            tenant_id=tenant_id,
        )
        has_next = len(rows) > limit
        page = rows[:limit]
        next_cursor = None
        if has_next and page:
            last = page[-1]
            next_cursor = _encode_cursor(
                "rescan-job",
                created_before=last["created_at"].isoformat(),
                id_before=str(last["id"]),
            )
        return RescanJobList(
            jobs=[self._rescan_job(row) for row in page],
            page_info=PageInfo(has_next_page=has_next, next_cursor=next_cursor),
        )

    async def scan_status(self, *, tenant_id: UUID | None) -> ScanStatus:
        if tenant_id is None:
            raise APIError(400, "TENANT_REQUIRED", "A tenant ID is required to read scan status.")
        policy = await self.get_scan_policy(tenant_id=tenant_id)
        quota_rows = await self.database.fetch_all(
            "SELECT * FROM connector_quota ORDER BY provider", tenant_id=tenant_id,
        )
        job_rows = await self.database.fetch_all(
            "SELECT * FROM rescan_job ORDER BY created_at DESC, id DESC LIMIT 10", tenant_id=tenant_id,
        )
        return ScanStatus(
            as_of=datetime.now(UTC),
            policy=policy,
            quotas=[
                ProviderQuota(
                    provider=row["provider"], used=row["used"], limit=row["limit_value"],
                    status=row["status"], resets_at=row["resets_at"],
                    backoff_until=row["backoff_until"], observed_at=row["observed_at"],
                )
                for row in quota_rows
            ],
            recent_jobs=[self._rescan_job(row) for row in job_rows],
        )

    async def service_status(self, *, tenant_id: UUID | None) -> ServiceStatusList:
        if tenant_id is None:
            raise APIError(400, "TENANT_REQUIRED", "A tenant ID is required to read service status.")
        heartbeat_rows = await self.database.fetch_all(
            "SELECT service_key,status,last_heartbeat_at FROM service_heartbeat",
            tenant_id=tenant_id,
        )
        control_rows = await self.database.fetch_all(
            "SELECT service_key,desired_state FROM tenant_service_control",
            tenant_id=tenant_id,
        )
        workload = await self.database.fetch_one(
            """
            SELECT
              (SELECT count(*) FROM connector_account
               WHERE tenant_id=%s AND external_account_key LIKE 'github:%%' AND status='ACTIVE') github_configured,
              (SELECT count(*) FROM ingest_run run JOIN ingest_target target ON target.id=run.ingest_target_id
               JOIN source_system source ON source.id=target.source_system_id
               WHERE run.tenant_id=%s AND source.source_key='github-app' AND run.status='PENDING') github_pending,
              (SELECT count(*) FROM ingest_run run JOIN ingest_target target ON target.id=run.ingest_target_id
               JOIN source_system source ON source.id=target.source_system_id
               WHERE run.tenant_id=%s AND source.source_key='github-app' AND run.status='RUNNING') github_running,
              (SELECT count(*) FROM ingest_run run JOIN ingest_target target ON target.id=run.ingest_target_id
               JOIN source_system source ON source.id=target.source_system_id
               WHERE run.tenant_id=%s AND source.source_key='github-app' AND run.status='FAILED'
                 AND (target.last_success_at IS NULL OR run.completed_at>target.last_success_at)) github_failed,
              (SELECT max(coalesce(run.completed_at,run.started_at,run.created_at)) FROM ingest_run run
               JOIN ingest_target target ON target.id=run.ingest_target_id
               JOIN source_system source ON source.id=target.source_system_id
               WHERE run.tenant_id=%s AND source.source_key='github-app') github_last,
              (SELECT count(*) FROM webhook_delivery WHERE tenant_id=%s AND status='PROCESSING') webhook_running,
              (SELECT count(*) FROM webhook_delivery WHERE tenant_id=%s AND status='FAILED') webhook_failed,
              (SELECT max(coalesce(processed_at,received_at)) FROM webhook_delivery WHERE tenant_id=%s) webhook_last,
              (SELECT count(*) FROM projection_outbox WHERE tenant_id=%s AND processed_at IS NULL) projection_pending,
              (SELECT count(*) FROM projection_outbox WHERE tenant_id=%s AND leased_by IS NOT NULL AND processed_at IS NULL) projection_running,
              (SELECT count(*) FROM projection_outbox WHERE tenant_id=%s AND last_error IS NOT NULL AND processed_at IS NULL) projection_failed,
              (SELECT max(coalesce(processed_at,created_at)) FROM projection_outbox WHERE tenant_id=%s) projection_last,
              (SELECT count(*) FROM intelligence_job WHERE tenant_id=%s AND status='PENDING') intelligence_pending,
              (SELECT count(*) FROM intelligence_job WHERE tenant_id=%s AND status='RUNNING') intelligence_running,
              (SELECT count(*) FROM intelligence_job failed
               WHERE failed.tenant_id=%s AND failed.status='FAILED'
                 AND NOT EXISTS (
                   SELECT 1 FROM intelligence_job recovered
                   WHERE recovered.tenant_id=failed.tenant_id
                     AND recovered.repository_entity_id=failed.repository_entity_id
                     AND recovered.status='SUCCEEDED'
                     AND recovered.completed_at>failed.updated_at
                 )) intelligence_failed,
              (SELECT max(coalesce(completed_at,started_at,created_at)) FROM intelligence_job WHERE tenant_id=%s) intelligence_last,
              (SELECT count(*) FROM ingest_run run JOIN ingest_target target ON target.id=run.ingest_target_id
               JOIN source_system source ON source.id=target.source_system_id
               WHERE run.tenant_id=%s AND source.source_key='deps.dev' AND run.status='PENDING') depsdev_pending,
              (SELECT count(*) FROM ingest_run run JOIN ingest_target target ON target.id=run.ingest_target_id
               JOIN source_system source ON source.id=target.source_system_id
               WHERE run.tenant_id=%s AND source.source_key='deps.dev' AND run.status='RUNNING') depsdev_running,
              (SELECT count(*) FROM ingest_run run JOIN ingest_target target ON target.id=run.ingest_target_id
               JOIN source_system source ON source.id=target.source_system_id
               WHERE run.tenant_id=%s AND source.source_key='deps.dev' AND run.status='FAILED'
                 AND (target.last_success_at IS NULL OR run.completed_at>target.last_success_at)) depsdev_failed,
              (SELECT max(coalesce(run.completed_at,run.started_at,run.created_at)) FROM ingest_run run
               JOIN ingest_target target ON target.id=run.ingest_target_id JOIN source_system source ON source.id=target.source_system_id
               WHERE run.tenant_id=%s AND source.source_key='deps.dev') depsdev_last,
              (SELECT count(*) FROM ingest_run run JOIN ingest_target target ON target.id=run.ingest_target_id
               JOIN source_system source ON source.id=target.source_system_id
               WHERE run.tenant_id=%s AND source.source_key='osv.dev' AND run.status='PENDING') osv_pending,
              (SELECT count(*) FROM ingest_run run JOIN ingest_target target ON target.id=run.ingest_target_id
               JOIN source_system source ON source.id=target.source_system_id
               WHERE run.tenant_id=%s AND source.source_key='osv.dev' AND run.status='RUNNING') osv_running,
              (SELECT count(*) FROM ingest_run run JOIN ingest_target target ON target.id=run.ingest_target_id
               JOIN source_system source ON source.id=target.source_system_id
               WHERE run.tenant_id=%s AND source.source_key='osv.dev' AND run.status='FAILED'
                 AND (target.last_success_at IS NULL OR run.completed_at>target.last_success_at)) osv_failed,
              (SELECT max(coalesce(run.completed_at,run.started_at,run.created_at)) FROM ingest_run run
               JOIN ingest_target target ON target.id=run.ingest_target_id JOIN source_system source ON source.id=target.source_system_id
               WHERE run.tenant_id=%s AND source.source_key='osv.dev') osv_last
            """,
            tuple([tenant_id] * 24),
            tenant_id=tenant_id,
        ) or {}
        now = datetime.now(UTC)
        heartbeats = {row["service_key"]: row for row in heartbeat_rows}
        desired_states = {row["service_key"]: row["desired_state"] for row in control_rows}

        def service(
            key: str, name: str, category: str, *, configured: bool = True,
            pending: int = 0, running: int = 0, failed: int = 0,
            last_activity_at: datetime | None = None,
            controllable: bool = False,
            management_scope: str = "Externally managed",
        ) -> ServiceStatus:
            heartbeat = heartbeats.get(key)
            heartbeat_at = heartbeat.get("last_heartbeat_at") if heartbeat else None
            online = bool(
                heartbeat_at is not None
                and (now - heartbeat_at).total_seconds() <= 45
                and heartbeat.get("status") == "RUNNING"
            )
            desired_state = desired_states.get(key, "RUNNING")
            if controllable and desired_state == "STOPPED" and running:
                state = "STOPPING"
                detail = f"Stop requested; {running} in-flight item{'s' if running != 1 else ''} may finish."
            elif controllable and desired_state == "STOPPED":
                state = "STOPPED"
                detail = "Stopped for this workspace; durable queued work is preserved."
            elif failed:
                state = "DEGRADED"
                detail = f"{failed} failed item{'s' if failed != 1 else ''} need attention."
            elif running:
                state = "RUNNING"
                detail = f"Processing {running} item{'s' if running != 1 else ''}."
            elif not online:
                state = "OFFLINE"
                detail = "No recent worker heartbeat."
            elif pending:
                state = "WAITING"
                detail = f"{pending} item{'s' if pending != 1 else ''} queued."
            elif not configured:
                state = "IDLE"
                detail = "Worker is online; no tenant connection or work is configured."
            else:
                state = "IDLE"
                detail = "Worker is online and the durable queue is clear."
            return ServiceStatus(
                key=key, name=name, category=category, state=state, detail=detail,
                desired_state=desired_state, controllable=controllable,
                management_scope=management_scope,
                configured=configured, pending=pending, running=running, failed=failed,
                last_activity_at=last_activity_at, last_heartbeat_at=heartbeat_at,
            )

        github_configured = int(workload.get("github_configured") or 0) > 0
        services = [
            ServiceStatus(
                key="web", name="Web UI", category="CORE", state="RUNNING",
                detail="This Admin page is running.", management_scope="Docker / deployment platform",
                last_activity_at=now, last_heartbeat_at=now,
            ),
            ServiceStatus(
                key="api", name="API", category="CORE", state="RUNNING",
                detail="The authenticated Admin API is responding.", management_scope="Docker / deployment platform",
                last_activity_at=now, last_heartbeat_at=now,
            ),
            ServiceStatus(
                key="database", name="PostgreSQL / AGE", category="CORE", state="RUNNING",
                detail="Operational state and graph storage are reachable.", management_scope="Docker / deployment platform",
                last_activity_at=now, last_heartbeat_at=now,
            ),
            service(
                "github-webhook", "GitHub webhooks", "INGESTION", configured=github_configured,
                running=int(workload.get("webhook_running") or 0),
                failed=int(workload.get("webhook_failed") or 0),
                last_activity_at=workload.get("webhook_last"),
                controllable=True, management_scope="This workspace",
            ),
            service(
                "github-control-loop", "GitHub discovery", "INGESTION", configured=github_configured,
                pending=int(workload.get("github_pending") or 0),
                running=int(workload.get("github_running") or 0),
                failed=int(workload.get("github_failed") or 0),
                last_activity_at=workload.get("github_last"),
                controllable=True, management_scope="This workspace",
            ),
            service(
                "depsdev", "deps.dev enrichment", "ENRICHMENT",
                pending=int(workload.get("depsdev_pending") or 0),
                running=int(workload.get("depsdev_running") or 0),
                failed=int(workload.get("depsdev_failed") or 0),
                last_activity_at=workload.get("depsdev_last"),
                management_scope="Shared OSS catalog pipeline",
            ),
            service(
                "osv", "OSV vulnerability enrichment", "ENRICHMENT",
                pending=int(workload.get("osv_pending") or 0),
                running=int(workload.get("osv_running") or 0),
                failed=int(workload.get("osv_failed") or 0),
                last_activity_at=workload.get("osv_last"),
                management_scope="Shared OSS catalog pipeline",
            ),
            service(
                "projection", "Graph projection", "GRAPH",
                pending=int(workload.get("projection_pending") or 0),
                running=int(workload.get("projection_running") or 0),
                failed=int(workload.get("projection_failed") or 0),
                last_activity_at=workload.get("projection_last"),
                controllable=True, management_scope="This workspace",
            ),
            service(
                "intelligence", "Modernization intelligence", "INTELLIGENCE",
                pending=int(workload.get("intelligence_pending") or 0),
                running=int(workload.get("intelligence_running") or 0),
                failed=int(workload.get("intelligence_failed") or 0),
                last_activity_at=workload.get("intelligence_last"),
                controllable=True, management_scope="This workspace",
            ),
        ]
        return ServiceStatusList(as_of=now, services=services)

    async def update_service_control(
        self, service_key: str, request: ServiceControlRequest,
        *, tenant_id: UUID | None, actor_key: str,
    ) -> ServiceStatus:
        if tenant_id is None:
            raise APIError(400, "TENANT_REQUIRED", "A tenant ID is required to control a service.")
        if service_key not in _CONTROLLABLE_SERVICES:
            raise APIError(
                409, "SERVICE_EXTERNALLY_MANAGED",
                "This service cannot be controlled from the workspace Admin UI.",
            )
        async with self.database.session(tenant_id) as connection:
            await connection.execute(
                """
                INSERT INTO tenant_service_control(
                  tenant_id,service_key,desired_state,updated_by
                ) VALUES (%s,%s,%s,%s)
                ON CONFLICT(tenant_id,service_key) DO UPDATE SET
                  desired_state=EXCLUDED.desired_state,
                  updated_by=EXCLUDED.updated_by,
                  updated_at=now()
                """,
                (tenant_id, service_key, request.desired_state, actor_key),
            )
            await self._write_admin_audit(
                connection, tenant_id=tenant_id, actor_key=actor_key,
                action="service.control", target_kind="service", target_id=service_key,
                detail={"desired_state": request.desired_state},
            )
        statuses = await self.service_status(tenant_id=tenant_id)
        return next(service for service in statuses.services if service.key == service_key)

    async def _write_admin_audit(
        self, connection: Any, *, tenant_id: UUID, actor_key: str, action: str,
        target_kind: str, target_id: Any, detail: dict[str, Any],
    ) -> None:
        await connection.execute(
            """
            INSERT INTO admin_audit_log (tenant_id, actor_key, action, target_kind, target_id, detail)
            VALUES (%s, %s, %s, %s, %s, %s::jsonb)
            """,
            (tenant_id, actor_key, action, target_kind, str(target_id), json.dumps(detail)),
        )

    @staticmethod
    def _scan_policy(row: dict[str, Any]) -> ScanPolicy:
        return ScanPolicy(
            cadence=row["cadence"], enabled=row["enabled"],
            updated_by=row["updated_by"], updated_at=row["updated_at"],
        )

    @staticmethod
    def _rescan_job(row: dict[str, Any]) -> RescanJob:
        return RescanJob(
            id=row["id"], connector_id=row["connector_id"], status=row["status"],
            reason=row["reason"], requested_by=row["requested_by"], last_error=row["last_error"],
            created_at=row["created_at"], started_at=row["started_at"], completed_at=row["completed_at"],
        )

    @staticmethod
    def _dedupe_entities(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return list({row["id"]: row for row in rows}.values())

    @staticmethod
    def _dedupe_citations(citations: list[Citation]) -> list[Citation]:
        return list({citation.fact_id: citation for citation in citations}.values())
