from __future__ import annotations

import base64
import json
import logging
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from app.age_graph import AgeGraphReader, AgeTopology
from app.database import Database
from app.errors import APIError
from app.models import (
    ApplicationDetail,
    AskRequest,
    AskResponse,
    AssessmentSummary,
    BusinessMapCapabilityNode,
    BusinessMapCreateRequest,
    BusinessMapDetail,
    BusinessMapFunctionAssignment,
    BusinessMapFunctionNode,
    BusinessMapLane,
    BusinessMapList,
    BusinessMapPlacement,
    BusinessMapProcessNode,
    BusinessMapRevisionList,
    BusinessMapRevisionSummary,
    BusinessMapSaveRequest,
    BusinessMapSharedGroup,
    BusinessMapStateModel,
    BusinessMapSummary,
    CapabilityDefinitionModel,
    CapabilityInferenceReviewRequest,
    CapabilityInferenceReviewResult,
    CapabilityInferenceSummary,
    CapabilityTaxonomyResponse,
    Citation,
    Coverage,
    DuplicateCapabilityReviewRequest,
    DuplicateCapabilityReviewResult,
    DuplicateCapabilityCandidateSummary,
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
    ModernizationCandidateModel,
    ModernizationCandidateReviewRequest,
    ModernizationCandidateReviewResult,
    ModernizationImpactModel,
    ModernizationOptionModel,
    ModernizationOptionEligibilityModel,
    ModernizationRecommendationModel,
    ModernizationRecommendationReviewRequest,
    ModernizationRecommendationReviewResult,
    ModernizationValidationOutcomeRequest,
    ModernizationValidationOutcomeResult,
    PackageSource,
    PageInfo,
    RankedItem,
    RecommendationSummary,
    RepositoryCapabilityIntelligence,
    RepositoryModernizationIntelligence,
    Phase3IntelligenceMetrics,
    Score,
    TechnologyDetail,
)


CONTRACT_VERSION = "1.0.0"
MAX_GRAPH_NODES = 50
logger = logging.getLogger(__name__)

# The DB stores uppercase enums; the API contract and UI use the workspace's kebab form.
_VIEW_MODE_TO_DB = {"value-chain": "VALUE_CHAIN", "organization": "ORGANIZATION"}
_VIEW_MODE_FROM_DB = {value: key for key, value in _VIEW_MODE_TO_DB.items()}

_GRAPH_NEIGHBORHOOD_CTE = """
WITH RECURSIVE filters(predicates,namespaces,min_confidence) AS (
  VALUES (%s::text[],%s::text[],%s::numeric)
), walk(id,depth) AS (
  SELECT %s::uuid,0
  UNION
  SELECT next_entity.id,w.depth+1
  FROM walk w
  CROSS JOIN filters
  JOIN current_relationship r ON r.source_entity_id=w.id OR r.target_entity_id=w.id
  JOIN entity next_entity ON next_entity.id=CASE
    WHEN r.source_entity_id=w.id THEN r.target_entity_id ELSE r.source_entity_id END
  LEFT JOIN identity_assertion ia ON r.relationship_type='SAME_AS'
    AND ((ia.left_entity_id=r.source_entity_id AND ia.right_entity_id=r.target_entity_id)
      OR (ia.right_entity_id=r.source_entity_id AND ia.left_entity_id=r.target_entity_id))
  WHERE w.depth<%s
    AND (filters.predicates IS NULL OR r.relationship_type=ANY(filters.predicates))
    AND (filters.namespaces IS NULL OR next_entity.namespace=ANY(filters.namespaces))
    AND r.confidence>=filters.min_confidence
    AND coalesce(ia.review_state,'NOT_APPLICABLE')<>'REJECTED'
), closest AS (
  SELECT id,min(depth) depth FROM walk GROUP BY id
), ranked AS (
  SELECT e.*,c.depth,
         row_number() OVER (ORDER BY c.depth,e.namespace,e.entity_type,e.name,e.id) node_rank
  FROM closest c JOIN entity e ON e.id=c.id
)
"""


def _number(value: Decimal | float | int | None, default: float = 0.0) -> float:
    return float(value) if value is not None else default


def _confidence_label(value: Decimal | float) -> str:
    confidence = float(value)
    if confidence >= 0.85:
        return "HIGH"
    if confidence >= 0.6:
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


def _aggregate_node_id(center_id: UUID, depth: int, namespace: str, entity_type: str) -> UUID:
    return uuid5(
        NAMESPACE_URL,
        f"stackgraph:aggregate:{center_id}:{depth}:{namespace}:{entity_type}",
    )


@dataclass(slots=True)
class GraphReadMetrics:
    age_reads: int = 0
    sql_reads: int = 0
    lag_fallbacks: int = 0
    unavailable_fallbacks: int = 0
    parity_fallbacks: int = 0
    discovery_limit_fallbacks: int = 0


class AgeParityError(RuntimeError):
    pass


class ReadModelStore:
    def __init__(
        self,
        database: Database,
        *,
        graph_read_mode: str = "sql",
        graph_discovery_limit: int = 5000,
    ) -> None:
        self.database = database
        self.graph_read_mode = graph_read_mode
        self.age_graph = AgeGraphReader(database, discovery_limit=graph_discovery_limit)
        self.graph_read_metrics = GraphReadMetrics()

    async def estate_summary(
        self,
        *,
        tenant_id: UUID | None,
        cursor: str | None,
        limit: int,
    ) -> EstateSummary:
        cursor_data = _decode_cursor(cursor, "estate")
        try:
            cursor_score = Decimal(cursor_data["score"]) if cursor_data else None
            cursor_name = str(cursor_data["name"]) if cursor_data else None
            cursor_id = UUID(cursor_data["id"]) if cursor_data else None
        except (KeyError, TypeError, ValueError) as error:
            raise APIError(400, "INVALID_CURSOR", "The pagination cursor is invalid.") from error
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
              AND (
                %s::numeric IS NULL
                OR coalesce(p.score,0)<%s::numeric
                OR (coalesce(p.score,0)=%s::numeric AND (e.name,e.id)>(%s::text,%s::uuid))
              )
            ORDER BY coalesce(p.score,0) DESC,e.name,e.id
            LIMIT %s
            """,
            (cursor_score, cursor_score, cursor_score, cursor_name, cursor_id, limit + 1),
            tenant_id=tenant_id,
        )
        has_next = len(rows) > limit
        rows = rows[:limit]
        citations_by_entity = await self._entity_citations_batch(
            [row["id"] for row in rows], tenant_id,
        )
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
                    citations=citations_by_entity.get(row["id"], []),
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
                next_cursor=(
                    _encode_cursor(
                        "estate",
                        score=str(rows[-1].get("priority_score") or 0),
                        name=rows[-1]["name"],
                        id=str(rows[-1]["id"]),
                    )
                    if has_next else None
                ),
            ),
        )

    async def application_detail(self, application_id: UUID, *, tenant_id: UUID | None) -> ApplicationDetail:
        application = await self._get_entity(application_id, tenant_id, namespace="ENTERPRISE", entity_type="Application")
        related = await self._application_related_entities(application_id, tenant_id)
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
        related = await self._technology_related_entities(technology_id, tenant_id)
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
        cursor_data = _decode_cursor(cursor, "modernization")
        try:
            cursor_confidence = Decimal(cursor_data["confidence"]) if cursor_data else None
            cursor_created_at = datetime.fromisoformat(cursor_data["created_at"]) if cursor_data else None
            cursor_id = UUID(cursor_data["id"]) if cursor_data else None
        except (KeyError, TypeError, ValueError) as error:
            raise APIError(400, "INVALID_CURSOR", "The pagination cursor is invalid.") from error
        rows = await self.database.fetch_all(
            """
            SELECT r.*,e.namespace,e.entity_type,e.name,e.properties,
                   coalesce(e.last_seen_at,r.updated_at,r.created_at) observed_at
            FROM recommendation r JOIN entity e ON e.id=r.subject_entity_id
            WHERE r.status NOT IN ('REJECTED','COMPLETED','DISMISSED') AND r.action<>'RETAIN'
              AND (
                %s::numeric IS NULL
                OR r.confidence<%s::numeric
                OR (r.confidence=%s::numeric AND r.created_at<%s::timestamptz)
                OR (r.confidence=%s::numeric AND r.created_at=%s::timestamptz AND r.id>%s::uuid)
              )
            ORDER BY r.confidence DESC,r.created_at DESC,r.id LIMIT %s
            """,
            (
                cursor_confidence, cursor_confidence, cursor_confidence, cursor_created_at,
                cursor_confidence, cursor_created_at, cursor_id, limit + 1,
            ),
            tenant_id=tenant_id,
        )
        has_next = len(rows) > limit
        rows = rows[:limit]
        citations_by_recommendation = await self._recommendation_citations_batch(
            [row["id"] for row in rows], tenant_id,
        )
        opportunities: list[RankedItem] = []
        for row in rows:
            confidence = _number(row["confidence"])
            citations = citations_by_recommendation.get(row["id"], [])
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
                next_cursor=(
                    _encode_cursor(
                        "modernization",
                        confidence=str(rows[-1]["confidence"]),
                        created_at=rows[-1]["created_at"].isoformat(),
                        id=str(rows[-1]["id"]),
                    )
                    if has_next else None
                ),
            ),
        )

    async def graph_neighborhood(
        self,
        center_id: UUID,
        *,
        tenant_id: UUID | None,
        depth: int,
        real_node_limit: int,
        predicates: list[str] | None = None,
        namespaces: list[str] | None = None,
        min_confidence: float = 0,
        highlight_to: UUID | None = None,
    ) -> GraphNeighborhood:
        if self.graph_read_mode != "sql":
            try:
                if self.graph_read_mode == "auto":
                    projection = await self.age_graph.projection_state(tenant_id)
                    if not projection.current:
                        self.graph_read_metrics.lag_fallbacks += 1
                        logger.info(
                            "graph read using SQL because AGE projection is behind",
                            extra={
                                "pending_events": projection.pending_events,
                                "oldest_pending_seconds": projection.oldest_pending_seconds,
                            },
                        )
                    else:
                        graph = await self._try_age_graph_neighborhood(
                            center_id,
                            tenant_id=tenant_id,
                            depth=depth,
                            real_node_limit=real_node_limit,
                            predicates=predicates,
                            namespaces=namespaces,
                            min_confidence=min_confidence,
                            highlight_to=highlight_to,
                        )
                        if graph is not None:
                            self.graph_read_metrics.age_reads += 1
                            return graph
                else:
                    graph = await self._try_age_graph_neighborhood(
                        center_id,
                        tenant_id=tenant_id,
                        depth=depth,
                        real_node_limit=real_node_limit,
                        predicates=predicates,
                        namespaces=namespaces,
                        min_confidence=min_confidence,
                        highlight_to=highlight_to,
                    )
                    if graph is not None:
                        self.graph_read_metrics.age_reads += 1
                        return graph
            except APIError:
                raise
            except AgeParityError as error:
                self.graph_read_metrics.parity_fallbacks += 1
                logger.warning(
                    "graph read falling back to SQL because AGE differs from current SQL state",
                    extra={"reason": str(error)},
                )
            except Exception as error:
                self.graph_read_metrics.unavailable_fallbacks += 1
                logger.warning(
                    "graph read falling back to SQL because AGE is unavailable",
                    extra={"error_type": type(error).__name__},
                )
        self.graph_read_metrics.sql_reads += 1
        return await self._sql_graph_neighborhood(
            center_id,
            tenant_id=tenant_id,
            depth=depth,
            real_node_limit=real_node_limit,
            predicates=predicates,
            namespaces=namespaces,
            min_confidence=min_confidence,
            highlight_to=highlight_to,
        )

    async def _try_age_graph_neighborhood(
        self,
        center_id: UUID,
        *,
        tenant_id: UUID | None,
        depth: int,
        real_node_limit: int,
        predicates: list[str] | None,
        namespaces: list[str] | None,
        min_confidence: float,
        highlight_to: UUID | None,
    ) -> GraphNeighborhood | None:
        await self._get_entity(center_id, tenant_id)
        if highlight_to is not None:
            await self._get_entity(highlight_to, tenant_id)
        topology = await self.age_graph.neighborhood(
            center_id,
            tenant_id=tenant_id,
            depth=depth,
            predicates=predicates,
            namespaces=namespaces,
            min_confidence=min_confidence,
        )
        if topology is None:
            self.graph_read_metrics.parity_fallbacks += 1
            return None
        if topology.discovery_capped:
            self.graph_read_metrics.discovery_limit_fallbacks += 1
            return None
        return await self._build_age_graph_neighborhood(
            center_id,
            topology,
            tenant_id=tenant_id,
            depth=depth,
            real_node_limit=real_node_limit,
            highlight_to=highlight_to,
        )

    async def _sql_graph_neighborhood(
        self,
        center_id: UUID,
        *,
        tenant_id: UUID | None,
        depth: int,
        real_node_limit: int,
        predicates: list[str] | None = None,
        namespaces: list[str] | None = None,
        min_confidence: float = 0,
        highlight_to: UUID | None = None,
    ) -> GraphNeighborhood:
        await self._get_entity(center_id, tenant_id)
        if highlight_to is not None:
            await self._get_entity(highlight_to, tenant_id)
        graph_params = (predicates or None, namespaces or None, min_confidence, center_id, depth)
        total_row = await self.database.fetch_one(
            _GRAPH_NEIGHBORHOOD_CTE + "SELECT count(*) total FROM ranked",
            graph_params,
            tenant_id=tenant_id,
        )
        total_nodes = int(total_row["total"]) if total_row else 1
        truncated = total_nodes > real_node_limit
        kept_real_count = min(total_nodes, real_node_limit)
        cluster_rows: list[dict[str, Any]] = []

        if truncated:
            while True:
                cluster_rows = await self._graph_cluster_rows(
                    center_id,
                    tenant_id=tenant_id,
                    depth=depth,
                    kept_real_count=kept_real_count,
                    predicates=predicates,
                    namespaces=namespaces,
                    min_confidence=min_confidence,
                )
                next_kept_count = max(
                    1,
                    min(real_node_limit, MAX_GRAPH_NODES - len(cluster_rows)),
                )
                if next_kept_count == kept_real_count:
                    break
                kept_real_count = next_kept_count

        node_rows = await self.database.fetch_all(
            _GRAPH_NEIGHBORHOOD_CTE
            + """
            SELECT *,coalesce(last_seen_at,updated_at) observed_at
            FROM ranked WHERE node_rank<=%s ORDER BY node_rank
            """,
            (*graph_params, kept_real_count),
            tenant_id=tenant_id,
        )
        node_ids = [row["id"] for row in node_rows]
        edge_rows = await self.database.fetch_all(
            """
            SELECT r.*,coalesce(ia.review_state,'NOT_APPLICABLE') review_state
            FROM current_relationship r
            LEFT JOIN identity_assertion ia ON r.relationship_type='SAME_AS'
              AND ((ia.left_entity_id=r.source_entity_id AND ia.right_entity_id=r.target_entity_id)
                OR (ia.right_entity_id=r.source_entity_id AND ia.left_entity_id=r.target_entity_id))
            WHERE r.source_entity_id=ANY(%s::uuid[]) AND r.target_entity_id=ANY(%s::uuid[])
              AND (%s::text[] IS NULL OR r.relationship_type=ANY(%s::text[]))
              AND r.confidence>=%s::numeric
            ORDER BY r.relationship_type,r.fact_assertion_id
            """,
            (node_ids, node_ids, predicates or None, predicates or None, min_confidence),
            tenant_id=tenant_id,
        )
        aggregate_nodes = [
            GraphNode(
                id=_aggregate_node_id(
                    center_id,
                    depth,
                    row["namespace"],
                    row["entity_type"],
                ),
                namespace=row["namespace"],
                type=row["entity_type"],
                key=(
                    f"aggregate:{center_id}:{depth}:"
                    f"{row['namespace']}:{row['entity_type']}"
                ),
                label=(
                    f"{row['entity_type']} cluster · {row['member_count']} "
                    f"{'node' if row['member_count'] == 1 else 'nodes'}"
                ),
                aggregate=True,
                member_count=row["member_count"],
            )
            for row in cluster_rows
        ]
        aggregate_edges = (
            await self._graph_aggregate_edges(
                center_id,
                tenant_id=tenant_id,
                depth=depth,
                kept_real_count=kept_real_count,
                predicates=predicates,
                namespaces=namespaces,
                min_confidence=min_confidence,
            )
            if truncated
            else []
        )
        highlighted_path = await self._graph_highlight_path(
            center_id,
            highlight_to,
            tenant_id=tenant_id,
            depth=depth,
            predicates=predicates,
            namespaces=namespaces,
            min_confidence=min_confidence,
        )
        visible_node_ids = set(node_ids) | {node.id for node in aggregate_nodes}
        if any(node_id not in visible_node_ids for node_id in highlighted_path):
            highlighted_path = []
        return GraphNeighborhood(
            center_id=center_id,
            nodes=[
                GraphNode(
                    id=row["id"], namespace=row["namespace"], type=row["entity_type"],
                    key=row["canonical_key"], label=row["name"], aggregate=False,
                )
                for row in node_rows
            ] + aggregate_nodes,
            edges=[
                GraphEdge(
                    id=row["fact_assertion_id"], source=row["source_entity_id"], target=row["target_entity_id"],
                    predicate=row["relationship_type"], confidence=_number(row["confidence"]),
                    assertion_class=row["assertion_class"], review_state=row["review_state"],
                    citation_fact_ids=[row["fact_assertion_id"]],
                )
                for row in edge_rows
                if row["review_state"] != "REJECTED"
            ] + aggregate_edges,
            highlighted_path=highlighted_path,
            truncated=truncated,
            truncation_reason="REAL_NODE_LIMIT" if truncated else None,
        )

    async def _build_age_graph_neighborhood(
        self,
        center_id: UUID,
        topology: AgeTopology,
        *,
        tenant_id: UUID | None,
        depth: int,
        real_node_limit: int,
        highlight_to: UUID | None,
    ) -> GraphNeighborhood:
        node_rows = await self.database.fetch_all(
            """
            SELECT *,coalesce(last_seen_at,updated_at,created_at) observed_at
            FROM entity WHERE id=ANY(%s::uuid[])
            """,
            (list(topology.node_depths),),
            tenant_id=tenant_id,
        )
        rows_by_id = {row["id"]: row for row in node_rows}
        missing_nodes = set(topology.node_depths) - set(rows_by_id)
        if missing_nodes:
            raise AgeParityError(f"{len(missing_nodes)} AGE nodes are absent from SQL")

        edge_rows = await self.database.fetch_all(
            """
            SELECT r.*,coalesce(identity.review_state,'NOT_APPLICABLE') review_state
            FROM current_relationship r
            LEFT JOIN LATERAL (
              SELECT ia.review_state
              FROM identity_assertion ia
              WHERE r.relationship_type='SAME_AS'
                AND ((ia.left_entity_id=r.source_entity_id AND ia.right_entity_id=r.target_entity_id)
                  OR (ia.right_entity_id=r.source_entity_id AND ia.left_entity_id=r.target_entity_id))
              ORDER BY ia.updated_at DESC,ia.id LIMIT 1
            ) identity ON true
            WHERE r.fact_assertion_id=ANY(%s::uuid[])
              AND r.source_entity_id=ANY(%s::uuid[])
              AND r.target_entity_id=ANY(%s::uuid[])
              AND coalesce(identity.review_state,'NOT_APPLICABLE')<>'REJECTED'
            ORDER BY r.relationship_type,r.fact_assertion_id
            """,
            (list(topology.fact_ids), list(topology.node_depths), list(topology.node_depths)),
            tenant_id=tenant_id,
        )
        sql_fact_ids = {row["fact_assertion_id"] for row in edge_rows}
        if sql_fact_ids != set(topology.fact_ids):
            raise AgeParityError(
                f"AGE returned {len(topology.fact_ids)} facts but SQL hydrated {len(sql_fact_ids)}"
            )

        ranked_rows = sorted(
            node_rows,
            key=lambda row: (
                topology.node_depths[row["id"]], row["namespace"], row["entity_type"],
                row["name"], row["id"],
            ),
        )
        total_nodes = len(ranked_rows)
        truncated = total_nodes > real_node_limit
        kept_real_count = min(total_nodes, real_node_limit)
        clusters: dict[tuple[str, str], list[dict[str, Any]]] = {}
        if truncated:
            while True:
                clusters = defaultdict(list)
                for row in ranked_rows[kept_real_count:]:
                    clusters[(row["namespace"], row["entity_type"])].append(row)
                next_kept_count = max(
                    1,
                    min(real_node_limit, MAX_GRAPH_NODES - len(clusters)),
                )
                if next_kept_count == kept_real_count:
                    break
                kept_real_count = next_kept_count

        kept_rows = ranked_rows[:kept_real_count]
        kept_ids = {row["id"] for row in kept_rows}
        aggregate_nodes = [
            GraphNode(
                id=_aggregate_node_id(center_id, depth, namespace, entity_type),
                namespace=namespace,
                type=entity_type,
                key=f"aggregate:{center_id}:{depth}:{namespace}:{entity_type}",
                label=(
                    f"{entity_type} cluster · {len(members)} "
                    f"{'node' if len(members) == 1 else 'nodes'}"
                ),
                aggregate=True,
                member_count=len(members),
            )
            for (namespace, entity_type), members in sorted(clusters.items())
        ]
        mapped_ids: dict[UUID, UUID] = {}
        for row in ranked_rows:
            mapped_ids[row["id"]] = (
                row["id"] if row["id"] in kept_ids else _aggregate_node_id(
                    center_id, depth, row["namespace"], row["entity_type"],
                )
            )

        real_edges: list[GraphEdge] = []
        aggregate_groups: dict[tuple[Any, ...], dict[str, Any]] = {}
        for row in edge_rows:
            source_id = mapped_ids[row["source_entity_id"]]
            target_id = mapped_ids[row["target_entity_id"]]
            if source_id == target_id:
                continue
            if row["source_entity_id"] in kept_ids and row["target_entity_id"] in kept_ids:
                real_edges.append(GraphEdge(
                    id=row["fact_assertion_id"],
                    source=source_id,
                    target=target_id,
                    predicate=row["relationship_type"],
                    confidence=_number(row["confidence"]),
                    assertion_class=row["assertion_class"],
                    review_state=row["review_state"],
                    citation_fact_ids=[row["fact_assertion_id"]],
                ))
                continue
            key = (
                source_id, target_id, row["relationship_type"],
                row["assertion_class"], row["review_state"],
            )
            group = aggregate_groups.setdefault(key, {
                "confidence": _number(row["confidence"]), "fact_ids": [],
            })
            group["confidence"] = min(group["confidence"], _number(row["confidence"]))
            if len(group["fact_ids"]) < 20:
                group["fact_ids"].append(row["fact_assertion_id"])

        aggregate_edges = []
        for key, group in sorted(aggregate_groups.items(), key=lambda item: tuple(map(str, item[0]))):
            source_id, target_id, predicate, assertion_class, review_state = key
            edge_id = uuid5(
                NAMESPACE_URL,
                (
                    f"stackgraph:aggregate-edge:{center_id}:{depth}:{source_id}:"
                    f"{target_id}:{predicate}:{assertion_class}:{review_state}"
                ),
            )
            aggregate_edges.append(GraphEdge(
                id=edge_id,
                source=source_id,
                target=target_id,
                predicate=predicate,
                confidence=group["confidence"],
                assertion_class=assertion_class,
                review_state=review_state,
                citation_fact_ids=group["fact_ids"],
            ))

        highlighted_path = self._shortest_graph_path(
            center_id, highlight_to, edge_rows, max_depth=depth,
        )
        visible_node_ids = kept_ids | {node.id for node in aggregate_nodes}
        if any(node_id not in visible_node_ids for node_id in highlighted_path):
            highlighted_path = []
        return GraphNeighborhood(
            center_id=center_id,
            nodes=[
                GraphNode(
                    id=row["id"], namespace=row["namespace"], type=row["entity_type"],
                    key=row["canonical_key"], label=row["name"], aggregate=False,
                ) for row in kept_rows
            ] + aggregate_nodes,
            edges=real_edges + aggregate_edges,
            highlighted_path=highlighted_path,
            truncated=truncated,
            truncation_reason="REAL_NODE_LIMIT" if truncated else None,
        )

    @staticmethod
    def _shortest_graph_path(
        center_id: UUID,
        highlight_to: UUID | None,
        edge_rows: list[dict[str, Any]],
        *,
        max_depth: int,
    ) -> list[UUID]:
        if highlight_to is None:
            return []
        if highlight_to == center_id:
            return [center_id]
        adjacent: dict[UUID, set[UUID]] = defaultdict(set)
        for row in edge_rows:
            adjacent[row["source_entity_id"]].add(row["target_entity_id"])
            adjacent[row["target_entity_id"]].add(row["source_entity_id"])
        queue = deque([(center_id, [center_id])])
        visited = {center_id}
        while queue:
            current, path = queue.popleft()
            if len(path) - 1 >= max_depth:
                continue
            for neighbor in sorted(adjacent[current], key=str):
                if neighbor in visited:
                    continue
                next_path = [*path, neighbor]
                if neighbor == highlight_to:
                    return next_path
                visited.add(neighbor)
                queue.append((neighbor, next_path))
        return []

    async def _graph_cluster_rows(
        self,
        center_id: UUID,
        *,
        tenant_id: UUID | None,
        depth: int,
        kept_real_count: int,
        predicates: list[str] | None,
        namespaces: list[str] | None,
        min_confidence: float,
    ) -> list[dict[str, Any]]:
        return await self.database.fetch_all(
            _GRAPH_NEIGHBORHOOD_CTE
            + """
            SELECT namespace,entity_type,count(*)::integer member_count,min(depth) min_depth
            FROM ranked WHERE node_rank>%s
            GROUP BY namespace,entity_type
            ORDER BY min(depth),namespace,entity_type
            """,
            (
                predicates or None, namespaces or None, min_confidence,
                center_id, depth, kept_real_count,
            ),
            tenant_id=tenant_id,
        )

    async def _graph_aggregate_edges(
        self,
        center_id: UUID,
        *,
        tenant_id: UUID | None,
        depth: int,
        kept_real_count: int,
        predicates: list[str] | None,
        namespaces: list[str] | None,
        min_confidence: float,
    ) -> list[GraphEdge]:
        rows = await self.database.fetch_all(
            _GRAPH_NEIGHBORHOOD_CTE
            + """
            , mapped AS (
              SELECT id,namespace,entity_type,node_rank,
                     CASE WHEN node_rank<=%s THEN id END real_id
              FROM ranked
            )
            SELECT
              source.real_id source_real_id,
              source.namespace source_namespace,
              source.entity_type source_entity_type,
              target.real_id target_real_id,
              target.namespace target_namespace,
              target.entity_type target_entity_type,
              r.relationship_type,
              r.assertion_class,
              coalesce(ia.review_state,'NOT_APPLICABLE') review_state,
              min(r.confidence) confidence,
              (array_agg(r.fact_assertion_id ORDER BY r.fact_assertion_id))[1:20] citation_fact_ids
            FROM current_relationship r
            CROSS JOIN filters
            JOIN mapped source ON source.id=r.source_entity_id
            JOIN mapped target ON target.id=r.target_entity_id
            LEFT JOIN identity_assertion ia ON r.relationship_type='SAME_AS'
              AND ((ia.left_entity_id=r.source_entity_id AND ia.right_entity_id=r.target_entity_id)
                OR (ia.right_entity_id=r.source_entity_id AND ia.left_entity_id=r.target_entity_id))
            WHERE (source.real_id IS NULL OR target.real_id IS NULL)
              AND (filters.predicates IS NULL OR r.relationship_type=ANY(filters.predicates))
              AND r.confidence>=filters.min_confidence
              AND coalesce(ia.review_state,'NOT_APPLICABLE')<>'REJECTED'
              AND NOT (
                source.real_id IS NULL AND target.real_id IS NULL
                AND source.namespace=target.namespace
                AND source.entity_type=target.entity_type
              )
            GROUP BY source.real_id,source.namespace,source.entity_type,
                     target.real_id,target.namespace,target.entity_type,
                     r.relationship_type,r.assertion_class,
                     coalesce(ia.review_state,'NOT_APPLICABLE')
            ORDER BY source.namespace,source.entity_type,target.namespace,target.entity_type,
                     r.relationship_type,r.assertion_class
            """,
            (
                predicates or None, namespaces or None, min_confidence,
                center_id, depth, kept_real_count,
            ),
            tenant_id=tenant_id,
        )
        edges: list[GraphEdge] = []
        for row in rows:
            source_id = row["source_real_id"] or _aggregate_node_id(
                center_id,
                depth,
                row["source_namespace"],
                row["source_entity_type"],
            )
            target_id = row["target_real_id"] or _aggregate_node_id(
                center_id,
                depth,
                row["target_namespace"],
                row["target_entity_type"],
            )
            edge_id = uuid5(
                NAMESPACE_URL,
                (
                    f"stackgraph:aggregate-edge:{center_id}:{depth}:{source_id}:"
                    f"{target_id}:{row['relationship_type']}:{row['assertion_class']}:"
                    f"{row['review_state']}"
                ),
            )
            edges.append(
                GraphEdge(
                    id=edge_id,
                    source=source_id,
                    target=target_id,
                    predicate=row["relationship_type"],
                    confidence=_number(row["confidence"]),
                    assertion_class=row["assertion_class"],
                    review_state=row["review_state"],
                    citation_fact_ids=row["citation_fact_ids"],
                )
            )
        return edges

    async def _graph_highlight_path(
        self,
        center_id: UUID,
        highlight_to: UUID | None,
        *,
        tenant_id: UUID | None,
        depth: int,
        predicates: list[str] | None,
        namespaces: list[str] | None,
        min_confidence: float,
    ) -> list[UUID]:
        if highlight_to is None:
            return []
        row = await self.database.fetch_one(
            """
            WITH RECURSIVE filters(predicates,namespaces,min_confidence) AS (
              VALUES (%s::text[],%s::text[],%s::numeric)
            ), paths(id,path,depth) AS (
              SELECT %s::uuid,ARRAY[%s::uuid],0
              UNION ALL
              SELECT next_entity.id,paths.path || next_entity.id,paths.depth+1
              FROM paths
              CROSS JOIN filters
              JOIN current_relationship r
                ON r.source_entity_id=paths.id OR r.target_entity_id=paths.id
              JOIN entity next_entity ON next_entity.id=CASE
                WHEN r.source_entity_id=paths.id THEN r.target_entity_id ELSE r.source_entity_id END
              LEFT JOIN identity_assertion ia ON r.relationship_type='SAME_AS'
                AND ((ia.left_entity_id=r.source_entity_id AND ia.right_entity_id=r.target_entity_id)
                  OR (ia.right_entity_id=r.source_entity_id AND ia.left_entity_id=r.target_entity_id))
              WHERE paths.depth<%s
                AND NOT next_entity.id=ANY(paths.path)
                AND (filters.predicates IS NULL OR r.relationship_type=ANY(filters.predicates))
                AND (filters.namespaces IS NULL OR next_entity.namespace=ANY(filters.namespaces))
                AND r.confidence>=filters.min_confidence
                AND coalesce(ia.review_state,'NOT_APPLICABLE')<>'REJECTED'
            )
            SELECT path FROM paths WHERE id=%s ORDER BY depth,path LIMIT 1
            """,
            (
                predicates or None, namespaces or None, min_confidence,
                center_id, center_id, depth, highlight_to,
            ),
            tenant_id=tenant_id,
        )
        return list(row["path"]) if row else []

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
        context_ids = request.context_entity_ids or []

        if "unsupported" in normalized and any(word in normalized for word in ("runtime", "node", "python", "java")):
            rows = await self.database.fetch_all(
                """
                WITH RECURSIVE paths(app_id,id,depth,visited,fact_ids) AS (
                  SELECT e.id,e.id,0,ARRAY[e.id],ARRAY[]::uuid[]
                  FROM entity e
                  WHERE e.namespace='ENTERPRISE' AND e.entity_type='Application'
                    AND lower(coalesce(e.properties->>'tier',e.properties->>'criticality',''))
                        IN ('tier_1','tier-1','tier 1','1','critical')
                    AND (cardinality(%s::uuid[])=0 OR e.id=ANY(%s::uuid[]))
                  UNION ALL
                  SELECT paths.app_id,next_entity.id,paths.depth+1,
                         paths.visited || next_entity.id,paths.fact_ids || r.fact_assertion_id
                  FROM paths
                  JOIN current_relationship r ON r.source_entity_id=paths.id OR r.target_entity_id=paths.id
                  JOIN entity next_entity ON next_entity.id=CASE
                    WHEN r.source_entity_id=paths.id THEN r.target_entity_id ELSE r.source_entity_id END
                  WHERE paths.depth<2 AND NOT next_entity.id=ANY(paths.visited)
                    AND r.relationship_type IN (
                      'IMPLEMENTED_BY','IMPLEMENTS','USES','RUNS_ON','DEPENDS_ON','HAS_VERSION'
                    )
                )
                SELECT DISTINCT ON (app.id,runtime.id)
                       app.id application_id,app.name application_name,
                       runtime.id runtime_id,runtime.name runtime_name,
                       a.categorical_value support_state,a.rationale,
                       paths.fact_ids[array_length(paths.fact_ids,1)] fact_id,
                       coalesce(sa.name,sa.external_key,'runtime evidence') citation_label
                FROM paths
                JOIN entity app ON app.id=paths.app_id
                JOIN entity runtime ON runtime.id=paths.id
                  AND runtime.namespace='TECHNOLOGY' AND runtime.entity_type='Runtime'
                LEFT JOIN assessment a ON a.subject_entity_id=runtime.id
                  AND a.status='CURRENT' AND lower(a.dimension) IN ('supportability','runtime_support')
                LEFT JOIN evidence ev
                  ON ev.fact_assertion_id=paths.fact_ids[array_length(paths.fact_ids,1)]
                LEFT JOIN source_artifact sa ON sa.id=ev.source_artifact_id
                WHERE upper(coalesce(a.categorical_value,runtime.properties->>'support_status',''))
                      IN ('UNSUPPORTED','END_OF_LIFE','EOL')
                ORDER BY app.id,runtime.id,ev.observed_at DESC
                """,
                (context_ids, context_ids),
                tenant_id=tenant_id,
            )
            citations = self._dedupe_citations([
                Citation(
                    fact_id=row["fact_id"],
                    label=row["citation_label"],
                    href=f"/api/v1/facts/{row['fact_id']}/evidence",
                )
                for row in rows if row.get("fact_id")
            ])
            result_rows = [
                {
                    "application_id": str(row["application_id"]),
                    "application": row["application_name"],
                    "runtime_id": str(row["runtime_id"]),
                    "runtime": row["runtime_name"],
                    "support_state": row.get("support_state") or "UNSUPPORTED",
                    "rationale": row.get("rationale"),
                }
                for row in rows
            ]
            return AskResponse(
                text=(
                    f"I found {len(rows)} Tier-1 application"
                    f"{'s' if len(rows) != 1 else ''} using unsupported runtimes."
                    if rows else "I found no evidence-backed Tier-1 applications using unsupported runtimes."
                ),
                citations=citations,
                result_kind="TABLE",
                rows=result_rows,
            )

        if "why" in normalized and any(word in normalized for word in ("viability", "supportability", "score")):
            rows = await self.database.fetch_all(
                """
                SELECT DISTINCT ON (a.id,f.id)
                       e.id entity_id,e.name,a.dimension,a.score,a.categorical_value,
                       a.rationale,f.id fact_id,
                       coalesce(sa.name,sa.external_key,f.predicate) citation_label
                FROM entity e
                JOIN assessment a ON a.subject_entity_id=e.id AND a.status='CURRENT'
                JOIN assessment_input ai ON ai.assessment_id=a.id
                JOIN fact_assertion f ON f.id=ai.fact_assertion_id
                LEFT JOIN evidence ev ON ev.fact_assertion_id=f.id
                LEFT JOIN source_artifact sa ON sa.id=ev.source_artifact_id
                WHERE lower(a.dimension) IN ('viability','supportability')
                  AND (
                    e.id=ANY(%s::uuid[])
                    OR (cardinality(%s::uuid[])=0 AND %s LIKE '%%' || lower(e.name) || '%%')
                    OR (cardinality(%s::uuid[])=0 AND %s LIKE '%%' || lower(split_part(e.name,' ',1)) || '%%')
                  )
                ORDER BY a.id,f.id,ev.observed_at DESC
                """,
                (context_ids, context_ids, normalized, context_ids, normalized),
                tenant_id=tenant_id,
            )
            if rows:
                citations = self._dedupe_citations([
                    Citation(
                        fact_id=row["fact_id"], label=row["citation_label"],
                        href=f"/api/v1/facts/{row['fact_id']}/evidence",
                    ) for row in rows
                ])
                result_rows = [{
                    "entity_id": str(row["entity_id"]), "entity": row["name"],
                    "dimension": row["dimension"], "score": _number(row["score"]) if row.get("score") is not None else None,
                    "value": row.get("categorical_value"), "rationale": row["rationale"],
                } for row in rows]
                return AskResponse(
                    text=" ".join(dict.fromkeys(row["rationale"] for row in rows)),
                    citations=citations, result_kind="ANSWER", rows=result_rows,
                )
            return AskResponse(
                text="I found no evidence-backed viability assessment for that application.",
                citations=[], result_kind="ANSWER", rows=[],
            )

        if "indirect" in normalized and any(word in normalized for word in ("depend", "uses", "used by")):
            if not context_ids:
                return AskResponse(
                    text="Select a package or technology before asking for indirect dependents.",
                    citations=[], result_kind="UNSUPPORTED",
                )
            center_id = context_ids[0]
            rows = await self.database.fetch_all(
                """
                WITH RECURSIVE paths(id,depth,visited,fact_ids) AS (
                  SELECT %s::uuid,0,ARRAY[%s::uuid],ARRAY[]::uuid[]
                  UNION ALL
                  SELECT next_entity.id,paths.depth+1,paths.visited || next_entity.id,
                         paths.fact_ids || r.fact_assertion_id
                  FROM paths
                  JOIN current_relationship r ON r.source_entity_id=paths.id OR r.target_entity_id=paths.id
                  JOIN entity next_entity ON next_entity.id=CASE
                    WHEN r.source_entity_id=paths.id THEN r.target_entity_id ELSE r.source_entity_id END
                  WHERE paths.depth<2 AND NOT next_entity.id=ANY(paths.visited)
                    AND r.relationship_type IN ('DEPENDS_ON','USES','IMPLEMENTED_BY','IMPLEMENTS')
                )
                SELECT DISTINCT ON (e.id) e.id,e.name,paths.fact_ids
                FROM paths JOIN entity e ON e.id=paths.id
                WHERE e.namespace='ENTERPRISE' AND e.entity_type='Application'
                ORDER BY e.id,paths.depth
                """,
                (center_id, center_id),
                tenant_id=tenant_id,
            )
            fact_ids = list(dict.fromkeys(
                fact_id for row in rows for fact_id in row["fact_ids"]
            ))
            citation_rows = await self.database.fetch_all(
                """
                SELECT DISTINCT ON (f.id) f.id fact_id,
                       coalesce(sa.name,sa.external_key,f.predicate) label
                FROM fact_assertion f
                LEFT JOIN evidence ev ON ev.fact_assertion_id=f.id
                LEFT JOIN source_artifact sa ON sa.id=ev.source_artifact_id
                WHERE f.id=ANY(%s::uuid[]) ORDER BY f.id,ev.observed_at DESC
                """,
                (fact_ids,),
                tenant_id=tenant_id,
            ) if fact_ids else []
            graph = None
            if rows:
                graph = await self.graph_neighborhood(
                    center_id,
                    tenant_id=tenant_id,
                    depth=2,
                    real_node_limit=50,
                    predicates=["DEPENDS_ON", "USES", "IMPLEMENTED_BY", "IMPLEMENTS"],
                    highlight_to=rows[0]["id"],
                )
            return AskResponse(
                text=(f"I found {len(rows)} indirectly dependent application"
                      f"{'s' if len(rows) != 1 else ''}."),
                citations=[Citation(
                    fact_id=row["fact_id"], label=row["label"],
                    href=f"/api/v1/facts/{row['fact_id']}/evidence",
                ) for row in citation_rows],
                result_kind="GRAPH" if graph else "ANSWER",
                rows=[{"application_id": str(row["id"]), "application": row["name"]} for row in rows],
                graph_highlight=graph,
            )

        if "depend" in normalized:
            rows = await self.database.fetch_all(
                """
                WITH applications AS (
                  SELECT e.id,e.name
                  FROM entity e
                  WHERE e.namespace='ENTERPRISE' AND e.entity_type='Application'
                    AND (
                      e.id=ANY(%s::uuid[])
                      OR (cardinality(%s::uuid[])=0 AND %s LIKE '%%' || lower(e.name) || '%%')
                      OR (cardinality(%s::uuid[])=0 AND %s LIKE '%%' || lower(split_part(e.name,' ',1)) || '%%')
                    )
                ), roots AS (
                  SELECT applications.id application_id,applications.name application_name,
                         applications.id root_id
                  FROM applications
                  UNION
                  SELECT applications.id,applications.name,
                         CASE WHEN r.source_entity_id=applications.id
                           THEN r.target_entity_id ELSE r.source_entity_id END
                  FROM applications JOIN current_relationship r
                    ON r.source_entity_id=applications.id OR r.target_entity_id=applications.id
                  JOIN entity repository ON repository.id=CASE
                    WHEN r.source_entity_id=applications.id
                      THEN r.target_entity_id ELSE r.source_entity_id END
                  WHERE repository.namespace='ENTERPRISE' AND repository.entity_type='Repository'
                    AND r.relationship_type IN ('IMPLEMENTED_BY','IMPLEMENTS','CONTAINS')
                )
                SELECT DISTINCT ON (roots.application_id,object.id,r.relationship_type)
                       roots.application_id,roots.application_name,
                       r.relationship_type predicate,object.id object_id,object.name object_name,
                       r.fact_assertion_id,
                       coalesce(sa.name,sa.external_key,r.relationship_type) citation_label
                FROM roots JOIN current_relationship r
                  ON r.source_entity_id=roots.root_id OR r.target_entity_id=roots.root_id
                JOIN entity object ON object.id=CASE WHEN r.source_entity_id=roots.root_id
                  THEN r.target_entity_id ELSE r.source_entity_id END
                LEFT JOIN evidence ev ON ev.fact_assertion_id=r.fact_assertion_id
                LEFT JOIN source_artifact sa ON sa.id=ev.source_artifact_id
                WHERE r.relationship_type IN ('DEPENDS_ON','USES')
                  AND object.namespace IN ('TECHNOLOGY','OSS')
                ORDER BY roots.application_id,object.id,r.relationship_type,ev.observed_at DESC
                """,
                (context_ids, context_ids, normalized, context_ids, normalized),
                tenant_id=tenant_id,
            )
            if rows:
                citations = self._dedupe_citations([
                    Citation(
                        fact_id=row["fact_assertion_id"], label=row["citation_label"],
                        href=f"/api/v1/facts/{row['fact_assertion_id']}/evidence",
                    ) for row in rows
                ])
                result_rows = [{
                    "application_id": str(row["application_id"]),
                    "application": row["application_name"],
                    "predicate": row["predicate"],
                    "technology_id": str(row["object_id"]),
                    "technology": row["object_name"],
                } for row in rows]
                first = rows[0]
                return AskResponse(
                    text=(f"{first['application_name']} directly depends on "
                          f"{first['object_name']}."),
                    citations=citations,
                    result_kind="ANSWER" if len(rows) == 1 else "TABLE",
                    rows=result_rows,
                )

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

    async def capability_taxonomy(
        self,
        *,
        tenant_id: UUID | None,
        version: str | None,
    ) -> CapabilityTaxonomyResponse:
        taxonomy = await self.database.fetch_one(
            """
            SELECT * FROM capability_taxonomy_version
            WHERE taxonomy_key='stackgraph.technical-capabilities'
              AND (tenant_id=%s OR tenant_id IS NULL)
              AND ((%s::text IS NULL AND status='ACTIVE') OR version=%s)
            ORDER BY (tenant_id IS NOT NULL) DESC,updated_at DESC LIMIT 1
            """,
            (tenant_id, version, version),
            tenant_id=tenant_id,
        )
        if taxonomy is None:
            raise APIError(404, "CAPABILITY_TAXONOMY_NOT_FOUND", "The capability taxonomy was not found.")
        rows = await self.database.fetch_all(
            """
            SELECT * FROM capability_definition
            WHERE taxonomy_version_id=%s ORDER BY capability_key
            """,
            (taxonomy["id"],),
            tenant_id=tenant_id,
        )
        return CapabilityTaxonomyResponse(
            key=taxonomy["taxonomy_key"],
            version=taxonomy["version"],
            name=taxonomy["name"],
            description=taxonomy["description"],
            content_hash=taxonomy["content_hash"],
            capabilities=[self._capability_definition(row) for row in rows],
        )

    async def repository_capabilities(
        self,
        repository_id: UUID,
        *,
        tenant_id: UUID | None,
    ) -> RepositoryCapabilityIntelligence:
        repository = await self._get_entity(
            repository_id, tenant_id, namespace="ENTERPRISE", entity_type="Repository",
        )
        rows = await self.database.fetch_all(
            """
            SELECT inference.*,subject.entity_type subject_type,subject.canonical_key subject_key,
                   subject.name subject_name,capability.capability_key,capability.name capability_name,
                   capability.description capability_description,capability.parent_capability_key,
                   capability.aliases,taxonomy.taxonomy_key,taxonomy.version taxonomy_version
            FROM capability_inference inference
            JOIN entity subject ON subject.id=inference.subject_entity_id
            JOIN capability_definition capability ON capability.id=inference.capability_definition_id
            JOIN capability_taxonomy_version taxonomy ON taxonomy.id=inference.taxonomy_version_id
            WHERE inference.repository_entity_id=%s AND inference.stale_at IS NULL
            ORDER BY capability.name,subject.name,inference.id
            """,
            (repository_id,),
            tenant_id=tenant_id,
        )
        inferences = [CapabilityInferenceSummary(
            id=row["id"],
            subject=EntitySummary(
                id=row["subject_entity_id"], kind=row["subject_type"],
                name=row["subject_name"], canonical_key=row["subject_key"],
            ),
            capability=self._capability_definition(row),
            source_revision=row["source_revision"],
            assertion_class=row["assertion_class"],
            confidence=_number(row["confidence"]),
            confidence_band=row["confidence_band"],
            supporting_fact_ids=list(row["supporting_fact_ids"]),
            counter_evidence_fact_ids=list(row["counter_evidence_fact_ids"]),
            taxonomy_key=row["taxonomy_key"],
            taxonomy_version=row["taxonomy_version"],
            analyzer=Extractor(key=row["analyzer_key"], version=row["analyzer_version"]),
            model_provider=row.get("model_provider"),
            model_name=row.get("model_name"),
            policy_version=row["policy_version"],
            rationale=row["rationale"],
            review_state=row["review_state"],
            version=row["version"],
            stale=row["stale_at"] is not None,
            created_at=row["created_at"],
        ) for row in rows]
        duplicate_rows = await self.database.fetch_all(
            """
            SELECT candidate.*,capability.capability_key,capability.name capability_name,
                   capability.description capability_description,capability.parent_capability_key,
                   capability.aliases
            FROM duplicate_capability_candidate candidate
            JOIN capability_definition capability ON capability.id=candidate.capability_definition_id
            WHERE candidate.repository_entity_id=%s AND candidate.stale_at IS NULL
            ORDER BY capability.name,candidate.id
            """,
            (repository_id,),
            tenant_id=tenant_id,
        )
        dependency_ids = sorted({
            entity_id for row in duplicate_rows for entity_id in row["dependency_entity_ids"]
        }, key=str)
        dependency_rows = await self.database.fetch_all(
            "SELECT * FROM entity WHERE id=ANY(%s::uuid[])",
            (dependency_ids or [repository_id],),
            tenant_id=tenant_id,
        )
        dependencies = {row["id"]: _entity(row) for row in dependency_rows}
        duplicates = [DuplicateCapabilityCandidateSummary(
            id=row["id"],
            capability=self._capability_definition(row),
            source_revision=row["source_revision"],
            dependencies=[dependencies[item] for item in row["dependency_entity_ids"] if item in dependencies],
            capability_inference_ids=list(row["capability_inference_ids"]),
            supporting_fact_ids=list(row["supporting_fact_ids"]),
            confidence=_number(row["confidence"]),
            summary=row["summary"],
            limitations=list(row["limitations"]),
            review_state=row["review_state"],
            version=row["version"],
            stale=row["stale_at"] is not None,
        ) for row in duplicate_rows]
        first = rows[0] if rows else None
        return RepositoryCapabilityIntelligence(
            repository=_entity(repository),
            taxonomy_key=first["taxonomy_key"] if first else None,
            taxonomy_version=first["taxonomy_version"] if first else None,
            inferences=inferences,
            duplicate_candidates=duplicates,
        )

    async def review_capability_inference(
        self,
        inference_id: UUID,
        review: CapabilityInferenceReviewRequest,
        *,
        tenant_id: UUID | None,
        actor_key: str,
    ) -> CapabilityInferenceReviewResult:
        if tenant_id is None:
            raise APIError(400, "TENANT_REQUIRED", "A tenant ID is required to review an inference.")
        async with self.database.session(tenant_id) as connection:
            cursor = await connection.execute(
                "SELECT * FROM capability_inference WHERE id=%s FOR UPDATE",
                (inference_id,),
            )
            inference = await cursor.fetchone()
            if inference is None:
                raise APIError(404, "CAPABILITY_INFERENCE_NOT_FOUND", "The capability inference was not found.")
            if inference["version"] != review.expected_version:
                raise APIError(
                    409, "VERSION_CONFLICT", "The capability inference changed before review.",
                    {"expected_version": review.expected_version, "actual_version": inference["version"]},
                )
            if inference["review_state"] != "UNREVIEWED":
                raise APIError(409, "ALREADY_REVIEWED", "The capability inference has already been reviewed.")
            reviewed_at = datetime.now(UTC)
            review_state = "CONFIRMED" if review.decision == "CONFIRM" else "REJECTED"
            new_version = inference["version"] + 1
            await connection.execute(
                """
                INSERT INTO capability_inference_review(
                  tenant_id,capability_inference_id,decision,rationale,reviewer_actor_key,
                  prior_version,resulting_version,reviewed_at
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    tenant_id, inference_id, review.decision, review.rationale,
                    actor_key, inference["version"], new_version, reviewed_at,
                ),
            )
            await connection.execute(
                """
                UPDATE capability_inference
                SET review_state=%s,version=%s,updated_at=%s WHERE id=%s
                """,
                (review_state, new_version, reviewed_at, inference_id),
            )
        return CapabilityInferenceReviewResult(
            capability_inference_id=inference_id,
            review_state=review_state,
            version=new_version,
            reviewed_at=reviewed_at,
        )

    async def review_duplicate_capability_candidate(
        self,
        candidate_id: UUID,
        review: DuplicateCapabilityReviewRequest,
        *,
        tenant_id: UUID | None,
        actor_key: str,
    ) -> DuplicateCapabilityReviewResult:
        if tenant_id is None:
            raise APIError(400, "TENANT_REQUIRED", "A tenant ID is required to review a candidate.")
        async with self.database.session(tenant_id) as connection:
            cursor = await connection.execute(
                "SELECT * FROM duplicate_capability_candidate WHERE id=%s FOR UPDATE",
                (candidate_id,),
            )
            candidate = await cursor.fetchone()
            if candidate is None:
                raise APIError(404, "DUPLICATE_CAPABILITY_NOT_FOUND", "The duplicate candidate was not found.")
            if candidate["version"] != review.expected_version:
                raise APIError(
                    409, "VERSION_CONFLICT", "The duplicate candidate changed before review.",
                    {"expected_version": review.expected_version, "actual_version": candidate["version"]},
                )
            if candidate["review_state"] != "UNREVIEWED":
                raise APIError(409, "ALREADY_REVIEWED", "The duplicate candidate has already been reviewed.")
            reviewed_at = datetime.now(UTC)
            review_state = "CONFIRMED" if review.decision == "CONFIRM" else "REJECTED"
            new_version = candidate["version"] + 1
            await connection.execute(
                """
                INSERT INTO duplicate_capability_candidate_review(
                  tenant_id,duplicate_capability_candidate_id,decision,rationale,
                  reviewer_actor_key,prior_version,resulting_version,reviewed_at
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    tenant_id, candidate_id, review.decision, review.rationale,
                    actor_key, candidate["version"], new_version, reviewed_at,
                ),
            )
            await connection.execute(
                """
                UPDATE duplicate_capability_candidate
                SET review_state=%s,version=%s,updated_at=%s WHERE id=%s
                """,
                (review_state, new_version, reviewed_at, candidate_id),
            )
        return DuplicateCapabilityReviewResult(
            duplicate_capability_candidate_id=candidate_id,
            review_state=review_state,
            version=new_version,
            reviewed_at=reviewed_at,
        )

    async def repository_modernization_intelligence(
        self,
        repository_id: UUID,
        *,
        tenant_id: UUID | None,
        limit: int,
    ) -> RepositoryModernizationIntelligence:
        repository = await self._get_entity(
            repository_id, tenant_id, namespace="ENTERPRISE", entity_type="Repository",
        )
        rows = await self.database.fetch_all(
            """
            SELECT candidate.*,capability.capability_key,capability.name capability_name,
                   capability.description capability_description,
                   capability.parent_capability_key,capability.aliases
            FROM modernization_candidate candidate
            LEFT JOIN capability_definition capability
              ON capability.id=candidate.capability_definition_id
            WHERE candidate.repository_entity_id=%s AND candidate.stale_at IS NULL
            ORDER BY candidate.confidence DESC,candidate.created_at,candidate.id
            LIMIT %s
            """,
            (repository_id, limit + 1),
            tenant_id=tenant_id,
        )
        truncated = len(rows) > limit
        rows = rows[:limit]
        candidate_ids = [row["id"] for row in rows]
        subject_ids = sorted({
            entity_id for row in rows for entity_id in row["subject_entity_ids"]
        }, key=str)
        option_rows = await self.database.fetch_all(
            """
            SELECT option.*,entity.namespace target_namespace,entity.entity_type target_type,
                   entity.canonical_key target_key,entity.name target_name,
                   evaluation.capability_fit eligibility_capability_fit,
                   evaluation.api_fit eligibility_api_fit,
                   evaluation.behavior_fit eligibility_behavior_fit,
                   evaluation.runtime_fit eligibility_runtime_fit,
                   evaluation.license_fit eligibility_license_fit,
                   evaluation.security_fit eligibility_security_fit,
                   evaluation.policy_fit eligibility_policy_fit,
                   evaluation.eligible eligibility_eligible,
                   evaluation.evidence eligibility_evidence,
                   evaluation.disqualifiers eligibility_disqualifiers,
                   evaluation.unknowns eligibility_unknowns
            FROM modernization_option option
            LEFT JOIN entity ON entity.id=option.target_entity_id
            LEFT JOIN modernization_option_evaluation evaluation
              ON evaluation.modernization_option_id=option.id
            WHERE option.modernization_candidate_id=ANY(%s::uuid[])
            ORDER BY option.modernization_candidate_id,option.rank,option.id
            """,
            (candidate_ids or [repository_id],),
            tenant_id=tenant_id,
        )
        recommendation_rows = await self.database.fetch_all(
            """
            SELECT * FROM modernization_recommendation
            WHERE modernization_candidate_id=ANY(%s::uuid[]) AND stale_at IS NULL
            ORDER BY modernization_candidate_id,created_at DESC,id
            """,
            (candidate_ids or [repository_id],),
            tenant_id=tenant_id,
        )
        impact_rows = await self.database.fetch_all(
            """
            SELECT * FROM modernization_impact
            WHERE modernization_candidate_id=ANY(%s::uuid[])
            """,
            (candidate_ids or [repository_id],),
            tenant_id=tenant_id,
        )
        subject_rows = await self.database.fetch_all(
            "SELECT * FROM entity WHERE id=ANY(%s::uuid[])",
            (subject_ids or [repository_id],),
            tenant_id=tenant_id,
        )
        subjects = {row["id"]: _entity(row) for row in subject_rows}
        options: dict[UUID, list[ModernizationOptionModel]] = defaultdict(list)
        for row in option_rows:
            target = None
            if row["target_entity_id"] is not None:
                target = EntitySummary(
                    id=row["target_entity_id"], kind=row["target_type"],
                    name=row["target_name"], canonical_key=row["target_key"],
                )
            eligibility = None
            if row["eligibility_capability_fit"] is not None:
                eligibility = ModernizationOptionEligibilityModel(
                    capability_fit=row["eligibility_capability_fit"],
                    api_fit=row["eligibility_api_fit"],
                    behavior_fit=row["eligibility_behavior_fit"],
                    runtime_fit=row["eligibility_runtime_fit"],
                    license_fit=row["eligibility_license_fit"],
                    security_fit=row["eligibility_security_fit"],
                    policy_fit=row["eligibility_policy_fit"],
                    eligible=row["eligibility_eligible"],
                    evidence=dict(row["eligibility_evidence"]),
                    disqualifiers=list(row["eligibility_disqualifiers"]),
                    unknowns=list(row["eligibility_unknowns"]),
                )
            options[row["modernization_candidate_id"]].append(ModernizationOptionModel(
                id=row["id"], kind=row["option_kind"], canonical_key=row["canonical_key"],
                name=row["name"], target_entity=target, compatibility=row["compatibility"],
                rank=row["rank"], score=_number(row["score"]),
                score_components={key: _number(value) for key, value in row["score_components"].items()},
                rationale=row["rationale"], tradeoffs=list(row["tradeoffs"]),
                disqualifiers=list(row["disqualifiers"]), validation_gaps=list(row["validation_gaps"]),
                supporting_fact_ids=list(row["supporting_fact_ids"]),
                eligibility=eligibility,
            ))
        impacts = {
            row["modernization_candidate_id"]: ModernizationImpactModel(
                affected_call_sites=row["affected_call_sites"],
                affected_files=row["affected_files"],
                covered_call_sites=row["covered_call_sites"],
                uncovered_call_sites=row["uncovered_call_sites"],
                affected_test_files=list(row["affected_test_files"]),
                dynamic_signals=list(row["dynamic_signals"]),
                configuration_touchpoints=list(row["configuration_touchpoints"]),
                build_touchpoints=list(row["build_touchpoints"]),
                deployment_touchpoints=list(row["deployment_touchpoints"]),
                evidence_locations=list(row["evidence_locations"]),
                confidence=_number(row["confidence"]), effort_points=row["effort_points"],
                effort_model_version=row["effort_model_version"],
                limitations=list(row["limitations"]),
            ) for row in impact_rows
        }
        recommendations = {
            row["modernization_candidate_id"]: ModernizationRecommendationModel(
                id=row["id"], selected_option_id=row["selected_option_id"], action=row["action"],
                objective=row["objective"], title=row["title"], rationale=row["rationale"],
                confidence=_number(row["confidence"]), estimated_effort=row["estimated_effort"],
                affected_call_sites=row["affected_call_sites"], affected_files=row["affected_files"],
                validation_gaps=list(row["validation_gaps"]), migration_plan=list(row["migration_plan"]),
                rollback_plan=list(row["rollback_plan"]), supporting_fact_ids=list(row["supporting_fact_ids"]),
                counter_evidence_fact_ids=list(row["counter_evidence_fact_ids"]),
                counter_signals=list(row["counter_signals"]), policy_version=row["policy_version"],
                review_state=row["review_state"], version=row["version"],
                stale=row["stale_at"] is not None, created_at=row["created_at"],
            )
            for row in recommendation_rows
        }
        candidates = [ModernizationCandidateModel(
            id=row["id"], source_revision=row["source_revision"],
            capability=self._capability_definition(row) if row["capability_definition_id"] else None,
            kind=row["candidate_kind"],
            subjects=[subjects[item] for item in row["subject_entity_ids"] if item in subjects],
            confidence=_number(row["confidence"]), summary=row["summary"],
            supporting_fact_ids=list(row["supporting_fact_ids"]),
            counter_evidence_fact_ids=list(row["counter_evidence_fact_ids"]),
            source_locations=list(row["source_locations"]), validation_gaps=list(row["validation_gaps"]),
            analyzer=Extractor(key=row["analyzer_key"], version=row["analyzer_version"]),
            review_state=row["review_state"], version=row["version"],
            stale=row["stale_at"] is not None, options=options[row["id"]],
            recommendation=recommendations.get(row["id"]),
            impact=impacts.get(row["id"]),
        ) for row in rows]
        return RepositoryModernizationIntelligence(
            repository=_entity(repository),
            source_revision=rows[0]["source_revision"] if rows else None,
            candidates=candidates,
            truncated=truncated,
        )

    async def review_modernization_candidate(
        self,
        candidate_id: UUID,
        review: ModernizationCandidateReviewRequest,
        *,
        tenant_id: UUID | None,
        actor_key: str,
    ) -> ModernizationCandidateReviewResult:
        if tenant_id is None:
            raise APIError(400, "TENANT_REQUIRED", "A tenant ID is required to review a candidate.")
        async with self.database.session(tenant_id) as connection:
            cursor = await connection.execute(
                "SELECT * FROM modernization_candidate WHERE id=%s FOR UPDATE",
                (candidate_id,),
            )
            candidate = await cursor.fetchone()
            if candidate is None:
                raise APIError(404, "MODERNIZATION_CANDIDATE_NOT_FOUND", "The candidate was not found.")
            if candidate["version"] != review.expected_version:
                raise APIError(
                    409, "VERSION_CONFLICT", "The candidate changed before review.",
                    {"expected_version": review.expected_version, "actual_version": candidate["version"]},
                )
            if candidate["review_state"] != "UNREVIEWED":
                raise APIError(409, "ALREADY_REVIEWED", "The candidate has already been reviewed.")
            reviewed_at = datetime.now(UTC)
            review_state = {"CONFIRM": "CONFIRMED", "REJECT": "REJECTED"}[review.decision]
            new_version = candidate["version"] + 1
            await connection.execute(
                """
                INSERT INTO modernization_candidate_review(
                  tenant_id,modernization_candidate_id,decision,rationale,
                  reviewer_actor_key,prior_version,resulting_version,reviewed_at
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    tenant_id, candidate_id, review.decision, review.rationale,
                    actor_key, candidate["version"], new_version, reviewed_at,
                ),
            )
            await connection.execute(
                """
                UPDATE modernization_candidate
                SET review_state=%s,version=%s,updated_at=%s WHERE id=%s
                """,
                (review_state, new_version, reviewed_at, candidate_id),
            )
        return ModernizationCandidateReviewResult(
            modernization_candidate_id=candidate_id, review_state=review_state,
            version=new_version, reviewed_at=reviewed_at,
        )

    async def review_modernization_recommendation(
        self,
        recommendation_id: UUID,
        review: ModernizationRecommendationReviewRequest,
        *,
        tenant_id: UUID | None,
        actor_key: str,
    ) -> ModernizationRecommendationReviewResult:
        if tenant_id is None:
            raise APIError(400, "TENANT_REQUIRED", "A tenant ID is required to review a recommendation.")
        async with self.database.session(tenant_id) as connection:
            cursor = await connection.execute(
                "SELECT * FROM modernization_recommendation WHERE id=%s FOR UPDATE",
                (recommendation_id,),
            )
            recommendation = await cursor.fetchone()
            if recommendation is None:
                raise APIError(404, "MODERNIZATION_RECOMMENDATION_NOT_FOUND", "The recommendation was not found.")
            if recommendation["version"] != review.expected_version:
                raise APIError(
                    409, "VERSION_CONFLICT", "The recommendation changed before review.",
                    {"expected_version": review.expected_version, "actual_version": recommendation["version"]},
                )
            if recommendation["review_state"] != "UNREVIEWED":
                raise APIError(409, "ALREADY_REVIEWED", "The recommendation has already been reviewed.")
            reviewed_at = datetime.now(UTC)
            review_state = {"ACCEPT": "ACCEPTED", "REJECT": "REJECTED", "DISMISS": "DISMISSED"}[review.decision]
            new_version = recommendation["version"] + 1
            await connection.execute(
                """
                INSERT INTO modernization_recommendation_review(
                  tenant_id,modernization_recommendation_id,decision,rationale,
                  reviewer_actor_key,prior_version,resulting_version,reviewed_at
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    tenant_id, recommendation_id, review.decision, review.rationale,
                    actor_key, recommendation["version"], new_version, reviewed_at,
                ),
            )
            await connection.execute(
                """
                UPDATE modernization_recommendation
                SET review_state=%s,version=%s,updated_at=%s WHERE id=%s
                """,
                (review_state, new_version, reviewed_at, recommendation_id),
            )
        return ModernizationRecommendationReviewResult(
            modernization_recommendation_id=recommendation_id,
            review_state=review_state,
            version=new_version,
            reviewed_at=reviewed_at,
        )

    async def record_modernization_validation_outcome(
        self,
        recommendation_id: UUID,
        outcome: ModernizationValidationOutcomeRequest,
        *,
        tenant_id: UUID | None,
        actor_key: str,
    ) -> ModernizationValidationOutcomeResult:
        if tenant_id is None:
            raise APIError(400, "TENANT_REQUIRED", "A tenant ID is required to report validation.")
        reported_at = datetime.now(UTC)
        async with self.database.session(tenant_id) as connection:
            cursor = await connection.execute(
                "SELECT id,review_state FROM modernization_recommendation WHERE id=%s FOR UPDATE",
                (recommendation_id,),
            )
            recommendation = await cursor.fetchone()
            if recommendation is None:
                raise APIError(
                    404, "MODERNIZATION_RECOMMENDATION_NOT_FOUND",
                    "The recommendation was not found.",
                )
            if recommendation["review_state"] != "ACCEPTED":
                raise APIError(
                    409, "RECOMMENDATION_NOT_ACCEPTED",
                    "Validation outcomes can be reported only for accepted recommendations.",
                )
            cursor = await connection.execute(
                """
                INSERT INTO modernization_validation_outcome(
                  tenant_id,modernization_recommendation_id,validation_status,
                  actual_call_sites,actual_files,actual_effort,successful_checks,
                  failed_checks,notes,reporter_actor_key,reported_at
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id
                """,
                (
                    tenant_id, recommendation_id, outcome.validation_status,
                    outcome.actual_call_sites, outcome.actual_files, outcome.actual_effort,
                    outcome.successful_checks, outcome.failed_checks, outcome.notes,
                    actor_key, reported_at,
                ),
            )
            row = await cursor.fetchone()
            assert row is not None
        return ModernizationValidationOutcomeResult(
            id=row["id"], modernization_recommendation_id=recommendation_id,
            validation_status=outcome.validation_status, reported_at=reported_at,
        )

    # --- Business Map ------------------------------------------------------
    # The map is the API's first read-write aggregate. A save is a whole-map replace
    # guarded by optimistic `expected_version`, reusing the identity-assertion FOR UPDATE
    # pattern; children are deleted and re-inserted inside one transaction and each save
    # writes an immutable revision snapshot.

    async def list_business_maps(
        self, *, tenant_id: UUID | None, cursor: str | None, limit: int,
    ) -> BusinessMapList:
        if tenant_id is None:
            raise APIError(400, "TENANT_REQUIRED", "A tenant ID is required to list business maps.")
        decoded = _decode_cursor(cursor, "business-map")
        rows = await self.database.fetch_all(
            """
            SELECT * FROM business_map
            WHERE status<>'ARCHIVED'
              AND (%(updated_before)s::timestamptz IS NULL
                   OR updated_at<%(updated_before)s
                   OR (updated_at=%(updated_before)s AND id<%(id_before)s))
            ORDER BY updated_at DESC,id DESC
            LIMIT %(limit)s
            """,
            {
                "updated_before": decoded["updated_before"] if decoded else None,
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
                "business-map",
                updated_before=last["updated_at"].isoformat(),
                id_before=str(last["id"]),
            )
        return BusinessMapList(
            as_of=datetime.now(UTC),
            maps=[self._business_map_summary(row) for row in page],
            page_info=PageInfo(has_next_page=has_next, next_cursor=next_cursor),
        )

    async def create_business_map(
        self, request: BusinessMapCreateRequest, *, tenant_id: UUID | None, actor_key: str,
    ) -> BusinessMapDetail:
        if tenant_id is None:
            raise APIError(400, "TENANT_REQUIRED", "A tenant ID is required to create a business map.")
        self._validate_business_map_state(request.state)
        async with self.database.session(tenant_id) as connection:
            existing = await connection.execute(
                "SELECT 1 FROM business_map WHERE map_key=%s", (request.map_key,),
            )
            if await existing.fetchone() is not None:
                raise APIError(
                    409, "BUSINESS_MAP_EXISTS", "A business map with this key already exists.",
                    {"map_key": request.map_key},
                )
            cursor = await connection.execute(
                """
                INSERT INTO business_map
                  (tenant_id,map_key,title,view_mode,template_id,status,version,created_by)
                VALUES (%s,%s,%s,%s,%s,'ACTIVE',1,%s)
                RETURNING id
                """,
                (
                    tenant_id, request.map_key, request.state.title,
                    _VIEW_MODE_TO_DB[request.state.view_mode], request.state.template_id, actor_key,
                ),
            )
            map_id = (await cursor.fetchone())["id"]
            await self._write_business_map_children(connection, map_id=map_id, tenant_id=tenant_id, state=request.state)
            await self._write_business_map_revision(
                connection, map_id=map_id, tenant_id=tenant_id, version=1,
                state=request.state, actor_key=actor_key,
            )
            return await self._business_map_detail(connection, map_id)

    async def business_map_detail(
        self, map_id: UUID, *, tenant_id: UUID | None,
    ) -> BusinessMapDetail:
        if tenant_id is None:
            raise APIError(400, "TENANT_REQUIRED", "A tenant ID is required to read a business map.")
        async with self.database.session(tenant_id) as connection:
            return await self._business_map_detail(connection, map_id)

    async def save_business_map(
        self, map_id: UUID, request: BusinessMapSaveRequest, *, tenant_id: UUID | None, actor_key: str,
    ) -> BusinessMapDetail:
        if tenant_id is None:
            raise APIError(400, "TENANT_REQUIRED", "A tenant ID is required to save a business map.")
        self._validate_business_map_state(request.state)
        async with self.database.session(tenant_id) as connection:
            cursor = await connection.execute(
                "SELECT * FROM business_map WHERE id=%s FOR UPDATE", (map_id,),
            )
            existing = await cursor.fetchone()
            if existing is None:
                raise APIError(404, "BUSINESS_MAP_NOT_FOUND", "The business map was not found.")
            if existing["status"] == "ARCHIVED":
                raise APIError(409, "BUSINESS_MAP_ARCHIVED", "An archived business map cannot be edited.")
            if existing["version"] != request.expected_version:
                raise APIError(
                    409, "VERSION_CONFLICT", "The business map changed before this save was applied.",
                    {"expected_version": request.expected_version, "actual_version": existing["version"]},
                )
            new_version = existing["version"] + 1
            now = datetime.now(UTC)
            # Delete parents; CASCADE clears processes, capabilities, placements,
            # shared-group members, and assignments.
            await connection.execute("DELETE FROM business_map_shared_group WHERE business_map_id=%s", (map_id,))
            await connection.execute("DELETE FROM business_map_function WHERE business_map_id=%s", (map_id,))
            await connection.execute("DELETE FROM business_map_lane WHERE business_map_id=%s", (map_id,))
            await connection.execute(
                """
                UPDATE business_map
                SET title=%s,view_mode=%s,template_id=%s,version=%s,updated_at=%s
                WHERE id=%s
                """,
                (
                    request.state.title, _VIEW_MODE_TO_DB[request.state.view_mode],
                    request.state.template_id, new_version, now, map_id,
                ),
            )
            await self._write_business_map_children(connection, map_id=map_id, tenant_id=tenant_id, state=request.state)
            await self._write_business_map_revision(
                connection, map_id=map_id, tenant_id=tenant_id, version=new_version,
                state=request.state, actor_key=actor_key,
            )
            return await self._business_map_detail(connection, map_id)

    async def archive_business_map(
        self, map_id: UUID, *, tenant_id: UUID | None, actor_key: str,
    ) -> BusinessMapSummary:
        if tenant_id is None:
            raise APIError(400, "TENANT_REQUIRED", "A tenant ID is required to archive a business map.")
        async with self.database.session(tenant_id) as connection:
            cursor = await connection.execute(
                """
                UPDATE business_map SET status='ARCHIVED',updated_at=now()
                WHERE id=%s AND status<>'ARCHIVED'
                RETURNING *
                """,
                (map_id,),
            )
            row = await cursor.fetchone()
            if row is None:
                probe = await connection.execute("SELECT 1 FROM business_map WHERE id=%s", (map_id,))
                if await probe.fetchone() is None:
                    raise APIError(404, "BUSINESS_MAP_NOT_FOUND", "The business map was not found.")
                cursor = await connection.execute("SELECT * FROM business_map WHERE id=%s", (map_id,))
                row = await cursor.fetchone()
        return self._business_map_summary(row)

    async def business_map_revisions(
        self, map_id: UUID, *, tenant_id: UUID | None,
    ) -> BusinessMapRevisionList:
        if tenant_id is None:
            raise APIError(400, "TENANT_REQUIRED", "A tenant ID is required to read business map revisions.")
        async with self.database.session(tenant_id) as connection:
            probe = await connection.execute("SELECT 1 FROM business_map WHERE id=%s", (map_id,))
            if await probe.fetchone() is None:
                raise APIError(404, "BUSINESS_MAP_NOT_FOUND", "The business map was not found.")
            cursor = await connection.execute(
                """
                SELECT version,actor_key,created_at FROM business_map_revision
                WHERE business_map_id=%s ORDER BY version DESC
                """,
                (map_id,),
            )
            rows = await cursor.fetchall()
        return BusinessMapRevisionList(
            business_map_id=map_id,
            revisions=[
                BusinessMapRevisionSummary(
                    version=row["version"], actor_key=row["actor_key"], created_at=row["created_at"],
                )
                for row in rows
            ],
        )

    @staticmethod
    def _business_map_summary(row: dict[str, Any]) -> BusinessMapSummary:
        return BusinessMapSummary(
            id=row["id"], map_key=row["map_key"], title=row["title"],
            view_mode=_VIEW_MODE_FROM_DB[row["view_mode"]], template_id=row["template_id"],
            status=row["status"], version=row["version"],
            created_at=row["created_at"], updated_at=row["updated_at"],
        )

    @staticmethod
    def _validate_business_map_state(state: BusinessMapStateModel) -> None:
        stage_keys = {stage.id for stage in state.stages}
        unit_keys = {unit.id for unit in state.organization_units}
        function_keys = {fn.id for fn in state.catalog}
        capability_keys = {
            capability.id
            for fn in state.catalog
            for process in fn.processes
            for capability in process.capabilities
        }

        def require(condition: bool, ref_kind: str, ref: str) -> None:
            if not condition:
                raise APIError(
                    422, "BUSINESS_MAP_INVALID_REFERENCE",
                    "The business map references an element it does not define.",
                    {"reference_kind": ref_kind, "reference": ref},
                )

        for placement in state.placements:
            require(placement.capability_id in capability_keys, "placement.capability_id", placement.capability_id)
            if placement.stage_id is not None:
                require(placement.stage_id in stage_keys, "placement.stage_id", placement.stage_id)
            if placement.source_function_id is not None:
                require(placement.source_function_id in function_keys, "placement.source_function_id", placement.source_function_id)
        for group in state.shared_groups:
            require(group.start_stage_id in stage_keys, "shared_group.start_stage_id", group.start_stage_id)
            require(group.end_stage_id in stage_keys, "shared_group.end_stage_id", group.end_stage_id)
            for capability_id in group.capability_ids:
                require(capability_id in capability_keys, "shared_group.capability_id", capability_id)
        for assignment in state.function_assignments:
            require(assignment.function_id in function_keys, "assignment.function_id", assignment.function_id)
            require(assignment.unit_id in unit_keys, "assignment.unit_id", assignment.unit_id)

    async def _write_business_map_children(
        self, connection: Any, *, map_id: UUID, tenant_id: UUID, state: BusinessMapStateModel,
    ) -> None:
        stage_ids: dict[str, UUID] = {}
        unit_ids: dict[str, UUID] = {}
        for order, stage in enumerate(state.stages):
            cursor = await connection.execute(
                """
                INSERT INTO business_map_lane
                  (tenant_id,business_map_id,lane_kind,lane_key,label,sublabel,color,gradient,icon,position)
                VALUES (%s,%s,'STAGE',%s,%s,%s,%s,%s,%s,%s) RETURNING id
                """,
                (tenant_id, map_id, stage.id, stage.label, stage.sublabel, stage.color, stage.gradient, stage.icon, order),
            )
            stage_ids[stage.id] = (await cursor.fetchone())["id"]
        for order, unit in enumerate(state.organization_units):
            cursor = await connection.execute(
                """
                INSERT INTO business_map_lane
                  (tenant_id,business_map_id,lane_kind,lane_key,label,sublabel,color,gradient,icon,position)
                VALUES (%s,%s,'ORG_UNIT',%s,%s,%s,%s,%s,%s,%s) RETURNING id
                """,
                (tenant_id, map_id, unit.id, unit.label, unit.sublabel, unit.color, unit.gradient, unit.icon, order),
            )
            unit_ids[unit.id] = (await cursor.fetchone())["id"]

        function_ids: dict[str, UUID] = {}
        capability_ids: dict[str, UUID] = {}
        for fn_order, fn in enumerate(state.catalog):
            cursor = await connection.execute(
                """
                INSERT INTO business_map_function
                  (tenant_id,business_map_id,function_key,name,description,color,gradient,icon,position)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id
                """,
                (tenant_id, map_id, fn.id, fn.name, fn.description, fn.color, fn.gradient, fn.icon, fn_order),
            )
            function_id = (await cursor.fetchone())["id"]
            function_ids[fn.id] = function_id
            for process_order, process in enumerate(fn.processes):
                cursor = await connection.execute(
                    """
                    INSERT INTO business_map_process
                      (tenant_id,business_map_id,business_map_function_id,process_key,name,description,position)
                    VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id
                    """,
                    (tenant_id, map_id, function_id, process.id, process.name, process.description, process_order),
                )
                process_id = (await cursor.fetchone())["id"]
                for capability_order, capability in enumerate(process.capabilities):
                    cursor = await connection.execute(
                        """
                        INSERT INTO business_map_capability
                          (tenant_id,business_map_id,business_map_process_id,capability_key,name,description,tags,kpis,owner,position)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id
                        """,
                        (tenant_id, map_id, process_id, capability.id, capability.name, capability.description,
                         capability.tags, capability.kpis, capability.owner, capability_order),
                    )
                    capability_ids[capability.id] = (await cursor.fetchone())["id"]

        for placement in state.placements:
            await connection.execute(
                """
                INSERT INTO business_map_placement
                  (tenant_id,business_map_id,business_map_capability_id,lane_id,source_function_id,maturity)
                VALUES (%s,%s,%s,%s,%s,%s)
                """,
                (
                    tenant_id, map_id, capability_ids[placement.capability_id],
                    stage_ids.get(placement.stage_id) if placement.stage_id else None,
                    function_ids.get(placement.source_function_id) if placement.source_function_id else None,
                    placement.maturity,
                ),
            )
        for group in state.shared_groups:
            cursor = await connection.execute(
                """
                INSERT INTO business_map_shared_group
                  (tenant_id,business_map_id,group_key,name,description,start_lane_id,end_lane_id)
                VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id
                """,
                (tenant_id, map_id, group.id, group.name, group.description,
                 stage_ids.get(group.start_stage_id), stage_ids.get(group.end_stage_id)),
            )
            group_id = (await cursor.fetchone())["id"]
            for capability_id in group.capability_ids:
                await connection.execute(
                    """
                    INSERT INTO business_map_shared_group_member
                      (tenant_id,shared_group_id,business_map_capability_id)
                    VALUES (%s,%s,%s) ON CONFLICT DO NOTHING
                    """,
                    (tenant_id, group_id, capability_ids[capability_id]),
                )
        for assignment in state.function_assignments:
            await connection.execute(
                """
                INSERT INTO business_map_function_assignment
                  (tenant_id,business_map_id,business_map_function_id,lane_id)
                VALUES (%s,%s,%s,%s)
                """,
                (tenant_id, map_id, function_ids[assignment.function_id], unit_ids.get(assignment.unit_id)),
            )

    async def _write_business_map_revision(
        self, connection: Any, *, map_id: UUID, tenant_id: UUID, version: int,
        state: BusinessMapStateModel, actor_key: str,
    ) -> None:
        await connection.execute(
            """
            INSERT INTO business_map_revision
              (tenant_id,business_map_id,version,snapshot,actor_key)
            VALUES (%s,%s,%s,%s::jsonb,%s)
            """,
            (tenant_id, map_id, version, json.dumps(state.model_dump(mode="json")), actor_key),
        )

    async def _business_map_detail(self, connection: Any, map_id: UUID) -> BusinessMapDetail:
        cursor = await connection.execute("SELECT * FROM business_map WHERE id=%s", (map_id,))
        row = await cursor.fetchone()
        if row is None:
            raise APIError(404, "BUSINESS_MAP_NOT_FOUND", "The business map was not found.")

        cursor = await connection.execute(
            "SELECT * FROM business_map_lane WHERE business_map_id=%s ORDER BY lane_kind,position", (map_id,),
        )
        lanes = await cursor.fetchall()
        lane_key_by_id = {lane["id"]: lane["lane_key"] for lane in lanes}
        stages = [self._business_map_lane(lane) for lane in lanes if lane["lane_kind"] == "STAGE"]
        units = [self._business_map_lane(lane) for lane in lanes if lane["lane_kind"] == "ORG_UNIT"]

        cursor = await connection.execute(
            "SELECT * FROM business_map_function WHERE business_map_id=%s ORDER BY position", (map_id,),
        )
        functions = await cursor.fetchall()
        function_key_by_id = {fn["id"]: fn["function_key"] for fn in functions}
        cursor = await connection.execute(
            "SELECT * FROM business_map_process WHERE business_map_id=%s ORDER BY position", (map_id,),
        )
        processes = await cursor.fetchall()
        cursor = await connection.execute(
            "SELECT * FROM business_map_capability WHERE business_map_id=%s ORDER BY position", (map_id,),
        )
        capabilities = await cursor.fetchall()
        capability_key_by_id = {cap["id"]: cap["capability_key"] for cap in capabilities}
        capabilities_by_process: dict[UUID, list[dict[str, Any]]] = defaultdict(list)
        for cap in capabilities:
            capabilities_by_process[cap["business_map_process_id"]].append(cap)
        processes_by_function: dict[UUID, list[dict[str, Any]]] = defaultdict(list)
        for process in processes:
            processes_by_function[process["business_map_function_id"]].append(process)

        catalog = [
            BusinessMapFunctionNode(
                id=fn["function_key"], name=fn["name"], description=fn["description"],
                color=fn["color"], gradient=fn["gradient"], icon=fn["icon"],
                processes=[
                    BusinessMapProcessNode(
                        id=process["process_key"], name=process["name"], description=process["description"],
                        capabilities=[
                            BusinessMapCapabilityNode(
                                id=cap["capability_key"], name=cap["name"], description=cap["description"],
                                tags=list(cap["tags"]), kpis=list(cap["kpis"]), owner=cap["owner"],
                            )
                            for cap in capabilities_by_process.get(process["id"], [])
                        ],
                    )
                    for process in processes_by_function.get(fn["id"], [])
                ],
            )
            for fn in functions
        ]

        cursor = await connection.execute(
            "SELECT * FROM business_map_placement WHERE business_map_id=%s", (map_id,),
        )
        placements = [
            BusinessMapPlacement(
                capability_id=capability_key_by_id[placement["business_map_capability_id"]],
                stage_id=lane_key_by_id.get(placement["lane_id"]) if placement["lane_id"] else None,
                maturity=placement["maturity"],
                source_function_id=function_key_by_id.get(placement["source_function_id"]) if placement["source_function_id"] else None,
            )
            for placement in await cursor.fetchall()
        ]

        cursor = await connection.execute(
            "SELECT * FROM business_map_shared_group WHERE business_map_id=%s ORDER BY created_at", (map_id,),
        )
        groups = await cursor.fetchall()
        cursor = await connection.execute(
            """
            SELECT member.shared_group_id,member.business_map_capability_id
            FROM business_map_shared_group_member member
            JOIN business_map_shared_group grp ON grp.id=member.shared_group_id
            WHERE grp.business_map_id=%s
            """,
            (map_id,),
        )
        members_by_group: dict[UUID, list[str]] = defaultdict(list)
        for member in await cursor.fetchall():
            members_by_group[member["shared_group_id"]].append(
                capability_key_by_id[member["business_map_capability_id"]]
            )
        shared_groups = [
            BusinessMapSharedGroup(
                id=group["group_key"], name=group["name"], description=group["description"],
                capability_ids=members_by_group.get(group["id"], []),
                start_stage_id=lane_key_by_id.get(group["start_lane_id"], ""),
                end_stage_id=lane_key_by_id.get(group["end_lane_id"], ""),
            )
            for group in groups
        ]

        cursor = await connection.execute(
            "SELECT * FROM business_map_function_assignment WHERE business_map_id=%s", (map_id,),
        )
        assignments = [
            BusinessMapFunctionAssignment(
                function_id=function_key_by_id[assignment["business_map_function_id"]],
                unit_id=lane_key_by_id.get(assignment["lane_id"], ""),
            )
            for assignment in await cursor.fetchall()
        ]

        return BusinessMapDetail(
            id=row["id"], map_key=row["map_key"], status=row["status"], version=row["version"],
            created_at=row["created_at"], updated_at=row["updated_at"],
            state=BusinessMapStateModel(
                title=row["title"], view_mode=_VIEW_MODE_FROM_DB[row["view_mode"]],
                template_id=row["template_id"], stages=stages, organization_units=units,
                catalog=catalog, placements=placements, shared_groups=shared_groups,
                function_assignments=assignments,
            ),
        )

    @staticmethod
    def _business_map_lane(lane: dict[str, Any]) -> BusinessMapLane:
        return BusinessMapLane(
            id=lane["lane_key"], label=lane["label"], sublabel=lane["sublabel"],
            color=lane["color"], gradient=lane["gradient"], icon=lane["icon"], order=lane["position"],
        )

    async def phase3_intelligence_metrics(
        self,
        *,
        tenant_id: UUID | None,
    ) -> Phase3IntelligenceMetrics:
        if tenant_id is None:
            raise APIError(400, "TENANT_REQUIRED", "A tenant ID is required for intelligence metrics.")
        candidate_rows = await self.database.fetch_all(
            """
            SELECT review_state,count(*) count FROM modernization_candidate
            WHERE stale_at IS NULL GROUP BY review_state
            """,
            tenant_id=tenant_id,
        )
        recommendation_rows = await self.database.fetch_all(
            """
            SELECT review_state,count(*) count FROM modernization_recommendation
            WHERE stale_at IS NULL GROUP BY review_state
            """,
            tenant_id=tenant_id,
        )
        job_rows = await self.database.fetch_all(
            "SELECT status,count(*) count FROM intelligence_job GROUP BY status",
            tenant_id=tenant_id,
        )
        aggregate = await self.database.fetch_one(
            """
            SELECT
              (SELECT percentile_cont(0.5) WITHIN GROUP (
                 ORDER BY greatest(0,extract(epoch FROM (coalesce(started_at,now())-created_at)))
               ) FROM intelligence_job) queue_lag_p50,
              (SELECT percentile_cont(0.95) WITHIN GROUP (
                 ORDER BY greatest(0,extract(epoch FROM (coalesce(started_at,now())-created_at)))
               ) FROM intelligence_job) queue_lag_p95,
              (SELECT percentile_cont(0.5) WITHIN GROUP (
                 ORDER BY extract(epoch FROM (completed_at-started_at))*1000
               ) FROM intelligence_job WHERE completed_at IS NOT NULL AND started_at IS NOT NULL) latency_p50,
              (SELECT percentile_cont(0.95) WITHIN GROUP (
                 ORDER BY extract(epoch FROM (completed_at-started_at))*1000
               ) FROM intelligence_job WHERE completed_at IS NOT NULL AND started_at IS NOT NULL) latency_p95,
              (SELECT coalesce(sum(greatest(attempt-1,0)),0) FROM intelligence_job) retry_count,
              (SELECT count(*) FROM dead_letter WHERE source_kind='INTELLIGENCE_JOB') dead_letter_count,
              (SELECT count(*) FROM modernization_candidate WHERE stale_at IS NOT NULL) stale_candidates,
              (SELECT count(*) FROM modernization_recommendation WHERE stale_at IS NOT NULL) stale_recommendations,
              (SELECT count(*) FROM ai_model_invocation WHERE tenant_id=%s) model_invocations,
              (SELECT coalesce(sum(actual_cost_usd),0) FROM ai_model_invocation WHERE tenant_id=%s) model_cost,
              (SELECT percentile_cont(0.95) WITHIN GROUP (ORDER BY duration_ms)
                 FROM ai_model_invocation WHERE tenant_id=%s AND duration_ms IS NOT NULL) model_latency_p95,
              (SELECT avg(CASE WHEN cardinality(candidate.supporting_fact_ids)>0 AND impact.id IS NOT NULL
                               THEN 1.0 ELSE 0.0 END)
                 FROM modernization_candidate candidate
                 LEFT JOIN modernization_impact impact
                   ON impact.modernization_candidate_id=candidate.id
                 WHERE candidate.stale_at IS NULL) evidence_completeness,
              (SELECT avg(abs(outcome.actual_call_sites-recommendation.affected_call_sites))
                 FROM modernization_validation_outcome outcome
                 JOIN modernization_recommendation recommendation
                   ON recommendation.id=outcome.modernization_recommendation_id
                 WHERE outcome.actual_call_sites IS NOT NULL) call_site_mae,
              (SELECT avg(abs(outcome.actual_files-recommendation.affected_files))
                 FROM modernization_validation_outcome outcome
                 JOIN modernization_recommendation recommendation
                   ON recommendation.id=outcome.modernization_recommendation_id
                 WHERE outcome.actual_files IS NOT NULL) files_mae,
              (SELECT avg((outcome.actual_effort=recommendation.estimated_effort)::int::numeric)
                 FROM modernization_validation_outcome outcome
                 JOIN modernization_recommendation recommendation
                   ON recommendation.id=outcome.modernization_recommendation_id
                 WHERE outcome.actual_effort IS NOT NULL AND outcome.actual_effort<>'UNKNOWN') effort_accuracy,
              (SELECT avg((validation_status='SUCCEEDED')::int::numeric)
                 FROM modernization_validation_outcome) validation_success
            """,
            (tenant_id, tenant_id, tenant_id),
            tenant_id=tenant_id,
        )
        assert aggregate is not None
        candidate_counts = {row["review_state"]: int(row["count"]) for row in candidate_rows}
        recommendation_counts = {
            row["review_state"]: int(row["count"]) for row in recommendation_rows
        }
        job_counts = {row["status"]: int(row["count"]) for row in job_rows}
        candidate_reviewed = candidate_counts.get("CONFIRMED", 0) + candidate_counts.get("REJECTED", 0)
        recommendation_reviewed = sum(
            recommendation_counts.get(state, 0) for state in ("ACCEPTED", "REJECTED", "DISMISSED")
        )
        return Phase3IntelligenceMetrics(
            as_of=datetime.now(UTC), candidate_counts=candidate_counts,
            recommendation_counts=recommendation_counts, job_counts=job_counts,
            candidate_review_precision=(
                candidate_counts.get("CONFIRMED", 0) / candidate_reviewed
                if candidate_reviewed else None
            ),
            recommendation_acceptance_rate=(
                recommendation_counts.get("ACCEPTED", 0) / recommendation_reviewed
                if recommendation_reviewed else None
            ),
            successful_validation_rate=(
                _number(aggregate["validation_success"]) if aggregate["validation_success"] is not None else None
            ),
            affected_call_site_mae=(
                _number(aggregate["call_site_mae"]) if aggregate["call_site_mae"] is not None else None
            ),
            affected_files_mae=(
                _number(aggregate["files_mae"]) if aggregate["files_mae"] is not None else None
            ),
            effort_band_accuracy=(
                _number(aggregate["effort_accuracy"]) if aggregate["effort_accuracy"] is not None else None
            ),
            evidence_completeness_rate=(
                _number(aggregate["evidence_completeness"])
                if aggregate["evidence_completeness"] is not None else None
            ),
            queue_lag_seconds_p50=(
                _number(aggregate["queue_lag_p50"]) if aggregate["queue_lag_p50"] is not None else None
            ),
            queue_lag_seconds_p95=(
                _number(aggregate["queue_lag_p95"]) if aggregate["queue_lag_p95"] is not None else None
            ),
            job_latency_ms_p50=(
                _number(aggregate["latency_p50"]) if aggregate["latency_p50"] is not None else None
            ),
            job_latency_ms_p95=(
                _number(aggregate["latency_p95"]) if aggregate["latency_p95"] is not None else None
            ),
            retry_count=int(aggregate["retry_count"]),
            dead_letter_count=int(aggregate["dead_letter_count"]),
            stale_candidate_count=int(aggregate["stale_candidates"]),
            stale_recommendation_count=int(aggregate["stale_recommendations"]),
            model_invocation_count=int(aggregate["model_invocations"]),
            model_cost_usd=_number(aggregate["model_cost"]),
            model_latency_ms_p95=(
                _number(aggregate["model_latency_p95"])
                if aggregate["model_latency_p95"] is not None else None
            ),
        )

    @staticmethod
    def _capability_definition(row: dict[str, Any]) -> CapabilityDefinitionModel:
        return CapabilityDefinitionModel(
            key=row["capability_key"],
            name=row.get("capability_name") or row["name"],
            description=row.get("capability_description") or row["description"],
            parent_key=row.get("parent_capability_key"),
            aliases=list(row.get("aliases") or []),
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

    async def _application_related_entities(
        self,
        application_id: UUID,
        tenant_id: UUID | None,
    ) -> list[dict[str, Any]]:
        return await self.database.fetch_all(
            """
            WITH direct AS (
              SELECT r.relationship_type,
                     CASE WHEN r.source_entity_id=%s THEN r.target_entity_id ELSE r.source_entity_id END id
              FROM current_relationship r
              WHERE r.source_entity_id=%s OR r.target_entity_id=%s
            ), repositories AS (
              SELECT d.id FROM direct d JOIN entity e ON e.id=d.id
              WHERE e.namespace='ENTERPRISE' AND e.entity_type='Repository'
                AND d.relationship_type IN ('IMPLEMENTED_BY','IMPLEMENTS','CONTAINS')
            ), repository_related AS (
              SELECT r.relationship_type,
                     CASE WHEN r.source_entity_id=repositories.id
                       THEN r.target_entity_id ELSE r.source_entity_id END id
              FROM repositories JOIN current_relationship r
                ON r.source_entity_id=repositories.id OR r.target_entity_id=repositories.id
              WHERE r.relationship_type IN (
                'DEPENDS_ON','USES','RUNS_ON','DEPLOYED_AS','BUILT_ON','HAS_VERSION'
              )
            ), selected AS (
              SELECT d.id,1 depth FROM direct d JOIN entity e ON e.id=d.id
              WHERE (
                e.namespace='BUSINESS'
                AND d.relationship_type IN ('ENABLED_BY','REQUIRES','PROVIDED_BY','CONTAINS')
              ) OR (
                e.namespace='ENTERPRISE' AND e.entity_type='Repository'
                AND d.relationship_type IN ('IMPLEMENTED_BY','IMPLEMENTS','CONTAINS')
              ) OR (
                e.namespace='DEPLOYMENT'
                AND d.relationship_type IN ('DEPLOYED_AS','RUNS_ON','HOSTED_IN','HOSTED_AT')
              ) OR (
                e.namespace IN ('TECHNOLOGY','OSS')
                AND d.relationship_type IN ('DEPENDS_ON','USES','RUNS_ON','BUILT_ON','HAS_VERSION')
              )
              UNION
              SELECT rr.id,2 FROM repository_related rr JOIN entity e ON e.id=rr.id
              WHERE e.namespace IN ('TECHNOLOGY','OSS','DEPLOYMENT')
            )
            SELECT e.*,min(selected.depth) depth,
                   coalesce(e.last_seen_at,e.updated_at,e.created_at) observed_at
            FROM selected JOIN entity e ON e.id=selected.id
            GROUP BY e.id ORDER BY min(selected.depth),e.namespace,e.entity_type,e.name,e.id
            """,
            (application_id, application_id, application_id),
            tenant_id=tenant_id,
        )

    async def _technology_related_entities(
        self,
        technology_id: UUID,
        tenant_id: UUID | None,
    ) -> list[dict[str, Any]]:
        return await self.database.fetch_all(
            """
            WITH direct AS (
              SELECT r.relationship_type,
                     CASE WHEN r.source_entity_id=%s THEN r.target_entity_id ELSE r.source_entity_id END id
              FROM current_relationship r
              WHERE r.source_entity_id=%s OR r.target_entity_id=%s
            ), repositories AS (
              SELECT d.id FROM direct d JOIN entity e ON e.id=d.id
              WHERE e.namespace='ENTERPRISE' AND e.entity_type='Repository'
                AND d.relationship_type IN ('DEPENDS_ON','USES','RUNS_ON','BUILT_ON','HAS_VERSION')
            ), applications AS (
              SELECT CASE WHEN r.source_entity_id=repositories.id
                       THEN r.target_entity_id ELSE r.source_entity_id END id
              FROM repositories JOIN current_relationship r
                ON r.source_entity_id=repositories.id OR r.target_entity_id=repositories.id
              JOIN entity e ON e.id=CASE WHEN r.source_entity_id=repositories.id
                       THEN r.target_entity_id ELSE r.source_entity_id END
              WHERE e.namespace='ENTERPRISE' AND e.entity_type='Application'
                AND r.relationship_type IN ('IMPLEMENTED_BY','IMPLEMENTS','CONTAINS')
            ), selected AS (
              SELECT d.id,1 depth FROM direct d JOIN entity e ON e.id=d.id
              WHERE (
                e.namespace='ENTERPRISE' AND e.entity_type='Repository'
                AND d.relationship_type IN ('DEPENDS_ON','USES','RUNS_ON','BUILT_ON','HAS_VERSION')
              ) OR (
                e.namespace='ENTERPRISE' AND e.entity_type='Application'
                AND d.relationship_type IN ('DEPENDS_ON','USES','RUNS_ON')
              ) OR (
                e.namespace='TECHNOLOGY'
                AND d.relationship_type IN ('HAS_VERSION','DEPENDS_ON','USES','ALTERNATIVE_TO')
              ) OR (
                e.namespace='OSS'
                AND d.relationship_type IN (
                  'PUBLISHED_BY','PUBLISHES','SAME_AS','ALTERNATIVE_TO',
                  'MIGRATED_TO','DEMONSTRATES'
                )
              )
              UNION SELECT id,2 FROM applications
            )
            SELECT e.*,min(selected.depth) depth,
                   coalesce(e.last_seen_at,e.updated_at,e.created_at) observed_at
            FROM selected JOIN entity e ON e.id=selected.id
            GROUP BY e.id ORDER BY min(selected.depth),e.namespace,e.entity_type,e.name,e.id
            """,
            (technology_id, technology_id, technology_id),
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

    async def _entity_citations_batch(
        self,
        entity_ids: list[UUID],
        tenant_id: UUID | None,
    ) -> dict[UUID, list[Citation]]:
        if not entity_ids:
            return {}
        rows = await self.database.fetch_all(
            """
            WITH matched AS (
              SELECT requested.entity_id,f.id fact_id,
                     coalesce(sa.name,sa.external_key,f.predicate) label,
                     row_number() OVER (
                       PARTITION BY requested.entity_id,f.id ORDER BY ev.observed_at DESC,ev.id
                     ) evidence_rank
              FROM unnest(%s::uuid[]) requested(entity_id)
              JOIN current_fact f
                ON f.subject_entity_id=requested.entity_id OR f.object_entity_id=requested.entity_id
              LEFT JOIN evidence ev ON ev.fact_assertion_id=f.id
              LEFT JOIN source_artifact sa ON sa.id=ev.source_artifact_id
            ), ranked AS (
              SELECT *,row_number() OVER (
                PARTITION BY entity_id ORDER BY fact_id
              ) citation_rank
              FROM matched WHERE evidence_rank=1
            )
            SELECT entity_id,fact_id,label FROM ranked
            WHERE citation_rank<=10 ORDER BY entity_id,citation_rank
            """,
            (entity_ids,),
            tenant_id=tenant_id,
        )
        grouped: dict[UUID, list[Citation]] = {entity_id: [] for entity_id in entity_ids}
        for row in rows:
            grouped[row["entity_id"]].append(Citation(
                fact_id=row["fact_id"],
                label=row["label"],
                href=f"/api/v1/facts/{row['fact_id']}/evidence",
            ))
        return grouped

    async def _recommendation_citations_batch(
        self,
        recommendation_ids: list[UUID],
        tenant_id: UUID | None,
    ) -> dict[UUID, list[Citation]]:
        if not recommendation_ids:
            return {}
        rows = await self.database.fetch_all(
            """
            SELECT DISTINCT ON (re.recommendation_id,f.id)
                   re.recommendation_id,f.id fact_id,
                   coalesce(sa.name,sa.external_key,f.predicate) label
            FROM recommendation_evidence re JOIN fact_assertion f ON f.id=re.fact_assertion_id
            LEFT JOIN evidence e ON e.fact_assertion_id=f.id
            LEFT JOIN source_artifact sa ON sa.id=e.source_artifact_id
            WHERE re.recommendation_id=ANY(%s::uuid[])
            ORDER BY re.recommendation_id,f.id,e.observed_at DESC
            """,
            (recommendation_ids,),
            tenant_id=tenant_id,
        )
        grouped: dict[UUID, list[Citation]] = {
            recommendation_id: [] for recommendation_id in recommendation_ids
        }
        for row in rows:
            grouped[row["recommendation_id"]].append(Citation(
                fact_id=row["fact_id"],
                label=row["label"],
                href=f"/api/v1/facts/{row['fact_id']}/evidence",
            ))
        return grouped

    @staticmethod
    def _dedupe_entities(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return list({row["id"]: row for row in rows}.values())

    @staticmethod
    def _dedupe_citations(citations: list[Citation]) -> list[Citation]:
        return list({citation.fact_id: citation for citation in citations}.values())
