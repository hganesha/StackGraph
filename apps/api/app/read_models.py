from __future__ import annotations

import base64
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from app.database import Database
from app.errors import APIError
from app.models import (
    ApplicationDetail,
    AskRequest,
    AskResponse,
    AssessmentSummary,
    Citation,
    Coverage,
    EntitySummary,
    EstateCounts,
    EstateSummary,
    EvidenceDetail,
    Extractor,
    Freshness,
    GraphEdge,
    GraphNeighborhood,
    GraphNode,
    IdentityReviewRequest,
    IdentityReviewResult,
    InternalUsage,
    ModernizationList,
    PackageSource,
    PageInfo,
    RankedItem,
    RecommendationSummary,
    Score,
    TechnologyDetail,
)


CONTRACT_VERSION = "1.0.0"


def _number(value: Decimal | float | int | None, default: float = 0.0) -> float:
    return float(value) if value is not None else default


def _confidence_label(value: Decimal | float) -> str:
    confidence = float(value)
    if confidence >= 0.8:
        return "HIGH"
    if confidence >= 0.5:
        return "MEDIUM"
    return "LOW"


def _freshness(observed_at: datetime | None, source_key: str | None = None) -> Freshness:
    timestamp = observed_at or datetime.now(UTC)
    if observed_at is None:
        status = "UNKNOWN"
    elif datetime.now(UTC) - observed_at <= timedelta(days=7):
        status = "FRESH"
    else:
        status = "STALE"
    return Freshness(observed_at=timestamp, status=status, source_key=source_key)


def _entity(row: dict[str, Any]) -> EntitySummary:
    summary = row.get("summary")
    if summary is None and isinstance(row.get("properties"), dict):
        summary = row["properties"].get("purpose") or row["properties"].get("definition")
    return EntitySummary(
        id=row["id"],
        kind=row["entity_type"],
        name=row["name"],
        canonical_key=row.get("canonical_key"),
        summary=summary,
    )


def _encode_cursor(offset: int) -> str:
    payload = json.dumps({"offset": offset}, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def _decode_cursor(cursor: str | None) -> int:
    if cursor is None:
        return 0
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded).decode())
        offset = int(payload["offset"])
        if offset < 0:
            raise ValueError
        return offset
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        raise APIError(400, "INVALID_CURSOR", "The pagination cursor is invalid.") from error


class ReadModelStore:
    def __init__(self, database: Database) -> None:
        self.database = database

    async def estate_summary(
        self,
        *,
        tenant_id: UUID | None,
        cursor: str | None,
        limit: int,
    ) -> EstateSummary:
        offset = _decode_cursor(cursor)
        counts_row = await self.database.fetch_one(
            """
            SELECT
              count(*) FILTER (WHERE namespace='ENTERPRISE' AND entity_type='Application') AS applications,
              count(*) FILTER (WHERE namespace='ENTERPRISE' AND entity_type='Repository') AS repositories,
              count(*) FILTER (WHERE namespace='ENTERPRISE' AND entity_type='Service') AS services,
              count(*) FILTER (WHERE namespace='TECHNOLOGY' AND entity_type<>'Capability') AS technologies
            FROM entity
            """,
            tenant_id=tenant_id,
        )
        counts_row = counts_row or {}
        counts = EstateCounts(
            applications=counts_row.get("applications", 0),
            repositories=counts_row.get("repositories", 0),
            services=counts_row.get("services", 0),
            technologies=counts_row.get("technologies", 0),
        )

        distribution_rows = await self.database.fetch_all(
            """
            SELECT 'technology.' || coalesce(properties->>'domain_id', lower(entity_type)) AS key, count(*) AS value
            FROM entity
            WHERE namespace='TECHNOLOGY' AND entity_type<>'Capability'
            GROUP BY 1 ORDER BY 1
            """,
            tenant_id=tenant_id,
        )
        coverage_row = await self.database.fetch_one(
            """
            SELECT
              count(*) FILTER (WHERE namespace='ENTERPRISE' AND entity_type='Repository') AS repositories_total,
              count(*) FILTER (WHERE namespace='ENTERPRISE' AND entity_type='Repository' AND last_seen_at IS NOT NULL) AS repositories_scanned,
              coalesce((SELECT count(DISTINCT e.fact_assertion_id)::numeric / nullif(count(DISTINCT f.id), 0)
                        FROM current_fact f LEFT JOIN evidence e ON e.fact_assertion_id=f.id), 0) AS evidence_ratio
            FROM entity
            """,
            tenant_id=tenant_id,
        )
        coverage_row = coverage_row or {}
        coverage = Coverage(
            repositories_total=coverage_row.get("repositories_total", 0),
            repositories_scanned=coverage_row.get("repositories_scanned", 0),
            facts_with_evidence_ratio=_number(coverage_row.get("evidence_ratio")),
        )

        rows = await self.database.fetch_all(
            """
            SELECT e.*, coalesce(e.last_seen_at,e.updated_at,e.created_at) observed_at,
                   p.id priority_id,p.score priority_score,p.confidence priority_confidence,p.method_version priority_method,
                   v.score viability_score,v.confidence viability_confidence,v.method_version viability_method
            FROM entity e
            LEFT JOIN LATERAL (
              SELECT * FROM assessment a WHERE a.subject_entity_id=e.id AND a.status='CURRENT' AND lower(a.dimension)='priority'
              ORDER BY a.valid_from DESC LIMIT 1
            ) p ON true
            LEFT JOIN LATERAL (
              SELECT * FROM assessment a WHERE a.subject_entity_id=e.id AND a.status='CURRENT' AND lower(a.dimension)='viability'
              ORDER BY a.valid_from DESC LIMIT 1
            ) v ON true
            WHERE e.namespace='ENTERPRISE' AND e.entity_type='Application'
            ORDER BY coalesce(p.score,0) DESC,e.name,e.id
            OFFSET %s LIMIT %s
            """,
            (offset, limit + 1),
            tenant_id=tenant_id,
        )
        has_next = len(rows) > limit
        rows = rows[:limit]
        ranked_items: list[RankedItem] = []
        for row in rows:
            priority_confidence = _number(row.get("priority_confidence"), 0.5)
            viability = None
            if row.get("viability_score") is not None:
                viability_confidence = _number(row.get("viability_confidence"), 0.5)
                viability = Score(
                    value=_number(row["viability_score"]),
                    confidence=viability_confidence,
                    confidence_label=_confidence_label(viability_confidence),
                    method_version=row.get("viability_method") or "viability-unavailable-v1",
                )
            ranked_items.append(
                RankedItem(
                    id=row["id"],
                    kind=row["entity_type"],
                    name=row["name"],
                    domain=row["namespace"],
                    priority=Score(
                        value=_number(row.get("priority_score")),
                        confidence=priority_confidence,
                        confidence_label=_confidence_label(priority_confidence),
                        method_version=row.get("priority_method") or "priority-unscored-v1",
                    ),
                    viability=viability,
                    summary=(row.get("properties") or {}).get("summary"),
                    freshness=_freshness(row.get("observed_at")),
                    citations=await self._entity_citations(row["id"], tenant_id),
                )
            )
        return EstateSummary(
            as_of=datetime.now(UTC),
            counts=counts,
            distributions={row["key"]: float(row["value"]) for row in distribution_rows},
            ranked_items=ranked_items,
            coverage=coverage,
            page_info=PageInfo(
                has_next_page=has_next,
                next_cursor=_encode_cursor(offset + limit) if has_next else None,
            ),
        )

    async def application_detail(self, application_id: UUID, *, tenant_id: UUID | None) -> ApplicationDetail:
        application = await self._get_entity(application_id, tenant_id, namespace="ENTERPRISE", entity_type="Application")
        related = await self._related_entities(application_id, tenant_id, depth=2)
        assessments = await self._assessments(application_id, tenant_id)
        recommendations = await self._recommendations(application_id, tenant_id)
        return ApplicationDetail(
            application=_entity(application),
            business_context=[_entity(row) for row in related if row["namespace"] == "BUSINESS"],
            repositories=[_entity(row) for row in related if row["entity_type"] == "Repository"],
            technologies=[_entity(row) for row in related if row["namespace"] in {"TECHNOLOGY", "OSS"}],
            deployments=[_entity(row) for row in related if row["namespace"] == "DEPLOYMENT"],
            assessments=assessments,
            recommendations=recommendations,
            freshness=_freshness(application.get("observed_at")),
        )

    async def technology_detail(self, technology_id: UUID, *, tenant_id: UUID | None) -> TechnologyDetail:
        technology = await self._get_entity(technology_id, tenant_id, namespace="TECHNOLOGY")
        related = await self._related_entities(technology_id, tenant_id, depth=2)
        repositories = [row for row in related if row["entity_type"] == "Repository"]
        applications = [row for row in related if row["entity_type"] == "Application"]
        packages = [row for row in [technology, *related] if row["entity_type"] in {"Package", "PackageVersion"}]
        projects = [row for row in related if row["entity_type"] == "OSSProject"]
        alternatives = await self._predicate_entities(technology_id, "ALTERNATIVE_TO", tenant_id)
        migrations = [row for row in related if row["entity_type"] == "MigrationPattern"]
        registry_rows = await self.database.fetch_all(
            """
            SELECT DISTINCT r.registry_key,r.origin_uri,r.visibility,(r.tenant_id IS NOT NULL) tenant_scoped,
                   coalesce(pri.last_seen_at,e.last_seen_at,e.updated_at) observed_at,ss.source_key
            FROM package_registry_identity pri
            JOIN package_registry r ON r.id=pri.package_registry_id
            JOIN source_system ss ON ss.id=r.source_system_id
            JOIN entity e ON e.id=pri.entity_id
            WHERE pri.entity_id = ANY(%s::uuid[])
            ORDER BY r.registry_key
            """,
            ([row["id"] for row in packages] or [technology_id],),
            tenant_id=tenant_id,
        )
        registry_sources = [
            PackageSource(
                registry_key=row["registry_key"],
                origin=row["origin_uri"],
                visibility=row["visibility"],
                tenant_scoped=row["tenant_scoped"],
                freshness=_freshness(row.get("observed_at"), row.get("source_key")),
            )
            for row in registry_rows
        ]
        return TechnologyDetail(
            technology=_entity(technology),
            internal_usage=InternalUsage(
                repository_count=len(repositories),
                application_count=len(applications),
                repositories=[_entity(row) for row in repositories],
            ),
            packages=[_entity(row) for row in self._dedupe_entities(packages)],
            projects=[_entity(row) for row in projects],
            registry_sources=registry_sources,
            alternatives=[_entity(row) for row in alternatives],
            migration_patterns=[_entity(row) for row in migrations],
            assessments=await self._assessments(technology_id, tenant_id),
            recommendations=await self._recommendations(technology_id, tenant_id),
            freshness=_freshness(technology.get("observed_at")),
        )

    async def modernization(
        self,
        *,
        tenant_id: UUID | None,
        cursor: str | None,
        limit: int,
    ) -> ModernizationList:
        offset = _decode_cursor(cursor)
        rows = await self.database.fetch_all(
            """
            SELECT r.*,e.namespace,e.entity_type,e.name,e.properties,
                   coalesce(e.last_seen_at,r.updated_at,r.created_at) observed_at
            FROM recommendation r JOIN entity e ON e.id=r.subject_entity_id
            WHERE r.status NOT IN ('REJECTED','COMPLETED','DISMISSED') AND r.action<>'RETAIN'
            ORDER BY r.confidence DESC,r.created_at DESC,r.id OFFSET %s LIMIT %s
            """,
            (offset, limit + 1),
            tenant_id=tenant_id,
        )
        has_next = len(rows) > limit
        rows = rows[:limit]
        opportunities: list[RankedItem] = []
        for row in rows:
            confidence = _number(row["confidence"])
            citations = await self._recommendation_citations(row["id"], tenant_id)
            opportunities.append(
                RankedItem(
                    id=row["id"],
                    kind="ModernizationOpportunity",
                    name=row["title"],
                    domain="INTELLIGENCE",
                    priority=Score(
                        value=round(confidence * 100, 2),
                        confidence=confidence,
                        confidence_label=_confidence_label(confidence),
                        method_version=row["method_version"],
                    ),
                    summary=row["rationale"],
                    freshness=_freshness(row.get("observed_at")),
                    citations=citations,
                )
            )
        return ModernizationList(
            as_of=datetime.now(UTC),
            opportunities=opportunities,
            page_info=PageInfo(
                has_next_page=has_next,
                next_cursor=_encode_cursor(offset + limit) if has_next else None,
            ),
        )

    async def graph_neighborhood(
        self,
        center_id: UUID,
        *,
        tenant_id: UUID | None,
        depth: int,
        real_node_limit: int,
    ) -> GraphNeighborhood:
        await self._get_entity(center_id, tenant_id)
        node_rows = await self.database.fetch_all(
            """
            WITH RECURSIVE walk(id,depth) AS (
              SELECT %s::uuid,0
              UNION
              SELECT CASE WHEN r.source_entity_id=w.id THEN r.target_entity_id ELSE r.source_entity_id END,w.depth+1
              FROM walk w JOIN current_relationship r ON r.source_entity_id=w.id OR r.target_entity_id=w.id
              WHERE w.depth<%s
            ), closest AS (SELECT id,min(depth) depth FROM walk GROUP BY id)
            SELECT e.*,c.depth,coalesce(e.last_seen_at,e.updated_at) observed_at
            FROM closest c JOIN entity e ON e.id=c.id
            ORDER BY c.depth,e.namespace,e.entity_type,e.name,e.id LIMIT %s
            """,
            (center_id, depth, real_node_limit + 1),
            tenant_id=tenant_id,
        )
        truncated = len(node_rows) > real_node_limit
        node_rows = node_rows[:real_node_limit]
        node_ids = [row["id"] for row in node_rows]
        edge_rows = await self.database.fetch_all(
            """
            SELECT r.*,coalesce(ia.review_state,'NOT_APPLICABLE') review_state
            FROM current_relationship r
            LEFT JOIN identity_assertion ia ON r.relationship_type='SAME_AS'
              AND ((ia.left_entity_id=r.source_entity_id AND ia.right_entity_id=r.target_entity_id)
                OR (ia.right_entity_id=r.source_entity_id AND ia.left_entity_id=r.target_entity_id))
            WHERE r.source_entity_id=ANY(%s::uuid[]) AND r.target_entity_id=ANY(%s::uuid[])
            ORDER BY r.relationship_type,r.fact_assertion_id
            """,
            (node_ids, node_ids),
            tenant_id=tenant_id,
        )
        return GraphNeighborhood(
            center_id=center_id,
            nodes=[
                GraphNode(
                    id=row["id"], namespace=row["namespace"], type=row["entity_type"],
                    key=row["canonical_key"], label=row["name"], aggregate=False,
                )
                for row in node_rows
            ],
            edges=[
                GraphEdge(
                    id=row["fact_assertion_id"], source=row["source_entity_id"], target=row["target_entity_id"],
                    predicate=row["relationship_type"], confidence=_number(row["confidence"]),
                    assertion_class=row["assertion_class"], review_state=row["review_state"],
                    citation_fact_ids=[row["fact_assertion_id"]],
                )
                for row in edge_rows
                if row["review_state"] != "REJECTED"
            ],
            highlighted_path=[],
            truncated=truncated,
            truncation_reason="REAL_NODE_LIMIT" if truncated else None,
        )

    async def evidence_detail(self, fact_id: UUID, *, tenant_id: UUID | None) -> EvidenceDetail:
        fact = await self.database.fetch_one(
            """
            SELECT f.*,dr.resolution_source,dr.requested_spec,dr.resolved_version,dr.resolved_artifact_uri,
                   dr.integrity,dr.npm_scope,dr.config_path,dr.custom_registry,dr.lockfile_behavior,dr.visibility,
                   pr.origin_uri registry_origin
            FROM fact_assertion f
            LEFT JOIN dependency_resolution dr ON dr.fact_assertion_id=f.id
            LEFT JOIN package_registry pr ON pr.id=dr.package_registry_id
            WHERE f.id=%s
            """,
            (fact_id,),
            tenant_id=tenant_id,
        )
        if fact is None:
            raise APIError(404, "FACT_NOT_FOUND", "The requested fact was not found.")
        evidence_rows = await self.database.fetch_all(
            """
            SELECT e.*,sa.name artifact_name,sa.external_key,sa.artifact_type,sa.source_revision artifact_revision
            FROM evidence e JOIN source_artifact sa ON sa.id=e.source_artifact_id
            WHERE e.fact_assertion_id=%s ORDER BY e.observed_at,e.id
            """,
            (fact_id,),
            tenant_id=tenant_id,
        )
        properties = dict(fact.get("properties") or {})
        if fact.get("resolution_source"):
            properties["requested_spec"] = fact["requested_spec"]
            properties["resolved_version"] = fact.get("resolved_version")
            properties["registry_resolution"] = {
                "origin": fact.get("registry_origin"),
                "source": fact["resolution_source"],
                "scope": fact.get("npm_scope"),
                "config_path": fact.get("config_path"),
                "custom_registry": fact.get("custom_registry"),
                "lockfile_behavior": fact.get("lockfile_behavior"),
                "visibility": fact.get("visibility"),
            }
        evidence = []
        for row in evidence_rows:
            item = {"type": row["evidence_type"], **(row["locator"] or {})}
            if row.get("artifact_name"):
                item["artifact_name"] = row["artifact_name"]
            if row.get("metadata"):
                item["metadata"] = row["metadata"]
            evidence.append(item)
        return EvidenceDetail(
            fact_id=fact_id,
            assertion_class=fact["assertion_class"],
            confidence=_number(fact["confidence"]),
            predicate=fact["predicate"],
            source_revision=fact["source_revision"],
            extractor=Extractor(key=fact["extractor_key"], version=fact["extractor_version"]),
            properties=properties,
            evidence=evidence,
            observed_at=fact["observed_at"],
            effective_at=fact.get("effective_from"),
            closed_at=fact.get("system_to"),
        )

    async def ask(self, request: AskRequest, *, tenant_id: UUID | None) -> AskResponse:
        normalized = " ".join(request.question.lower().split())
        if any(phrase in normalized for phrase in ("how many", "estate count", "estate summary")):
            summary = await self.estate_summary(tenant_id=tenant_id, cursor=None, limit=1)
            rows = [summary.counts.model_dump(mode="json")]
            return AskResponse(
                text=(f"The estate contains {summary.counts.applications} applications, "
                      f"{summary.counts.repositories} repositories, {summary.counts.services} services, "
                      f"and {summary.counts.technologies} technologies."),
                citations=[], result_kind="TABLE", rows=rows,
            )

        if any(word in normalized for word in ("depend", "uses", "used by", "relationship")):
            context_ids = request.context_entity_ids or []
            rows = await self.database.fetch_all(
                """
                SELECT r.fact_assertion_id,s.id subject_id,s.name subject_name,r.relationship_type predicate,
                       o.id object_id,o.name object_name,sa.name artifact_name
                FROM current_relationship r
                JOIN entity s ON s.id=r.source_entity_id JOIN entity o ON o.id=r.target_entity_id
                LEFT JOIN evidence ev ON ev.fact_assertion_id=r.fact_assertion_id
                LEFT JOIN source_artifact sa ON sa.id=ev.source_artifact_id
                WHERE (cardinality(%s::uuid[])=0 OR s.id=ANY(%s::uuid[]) OR o.id=ANY(%s::uuid[]))
                  AND r.relationship_type IN ('DEPENDS_ON','USES','IMPLEMENTS','RUNS_ON','DEPLOYED_AS','PUBLISHED_BY')
                ORDER BY s.name,r.relationship_type,o.name LIMIT 25
                """,
                (context_ids, context_ids, context_ids),
                tenant_id=tenant_id,
            )
            if rows:
                citations = self._dedupe_citations([
                    Citation(
                        fact_id=row["fact_assertion_id"], label=row.get("artifact_name") or row["predicate"],
                        href=f"/api/v1/facts/{row['fact_assertion_id']}/evidence",
                    ) for row in rows
                ])
                result_rows = [
                    {"subject_id": str(row["subject_id"]), "subject": row["subject_name"],
                     "predicate": row["predicate"], "object_id": str(row["object_id"]), "object": row["object_name"]}
                    for row in rows
                ]
                first = rows[0]
                suffix = "" if len(rows) == 1 else f" I found {len(rows)} matching relationships."
                return AskResponse(
                    text=f"{first['subject_name']} {first['predicate'].lower().replace('_', ' ')} {first['object_name']}.{suffix}",
                    citations=citations, result_kind="TABLE" if len(rows) > 1 else "ANSWER", rows=result_rows,
                )
            return AskResponse(
                text="I found no evidence-backed dependency or usage relationships for that question.",
                citations=[], result_kind="ANSWER", rows=[],
            )

        if any(word in normalized for word in ("modernization", "recommendation", "upgrade", "replace", "retire")):
            opportunities = await self.modernization(tenant_id=tenant_id, cursor=None, limit=25)
            rows = [
                {"id": str(item.id), "name": item.name, "priority": item.priority.value, "summary": item.summary}
                for item in opportunities.opportunities
            ]
            citations = self._dedupe_citations([
                citation for item in opportunities.opportunities for citation in (item.citations or [])
            ])
            text = (f"I found {len(rows)} active modernization opportunities."
                    if rows else "I found no active evidence-backed modernization opportunities.")
            return AskResponse(text=text, citations=citations, result_kind="TABLE", rows=rows)

        return AskResponse(
            text=("That question is not supported by the deterministic estate query templates yet. "
                  "Try asking for estate counts, dependencies, usage, or modernization opportunities."),
            citations=[], result_kind="UNSUPPORTED",
        )

    async def review_identity_assertion(
        self,
        assertion_id: UUID,
        request: IdentityReviewRequest,
        *,
        tenant_id: UUID | None,
        actor_key: str,
    ) -> IdentityReviewResult:
        if tenant_id is None:
            raise APIError(400, "TENANT_REQUIRED", "A tenant ID is required to review an identity assertion.")
        async with self.database.session(tenant_id) as connection:
            cursor = await connection.execute(
                "SELECT * FROM identity_assertion WHERE id=%s FOR UPDATE",
                (assertion_id,),
            )
            assertion = await cursor.fetchone()
            if assertion is None:
                raise APIError(404, "IDENTITY_ASSERTION_NOT_FOUND", "The identity assertion was not found.")
            if assertion["version"] != request.expected_version:
                raise APIError(
                    409, "VERSION_CONFLICT", "The identity assertion changed before this review was applied.",
                    {"expected_version": request.expected_version, "actual_version": assertion["version"]},
                )
            if assertion["review_state"] != "POSSIBLE":
                raise APIError(409, "ALREADY_REVIEWED", "The identity assertion has already been reviewed.")
            reviewed_at = datetime.now(UTC)
            review_state = "CONFIRMED" if request.decision == "CONFIRM" else "REJECTED"
            new_version = assertion["version"] + 1
            await connection.execute(
                """
                INSERT INTO identity_assertion_review
                  (tenant_id,identity_assertion_id,decision,rationale,actor_key,prior_version,created_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s)
                """,
                (tenant_id, assertion_id, request.decision, request.rationale, actor_key,
                 request.expected_version, reviewed_at),
            )
            await connection.execute(
                "UPDATE identity_assertion SET review_state=%s,version=%s,updated_at=%s WHERE id=%s",
                (review_state, new_version, reviewed_at, assertion_id),
            )
            await connection.execute(
                """
                INSERT INTO projection_outbox
                  (tenant_id,aggregate_type,aggregate_id,operation,dedupe_key,payload)
                VALUES (%s,'IDENTITY_ASSERTION',%s,'UPSERT',%s,%s::jsonb)
                ON CONFLICT(dedupe_key) DO NOTHING
                """,
                (tenant_id, assertion_id, f"identity-review:{assertion_id}:v{new_version}",
                 json.dumps({"review_state": review_state, "version": new_version})),
            )
        return IdentityReviewResult(
            identity_assertion_id=assertion_id,
            review_state=review_state,
            version=new_version,
            reviewed_at=reviewed_at,
        )

    async def _get_entity(
        self,
        entity_id: UUID,
        tenant_id: UUID | None,
        *,
        namespace: str | None = None,
        entity_type: str | None = None,
    ) -> dict[str, Any]:
        row = await self.database.fetch_one(
            """
            SELECT *,coalesce(last_seen_at,updated_at,created_at) observed_at FROM entity
            WHERE id=%s
              AND (%s::text IS NULL OR namespace=%s::text)
              AND (%s::text IS NULL OR entity_type=%s::text)
            """,
            (entity_id, namespace, namespace, entity_type, entity_type),
            tenant_id=tenant_id,
        )
        if row is None:
            raise APIError(404, "ENTITY_NOT_FOUND", "The requested entity was not found.")
        return row

    async def _related_entities(self, entity_id: UUID, tenant_id: UUID | None, *, depth: int) -> list[dict[str, Any]]:
        return await self.database.fetch_all(
            """
            WITH RECURSIVE walk(id,depth) AS (
              SELECT %s::uuid,0
              UNION
              SELECT CASE WHEN r.source_entity_id=w.id THEN r.target_entity_id ELSE r.source_entity_id END,w.depth+1
              FROM walk w JOIN current_relationship r ON r.source_entity_id=w.id OR r.target_entity_id=w.id
              WHERE w.depth<%s
            )
            SELECT e.*,min(w.depth) depth,coalesce(e.last_seen_at,e.updated_at,e.created_at) observed_at
            FROM walk w JOIN entity e ON e.id=w.id WHERE w.id<>%s
            GROUP BY e.id ORDER BY min(w.depth),e.namespace,e.entity_type,e.name,e.id
            """,
            (entity_id, depth, entity_id),
            tenant_id=tenant_id,
        )

    async def _predicate_entities(self, entity_id: UUID, predicate: str, tenant_id: UUID | None) -> list[dict[str, Any]]:
        return await self.database.fetch_all(
            """
            SELECT e.*,coalesce(e.last_seen_at,e.updated_at,e.created_at) observed_at
            FROM current_relationship r JOIN entity e
              ON e.id=CASE WHEN r.source_entity_id=%s THEN r.target_entity_id ELSE r.source_entity_id END
            WHERE r.relationship_type=%s AND (r.source_entity_id=%s OR r.target_entity_id=%s)
            ORDER BY e.name,e.id
            """,
            (entity_id, predicate, entity_id, entity_id),
            tenant_id=tenant_id,
        )

    async def _assessments(self, subject_id: UUID, tenant_id: UUID | None) -> list[AssessmentSummary]:
        rows = await self.database.fetch_all(
            """
            SELECT a.*,f.id fact_id,coalesce(sa.name,sa.external_key,f.predicate) citation_label
            FROM assessment a JOIN assessment_input ai ON ai.assessment_id=a.id
            JOIN fact_assertion f ON f.id=ai.fact_assertion_id
            LEFT JOIN evidence ev ON ev.fact_assertion_id=f.id
            LEFT JOIN source_artifact sa ON sa.id=ev.source_artifact_id
            WHERE a.subject_entity_id=%s AND a.status='CURRENT'
            ORDER BY a.dimension,a.id,f.id
            """,
            (subject_id,),
            tenant_id=tenant_id,
        )
        grouped: dict[UUID, dict[str, Any]] = {}
        for row in rows:
            item = grouped.setdefault(row["id"], {"row": row, "citations": []})
            item["citations"].append(Citation(
                fact_id=row["fact_id"], label=row["citation_label"],
                href=f"/api/v1/facts/{row['fact_id']}/evidence",
            ))
        result = []
        for item in grouped.values():
            row = item["row"]
            confidence = _number(row["confidence"])
            result.append(AssessmentSummary(
                id=row["id"], dimension=row["dimension"],
                score=_number(row["score"]) if row.get("score") is not None else None,
                categorical_value=row.get("categorical_value"), confidence=confidence,
                confidence_label=_confidence_label(confidence), method_version=row["method_version"],
                rationale=row.get("rationale"), citations=self._dedupe_citations(item["citations"]),
            ))
        return result

    async def _recommendations(self, subject_id: UUID, tenant_id: UUID | None) -> list[RecommendationSummary]:
        rows = await self.database.fetch_all(
            """
            SELECT r.*,t.id target_id,t.entity_type target_type,t.name target_name,t.canonical_key target_key,
                   f.id fact_id,coalesce(sa.name,sa.external_key,f.predicate) citation_label
            FROM recommendation r JOIN recommendation_evidence re ON re.recommendation_id=r.id
            JOIN fact_assertion f ON f.id=re.fact_assertion_id
            LEFT JOIN evidence ev ON ev.fact_assertion_id=f.id
            LEFT JOIN source_artifact sa ON sa.id=ev.source_artifact_id
            LEFT JOIN entity t ON t.id=r.target_entity_id
            WHERE r.subject_entity_id=%s
            ORDER BY r.created_at DESC,r.id,f.id
            """,
            (subject_id,),
            tenant_id=tenant_id,
        )
        grouped: dict[UUID, dict[str, Any]] = {}
        for row in rows:
            item = grouped.setdefault(row["id"], {"row": row, "citations": []})
            item["citations"].append(Citation(
                fact_id=row["fact_id"], label=row["citation_label"],
                href=f"/api/v1/facts/{row['fact_id']}/evidence",
            ))
        result = []
        for item in grouped.values():
            row = item["row"]
            confidence = _number(row["confidence"])
            target = None
            if row.get("target_id"):
                target = EntitySummary(id=row["target_id"], kind=row["target_type"], name=row["target_name"], canonical_key=row["target_key"])
            result.append(RecommendationSummary(
                id=row["id"], action=row["action"], title=row["title"], rationale=row["rationale"],
                confidence=confidence, confidence_label=_confidence_label(confidence), status=row["status"],
                estimated_effort=row.get("estimated_effort"), counter_signals=row.get("counter_signals") or [],
                target=target, citations=self._dedupe_citations(item["citations"]),
            ))
        return result

    async def _entity_citations(self, entity_id: UUID, tenant_id: UUID | None) -> list[Citation]:
        rows = await self.database.fetch_all(
            """
            SELECT DISTINCT ON (f.id) f.id fact_id,coalesce(sa.name,sa.external_key,f.predicate) label
            FROM current_fact f LEFT JOIN evidence e ON e.fact_assertion_id=f.id
            LEFT JOIN source_artifact sa ON sa.id=e.source_artifact_id
            WHERE f.subject_entity_id=%s OR f.object_entity_id=%s ORDER BY f.id,e.observed_at DESC LIMIT 10
            """,
            (entity_id, entity_id),
            tenant_id=tenant_id,
        )
        return [Citation(fact_id=row["fact_id"], label=row["label"], href=f"/api/v1/facts/{row['fact_id']}/evidence") for row in rows]

    async def _recommendation_citations(self, recommendation_id: UUID, tenant_id: UUID | None) -> list[Citation]:
        rows = await self.database.fetch_all(
            """
            SELECT DISTINCT ON (f.id) f.id fact_id,coalesce(sa.name,sa.external_key,f.predicate) label
            FROM recommendation_evidence re JOIN fact_assertion f ON f.id=re.fact_assertion_id
            LEFT JOIN evidence e ON e.fact_assertion_id=f.id LEFT JOIN source_artifact sa ON sa.id=e.source_artifact_id
            WHERE re.recommendation_id=%s ORDER BY f.id,e.observed_at DESC
            """,
            (recommendation_id,),
            tenant_id=tenant_id,
        )
        return [Citation(fact_id=row["fact_id"], label=row["label"], href=f"/api/v1/facts/{row['fact_id']}/evidence") for row in rows]

    @staticmethod
    def _dedupe_entities(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return list({row["id"]: row for row in rows}.values())

    @staticmethod
    def _dedupe_citations(citations: list[Citation]) -> list[Citation]:
        return list({citation.fact_id: citation for citation in citations}.values())
