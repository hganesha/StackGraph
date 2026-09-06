from __future__ import annotations

import hashlib
import asyncio
import json
import re
import socket
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4, uuid5

from psycopg.types.json import Jsonb

from app.errors import APIError
from app.impact_traversal import (
    ImpactPolicyConfiguration,
    ImpactTraversal,
    TraversedNode,
    eligibility,
)
from app.models import (
    ActionSubject,
    ActionSubjectCapability,
    ActionSubjectList,
    ActionTypeList,
    ActionTypeSummary,
    ChangeGate,
    ChangeScope,
    ChangeSetCompileRequest,
    ChangeScopeList,
    ChangeSetModel,
    EntityResolution,
    EntitySummary,
    GateReason,
    MutationCompileRequest,
    MutationCompileResult,
    MutationIR,
    RecommendationCompileRequest,
    RepositoryFingerprintList,
    RepositoryFingerprintSnapshot,
    MutationValidateRequest,
    MutationValidationError,
    ObservedMutationCreateRequest,
    ObservedMutationList,
    ObservedMutationModel,
    PageInfo,
    ResolutionCandidate,
    SimulationCreateRequest,
    SimulationFinding,
    QuarantinedClaim,
    SimulationInterpretation,
    SimulationRunModel,
    TargetCoverage,
    ValidTarget,
    ValidTargetList,
    VersionDistribution,
)


ONTOLOGY_VERSION = "actions/1.0.0"
RESOLUTION_VERSION = "identity-resolution/1.0.0"
PROVIDER_VERSION = "package-registry/1.0.0"
POLICY_KEY = "upgrade-package"
_SIMULATION_NAMESPACE = UUID("fd4ecf06-230c-4d15-a65a-04a967c6487f")
# Findings are ordered most-actionable first so a truncated read still shows what matters.
_CLASSIFICATION_ORDER = ("DIRECT", "TRANSITIVE", "CONTEXT", "STOP", "INFORMATIONAL")
_IMPACT_SEVERITY = {"DIRECT": "MEDIUM", "TRANSITIVE": "MEDIUM", "CONTEXT": "LOW"}
# An interpretation outage must not hold a completed deterministic result hostage.
_INTERPRETATION_TIMEOUT_SECONDS = 30
# Registries and assessments spell end-of-life several ways; the contract has one word for it.
_SUPPORT_STATUS = {
    "SUPPORTED": "SUPPORTED", "ACTIVE": "SUPPORTED", "CURRENT": "SUPPORTED",
    "UNSUPPORTED": "UNSUPPORTED", "DEPRECATED": "UNSUPPORTED",
    "END_OF_LIFE": "END_OF_LIFE", "EOL": "END_OF_LIFE",
}
_INTENT = re.compile(
    r"^\s*upgrade\s+(?P<subject>.+?)\s+to\s+(?P<target>[^\s]+)(?:\s+(?:in|within)\s+(?P<scope>.+))?\s*$",
    re.IGNORECASE,
)


def _fingerprint(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return "sha256:" + hashlib.sha256(payload.encode()).hexdigest()


# purl type as the scanner mints it, mapped to the catalogue's ecosystem column. They differ in
# exactly one place — the purl type is `golang` and the catalogue calls it `go` — and conflating
# them would silently return an empty catalogue for every Go module.
_PURL_ECOSYSTEMS = {
    "npm": "npm", "pypi": "pypi", "maven": "maven", "cargo": "cargo", "nuget": "nuget",
    "golang": "go",
}


def _purl_ecosystem(canonical_key: str) -> tuple[str, str]:
    """Read the purl type out of a package entity's canonical key.

    An unrecognised type falls back to `npm` because that is where the estate's packages have
    always come from, and a mismatched prefix returns an empty catalogue rather than another
    ecosystem's releases.
    """
    if canonical_key.startswith("pkg:"):
        purl_type = canonical_key[4:].split("/", 1)[0]
        if purl_type in _PURL_ECOSYSTEMS:
            return purl_type, _PURL_ECOSYSTEMS[purl_type]
    return "npm", "npm"


def _entity(row: dict[str, Any]) -> EntitySummary:
    return EntitySummary(
        id=row["id"], kind=row["entity_type"], name=row["name"],
        canonical_key=row.get("canonical_key"),
    )


def _version_key(value: str) -> tuple[tuple[int, Any], ...]:
    return tuple(
        (0, int(part)) if part.isdigit() else (1, part.lower())
        for part in re.split(r"[.+\-_]", value)
    )


def _freshness(value: datetime | None) -> str:
    if value is None:
        return "UNKNOWN"
    return "FRESH" if value >= datetime.now(UTC) - timedelta(days=30) else "STALE"


def _impact_quantity(value: Any) -> int:
    """Count numeric impact leaves without treating booleans as quantities."""
    if isinstance(value, bool) or value is None:
        return 0
    if isinstance(value, (int, float)):
        return max(0, int(value))
    if isinstance(value, dict):
        return sum(_impact_quantity(item) for item in value.values())
    if isinstance(value, list):
        return sum(_impact_quantity(item) for item in value)
    return 0


def _clear_gate() -> ChangeGate:
    return ChangeGate(state="CLEAR", reasons=[])


@dataclass
class MutationDraft:
    """One compiled-but-unpersisted mutation and everything the gate decided about it."""

    mutation: MutationIR
    predicate: str
    resolution: Any
    target: ValidTarget | None
    scope: ChangeScope | None
    errors: list[MutationValidationError]
    reasons: list[GateReason]
    fingerprint: str


def _change_set_conflicts(drafts: list["MutationDraft"]) -> list[GateReason]:
    """Reject a ChangeSet whose mutations disagree with each other.

    C2 requires conflict detection, and the cases that matter are the ones a per-mutation gate
    cannot see: two mutations moving the same subject in the same scope to different targets,
    and the same mutation listed twice. Either would make the set's stated effect depend on the
    order it happened to be applied in.
    """
    reasons: list[GateReason] = []
    by_subject: dict[tuple[str, str], set[str]] = {}
    seen_fingerprints: set[str] = set()
    duplicated = False
    for draft in drafts:
        if draft.fingerprint in seen_fingerprints:
            duplicated = True
        seen_fingerprints.add(draft.fingerprint)
        if draft.resolution.entity is None or draft.scope is None or draft.target is None:
            continue
        key = (str(draft.resolution.entity.id), draft.scope.id)
        by_subject.setdefault(key, set()).add(draft.target.version)
    if duplicated:
        reasons.append(GateReason(
            code="DUPLICATE_MUTATION",
            message="The ChangeSet lists the same mutation more than once.",
        ))
    conflicting = sorted(key for key, versions in by_subject.items() if len(versions) > 1)
    if conflicting:
        reasons.append(GateReason(
            code="CONFLICTING_MUTATIONS",
            message=(
                "Two mutations move the same subject in the same scope to different targets, so "
                "the ChangeSet's effect would depend on application order."
            ),
        ))
    return reasons


class Phase2ChangeMixin:
    """Tenant-safe compiler and deterministic simulation read/write model.

    Natural language is accepted only by the bounded lexical parser above. The
    simulator consumes persisted Mutation IR, never the original command text.
    """

    database: Any
    # Set by the composing store when a provider is configured. Left None everywhere else so
    # the interpretation partition degrades explicitly instead of raising.
    ai: Any = None

    async def phase2_feature_enabled(
        self, flag_key: str, *, tenant_id: UUID | None,
    ) -> bool:
        row = await self.database.fetch_one(
            """
            SELECT enabled FROM phase2_feature_flag
            WHERE flag_key=%s AND (tenant_id IS NULL OR tenant_id=%s)
            ORDER BY (tenant_id IS NOT NULL) DESC LIMIT 1
            """,
            (flag_key, tenant_id), tenant_id=tenant_id,
        )
        return bool(row and row["enabled"])

    async def _audit_change(
        self, *, tenant_id: UUID, actor_key: str, action: str,
        target_kind: str, target_id: str, detail: dict[str, Any],
    ) -> None:
        async with self.database.session(tenant_id) as connection:
            await connection.execute(
                """
                INSERT INTO admin_audit_log(
                  tenant_id,actor_key,action,target_kind,target_id,detail
                ) VALUES (%s,%s,%s,%s,%s,%s)
                """,
                (tenant_id, actor_key, action, target_kind, target_id, Jsonb(detail)),
            )

    async def action_types(self, *, tenant_id: UUID | None) -> ActionTypeList:
        rows = await self.database.fetch_all(
            """
            SELECT predicate,subject_type,ontology_version,lifecycle
            FROM action_capability
            WHERE lifecycle IN ('ACTIVE','DISABLED')
            ORDER BY predicate,subject_type
            """,
            tenant_id=tenant_id,
        )
        grouped: dict[str, dict[str, Any]] = {}
        descriptions = {
            "UPGRADE": "Move an observed technology to an exact supported version.",
            "REPLACE": "Replace one canonical technology with another.",
            "REMOVE": "Remove a canonical technology from an observed scope.",
            "DEPRECATE": "Mark an API or service contract for retirement.",
            "MIGRATE": "Move data or behavior between compatible platforms.",
            "MOVE": "Change the deployment location of a service.",
        }
        for row in rows:
            item = grouped.setdefault(row["predicate"], {
                "predicate": row["predicate"], "label": row["predicate"].title(),
                "description": descriptions[row["predicate"]], "subject_types": [],
                "subjects": [], "enabled": False, "lifecycle": row["lifecycle"],
                "ontology_version": row["ontology_version"],
            })
            active = row["lifecycle"] == "ACTIVE"
            item["subject_types"].append(row["subject_type"])
            item["subjects"].append(ActionSubjectCapability(
                subject_type=row["subject_type"], lifecycle=row["lifecycle"], enabled=active,
            ))
            # Offerable when *any* subject type can compile. ANDing across subjects would mean
            # publishing the planned half of the grammar disables the half that works.
            item["enabled"] = item["enabled"] or active
            if active:
                item["lifecycle"] = "ACTIVE"
        return ActionTypeList(
            action_types=[ActionTypeSummary(**item) for item in grouped.values()],
            policy_version=ONTOLOGY_VERSION,
        )

    async def repository_fingerprints(
        self, repository_id: UUID, *, tenant_id: UUID | None, limit: int,
    ) -> RepositoryFingerprintList:
        repository = await self.database.fetch_one(
            """
            SELECT id,entity_type,name,canonical_key FROM entity
            WHERE id=%s AND entity_type='Repository'
            """,
            (repository_id,), tenant_id=tenant_id,
        )
        if repository is None:
            raise APIError(404, "REPOSITORY_NOT_FOUND", "The repository was not found.")
        rows = await self.database.fetch_all(
            """
            SELECT id fact_id,source_revision,observed_at,system_from,system_to,
                   confidence,object_value
            FROM fact_assertion
            WHERE subject_entity_id=%s AND predicate='HAS_PROPERTY'
              AND object_value->>'record_kind'='repository_fingerprint'
            ORDER BY observed_at DESC,system_from DESC,id DESC
            LIMIT %s
            """,
            (repository_id, limit + 1), tenant_id=tenant_id,
        )
        return RepositoryFingerprintList(
            repository=_entity(repository),
            snapshots=[RepositoryFingerprintSnapshot(
                fact_id=row["fact_id"], source_revision=row["source_revision"],
                observed_at=row["observed_at"], system_from=row["system_from"],
                system_to=row["system_to"], confidence=float(row["confidence"]),
                fingerprint=row["object_value"]["fingerprint"],
                profile=row["object_value"],
            ) for row in rows[:limit]],
            page_info=PageInfo(has_next_page=len(rows) > limit),
        )

    @staticmethod
    def _observed_mutation(row: dict[str, Any]) -> ObservedMutationModel:
        return ObservedMutationModel(
            id=row["id"], correlation_key=row["correlation_key"],
            source_kind=row["source_kind"], predicate=row["predicate"],
            subject=EntitySummary(
                id=row["subject_entity_id"], kind=row["entity_type"], name=row["name"],
                canonical_key=row["canonical_key"],
            ),
            before=row["before_state"], after=row["after_state"], scope=row["scope"],
            observed_impact=row["observed_impact"], unexpected_impact=row["unexpected_impact"],
            success=row["success"], intervention_required=row["intervention_required"],
            rolled_back=row["rolled_back"], evidence_fact_ids=row["evidence_fact_ids"],
            graph_watermark_before=row["graph_watermark_before"],
            predicted_simulation_run_id=row["predicted_simulation_run_id"],
            predicted_finding_count=row.get("predicted_finding_count"),
            observed_impact_count=_impact_quantity(row["observed_impact"]),
            unexpected_impact_count=_impact_quantity(row["unexpected_impact"]),
            resolution=row["resolution"], confidence=float(row["confidence"]),
            input_fingerprint=row["input_fingerprint"], observed_at=row["observed_at"],
            created_at=row["created_at"],
        )

    async def record_observed_mutation(
        self, request: ObservedMutationCreateRequest, *, tenant_id: UUID | None, actor_key: str,
    ) -> ObservedMutationModel:
        if tenant_id is None:
            raise APIError(400, "TENANT_REQUIRED", "A tenant is required to record a change outcome.")
        evidence = await self.database.fetch_one(
            """
            SELECT count(*) matched FROM fact_assertion
            WHERE tenant_id=%s AND id=ANY(%s::uuid[])
            """,
            (tenant_id, request.evidence_fact_ids), tenant_id=tenant_id,
        )
        if int((evidence or {}).get("matched") or 0) != len(set(request.evidence_fact_ids)):
            raise APIError(
                422, "OUTCOME_EVIDENCE_NOT_FOUND",
                "Every observed outcome must cite facts in the active tenant.",
            )
        fingerprint = _fingerprint({
            "schema_version": "observed-mutation/1.0.0",
            "source_kind": request.source_kind, "predicate": request.predicate,
            "subject_entity_id": str(request.subject_entity_id),
            "before": request.before, "after": request.after, "scope": request.scope,
            "observed_impact": request.observed_impact,
            "unexpected_impact": request.unexpected_impact,
            "success": request.success,
            "intervention_required": request.intervention_required,
            "rolled_back": request.rolled_back,
            "evidence_fact_ids": sorted(map(str, request.evidence_fact_ids)),
            "graph_watermark_before": request.graph_watermark_before,
            "predicted_simulation_run_id": str(request.predicted_simulation_run_id)
            if request.predicted_simulation_run_id else None,
            "resolution": request.resolution, "confidence": request.confidence,
            "observed_at": request.observed_at.isoformat(),
        })
        async with self.database.session(tenant_id) as connection:
            cursor = await connection.execute(
                """
                INSERT INTO observed_mutation(
                  tenant_id,correlation_key,source_kind,predicate,subject_entity_id,
                  before_state,after_state,scope,observed_impact,unexpected_impact,
                  success,intervention_required,rolled_back,evidence_fact_ids,
                  graph_watermark_before,predicted_simulation_run_id,resolution,confidence,
                  input_fingerprint,observed_at,created_by
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT DO NOTHING RETURNING id
                """,
                (
                    tenant_id, request.correlation_key, request.source_kind, request.predicate,
                    request.subject_entity_id, Jsonb(request.before), Jsonb(request.after),
                    Jsonb(request.scope), Jsonb(request.observed_impact),
                    Jsonb(request.unexpected_impact), request.success,
                    request.intervention_required, request.rolled_back,
                    request.evidence_fact_ids, request.graph_watermark_before,
                    request.predicted_simulation_run_id, request.resolution, request.confidence,
                    fingerprint, request.observed_at, actor_key,
                ),
            )
            created = await cursor.fetchone()
            if created is None:
                cursor = await connection.execute(
                    """
                    SELECT id,input_fingerprint,correlation_key FROM observed_mutation
                    WHERE tenant_id=%s AND (correlation_key=%s OR input_fingerprint=%s)
                    ORDER BY (correlation_key=%s) DESC LIMIT 1
                    """,
                    (tenant_id, request.correlation_key, fingerprint, request.correlation_key),
                )
                existing = await cursor.fetchone()
                if existing is None or existing["input_fingerprint"] != fingerprint:
                    raise APIError(
                        409, "OUTCOME_CORRELATION_CONFLICT",
                        "The correlation key already identifies a different observed outcome.",
                    )
                outcome_id = existing["id"]
            else:
                outcome_id = created["id"]
        row = await self.database.fetch_one(
            """
            SELECT outcome.*,entity.entity_type,entity.name,entity.canonical_key,
                   predicted.finding_count predicted_finding_count
            FROM observed_mutation outcome JOIN entity ON entity.id=outcome.subject_entity_id
            LEFT JOIN LATERAL (
              SELECT count(*)::int finding_count FROM simulation_finding finding
              WHERE finding.simulation_run_id=outcome.predicted_simulation_run_id
            ) predicted ON outcome.predicted_simulation_run_id IS NOT NULL
            WHERE outcome.id=%s
            """,
            (outcome_id,), tenant_id=tenant_id,
        )
        assert row is not None
        await self._audit_change(
            tenant_id=tenant_id, actor_key=actor_key, action="observed_mutation.record",
            target_kind="observed_mutation", target_id=str(outcome_id),
            detail={"correlation_key": request.correlation_key, "predicate": request.predicate},
        )
        return self._observed_mutation(row)

    async def change_history(
        self, subject_id: UUID, *, tenant_id: UUID | None, limit: int,
    ) -> ObservedMutationList:
        subject = await self.database.fetch_one(
            "SELECT id,entity_type,name,canonical_key FROM entity WHERE id=%s",
            (subject_id,), tenant_id=tenant_id,
        )
        if subject is None:
            raise APIError(404, "ENTITY_NOT_FOUND", "The change-history subject was not found.")
        rows = await self.database.fetch_all(
            """
            SELECT outcome.*,entity.entity_type,entity.name,entity.canonical_key,
                   predicted.finding_count predicted_finding_count
            FROM observed_mutation outcome JOIN entity ON entity.id=outcome.subject_entity_id
            LEFT JOIN LATERAL (
              SELECT count(*)::int finding_count FROM simulation_finding finding
              WHERE finding.simulation_run_id=outcome.predicted_simulation_run_id
            ) predicted ON outcome.predicted_simulation_run_id IS NOT NULL
            WHERE outcome.subject_entity_id=%s
            ORDER BY outcome.observed_at DESC,outcome.id DESC LIMIT %s
            """,
            (subject_id, limit + 1), tenant_id=tenant_id,
        )
        predicates = sorted({row["predicate"] for row in rows})
        similar_rows = await self.database.fetch_all(
            """
            SELECT outcome.*,entity.entity_type,entity.name,entity.canonical_key,
                   predicted.finding_count predicted_finding_count
            FROM observed_mutation outcome JOIN entity ON entity.id=outcome.subject_entity_id
            LEFT JOIN LATERAL (
              SELECT count(*)::int finding_count FROM simulation_finding finding
              WHERE finding.simulation_run_id=outcome.predicted_simulation_run_id
            ) predicted ON outcome.predicted_simulation_run_id IS NOT NULL
            WHERE outcome.subject_entity_id<>%s AND entity.entity_type=%s
              AND outcome.predicate=ANY(%s::text[])
            ORDER BY outcome.observed_at DESC,outcome.id DESC LIMIT %s
            """,
            (subject_id, subject["entity_type"], predicates, limit), tenant_id=tenant_id,
        ) if predicates else []
        limitations = []
        if len(rows) + len(similar_rows) < 5:
            limitations.append(GateReason(
                code="CHANGE_MEMORY_SAMPLE_THIN",
                message="Fewer than five exact or comparable outcomes are available; rates remain descriptive counts.",
            ))
        if not similar_rows:
            limitations.append(GateReason(
                code="NO_COMPARABLE_CHANGES",
                message="No changes with the same subject type and predicate are recorded elsewhere in this tenant.",
            ))
        return ObservedMutationList(
            subject=_entity(subject), outcomes=[self._observed_mutation(row) for row in rows[:limit]],
            similar_outcomes=[self._observed_mutation(row) for row in similar_rows],
            limitations=limitations,
            page_info=PageInfo(has_next_page=len(rows) > limit),
        )

    async def action_subjects(
        self, predicate: str, *, tenant_id: UUID | None, query: str | None, limit: int,
    ) -> ActionSubjectList:
        if predicate != "UPGRADE":
            return ActionSubjectList(
                predicate=predicate, subjects=[], page_info=PageInfo(has_next_page=False),
            )
        pattern = f"%{query.strip()}%" if query else "%"
        rows = await self.database.fetch_all(
            """
            WITH package_groups AS (
              SELECT lower(pri.package_name) package_key,pri.package_name,
                     (array_agg(e.id ORDER BY (pri.package_version IS NULL) DESC,e.updated_at DESC,e.id))[1] id,
                     (array_agg(e.entity_type ORDER BY (pri.package_version IS NULL) DESC,e.updated_at DESC,e.id))[1] entity_type,
                     (array_agg(e.name ORDER BY (pri.package_version IS NULL) DESC,e.updated_at DESC,e.id))[1] name,
                     (array_agg(e.canonical_key ORDER BY (pri.package_version IS NULL) DESC,e.updated_at DESC,e.id))[1] canonical_key,
                     array_remove(array_agg(DISTINCT pri.package_version),NULL) versions
              FROM package_registry_identity pri
              JOIN entity e ON e.id=pri.entity_id
              WHERE pri.package_name ILIKE %s
              GROUP BY lower(pri.package_name),pri.package_name
            ), usage AS (
              SELECT lower(pri.package_name) package_key,count(DISTINCT f.subject_entity_id) dependent_count,
                     array_agg(DISTINCT f.id) evidence_fact_ids
              FROM fact_assertion f
              JOIN package_registry_identity pri ON pri.entity_id=f.object_entity_id
              WHERE f.tenant_id=%s AND f.predicate='DEPENDS_ON' AND f.system_to IS NULL
              GROUP BY lower(pri.package_name)
            )
            SELECT package_groups.*,coalesce(usage.dependent_count,0) dependent_count,
                   coalesce(usage.evidence_fact_ids,'{}') evidence_fact_ids
            FROM package_groups JOIN usage USING(package_key)
            ORDER BY dependent_count DESC,package_name LIMIT %s
            """,
            (pattern, tenant_id, limit + 1), tenant_id=tenant_id,
        )
        subjects = [ActionSubject(
            entity=_entity(row), observed_versions=sorted(row["versions"] or [], key=_version_key),
            dependent_count=row["dependent_count"], evidence_fact_ids=row["evidence_fact_ids"] or [],
        ) for row in rows[:limit]]
        return ActionSubjectList(
            predicate="UPGRADE", subjects=subjects,
            page_info=PageInfo(has_next_page=len(rows) > limit),
        )

    async def _package_resolution(
        self, *, tenant_id: UUID | None, subject_id: UUID | None, query: str | None,
    ) -> tuple[EntityResolution, str | None]:
        if subject_id is not None:
            rows = await self.database.fetch_all(
                """
                SELECT e.id,e.entity_type,e.name,e.canonical_key,pri.package_name,
                       array_agg(DISTINCT f.id) FILTER (WHERE f.id IS NOT NULL) evidence_fact_ids
                FROM entity e
                LEFT JOIN package_registry_identity pri ON pri.entity_id=e.id
                LEFT JOIN fact_assertion f ON f.object_entity_id=e.id AND f.tenant_id=%s
                  AND f.predicate='DEPENDS_ON' AND f.system_to IS NULL
                WHERE e.id=%s AND e.entity_type='Package'
                GROUP BY e.id,e.entity_type,e.name,e.canonical_key,pri.package_name
                """,
                (tenant_id, subject_id), tenant_id=tenant_id,
            )
            if rows:
                row = rows[0]
                return EntityResolution(
                    state="RESOLVED", entity=_entity(row), candidates=[], confidence=1,
                    method="CANONICAL_ID", method_version=RESOLUTION_VERSION,
                    evidence_fact_ids=row["evidence_fact_ids"] or [],
                ), row["package_name"]
        normalized = (query or "").strip()
        if not normalized:
            return EntityResolution(
                state="UNRESOLVED", confidence=0, method="EMPTY_INPUT",
                method_version=RESOLUTION_VERSION,
            ), None
        rows = await self.database.fetch_all(
            """
            WITH candidates AS (
              SELECT lower(pri.package_name) package_key,pri.package_name,
                     (array_agg(e.id ORDER BY (pri.package_version IS NULL) DESC,e.updated_at DESC,e.id))[1] id,
                     (array_agg(e.entity_type ORDER BY (pri.package_version IS NULL) DESC,e.updated_at DESC,e.id))[1] entity_type,
                     (array_agg(e.name ORDER BY (pri.package_version IS NULL) DESC,e.updated_at DESC,e.id))[1] name,
                     (array_agg(e.canonical_key ORDER BY (pri.package_version IS NULL) DESC,e.updated_at DESC,e.id))[1] canonical_key,
                     bool_or(lower(pri.package_name)=lower(%s) OR lower(e.name)=lower(%s)
                       OR lower(e.canonical_key)=lower(%s)) exact
              FROM package_registry_identity pri JOIN entity e ON e.id=pri.entity_id
              WHERE pri.package_name ILIKE %s OR e.name ILIKE %s OR e.canonical_key ILIKE %s
              GROUP BY lower(pri.package_name),pri.package_name
            )
            SELECT candidates.*,
                   array_agg(DISTINCT f.id) FILTER (WHERE f.id IS NOT NULL) evidence_fact_ids
            FROM candidates
            LEFT JOIN package_registry_identity pri ON lower(pri.package_name)=candidates.package_key
            LEFT JOIN fact_assertion f ON f.object_entity_id=pri.entity_id AND f.tenant_id=%s
              AND f.predicate='DEPENDS_ON' AND f.system_to IS NULL
            GROUP BY candidates.package_key,candidates.package_name,candidates.id,
                     candidates.entity_type,candidates.name,candidates.canonical_key,candidates.exact
            ORDER BY candidates.exact DESC,candidates.package_name LIMIT 8
            """,
            (
                normalized, normalized, normalized, f"%{normalized}%", f"%{normalized}%",
                f"%{normalized}%", tenant_id,
            ), tenant_id=tenant_id,
        )
        exact = [row for row in rows if row["exact"]]
        if len(exact) == 1:
            row = exact[0]
            return EntityResolution(
                state="RESOLVED", entity=_entity(row), candidates=[], confidence=1,
                method="EXACT_CANONICAL_IDENTIFIER", method_version=RESOLUTION_VERSION,
                evidence_fact_ids=row["evidence_fact_ids"] or [],
            ), row["package_name"]
        candidates = [ResolutionCandidate(
            entity=_entity(row), confidence=0.75 if row["exact"] else 0.55,
            method="EXACT_ALIAS" if row["exact"] else "STRUCTURAL_MATCH",
        ) for row in rows]
        return EntityResolution(
            state="INFERRED" if candidates else "UNRESOLVED", candidates=candidates,
            confidence=max((candidate.confidence for candidate in candidates), default=0),
            method="AMBIGUOUS_CANDIDATES" if candidates else "NO_MATCH",
            method_version=RESOLUTION_VERSION,
        ), None

    async def valid_targets(
        self, entity_id: UUID, *, tenant_id: UUID | None, limit: int,
    ) -> ValidTargetList:
        """Enumerate the exact versions this package may be moved to, and say why each matters.

        §6 wants more than a list of version strings: the estate's own spread, a consolidation
        target, a candidate upgrade, and an explicit statement of what the list was drawn from.
        Support status is read from the governed assessment rather than assumed, because
        "unknown support" and "supported" are different answers and only one of them is safe to
        infer from silence.
        """
        resolution, package_name = await self._package_resolution(
            tenant_id=tenant_id, subject_id=entity_id, query=None,
        )
        if resolution.state != "RESOLVED" or package_name is None or resolution.entity is None:
            raise APIError(404, "PACKAGE_NOT_RESOLVED", "The package does not have a canonical registry identity.")
        # Six ecosystems are catalogued now, and `serde` names a crate and could name an npm
        # package. Matching on the name alone would offer one ecosystem's releases as the
        # other's upgrade targets, so every query below is scoped by purl type.
        purl_type, ecosystem = _purl_ecosystem(resolution.entity.canonical_key)
        purl_prefix = f"pkg:{purl_type}/"
        rows = await self.database.fetch_all(
            """
            SELECT e.id,e.canonical_key,pri.package_version,
                   coalesce(pri.last_seen_at,pri.first_seen_at,e.updated_at) observed_at,
                   registry.registry_key,
                   upper(coalesce(
                     support.categorical_value, e.properties->>'support_status', 'UNKNOWN'
                   )) support_status
            FROM package_registry_identity pri
            JOIN package_registry registry ON registry.id=pri.package_registry_id
            JOIN entity e ON e.id=pri.entity_id
            LEFT JOIN LATERAL (
              SELECT categorical_value FROM assessment
              WHERE subject_entity_id=e.id AND status='CURRENT' AND valid_to IS NULL
                AND lower(dimension) IN ('support','support_status','lifecycle')
                AND categorical_value IS NOT NULL
              ORDER BY valid_from DESC LIMIT 1
            ) support ON true
            WHERE lower(pri.package_name)=lower(%s) AND pri.package_version IS NOT NULL
              AND pri.purl LIKE %s
            """,
            (package_name, f"{purl_prefix}%"), tenant_id=tenant_id,
        )
        # The registry's catalogue, which is a different claim from the estate's identity: it
        # says a version can be chosen, not that anything runs it. Joined here so an upgrade
        # target need not already exist somewhere in the estate.
        catalog = await self.database.fetch_all(
            """
            SELECT catalog.version, catalog.is_prerelease, catalog.is_yanked,
                   catalog.is_deprecated, catalog.published_at, catalog.collected_at,
                   catalog.registry_key, catalog.support_status
            FROM package_version_catalog catalog
            WHERE lower(catalog.package_name)=lower(%s) AND catalog.ecosystem=%s
              AND NOT catalog.is_yanked
            ORDER BY catalog.version
            """,
            (package_name, ecosystem), tenant_id=tenant_id,
        )
        collection = await self.database.fetch_one(
            """
            SELECT status, version_count, limitations, collected_at
            FROM package_catalog_collection
            WHERE lower(package_name)=lower(%s) AND ecosystem=%s
            ORDER BY collected_at DESC LIMIT 1
            """,
            (package_name, ecosystem), tenant_id=tenant_id,
        )
        known = {row["package_version"] for row in rows}
        for entry in catalog:
            if entry["version"] in known:
                continue
            # A catalogue version has no entity, because the estate does not run it. The
            # compiler resolves it to one only if the change is actually submitted.
            rows.append({
                "id": None,
                "canonical_key": f"{purl_prefix}{package_name}@{entry['version']}",
                "package_version": entry["version"], "observed_at": entry["collected_at"],
                "registry_key": entry["registry_key"],
                "support_status": (
                    "UNSUPPORTED" if entry["is_deprecated"]
                    else str(entry["support_status"] or "UNKNOWN")
                ),
                "from_catalog": True, "is_prerelease": entry["is_prerelease"],
            })
        rows.sort(key=lambda row: _version_key(row["package_version"]), reverse=True)
        observed = await self.database.fetch_all(
            """
            SELECT coalesce(dr.resolved_version,pri.package_version,
                     f.properties->>'resolved_version') version,
                   count(DISTINCT f.subject_entity_id)::int repositories
            FROM fact_assertion f
            JOIN entity consumer ON consumer.id=f.subject_entity_id
                                AND consumer.entity_type='Repository'
            JOIN package_registry_identity pri ON pri.entity_id=f.object_entity_id
            LEFT JOIN dependency_resolution dr ON dr.fact_assertion_id=f.id
            WHERE f.tenant_id=%s AND f.predicate='DEPENDS_ON' AND f.system_to IS NULL
              AND lower(pri.package_name)=lower(%s) AND pri.purl LIKE %s
            GROUP BY 1
            """,
            (tenant_id, package_name, f"{purl_prefix}%"), tenant_id=tenant_id,
        )
        counts = {
            str(row["version"]): int(row["repositories"])
            for row in observed if row["version"]
        }
        # The version the most repositories already run is the one an upgrade can converge on
        # without introducing a version nothing in the estate has exercised.
        consolidate = max(counts, key=lambda value: (counts[value], _version_key(value))) if counts else None
        candidates = [
            row["package_version"] for row in rows
            if row["support_status"] not in {"UNSUPPORTED", "END_OF_LIFE", "EOL"}
            # A prerelease is not the latest thing to upgrade *to*. Offering one as the headline
            # target would push an estate onto a release its own publisher has not finished.
            and not row.get("is_prerelease")
        ]
        latest = candidates[0] if candidates else None

        targets: list[ValidTarget] = []
        for row in rows[:limit]:
            version = row["package_version"]
            support = _SUPPORT_STATUS.get(row["support_status"], "UNKNOWN")
            from_catalog = bool(row.get("from_catalog"))
            if version == consolidate:
                recommendation = "CONSOLIDATE"
                detail = (
                    f"{counts[version]} repositories already run this version, so converging "
                    "here introduces no version the estate has not exercised."
                )
            elif version == latest:
                recommendation = "LATEST_KNOWN"
                detail = (
                    "The highest release the registry currently offers."
                    if from_catalog else
                    "The highest version StackGraph has collected for this package."
                )
            elif counts and version not in counts:
                recommendation = "CANDIDATE"
                detail = (
                    "The registry offers this release; no repository runs it yet."
                    if from_catalog else "No repository runs this version yet."
                )
            else:
                recommendation = "NONE"
                detail = None
            targets.append(ValidTarget(
                entity_id=row["id"], version=version, canonical_key=row["canonical_key"],
                source=row["registry_key"], observed_at=row["observed_at"],
                freshness=_freshness(row["observed_at"]), support=support,
                recommendation=recommendation, recommendation_detail=detail,
                observed_repository_count=counts.get(version, 0),
                origin="REGISTRY_CATALOG" if from_catalog else "ESTATE",
                is_prerelease=bool(row.get("is_prerelease")),
            ))

        # Being explicit about where the list came from is the difference between "there are no
        # newer versions" and "no newer version has been collected". A collection record is the
        # only thing that distinguishes them, so it is read rather than inferred from the shape
        # of the result.
        enumerated = collection is not None and collection["status"] in {"AVAILABLE", "PARTIAL"}
        estate_only = not any(target.origin == "REGISTRY_CATALOG" for target in targets)
        coverage = TargetCoverage(
            source=(
                "ESTATE_OBSERVED" if not enumerated
                else "MIXED" if counts and not estate_only
                else "REGISTRY_ENUMERATED"
            ),
            registry_enumeration="AVAILABLE" if enumerated else "NOT_COLLECTED",
            detail=(
                (
                    f"The registry catalogue was collected "
                    f"{_freshness(collection['collected_at']).lower()} and offers "
                    f"{collection['version_count']} versions."
                )
                if enumerated else
                "Every target is a version the estate already runs. A newer release may exist "
                "that registry enumeration has not collected."
            ),
        )
        limitations = []
        if not targets:
            limitations.append(GateReason(
                code="TARGET_PROVIDER_EMPTY",
                message="No immutable versions are available from the configured package registries.",
            ))
        elif all(target.freshness == "STALE" for target in targets):
            limitations.append(GateReason(
                code="TARGET_PROVIDER_STALE",
                message="Target metadata is older than the active freshness policy.",
            ))
        if targets and not enumerated:
            limitations.append(GateReason(
                code="TARGET_PROVIDER_ESTATE_ONLY",
                message=(
                    "Targets are limited to versions already observed in the estate; a newer "
                    "release may exist that has not been collected."
                ),
            ))
        for item in collection["limitations"] if collection else []:
            limitations.append(GateReason(code="TARGET_CATALOG_BOUNDED", message=str(item)))
        return ValidTargetList(
            subject=resolution.entity, targets=targets, policy_version=PROVIDER_VERSION,
            page_info=PageInfo(has_next_page=len(rows) > limit), coverage=coverage,
            limitations=limitations,
        )

    async def scopes(self, entity_id: UUID, *, tenant_id: UUID | None) -> ChangeScopeList:
        resolution, package_name = await self._package_resolution(
            tenant_id=tenant_id, subject_id=entity_id, query=None,
        )
        if resolution.state != "RESOLVED" or package_name is None or resolution.entity is None:
            raise APIError(404, "PACKAGE_NOT_RESOLVED", "The package does not have a canonical registry identity.")
        rows = await self.database.fetch_all(
            """
            SELECT f.id fact_id,consumer.id,consumer.entity_type,consumer.name,consumer.canonical_key,
                   coalesce(f.properties->>'component_path','') component_path,
                   coalesce(dr.resolved_version,pri.package_version,f.properties->>'resolved_version',
                     f.properties->>'requested_spec','unknown') version
            FROM fact_assertion f
            JOIN entity consumer ON consumer.id=f.subject_entity_id
            JOIN package_registry_identity pri ON pri.entity_id=f.object_entity_id
            LEFT JOIN dependency_resolution dr ON dr.fact_assertion_id=f.id
            WHERE f.tenant_id=%s AND f.predicate='DEPENDS_ON' AND f.system_to IS NULL
              AND consumer.entity_type='Repository'
              AND lower(pri.package_name)=lower(%s)
            ORDER BY consumer.name,component_path,f.id
            """,
            (tenant_id, package_name), tenant_id=tenant_id,
        )
        if not rows:
            return ChangeScopeList(subject=resolution.entity, scopes=[], policy_version=POLICY_KEY + "/1")
        scopes: list[ChangeScope] = []

        def build_scope(scope_id: str, kind: str, label: str, subset: list[dict[str, Any]], **extra: Any) -> ChangeScope:
            counts: dict[str, int] = defaultdict(int)
            for item in subset:
                counts[item["version"]] += 1
            return ChangeScope(
                id=scope_id, kind=kind, label=label, affected_count=len(subset),
                version_distribution=[
                    VersionDistribution(version=version, count=count)
                    for version, count in sorted(counts.items(), key=lambda item: _version_key(item[0]))
                ],
                evidence_fact_ids=sorted({item["fact_id"] for item in subset}, key=str), **extra,
            )

        scopes.append(build_scope("estate", "ESTATE", "Entire observed estate", rows))
        by_entity: dict[UUID, list[dict[str, Any]]] = defaultdict(list)
        by_component: dict[tuple[UUID, str], list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            by_entity[row["id"]].append(row)
            if row["component_path"]:
                by_component[(row["id"], row["component_path"])].append(row)
        for entity_id, subset in by_entity.items():
            scopes.append(build_scope(
                f"repository:{entity_id}", "REPOSITORY", subset[0]["name"], subset,
                entity_id=entity_id,
            ))
        for (entity_id, component_path), subset in by_component.items():
            scopes.append(build_scope(
                f"component:{entity_id}:{component_path}", "COMPONENT",
                f"{subset[0]['name']} · {component_path}", subset,
                entity_id=entity_id, component_path=component_path,
            ))
        return ChangeScopeList(subject=resolution.entity, scopes=scopes, policy_version=POLICY_KEY + "/1")

    async def _compile_draft(
        self, request: MutationCompileRequest, *, tenant_id: UUID, actor_key: str,
        provenance: dict[str, Any] | None = None,
    ) -> "MutationDraft":
        """Resolve, validate, and gate one mutation without persisting anything.

        Split out so a ChangeSet carrying several mutations compiles each through exactly the
        same grammar, resolution order, and gates as a single one. C2 requires ordered,
        atomicity-aware ChangeSets; letting the multi-mutation path validate differently from
        the single-mutation path would be a second compiler with a second set of rules.
        """
        predicate = request.predicate
        subject_query = request.subject_query
        target_version = request.target_version
        scope_id = request.scope_id
        parse_error: MutationValidationError | None = None
        if request.intent:
            match = _INTENT.fullmatch(request.intent)
            if match:
                predicate = "UPGRADE"
                subject_query = match.group("subject")
                target_version = match.group("target")
                raw_scope = match.group("scope")
                scope_id = "estate" if not raw_scope or raw_scope.lower() in {"estate", "the estate"} else raw_scope
            else:
                predicate = "UPGRADE"
                parse_error = MutationValidationError(
                    code="UNSUPPORTED_INTENT", field="intent",
                    message="Use the bounded form ‘Upgrade <package> to <exact version> [in <scope>]’.",
                )
        predicate = predicate or "UPGRADE"
        resolution, _ = await self._package_resolution(
            tenant_id=tenant_id, subject_id=request.subject_id, query=subject_query,
        )
        errors = [parse_error] if parse_error else []
        reasons: list[GateReason] = []
        target: ValidTarget | None = None
        selected_scope: ChangeScope | None = None
        capability = await self._action_capability(predicate, "Package", tenant_id=tenant_id)
        if capability is None or capability["lifecycle"] != "ACTIVE":
            errors.append(MutationValidationError(
                code="ACTION_NOT_ENABLED", field="predicate",
                message=(
                    f"{predicate} is in the ontology but is not enabled for deterministic compilation."
                    if capability is not None else
                    f"{predicate} has no registered capability for a Package subject."
                ),
            ))
        if resolution.state != "RESOLVED" or resolution.entity is None:
            errors.append(MutationValidationError(
                code="SUBJECT_NOT_RESOLVED", field="subject",
                message="Choose one exact canonical package; inferred candidates cannot compile.",
            ))
            reasons.append(GateReason(
                code="SUBJECT_NOT_RESOLVED",
                message="Package identity is ambiguous or absent. Choose an estate-backed candidate.",
                evidence_fact_ids=resolution.evidence_fact_ids,
            ))
        else:
            targets = await self.valid_targets(resolution.entity.id, tenant_id=tenant_id, limit=200)
            matches = [item for item in targets.targets if item.version == target_version]
            if len(matches) == 1:
                target = matches[0]
            else:
                errors.append(MutationValidationError(
                    code="TARGET_NOT_RESOLVED", field="target_version",
                    message="Choose an exact immutable version returned by the target provider.",
                ))
                reasons.append(GateReason(
                    code="TARGET_NOT_RESOLVED",
                    message="The requested target is not an exact registry-backed version.",
                ))
            scope_list = await self.scopes(resolution.entity.id, tenant_id=tenant_id)
            requested_scope = scope_id or "estate"
            matches = [scope for scope in scope_list.scopes if scope.id == requested_scope]
            if not matches:
                label_matches = [
                    scope for scope in scope_list.scopes
                    if scope.label.casefold() == requested_scope.casefold()
                ]
                if len(label_matches) == 1:
                    matches = label_matches
            if len(matches) == 1:
                selected_scope = matches[0]
            else:
                errors.append(MutationValidationError(
                    code="SCOPE_NOT_RESOLVED", field="scope_id",
                    message="Choose a scope backed by current dependency evidence.",
                ))
                reasons.append(GateReason(
                    code="SCOPE_NOT_RESOLVED",
                    message="The requested scope is not present in the observed estate.",
                ))
        if target and selected_scope and all(
            item.version == target.version for item in selected_scope.version_distribution
        ):
            errors.append(MutationValidationError(
                code="ALREADY_AT_TARGET", field="target_version",
                message="Every observed dependency in the selected scope is already at the target version.",
                evidence_fact_ids=selected_scope.evidence_fact_ids,
            ))
            reasons.append(GateReason(
                code="ALREADY_AT_TARGET",
                message="The proposed upgrade would not change the selected scope.",
                evidence_fact_ids=selected_scope.evidence_fact_ids,
            ))
        governed_entity_ids = [
            entity_id for entity_id in (
                resolution.entity.id if resolution.entity else None,
                selected_scope.entity_id if selected_scope else None,
            ) if entity_id is not None
        ]
        contradictions = await self.database.fetch_all(
            """
            SELECT DISTINCT contradiction.id,
              coalesce(array_agg(evidence.fact_assertion_id)
                FILTER (WHERE evidence.fact_assertion_id IS NOT NULL),'{}') evidence_fact_ids
            FROM estate_contradiction contradiction
            LEFT JOIN estate_assumption_dependent dependent
              ON dependent.assumption_id=contradiction.assumption_id
            LEFT JOIN estate_contradiction_claim contradiction_claim
              ON contradiction_claim.contradiction_id=contradiction.id
            LEFT JOIN estate_assumption_claim_evidence evidence
              ON evidence.claim_id=contradiction_claim.claim_id
            WHERE contradiction.status='OPEN'
              AND (contradiction.subject_entity_id=ANY(%s) OR dependent.entity_id=ANY(%s))
            GROUP BY contradiction.id
            """,
            (governed_entity_ids, governed_entity_ids), tenant_id=tenant_id,
        ) if governed_entity_ids else []
        if contradictions:
            evidence_ids = list(dict.fromkeys(
                fact_id for item in contradictions for fact_id in item["evidence_fact_ids"]
            ))
            errors.append(MutationValidationError(
                code="UNRESOLVED_CONTRADICTION", field="subject",
                message="Resolve contradictory estate claims affecting this mutation before compiling.",
                evidence_fact_ids=evidence_ids,
            ))
            reasons.append(GateReason(
                code="UNRESOLVED_CONTRADICTION",
                message="The mutation is blocked by the governed contradiction ledger.",
                evidence_fact_ids=evidence_ids,
            ))
        before = {
            "versions": [item.model_dump(mode="json") for item in selected_scope.version_distribution]
            if selected_scope else [],
        }
        after = {
            "version": target.version,
            # A catalogue target has no entity because the estate does not run it. Recording
            # None honestly is better than minting an entity for something nobody has.
            "target_entity_id": str(target.entity_id) if target.entity_id else None,
            "target_origin": target.origin,
        } if target else {}
        canonical_input = {
            "schema_version": "mutation/1.0.0", "predicate": predicate,
            "subject_entity_id": str(resolution.entity.id) if resolution.entity else None,
            "before": before, "after": after,
            "scope": selected_scope.model_dump(mode="json") if selected_scope else None,
            "constraints": {"exact_target": True, "require_evidence": True},
            "ontology_version": ONTOLOGY_VERSION,
        }
        mutation_fingerprint = _fingerprint(canonical_input)
        lifecycle = "VALIDATED" if not errors else "REJECTED"
        mutation_provenance = {
            "actor_key": actor_key, "entry_point": "COMMAND" if request.intent else "API",
            "ontology_version": ONTOLOGY_VERSION, "provider_version": PROVIDER_VERSION,
        }
        if provenance:
            mutation_provenance.update(provenance)
        mutation = MutationIR(
            predicate=predicate, subject=resolution, before=before, after=after,
            scope=selected_scope, constraints=canonical_input["constraints"],
            provenance=mutation_provenance,
            input_fingerprint=mutation_fingerprint, lifecycle=lifecycle,
            validation_errors=[error for error in errors if error is not None],
        )
        for error in errors:
            if error and not any(reason.code == error.code for reason in reasons):
                reasons.append(GateReason(
                    code=error.code, message=error.message,
                    evidence_fact_ids=error.evidence_fact_ids,
                ))
        return MutationDraft(
            mutation=mutation, predicate=predicate, resolution=resolution, target=target,
            scope=selected_scope, errors=[error for error in errors if error is not None],
            reasons=reasons, fingerprint=mutation_fingerprint,
        )

    async def _action_capability(
        self, predicate: str, subject_type: str, *, tenant_id: UUID | None,
    ) -> dict[str, Any] | None:
        """Return the registered ActionCapability governing a predicate and subject type.

        C1 says the ontology and its capability rows decide what may compile. Until now this
        table was read only to list action types while validation was hardcoded to UPGRADE, so
        enabling a predicate meant editing Python rather than seeding a row.
        """
        return await self.database.fetch_one(
            """
            SELECT * FROM action_capability
            WHERE predicate=%s AND subject_type=%s
            ORDER BY (tenant_id IS NOT NULL) DESC LIMIT 1
            """,
            (predicate, subject_type), tenant_id=tenant_id,
        )

    async def compile_mutation(
        self, request: MutationCompileRequest, *, tenant_id: UUID | None, actor_key: str,
        provenance: dict[str, Any] | None = None,
    ) -> MutationCompileResult:
        if tenant_id is None:
            raise APIError(400, "TENANT_REQUIRED", "A tenant is required to compile a change.")
        return await self._compile_change_set(
            [request], tenant_id=tenant_id, actor_key=actor_key,
            idempotency_key=request.idempotency_key, provenance=provenance,
        )

    async def compile_change_set(
        self, request: ChangeSetCompileRequest, *, tenant_id: UUID | None, actor_key: str,
    ) -> MutationCompileResult:
        """Compile a ChangeSet from a pull request, ticket, architecture change, or agent.

        Every one of these entry points reaches the deterministic engine through the same
        Mutation IR as the command bar, which is what §7 asks for. The source states what it
        proposes; StackGraph decides whether that grounds in the estate.
        """
        if tenant_id is None:
            raise APIError(400, "TENANT_REQUIRED", "A tenant is required to compile a change.")
        provenance: dict[str, Any] = {"entry_point": request.entry_point}
        if request.external_reference:
            provenance["external_reference"] = request.external_reference
        return await self._compile_change_set(
            [
                MutationCompileRequest(
                    predicate=item.predicate, subject_id=item.subject_id,
                    subject_query=item.subject_query, target_version=item.target_version,
                    scope_id=item.scope_id, idempotency_key=request.idempotency_key,
                )
                for item in request.mutations
            ],
            tenant_id=tenant_id, actor_key=actor_key,
            idempotency_key=request.idempotency_key, provenance=provenance,
            atomic=request.atomic,
        )

    async def _compile_change_set(
        self, requests: list[MutationCompileRequest], *, tenant_id: UUID, actor_key: str,
        idempotency_key: str, provenance: dict[str, Any] | None = None, atomic: bool = True,
    ) -> MutationCompileResult:
        """Compile an ordered ChangeSet of one or more mutations.

        Every mutation must pass its own gates *and* the set must be internally consistent
        before anything is persisted. A ChangeSet is atomic by default, so one blocked mutation
        blocks the set: persisting a partially valid set would offer the user a plan whose
        stated scope is not the plan that would run.
        """
        if not requests:
            raise APIError(400, "EMPTY_CHANGE_SET", "A ChangeSet must contain at least one mutation.")
        capability = await self._action_capability("UPGRADE", "Package", tenant_id=tenant_id)
        max_mutations = int(
            ((capability or {}).get("validation_rules") or {}).get("max_mutations") or 20
        )
        if len(requests) > max_mutations:
            raise APIError(
                422, "CHANGE_SET_TOO_LARGE",
                f"A ChangeSet may carry at most {max_mutations} mutations.",
                {"requested": len(requests), "limit": max_mutations},
            )
        drafts = [
            await self._compile_draft(
                item, tenant_id=tenant_id, actor_key=actor_key, provenance=provenance,
            )
            for item in requests
        ]
        reasons: list[GateReason] = []
        for reason in (item for draft in drafts for item in draft.reasons):
            if not any(existing.code == reason.code for existing in reasons):
                reasons.append(reason)
        reasons.extend(_change_set_conflicts(drafts))

        if reasons or any(draft.errors for draft in drafts):
            first = drafts[0]
            result = MutationCompileResult(
                command_state=(
                    "TOKENISED" if first.resolution.state != "UNRESOLVED" else "RESOLVING"
                ),
                draft=first.mutation, gate=ChangeGate(state="BLOCKED", reasons=reasons),
            )
            await self._audit_change(
                tenant_id=tenant_id, actor_key=actor_key, action="change_set.compile_blocked",
                target_kind="mutation_draft", target_id=first.fingerprint,
                detail={
                    "predicate": first.predicate,
                    "mutations": len(drafts),
                    "reason_codes": [reason.code for reason in reasons],
                    "entry_point": first.mutation.provenance["entry_point"],
                },
            )
            return result

        change_fingerprint = _fingerprint({
            "atomic": atomic, "mutations": [draft.fingerprint for draft in drafts],
        })
        async with self.database.session(tenant_id) as connection:
            existing_cursor = await connection.execute(
                """
                SELECT id,input_fingerprint,idempotency_key,created_at
                FROM change_set
                WHERE tenant_id=%s AND (idempotency_key=%s OR input_fingerprint=%s)
                ORDER BY (idempotency_key=%s) DESC
                LIMIT 1
                """,
                (tenant_id, idempotency_key, change_fingerprint, idempotency_key),
            )
            existing = await existing_cursor.fetchone()
            if (
                existing
                and existing["idempotency_key"] == idempotency_key
                and existing["input_fingerprint"] != change_fingerprint
            ):
                raise APIError(
                    409, "IDEMPOTENCY_KEY_REUSED",
                    "The idempotency key was already used for a different ChangeSet.",
                )
            replayed = existing is not None
            if existing:
                change_set_id = existing["id"]
                created_at = existing["created_at"]
                mutation_cursor = await connection.execute(
                    "SELECT id FROM mutation WHERE change_set_id=%s ORDER BY ordinal",
                    (change_set_id,),
                )
                for draft, row in zip(drafts, await mutation_cursor.fetchall()):
                    draft.mutation.id = row["id"]
            else:
                change_set_id = uuid4()
                created_at = datetime.now(UTC)
                await connection.execute(
                    """
                    INSERT INTO change_set(
                      id,tenant_id,atomic,lifecycle,input_fingerprint,idempotency_key,
                      provenance,created_by,created_at
                    ) VALUES (%s,%s,%s,'VALIDATED',%s,%s,%s,%s,%s)
                    """,
                    (
                        change_set_id, tenant_id, atomic, change_fingerprint, idempotency_key,
                        Jsonb(drafts[0].mutation.provenance), actor_key, created_at,
                    ),
                )
                for ordinal, draft in enumerate(drafts):
                    draft.mutation.id = uuid4()
                    assert draft.resolution.entity is not None and draft.scope is not None
                    await connection.execute(
                        """
                        INSERT INTO mutation(
                          id,tenant_id,change_set_id,ordinal,predicate,subject_entity_id,
                          subject_resolution,before_state,after_state,scope,constraints,
                          provenance,input_fingerprint,lifecycle
                        ) VALUES (%s,%s,%s,%s,%s,%s,'RESOLVED',%s,%s,%s,%s,%s,%s,'VALIDATED')
                        """,
                        (
                            draft.mutation.id, tenant_id, change_set_id, ordinal, draft.predicate,
                            draft.resolution.entity.id, Jsonb(draft.mutation.before),
                            Jsonb(draft.mutation.after),
                            Jsonb(draft.scope.model_dump(mode="json")),
                            Jsonb(draft.mutation.constraints),
                            Jsonb(draft.mutation.provenance), draft.fingerprint,
                        ),
                    )
        change_set = ChangeSetModel(
            id=change_set_id, mutations=[draft.mutation for draft in drafts],
            lifecycle="VALIDATED", input_fingerprint=change_fingerprint, created_at=created_at,
        )
        result = MutationCompileResult(
            command_state="COMPILED", change_set=change_set, draft=drafts[0].mutation,
            gate=_clear_gate(), replayed=replayed,
        )
        await self._audit_change(
            tenant_id=tenant_id, actor_key=actor_key, action="change_set.compile",
            target_kind="change_set", target_id=str(change_set_id),
            detail={
                "predicate": drafts[0].predicate, "replayed": replayed,
                "mutations": len(drafts),
                "entry_point": drafts[0].mutation.provenance["entry_point"],
            },
        )
        return result

    async def compile_deterministic_insight(
        self, insight_id: UUID, request: RecommendationCompileRequest,
        *, tenant_id: UUID | None, actor_key: str,
    ) -> MutationCompileResult:
        """Compile a deterministic insight into a ChangeSet without re-entering it by hand.

        §8 names version fragmentation and unsupported runtimes among the changes worth
        surfacing, and R1 requires reaching a simulation from an estate finding without manual
        re-entry. Insights carry a subject and a recommended action but no target version, so
        the target is derived the same way the command bar derives it: the version the most
        repositories already run, which converges the estate without introducing anything it has
        not exercised.

        Anything that cannot produce a valid proposal is refused with a precise reason rather
        than a generic failure, because "this cannot be simulated" is only useful if it says why.
        """
        if tenant_id is None:
            raise APIError(400, "TENANT_REQUIRED", "A tenant is required to compile an insight.")
        insights = await self.deterministic_insights(
            tenant_id=tenant_id, scope_entity_id=None, rule_key=None, limit=500,
        )
        insight = next(
            (item for item in insights.insights if item.id == insight_id), None,
        )
        if insight is None:
            raise APIError(404, "INSIGHT_NOT_FOUND", "The deterministic insight was not found.")

        reason: dict[str, Any] | None = None
        if insight.recommendation is None:
            reason = {
                "code": "NO_RECOMMENDED_ACTION",
                "message": "The insight reports a condition but recommends no action.",
            }
        elif insight.recommendation.action not in {"UPGRADE", "CONSOLIDATE"}:
            reason = {
                "code": "ACTION_NOT_ENABLED",
                "message": (
                    f"{insight.recommendation.action} insights are not yet compilable; only "
                    "upgrade and consolidation are."
                ),
            }
        elif insight.subject.kind not in {"Package", "PackageVersion"}:
            reason = {
                "code": "SUBJECT_NOT_RESOLVED",
                "message": (
                    f"The insight subject is a {insight.subject.kind}; only a canonical package "
                    "can currently compile."
                ),
            }
        if reason is None:
            targets = await self.valid_targets(insight.subject.id, tenant_id=tenant_id, limit=200)
            consolidation = next(
                (item for item in targets.targets if item.recommendation == "CONSOLIDATE"), None,
            )
            if consolidation is None:
                reason = {
                    "code": "TARGET_NOT_RESOLVED",
                    "message": (
                        "No estate-backed consolidation target exists for this package, so the "
                        "insight cannot propose an exact version."
                    ),
                }
        if reason is not None:
            raise APIError(
                409, "INSIGHT_NOT_SIMULATABLE", reason["message"],
                {"insight_id": str(insight_id), "reason": reason},
            )

        idempotency_key = request.idempotency_key or (
            f"insight:{insight_id}:{insight.input_fingerprint}"
        )
        return await self._compile_change_set(
            [MutationCompileRequest(
                predicate="UPGRADE", subject_id=insight.subject.id,
                target_version=consolidation.version, scope_id="estate",
                idempotency_key=idempotency_key,
            )],
            tenant_id=tenant_id, actor_key=actor_key, idempotency_key=idempotency_key,
            provenance={
                "entry_point": "DETERMINISTIC_INSIGHT",
                "insight_id": str(insight_id),
                "rule_key": insight.rule_key,
                "rule_version": insight.rule_version,
                "insight_fingerprint": insight.input_fingerprint,
            },
        )

    async def compile_modernization_recommendation(
        self, recommendation_id: UUID, request: RecommendationCompileRequest,
        *, tenant_id: UUID | None, actor_key: str,
    ) -> MutationCompileResult:
        if tenant_id is None:
            raise APIError(400, "TENANT_REQUIRED", "A tenant is required to compile a recommendation.")
        recommendation = await self.database.fetch_one(
            """
            SELECT recommendation.id,recommendation.action,recommendation.source_revision,
                   recommendation.analysis_fingerprint,recommendation.stale_at,
                   recommendation.repository_entity_id,recommendation.proposed_change_set_id,
                   candidate.subject_entity_ids,option.id option_id,option.option_kind,
                   option.target_entity_id,subject.entity_type subject_type,
                   target_identity.package_name target_package_name,
                   target_identity.package_version target_version
            FROM modernization_recommendation recommendation
            JOIN modernization_candidate candidate
              ON candidate.id=recommendation.modernization_candidate_id
            LEFT JOIN modernization_option option ON option.id=recommendation.selected_option_id
            LEFT JOIN entity subject ON subject.id=candidate.subject_entity_ids[1]
            LEFT JOIN package_registry_identity target_identity
              ON target_identity.entity_id=option.target_entity_id
            WHERE recommendation.id=%s
            """,
            (recommendation_id,), tenant_id=tenant_id,
        )
        if recommendation is None:
            raise APIError(
                404, "MODERNIZATION_RECOMMENDATION_NOT_FOUND", "The recommendation was not found.",
            )
        reason: dict[str, Any] | None = None
        subject_ids = list(recommendation["subject_entity_ids"] or [])
        if recommendation["stale_at"] is not None:
            reason = {"code": "RECOMMENDATION_STALE", "message": "The recommendation is stale."}
        elif recommendation["action"] != "UPGRADE":
            reason = {
                "code": "ACTION_NOT_ENABLED",
                "message": "Only UPGRADE Package recommendations are currently simulatable.",
            }
        elif len(subject_ids) != 1 or recommendation["subject_type"] != "Package":
            reason = {
                "code": "SUBJECT_NOT_RESOLVED",
                "message": "The recommendation must identify one canonical Package subject.",
            }
        elif recommendation["target_entity_id"] is None or not recommendation["target_version"]:
            reason = {
                "code": "TARGET_NOT_RESOLVED",
                "message": "The selected recommendation option has no exact registry-backed version.",
            }
        if reason:
            async with self.database.session(tenant_id) as connection:
                await connection.execute(
                    """
                    UPDATE modernization_recommendation
                    SET not_simulatable_reason=%s,updated_at=now()
                    WHERE id=%s
                    """,
                    (Jsonb(reason), recommendation_id),
                )
            raise APIError(
                409, "RECOMMENDATION_NOT_SIMULATABLE", reason["message"],
                {"recommendation_id": str(recommendation_id), "reason": reason},
            )
        idempotency_key = request.idempotency_key or (
            f"recommendation:{recommendation_id}:{recommendation['analysis_fingerprint']}"
        )
        result = await self.compile_mutation(
            MutationCompileRequest(
                predicate="UPGRADE", subject_id=subject_ids[0],
                target_version=recommendation["target_version"],
                scope_id=f"repository:{recommendation['repository_entity_id']}",
                idempotency_key=idempotency_key,
            ),
            tenant_id=tenant_id, actor_key=actor_key,
            provenance={
                "entry_point": "MODERNIZATION_RECOMMENDATION",
                "recommendation_id": str(recommendation_id),
                "recommendation_fingerprint": recommendation["analysis_fingerprint"],
                "source_revision": recommendation["source_revision"],
                "selected_option_id": str(recommendation["option_id"]),
            },
        )
        if result.change_set and result.change_set.id:
            async with self.database.session(tenant_id) as connection:
                await connection.execute(
                    """
                    UPDATE modernization_recommendation
                    SET proposed_change_set_id=%s,not_simulatable_reason=NULL,updated_at=now()
                    WHERE id=%s
                    """,
                    (result.change_set.id, recommendation_id),
                )
        elif result.gate.state != "CLEAR":
            detail = {
                "code": "COMPILATION_BLOCKED",
                "message": "The recommendation did not pass deterministic compilation gates.",
                "gate_reasons": [item.model_dump(mode="json") for item in result.gate.reasons],
            }
            async with self.database.session(tenant_id) as connection:
                await connection.execute(
                    """
                    UPDATE modernization_recommendation
                    SET not_simulatable_reason=%s,updated_at=now() WHERE id=%s
                    """,
                    (Jsonb(detail), recommendation_id),
                )
        return result

    async def validate_mutation(
        self, request: MutationValidateRequest, *, tenant_id: UUID | None, actor_key: str,
    ) -> MutationCompileResult:
        change_set = await self._load_change_set(request.change_set_id, tenant_id=tenant_id)
        if tenant_id is not None:
            await self._audit_change(
                tenant_id=tenant_id, actor_key=actor_key, action="change_set.validate",
                target_kind="change_set", target_id=str(request.change_set_id),
                detail={"lifecycle": change_set.lifecycle},
            )
        return MutationCompileResult(
            command_state="COMPILED", change_set=change_set, draft=change_set.mutations[0],
            gate=_clear_gate(), replayed=True,
        )

    async def _load_change_set(
        self, change_set_id: UUID, *, tenant_id: UUID | None,
    ) -> ChangeSetModel:
        change = await self.database.fetch_one(
            "SELECT * FROM change_set WHERE id=%s", (change_set_id,), tenant_id=tenant_id,
        )
        if change is None:
            raise APIError(404, "CHANGE_SET_NOT_FOUND", "The ChangeSet was not found.")
        rows = await self.database.fetch_all(
            """
            SELECT m.*,e.entity_type,e.name,e.canonical_key
            FROM mutation m JOIN entity e ON e.id=m.subject_entity_id
            WHERE m.change_set_id=%s ORDER BY m.ordinal
            """,
            (change_set_id,), tenant_id=tenant_id,
        )
        mutations = [MutationIR(
            id=row["id"], predicate=row["predicate"],
            subject=EntityResolution(
                state="RESOLVED", entity=EntitySummary(
                    id=row["subject_entity_id"], kind=row["entity_type"], name=row["name"],
                    canonical_key=row["canonical_key"],
                ),
                confidence=1, method="PERSISTED_CANONICAL_ID", method_version=RESOLUTION_VERSION,
            ),
            before=row["before_state"], after=row["after_state"],
            scope=ChangeScope(**row["scope"]), constraints=row["constraints"],
            provenance=row["provenance"], input_fingerprint=row["input_fingerprint"],
            lifecycle=row["lifecycle"], validation_errors=[
                MutationValidationError(**error) for error in row["validation_errors"]
            ],
        ) for row in rows]
        return ChangeSetModel(
            id=change["id"], atomic=change["atomic"], mutations=mutations,
            lifecycle=change["lifecycle"], input_fingerprint=change["input_fingerprint"],
            created_at=change["created_at"],
        )

    async def submit_simulation(
        self, request: SimulationCreateRequest, *, tenant_id: UUID | None, actor_key: str,
    ) -> SimulationRunModel:
        if tenant_id is None:
            raise APIError(400, "TENANT_REQUIRED", "A tenant is required to simulate a change.")
        change_set = await self._load_change_set(request.change_set_id, tenant_id=tenant_id)
        if change_set.lifecycle != "VALIDATED":
            raise APIError(409, "CHANGE_SET_NOT_VALIDATED", "Only a validated ChangeSet can be simulated.")
        policy = await self.database.fetch_one(
            """
            SELECT * FROM impact_policy WHERE policy_key=%s AND status='ACTIVE'
            ORDER BY (tenant_id IS NOT NULL) DESC,version DESC LIMIT 1
            """,
            (POLICY_KEY,), tenant_id=tenant_id,
        )
        if policy is None:
            raise APIError(503, "IMPACT_POLICY_UNAVAILABLE", "No active package-upgrade impact policy is available.")
        watermark_row = await self.database.fetch_one(
            """
            SELECT coalesce(max(system_from)::text,'empty') fact_watermark,
                   coalesce((SELECT max(id)::text FROM projection_outbox),'empty') projection_watermark
            FROM fact_assertion WHERE tenant_id=%s AND system_to IS NULL
            """,
            (tenant_id,), tenant_id=tenant_id,
        )
        estate_watermark = f"facts:{watermark_row['fact_watermark']};projection:{watermark_row['projection_watermark']}"
        input_fingerprint = _fingerprint({
            "tenant_id": tenant_id, "change_set": change_set.input_fingerprint,
            "estate_watermark": estate_watermark, "policy": policy["content_hash"],
            "provider": PROVIDER_VERSION,
        })
        async with self.database.session(tenant_id) as connection:
            cursor = await connection.execute(
                """
                INSERT INTO simulation_run(
                  tenant_id,change_set_id,idempotency_key,status,estate_watermark,policy_id,
                  policy_version,provider_version,scanner_versions,input_fingerprint,created_by
                ) VALUES (%s,%s,%s,'QUEUED',%s,%s,%s,%s,'{}',%s,%s)
                ON CONFLICT DO NOTHING RETURNING id
                """,
                (
                    tenant_id, request.change_set_id, request.idempotency_key, estate_watermark,
                    policy["id"], f"{POLICY_KEY}/{policy['version']}", PROVIDER_VERSION,
                    input_fingerprint, actor_key,
                ),
            )
            created = await cursor.fetchone()
            if created is None:
                cursor = await connection.execute(
                    """
                    SELECT id,input_fingerprint FROM simulation_run
                    WHERE tenant_id=%s AND (idempotency_key=%s OR input_fingerprint=%s)
                    ORDER BY created_at DESC LIMIT 1
                    """,
                    (tenant_id, request.idempotency_key, input_fingerprint),
                )
                existing = await cursor.fetchone()
                if existing is None:
                    raise APIError(409, "SIMULATION_CONFLICT", "The simulation could not be submitted idempotently.")
                if existing["input_fingerprint"] != input_fingerprint:
                    raise APIError(
                        409, "IDEMPOTENCY_KEY_REUSED",
                        "The idempotency key was already used for a different simulation.",
                    )
                run_id = existing["id"]
                replayed = True
            else:
                run_id = created["id"]
                replayed = False
        result = await self.simulation(run_id, tenant_id=tenant_id)
        result.replayed = replayed
        await self._audit_change(
            tenant_id=tenant_id, actor_key=actor_key, action="simulation.submit",
            target_kind="simulation_run", target_id=str(run_id),
            detail={"change_set_id": str(request.change_set_id), "replayed": replayed},
        )
        return result

    async def simulation(self, run_id: UUID, *, tenant_id: UUID | None) -> SimulationRunModel:
        run = await self.database.fetch_one(
            "SELECT * FROM simulation_run WHERE id=%s", (run_id,), tenant_id=tenant_id,
        )
        if run is None:
            raise APIError(404, "SIMULATION_NOT_FOUND", "The SimulationRun was not found.")
        rows = await self.database.fetch_all(
            """
            SELECT finding.*,entity.entity_type,entity.name,entity.canonical_key
            FROM simulation_finding finding
            LEFT JOIN entity ON entity.id=finding.affected_entity_id
            WHERE finding.simulation_run_id=%s
            ORDER BY CASE finding.classification
              WHEN 'DIRECT' THEN 1 WHEN 'TRANSITIVE' THEN 2 WHEN 'CONTEXT' THEN 3
              WHEN 'STOP' THEN 4 ELSE 5 END,finding.severity DESC,finding.deterministic_key
            """,
            (run_id,), tenant_id=tenant_id,
        )
        path_ids = {value for row in rows for value in (row["path_entity_ids"] or [])}
        path_rows = await self.database.fetch_all(
            "SELECT id,entity_type,name,canonical_key FROM entity WHERE id=ANY(%s)",
            (list(path_ids),), tenant_id=tenant_id,
        ) if path_ids else []
        path_entities = {row["id"]: _entity(row) for row in path_rows}
        findings = [SimulationFinding(
            id=row["id"], rule_key=row["rule_key"], rule_version=row["rule_version"],
            classification=row["classification"], severity=row["severity"], title=row["title"],
            detail=row["detail"],
            affected_entity=_entity(row) if row["affected_entity_id"] else None,
            confidence=float(row["confidence"]), evidence_fact_ids=row["evidence_fact_ids"] or [],
            path=[path_entities[value] for value in (row["path_entity_ids"] or []) if value in path_entities],
        ) for row in rows]
        interpretation_row = await self.database.fetch_one(
            "SELECT * FROM simulation_interpretation WHERE simulation_run_id=%s",
            (run_id,), tenant_id=tenant_id,
        )
        interpretation = SimulationInterpretation(
            status=interpretation_row["status"], risk=interpretation_row["risk"],
            explanation=interpretation_row["explanation"], rollout=interpretation_row["rollout"],
            remediation=interpretation_row.get("remediation") or [],
            verification=interpretation_row["verification"],
            cited_finding_ids=interpretation_row["cited_finding_ids"],
            quarantined_claims=[
                QuarantinedClaim(**item)
                for item in interpretation_row.get("quarantined_claims") or []
            ],
            limitation=interpretation_row["limitation"],
        ) if interpretation_row else SimulationInterpretation(
            status="UNAVAILABLE", limitation=(
                "Interpretation has not run. Deterministic findings remain authoritative."
                if run["status"] in {"QUEUED", "RUNNING"}
                else "AI interpretation is disabled; deterministic findings are complete."
            ),
        )
        limitations = [GateReason(**item) for item in run["limitations"]]
        gate = ChangeGate(
            state="CONSTRAIN" if run["status"] == "LIMITED" else (
                "BLOCKED" if run["status"] in {"NOT_SIMULATABLE", "FAILED", "CANCELLED"} else "CLEAR"
            ),
            reasons=limitations if run["status"] in {"LIMITED", "NOT_SIMULATABLE", "FAILED", "CANCELLED"}
            else [],
        )
        return SimulationRunModel(
            id=run["id"], change_set_id=run["change_set_id"], status=run["status"], gate=gate,
            estate_watermark=run["estate_watermark"], policy_version=run["policy_version"],
            provider_version=run["provider_version"], scanner_versions=run["scanner_versions"],
            findings=findings, interpretation=interpretation, limitations=limitations,
            result_hash=run["result_hash"], created_at=run["created_at"],
            started_at=run["started_at"], completed_at=run["completed_at"],
        )

    async def cancel_simulation(
        self, run_id: UUID, *, tenant_id: UUID | None, actor_key: str,
    ) -> SimulationRunModel:
        row = await self.database.fetch_one(
            "SELECT status FROM simulation_run WHERE id=%s", (run_id,), tenant_id=tenant_id,
        )
        if row is None:
            raise APIError(404, "SIMULATION_NOT_FOUND", "The SimulationRun was not found.")
        if row["status"] not in {"QUEUED", "RUNNING"}:
            raise APIError(409, "SIMULATION_TERMINAL", "A terminal SimulationRun cannot be cancelled.")
        await self.database.fetch_one(
            """
            UPDATE simulation_run SET status='CANCELLED',completed_at=now(),updated_at=now(),
              limitations='[{"code":"CANCELLED","message":"Simulation was cancelled by an authorized user.","evidence_fact_ids":[]}]'
            WHERE id=%s RETURNING id
            """,
            (run_id,), tenant_id=tenant_id,
        )
        if tenant_id is not None:
            await self._audit_change(
                tenant_id=tenant_id, actor_key=actor_key, action="simulation.cancel",
                target_kind="simulation_run", target_id=str(run_id), detail={},
            )
        return await self.simulation(run_id, tenant_id=tenant_id)

    async def run_next_simulation(
        self, *, max_nodes: int, max_edges: int, timeout_seconds: int = 120,
    ) -> bool:
        worker = f"{socket.gethostname()}:{uuid4().hex[:8]}"
        async with self.database.session(None) as connection:
            cursor = await connection.execute(
                """
                WITH candidate AS (
                  SELECT id FROM simulation_run
                  WHERE status='QUEUED' AND available_at<=now()
                    AND stackgraph_tenant_service_running(tenant_id,'change-simulator')
                    AND (leased_until IS NULL OR leased_until<now())
                  ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1
                )
                UPDATE simulation_run run SET status='RUNNING',leased_by=%s,
                  leased_until=now()+interval '2 minutes',attempt=attempt+1,
                  started_at=coalesce(started_at,now()),updated_at=now()
                FROM candidate WHERE run.id=candidate.id RETURNING run.*
                """,
                (worker,),
            )
            run = await cursor.fetchone()
        if run is None:
            return False
        try:
            async with asyncio.timeout(timeout_seconds):
                await self._execute_simulation(run, max_nodes=max_nodes, max_edges=max_edges)
        except Exception as error:
            async with self.database.session(run["tenant_id"]) as connection:
                if run["attempt"] >= run["max_attempts"]:
                    limitation = [{
                        "code": "SIMULATION_FAILED",
                        "message": "Deterministic simulation exhausted its bounded retries.",
                        "evidence_fact_ids": [],
                    }]
                    await connection.execute(
                        """
                        UPDATE simulation_run SET status='FAILED',failure_detail=%s,limitations=%s,
                          completed_at=now(),leased_by=NULL,leased_until=NULL,updated_at=now()
                        WHERE id=%s
                        """,
                        (Jsonb({"error_class": type(error).__name__}), Jsonb(limitation), run["id"]),
                    )
                else:
                    await connection.execute(
                        """
                        UPDATE simulation_run SET status='QUEUED',available_at=now()+interval '10 seconds',
                          failure_detail=%s,leased_by=NULL,leased_until=NULL,updated_at=now()
                        WHERE id=%s
                        """,
                        (Jsonb({"error_class": type(error).__name__}), run["id"]),
                    )
        return True


    async def _execute_simulation(
        self, run: dict[str, Any], *, max_nodes: int, max_edges: int,
    ) -> None:
        """Simulate every mutation in the ChangeSet and persist one merged result.

        A ChangeSet is the unit a user submits, so it is the unit that gets a status, a result
        hash, and a set of findings. Each mutation is walked separately under the same pinned
        policy and its findings are namespaced by ordinal, so two mutations touching the same
        dependency fact produce two distinct findings rather than silently colliding.
        """
        tenant_id = run["tenant_id"]
        change_set = await self._load_change_set(run["change_set_id"], tenant_id=tenant_id)
        if not change_set.mutations:
            raise RuntimeError("persisted ChangeSet carries no mutations")
        policy_row = await self.database.fetch_one(
            "SELECT * FROM impact_policy WHERE id=%s", (run["policy_id"],), tenant_id=tenant_id,
        )
        if policy_row is None:
            raise RuntimeError("the simulation's pinned impact policy no longer exists")
        # A policy that cannot be read is a refusal. Falling back to a default walk would
        # produce a result stamped with a policy version that does not describe how it was made.
        policy = ImpactPolicyConfiguration.from_row(policy_row)
        node_budget = min(max_nodes, policy.max_nodes) if policy.max_nodes else max_nodes
        edge_budget = min(max_edges, policy.max_edges) if policy.max_edges else max_edges
        # Budgets are the ChangeSet's, not each mutation's, so a large set cannot multiply the
        # traversal cost by its own length.
        per_mutation_nodes = max(1, node_budget // len(change_set.mutations))
        per_mutation_edges = max(1, edge_budget // len(change_set.mutations))

        findings: list[dict[str, Any]] = []
        limitations: list[dict[str, Any]] = []
        scanner_versions: set[str] = set()
        limited = False
        simulatable = 0
        for ordinal, mutation in enumerate(change_set.mutations):
            outcome = await self._simulate_mutation(
                run=run, mutation=mutation, ordinal=ordinal, policy=policy,
                node_budget=per_mutation_nodes, edge_budget=per_mutation_edges,
            )
            findings.extend(outcome["findings"])
            scanner_versions |= outcome["scanner_versions"]
            limited = limited or outcome["limited"]
            simulatable += int(outcome["eligible"] > 0)
            for limitation in outcome["limitations"]:
                if not any(item["code"] == limitation["code"] for item in limitations):
                    limitations.append(limitation)

        if simulatable == 0:
            status = "NOT_SIMULATABLE"
        elif limited or simulatable < len(change_set.mutations):
            # A set where some mutations found no eligible path is constrained, not complete.
            status = "LIMITED"
        else:
            status = "SUCCEEDED"

        findings.sort(key=lambda item: (
            _CLASSIFICATION_ORDER.index(item["classification"]), item["deterministic_key"],
        ))
        canonical_result = [{
            key: (str(value) if isinstance(value, UUID) else value)
            for key, value in finding.items() if key not in {"id"}
        } for finding in findings]
        result_hash = _fingerprint({
            "change_set": change_set.input_fingerprint,
            "estate_watermark": run["estate_watermark"], "policy": run["policy_version"],
            "policy_schema": policy.schema_version,
            "findings": canonical_result, "limitations": limitations,
        })
        async with self.database.session(tenant_id) as connection:
            for finding in findings:
                await connection.execute(
                    """
                    INSERT INTO simulation_finding(
                      id,tenant_id,simulation_run_id,rule_key,rule_version,classification,severity,
                      title,detail,affected_entity_id,confidence,evidence_fact_ids,path_entity_ids,
                      fact_payload,curated_evidence,deterministic_key
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT(simulation_run_id,deterministic_key) DO NOTHING
                    """,
                    (
                        finding["id"], tenant_id, run["id"], finding["rule_key"],
                        finding["rule_version"], finding["classification"], finding["severity"],
                        finding["title"], finding["detail"], finding["affected_entity_id"],
                        finding["confidence"], finding["evidence_fact_ids"], finding["path_entity_ids"],
                        Jsonb(finding["fact_payload"]), Jsonb(finding["curated_evidence"]),
                        finding["deterministic_key"],
                    ),
                )
            await connection.execute(
                """
                UPDATE simulation_run SET status=%s,result_hash=%s,limitations=%s,
                  scanner_versions=%s,completed_at=now(),leased_by=NULL,leased_until=NULL,updated_at=now()
                WHERE id=%s
                """,
                (status, result_hash, Jsonb(limitations), sorted(scanner_versions), run["id"]),
            )
        await self._interpret_simulation(run_id=run["id"], tenant_id=tenant_id, findings=findings)

    async def _simulate_mutation(
        self, *, run: dict[str, Any], mutation: Any, ordinal: int,
        policy: ImpactPolicyConfiguration, node_budget: int, edge_budget: int,
    ) -> dict[str, Any]:
        """Walk the estate for one mutation and return its findings, unpersisted."""
        tenant_id = run["tenant_id"]
        if mutation.subject.entity is None or mutation.scope is None:
            raise RuntimeError("persisted mutation is missing canonical identity or scope")

        _, package_name = await self._package_resolution(
            tenant_id=tenant_id, subject_id=mutation.subject.entity.id, query=None,
        )
        if package_name is None:
            raise RuntimeError("persisted package identity no longer resolves")
        subject_id = mutation.subject.entity.id
        scope = mutation.scope

        seed_rows = await self._seed_dependents(
            tenant_id=tenant_id, package_name=package_name, scope=scope,
            subject_types=policy.seed_subject_types, limit=edge_budget + 1,
        )
        limitations: list[dict[str, Any]] = []
        limited = len(seed_rows) > edge_budget
        seed_rows = seed_rows[:edge_budget]
        if limited:
            limitations.append({
                "code": "TRAVERSAL_BUDGET",
                "message": "The edge budget truncated the direct dependency set.",
                "evidence_fact_ids": [],
            })

        scanner_versions = {
            f"{row['extractor_key']}/{row['extractor_version']}" for row in seed_rows
        }
        findings: list[dict[str, Any]] = []
        seeds: list[TraversedNode] = []
        eligible_rows: list[dict[str, Any]] = []

        def add_finding(
            *, key: str, rule_key: str, classification: str, severity: str, title: str,
            detail: str, affected_entity_id: UUID, confidence: float,
            evidence_fact_ids: list[UUID], path_entity_ids: list[UUID],
            fact_payload: dict[str, Any], curated_evidence: list[dict[str, Any]] | None = None,
        ) -> None:
            # Namespaced by ordinal so two mutations touching the same dependency fact
            # produce two findings rather than one silently overwriting the other.
            key = f"m{ordinal}:{key}"
            findings.append({
                "id": uuid5(_SIMULATION_NAMESPACE, f"{run['id']}:{key}"),
                "rule_key": rule_key, "rule_version": "2.0.0",
                "classification": classification, "severity": severity,
                "title": title, "detail": detail,
                "affected_entity_id": affected_entity_id, "confidence": confidence,
                "evidence_fact_ids": evidence_fact_ids,
                "path_entity_ids": path_entity_ids,
                "fact_payload": fact_payload,
                "curated_evidence": curated_evidence or [],
                "deterministic_key": key,
            })

        for row in seed_rows:
            reason = eligibility(
                has_evidence=row["has_evidence"], confidence=float(row["confidence"]),
                minimum_confidence=policy.minimum_confidence,
            )
            if reason is not None:
                key = f"stop:{row['fact_id']}"
                add_finding(
                    key=key, rule_key="policy.stop-ineligible-edge", classification="STOP",
                    severity="INFO", title=f"Stopped before {row['name']}",
                    detail=(
                        f"The impact policy stopped this branch because the dependency has {reason}."
                    ),
                    affected_entity_id=row["id"], confidence=float(row["confidence"]),
                    evidence_fact_ids=[row["fact_id"]] if row["has_evidence"] else [],
                    path_entity_ids=[subject_id, row["id"]],
                    fact_payload={"stop_reason": reason, "policy_stage": "SEED"},
                )
                continue
            if len(eligible_rows) >= node_budget:
                limited = True
                if not any(item["code"] == "TRAVERSAL_BUDGET" for item in limitations):
                    limitations.append({
                        "code": "TRAVERSAL_BUDGET",
                        "message": "The node budget truncated the direct dependency set.",
                        "evidence_fact_ids": [],
                    })
                break
            eligible_rows.append(row)
            component = row["properties"].get("component_path")
            location = f" in {component}" if component else ""
            key = f"direct:{row['fact_id']}"
            add_finding(
                key=key, rule_key="package.direct-dependent",
                classification=policy.seed_classification, severity="MEDIUM",
                title=f"{row['name']} directly depends on {package_name}",
                detail=(
                    f"{row['name']}{location} moves from {row['current_version']} to "
                    f"{mutation.after['version']}. Validate its declared version constraint and tests."
                ),
                affected_entity_id=row["id"], confidence=float(row["confidence"]),
                evidence_fact_ids=[row["fact_id"]],
                path_entity_ids=[subject_id, row["id"]],
                fact_payload={
                    "before": row["current_version"], "after": mutation.after["version"],
                    "component_path": component, "source_revision": row["source_revision"],
                },
            )
            seeds.append(TraversedNode(
                entity_id=row["id"], entity_type=row["entity_type"], name=row["name"],
                canonical_key=row["canonical_key"], depth=1,
                classification=policy.seed_classification, weight=1.0,
                predicate="DEPENDS_ON", origin_id=subject_id, fact_id=row["fact_id"],
                confidence=float(row["confidence"]), path=(subject_id, row["id"]),
            ))

        traversal = ImpactTraversal(self.database, tenant_id=tenant_id, policy=policy)
        # The seeds are already counted inside the traversal's node budget, and the seed query
        # has already spent its share of the edge budget.
        walk = await traversal.expand(
            seeds,
            node_budget=node_budget,
            edge_budget=max(0, edge_budget - len(seed_rows)),
        )
        limited = limited or walk.truncated
        for limitation in walk.limitations:
            if not any(item["code"] == limitation["code"] for item in limitations):
                limitations.append(limitation)
        scanner_versions |= walk.scanner_versions

        for node in walk.nodes:
            if node.depth <= 1:
                continue  # the seed set already produced its own findings
            severity = _IMPACT_SEVERITY.get(node.classification, "LOW")
            key = f"{node.classification.lower()}:{node.predicate}:{node.fact_id}:{node.entity_id}"
            if node.classification == "TRANSITIVE":
                title = f"{node.name} is reached through {node.depth} evidence-backed hops"
                detail = (
                    f"The policy walked {node.predicate} to this {node.entity_type} at depth "
                    f"{node.depth}. It is affected through a dependent, not directly, so verify "
                    "it after the direct dependents are validated."
                )
                rule_key = "package.transitive-impact"
            else:
                title = f"{node.name} is in the affected estate context"
                detail = (
                    f"The {node.predicate} relationship connects this {node.entity_type} to an "
                    "evidence-backed impacted entity. It is contextual, not asserted as broken."
                )
                rule_key = "package.estate-context"
            add_finding(
                key=key, rule_key=rule_key, classification=node.classification,
                severity=severity, title=title, detail=detail,
                affected_entity_id=node.entity_id, confidence=node.confidence,
                evidence_fact_ids=[node.fact_id] if node.fact_id else [],
                path_entity_ids=list(node.path),
                fact_payload={
                    "relationship": node.predicate, "depth": node.depth,
                    "policy_weight": node.weight,
                    "overlay": {
                        "changed_subject_id": str(subject_id),
                        "target_version": mutation.after["version"],
                    },
                },
            )

        for branch in walk.stopped:
            key = f"stop:{branch.predicate}:{branch.fact_id}:{branch.entity_id}"
            add_finding(
                key=key, rule_key="policy.stop-ineligible-edge", classification="STOP",
                severity="INFO", title=f"Stopped before {branch.name}",
                detail=(
                    f"The impact policy stopped this branch at depth {branch.depth} because the "
                    f"{branch.predicate} relationship has {branch.reason}."
                ),
                affected_entity_id=branch.entity_id, confidence=branch.confidence,
                evidence_fact_ids=[branch.fact_id] if branch.fact_id else [],
                path_entity_ids=list(branch.path),
                fact_payload={
                    "relationship": branch.predicate, "stop_reason": branch.reason,
                    "depth": branch.depth, "policy_stage": "TRAVERSAL",
                },
            )

        capability_limitations, capability_summary = await self._capability_findings(
            traversal=traversal, walk=walk, policy=policy,
            subject_id=subject_id, add_finding=add_finding, limit=node_budget,
        )
        limitations.extend(capability_limitations)

        await self._change_memory_finding(
            tenant_id=tenant_id, mutation=mutation, scope=scope,
            subject_id=subject_id, add_finding=add_finding,
        )

        distribution_key = "informational:version-spread"
        add_finding(
            key=distribution_key, rule_key="package.version-spread",
            classification="INFORMATIONAL", severity="INFO",
            title="Version spread after the proposed change",
            detail=(
                f"The selected scope converges {len(eligible_rows)} evidence-backed dependencies "
                f"to {mutation.after['version']}; stopped branches remain unchanged."
            ),
            affected_entity_id=subject_id, confidence=1,
            evidence_fact_ids=sorted({row["fact_id"] for row in eligible_rows}, key=str),
            path_entity_ids=[subject_id],
            fact_payload={
                "now": mutation.before["versions"],
                "simulated": [{"version": mutation.after["version"], "count": len(eligible_rows)}],
                "unchanged": len(seed_rows) - len(eligible_rows),
                "transitive": len(walk.by_classification("TRANSITIVE")),
                "context": len(walk.by_classification("CONTEXT")),
                "capabilities": capability_summary,
            },
        )

        if not eligible_rows:
            limitations.append({
                "code": "NO_ELIGIBLE_IMPACT_PATH",
                "message": "No current dependency path met the policy's evidence and confidence thresholds.",
                "evidence_fact_ids": [row["fact_id"] for row in seed_rows if row["has_evidence"]],
            })
        return {
            "findings": findings,
            "limitations": limitations,
            "scanner_versions": scanner_versions,
            "limited": limited,
            "eligible": len(eligible_rows),
        }

    async def _seed_dependents(
        self, *, tenant_id: UUID, package_name: str, scope: Any,
        subject_types: frozenset[str], limit: int,
    ) -> list[dict[str, Any]]:
        """Resolve the mutation subject to the estate entities that declare it.

        This is the one predicate-specific step. Everything after it is decided by the policy,
        which is what lets a second predicate arrive as a new seed plus a policy row rather
        than as a second traversal implementation.
        """
        params: list[Any] = [tenant_id, package_name, sorted(subject_types)]
        scope_sql = ""
        if scope.kind in {"REPOSITORY", "COMPONENT"}:
            scope_sql += " AND f.subject_entity_id=%s"
            params.append(scope.entity_id)
        if scope.kind == "COMPONENT":
            scope_sql += " AND coalesce(f.properties->>'component_path','')=%s"
            params.append(scope.component_path)
        params.append(limit)
        return await self.database.fetch_all(
            f"""
            SELECT f.id fact_id,f.confidence,f.assertion_class,f.source_revision,f.extractor_key,
                   f.extractor_version,f.properties,consumer.id,consumer.entity_type,consumer.name,
                   consumer.canonical_key,coalesce(dr.resolved_version,pri.package_version,
                     f.properties->>'resolved_version',f.properties->>'requested_spec','unknown') current_version,
                   EXISTS(SELECT 1 FROM evidence ev WHERE ev.fact_assertion_id=f.id) has_evidence
            FROM fact_assertion f
            JOIN entity consumer ON consumer.id=f.subject_entity_id
            JOIN package_registry_identity pri ON pri.entity_id=f.object_entity_id
            LEFT JOIN dependency_resolution dr ON dr.fact_assertion_id=f.id
            WHERE f.tenant_id=%s AND lower(pri.package_name)=lower(%s)
              AND f.predicate='DEPENDS_ON' AND f.system_to IS NULL
              AND consumer.entity_type=ANY(%s::text[]) {scope_sql}
            ORDER BY consumer.canonical_key,f.properties->>'component_path',f.id
            LIMIT %s
            """,
            tuple(params), tenant_id=tenant_id,
        )

    async def _capability_findings(
        self, *, traversal: ImpactTraversal, walk: Any, policy: ImpactPolicyConfiguration,
        subject_id: UUID, add_finding: Any, limit: int,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """Join reached applications to the curated business capability map.

        §22 and the §44 demo both insist the headline is business impact, not a repository
        count. The relationship is curated rather than observed, so it is cited as curated
        provenance and every finding says so in its own detail text.
        """
        summary = {"count": 0, "tier_zero": 0, "collected": False}
        if policy.capability_rule is None:
            return [], summary
        rule = policy.capability_rule
        application_ids = [
            node.entity_id for node in walk.nodes
            if node.entity_type in rule.from_types and node.depth <= rule.max_depth
        ]
        if not application_ids:
            return [{
                "code": "NO_BUSINESS_CAPABILITY_PATH",
                "message": (
                    "No application was reached within the policy's depth bound, so business "
                    "capability impact could not be evaluated."
                ),
                "evidence_fact_ids": [],
            }], summary
        rows = await traversal.capabilities(application_ids, limit=limit)
        if not rows:
            return [{
                "code": "BUSINESS_CAPABILITY_NOT_MAPPED",
                "message": (
                    "The reached applications are not assigned to any capability on the current "
                    "business map, so business impact is unknown rather than absent."
                ),
                "evidence_fact_ids": [],
            }], summary
        by_capability: dict[UUID, list[dict[str, Any]]] = {}
        for row in rows:
            by_capability.setdefault(row["capability_entity_id"], []).append(row)
        tier_zero = 0
        for capability_id in sorted(by_capability, key=str):
            group = by_capability[capability_id]
            first = group[0]
            criticality = int(first["criticality"])
            is_tier_zero = criticality <= rule.tier_zero_criticality
            tier_zero += 1 if is_tier_zero else 0
            key = f"capability:{capability_id}"
            add_finding(
                key=key, rule_key="capability.business-impact",
                classification=rule.classification,
                severity="HIGH" if is_tier_zero else "MEDIUM",
                title=(
                    f"{first['name']} is affected"
                    + (" (Tier-0 capability)" if is_tier_zero else f" (criticality {criticality})")
                ),
                detail=(
                    f"{len(group)} affected application(s) deliver this capability. The "
                    "capability-to-application assignment is curated on the business map, not "
                    "observed from code, so it carries the map revision as its provenance."
                ),
                affected_entity_id=capability_id, confidence=float(first["confidence"]),
                evidence_fact_ids=[],
                path_entity_ids=[subject_id, first["application_entity_id"], capability_id],
                fact_payload={
                    "criticality": criticality,
                    "tier_zero": is_tier_zero,
                    "affected_application_ids": sorted(
                        {str(item["application_entity_id"]) for item in group}
                    ),
                    "provenance_kind": "CURATED_BUSINESS_MAP",
                },
                curated_evidence=[{
                    "kind": "BUSINESS_MAP_REVISION",
                    "business_map_id": str(first["business_map_id"]),
                    "revision_id": str(first["evidence_revision_id"]),
                    "analysis_fingerprint": first["analysis_fingerprint"],
                }],
            )
        summary = {"count": len(by_capability), "tier_zero": tier_zero, "collected": True}
        return [], summary

    async def _change_memory_finding(
        self, *, tenant_id: UUID, mutation: Any, scope: Any,
        subject_id: UUID, add_finding: Any,
    ) -> None:
        history_rows = await self.database.fetch_all(
            """
            SELECT id,success,intervention_required,rolled_back,confidence,
                   evidence_fact_ids,observed_impact,unexpected_impact,observed_at
            FROM observed_mutation
            WHERE tenant_id=%s AND predicate=%s AND subject_entity_id=%s
              AND success IS NOT NULL AND confidence>=0.8
              AND scope->>'kind'=%s
            ORDER BY observed_at DESC,id DESC LIMIT 50
            """,
            (tenant_id, mutation.predicate, subject_id, scope.kind),
            tenant_id=tenant_id,
        )
        if len(history_rows) < 3:
            return
        successes = sum(bool(row["success"]) for row in history_rows)
        rollbacks = sum(bool(row["rolled_back"]) for row in history_rows)
        interventions = sum(bool(row["intervention_required"]) for row in history_rows)
        add_finding(
            key="informational:qualified-change-memory",
            rule_key="change-memory.qualified-outcomes", classification="INFORMATIONAL",
            severity="INFO", title=f"{len(history_rows)} comparable observed changes",
            detail=(
                "Organization-specific history is reported as a bounded sample, not as a "
                "guarantee. Review cited outcomes and coverage before using it as a predictor."
            ),
            affected_entity_id=subject_id,
            confidence=min(float(row["confidence"]) for row in history_rows),
            evidence_fact_ids=sorted({
                fact_id for row in history_rows for fact_id in row["evidence_fact_ids"]
            }, key=str),
            path_entity_ids=[subject_id],
            fact_payload={
                "sample_size": len(history_rows), "successes": successes,
                "rollbacks": rollbacks, "interventions": interventions,
                "success_rate": round(successes / len(history_rows), 4),
                "rollback_rate": round(rollbacks / len(history_rows), 4),
                "bias_and_coverage_limitations": [
                    "only explicitly correlated outcomes with confidence at least 0.80 are included",
                    "historical association is not causal and may not transfer to the current estate",
                ],
                "outcome_ids": [str(row["id"]) for row in history_rows],
            },
        )

    async def _interpret_simulation(
        self, *, run_id: UUID, tenant_id: UUID, findings: list[dict[str, Any]],
    ) -> None:
        """Produce the AI interpretation partition, or record why there is none.

        §14 puts a hard line between deterministic findings and interpretation: the engine
        establishes the facts, AI explains them, and AI may not manufacture the impact graph.
        That line is enforced here rather than trusted to the prompt — every claim must cite a
        finding this run actually produced, and output that cites nothing is quarantined into
        its own column where it stays visible but cannot influence risk or the gate.

        Deterministic findings are already committed when this runs, so every failure path
        below leaves them complete and unchanged. That is M2's exit gate.
        """
        enabled = await self.phase2_feature_enabled("AI_INTERPRETATION", tenant_id=tenant_id)
        if not enabled or self.ai is None:
            await self._record_interpretation(
                run_id=run_id, tenant_id=tenant_id, status="UNAVAILABLE",
                limitation=(
                    "AI interpretation is disabled; deterministic findings are complete and unchanged."
                    if not enabled else
                    "No AI provider is configured; deterministic findings are complete and unchanged."
                ),
            )
            return

        finding_ids = {str(finding["id"]) for finding in findings}
        payload = [{
            "id": str(finding["id"]),
            "classification": finding["classification"],
            "severity": finding["severity"],
            "rule_key": finding["rule_key"],
            "title": finding["title"],
            "detail": finding["detail"],
            "confidence": float(finding["confidence"]),
            "provenance_kind": finding["fact_payload"].get("provenance_kind", "OBSERVED_FACT"),
        } for finding in findings]
        try:
            async with asyncio.timeout(_INTERPRETATION_TIMEOUT_SECONDS):
                invocation = await self.ai.invoke(
                    "simulation.interpret",
                    {
                        "mutation": json.dumps(
                            {"run_id": str(run_id)}, sort_keys=True,
                        ),
                        "findings": json.dumps(payload, sort_keys=True),
                    },
                    tenant_id=tenant_id,
                    metadata={"simulation_run_id": str(run_id)},
                )
        except Exception as error:
            # An interpretation outage is not a simulation failure. §9.3 requires the
            # deterministic result to stay available and say that interpretation did not.
            await self._record_interpretation(
                run_id=run_id, tenant_id=tenant_id, status="UNAVAILABLE",
                limitation=(
                    f"AI interpretation did not complete ({type(error).__name__}); "
                    "deterministic findings are complete and unchanged."
                ),
            )
            return

        output = getattr(invocation, "output", None)
        if not isinstance(output, dict):
            await self._record_interpretation(
                run_id=run_id, tenant_id=tenant_id, status="UNAVAILABLE",
                limitation=(
                    "AI interpretation returned no structured output; deterministic findings "
                    "are complete and unchanged."
                ),
            )
            return

        cited = [
            value for value in output.get("cited_finding_ids") or []
            if str(value) in finding_ids
        ]
        invented = sorted(
            str(value) for value in output.get("cited_finding_ids") or []
            if str(value) not in finding_ids
        )
        quarantined: list[dict[str, Any]] = []
        if invented:
            quarantined.append({
                "reason": "CITED_UNKNOWN_FINDING",
                "detail": "The interpretation cited finding IDs this run did not produce.",
                "values": invented,
            })
        if not cited:
            quarantined.append({
                "reason": "UNCITED_OUTPUT",
                "detail": "The interpretation cited no finding from this run.",
                "values": [str(output.get("explanation") or "")[:2000]],
            })

        if quarantined:
            await self._record_interpretation(
                run_id=run_id, tenant_id=tenant_id, status="QUARANTINED",
                limitation=(
                    "Interpretation output could not be grounded in this run's findings and is "
                    "quarantined. It does not affect risk, the gate, or any deterministic result."
                ),
                quarantined_claims=quarantined,
                provider=getattr(invocation, "provider", None),
                model=getattr(invocation, "model", None),
                prompt_version=getattr(invocation, "prompt_version", None),
            )
            return

        await self._record_interpretation(
            run_id=run_id, tenant_id=tenant_id, status="AVAILABLE",
            risk=str(output.get("risk") or "") or None,
            explanation=str(output.get("explanation") or "") or None,
            rollout=[str(item) for item in output.get("rollout") or []],
            remediation=[str(item) for item in output.get("remediation") or []],
            verification=[str(item) for item in output.get("verification") or []],
            cited_finding_ids=[UUID(str(value)) for value in cited],
            provider=getattr(invocation, "provider", None),
            model=getattr(invocation, "model", None),
            prompt_version=getattr(invocation, "prompt_version", None),
            limitation=(
                None if len(cited) == len(findings)
                else "Interpretation does not cite every finding. Uncited findings remain visible and authoritative."
            ),
        )

    async def _record_interpretation(
        self, *, run_id: UUID, tenant_id: UUID, status: str,
        risk: str | None = None, explanation: str | None = None,
        rollout: list[str] | None = None, remediation: list[str] | None = None,
        verification: list[str] | None = None, cited_finding_ids: list[UUID] | None = None,
        limitation: str | None = None, quarantined_claims: list[dict[str, Any]] | None = None,
        provider: str | None = None, model: str | None = None, prompt_version: str | None = None,
    ) -> None:
        async with self.database.session(tenant_id) as connection:
            await connection.execute(
                """
                INSERT INTO simulation_interpretation(
                  tenant_id,simulation_run_id,status,provider,model,prompt_version,risk,
                  explanation,rollout,remediation,verification,cited_finding_ids,limitation,
                  quarantined_claims
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT(simulation_run_id) DO NOTHING
                """,
                (
                    tenant_id, run_id, status, provider, model, prompt_version, risk,
                    explanation, Jsonb(rollout or []), Jsonb(remediation or []),
                    Jsonb(verification or []), cited_finding_ids or [], limitation,
                    Jsonb(quarantined_claims or []),
                ),
            )
