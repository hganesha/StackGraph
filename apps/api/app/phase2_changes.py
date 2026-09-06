from __future__ import annotations

import hashlib
import asyncio
import json
import re
import socket
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4, uuid5

from psycopg.types.json import Jsonb

from app.errors import APIError
from app.models import (
    ActionSubject,
    ActionSubjectList,
    ActionTypeList,
    ActionTypeSummary,
    ChangeGate,
    ChangeScope,
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
    SimulationInterpretation,
    SimulationRunModel,
    ValidTarget,
    ValidTargetList,
    VersionDistribution,
)


ONTOLOGY_VERSION = "actions/1.0.0"
RESOLUTION_VERSION = "identity-resolution/1.0.0"
PROVIDER_VERSION = "package-registry/1.0.0"
POLICY_KEY = "upgrade-package"
_SIMULATION_NAMESPACE = UUID("fd4ecf06-230c-4d15-a65a-04a967c6487f")
_INTENT = re.compile(
    r"^\s*upgrade\s+(?P<subject>.+?)\s+to\s+(?P<target>[^\s]+)(?:\s+(?:in|within)\s+(?P<scope>.+))?\s*$",
    re.IGNORECASE,
)


def _fingerprint(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return "sha256:" + hashlib.sha256(payload.encode()).hexdigest()


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


def _clear_gate() -> ChangeGate:
    return ChangeGate(state="CLEAR", reasons=[])


class Phase2ChangeMixin:
    """Tenant-safe compiler and deterministic simulation read/write model.

    Natural language is accepted only by the bounded lexical parser above. The
    simulator consumes persisted Mutation IR, never the original command text.
    """

    database: Any

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
                "enabled": row["lifecycle"] == "ACTIVE", "lifecycle": row["lifecycle"],
                "ontology_version": row["ontology_version"],
            })
            item["subject_types"].append(row["subject_type"])
            item["enabled"] = item["enabled"] and row["lifecycle"] == "ACTIVE"
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
            SELECT outcome.*,entity.entity_type,entity.name,entity.canonical_key
            FROM observed_mutation outcome JOIN entity ON entity.id=outcome.subject_entity_id
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
            SELECT outcome.*,entity.entity_type,entity.name,entity.canonical_key
            FROM observed_mutation outcome JOIN entity ON entity.id=outcome.subject_entity_id
            WHERE outcome.subject_entity_id=%s
            ORDER BY outcome.observed_at DESC,outcome.id DESC LIMIT %s
            """,
            (subject_id, limit + 1), tenant_id=tenant_id,
        )
        return ObservedMutationList(
            subject=_entity(subject), outcomes=[self._observed_mutation(row) for row in rows[:limit]],
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
        resolution, package_name = await self._package_resolution(
            tenant_id=tenant_id, subject_id=entity_id, query=None,
        )
        if resolution.state != "RESOLVED" or package_name is None or resolution.entity is None:
            raise APIError(404, "PACKAGE_NOT_RESOLVED", "The package does not have a canonical registry identity.")
        rows = await self.database.fetch_all(
            """
            SELECT e.id,e.canonical_key,pri.package_version,
                   coalesce(pri.last_seen_at,pri.first_seen_at,e.updated_at) observed_at,
                   registry.registry_key
            FROM package_registry_identity pri
            JOIN package_registry registry ON registry.id=pri.package_registry_id
            JOIN entity e ON e.id=pri.entity_id
            WHERE lower(pri.package_name)=lower(%s) AND pri.package_version IS NOT NULL
            """,
            (package_name,), tenant_id=tenant_id,
        )
        rows.sort(key=lambda row: _version_key(row["package_version"]), reverse=True)
        targets = [ValidTarget(
            entity_id=row["id"], version=row["package_version"], canonical_key=row["canonical_key"],
            source=row["registry_key"], observed_at=row["observed_at"],
            freshness=_freshness(row["observed_at"]), support="UNKNOWN",
        ) for row in rows[:limit]]
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
        return ValidTargetList(
            subject=resolution.entity, targets=targets, policy_version=PROVIDER_VERSION,
            page_info=PageInfo(has_next_page=len(rows) > limit), limitations=limitations,
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

    async def compile_mutation(
        self, request: MutationCompileRequest, *, tenant_id: UUID | None, actor_key: str,
        provenance: dict[str, Any] | None = None,
    ) -> MutationCompileResult:
        if tenant_id is None:
            raise APIError(400, "TENANT_REQUIRED", "A tenant is required to compile a change.")
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
        if predicate != "UPGRADE":
            errors.append(MutationValidationError(
                code="ACTION_NOT_ENABLED", field="predicate",
                message=f"{predicate} is in the ontology but is not enabled for deterministic compilation.",
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
        after = {"version": target.version, "target_entity_id": str(target.entity_id)} if target else {}
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
        if errors:
            for error in errors:
                if error and not any(reason.code == error.code for reason in reasons):
                    reasons.append(GateReason(
                        code=error.code, message=error.message,
                        evidence_fact_ids=error.evidence_fact_ids,
                    ))
            result = MutationCompileResult(
                command_state="TOKENISED" if resolution.state != "UNRESOLVED" else "RESOLVING",
                draft=mutation, gate=ChangeGate(state="BLOCKED", reasons=reasons),
            )
            await self._audit_change(
                tenant_id=tenant_id, actor_key=actor_key, action="change_set.compile_blocked",
                target_kind="mutation_draft", target_id=mutation.input_fingerprint,
                detail={
                    "predicate": predicate,
                    "reason_codes": [reason.code for reason in reasons],
                    "entry_point": mutation.provenance["entry_point"],
                },
            )
            return result
        change_fingerprint = _fingerprint({"atomic": True, "mutations": [mutation_fingerprint]})
        async with self.database.session(tenant_id) as connection:
            existing_cursor = await connection.execute(
                """
                SELECT id,input_fingerprint,idempotency_key,created_at
                FROM change_set
                WHERE tenant_id=%s AND (idempotency_key=%s OR input_fingerprint=%s)
                ORDER BY (idempotency_key=%s) DESC
                LIMIT 1
                """,
                (tenant_id, request.idempotency_key, change_fingerprint, request.idempotency_key),
            )
            existing = await existing_cursor.fetchone()
            if (
                existing
                and existing["idempotency_key"] == request.idempotency_key
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
                    "SELECT id FROM mutation WHERE change_set_id=%s ORDER BY ordinal LIMIT 1",
                    (change_set_id,),
                )
                mutation_row = await mutation_cursor.fetchone()
                assert mutation_row is not None
                mutation.id = mutation_row["id"]
            else:
                change_set_id = uuid4()
                created_at = datetime.now(UTC)
                mutation.id = uuid4()
                await connection.execute(
                    """
                    INSERT INTO change_set(
                      id,tenant_id,lifecycle,input_fingerprint,idempotency_key,provenance,created_by,created_at
                    ) VALUES (%s,%s,'VALIDATED',%s,%s,%s,%s,%s)
                    """,
                    (
                        change_set_id, tenant_id, change_fingerprint, request.idempotency_key,
                        Jsonb(mutation.provenance), actor_key, created_at,
                    ),
                )
                await connection.execute(
                    """
                    INSERT INTO mutation(
                      id,tenant_id,change_set_id,ordinal,predicate,subject_entity_id,subject_resolution,
                      before_state,after_state,scope,constraints,provenance,input_fingerprint,lifecycle
                    ) VALUES (%s,%s,%s,0,%s,%s,'RESOLVED',%s,%s,%s,%s,%s,%s,'VALIDATED')
                    """,
                    (
                        mutation.id, tenant_id, change_set_id, predicate, resolution.entity.id,
                        Jsonb(before), Jsonb(after), Jsonb(selected_scope.model_dump(mode="json")),
                        Jsonb(mutation.constraints), Jsonb(mutation.provenance), mutation_fingerprint,
                    ),
                )
        change_set = ChangeSetModel(
            id=change_set_id, mutations=[mutation], lifecycle="VALIDATED",
            input_fingerprint=change_fingerprint, created_at=created_at,
        )
        result = MutationCompileResult(
            command_state="COMPILED", change_set=change_set, draft=mutation,
            gate=_clear_gate(), replayed=replayed,
        )
        await self._audit_change(
            tenant_id=tenant_id, actor_key=actor_key, action="change_set.compile",
            target_kind="change_set", target_id=str(change_set_id),
            detail={"predicate": predicate, "replayed": replayed,
                    "entry_point": mutation.provenance["entry_point"]},
        )
        return result

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
            verification=interpretation_row["verification"],
            cited_finding_ids=interpretation_row["cited_finding_ids"],
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
        tenant_id = run["tenant_id"]
        change_set = await self._load_change_set(run["change_set_id"], tenant_id=tenant_id)
        mutation = change_set.mutations[0]
        if mutation.subject.entity is None or mutation.scope is None:
            raise RuntimeError("persisted mutation is missing canonical identity or scope")
        _, package_name = await self._package_resolution(
            tenant_id=tenant_id, subject_id=mutation.subject.entity.id, query=None,
        )
        if package_name is None:
            raise RuntimeError("persisted package identity no longer resolves")
        scope = mutation.scope
        params: list[Any] = [tenant_id, package_name]
        scope_sql = ""
        if scope.kind in {"REPOSITORY", "COMPONENT"}:
            scope_sql += " AND f.subject_entity_id=%s"
            params.append(scope.entity_id)
        if scope.kind == "COMPONENT":
            scope_sql += " AND coalesce(f.properties->>'component_path','')=%s"
            params.append(scope.component_path)
        rows = await self.database.fetch_all(
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
              AND consumer.entity_type='Repository' {scope_sql}
            ORDER BY consumer.canonical_key,f.properties->>'component_path',f.id
            LIMIT %s
            """,
            (*params, max_edges + 1), tenant_id=tenant_id,
        )
        limitations: list[dict[str, Any]] = []
        limited = len(rows) > max_edges
        rows = rows[:max_edges]
        if limited:
            limitations.append({
                "code": "TRAVERSAL_BUDGET", "message": "The edge budget truncated the simulation.",
                "evidence_fact_ids": [],
            })
        findings: list[dict[str, Any]] = []
        scanner_versions = sorted({f"{row['extractor_key']}/{row['extractor_version']}" for row in rows})
        eligible = [row for row in rows if row["has_evidence"] and float(row["confidence"]) >= 0.8]
        excluded = [row for row in rows if row not in eligible]
        for row in eligible[:max_nodes]:
            component = row["properties"].get("component_path")
            location = f" in {component}" if component else ""
            key = f"direct:{row['fact_id']}"
            findings.append({
                "id": uuid5(_SIMULATION_NAMESPACE, f"{run['id']}:{key}"),
                "rule_key": "package.direct-dependent", "rule_version": "1.0.0",
                "classification": "DIRECT", "severity": "MEDIUM",
                "title": f"{row['name']} directly depends on {package_name}",
                "detail": (
                    f"{row['name']}{location} moves from {row['current_version']} to "
                    f"{mutation.after['version']}. Validate its declared version constraint and tests."
                ),
                "affected_entity_id": row["id"], "confidence": float(row["confidence"]),
                "evidence_fact_ids": [row["fact_id"]],
                "path_entity_ids": [mutation.subject.entity.id, row["id"]],
                "fact_payload": {
                    "before": row["current_version"], "after": mutation.after["version"],
                    "component_path": component, "source_revision": row["source_revision"],
                },
                "deterministic_key": key,
            })
        if len(eligible) > max_nodes:
            limited = True
            limitations.append({
                "code": "TRAVERSAL_BUDGET", "message": "The node budget truncated the simulation.",
                "evidence_fact_ids": [],
            })
        for row in excluded:
            key = f"stop:{row['fact_id']}"
            reason = "missing evidence" if not row["has_evidence"] else "confidence below 0.80"
            findings.append({
                "id": uuid5(_SIMULATION_NAMESPACE, f"{run['id']}:{key}"),
                "rule_key": "policy.stop-ineligible-edge", "rule_version": "1.0.0",
                "classification": "STOP", "severity": "INFO",
                "title": f"Stopped before {row['name']}",
                "detail": f"The impact policy stopped this branch because the dependency has {reason}.",
                "affected_entity_id": row["id"], "confidence": float(row["confidence"]),
                "evidence_fact_ids": [row["fact_id"]] if row["has_evidence"] else [],
                "path_entity_ids": [mutation.subject.entity.id, row["id"]],
                "fact_payload": {"stop_reason": reason}, "deterministic_key": key,
            })
        impacted_repository_ids = sorted({row["id"] for row in eligible}, key=str)
        context_rows: list[dict[str, Any]] = []
        if impacted_repository_ids and len(findings) < max_nodes:
            context_rows = await self.database.fetch_all(
                """
                SELECT relationship.id fact_id,relationship.predicate,relationship.confidence,
                       relationship.extractor_key,relationship.extractor_version,
                       related.id,related.entity_type,related.name,related.canonical_key,
                       EXISTS(SELECT 1 FROM evidence WHERE fact_assertion_id=relationship.id) has_evidence,
                       repository.id repository_id
                FROM fact_assertion relationship
                JOIN entity repository ON repository.id=ANY(%s::uuid[])
                JOIN entity related ON related.id=CASE
                  WHEN relationship.object_entity_id=repository.id THEN relationship.subject_entity_id
                  ELSE relationship.object_entity_id END
                WHERE relationship.tenant_id=%s AND relationship.system_to IS NULL
                  AND (
                    (relationship.object_entity_id=repository.id
                     AND relationship.predicate IN ('IMPLEMENTED_BY'))
                    OR
                    (relationship.subject_entity_id=repository.id
                     AND relationship.predicate IN ('CONTAINS','DEPLOYED_AS','USES'))
                  )
                ORDER BY repository.canonical_key,relationship.predicate,related.canonical_key,
                         relationship.id
                LIMIT %s
                """,
                (impacted_repository_ids, tenant_id, max_edges + 1), tenant_id=tenant_id,
            )
            if len(context_rows) > max_edges:
                context_rows = context_rows[:max_edges]
                limited = True
                limitations.append({
                    "code": "TRAVERSAL_BUDGET",
                    "message": "The context-edge budget truncated the simulation.",
                    "evidence_fact_ids": [],
                })
        scanner_versions = sorted({
            *scanner_versions,
            *(f"{row['extractor_key']}/{row['extractor_version']}" for row in context_rows),
        })
        context_seen: set[tuple[UUID, str]] = set()
        remaining_nodes = max(0, max_nodes - len(eligible))
        for row in context_rows:
            dedupe_key = (row["id"], row["predicate"])
            if dedupe_key in context_seen:
                continue
            context_seen.add(dedupe_key)
            if len(context_seen) > remaining_nodes:
                limited = True
                limitations.append({
                    "code": "TRAVERSAL_BUDGET",
                    "message": "The context-node budget truncated the simulation.",
                    "evidence_fact_ids": [],
                })
                break
            confidence = float(row["confidence"])
            eligible_context = row["has_evidence"] and confidence >= 0.8
            classification = "CONTEXT" if eligible_context else "STOP"
            key = f"{classification.lower()}:context:{row['fact_id']}:{row['id']}"
            if eligible_context:
                title = f"{row['name']} is in the affected repository context"
                detail = (
                    f"The {row['predicate']} relationship connects this {row['entity_type']} to an "
                    "evidence-backed direct dependent. It is contextual, not asserted as directly broken."
                )
                rule_key = "package.repository-context"
                fact_payload = {
                    "relationship": row["predicate"],
                    "overlay": {
                        "changed_subject_id": str(mutation.subject.entity.id),
                        "target_version": mutation.after["version"],
                        "authoritative_facts_unchanged": True,
                    },
                }
            else:
                reason = "missing evidence" if not row["has_evidence"] else "confidence below 0.80"
                title = f"Stopped before contextual {row['name']}"
                detail = f"The impact policy stopped this branch because the relationship has {reason}."
                rule_key = "policy.stop-ineligible-edge"
                fact_payload = {"relationship": row["predicate"], "stop_reason": reason}
            findings.append({
                "id": uuid5(_SIMULATION_NAMESPACE, f"{run['id']}:{key}"),
                "rule_key": rule_key, "rule_version": "1.0.0",
                "classification": classification, "severity": "LOW" if eligible_context else "INFO",
                "title": title, "detail": detail, "affected_entity_id": row["id"],
                "confidence": confidence,
                "evidence_fact_ids": [row["fact_id"]] if row["has_evidence"] else [],
                "path_entity_ids": [mutation.subject.entity.id, row["repository_id"], row["id"]],
                "fact_payload": fact_payload, "deterministic_key": key,
            })
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
            (tenant_id, mutation.predicate, mutation.subject.entity.id, scope.kind),
            tenant_id=tenant_id,
        )
        if len(history_rows) >= 3:
            historical_key = "informational:qualified-change-memory"
            successes = sum(bool(row["success"]) for row in history_rows)
            rollbacks = sum(bool(row["rolled_back"]) for row in history_rows)
            interventions = sum(bool(row["intervention_required"]) for row in history_rows)
            findings.append({
                "id": uuid5(_SIMULATION_NAMESPACE, f"{run['id']}:{historical_key}"),
                "rule_key": "change-memory.qualified-outcomes", "rule_version": "1.0.0",
                "classification": "INFORMATIONAL", "severity": "INFO",
                "title": f"{len(history_rows)} comparable observed changes",
                "detail": (
                    "Organization-specific history is reported as a bounded sample, not as a "
                    "guarantee. Review cited outcomes and coverage before using it as a predictor."
                ),
                "affected_entity_id": mutation.subject.entity.id,
                "confidence": min(float(row["confidence"]) for row in history_rows),
                "evidence_fact_ids": sorted({
                    fact_id for row in history_rows for fact_id in row["evidence_fact_ids"]
                }, key=str),
                "path_entity_ids": [mutation.subject.entity.id],
                "fact_payload": {
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
                "deterministic_key": historical_key,
            })
        distribution_key = "informational:version-spread"
        findings.append({
            "id": uuid5(_SIMULATION_NAMESPACE, f"{run['id']}:{distribution_key}"),
            "rule_key": "package.version-spread", "rule_version": "1.0.0",
            "classification": "INFORMATIONAL", "severity": "INFO",
            "title": "Version spread after the proposed change",
            "detail": (
                f"The selected scope converges {len(eligible)} evidence-backed dependencies to "
                f"{mutation.after['version']}; stopped branches remain unchanged."
            ),
            "affected_entity_id": mutation.subject.entity.id, "confidence": 1,
            "evidence_fact_ids": sorted({value for row in eligible for value in [row["fact_id"]]}, key=str),
            "path_entity_ids": [mutation.subject.entity.id],
            "fact_payload": {
                "now": mutation.before["versions"],
                "simulated": [{"version": mutation.after["version"], "count": len(eligible)}],
                "unchanged": len(excluded),
            },
            "deterministic_key": distribution_key,
        })
        if not eligible:
            limitations.append({
                "code": "NO_ELIGIBLE_IMPACT_PATH",
                "message": "No current dependency path met the policy's evidence and confidence thresholds.",
                "evidence_fact_ids": [row["fact_id"] for row in rows if row["has_evidence"]],
            })
            status = "NOT_SIMULATABLE"
        else:
            status = "LIMITED" if limited else "SUCCEEDED"
        canonical_result = [{
            key: (str(value) if isinstance(value, UUID) else value)
            for key, value in finding.items() if key not in {"id"}
        } for finding in findings]
        result_hash = _fingerprint({
            "change_set": change_set.input_fingerprint,
            "estate_watermark": run["estate_watermark"], "policy": run["policy_version"],
            "findings": canonical_result, "limitations": limitations,
        })
        async with self.database.session(tenant_id) as connection:
            for finding in findings:
                await connection.execute(
                    """
                    INSERT INTO simulation_finding(
                      id,tenant_id,simulation_run_id,rule_key,rule_version,classification,severity,
                      title,detail,affected_entity_id,confidence,evidence_fact_ids,path_entity_ids,
                      fact_payload,deterministic_key
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT(simulation_run_id,deterministic_key) DO NOTHING
                    """,
                    (
                        finding["id"], tenant_id, run["id"], finding["rule_key"],
                        finding["rule_version"], finding["classification"], finding["severity"],
                        finding["title"], finding["detail"], finding["affected_entity_id"],
                        finding["confidence"], finding["evidence_fact_ids"], finding["path_entity_ids"],
                        Jsonb(finding["fact_payload"]), finding["deterministic_key"],
                    ),
                )
            await connection.execute(
                """
                INSERT INTO simulation_interpretation(
                  tenant_id,simulation_run_id,status,limitation
                ) VALUES (%s,%s,'UNAVAILABLE',%s)
                ON CONFLICT(simulation_run_id) DO NOTHING
                """,
                (
                    tenant_id, run["id"],
                    "AI interpretation is disabled; deterministic findings are complete and unchanged.",
                ),
            )
            await connection.execute(
                """
                UPDATE simulation_run SET status=%s,result_hash=%s,limitations=%s,
                  scanner_versions=%s,completed_at=now(),leased_by=NULL,leased_until=NULL,updated_at=now()
                WHERE id=%s
                """,
                (status, result_hash, Jsonb(limitations), scanner_versions, run["id"]),
            )
