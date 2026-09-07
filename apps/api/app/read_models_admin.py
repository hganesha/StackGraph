from __future__ import annotations

import base64
import hashlib
import json
import os
import re
from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

import httpx
from psycopg.errors import UniqueViolation
from stackgraph_ai.errors import ProviderRequestError, ProviderResponseError
from stackgraph_ai.governance import (
    CalibrationMetrics,
    CalibrationThresholds,
    EcosystemDemand,
    evaluate_ecosystem_admission as decide_ecosystem_admission,
    evaluate_promotion_gate,
    sha256_fingerprint,
)
from stackgraph_ai.models import ModelMessage, ModelRequest
from stackgraph_ai.providers import AnthropicAdapter, OpenAIAdapter, OpenRouterAdapter

from app.architecture_catalog import (
    load_architecture_catalog,
    sha256_fingerprint as architecture_fingerprint,
)
from app.errors import APIError
from app.deterministic_insights import METHOD_VERSION as DETERMINISTIC_METHOD_VERSION
from app.deterministic_insights import RULE_CATALOG, list_deterministic_insights
from app.models import (
    AIProviderConfiguration,
    AIProviderConfigurationUpdateRequest,
    AIProviderConnectionTest,
    ArchitectureProfileCreateRequest,
    ArchitectureProfileDetail,
    ArchitectureProfileList,
    ArchitectureProfilePublishRequest,
    ArchitectureProfileStateModel,
    ArchitectureProfileSummary,
    ArchitectureProfileUpdateRequest,
    Citation,
    Connector,
    ConnectorList,
    ConnectorRegisterRequest,
    ConnectorUpdateRequest,
    GitHubInstallationConnectRequest,
    GitHubRepositoryConnectRequest,
    GitHubRepositoryOption,
    GitHubRepositoryOptionList,
    GitHubTokenConfiguration,
    GitHubTokenUpdateRequest,
    MemberInviteRequest,
    MemberUpdateRequest,
    ModernizationGovernanceState,
    DeterministicInsightGovernanceState,
    DeterministicInsightRuleSummary,
    DeterministicInsightRuleUpdateRequest,
    ModernizationPolicyPublishRequest,
    ModernizationPolicySummary,
    InternalCatalogComponentUpsertRequest,
    InternalCatalogComponentSummary,
    InternalCatalogCandidateSummary,
    CalibrationCorpusPublishRequest,
    CalibrationCorpusSummary,
    CalibrationObservedMetrics,
    EcosystemAdmissionEvaluateRequest,
    EcosystemAdmissionSummary,
    EcosystemName,
    CodePolicyTechnologySummary,
    CodePolicyViolation,
    EntitySummary,
    RepositoryCodePolicyEvaluation,
    TenantCodeFunctionPolicySummary,
    TenantCodeFunctionSummary,
    TenantCodeFunctionUpsertRequest,
    TenantCodePolicyState,
    TenantCodePolicySummary,
    PageInfo,
    ProviderQuota,
    RescanJob,
    RescanJobList,
    RescanRequest,
    GraphAnalysisRequestCreate,
    GraphAnalysisRequestResult,
    EmbeddingBackfillRequest,
    EmbeddingBackfillResult,
    EmbeddingSpacePromotionRequest,
    EmbeddingSpacePromotionResult,
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
    "APPLICATION_SIMILARITY": "/similarity-candidates/{id}/review",
}

_RAW_SECRET_MARKERS: tuple[str, ...] = (
    "ghp_", "gho_", "ghu_", "ghs_", "ghr_", "github_pat_", "xox", "-----BEGIN", "AKIA",
)

_CONTROLLABLE_SERVICES = frozenset({
    "github-webhook", "github-control-loop", "projection", "intelligence", "graph-intelligence", "embeddings",
    "change-simulator", "mcp",
})

_OPENROUTER_INTELLIGENCE_REQUIRED_PARAMETERS = frozenset({"max_tokens", "response_format"})

_ECOSYSTEM_SEQUENCE: dict[EcosystemName, int] = {
    "PYPI": 1, "MAVEN": 2, "CARGO": 3, "NUGET": 4,
}
_ECOSYSTEM_PURL_TYPE: dict[EcosystemName, str] = {
    "PYPI": "pypi", "MAVEN": "maven", "CARGO": "cargo", "NUGET": "nuget",
}
# Metadata parity is a server capability, not an operator attestation. Only PyPI is implemented.
_ECOSYSTEM_METADATA_PARITY: dict[EcosystemName, bool] = {
    "PYPI": True, "MAVEN": False, "CARGO": False, "NUGET": False,
}

_AI_CONNECTION_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"answer": {"type": "string", "const": "ok"}},
    "required": ["answer"],
    "additionalProperties": False,
}


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

    # --- Architecture profiles -------------------------------------------

    async def list_architecture_profiles(
        self, *, tenant_id: UUID | None,
    ) -> ArchitectureProfileList:
        if tenant_id is None:
            raise APIError(400, "TENANT_REQUIRED", "A tenant ID is required to list architecture profiles.")
        rows = await self.database.fetch_all(
            """
            SELECT * FROM tenant_architecture_profile
            ORDER BY CASE status WHEN 'ACTIVE' THEN 0 WHEN 'DRAFT' THEN 1 ELSE 2 END,
                     updated_at DESC,id DESC
            """,
            tenant_id=tenant_id,
        )
        return ArchitectureProfileList(
            profiles=[self._architecture_profile_summary(row) for row in rows],
        )

    async def create_architecture_profile(
        self, request: ArchitectureProfileCreateRequest, *, tenant_id: UUID | None, actor_key: str,
    ) -> ArchitectureProfileDetail:
        if tenant_id is None:
            raise APIError(400, "TENANT_REQUIRED", "A tenant ID is required to create an architecture profile.")
        self._validate_architecture_profile_state(request.state)
        state = request.state.model_dump(mode="json")
        fingerprint = architecture_fingerprint(state)
        try:
            async with self.database.session(tenant_id) as connection:
                cursor = await connection.execute(
                    """
                    INSERT INTO tenant_architecture_profile(
                      tenant_id,profile_key,name,reference_model_key,reference_model_version,
                      version,status,state,fingerprint,created_by,updated_by
                    ) VALUES (%s,%s,%s,%s,%s,1,'DRAFT',%s::jsonb,%s,%s,%s)
                    RETURNING *
                    """,
                    (
                        tenant_id, request.profile_key, request.state.name,
                        request.state.reference_model_key, request.state.reference_model_version,
                        json.dumps(state), fingerprint, actor_key, actor_key,
                    ),
                )
                row = await cursor.fetchone()
                await self._write_architecture_profile_revision(
                    connection, tenant_id=tenant_id, profile_id=row["id"], version=1,
                    status="DRAFT", state=state, fingerprint=fingerprint, actor_key=actor_key,
                )
        except UniqueViolation as error:
            raise APIError(
                409, "ARCHITECTURE_PROFILE_EXISTS",
                "An architecture profile with this key already exists.",
                {"profile_key": request.profile_key},
            ) from error
        return self._architecture_profile_detail(row)

    async def update_architecture_profile(
        self, profile_id: UUID, request: ArchitectureProfileUpdateRequest,
        *, tenant_id: UUID | None, actor_key: str,
    ) -> ArchitectureProfileDetail:
        if tenant_id is None:
            raise APIError(400, "TENANT_REQUIRED", "A tenant ID is required to update an architecture profile.")
        self._validate_architecture_profile_state(request.state)
        state = request.state.model_dump(mode="json")
        fingerprint = architecture_fingerprint(state)
        async with self.database.session(tenant_id) as connection:
            existing = await self._lock_architecture_profile(connection, profile_id)
            if existing["status"] != "DRAFT":
                raise APIError(
                    409, "ARCHITECTURE_PROFILE_NOT_EDITABLE",
                    "Only draft architecture profiles can be edited.",
                )
            self._require_architecture_profile_version(existing, request.expected_version)
            version = existing["version"] + 1
            cursor = await connection.execute(
                """
                UPDATE tenant_architecture_profile
                SET name=%s,reference_model_key=%s,reference_model_version=%s,
                    version=%s,state=%s::jsonb,fingerprint=%s,updated_by=%s,updated_at=now()
                WHERE id=%s RETURNING *
                """,
                (
                    request.state.name, request.state.reference_model_key,
                    request.state.reference_model_version, version, json.dumps(state),
                    fingerprint, actor_key, profile_id,
                ),
            )
            row = await cursor.fetchone()
            await self._write_architecture_profile_revision(
                connection, tenant_id=tenant_id, profile_id=profile_id, version=version,
                status="DRAFT", state=state, fingerprint=fingerprint, actor_key=actor_key,
            )
        return self._architecture_profile_detail(row)

    async def publish_architecture_profile(
        self, profile_id: UUID, request: ArchitectureProfilePublishRequest,
        *, tenant_id: UUID | None, actor_key: str,
    ) -> ArchitectureProfileDetail:
        if tenant_id is None:
            raise APIError(400, "TENANT_REQUIRED", "A tenant ID is required to publish an architecture profile.")
        async with self.database.session(tenant_id) as connection:
            existing = await self._lock_architecture_profile(connection, profile_id)
            if existing["status"] != "DRAFT":
                raise APIError(
                    409, "ARCHITECTURE_PROFILE_NOT_PUBLISHABLE",
                    "Only draft architecture profiles can be published.",
                )
            self._require_architecture_profile_version(existing, request.expected_version)
            state = self._architecture_profile_state(existing["state"])
            self._validate_architecture_profile_state(state)
            active_cursor = await connection.execute(
                """
                SELECT * FROM tenant_architecture_profile
                WHERE id<>%s AND reference_model_key=%s AND reference_model_version=%s
                  AND status='ACTIVE'
                FOR UPDATE
                """,
                (
                    profile_id, existing["reference_model_key"],
                    existing["reference_model_version"],
                ),
            )
            for active in await active_cursor.fetchall():
                archived_version = active["version"] + 1
                await connection.execute(
                    """
                    UPDATE tenant_architecture_profile
                    SET status='ARCHIVED',version=%s,updated_by=%s,updated_at=now()
                    WHERE id=%s
                    """,
                    (archived_version, actor_key, active["id"]),
                )
                await self._write_architecture_profile_revision(
                    connection, tenant_id=tenant_id, profile_id=active["id"],
                    version=archived_version, status="ARCHIVED",
                    state=self._json_object(active["state"]), fingerprint=active["fingerprint"],
                    actor_key=actor_key,
                )
            version = existing["version"] + 1
            cursor = await connection.execute(
                """
                UPDATE tenant_architecture_profile
                SET status='ACTIVE',version=%s,updated_by=%s,updated_at=now()
                WHERE id=%s RETURNING *
                """,
                (version, actor_key, profile_id),
            )
            row = await cursor.fetchone()
            await self._write_architecture_profile_revision(
                connection, tenant_id=tenant_id, profile_id=profile_id, version=version,
                status="ACTIVE", state=state.model_dump(mode="json"),
                fingerprint=existing["fingerprint"], actor_key=actor_key,
            )
        return self._architecture_profile_detail(row)

    @staticmethod
    def _json_object(value: Any) -> dict[str, Any]:
        parsed = json.loads(value) if isinstance(value, str) else value
        if not isinstance(parsed, dict):
            raise APIError(500, "INVALID_PERSISTED_PROFILE", "The stored architecture profile is invalid.")
        return parsed

    @classmethod
    def _architecture_profile_state(cls, value: Any) -> ArchitectureProfileStateModel:
        return ArchitectureProfileStateModel.model_validate(cls._json_object(value))

    @staticmethod
    def _architecture_profile_summary(row: dict[str, Any]) -> ArchitectureProfileSummary:
        return ArchitectureProfileSummary(
            id=row["id"], profile_key=row["profile_key"], name=row["name"],
            reference_model_key=row["reference_model_key"],
            reference_model_version=row["reference_model_version"],
            version=row["version"], status=row["status"], fingerprint=row["fingerprint"],
            created_at=row["created_at"], updated_at=row["updated_at"],
        )

    @classmethod
    def _architecture_profile_detail(cls, row: dict[str, Any]) -> ArchitectureProfileDetail:
        summary = cls._architecture_profile_summary(row)
        return ArchitectureProfileDetail(
            **summary.model_dump(), state=cls._architecture_profile_state(row["state"]),
        )

    @staticmethod
    def _validate_architecture_profile_state(state: ArchitectureProfileStateModel) -> None:
        catalog = load_architecture_catalog()
        if (
            state.reference_model_key != catalog.reference_model.key
            or state.reference_model_version != catalog.reference_model.version
        ):
            raise APIError(
                422, "ARCHITECTURE_REFERENCE_MODEL_MISMATCH",
                "The profile must target the canonical reference-model key and version.",
                {
                    "expected_key": catalog.reference_model.key,
                    "expected_version": catalog.reference_model.version,
                },
            )
        unknown_cells = sorted(
            {policy.cell_key for policy in state.cell_policies} - set(catalog.cells_by_key)
        )
        if unknown_cells:
            raise APIError(
                422, "ARCHITECTURE_PROFILE_UNKNOWN_CELL",
                "The profile references unknown canonical cells.",
                {"cell_keys": unknown_cells},
            )
        known_aspects = {aspect.key for aspect in catalog.taxonomy.aspects}
        known_capabilities = {capability.key for capability in catalog.taxonomy.capabilities}
        for extension in state.extension_cells:
            unknown_aspects = sorted(set(extension.aspect_keys) - known_aspects)
            if unknown_aspects:
                raise APIError(
                    422, "ARCHITECTURE_PROFILE_UNKNOWN_ASPECT",
                    "An extension cell references unknown aspects.",
                    {"cell_key": extension.key, "aspect_keys": unknown_aspects},
                )
            for binding in extension.bindings:
                if binding.kind == "CAPABILITY":
                    unknown = sorted(set(binding.keys) - known_capabilities)
                    if unknown:
                        raise APIError(
                            422, "ARCHITECTURE_PROFILE_UNKNOWN_CAPABILITY",
                            "An extension cell references unknown canonical capabilities.",
                            {"cell_key": extension.key, "capability_keys": unknown},
                        )

    async def _lock_architecture_profile(self, connection: Any, profile_id: UUID) -> dict[str, Any]:
        cursor = await connection.execute(
            "SELECT * FROM tenant_architecture_profile WHERE id=%s FOR UPDATE", (profile_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            raise APIError(404, "ARCHITECTURE_PROFILE_NOT_FOUND", "The architecture profile was not found.")
        return row

    @staticmethod
    def _require_architecture_profile_version(row: dict[str, Any], expected_version: int) -> None:
        if row["version"] != expected_version:
            raise APIError(
                409, "VERSION_CONFLICT",
                "The architecture profile changed before this operation was applied.",
                {"expected_version": expected_version, "actual_version": row["version"]},
            )

    @staticmethod
    async def _write_architecture_profile_revision(
        connection: Any, *, tenant_id: UUID, profile_id: UUID, version: int,
        status: str, state: dict[str, Any], fingerprint: str, actor_key: str,
    ) -> None:
        await connection.execute(
            """
            INSERT INTO tenant_architecture_profile_revision(
              tenant_id,profile_id,version,status,state,fingerprint,actor_key
            ) VALUES (%s,%s,%s,%s,%s::jsonb,%s,%s)
            """,
            (tenant_id, profile_id, version, status, json.dumps(state), fingerprint, actor_key),
        )

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
              UNION ALL
              SELECT similarity.id, 'APPLICATION_SIMILARITY', similarity.review_state, NULL::uuid,
                     similarity.score, 1, similarity.created_at,
                     concat(left_app.name, ' ↔ ', right_app.name),
                     concat('Explainable application similarity ',round(similarity.score::numeric*100),' percent')
              FROM application_similarity_candidate similarity
              JOIN entity left_app ON left_app.id=similarity.left_entity_id
              JOIN entity right_app ON right_app.id=similarity.right_entity_id
              WHERE similarity.review_state='UNREVIEWED'
                AND similarity.entity_kind='Application'
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
            UNION ALL SELECT 'APPLICATION_SIMILARITY', count(*)
              FROM application_similarity_candidate WHERE review_state = 'UNREVIEWED'
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
        _token, token_source = await self._github_token(tenant_id)
        credential_reference = (
            "tenant-secret://github-token"
            if token_source == "TENANT_SECRET"
            else request.credential_reference
        )
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
                    credential_reference,
                    json.dumps(scopes),
                ),
            )
            account = await account_cursor.fetchone()
            assert account is not None
            connection_policy = json.dumps({
                "provider": "github",
                "direct_repository": True,
                "owner": owner,
                "name": name,
                "full_name": full_name,
                "activity_enabled": True,
                "cadence_seconds": cadence_seconds,
                "schedule_enabled": schedule_enabled,
            })
            # A repository that has been scanned before no longer carries the key it was created
            # with: the first successful scan promotes `github:repo-name:<owner>/<name>` to the
            # canonical `github:repo:<id>`. Its durable identity is the full name in the refresh
            # policy, so that is what a re-add matches on.
            #
            # Upserting on the pending key instead misses the promoted row and inserts a second
            # target for one repository — and the next scan promotes that one onto the key the
            # first already holds, raising a unique violation far from the action that caused it.
            #
            # A repository renamed on GitHub while it was stopped is not matched here: the
            # request carries only the new owner/name, and the repository id that would identify
            # it is not known until a scan runs. That case still collides at promotion, and is
            # left visible rather than papered over with a guess about which row it meant.
            existing_cursor = await connection.execute(
                """
                SELECT id,target_key,enabled,disabled_at,disabled_by
                FROM ingest_target
                WHERE tenant_id=%s AND source_system_id=%s AND target_kind='REPOSITORY'
                  AND (target_key=%s OR lower(refresh_policy->>'full_name')=%s)
                ORDER BY (target_key=%s) DESC,created_at
                LIMIT 1
                FOR UPDATE
                """,
                (
                    tenant_id, source["id"], pending_target_key, normalized_name,
                    pending_target_key,
                ),
            )
            existing_target = await existing_cursor.fetchone()
            if existing_target is None:
                target_cursor = await connection.execute(
                    """
                    INSERT INTO ingest_target(
                      tenant_id,source_system_id,connector_account_id,target_kind,target_key,
                      priority,enabled,refresh_policy,next_due_at
                    ) VALUES (%s,%s,%s,'REPOSITORY',%s,'HOT',true,%s::jsonb,
                              CASE WHEN %s THEN now() ELSE NULL END)
                    ON CONFLICT(tenant_id,source_system_id,target_kind,target_key) DO UPDATE
                      SET connector_account_id=EXCLUDED.connector_account_id,enabled=true,
                          refresh_policy=ingest_target.refresh_policy||EXCLUDED.refresh_policy,
                          disabled_at=NULL,disabled_by=NULL,
                          next_due_at=EXCLUDED.next_due_at,updated_at=now()
                    RETURNING id
                    """,
                    (
                        tenant_id, source["id"], account["id"], pending_target_key,
                        connection_policy, schedule_enabled,
                    ),
                )
            else:
                # Resume the row rather than replace it. The stored policy is merged into, not
                # overwritten, so what the first scan learned — repository id, default branch,
                # visibility — survives a stop and restart instead of being rediscovered as
                # though the repository had never been seen.
                target_cursor = await connection.execute(
                    """
                    UPDATE ingest_target
                    SET connector_account_id=%s,enabled=true,
                        refresh_policy=refresh_policy||%s::jsonb,
                        disabled_at=NULL,disabled_by=NULL,
                        next_due_at=CASE WHEN %s THEN now() ELSE NULL END,
                        updated_at=now()
                    WHERE id=%s
                    RETURNING id
                    """,
                    (account["id"], connection_policy, schedule_enabled, existing_target["id"]),
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
                    credential_reference,
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
        token, _source = await self._github_token(tenant_id)
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

    async def get_github_token_configuration(
        self, *, tenant_id: UUID | None,
    ) -> GitHubTokenConfiguration:
        if tenant_id is None:
            raise APIError(400, "TENANT_REQUIRED", "A tenant ID is required to read GitHub configuration.")
        row = await self.database.fetch_one(
            """
            SELECT fingerprint,created_by,updated_at
            FROM tenant_secret
            WHERE secret_kind='GITHUB_TOKEN'
            ORDER BY updated_at DESC,id DESC LIMIT 1
            """,
            tenant_id=tenant_id,
        )
        if row is not None:
            return GitHubTokenConfiguration(
                configured=True,
                fingerprint=row["fingerprint"],
                source="TENANT_SECRET",
                updated_by=row["created_by"],
                updated_at=row["updated_at"],
            )
        environment_token = os.getenv("GITHUB_TOKEN", "").strip()
        return GitHubTokenConfiguration(
            configured=bool(environment_token),
            fingerprint=environment_token[-4:] if environment_token else None,
            source="ENVIRONMENT" if environment_token else "NONE",
        )

    async def update_github_token(
        self,
        request: GitHubTokenUpdateRequest,
        *,
        tenant_id: UUID | None,
        actor_key: str,
    ) -> GitHubTokenConfiguration:
        if tenant_id is None:
            raise APIError(400, "TENANT_REQUIRED", "A tenant ID is required to update GitHub configuration.")
        token = request.token.strip()
        if not token:
            raise APIError(422, "GITHUB_TOKEN_EMPTY", "The GitHub token cannot be empty.")
        credential_reference = "tenant-secret://github-token"
        async with self.database.session(tenant_id) as connection:
            await connection.execute(
                "DELETE FROM tenant_secret WHERE secret_kind='GITHUB_TOKEN'",
            )
            cursor = await connection.execute(
                """
                INSERT INTO tenant_secret(
                  tenant_id,secret_kind,ciphertext,fingerprint,created_by
                ) VALUES (
                  %s,'GITHUB_TOKEN',
                  pgp_sym_encrypt(%s,%s,'cipher-algo=aes256'),%s,%s
                ) RETURNING fingerprint,created_by,updated_at
                """,
                (tenant_id, token, self.credential_encryption_key, token[-4:], actor_key),
            )
            row = await cursor.fetchone()
            assert row is not None
            await connection.execute(
                """
                UPDATE connector_account
                SET credential_reference=%s,status='ACTIVE',updated_at=now()
                WHERE external_account_key LIKE 'github:repository:%%'
                """,
                (credential_reference,),
            )
            await connection.execute(
                """
                UPDATE connector
                SET credential_reference=%s,status='CONNECTED',last_error=NULL,updated_at=now()
                WHERE provider='GITHUB_APP'
                  AND external_account_key LIKE 'github:repository:%%'
                """,
                (credential_reference,),
            )
            await self._write_admin_audit(
                connection,
                tenant_id=tenant_id,
                actor_key=actor_key,
                action="github_token.update",
                target_kind="tenant_github_configuration",
                target_id=tenant_id,
                detail={"key_rotated": True, "fingerprint": token[-4:]},
            )
        return GitHubTokenConfiguration(
            configured=True,
            fingerprint=row["fingerprint"],
            source="TENANT_SECRET",
            updated_by=row["created_by"],
            updated_at=row["updated_at"],
        )

    async def remove_github_token(
        self, *, tenant_id: UUID | None, actor_key: str,
    ) -> GitHubTokenConfiguration:
        if tenant_id is None:
            raise APIError(400, "TENANT_REQUIRED", "A tenant ID is required to update GitHub configuration.")
        environment_token = os.getenv("GITHUB_TOKEN", "").strip()
        async with self.database.session(tenant_id) as connection:
            await connection.execute(
                "DELETE FROM tenant_secret WHERE secret_kind='GITHUB_TOKEN'",
            )
            replacement = "env://GITHUB_TOKEN"
            await connection.execute(
                """
                UPDATE connector_account
                SET credential_reference=%s,status=%s,updated_at=now()
                WHERE external_account_key LIKE 'github:repository:%%'
                """,
                (replacement, "ACTIVE" if environment_token else "DISABLED"),
            )
            await connection.execute(
                """
                UPDATE connector
                SET credential_reference=%s,status=%s,updated_at=now()
                WHERE provider='GITHUB_APP'
                  AND external_account_key LIKE 'github:repository:%%'
                """,
                (replacement, "CONNECTED" if environment_token else "NEEDS_REAUTH"),
            )
            await self._write_admin_audit(
                connection,
                tenant_id=tenant_id,
                actor_key=actor_key,
                action="github_token.remove",
                target_kind="tenant_github_configuration",
                target_id=tenant_id,
                detail={"environment_fallback": bool(environment_token)},
            )
        return GitHubTokenConfiguration(
            configured=bool(environment_token),
            fingerprint=environment_token[-4:] if environment_token else None,
            source="ENVIRONMENT" if environment_token else "NONE",
        )

    async def _github_token(self, tenant_id: UUID) -> tuple[str, str]:
        row = await self.database.fetch_one(
            """
            SELECT pgp_sym_decrypt(ciphertext,%s)::text AS token
            FROM tenant_secret
            WHERE secret_kind='GITHUB_TOKEN'
            ORDER BY updated_at DESC,id DESC LIMIT 1
            """,
            (self.credential_encryption_key,),
            tenant_id=tenant_id,
        )
        if row is not None and str(row["token"]).strip():
            return str(row["token"]).strip(), "TENANT_SECRET"
        environment_token = os.getenv("GITHUB_TOKEN", "").strip()
        return environment_token, "ENVIRONMENT" if environment_token else "NONE"

    async def connect_github_installation(
        self,
        request: GitHubInstallationConnectRequest,
        *,
        tenant_id: UUID | None,
        actor_key: str,
    ) -> Connector:
        if tenant_id is None:
            raise APIError(400, "TENANT_REQUIRED", "A tenant ID is required to connect GitHub.")
        async with self.database.session(tenant_id) as connection:
            row = await self._connect_github_installation(
                connection,
                tenant_id=tenant_id,
                actor_key=actor_key,
                installation_id=request.installation_id,
                display_name=request.display_name,
                scopes=["contents:read", "metadata:read"],
                binding_mode="MANUAL_PILOT",
                audit_detail={
                    "pilot_manual_binding_acknowledged": request.pilot_manual_binding_acknowledged,
                },
            )
        return self._connector(row)

    async def begin_github_installation_setup(
        self,
        *,
        state_hash: str,
        return_to: str,
        expires_at: datetime,
        tenant_id: UUID | None,
        actor_key: str,
    ) -> None:
        if tenant_id is None:
            raise APIError(400, "TENANT_REQUIRED", "A tenant ID is required to connect GitHub.")
        async with self.database.session(tenant_id) as connection:
            await connection.execute(
                """
                DELETE FROM github_installation_setup
                WHERE tenant_id=%s AND consumed_at IS NULL AND expires_at<now()
                """,
                (tenant_id,),
            )
            await connection.execute(
                """
                INSERT INTO github_installation_setup(
                  tenant_id,actor_key,state_hash,return_to,expires_at
                ) VALUES (%s,%s,%s,%s,%s)
                """,
                (tenant_id, actor_key, state_hash, return_to, expires_at),
            )
            await self._write_admin_audit(
                connection,
                tenant_id=tenant_id,
                actor_key=actor_key,
                action="github_installation.setup_started",
                target_kind="github_installation_setup",
                target_id=state_hash,
                detail={"expires_at": expires_at.isoformat()},
            )

    async def validate_github_installation_setup(
        self,
        *,
        state_hash: str,
        tenant_id: UUID | None,
        actor_key: str,
    ) -> str:
        if tenant_id is None:
            raise APIError(400, "TENANT_REQUIRED", "A tenant ID is required to connect GitHub.")
        async with self.database.session(tenant_id) as connection:
            cursor = await connection.execute(
                """
                SELECT actor_key,return_to,expires_at,consumed_at
                FROM github_installation_setup
                WHERE state_hash=%s
                """,
                (state_hash,),
            )
            setup = await cursor.fetchone()
            self._validate_github_setup_row(setup, actor_key=actor_key)
            return str(setup["return_to"])

    async def complete_hosted_github_installation(
        self,
        *,
        state_hash: str,
        installation_id: str,
        account_login: str,
        account_id: int,
        target_type: str,
        scopes: list[str],
        tenant_id: UUID | None,
        actor_key: str,
    ) -> Connector:
        if tenant_id is None:
            raise APIError(400, "TENANT_REQUIRED", "A tenant ID is required to connect GitHub.")
        async with self.database.session(tenant_id) as connection:
            cursor = await connection.execute(
                """
                SELECT actor_key,return_to,expires_at,consumed_at
                FROM github_installation_setup
                WHERE state_hash=%s
                FOR UPDATE
                """,
                (state_hash,),
            )
            setup = await cursor.fetchone()
            self._validate_github_setup_row(setup, actor_key=actor_key)
            await connection.execute(
                """
                UPDATE github_installation_setup
                SET consumed_at=now(),installation_id=%s
                WHERE state_hash=%s AND consumed_at IS NULL
                """,
                (installation_id, state_hash),
            )
            row = await self._connect_github_installation(
                connection,
                tenant_id=tenant_id,
                actor_key=actor_key,
                installation_id=installation_id,
                display_name=f"{account_login} GitHub installation",
                scopes=scopes,
                binding_mode="HOSTED_SETUP",
                audit_detail={
                    "github_account_login": account_login,
                    "github_account_id": account_id,
                    "github_target_type": target_type,
                    "setup_state_hash": state_hash,
                },
            )
        return self._connector(row)

    @staticmethod
    def _validate_github_setup_row(setup: Any, *, actor_key: str) -> None:
        if setup is None or setup["actor_key"] != actor_key:
            raise APIError(401, "GITHUB_SETUP_STATE_INVALID", "The GitHub setup state is invalid.")
        if setup["consumed_at"] is not None:
            raise APIError(409, "GITHUB_SETUP_STATE_REPLAYED", "The GitHub setup state has already been used.")
        if setup["expires_at"] <= datetime.now(UTC):
            raise APIError(410, "GITHUB_SETUP_STATE_EXPIRED", "The GitHub setup state has expired.")

    async def _connect_github_installation(
        self,
        connection: Any,
        *,
        tenant_id: UUID,
        actor_key: str,
        installation_id: str,
        display_name: str | None,
        scopes: list[str],
        binding_mode: str,
        audit_detail: dict[str, Any],
    ) -> Any:
        external_account_key = f"github:installation:{installation_id}"
        credential_reference = f"github-app://installation/{installation_id}"
        normalized_display_name = display_name or f"GitHub installation {installation_id}"

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
                    tenant_id, normalized_display_name, external_account_key, credential_reference, scopes,
                    json.dumps({
                        "connection_mode": "GITHUB_APP_INSTALLATION",
                        "binding_mode": binding_mode,
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
            detail={
                "installation_id": installation_id,
                "ingest_target_id": str(target["id"]),
                "binding_mode": binding_mode,
                **audit_detail,
            },
        )
        return row

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
                    SET enabled=false,next_due_at=NULL,
                        disabled_at=now(),disabled_by=%s,updated_at=now()
                    FROM ingest_target root
                    WHERE root.id=%s AND (
                      target.id=root.id OR target.connector_account_id=root.connector_account_id
                    )
                    """,
                    (actor_key, target_id),
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

    # --- Admin: deterministic insight governance -------------------------

    async def get_deterministic_insight_governance(
        self, *, tenant_id: UUID | None,
    ) -> DeterministicInsightGovernanceState:
        if tenant_id is None:
            raise APIError(400, "TENANT_REQUIRED", "A tenant ID is required to read insight governance.")
        stored = await self.database.fetch_all(
            "SELECT * FROM deterministic_insight_rule_policy ORDER BY rule_key",
            tenant_id=tenant_id,
        )
        policies = {row["rule_key"]: row for row in stored}
        findings = await list_deterministic_insights(
            self.database, tenant_id=tenant_id, limit=500,
        )
        finding_counts: dict[str, int] = defaultdict(int)
        for finding in findings.insights:
            finding_counts[finding.rule_key] += 1
            if (finding.stages.production or 0) > 0 or (finding.stages.externally_exposed or 0) > 0:
                finding_counts["deployment.external-exposure"] += 1
            if (finding.stages.business_critical or 0) > 0:
                finding_counts["business.critical-impact"] += 1
        rules = []
        for definition in RULE_CATALOG:
            policy = policies.get(definition["key"])
            rules.append(DeterministicInsightRuleSummary(
                rule_key=definition["key"], name=definition["name"],
                description=definition["description"], phase=definition["phase"],
                readiness=definition["readiness"],
                enabled=bool(policy["enabled"] if policy else definition["readiness"] == "ACTIVE"),
                severity=policy["severity"] if policy else definition["severity"],
                minimum_repositories=int(
                    policy["minimum_repositories"]
                    if policy else definition.get("minimum_repositories", 1)
                ),
                configuration={
                    **dict(definition.get("configuration") or {}),
                    **dict(policy["configuration"] if policy else {}),
                },
                version=int(policy["version"] if policy else 0),
                finding_count=finding_counts[definition["key"]],
                missing_inputs=list(definition["missing"]),
                updated_by=policy.get("updated_by") if policy else None,
                updated_at=policy.get("updated_at") if policy else None,
            ))
        coverage = (
            sum(item.evidence_coverage for item in findings.insights) / len(findings.insights)
            if findings.insights else 0.0
        )
        return DeterministicInsightGovernanceState(
            method_version=DETERMINISTIC_METHOD_VERSION,
            rules=rules,
            active_rule_count=sum(rule.enabled and rule.readiness == "ACTIVE" for rule in rules),
            needs_data_rule_count=sum(rule.readiness == "NEEDS_DATA" for rule in rules),
            finding_count=findings.summary.total,
            evidence_coverage=coverage,
            last_evaluated_at=findings.as_of,
        )

    async def update_deterministic_insight_rule(
        self, rule_key: str, request: DeterministicInsightRuleUpdateRequest,
        *, tenant_id: UUID | None, actor_key: str,
    ) -> DeterministicInsightGovernanceState:
        if tenant_id is None:
            raise APIError(400, "TENANT_REQUIRED", "A tenant ID is required to govern insight rules.")
        definition = next((item for item in RULE_CATALOG if item["key"] == rule_key), None)
        if definition is None:
            raise APIError(404, "INSIGHT_RULE_NOT_FOUND", "The deterministic insight rule was not found.")
        if request.enabled and definition["readiness"] == "NEEDS_DATA":
            raise APIError(
                422, "INSIGHT_RULE_INPUTS_MISSING",
                "This rule cannot be enabled until its authoritative inputs are available.",
                {"missing_inputs": list(definition["missing"])},
            )
        async with self.database.session(tenant_id) as connection:
            cursor = await connection.execute(
                "SELECT * FROM deterministic_insight_rule_policy WHERE rule_key=%s FOR UPDATE",
                (rule_key,),
            )
            existing = await cursor.fetchone()
            current_version = int(existing["version"]) if existing else 0
            if request.expected_version != current_version:
                raise APIError(
                    409, "INSIGHT_RULE_VERSION_CONFLICT",
                    "The rule policy changed. Reload the current governance state and try again.",
                    {"current_version": current_version},
                )
            resulting_version = current_version + 1
            if existing:
                await connection.execute(
                    """
                    UPDATE deterministic_insight_rule_policy
                    SET enabled=%s,severity=%s,minimum_repositories=%s,configuration=%s::jsonb,
                        version=%s,updated_by=%s,updated_at=now()
                    WHERE id=%s
                    """,
                    (request.enabled, request.severity, request.minimum_repositories,
                     json.dumps(request.configuration), resulting_version, actor_key, existing["id"]),
                )
                policy_id = existing["id"]
            else:
                insert = await connection.execute(
                    """
                    INSERT INTO deterministic_insight_rule_policy(
                      tenant_id,rule_key,enabled,severity,minimum_repositories,
                      configuration,version,updated_by
                    ) VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s,%s) RETURNING id
                    """,
                    (tenant_id, rule_key, request.enabled, request.severity,
                     request.minimum_repositories, json.dumps(request.configuration),
                     resulting_version, actor_key),
                )
                policy_id = (await insert.fetchone())["id"]
            await connection.execute(
                """
                INSERT INTO deterministic_insight_rule_policy_revision(
                  tenant_id,rule_policy_id,prior_version,resulting_version,enabled,severity,
                  minimum_repositories,configuration,actor_key
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s)
                """,
                (tenant_id, policy_id, current_version, resulting_version, request.enabled,
                 request.severity, request.minimum_repositories,
                 json.dumps(request.configuration), actor_key),
            )
            await self._write_admin_audit(
                connection, tenant_id=tenant_id, actor_key=actor_key,
                action="deterministic_insight_rule.update",
                target_kind="deterministic_insight_rule", target_id=rule_key,
                detail={"version": resulting_version, "enabled": request.enabled},
            )
        return await self.get_deterministic_insight_governance(tenant_id=tenant_id)

    # --- Admin: modernization governance ---------------------------------

    async def get_modernization_governance(
        self, *, tenant_id: UUID | None,
    ) -> ModernizationGovernanceState:
        if tenant_id is None:
            raise APIError(400, "TENANT_REQUIRED", "A tenant ID is required to read governance.")
        async with self.database.session(tenant_id) as connection:
            return await self._modernization_governance_state(connection)

    async def publish_modernization_policy(
        self, request: ModernizationPolicyPublishRequest,
        *, tenant_id: UUID | None, actor_key: str,
    ) -> ModernizationGovernanceState:
        if tenant_id is None:
            raise APIError(400, "TENANT_REQUIRED", "A tenant ID is required to publish policy.")
        async with self.database.session(tenant_id) as connection:
            components = await self._governed_component_payload(connection)
            policy_payload = request.model_dump(mode="json")
            configuration_fingerprint = sha256_fingerprint({
                "version": "tenant-modernization-configuration/v1",
                "policy": policy_payload,
                "internal_components": components,
            })
            content_hash = sha256_fingerprint(policy_payload)
            existing_cursor = await connection.execute(
                """
                SELECT content_hash FROM modernization_policy
                WHERE policy_key=%s AND version=%s
                """,
                (request.policy_key, request.version),
            )
            existing = await existing_cursor.fetchone()
            if existing is not None and existing["content_hash"] != content_hash:
                raise APIError(
                    409, "POLICY_VERSION_IMMUTABLE",
                    "Publish policy changes under a new version.",
                    {"policy_key": request.policy_key, "version": request.version},
                )
            await connection.execute(
                """
                UPDATE modernization_policy
                SET status='RETIRED',retired_by=%s,retired_at=now(),updated_at=now()
                WHERE policy_key=%s AND status='ACTIVE' AND version<>%s
                """,
                (actor_key, request.policy_key, request.version),
            )
            await connection.execute(
                """
                INSERT INTO modernization_policy(
                  tenant_id,policy_key,version,status,runtime_versions,allowed_licenses,
                  denied_option_keys,allowed_security_statuses,required_policy_tags,
                  metadata,content_hash,configuration_fingerprint,created_by,activated_by,activated_at
                ) VALUES (%s,%s,%s,'ACTIVE',%s::jsonb,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s,now())
                ON CONFLICT(tenant_id,policy_key,version) DO UPDATE SET
                  status='ACTIVE',configuration_fingerprint=EXCLUDED.configuration_fingerprint,
                  activated_by=EXCLUDED.activated_by,activated_at=now(),retired_by=NULL,
                  retired_at=NULL,updated_at=now()
                """,
                (
                    tenant_id, request.policy_key, request.version,
                    json.dumps(request.runtime_versions), request.allowed_licenses,
                    request.denied_option_keys, request.allowed_security_statuses,
                    request.required_policy_tags,
                    json.dumps({"fingerprint_version": "tenant-modernization-configuration/v1"}),
                    content_hash, configuration_fingerprint, actor_key, actor_key,
                ),
            )
            await self._enqueue_governed_reanalysis(connection, tenant_id, configuration_fingerprint)
            await self._write_admin_audit(
                connection, tenant_id=tenant_id, actor_key=actor_key,
                action="modernization_policy.publish", target_kind="modernization_policy",
                target_id=f"{request.policy_key}/{request.version}",
                detail={"configuration_fingerprint": configuration_fingerprint},
            )
            return await self._modernization_governance_state(connection)

    async def govern_internal_component(
        self, component_key: str, request: InternalCatalogComponentUpsertRequest,
        *, tenant_id: UUID | None, actor_key: str,
    ) -> ModernizationGovernanceState:
        if tenant_id is None:
            raise APIError(400, "TENANT_REQUIRED", "A tenant ID is required to govern the catalog.")
        normalized_key = component_key.strip()
        if not normalized_key or len(normalized_key) > 255:
            raise APIError(422, "INVALID_COMPONENT_KEY", "The component key is invalid.")
        async with self.database.session(tenant_id) as connection:
            entity_cursor = await connection.execute(
                "SELECT id,name FROM entity WHERE id=%s", (request.component_entity_id,),
            )
            entity = await entity_cursor.fetchone()
            if entity is None:
                raise APIError(422, "COMPONENT_NOT_FOUND", "The internal component entity was not found.")
            capability_cursor = await connection.execute(
                "SELECT id FROM capability_definition WHERE id=%s", (request.capability_definition_id,),
            )
            if await capability_cursor.fetchone() is None:
                raise APIError(422, "CAPABILITY_NOT_FOUND", "The capability definition was not found.")
            fact_cursor = await connection.execute(
                "SELECT id FROM current_fact WHERE id=ANY(%s::uuid[])",
                (request.supporting_fact_ids,),
            )
            found_fact_ids = {row["id"] for row in await fact_cursor.fetchall()}
            missing_fact_ids = [
                str(fact_id) for fact_id in request.supporting_fact_ids
                if fact_id not in found_fact_ids
            ]
            if missing_fact_ids:
                raise APIError(
                    422, "INTERNAL_COMPONENT_EVIDENCE_NOT_FOUND",
                    "Approved internal components require current tenant evidence.",
                    {"fact_ids": missing_fact_ids},
                )
            review_state = "APPROVED" if request.decision == "APPROVE" else "REJECTED"
            payload = {"component_key": normalized_key, **request.model_dump(mode="json")}
            catalog_fingerprint = sha256_fingerprint(payload)
            await connection.execute(
                """
                INSERT INTO modernization_internal_component(
                  tenant_id,component_entity_id,capability_definition_id,component_key,version,
                  status,api_symbols,runtime_constraints,behavior_claims,license,security_status,
                  policy_tags,supporting_fact_ids,metadata,review_state,owner,governed_by,
                  governed_at,catalog_fingerprint
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,now(),%s)
                ON CONFLICT(tenant_id,component_key,version) DO UPDATE SET
                  component_entity_id=EXCLUDED.component_entity_id,
                  capability_definition_id=EXCLUDED.capability_definition_id,status=EXCLUDED.status,
                  api_symbols=EXCLUDED.api_symbols,runtime_constraints=EXCLUDED.runtime_constraints,
                  behavior_claims=EXCLUDED.behavior_claims,license=EXCLUDED.license,
                  security_status=EXCLUDED.security_status,policy_tags=EXCLUDED.policy_tags,
                  supporting_fact_ids=EXCLUDED.supporting_fact_ids,review_state=EXCLUDED.review_state,
                  owner=EXCLUDED.owner,governed_by=EXCLUDED.governed_by,governed_at=now(),
                  catalog_fingerprint=EXCLUDED.catalog_fingerprint,updated_at=now()
                """,
                (
                    tenant_id, request.component_entity_id, request.capability_definition_id,
                    normalized_key, request.version, request.status, request.api_symbols,
                    json.dumps(request.runtime_constraints), json.dumps(request.behavior_claims),
                    request.license, request.security_status, request.policy_tags,
                    request.supporting_fact_ids, json.dumps({"decision": request.decision}),
                    review_state, request.owner, actor_key, catalog_fingerprint,
                ),
            )
            fingerprint = await self._current_governance_fingerprint(connection)
            if fingerprint is not None:
                await connection.execute(
                    """
                    UPDATE modernization_policy SET configuration_fingerprint=%s,updated_at=now()
                    WHERE status='ACTIVE'
                    """,
                    (fingerprint,),
                )
                await self._enqueue_governed_reanalysis(connection, tenant_id, fingerprint)
            await self._write_admin_audit(
                connection, tenant_id=tenant_id, actor_key=actor_key,
                action="internal_component.govern", target_kind="modernization_internal_component",
                target_id=f"{normalized_key}/{request.version}",
                detail={"decision": request.decision, "catalog_fingerprint": catalog_fingerprint},
            )
            return await self._modernization_governance_state(connection)

    async def publish_calibration_corpus(
        self, request: CalibrationCorpusPublishRequest,
        *, tenant_id: UUID | None, actor_key: str,
    ) -> ModernizationGovernanceState:
        if tenant_id is None:
            raise APIError(400, "TENANT_REQUIRED", "A tenant ID is required to publish calibration.")
        if any(
            not value.startswith("sha256:")
            or len(value) != 71
            or any(character not in "0123456789abcdef" for character in value[7:])
            for value in request.case_fingerprints
        ):
            raise APIError(422, "INVALID_CASE_FINGERPRINT", "Calibration cases require sha256 fingerprints.")
        case_fingerprints = sorted(set(request.case_fingerprints))
        thresholds = CalibrationThresholds(
            minimum_candidate_precision=request.minimum_candidate_precision,
            minimum_recommendation_acceptance=request.minimum_recommendation_acceptance,
            minimum_validation_success=request.minimum_validation_success,
            maximum_affected_scope_mae=request.maximum_affected_scope_mae,
            minimum_effort_accuracy=request.minimum_effort_accuracy,
            minimum_reviewed_cases=request.minimum_reviewed_cases,
        )
        async with self.database.session(tenant_id) as connection:
            metrics, case_manifest = await self._derive_calibration_metrics(
                connection, case_fingerprints,
            )
            result = evaluate_promotion_gate(metrics, thresholds)
            metrics_source_version = "persisted-review-outcomes/v1"
            corpus_fingerprint = sha256_fingerprint({
                "corpus_key": request.corpus_key,
                "version": request.version,
                "case_manifest": case_manifest,
                "metrics_source_version": metrics_source_version,
            })
            existing_cursor = await connection.execute(
                """
                SELECT corpus_fingerprint FROM modernization_calibration_corpus
                WHERE corpus_key=%s AND version=%s
                """,
                (request.corpus_key, request.version),
            )
            existing = await existing_cursor.fetchone()
            if existing is not None:
                if existing["corpus_fingerprint"] != corpus_fingerprint:
                    raise APIError(
                        409,
                        "CALIBRATION_VERSION_IMMUTABLE",
                        "This calibration version already identifies a different evidence manifest.",
                    )
                return await self._modernization_governance_state(connection)
            await connection.execute(
                "UPDATE modernization_calibration_corpus SET status='RETIRED',updated_at=now() WHERE corpus_key=%s AND status='ACTIVE'",
                (request.corpus_key,),
            )
            cursor = await connection.execute(
                """
                INSERT INTO modernization_calibration_corpus(
                  tenant_id,corpus_key,version,status,case_count,case_fingerprints,
                  thresholds,observed_metrics,corpus_fingerprint,promotion_passed,
                  promotion_failures,evaluation_fingerprint,evaluated_at,created_by,
                  case_manifest,metrics_source_version
                ) VALUES (%s,%s,%s,'ACTIVE',%s,%s,%s::jsonb,%s::jsonb,%s,%s,%s,%s,now(),%s,%s::jsonb,%s)
                RETURNING id
                """,
                (
                    tenant_id, request.corpus_key, request.version,
                    len(case_fingerprints), case_fingerprints,
                    json.dumps({field: getattr(thresholds, field) for field in thresholds.__dataclass_fields__}),
                    json.dumps({field: getattr(metrics, field) for field in metrics.__dataclass_fields__}),
                    corpus_fingerprint, result.passed, list(result.failures), result.fingerprint, actor_key,
                    json.dumps(case_manifest), metrics_source_version,
                ),
            )
            corpus_id = (await cursor.fetchone())["id"]
            if result.passed:
                weights = {
                    "business": 0.25, "viability_gap": 0.2, "entropy": 0.2,
                    "reuse": 0.2, "confidence": 0.15,
                }
                policy_fingerprint = sha256_fingerprint({
                    "version": "modernization-portfolio/v1",
                    "weights": weights, "effort_penalty_weight": 0.2,
                    "calibration": corpus_fingerprint,
                })
                await connection.execute(
                    "UPDATE modernization_portfolio_policy SET status='RETIRED',updated_at=now() WHERE policy_key='modernization.portfolio' AND status='ACTIVE'",
                )
                await connection.execute(
                    """
                    INSERT INTO modernization_portfolio_policy(
                      tenant_id,policy_key,version,status,weights,effort_penalty_weight,
                      policy_fingerprint,calibration_corpus_id,created_by
                    ) VALUES (%s,'modernization.portfolio',%s,'ACTIVE',%s::jsonb,0.2,%s,%s,%s)
                    ON CONFLICT(tenant_id,policy_key,version) DO UPDATE SET
                      status='ACTIVE',weights=EXCLUDED.weights,
                      policy_fingerprint=EXCLUDED.policy_fingerprint,
                      calibration_corpus_id=EXCLUDED.calibration_corpus_id,updated_at=now()
                    """,
                    (tenant_id, request.version, json.dumps(weights), policy_fingerprint, corpus_id, actor_key),
                )
            await self._write_admin_audit(
                connection, tenant_id=tenant_id, actor_key=actor_key,
                action="calibration_corpus.publish", target_kind="modernization_calibration_corpus",
                target_id=f"{request.corpus_key}/{request.version}",
                detail={"promotion_passed": result.passed, "failures": list(result.failures)},
            )
            return await self._modernization_governance_state(connection)

    async def _derive_calibration_metrics(
        self,
        connection: Any,
        case_fingerprints: list[str],
    ) -> tuple[CalibrationMetrics, list[dict[str, Any]]]:
        candidate_cursor = await connection.execute(
            """
            SELECT id,analysis_fingerprint,source_revision,input_fingerprint,review_state
            FROM modernization_candidate
            WHERE analysis_fingerprint=ANY(%s::text[])
              AND review_state<>'UNREVIEWED' AND stale_at IS NULL
            """,
            (case_fingerprints,),
        )
        candidate_rows = await candidate_cursor.fetchall()
        recommendation_cursor = await connection.execute(
            """
            SELECT recommendation.id,recommendation.analysis_fingerprint,
                   recommendation.source_revision,recommendation.input_fingerprint,
                   recommendation.review_state,recommendation.affected_call_sites,
                   recommendation.affected_files,recommendation.estimated_effort,
                   outcome.id validation_outcome_id,outcome.validation_status,
                   outcome.actual_call_sites,outcome.actual_files,outcome.actual_effort,
                   outcome.reported_at
            FROM modernization_recommendation recommendation
            LEFT JOIN LATERAL (
              SELECT validation.* FROM modernization_validation_outcome validation
              WHERE validation.modernization_recommendation_id=recommendation.id
              ORDER BY validation.reported_at DESC,validation.id DESC LIMIT 1
            ) outcome ON true
            WHERE recommendation.analysis_fingerprint=ANY(%s::text[])
              AND recommendation.review_state<>'UNREVIEWED'
              AND recommendation.stale_at IS NULL
            """,
            (case_fingerprints,),
        )
        recommendation_rows = await recommendation_cursor.fetchall()
        found = [
            *(str(row["analysis_fingerprint"]) for row in candidate_rows),
            *(str(row["analysis_fingerprint"]) for row in recommendation_rows),
        ]
        duplicate_fingerprints = sorted({fingerprint for fingerprint in found if found.count(fingerprint) > 1})
        if duplicate_fingerprints:
            raise APIError(
                422,
                "CALIBRATION_CASE_AMBIGUOUS",
                "A calibration fingerprint must identify exactly one reviewed analysis.",
                {"case_fingerprints": duplicate_fingerprints},
            )
        missing_cases = sorted(set(case_fingerprints) - set(found))
        if missing_cases:
            raise APIError(
                422,
                "CALIBRATION_CASE_NOT_REVIEWED",
                "Calibration cases must reference current reviewed candidate or recommendation fingerprints.",
                {"case_fingerprints": missing_cases},
            )

        candidate_precision = (
            sum(row["review_state"] == "CONFIRMED" for row in candidate_rows) / len(candidate_rows)
            if candidate_rows else None
        )
        recommendation_acceptance = (
            sum(row["review_state"] == "ACCEPTED" for row in recommendation_rows)
            / len(recommendation_rows)
            if recommendation_rows else None
        )
        accepted = [row for row in recommendation_rows if row["review_state"] == "ACCEPTED"]
        validations_complete = bool(accepted) and all(row["validation_outcome_id"] is not None for row in accepted)
        validation_success = (
            sum(row["validation_status"] == "SUCCEEDED" for row in accepted) / len(accepted)
            if validations_complete else None
        )
        scope_complete = validations_complete and all(
            row["actual_call_sites"] is not None and row["actual_files"] is not None
            for row in accepted
        )
        scope_errors: list[float] = []
        if scope_complete:
            for row in accepted:
                call_site_error = abs(row["actual_call_sites"] - row["affected_call_sites"]) / max(
                    row["actual_call_sites"], 1,
                )
                file_error = abs(row["actual_files"] - row["affected_files"]) / max(
                    row["actual_files"], 1,
                )
                scope_errors.append((call_site_error + file_error) / 2)
        affected_scope_mae = sum(scope_errors) / len(scope_errors) if scope_errors else None
        effort_complete = validations_complete and all(
            row["actual_effort"] not in {None, "UNKNOWN"} for row in accepted
        )
        effort_accuracy = (
            sum(row["actual_effort"] == row["estimated_effort"] for row in accepted) / len(accepted)
            if effort_complete else None
        )

        manifest: list[dict[str, Any]] = []
        for row in candidate_rows:
            manifest.append({
                "kind": "CANDIDATE",
                "analysis_fingerprint": row["analysis_fingerprint"],
                "analysis_id": str(row["id"]),
                "source_revision": row["source_revision"],
                "input_fingerprint": row["input_fingerprint"],
                "review_state": row["review_state"],
            })
        for row in recommendation_rows:
            manifest.append({
                "kind": "RECOMMENDATION",
                "analysis_fingerprint": row["analysis_fingerprint"],
                "analysis_id": str(row["id"]),
                "source_revision": row["source_revision"],
                "input_fingerprint": row["input_fingerprint"],
                "review_state": row["review_state"],
                "validation": ({
                    "id": str(row["validation_outcome_id"]),
                    "status": row["validation_status"],
                    "actual_call_sites": row["actual_call_sites"],
                    "actual_files": row["actual_files"],
                    "actual_effort": row["actual_effort"],
                    "reported_at": row["reported_at"].isoformat(),
                } if row["validation_outcome_id"] is not None else None),
            })
        manifest.sort(key=lambda item: (item["analysis_fingerprint"], item["kind"]))
        return CalibrationMetrics(
            candidate_precision=candidate_precision,
            recommendation_acceptance=recommendation_acceptance,
            validation_success=validation_success,
            affected_scope_mae=affected_scope_mae,
            effort_accuracy=effort_accuracy,
            reviewed_cases=len(manifest),
        ), manifest

    async def evaluate_ecosystem_admission(
        self, ecosystem: EcosystemName, request: EcosystemAdmissionEvaluateRequest,
        *, tenant_id: UUID | None, actor_key: str,
    ) -> ModernizationGovernanceState:
        if tenant_id is None:
            raise APIError(400, "TENANT_REQUIRED", "A tenant ID is required to evaluate ecosystem admission.")
        sequence = _ECOSYSTEM_SEQUENCE[ecosystem]
        async with self.database.session(tenant_id) as connection:
            predecessor_admitted = True
            if sequence > 1:
                predecessor = next(
                    item for item, item_sequence in _ECOSYSTEM_SEQUENCE.items()
                    if item_sequence == sequence - 1
                )
                current = await self._ecosystem_governance_state(connection)
                predecessor_admitted = next(
                    item.status == "ADMITTED" for item in current if item.ecosystem == predecessor
                )
            observed_repositories, observed_dependency_share = await self._ecosystem_demand(
                connection, ecosystem,
            )
            calibration_gate_passed = await self._calibration_gate_passed(connection)
            metadata_parity = _ECOSYSTEM_METADATA_PARITY[ecosystem]
            decision = decide_ecosystem_admission(
                EcosystemDemand(
                    ecosystem=ecosystem,
                    observed_repositories=observed_repositories,
                    observed_dependency_share=observed_dependency_share,
                    metadata_parity=metadata_parity,
                    calibration_gate_passed=calibration_gate_passed,
                ),
                predecessor_admitted=predecessor_admitted,
                minimum_repositories=request.minimum_repositories,
                minimum_dependency_share=request.minimum_dependency_share,
            )
            status = "ADMITTED" if decision.admitted else "PROPOSED"
            await connection.execute(
                """
                INSERT INTO ecosystem_admission(
                  tenant_id,ecosystem,sequence,status,observed_repositories,
                  observed_dependency_share,minimum_repositories,minimum_dependency_share,
                  metadata_parity,calibration_gate_passed,decision_fingerprint,reasons,decided_by
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT(tenant_id,ecosystem) DO UPDATE SET
                  sequence=EXCLUDED.sequence,status=EXCLUDED.status,
                  observed_repositories=EXCLUDED.observed_repositories,
                  observed_dependency_share=EXCLUDED.observed_dependency_share,
                  minimum_repositories=EXCLUDED.minimum_repositories,
                  minimum_dependency_share=EXCLUDED.minimum_dependency_share,
                  metadata_parity=EXCLUDED.metadata_parity,
                  calibration_gate_passed=EXCLUDED.calibration_gate_passed,
                  decision_fingerprint=EXCLUDED.decision_fingerprint,
                  reasons=EXCLUDED.reasons,decided_by=EXCLUDED.decided_by,decided_at=now()
                """,
                (
                    tenant_id, ecosystem, sequence, status, observed_repositories,
                    observed_dependency_share, request.minimum_repositories,
                    request.minimum_dependency_share, metadata_parity,
                    calibration_gate_passed, decision.fingerprint,
                    list(decision.reasons), actor_key,
                ),
            )
            await self._write_admin_audit(
                connection, tenant_id=tenant_id, actor_key=actor_key,
                action="ecosystem_admission.evaluate", target_kind="ecosystem_admission",
                target_id=ecosystem,
                detail={
                    "status": status,
                    "observed_repositories": observed_repositories,
                    "observed_dependency_share": observed_dependency_share,
                    "metadata_parity": metadata_parity,
                    "calibration_gate_passed": calibration_gate_passed,
                    "predecessor_admitted": predecessor_admitted,
                    "decision_fingerprint": decision.fingerprint,
                    "reasons": list(decision.reasons),
                },
            )
            return await self._modernization_governance_state(connection)

    async def _ecosystem_demand(
        self, connection: Any, ecosystem: EcosystemName,
    ) -> tuple[int, float]:
        purl_pattern = f"pkg:{_ECOSYSTEM_PURL_TYPE[ecosystem]}/%"
        cursor = await connection.execute(
            """
            SELECT
              count(DISTINCT fact.subject_entity_id)
                FILTER (WHERE package.canonical_key LIKE %s) observed_repositories,
              coalesce(
                count(*) FILTER (WHERE package.canonical_key LIKE %s)::numeric
                  / nullif(count(*),0),
                0
              ) observed_dependency_share
            FROM dependency_usage_summary usage
            JOIN current_fact fact ON fact.id=usage.dependency_fact_assertion_id
            JOIN entity package ON package.id=fact.object_entity_id
            WHERE usage.tenant_id=stackgraph_current_tenant_id()
              AND (usage.referenced OR usage.runtime_observed='OBSERVED')
            """,
            (purl_pattern, purl_pattern),
        )
        row = await cursor.fetchone()
        return int(row["observed_repositories"] or 0), float(row["observed_dependency_share"] or 0)

    async def _calibration_gate_passed(self, connection: Any) -> bool:
        cursor = await connection.execute(
            """
            SELECT 1 FROM modernization_calibration_corpus
            WHERE status='ACTIVE' AND promotion_passed
            LIMIT 1
            """
        )
        return await cursor.fetchone() is not None

    async def _ecosystem_governance_state(
        self, connection: Any,
    ) -> list[EcosystemAdmissionSummary]:
        cursor = await connection.execute(
            "SELECT * FROM ecosystem_admission ORDER BY sequence"
        )
        recorded = {row["ecosystem"]: row for row in await cursor.fetchall()}
        calibration_gate_passed = await self._calibration_gate_passed(connection)
        summaries: list[EcosystemAdmissionSummary] = []
        predecessor_admitted = True
        for ecosystem, sequence in _ECOSYSTEM_SEQUENCE.items():
            row = recorded.get(ecosystem)
            minimum_repositories = int(row["minimum_repositories"]) if row else 10
            minimum_dependency_share = float(row["minimum_dependency_share"]) if row else 0.02
            observed_repositories, observed_dependency_share = await self._ecosystem_demand(
                connection, ecosystem,
            )
            decision = decide_ecosystem_admission(
                EcosystemDemand(
                    ecosystem=ecosystem,
                    observed_repositories=observed_repositories,
                    observed_dependency_share=observed_dependency_share,
                    metadata_parity=_ECOSYSTEM_METADATA_PARITY[ecosystem],
                    calibration_gate_passed=calibration_gate_passed,
                ),
                predecessor_admitted=predecessor_admitted,
                minimum_repositories=minimum_repositories,
                minimum_dependency_share=minimum_dependency_share,
            )
            if row is None:
                status = "NOT_EVALUATED"
            elif row["decision_fingerprint"] != decision.fingerprint:
                status = "STALE"
            else:
                status = row["status"]
            summaries.append(EcosystemAdmissionSummary(
                ecosystem=ecosystem, sequence=sequence, status=status,
                observed_repositories=observed_repositories,
                observed_dependency_share=observed_dependency_share,
                minimum_repositories=minimum_repositories,
                minimum_dependency_share=minimum_dependency_share,
                predecessor_admitted=predecessor_admitted,
                metadata_parity=_ECOSYSTEM_METADATA_PARITY[ecosystem],
                calibration_gate_passed=calibration_gate_passed,
                reasons=list(decision.reasons), decision_fingerprint=decision.fingerprint,
                decided_by=row["decided_by"] if row else None,
                decided_at=row["decided_at"] if row else None,
            ))
            predecessor_admitted = status == "ADMITTED"
        return summaries

    async def _modernization_governance_state(self, connection: Any) -> ModernizationGovernanceState:
        cursor = await connection.execute(
            "SELECT * FROM modernization_policy WHERE status='ACTIVE' ORDER BY updated_at DESC,id LIMIT 1"
        )
        policy = await cursor.fetchone()
        cursor = await connection.execute(
            """
            SELECT component.*,entity.name FROM modernization_internal_component component
            JOIN entity ON entity.id=component.component_entity_id
            ORDER BY component.component_key,component.version
            """
        )
        components = await cursor.fetchall()
        cursor = await connection.execute(
            """
            SELECT DISTINCT ON (component.canonical_key,candidate.capability_definition_id)
                   candidate.id candidate_id,component.id component_entity_id,
                   component.canonical_key component_key,component.name,
                   repository.name repository_name,
                   candidate.capability_definition_id,capability.name capability,
                   candidate.confidence,
                   coalesce(impact.affected_call_sites,0)::integer affected_call_sites,
                   coalesce(impact.affected_files,0)::integer affected_files,
                   ARRAY(
                     SELECT DISTINCT fact_id
                     FROM unnest(
                       candidate.supporting_fact_ids || option.supporting_fact_ids
                       || ARRAY[publication.id]
                     ) fact_id
                     ORDER BY fact_id
                   ) supporting_fact_ids
            FROM modernization_candidate candidate
            JOIN modernization_option option
              ON option.modernization_candidate_id=candidate.id
             AND option.option_kind='INTERNAL' AND option.target_entity_id IS NOT NULL
            JOIN entity repository ON repository.id=option.target_entity_id
              AND repository.namespace='ENTERPRISE' AND repository.entity_type='Repository'
            JOIN fact_assertion publication
              ON publication.subject_entity_id=repository.id
             AND publication.predicate='PUBLISHES' AND publication.system_to IS NULL
             AND publication.assertion_class='DECLARED'
             AND coalesce((publication.properties->>'internal')::boolean,false)
            JOIN entity component ON component.id=publication.object_entity_id
              AND component.namespace='TECHNOLOGY'
              AND component.entity_type IN ('Package','PackageVersion')
              AND component.canonical_key LIKE 'registry:%%'
            JOIN capability_definition capability
              ON capability.id=candidate.capability_definition_id
            LEFT JOIN modernization_impact impact
              ON impact.modernization_candidate_id=candidate.id
            WHERE candidate.stale_at IS NULL AND candidate.review_state<>'REJECTED'
              AND candidate.confidence>=0.8
              AND option.name !~* '^(test_|main$)'
              AND option.canonical_key NOT LIKE '%%:tests/%%'
              AND option.canonical_key NOT LIKE '%%/__tests__/%%'
              AND NOT EXISTS (
                SELECT 1 FROM modernization_internal_component component
                WHERE component.component_entity_id=publication.object_entity_id
                  AND component.capability_definition_id=candidate.capability_definition_id
                  AND component.review_state='APPROVED'
              )
            ORDER BY component.canonical_key,candidate.capability_definition_id,
                     candidate.confidence DESC,option.score DESC,candidate.id
            LIMIT 50
            """
        )
        component_candidates = await cursor.fetchall()
        cursor = await connection.execute(
            "SELECT * FROM modernization_calibration_corpus WHERE status='ACTIVE' ORDER BY updated_at DESC,id LIMIT 1"
        )
        calibration = await cursor.fetchone()
        return ModernizationGovernanceState(
            active_policy=ModernizationPolicySummary(
                id=policy["id"], policy_key=policy["policy_key"], version=policy["version"],
                status=policy["status"], runtime_versions=dict(policy["runtime_versions"]),
                allowed_licenses=list(policy["allowed_licenses"]),
                denied_option_keys=list(policy["denied_option_keys"]),
                allowed_security_statuses=list(policy["allowed_security_statuses"]),
                required_policy_tags=list(policy["required_policy_tags"]),
                configuration_fingerprint=(
                    policy["configuration_fingerprint"]
                    or sha256_fingerprint({"legacy_policy_content_hash": policy["content_hash"]})
                ),
                activated_by=policy["activated_by"] or policy["created_by"],
                activated_at=policy["activated_at"] or policy["created_at"],
            ) if policy else None,
            internal_components=[InternalCatalogComponentSummary(
                id=row["id"], component_key=row["component_key"], version=row["version"],
                name=row["name"], status=row["status"], review_state=row["review_state"],
                owner=row["owner"], catalog_fingerprint=(
                    row["catalog_fingerprint"]
                    or sha256_fingerprint({
                        "component_key": row["component_key"], "version": row["version"]
                    })
                ),
                supporting_fact_ids=list(row["supporting_fact_ids"]),
                governed_by=row["governed_by"], governed_at=row["governed_at"],
            ) for row in components],
            internal_component_candidates=[InternalCatalogCandidateSummary(
                candidate_id=row["candidate_id"],
                component_entity_id=row["component_entity_id"],
                component_key=row["component_key"], name=row["name"],
                repository_name=row["repository_name"],
                capability_definition_id=row["capability_definition_id"],
                capability=row["capability"], confidence=_number(row["confidence"]),
                affected_call_sites=row["affected_call_sites"],
                affected_files=row["affected_files"],
                supporting_fact_ids=list(row["supporting_fact_ids"]),
            ) for row in component_candidates],
            active_calibration=CalibrationCorpusSummary(
                id=calibration["id"], corpus_key=calibration["corpus_key"],
                version=calibration["version"], case_count=calibration["case_count"],
                corpus_fingerprint=calibration["corpus_fingerprint"],
                observed_metrics=CalibrationObservedMetrics(**calibration["observed_metrics"]),
                metrics_source_version=calibration["metrics_source_version"],
                promotion_passed=calibration["promotion_passed"],
                promotion_failures=list(calibration["promotion_failures"]),
                evaluation_fingerprint=calibration["evaluation_fingerprint"],
                evaluated_at=calibration["evaluated_at"],
            ) if calibration else None,
            ecosystem_admissions=await self._ecosystem_governance_state(connection),
        )

    async def _governed_component_payload(self, connection: Any) -> list[dict[str, Any]]:
        cursor = await connection.execute(
            """
            SELECT component_key,version,status,review_state,catalog_fingerprint
            FROM modernization_internal_component
            WHERE review_state='APPROVED'
            ORDER BY component_key,version
            """
        )
        return [dict(row) for row in await cursor.fetchall()]

    async def _current_governance_fingerprint(self, connection: Any) -> str | None:
        cursor = await connection.execute(
            "SELECT * FROM modernization_policy WHERE status='ACTIVE' ORDER BY updated_at DESC,id LIMIT 1"
        )
        policy = await cursor.fetchone()
        if policy is None:
            return None
        return sha256_fingerprint({
            "version": "tenant-modernization-configuration/v1",
            "policy": {
                "key": policy["policy_key"], "version": policy["version"],
                "content_hash": policy["content_hash"],
            },
            "internal_components": await self._governed_component_payload(connection),
        })

    async def _enqueue_governed_reanalysis(
        self, connection: Any, tenant_id: UUID, configuration_fingerprint: str,
    ) -> None:
        await connection.execute(
            """
            INSERT INTO intelligence_job(
              tenant_id,repository_entity_id,source_snapshot_id,source_revision,
              job_kind,configuration_fingerprint
            )
            SELECT DISTINCT ON (repository.id)
              %s,repository.id,snapshot.id,snapshot.source_revision,
              'REPOSITORY_MODERNIZATION',%s
            FROM source_snapshot snapshot
            JOIN ingest_target target ON target.id=snapshot.ingest_target_id
            JOIN entity repository
              ON repository.tenant_id=%s AND repository.namespace='ENTERPRISE'
             AND repository.entity_type='Repository' AND repository.canonical_key=target.target_key
            WHERE snapshot.status='PUBLISHED' AND snapshot.completeness='COMPLETE'
              AND snapshot.extractor_key='repository-dependency-usage'
            ORDER BY repository.id,snapshot.published_at DESC,snapshot.id DESC
            ON CONFLICT DO NOTHING
            """,
            (tenant_id, configuration_fingerprint, tenant_id),
        )

    # --- Admin: tenant code policies ------------------------------------

    async def get_tenant_code_policies(
        self, *, tenant_id: UUID | None,
    ) -> TenantCodePolicyState:
        if tenant_id is None:
            raise APIError(400, "TENANT_REQUIRED", "A tenant ID is required to read code policies.")
        async with self.database.session(tenant_id) as connection:
            return await self._tenant_code_policy_state(connection)

    async def upsert_tenant_code_function(
        self, function_key: str, request: TenantCodeFunctionUpsertRequest,
        *, tenant_id: UUID | None, actor_key: str,
    ) -> TenantCodePolicyState:
        if tenant_id is None:
            raise APIError(400, "TENANT_REQUIRED", "A tenant ID is required to update code policies.")
        normalized_key = function_key.strip().lower()
        if re.fullmatch(r"[a-z][a-z0-9.-]{1,127}", normalized_key) is None:
            raise APIError(422, "INVALID_CODE_FUNCTION_KEY", "The code function key is invalid.")
        allowed_ids = sorted(set(request.allowed_technology_ids), key=str)
        prohibited_ids = sorted(set(request.prohibited_technology_ids), key=str)
        if set(allowed_ids) & set(prohibited_ids):
            raise APIError(
                422, "CODE_POLICY_TECHNOLOGY_CONFLICT",
                "A technology cannot be both allowed and prohibited for the same function.",
            )

        async with self.database.session(tenant_id) as connection:
            primary_cursor = await connection.execute(
                """
                SELECT id,name,properties FROM entity
                WHERE tenant_id IS NULL AND namespace='TECHNOLOGY' AND entity_type='Capability'
                  AND coalesce(properties->>'capability_key',replace(canonical_key,'stackgraph:capability:',''))=%s
                LIMIT 1
                """,
                (normalized_key,),
            )
            primary = await primary_cursor.fetchone()
            custom_cursor = await connection.execute(
                "SELECT * FROM tenant_code_function WHERE function_key=%s",
                (normalized_key,),
            )
            custom = await custom_cursor.fetchone()

            if request.source == "PRIMARY":
                if primary is None:
                    raise APIError(
                        422, "PRIMARY_CODE_FUNCTION_NOT_FOUND",
                        "The requested primary StackGraph function does not exist.",
                    )
                if request.status != "ACTIVE":
                    raise APIError(
                        422, "PRIMARY_CODE_FUNCTION_IMMUTABLE",
                        "Primary StackGraph functions cannot be retired by a tenant.",
                    )
                if custom is not None:
                    raise APIError(
                        409, "CODE_FUNCTION_SOURCE_CONFLICT",
                        "A custom function already uses this primary function key.",
                    )
                function_name = str(primary["name"])
                primary_properties = primary.get("properties") if isinstance(primary.get("properties"), dict) else {}
                function_description = str(primary_properties.get("definition") or "")
                domain_key = str(primary_properties.get("domain_id") or request.domain_key)
            else:
                if primary is not None:
                    raise APIError(
                        409, "CUSTOM_CODE_FUNCTION_SHADOWS_PRIMARY",
                        "Custom functions cannot replace a primary StackGraph function key.",
                    )
                function_name = request.name.strip()
                function_description = request.description.strip()
                domain_key = request.domain_key
                await connection.execute(
                    """
                    INSERT INTO tenant_code_function(
                      tenant_id,function_key,name,description,domain_key,status,created_by,updated_by
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT(tenant_id,function_key) DO UPDATE SET
                      name=EXCLUDED.name,description=EXCLUDED.description,
                      domain_key=EXCLUDED.domain_key,status=EXCLUDED.status,
                      updated_by=EXCLUDED.updated_by,updated_at=now()
                    """,
                    (
                        tenant_id, normalized_key, function_name, function_description,
                        domain_key, request.status, actor_key, actor_key,
                    ),
                )

            requested_technology_ids = allowed_ids + prohibited_ids
            if requested_technology_ids:
                technology_cursor = await connection.execute(
                    """
                    SELECT id FROM entity
                    WHERE id=ANY(%s::uuid[]) AND namespace IN ('TECHNOLOGY','OSS')
                    """,
                    (requested_technology_ids,),
                )
                found = {row["id"] for row in await technology_cursor.fetchall()}
                missing = [str(item) for item in requested_technology_ids if item not in found]
                if missing:
                    raise APIError(
                        422, "CODE_POLICY_TECHNOLOGY_NOT_FOUND",
                        "Every policy technology must be visible to the tenant.",
                        {"technology_ids": missing},
                    )

            policy_payload = {
                "version": "tenant-code-policy/v1",
                "function_key": normalized_key,
                "function_source": request.source,
                "function": {
                    "name": function_name,
                    "description": function_description,
                    "domain_key": domain_key,
                    "status": request.status,
                },
                "allowed_technology_ids": [str(item) for item in allowed_ids],
                "prohibited_technology_ids": [str(item) for item in prohibited_ids],
            }
            policy_fingerprint = sha256_fingerprint(policy_payload)
            await connection.execute(
                """
                INSERT INTO tenant_code_policy(
                  tenant_id,function_key,function_source,allowed_technology_ids,
                  prohibited_technology_ids,policy_fingerprint,updated_by
                ) VALUES (%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT(tenant_id,function_key) DO UPDATE SET
                  function_source=EXCLUDED.function_source,
                  allowed_technology_ids=EXCLUDED.allowed_technology_ids,
                  prohibited_technology_ids=EXCLUDED.prohibited_technology_ids,
                  policy_fingerprint=EXCLUDED.policy_fingerprint,
                  updated_by=EXCLUDED.updated_by,updated_at=now()
                """,
                (
                    tenant_id, normalized_key, request.source, allowed_ids,
                    prohibited_ids, policy_fingerprint, actor_key,
                ),
            )
            await self._write_admin_audit(
                connection, tenant_id=tenant_id, actor_key=actor_key,
                action="code_policy.upsert", target_kind="tenant_code_policy",
                target_id=normalized_key,
                detail={
                    "source": request.source,
                    "status": request.status,
                    "allowed_technology_count": len(allowed_ids),
                    "prohibited_technology_count": len(prohibited_ids),
                    "policy_fingerprint": policy_fingerprint,
                },
            )
            return await self._tenant_code_policy_state(connection)

    async def evaluate_tenant_code_policies(
        self, *, tenant_id: UUID | None, actor_key: str,
    ) -> TenantCodePolicyState:
        if tenant_id is None:
            raise APIError(400, "TENANT_REQUIRED", "A tenant ID is required to evaluate code policies.")
        async with self.database.session(tenant_id) as connection:
            definitions = await self._code_policy_definitions(connection)
            policy_set_fingerprint = self._code_policy_set_fingerprint(definitions)
            active_policies = {
                key: value for key, value in definitions.items()
                if value["status"] == "ACTIVE" and value.get("policy") is not None
            }
            repository_cursor = await connection.execute(
                """
                SELECT * FROM entity
                WHERE tenant_id=%s AND namespace='ENTERPRISE' AND entity_type='Repository'
                ORDER BY name,id
                """,
                (tenant_id,),
            )
            repositories = await repository_cursor.fetchall()
            usage_cursor = await connection.execute(
                """
                SELECT repository.id repository_id,fact.id fact_id,technology.*
                FROM entity repository
                JOIN current_fact fact
                  ON fact.subject_entity_id=repository.id
                 AND fact.predicate IN ('DEPENDS_ON','USES','RUNS_ON','BUILT_ON','HAS_VERSION')
                JOIN entity technology ON technology.id=fact.object_entity_id
                WHERE repository.tenant_id=%s
                  AND repository.namespace='ENTERPRISE' AND repository.entity_type='Repository'
                  AND technology.namespace IN ('TECHNOLOGY','OSS')
                ORDER BY repository.id,technology.name,technology.id,fact.id
                """,
                (tenant_id,),
            )
            usage_rows = await usage_cursor.fetchall()
            catalog_rows = await self._code_policy_catalog_rows(connection)
            from app.read_models import _resolve_technology_catalog_entry, _technology_catalog_index
            catalog_by_id, catalog_by_key = _technology_catalog_index(catalog_rows)
            usage_by_repository: dict[UUID, list[dict[str, Any]]] = defaultdict(list)
            for row in usage_rows:
                usage_by_repository[UUID(str(row["repository_id"]))].append(row)

            status_counts = {"COMPLIANT": 0, "MISALIGNED": 0, "UNASSESSED": 0}
            for repository in repositories:
                repository_id = UUID(str(repository["id"]))
                violations: dict[tuple[str, str, UUID], dict[str, Any]] = {}
                unclassified: dict[UUID, EntitySummary] = {}
                evidence_manifest: list[dict[str, Any]] = []
                for usage in usage_by_repository.get(repository_id, []):
                    actual_id = UUID(str(usage["id"]))
                    resolved, _direct = _resolve_technology_catalog_entry(
                        usage, catalog_by_id, catalog_by_key,
                    )
                    resolved_id = UUID(str(resolved["row"]["id"])) if resolved else actual_id
                    candidate_ids = {actual_id, resolved_id}
                    function_keys = {
                        str(item.get("capability_key") or "").strip()
                        for item in (resolved["capabilities"] if resolved else [])
                        if str(item.get("capability_key") or "").strip()
                    }
                    for function_key, definition in active_policies.items():
                        if definition["source"] != "CUSTOM":
                            continue
                        policy = definition["policy"]
                        governed_ids = set(policy["allowed_technology_ids"]) | set(policy["prohibited_technology_ids"])
                        if candidate_ids & governed_ids:
                            function_keys.add(function_key)
                    if not function_keys:
                        unclassified[actual_id] = self._code_policy_entity_summary(usage)

                    evidence_manifest.append({
                        "fact_id": str(usage["fact_id"]),
                        "technology_id": str(actual_id),
                        "matched_technology_id": str(resolved_id),
                        "function_keys": sorted(function_keys),
                    })
                    for function_key in sorted(function_keys):
                        definition = active_policies.get(function_key)
                        if definition is None:
                            continue
                        policy = definition["policy"]
                        prohibited = set(policy["prohibited_technology_ids"])
                        allowed = set(policy["allowed_technology_ids"])
                        rule = None
                        if candidate_ids & prohibited:
                            rule = "PROHIBITED"
                        elif allowed and not candidate_ids & allowed:
                            rule = "NOT_ALLOWED"
                        if rule is None:
                            continue
                        key = (rule, function_key, actual_id)
                        violation = violations.setdefault(key, {
                            "rule": rule,
                            "function_key": function_key,
                            "function_name": definition["name"],
                            "technology": self._code_policy_entity_summary(usage).model_dump(mode="json"),
                            "matched_technology_id": str(resolved_id),
                            "fact_ids": [],
                            "message": (
                                f"{usage['name']} is strictly prohibited for {definition['name']}."
                                if rule == "PROHIBITED"
                                else f"{usage['name']} is not in the allowlist for {definition['name']}."
                            ),
                        })
                        fact_id = str(usage["fact_id"])
                        if fact_id not in violation["fact_ids"]:
                            violation["fact_ids"].append(fact_id)

                evidence_manifest.sort(key=lambda item: (
                    item["technology_id"], item["fact_id"], item["matched_technology_id"],
                ))
                evidence_fingerprint = sha256_fingerprint({
                    "version": "repository-code-policy-evidence/v1",
                    "repository_id": str(repository_id),
                    "usage": evidence_manifest,
                })
                if not active_policies or not evidence_manifest:
                    status = "UNASSESSED"
                else:
                    status = "MISALIGNED" if violations else "COMPLIANT"
                status_counts[status] += 1
                details = {
                    "violations": sorted(
                        violations.values(),
                        key=lambda item: (item["function_name"].lower(), item["technology"]["name"].lower(), item["rule"]),
                    ),
                    "unclassified_technologies": [
                        value.model_dump(mode="json") for _key, value in sorted(
                            unclassified.items(), key=lambda item: (item[1].name.lower(), str(item[0])),
                        )
                    ],
                    "evidence_fact_ids": sorted({item["fact_id"] for item in evidence_manifest}),
                }
                await connection.execute(
                    """
                    INSERT INTO repository_code_policy_evaluation(
                      tenant_id,repository_entity_id,policy_set_fingerprint,evidence_fingerprint,
                      status,violation_count,unclassified_count,details,evaluated_by
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s)
                    ON CONFLICT(tenant_id,repository_entity_id,policy_set_fingerprint,evidence_fingerprint)
                    DO UPDATE SET status=EXCLUDED.status,violation_count=EXCLUDED.violation_count,
                      unclassified_count=EXCLUDED.unclassified_count,details=EXCLUDED.details,
                      evaluated_by=EXCLUDED.evaluated_by,evaluated_at=now()
                    """,
                    (
                        tenant_id, repository_id, policy_set_fingerprint, evidence_fingerprint,
                        status, len(violations), len(unclassified), json.dumps(details), actor_key,
                    ),
                )

            await self._write_admin_audit(
                connection, tenant_id=tenant_id, actor_key=actor_key,
                action="code_policy.evaluate", target_kind="repository_code_policy_evaluation",
                target_id="estate",
                detail={
                    "policy_set_fingerprint": policy_set_fingerprint,
                    "repository_count": len(repositories),
                    "status_counts": status_counts,
                },
            )
            return await self._tenant_code_policy_state(connection)

    async def _tenant_code_policy_state(self, connection: Any) -> TenantCodePolicyState:
        definitions = await self._code_policy_definitions(connection)
        policy_set_fingerprint = self._code_policy_set_fingerprint(definitions)
        technology_rows = await self._code_policy_available_technologies(connection)
        catalog_rows = await self._code_policy_catalog_rows(connection)
        from app.read_models import _resolve_technology_catalog_entry, _technology_catalog_index
        catalog_by_id, catalog_by_key = _technology_catalog_index(catalog_rows)
        technology_catalog_truncated = len(technology_rows) > 2000
        available_technologies: list[CodePolicyTechnologySummary] = []
        for row in technology_rows[:2000]:
            resolved, direct = _resolve_technology_catalog_entry(row, catalog_by_id, catalog_by_key)
            properties = resolved["row"].get("properties", {}) if resolved else {}
            classification = "UNCLASSIFIED"
            if resolved is not None:
                classification = "CURATED" if direct else "CATALOG_MATCH"
            available_technologies.append(CodePolicyTechnologySummary(
                technology=self._code_policy_entity_summary(row),
                classification=classification,
                domain_key=str(properties.get("domain_id")) if properties.get("domain_id") else None,
                category_key=str(properties.get("category_id")) if properties.get("category_id") else None,
                detected_repository_count=int(row.get("detected_repository_count") or 0),
            ))

        evaluation_cursor = await connection.execute(
            """
            SELECT DISTINCT ON (evaluation.repository_entity_id)
                   evaluation.*,repository.name repository_name,
                   repository.canonical_key repository_canonical_key,
                   repository.properties repository_properties
            FROM repository_code_policy_evaluation evaluation
            JOIN entity repository ON repository.id=evaluation.repository_entity_id
            ORDER BY evaluation.repository_entity_id,evaluation.evaluated_at DESC,evaluation.id DESC
            """
        )
        current_evidence_cursor = await connection.execute(
            """
            SELECT repository.id repository_id,array_agg(fact.id ORDER BY fact.id) fact_ids
            FROM entity repository
            LEFT JOIN current_fact fact
              ON fact.subject_entity_id=repository.id
             AND fact.predicate IN ('DEPENDS_ON','USES','RUNS_ON','BUILT_ON','HAS_VERSION')
             AND fact.object_entity_id IN (
               SELECT id FROM entity WHERE namespace IN ('TECHNOLOGY','OSS')
             )
            WHERE repository.tenant_id=stackgraph_current_tenant_id()
              AND repository.namespace='ENTERPRISE' AND repository.entity_type='Repository'
            GROUP BY repository.id
            """
        )
        current_evidence = {
            row["repository_id"]: {str(item) for item in (row["fact_ids"] or []) if item is not None}
            for row in await current_evidence_cursor.fetchall()
        }
        evaluations: list[RepositoryCodePolicyEvaluation] = []
        for row in await evaluation_cursor.fetchall():
            details = row["details"] if isinstance(row.get("details"), dict) else {}
            evidence_changed = current_evidence.get(row["repository_entity_id"], set()) != set(
                details.get("evidence_fact_ids", [])
            )
            evaluations.append(RepositoryCodePolicyEvaluation(
                id=row["id"],
                repository=EntitySummary(
                    id=row["repository_entity_id"], kind="Repository", name=row["repository_name"],
                    canonical_key=row["repository_canonical_key"],
                    summary=(row["repository_properties"] or {}).get("purpose")
                    if isinstance(row.get("repository_properties"), dict) else None,
                ),
                status=(
                    row["status"]
                    if row["policy_set_fingerprint"] == policy_set_fingerprint and not evidence_changed
                    else "STALE"
                ),
                violations=[CodePolicyViolation(**item) for item in details.get("violations", [])],
                unclassified_technologies=[
                    EntitySummary(**item) for item in details.get("unclassified_technologies", [])
                ],
                policy_set_fingerprint=row["policy_set_fingerprint"],
                evidence_fingerprint=row["evidence_fingerprint"],
                evaluated_by=row["evaluated_by"], evaluated_at=row["evaluated_at"],
            ))
        evaluations.sort(key=lambda item: (item.repository.name.lower(), str(item.repository.id)))

        function_summaries = [
            TenantCodeFunctionSummary(
                function_key=key, name=value["name"], description=value["description"],
                domain_key=value["domain_key"], source=value["source"], status=value["status"],
                policy=(TenantCodeFunctionPolicySummary(
                    id=value["policy"]["id"],
                    allowed_technology_ids=list(value["policy"]["allowed_technology_ids"]),
                    prohibited_technology_ids=list(value["policy"]["prohibited_technology_ids"]),
                    policy_fingerprint=value["policy"]["policy_fingerprint"],
                    updated_by=value["policy"]["updated_by"],
                    updated_at=value["policy"]["updated_at"],
                ) if value.get("policy") else None),
            )
            for key, value in definitions.items()
        ]
        function_summaries.sort(key=lambda item: (
            0 if item.source == "PRIMARY" else 1, item.domain_key, item.name.lower(), item.function_key,
        ))
        return TenantCodePolicyState(
            policy_set_fingerprint=policy_set_fingerprint,
            functions=function_summaries,
            available_technologies=available_technologies,
            technology_catalog_truncated=technology_catalog_truncated,
            evaluations=evaluations,
            summary=TenantCodePolicySummary(
                governed_functions=sum(
                    1 for item in function_summaries if item.status == "ACTIVE" and item.policy is not None
                ),
                custom_functions=sum(
                    1 for item in function_summaries if item.source == "CUSTOM" and item.status == "ACTIVE"
                ),
                evaluated_repositories=sum(item.status != "STALE" for item in evaluations),
                compliant_repositories=sum(item.status == "COMPLIANT" for item in evaluations),
                misaligned_repositories=sum(item.status == "MISALIGNED" for item in evaluations),
                stale_repositories=sum(item.status == "STALE" for item in evaluations),
            ),
        )

    async def _code_policy_definitions(self, connection: Any) -> dict[str, dict[str, Any]]:
        primary_cursor = await connection.execute(
            """
            SELECT coalesce(properties->>'capability_key',replace(canonical_key,'stackgraph:capability:','')) function_key,
                   name,coalesce(properties->>'definition','') description,
                   coalesce(properties->>'domain_id','unclassified') domain_key
            FROM entity
            WHERE tenant_id IS NULL AND namespace='TECHNOLOGY' AND entity_type='Capability'
            ORDER BY domain_key,name,id
            """
        )
        definitions = {
            row["function_key"]: {
                "name": row["name"], "description": row["description"],
                "domain_key": row["domain_key"], "source": "PRIMARY", "status": "ACTIVE",
            }
            for row in await primary_cursor.fetchall()
        }
        custom_cursor = await connection.execute(
            "SELECT * FROM tenant_code_function ORDER BY domain_key,name,id"
        )
        for row in await custom_cursor.fetchall():
            definitions[row["function_key"]] = {
                "name": row["name"], "description": row["description"],
                "domain_key": row["domain_key"], "source": "CUSTOM", "status": row["status"],
            }
        policy_cursor = await connection.execute(
            "SELECT * FROM tenant_code_policy ORDER BY function_key"
        )
        for row in await policy_cursor.fetchall():
            if row["function_key"] in definitions:
                definitions[row["function_key"]]["policy"] = row
        return definitions

    @staticmethod
    def _code_policy_set_fingerprint(definitions: dict[str, dict[str, Any]]) -> str:
        active = []
        for function_key, definition in definitions.items():
            policy = definition.get("policy")
            if definition["status"] != "ACTIVE" or policy is None:
                continue
            active.append({
                "function_key": function_key,
                "source": definition["source"],
                "name": definition["name"],
                "description": definition["description"],
                "domain_key": definition["domain_key"],
                "policy_fingerprint": policy["policy_fingerprint"],
            })
        active.sort(key=lambda item: item["function_key"])
        return sha256_fingerprint({"version": "tenant-code-policy-set/v1", "functions": active})

    async def _code_policy_catalog_rows(self, connection: Any) -> list[dict[str, Any]]:
        cursor = await connection.execute(
            """
            SELECT technology.*,capability.id capability_id,
                   coalesce(capability.properties->>'capability_key',replace(capability.canonical_key,'stackgraph:capability:','')) capability_key,
                   capability.name capability_name,
                   capability.properties->>'definition' capability_summary,
                   provides.id classification_fact_id,
                   provides.confidence classification_confidence
            FROM entity technology
            LEFT JOIN fact_assertion provides
              ON provides.subject_entity_id=technology.id
             AND provides.predicate='PROVIDES' AND provides.system_to IS NULL
            LEFT JOIN entity capability
              ON capability.id=provides.object_entity_id AND capability.entity_type='Capability'
            WHERE technology.tenant_id IS NULL
              AND technology.namespace='TECHNOLOGY' AND technology.entity_type='Technology'
              AND technology.properties ? 'domain_id'
            ORDER BY technology.name,capability.name,technology.id,capability.id
            """
        )
        return list(await cursor.fetchall())

    async def _code_policy_available_technologies(self, connection: Any) -> list[dict[str, Any]]:
        cursor = await connection.execute(
            """
            WITH governed AS (
              SELECT DISTINCT unnest(allowed_technology_ids || prohibited_technology_ids) id
              FROM tenant_code_policy
            ), detected AS (
              SELECT technology.id,count(DISTINCT repository.id)::integer detected_repository_count
              FROM entity repository
              JOIN current_fact fact
                ON fact.subject_entity_id=repository.id
               AND fact.predicate IN ('DEPENDS_ON','USES','RUNS_ON','BUILT_ON','HAS_VERSION')
              JOIN entity technology ON technology.id=fact.object_entity_id
              WHERE repository.tenant_id=stackgraph_current_tenant_id()
                AND repository.namespace='ENTERPRISE' AND repository.entity_type='Repository'
                AND technology.namespace IN ('TECHNOLOGY','OSS')
              GROUP BY technology.id
            )
            SELECT entity.*,coalesce(detected.detected_repository_count,0) detected_repository_count
            FROM entity
            LEFT JOIN detected ON detected.id=entity.id
            LEFT JOIN governed ON governed.id=entity.id
            WHERE governed.id IS NOT NULL OR detected.id IS NOT NULL OR (
              entity.tenant_id IS NULL AND entity.namespace='TECHNOLOGY'
              AND entity.entity_type='Technology' AND entity.properties ? 'domain_id'
            )
            ORDER BY (governed.id IS NOT NULL) DESC,
                     coalesce(detected.detected_repository_count,0) DESC,entity.name,entity.id
            LIMIT 2001
            """
        )
        return list(await cursor.fetchall())

    @staticmethod
    def _code_policy_entity_summary(row: dict[str, Any]) -> EntitySummary:
        properties = row.get("properties") if isinstance(row.get("properties"), dict) else {}
        summary = properties.get("purpose") or properties.get("summary")
        return EntitySummary(
            id=row["id"], kind=row["entity_type"], name=row["name"],
            canonical_key=row.get("canonical_key"),
            summary=str(summary) if isinstance(summary, str) and summary.strip() else None,
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
            async with httpx.AsyncClient(timeout=30.0) as client:
                if provider == "openrouter":
                    authentication = await client.get(
                        f"{self._ai_provider_base_url(provider)}/auth/key", headers=headers,
                    )
                    authentication.raise_for_status()
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                payload = response.json()
                if provider == "openrouter":
                    endpoints = await client.get(
                        f"{self._ai_provider_base_url(provider)}/endpoints/zdr", headers=headers,
                    )
                    endpoints.raise_for_status()
                    openrouter_zdr_endpoints = endpoints.json()
                available_models = self._ai_model_ids(payload)
                models = available_models[:100]
                if available_models and row["model"] not in available_models:
                    message = f"The selected model {row['model']!r} is not available to this provider key."
                    await self._record_ai_connection_test(
                        tenant_id=tenant_id, actor_key=actor_key, status="FAILED", error=message,
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
                    await self._record_ai_connection_test(
                        tenant_id=tenant_id, actor_key=actor_key, status="FAILED", error=message,
                    )
                    raise APIError(422, "AI_MODEL_INCOMPATIBLE", message)

                adapter = self._ai_provider_adapter(provider, api_key, client)
                probe = await adapter.complete(ModelRequest(
                    model=row["model"],
                    messages=(
                        ModelMessage(
                            role="system",
                            content="Return only the requested structured result.",
                        ),
                        ModelMessage(role="user", content="Set answer to ok."),
                    ),
                    max_output_tokens=64,
                    output_schema=_AI_CONNECTION_OUTPUT_SCHEMA,
                    output_schema_name="stackgraph_connection_test",
                ))
                if probe.structured_output != {"answer": "ok"}:
                    raise ProviderResponseError(
                        f"{provider} did not satisfy the structured-output probe"
                    )
        except APIError:
            raise
        except (ProviderRequestError, ProviderResponseError) as error:
            message = (
                "Provider authentication and model discovery succeeded, but the selected model "
                "failed StackGraph's structured-output probe."
            )
            await self._record_ai_connection_test(
                tenant_id=tenant_id, actor_key=actor_key, status="FAILED", error=message,
            )
            raise APIError(422, "AI_STRUCTURED_OUTPUT_FAILED", message) from error
        except (httpx.HTTPError, ValueError, TypeError) as error:
            message = "Provider authentication or model discovery failed."
            await self._record_ai_connection_test(
                tenant_id=tenant_id, actor_key=actor_key, status="FAILED", error=message,
            )
            raise APIError(502, "AI_CONNECTION_FAILED", message) from error
        await self._record_ai_connection_test(
            tenant_id=tenant_id, actor_key=actor_key, status="SUCCEEDED", error=None,
        )
        return AIProviderConnectionTest(provider=provider, models=models)

    async def _record_ai_connection_test(
        self,
        *,
        tenant_id: UUID,
        actor_key: str,
        status: str,
        error: str | None,
    ) -> None:
        await self.database.fetch_one(
            """
            UPDATE tenant_ai_configuration SET test_status=%s,tested_at=now(),
              last_error=%s,updated_by=%s,updated_at=now() RETURNING tenant_id
            """,
            (status, error, actor_key), tenant_id=tenant_id,
        )

    @staticmethod
    def _ai_provider_adapter(
        provider: str, api_key: str, client: httpx.AsyncClient,
    ) -> AnthropicAdapter | OpenAIAdapter | OpenRouterAdapter:
        if provider == "anthropic":
            return AnthropicAdapter(
                api_key,
                base_url=AdminReadModelsMixin._ai_provider_base_url(provider),
                client=client,
            )
        if provider == "openai":
            return OpenAIAdapter(
                api_key,
                base_url=AdminReadModelsMixin._ai_provider_base_url(provider),
                client=client,
            )
        if provider == "openrouter":
            return OpenRouterAdapter(
                api_key,
                base_url=AdminReadModelsMixin._ai_provider_base_url(provider),
                site_url=os.getenv("OPENROUTER_SITE_URL"),
                site_name=os.getenv("OPENROUTER_SITE_NAME", "StackGraph"),
                client=client,
            )
        raise ValueError(f"Unsupported AI provider: {provider}")

    @staticmethod
    def _ai_models_request(provider: str, api_key: str) -> tuple[str, dict[str, str]]:
        if provider == "anthropic":
            return (
                f"{AdminReadModelsMixin._ai_provider_base_url(provider)}/models",
                {"x-api-key": api_key, "anthropic-version": "2023-06-01"},
            )
        base = AdminReadModelsMixin._ai_provider_base_url(provider)
        return f"{base}/models", {"Authorization": f"Bearer {api_key}"}

    @staticmethod
    def _ai_provider_base_url(provider: str) -> str:
        defaults = {
            "anthropic": "https://api.anthropic.com/v1",
            "openai": "https://api.openai.com/v1",
            "openrouter": "https://openrouter.ai/api/v1",
        }
        environment_names = {
            "anthropic": "ANTHROPIC_BASE_URL",
            "openai": "OPENAI_BASE_URL",
            "openrouter": "OPENROUTER_BASE_URL",
        }
        if provider not in defaults:
            raise ValueError(f"Unsupported AI provider: {provider}")
        return os.getenv(environment_names[provider], defaults[provider]).rstrip("/")

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

    async def request_graph_analysis(
        self,request: GraphAnalysisRequestCreate,*,tenant_id: UUID | None,actor_key: str,
    ) -> tuple[GraphAnalysisRequestResult,bool]:
        if tenant_id is None:
            raise APIError(400,"TENANT_REQUIRED","A tenant ID is required to request graph analysis.")
        async with self.database.session(tenant_id) as connection:
            cursor = await connection.execute(
                """
                SELECT policy.id,policy.policy_key,deployment.desired_outbox_id,
                       deployment.projected_outbox_id
                FROM graph_analysis_policy policy
                JOIN tenant_graph_deployment deployment ON deployment.tenant_id=%s
                WHERE policy.status='ACTIVE' AND policy.policy_key=%s
                  AND (policy.tenant_id IS NULL OR policy.tenant_id=%s)
                ORDER BY (policy.tenant_id IS NOT NULL) DESC,policy.version DESC LIMIT 1
                """,
                (tenant_id,request.policy_key,tenant_id),
            )
            policy = await cursor.fetchone()
            if policy is None:
                raise APIError(
                    404,"GRAPH_POLICY_NOT_FOUND",
                    "No active graph-analysis policy or deployment was found for this key.",
                )
            watermark=int(policy["desired_outbox_id"] or 0)
            status=(
                "PENDING" if int(policy["projected_outbox_id"] or 0)>=watermark
                else "WAITING_FOR_PROJECTION"
            )
            cursor = await connection.execute(
                """
                INSERT INTO graph_analysis_request(
                  tenant_id,policy_id,policy_key,requested_change_watermark,reason,status
                ) VALUES (%s,%s,%s,%s,%s,%s)
                ON CONFLICT(tenant_id,policy_id)
                  WHERE status IN ('PENDING','WAITING_FOR_PROJECTION')
                DO UPDATE SET requested_change_watermark=greatest(
                    graph_analysis_request.requested_change_watermark,
                    EXCLUDED.requested_change_watermark
                  ),reason=EXCLUDED.reason,status=EXCLUDED.status,available_at=now(),
                  last_error=NULL,updated_at=now()
                RETURNING *,xmax=0 created
                """,
                (tenant_id,policy["id"],policy["policy_key"],watermark,request.reason,status),
            )
            row = await cursor.fetchone()
            assert row is not None
            await self._write_admin_audit(
                connection,tenant_id=tenant_id,actor_key=actor_key,
                action="graph_analysis.request",target_kind="graph_analysis_request",
                target_id=row["id"],detail={
                    "policy_key":row["policy_key"],"watermark":row["requested_change_watermark"],
                    "coalesced":not bool(row["created"]),
                },
            )
        return GraphAnalysisRequestResult(
            id=row["id"],policy_key=row["policy_key"],
            requested_change_watermark=row["requested_change_watermark"],
            status=row["status"],created_at=row["created_at"],
        ),bool(row["created"])

    async def request_embedding_backfill(
        self,request: EmbeddingBackfillRequest,*,tenant_id: UUID | None,actor_key: str,
    ) -> EmbeddingBackfillResult:
        if tenant_id is None:
            raise APIError(400,"TENANT_REQUIRED","A tenant ID is required to request an embedding backfill.")
        async with self.database.session(tenant_id) as connection:
            cursor = await connection.execute(
                """
                SELECT space.* FROM embedding_space space
                WHERE space.tenant_id=%s AND space.space_kind='SEMANTIC_ENTITY'
                  AND space.lifecycle_state IN ('SHADOW','ACTIVE')
                  AND space.id=coalesce(%s::uuid,(
                    SELECT embedding_space_id FROM active_embedding_space
                    WHERE tenant_id=%s AND space_kind='SEMANTIC_ENTITY'
                  ))
                """,
                (tenant_id,request.embedding_space_id,tenant_id),
            )
            space = await cursor.fetchone()
            if space is None:
                raise APIError(
                    404,"EMBEDDING_SPACE_NOT_FOUND",
                    "No eligible semantic embedding space was found for this backfill.",
                )
            cursor = await connection.execute(
                """
                WITH selected AS (
                  SELECT entity.* FROM entity
                  WHERE (entity.tenant_id=%s OR entity.tenant_id IS NULL)
                    AND (cardinality(%s::uuid[])=0 OR entity.id=ANY(%s::uuid[]))
                    AND (cardinality(%s::text[])=0 OR entity.entity_type=ANY(%s::text[]))
                  ORDER BY entity.updated_at,entity.id LIMIT %s
                )
                INSERT INTO embedding_job(tenant_id,embedding_space_id,subject_id,input_hash)
                SELECT %s,%s,selected.id,
                  'sha256:'||encode(digest(concat_ws(E'\n',selected.entity_type,selected.name,
                    selected.canonical_key,selected.properties::text,%s),'sha256'),'hex')
                FROM selected
                ON CONFLICT DO NOTHING RETURNING id
                """,
                (
                    tenant_id,request.entity_ids,request.entity_ids,
                    request.entity_types,request.entity_types,request.limit,
                    tenant_id,space["id"],space["template_version"],
                ),
            )
            queued=len(await cursor.fetchall())
            await self._write_admin_audit(
                connection,tenant_id=tenant_id,actor_key=actor_key,
                action="embedding.backfill",target_kind="embedding_space",
                target_id=space["id"],detail={"queued_jobs":queued,"limit":request.limit},
            )
        return EmbeddingBackfillResult(
            embedding_space_id=space["id"],queued_jobs=queued,requested_at=datetime.now(UTC),
        )

    async def promote_embedding_space(
        self,space_id: UUID,request: EmbeddingSpacePromotionRequest,
        *,tenant_id: UUID | None,actor_key: str,
    ) -> EmbeddingSpacePromotionResult:
        if tenant_id is None:
            raise APIError(400,"TENANT_REQUIRED","A tenant ID is required to promote an embedding space.")
        async with self.database.session(tenant_id) as connection:
            cursor = await connection.execute(
                """
                SELECT * FROM embedding_space WHERE id=%s AND tenant_id=%s FOR UPDATE
                """,
                (space_id,tenant_id),
            )
            space = await cursor.fetchone()
            if space is None:
                raise APIError(404,"EMBEDDING_SPACE_NOT_FOUND","The embedding space was not found.")
            failed_gates=[]
            if float(space["coverage_ratio"])<0.95:
                failed_gates.append("coverage_ratio>=0.95")
            if (space.get("evaluation") or {}).get("passed") is not True:
                failed_gates.append("evaluation.passed")
            if failed_gates:
                raise APIError(
                    409,"EMBEDDING_PROMOTION_GATES_FAILED",
                    "The embedding space cannot be activated until every promotion gate passes.",
                    {"failed_gates":failed_gates,"coverage_ratio":space["coverage_ratio"]},
                )
            await connection.execute(
                """
                INSERT INTO active_embedding_space(
                  tenant_id,space_kind,embedding_space_id,activated_by
                ) VALUES (%s,%s,%s,%s)
                ON CONFLICT(tenant_id,space_kind) DO UPDATE SET
                  embedding_space_id=EXCLUDED.embedding_space_id,activated_at=now(),
                  activated_by=EXCLUDED.activated_by
                """,
                (tenant_id,space["space_kind"],space_id,actor_key),
            )
            await self._write_admin_audit(
                connection,tenant_id=tenant_id,actor_key=actor_key,
                action=f"embedding_space.{request.action.lower()}",
                target_kind="embedding_space",target_id=space_id,
                detail={"space_kind":space["space_kind"],"coverage_ratio":space["coverage_ratio"]},
            )
        return EmbeddingSpacePromotionResult(
            embedding_space_id=space_id,space_kind=space["space_kind"],
            action=request.action,activated_at=datetime.now(UTC),
        )

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
            WITH intelligence_scope AS (
              SELECT coalesce(
                max(tenant_ai_configuration_fingerprint(
                  provider,model,credential_secret_id
                )) FILTER (
                  WHERE enabled AND model<>'' AND credential_secret_id IS NOT NULL
                ),
                'snapshot-v1'
              ) fingerprint
              FROM tenant_ai_configuration
              WHERE tenant_id=%s
            )
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
              (SELECT count(*) FROM graph_projection_delivery
               WHERE tenant_id=%s AND status='PENDING') projection_pending,
              (SELECT count(*) FROM graph_projection_delivery
               WHERE tenant_id=%s AND status='PROCESSING') projection_running,
              (SELECT count(*) FROM graph_projection_delivery
               WHERE tenant_id=%s AND status='DEAD_LETTER') projection_failed,
              (SELECT max(coalesce(processed_at,created_at)) FROM graph_projection_delivery
               WHERE tenant_id=%s) projection_last,
              (SELECT count(*) FROM intelligence_job job, intelligence_scope scope
               WHERE job.tenant_id=%s AND job.configuration_fingerprint=scope.fingerprint
                 AND job.status='PENDING') intelligence_pending,
              (SELECT count(*) FROM intelligence_job job, intelligence_scope scope
               WHERE job.tenant_id=%s AND job.configuration_fingerprint=scope.fingerprint
                 AND job.status='RUNNING') intelligence_running,
              (SELECT count(*) FROM intelligence_job failed, intelligence_scope scope
               WHERE failed.tenant_id=%s
                 AND failed.configuration_fingerprint=scope.fingerprint
                 AND failed.status='FAILED'
                 AND NOT EXISTS (
                   SELECT 1 FROM intelligence_job recovered
                   WHERE recovered.tenant_id=failed.tenant_id
                     AND recovered.repository_entity_id=failed.repository_entity_id
                     AND recovered.configuration_fingerprint=failed.configuration_fingerprint
                     AND recovered.status='SUCCEEDED'
                     AND recovered.completed_at>failed.updated_at
                 )) intelligence_failed,
              (SELECT max(coalesce(job.completed_at,job.started_at,job.created_at))
               FROM intelligence_job job, intelligence_scope scope
               WHERE job.tenant_id=%s
                 AND job.configuration_fingerprint=scope.fingerprint) intelligence_last,
              (SELECT count(*) FROM graph_analysis_request
               WHERE tenant_id=%s AND status IN ('PENDING','WAITING_FOR_PROJECTION')) graph_intelligence_pending,
              (SELECT count(*) FROM graph_analysis_request
               WHERE tenant_id=%s AND status='RUNNING') graph_intelligence_running,
              (SELECT count(*) FROM graph_analysis_request failed
               WHERE failed.tenant_id=%s AND failed.status='FAILED'
                 AND NOT EXISTS (
                   SELECT 1 FROM graph_analysis_request recovered
                   WHERE recovered.tenant_id=failed.tenant_id
                     AND recovered.policy_id=failed.policy_id
                     AND recovered.status='SUCCEEDED'
                     AND recovered.completed_at>failed.completed_at
                 )) graph_intelligence_failed,
              (SELECT max(coalesce(completed_at,started_at,created_at))
               FROM graph_analysis_request WHERE tenant_id=%s) graph_intelligence_last,
              (SELECT count(*) FROM embedding_job
               WHERE tenant_id=%s AND status IN ('PENDING','RETRY_WAIT')) embeddings_pending,
              (SELECT count(*) FROM embedding_job
               WHERE tenant_id=%s AND status='RUNNING') embeddings_running,
              (SELECT count(*) FROM embedding_job
               WHERE tenant_id=%s AND status='DEAD_LETTER') embeddings_failed,
              (SELECT max(coalesce(completed_at,started_at,created_at))
               FROM embedding_job WHERE tenant_id=%s) embeddings_last,
              (SELECT count(*) FROM simulation_run
               WHERE tenant_id=%s AND status='QUEUED') simulation_pending,
              (SELECT count(*) FROM simulation_run
               WHERE tenant_id=%s AND status='RUNNING') simulation_running,
              (SELECT count(*) FROM simulation_run
               WHERE tenant_id=%s AND status='FAILED') simulation_failed,
              (SELECT max(coalesce(completed_at,started_at,created_at))
               FROM simulation_run WHERE tenant_id=%s) simulation_last,
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
            tuple([tenant_id] * 37),
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
            idle_detail: str = "Worker is online and the durable queue is clear.",
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
                detail = idle_detail
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
                key="database", name="PostgreSQL", category="CORE", state="RUNNING",
                detail="Authoritative operational state is reachable.", management_scope="Docker / deployment platform",
                last_activity_at=now, last_heartbeat_at=now,
            ),
            service(
                "mcp", "MCP server", "CORE",
                controllable=True, management_scope="This workspace",
                idle_detail="MCP endpoint is online; agent tool calls are proxied to the API.",
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
                "graph-intelligence", "Graph intelligence", "GRAPH",
                pending=int(workload.get("graph_intelligence_pending") or 0),
                running=int(workload.get("graph_intelligence_running") or 0),
                failed=int(workload.get("graph_intelligence_failed") or 0),
                last_activity_at=workload.get("graph_intelligence_last"),
                controllable=True,management_scope="This workspace",
            ),
            service(
                "embeddings", "Semantic embeddings", "INTELLIGENCE",
                pending=int(workload.get("embeddings_pending") or 0),
                running=int(workload.get("embeddings_running") or 0),
                failed=int(workload.get("embeddings_failed") or 0),
                last_activity_at=workload.get("embeddings_last"),
                controllable=True,management_scope="This workspace",
            ),
            service(
                "intelligence", "Modernization intelligence", "INTELLIGENCE",
                pending=int(workload.get("intelligence_pending") or 0),
                running=int(workload.get("intelligence_running") or 0),
                failed=int(workload.get("intelligence_failed") or 0),
                last_activity_at=workload.get("intelligence_last"),
                controllable=True, management_scope="This workspace",
            ),
            service(
                "change-simulator", "Change simulator", "INTELLIGENCE",
                pending=int(workload.get("simulation_pending") or 0),
                running=int(workload.get("simulation_running") or 0),
                failed=int(workload.get("simulation_failed") or 0),
                last_activity_at=workload.get("simulation_last"),
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
