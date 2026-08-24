from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import re
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, Mapping
from uuid import NAMESPACE_URL, UUID, uuid5

import httpx
from stackgraph_graph_intelligence.embeddings import (
    LocalHashEmbeddingAdapter,
    OpenAICompatibleEmbeddingAdapter,
    TOKEN_PATTERN,
    content_hash as embedding_content_hash,
    vector_literal,
)
from stackgraph_ai.governance import (
    CapabilityFootprint as GovernedCapabilityFootprint,
    PortfolioCandidate,
    PortfolioScoringPolicy,
    optimize_portfolio,
    score_portfolio_candidate,
)

from app.age_graph import AgeGraphReader, AgeTopology
from app.architecture_catalog import load_architecture_catalog, sha256_fingerprint
from app.database import Database
from app.deterministic_insights import invalidate_deterministic_insight_cache
from app.deterministic_insights import list_deterministic_insights
from app.enterprise_posture_insights import (
    ASSURANCE_COVERAGE,
    POSTURE_INSIGHT_REPORTS,
    answer_posture_report,
    assurance_report_presentation,
    match_posture_question,
    posture_report_readiness,
)
from app.errors import APIError
from app.neo4j_graph import Neo4jGraphReader, Neo4jTopology
from app.read_models_admin import AdminReadModelsMixin
from app.models import (
    ApplicationDetail,
    ApplicationSimilarityCandidate,
    ApplicationSimilarityList,
    ApplicationSimilarityReviewRequest,
    ApplicationSimilarityReviewResult,
    ApplicationComponentDependencyHierarchy,
    ApplicationDependencyNode,
    ApplicationRepositoryDependencyHierarchy,
    ApplicationTechnologyFunction,
    ApplicationTechnologyGroup,
    ApplicationTechnologyResourceDetails,
    ApplicationTechnologyUsage,
    AIProviderConfiguration,
    AIProviderConfigurationUpdateRequest,
    AIProviderConnectionTest,
    AskRequest,
    AskResponse,
    AssessmentSummary,
    BusinessMapApplicationAssignment,
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
    ArchitectureProfileStateModel,
    ArchitectureReferenceModel,
    ArchitectureReferenceModelList,
    ArchitectureTaxonomyResponse,
    CanvasCellComparisonModel,
    CanvasCellMeasuresModel,
    CanvasCellProjectionModel,
    CanvasClassificationTrayItemModel,
    CanvasClassificationTrayModel,
    CanvasComparison,
    CanvasComparisonRequest,
    CanvasComparisonSummaryModel,
    CanvasOccupantModel,
    CanvasProjection,
    CanvasProjectionSelectorModel,
    CanvasProjectionSummaryModel,
    CanvasTemplateList,
    CellExpectationModel,
    CellObservationStatusModel,
    MeasureResultModel,
    TenantCellPolicyModel,
    CapabilityDefinitionModel,
    CapabilityInferenceReviewRequest,
    CapabilityInferenceReviewResult,
    CapabilityInferenceSummary,
    CapabilityTaxonomyResponse,
    CapabilityFootprintList,
    CapabilityFootprintModel,
    Citation,
    Coverage,
    DuplicateCapabilityReviewRequest,
    DuplicateCapabilityReviewResult,
    DuplicateCapabilityCandidateSummary,
    EmbeddingSpaceSnapshot,
    EmbeddingStatus,
    DeterministicInsightList,
    EnterpriseInsightReport,
    EnterpriseInsightReportList,
    EntitySummary,
    EstateCounts,
    EstateSummary,
    EvidenceDetail,
    Extractor,
    Freshness,
    GraphEdge,
    GraphAnalysisSnapshot,
    GraphBlastRadius,
    GraphCommunity,
    GraphCommunityList,
    GraphAnomaly,
    GraphAnomalyList,
    GraphMotif,
    GraphMotifList,
    CriticalGraphEdge,
    CriticalGraphEdgeList,
    GraphImpactPath,
    GraphIntelligenceStatus,
    GraphMetric,
    GraphNeighborhood,
    GraphNode,
    GraphRiskItem,
    GraphRiskList,
    IdentityReviewRequest,
    IdentityReviewResult,
    InternalUsage,
    EntityGraphIntelligence,
    ModernizationList,
    ModernizationScenarioItem,
    ModernizationScenarioRequest,
    ModernizationScenarioResult,
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
    RepositoryDetail,
    RepositoryProfile,
    RepositoryModernizationIntelligence,
    Phase3IntelligenceMetrics,
    Score,
    TechnologyEstateHierarchy,
    TechnologyEstateHierarchyNode,
    TechnologyCatalogProfile,
    TechnologyDetail,
    ReviewQueue,
    ReviewQueueItem,
    ReviewQueueItemType,
    TenantMember,
    TenantMemberList,
    TaxonomySummary,
    MemberInviteRequest,
    MemberUpdateRequest,
    Connector,
    ConnectorList,
    ConnectorRegisterRequest,
    GitHubRepositoryConnectRequest,
    ConnectorUpdateRequest,
    ScanPolicy,
    ScanPolicyUpdateRequest,
    RescanRequest,
    RescanJob,
    RescanJobList,
    ProviderQuota,
    ScanStatus,
    SemanticSearchHit,
    SemanticSearchRequest,
    SemanticSearchResponse,
)


CONTRACT_VERSION = "1.0.0"
MAX_GRAPH_NODES = 50
CANVAS_PROJECTION_METHOD_VERSION = "architecture-canvas-projection/v1"
CANVAS_COMPARISON_METHOD_VERSION = "architecture-canvas-comparison/v1"
CANVAS_OBSERVATION_METHOD_VERSION = "architecture-observation/v1"
CANVAS_MEASURE_METHOD_VERSION = "architecture-measures/v1"
CANVAS_CLASSIFICATION_TRAY_LIMIT = 200
logger = logging.getLogger(__name__)

# The DB stores uppercase enums; the API contract and UI use the workspace's kebab form.
_VIEW_MODE_TO_DB = {"value-chain": "VALUE_CHAIN", "organization": "ORGANIZATION"}
_VIEW_MODE_FROM_DB = {value: key for key, value in _VIEW_MODE_TO_DB.items()}

_ENTERPRISE_INSIGHT_REPORTS: tuple[dict[str, str], ...] = (
    {
        "key": "systemic_dependency_risk", "title": "Systemic dependency risk",
        "category": "ENTERPRISE_RISK", "metric_label": "highest risk score",
        "question": "Show me the top 20 dependencies representing systemic enterprise risk.",
        "populated_status": "ACTION_REQUIRED", "metric_field": "risk_score",
    },
    {
        "key": "reachable_vulnerabilities", "title": "Reachable Tier-1 vulnerabilities",
        "category": "ENTERPRISE_RISK", "metric_label": "reachable impact paths",
        "question": "Which vulnerabilities are actually reachable in production Tier-1 applications?",
        "populated_status": "ACTION_REQUIRED", "metric_field": "row_count",
        "empty_requires_data": "true",
    },
    {
        "key": "package_business_blast_radius", "title": "Largest package blast radius",
        "category": "ENTERPRISE_RISK", "metric_label": "enterprise impact groups",
        "question": "Which package has the largest governed business-capability blast radius?",
        "populated_status": "WATCH", "metric_field": "row_count", "empty_requires_data": "true",
        "requires_mapped_rows": "true",
    },
    {
        "key": "duplicate_capability_implementations", "title": "Duplicated capabilities",
        "category": "TECHNOLOGY_RATIONALIZATION", "metric_label": "duplicated capabilities",
        "question": "Where have teams independently implemented the same capability?",
        "populated_status": "WATCH", "metric_field": "row_count",
    },
    {
        "key": "technology_diversity", "title": "Unnecessary technology diversity",
        "category": "TECHNOLOGY_RATIONALIZATION", "metric_label": "diverse package categories",
        "question": "Which package categories have the most unnecessary technology diversity?",
        "populated_status": "WATCH", "metric_field": "row_count",
    },
    {
        "key": "modernization_blockers", "title": "Modernization blockers",
        "category": "TECHNOLOGY_RATIONALIZATION", "metric_label": "unsupported blockers",
        "question": "Which unsupported dependencies block our Node/Python/.NET modernization?",
        "populated_status": "ACTION_REQUIRED", "metric_field": "row_count",
        "empty_requires_data": "true",
    },
    {
        "key": "custom_to_internal_platform", "title": "Internal platform replacements",
        "category": "TECHNOLOGY_RATIONALIZATION", "metric_label": "replacement candidates",
        "question": "Which custom implementations should be replaced by existing internal platforms?",
        "populated_status": "WATCH", "metric_field": "row_count", "empty_requires_data": "true",
    },
    {
        "key": "internal_library_standards", "title": "Enterprise library standards",
        "category": "PORTFOLIO_DECISIONS", "metric_label": "standard candidates",
        "question": "Which internal libraries should become enterprise standards?",
        "populated_status": "WATCH", "metric_field": "row_count", "empty_requires_data": "true",
    },
    {
        "key": "application_retirement_consolidation", "title": "Retirement & consolidation",
        "category": "PORTFOLIO_DECISIONS", "metric_label": "portfolio candidates",
        "question": "What are our best application retirement/consolidation candidates?",
        "populated_status": "WATCH", "metric_field": "row_count", "empty_requires_data": "true",
    },
    {
        "key": "standardization_initiatives", "title": "Standardization payoff",
        "category": "PORTFOLIO_DECISIONS", "metric_label": "highest payoff score",
        "question": "What are the 10 engineering standardization initiatives with the largest enterprise payoff?",
        "populated_status": "ACTION_REQUIRED", "metric_field": "enterprise_payoff",
        "empty_requires_data": "true",
    },
) + POSTURE_INSIGHT_REPORTS

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

# Catalog entities are globally visible so they can enrich every tenant's graph.  They only
# become part of a tenant's estate after tenant-scoped evidence connects them directly to a
# tenant-owned enterprise entity.  Keeping this boundary in SQL prevents the global OSS
# catalog from inflating estate counts and lists, even for database roles that bypass RLS.
_OBSERVED_TECHNOLOGY_CTE = """
WITH tenant_scope AS (
  SELECT %s::uuid tenant_id
), observed_technology AS (
  SELECT technology.id,
         min(CASE
           WHEN relationship.relationship_type<>'DEPENDS_ON'
             OR relationship.properties->>'direct' IS NULL
             OR lower(relationship.properties->>'direct')='true'
           THEN 1 ELSE 2 END) dependency_tier
  FROM current_relationship relationship
  JOIN entity technology
    ON technology.id IN (relationship.source_entity_id,relationship.target_entity_id)
   AND technology.namespace IN ('TECHNOLOGY','OSS')
   AND technology.entity_type<>'Capability'
  JOIN entity estate_entity
    ON estate_entity.id=CASE
      WHEN technology.id=relationship.source_entity_id
        THEN relationship.target_entity_id
      ELSE relationship.source_entity_id
    END
   AND estate_entity.namespace='ENTERPRISE'
   AND estate_entity.tenant_id=(SELECT tenant_id FROM tenant_scope)
  WHERE relationship.tenant_id=(SELECT tenant_id FROM tenant_scope)
  GROUP BY technology.id
)
"""


def _number(value: Decimal | float | int | None, default: float = 0.0) -> float:
    return float(value) if value is not None else default


def _optional_string(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


# The per-source submission endpoint for each review-queue item type, so the queue can point
# the UI straight at the route that accepts a decision without the client hard-coding the map.
_REVIEW_PATHS: dict[str, str] = {
    "IDENTITY_ASSERTION": "/identity-assertions/{id}/review",
    "CAPABILITY_INFERENCE": "/capability-inferences/{id}/review",
    "DUPLICATE_CAPABILITY": "/duplicate-capability-candidates/{id}/review",
    "MODERNIZATION_CANDIDATE": "/modernization-candidates/{id}/review",
    "MODERNIZATION_RECOMMENDATION": "/modernization-recommendations/{id}/review",
}

# A registered credential must be a reference into the secret store, never the secret itself.
# These prefixes catch the most common raw-token pastes so they are rejected at the boundary.
_RAW_SECRET_MARKERS: tuple[str, ...] = (
    "ghp_", "gho_", "ghu_", "ghs_", "ghr_", "github_pat_", "xox", "-----BEGIN", "AKIA",
)


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
        properties = row["properties"]
        catalog_metadata = properties.get("catalog_metadata")
        summary = properties.get("purpose") or properties.get("definition")
        if summary is None and isinstance(catalog_metadata, dict):
            summary = catalog_metadata.get("description")
    return EntitySummary(
        id=row["id"],
        kind=row["entity_type"],
        name=row["name"],
        canonical_key=row.get("canonical_key"),
        summary=summary,
    )


_TECHNOLOGY_DOMAIN_ORDER = {
    "frontend": 0,
    "middleware": 1,
    "backend": 2,
    "data": 3,
    "deployment": 4,
    "unclassified": 5,
}
_CLASSIFIABLE_TECHNOLOGY_DOMAINS = frozenset(_TECHNOLOGY_DOMAIN_ORDER) - {"unclassified"}


def _taxonomy_name(key: str) -> str:
    return key.replace("-", " ").replace("_", " ").strip().title()


def _string_list(value: object) -> list[str]:
    return [str(item) for item in value] if isinstance(value, list) else []


def _dedupe_summaries(values: list[EntitySummary]) -> list[EntitySummary]:
    return list({value.id: value for value in values}.values())


def _integer(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return None


def _usage_citations(row: dict[str, Any], *extra_fact_ids: UUID | None) -> list[Citation]:
    usage_fact_ids = list(dict.fromkeys(
        UUID(str(value)) for value in _string_list(row.get("usage_fact_ids"))
    ))
    classification_fact_ids = [
        fact_id for fact_id in dict.fromkeys(extra_fact_ids)
        if fact_id is not None and fact_id not in usage_fact_ids
    ]
    return [
        Citation(
            fact_id=fact_id,
            label="Technology usage",
            href=f"/api/v1/facts/{fact_id}/evidence",
        )
        for fact_id in usage_fact_ids
    ] + [
        Citation(
            fact_id=fact_id,
            label="Catalog classification",
            href=f"/api/v1/facts/{fact_id}/evidence",
        )
        for fact_id in classification_fact_ids
    ]


def _technology_lookup_keys(row: dict[str, Any]) -> set[str]:
    properties = row.get("properties") if isinstance(row.get("properties"), dict) else {}
    keys = {
        str(value).strip().lower()
        for value in _string_list(properties.get("catalog_lookup_keys"))
        if str(value).strip()
    }
    package_name = properties.get("package_name")
    catalog_metadata = properties.get("catalog_metadata")
    if isinstance(catalog_metadata, dict):
        package_name = package_name or catalog_metadata.get("package_name")
    if isinstance(package_name, str) and package_name.strip():
        normalized_package = package_name.strip().lower()
        keys.add(normalized_package)
        if "/" in normalized_package:
            keys.add(normalized_package.rsplit("/", 1)[-1])
    canonical_key = row.get("canonical_key")
    if isinstance(canonical_key, str) and canonical_key.startswith("pkg:npm/"):
        coordinate = canonical_key.removeprefix("pkg:npm/").split("?", 1)[0].split("#", 1)[0]
        if coordinate.startswith("@"):
            package_parts = coordinate.split("/")
            if len(package_parts) >= 2:
                keys.add(f"{package_parts[0]}/{package_parts[1].split('@', 1)[0]}".lower())
        else:
            keys.add(coordinate.split("@", 1)[0].lower())
    if row.get("entity_type") == "Technology":
        names = [row.get("name"), *_string_list(properties.get("aliases"))]
        for name in names:
            if not isinstance(name, str):
                continue
            # A slash separates products in legacy comparison-group names, but
            # it is part of the identity of a scoped npm package or pattern.
            parts = [name] if name.strip().startswith("@") else name.split("/")
            for part in parts:
                normalized_name = re.sub(r"\s*\([^)]*\)\s*", " ", part).strip().lower()
                if normalized_name:
                    keys.add(normalized_name)
    return keys


def _technology_catalog_index(
    catalog_rows: list[dict[str, Any]],
) -> tuple[dict[UUID, dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    catalog_by_id: dict[UUID, dict[str, Any]] = {}
    for row in catalog_rows:
        technology_id = UUID(str(row["id"]))
        entry = catalog_by_id.setdefault(technology_id, {"row": row, "capabilities": []})
        if row.get("capability_id") is not None:
            entry["capabilities"].append(row)

    catalog_by_key: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for technology_id, entry in catalog_by_id.items():
        for key in _technology_lookup_keys(entry["row"]):
            if all(UUID(str(candidate["row"]["id"])) != technology_id for candidate in catalog_by_key[key]):
                catalog_by_key[key].append(entry)
    return catalog_by_id, catalog_by_key


def _resolve_technology_catalog_entry(
    technology_row: dict[str, Any],
    catalog_by_id: dict[UUID, dict[str, Any]],
    catalog_by_key: dict[str, list[dict[str, Any]]],
) -> tuple[dict[str, Any] | None, bool]:
    technology_id = UUID(str(technology_row["id"]))
    direct = catalog_by_id.get(technology_id)
    technology_keys = _technology_lookup_keys(technology_row)
    exact_matches = {
        UUID(str(entry["row"]["id"])): entry
        for key in technology_keys
        for entry in catalog_by_key.get(key, [])
    }
    if direct is not None or exact_matches:
        return (
            direct or (next(iter(exact_matches.values())) if len(exact_matches) == 1 else None),
            direct is not None,
        )

    wildcard_matches = {
        UUID(str(entry["row"]["id"])): entry
        for key in technology_keys
        for pattern, entries in catalog_by_key.items()
        if pattern != "*" and pattern.endswith("*") and key.startswith(pattern[:-1])
        for entry in entries
    }
    return (
        next(iter(wildcard_matches.values())) if len(wildcard_matches) == 1 else None,
        False,
    )


def _technology_catalog_profiles(
    technology_rows: list[dict[str, Any]],
    catalog_rows: list[dict[str, Any]],
    metadata_rows: list[dict[str, Any]],
) -> dict[UUID, TechnologyCatalogProfile]:
    catalog_by_id, catalog_by_key = _technology_catalog_index(catalog_rows)
    metadata_by_id = {
        UUID(str(row["selected_technology_id"])): row
        for row in metadata_rows
    }
    profiles: dict[UUID, TechnologyCatalogProfile] = {}
    for technology_row in technology_rows:
        technology_id = UUID(str(technology_row["id"]))
        metadata_row = metadata_by_id.get(technology_id)
        metadata = (
            metadata_row.get("catalog_properties", {}).get("catalog_metadata", {})
            if metadata_row and isinstance(metadata_row.get("catalog_properties"), dict)
            else {}
        )
        resolved, direct = _resolve_technology_catalog_entry(
            technology_row, catalog_by_id, catalog_by_key,
        )
        properties = resolved["row"].get("properties", {}) if resolved else {}
        domain_key = str(properties.get("domain_id") or "")
        if domain_key not in _CLASSIFIABLE_TECHNOLOGY_DOMAINS:
            resolved = None
            direct = False
            properties = {}
            domain_key = ""
        if not metadata and resolved is None:
            continue

        domain = (
            TaxonomySummary(
                key=domain_key,
                name=str(properties.get("domain_name") or _taxonomy_name(domain_key)),
            )
            if resolved else None
        )
        category = None
        if resolved and properties.get("category_id"):
            category_key = str(properties["category_id"])
            category = TaxonomySummary(
                key=category_key,
                name=str(properties.get("category_name") or _taxonomy_name(category_key)),
            )
        functions = []
        seen_functions: set[str] = set()
        for capability in resolved["capabilities"] if resolved else []:
            function_key = str(capability.get("capability_key") or "").strip()
            if not function_key or function_key in seen_functions:
                continue
            seen_functions.add(function_key)
            functions.append(TaxonomySummary(
                key=function_key,
                name=str(capability.get("capability_name") or _taxonomy_name(function_key)),
                summary=capability.get("capability_summary"),
            ))
        citations: list[Citation] = []
        if metadata_row and metadata_row.get("catalog_fact_id") is not None:
            fact_id = UUID(str(metadata_row["catalog_fact_id"]))
            citations.append(Citation(
                fact_id=fact_id,
                label="OSS catalog metadata",
                href=f"/api/v1/facts/{fact_id}/evidence",
            ))
        if resolved and resolved["row"].get("catalog_fact_id") is not None:
            fact_id = UUID(str(resolved["row"]["catalog_fact_id"]))
            if all(citation.fact_id != fact_id for citation in citations):
                citations.append(Citation(
                    fact_id=fact_id,
                    label="Catalog classification",
                    href=f"/api/v1/facts/{fact_id}/evidence",
                ))
        for capability in resolved["capabilities"] if resolved else []:
            if capability.get("classification_fact_id") is None:
                continue
            fact_id = UUID(str(capability["classification_fact_id"]))
            if all(citation.fact_id != fact_id for citation in citations):
                citations.append(Citation(
                    fact_id=fact_id,
                    label="Catalog classification",
                    href=f"/api/v1/facts/{fact_id}/evidence",
                ))
        if not citations:
            continue

        classification = "UNCLASSIFIED"
        if resolved is not None:
            classification = "CURATED" if direct else "CATALOG_MATCH"
        profiles[technology_id] = TechnologyCatalogProfile(
            summary=(
                metadata.get("description")
                or properties.get("purpose")
                or properties.get("definition")
            ),
            package_name=metadata.get("package_name"),
            ecosystem=metadata.get("ecosystem"),
            license=metadata.get("license"),
            homepage=metadata.get("homepage"),
            repository_url=metadata.get("repository"),
            package_url=metadata.get("package_url"),
            latest_version=metadata.get("latest_version"),
            weekly_downloads=_integer(metadata.get("weekly_downloads")),
            dependents=_integer(metadata.get("dependents")),
            versions=_integer(metadata.get("versions")),
            installation_command=metadata.get("installation_command"),
            catalog_technology=_entity(resolved["row"]) if resolved else None,
            domain=domain,
            category=category,
            functions=functions,
            classification=classification,
            citations=citations,
        )
    return profiles


def _application_resource_details(
    technology_row: Mapping[str, Any],
) -> tuple[ApplicationTechnologyResourceDetails | None, tuple[str, str]]:
    raw_property_sets = technology_row.get("usage_property_sets")
    property_sets = (
        [value for value in raw_property_sets if isinstance(value, Mapping)]
        if isinstance(raw_property_sets, list) else []
    )
    if not property_sets and isinstance(technology_row.get("usage_properties"), Mapping):
        property_sets = [technology_row["usage_properties"]]

    resource_sets = [
        value for value in property_sets
        if str(value.get("resource_kind") or "").upper() in {"DATABASE", "STORAGE"}
    ]
    entity_type = str(technology_row.get("entity_type") or "")
    if not resource_sets and entity_type not in {"Database", "Storage"}:
        return None, ("", "")

    def strings(key: str) -> list[str]:
        return sorted({
            str(item)
            for properties in resource_sets
            for item in (properties.get(key) if isinstance(properties.get(key), list) else [])
            if str(item).strip()
        })

    engine = next((
        str(properties["engine"]).strip()
        for properties in resource_sets
        if isinstance(properties.get("engine"), str) and str(properties["engine"]).strip()
    ), str(technology_row.get("name") or "unknown").strip())
    raw_kind = next((
        str(properties.get("resource_kind") or "").upper()
        for properties in resource_sets
        if properties.get("resource_kind")
    ), entity_type.upper())
    canonical_key = str(technology_row.get("canonical_key") or "").casefold()
    if raw_kind == "STORAGE" or entity_type == "Storage":
        resource_kind = "OBJECT_STORAGE"
        category = ("object-storage", "Object storage")
    elif engine.casefold() in {"redis", "valkey"} or "redis-valkey" in canonical_key:
        resource_kind = "CACHE"
        category = ("caches", "Caches")
    else:
        resource_kind = "DATABASE"
        category = ("databases", "Databases")

    assertion_classes = {
        str(value).upper()
        for value in (technology_row.get("usage_assertion_classes") or [])
        if str(value).upper() in {
            "DECLARED", "OBSERVED", "INFERRED", "CURATED", "EXTERNAL_MEASURED",
        }
    }
    assertion_class = next(
        (value for value in (
            "CURATED", "DECLARED", "OBSERVED", "EXTERNAL_MEASURED", "INFERRED",
        ) if value in assertion_classes),
        "INFERRED",
    )
    inference_method = next((
        str(properties["inference_method"])
        for properties in resource_sets
        if isinstance(properties.get("inference_method"), str)
    ), None)
    return ApplicationTechnologyResourceDetails(
        resource_kind=resource_kind,
        engine=engine,
        providers=strings("providers"),
        signal_kinds=strings("signal_kinds"),
        package_dependencies=strings("package_dependencies"),
        config_keys=strings("config_keys"),
        source_referenced=any(bool(value.get("source_referenced")) for value in resource_sets),
        inference_method=inference_method,
        assertion_class=assertion_class,
        limitations=strings("limitations"),
    ), category


def _group_application_technologies(
    technology_rows: list[dict[str, Any]],
    catalog_rows: list[dict[str, Any]],
) -> list[ApplicationTechnologyGroup]:
    catalog_by_id, catalog_by_key = _technology_catalog_index(catalog_rows)

    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for technology_row in technology_rows:
        technology_id = UUID(str(technology_row["id"]))
        usage_confidence = _number(technology_row.get("usage_confidence"), 1.0)
        resource_details, resource_category = _application_resource_details(technology_row)
        resolved = None
        if resource_details is not None:
            direct = None
            properties: dict[str, Any] = {}
            domain_key = "data"
            domain_name = "Data infrastructure"
            classification = "DETERMINISTIC"
            classification_factor = 1.0
            category = TaxonomySummary(
                key=resource_category[0], name=resource_category[1],
            )
            capabilities = [{
                "capability_key": category.key,
                "capability_name": category.name,
                "capability_summary": "Detected from repository code and infrastructure evidence.",
                "classification_fact_id": None,
                "classification_confidence": 1.0,
            }]
        else:
            resolved, is_direct_catalog = _resolve_technology_catalog_entry(
                technology_row, catalog_by_id, catalog_by_key,
            )
            direct = resolved if is_direct_catalog else None
            properties = resolved["row"].get("properties", {}) if resolved else {}
            domain_key = str(properties.get("domain_id") or "unclassified")
            if domain_key not in _CLASSIFIABLE_TECHNOLOGY_DOMAINS:
                resolved = None
                domain_key = "unclassified"

            classification = "UNCLASSIFIED"
            classification_factor = 0.0
            if resolved is not None:
                classification = "CURATED" if direct is not None else "CATALOG_MATCH"
                classification_factor = 1.0 if direct is not None else 0.85
            domain_name = (
                str(properties.get("domain_name") or _taxonomy_name(domain_key))
                if resolved else "Unclassified"
            )
            category = None
            if resolved is not None and properties.get("category_id"):
                category_key = str(properties["category_id"])
                category = TaxonomySummary(
                    key=category_key,
                    name=str(properties.get("category_name") or _taxonomy_name(category_key)),
                )

            capabilities = list(resolved["capabilities"]) if resolved else []
            if not capabilities:
                capabilities = [{
                    "capability_key": category.key if category else "unclassified",
                    "capability_name": category.name if category else "Function not yet classified",
                    "capability_summary": None,
                    "classification_fact_id": None,
                    "classification_confidence": classification_factor,
                }]

        for capability in capabilities:
            function_key = str(capability.get("capability_key") or "unclassified")
            function_name = str(capability.get("capability_name") or _taxonomy_name(function_key))
            confidence = min(
                usage_confidence,
                classification_factor,
                _number(capability.get("classification_confidence"), classification_factor),
            )
            citations = _usage_citations(
                technology_row,
                resolved["row"].get("catalog_fact_id") if resolved else None,
                capability.get("classification_fact_id"),
            )
            if not citations:
                continue
            group_key = (domain_key, function_key)
            bucket = grouped.setdefault(group_key, {
                "domain": TaxonomySummary(key=domain_key, name=domain_name),
                "function": TaxonomySummary(
                    key=function_key,
                    name=function_name,
                    summary=capability.get("capability_summary"),
                ),
                "technologies": {},
            })
            bucket["technologies"][technology_id] = ApplicationTechnologyUsage(
                technology=_entity(technology_row),
                category=category,
                classification=classification,
                confidence=confidence,
                confidence_label=_confidence_label(confidence),
                resource_details=resource_details,
                citations=citations,
            )

    domains: dict[str, dict[str, Any]] = {}
    for (domain_key, _function_key), bucket in grouped.items():
        domain = domains.setdefault(domain_key, {"domain": bucket["domain"], "functions": []})
        domain["functions"].append(ApplicationTechnologyFunction(
            function=bucket["function"],
            technologies=sorted(
                bucket["technologies"].values(),
                key=lambda item: (item.technology.name.lower(), str(item.technology.id)),
            ),
        ))
    return [
        ApplicationTechnologyGroup(
            domain=value["domain"],
            functions=sorted(
                value["functions"],
                key=lambda item: (item.function.name.lower(), item.function.key),
            ),
        )
        for key, value in sorted(
            domains.items(),
            key=lambda item: (
                _TECHNOLOGY_DOMAIN_ORDER.get(item[0], 99),
                item[1]["domain"].name.lower(),
            ),
        )
    ]


def _canvas_policy_applies(
    policy: TenantCellPolicyModel,
    scope: str,
    subject_id: UUID | None,
    as_of: datetime,
) -> bool:
    if policy.effective_from is not None and as_of < policy.effective_from:
        return False
    if policy.effective_to is not None and as_of >= policy.effective_to:
        return False
    selector = policy.scope_selector
    scoped = bool(selector.application_ids or selector.repository_ids or selector.tags)
    if not scoped:
        return True
    if selector.tags:
        return False  # Tag-scoped profiles remain inactive until tag facts are projected.
    if scope == "APPLICATION":
        return subject_id in selector.application_ids
    if scope == "REPOSITORY":
        return subject_id in selector.repository_ids
    return False


def _canvas_policy_status(
    technology_id: UUID,
    policy: TenantCellPolicyModel | None,
    subject_id: UUID | None,
    as_of: datetime,
) -> str:
    if policy is None:
        return "UNGOVERNED"
    if subject_id is not None and any(
        subject_id in exception.subject_ids
        and (exception.effective_from is None or as_of >= exception.effective_from)
        and (exception.effective_to is None or as_of < exception.effective_to)
        for exception in policy.exceptions
    ):
        return "EXEMPTED"
    if technology_id in policy.preferred_technology_ids:
        return "PREFERRED"
    if technology_id in policy.allowed_technology_ids:
        return "ALLOWED"
    if technology_id in policy.discouraged_technology_ids:
        return "DISCOURAGED"
    if technology_id in policy.prohibited_technology_ids:
        return "PROHIBITED"
    return "UNGOVERNED"


def _canvas_measure_result(
    *,
    value: float | None,
    status: str,
    inputs: list[str],
    supporting_fact_ids: list[UUID],
    method: str,
) -> MeasureResultModel:
    return MeasureResultModel(
        value=value,
        status=status,
        inputs=inputs,
        supporting_fact_ids=list(dict.fromkeys(supporting_fact_ids)),
        method_version=method,
    )


def _canvas_cell_measures(
    *,
    state: str,
    expectation: CellExpectationModel,
    policy: TenantCellPolicyModel | None,
    occupants: list[CanvasOccupantModel],
    observation: CellObservationStatusModel,
) -> CanvasCellMeasuresModel:
    fact_ids = [citation.fact_id for item in occupants for citation in item.citations]
    eligible_values: list[float] = []
    missing_inputs: list[str] = []

    if expectation.applicability == "NOT_APPLICABLE" or state == "NOT_APPLICABLE":
        coverage = _canvas_measure_result(
            value=None, status="NOT_APPLICABLE", inputs=["cell applicability"],
            supporting_fact_ids=[], method="architecture-coverage/v1",
        )
    elif state in {"UNOBSERVED", "UNBOUND"}:
        status = "NOT_CONFIGURED" if state == "UNBOUND" else "INSUFFICIENT_DATA"
        coverage = _canvas_measure_result(
            value=None, status=status,
            inputs=["effective expectation", "observation completeness"],
            supporting_fact_ids=[], method="architecture-coverage/v1",
        )
        missing_inputs.extend(observation.missing_inputs or ["observation completeness"])
    elif expectation.minimum_implementations in (None, 0):
        coverage = _canvas_measure_result(
            value=None, status="NOT_CONFIGURED",
            inputs=["minimum implementation expectation"],
            supporting_fact_ids=fact_ids, method="architecture-coverage/v1",
        )
    else:
        minimum = expectation.minimum_implementations
        assert minimum is not None and minimum > 0
        coverage_value = min(100.0, 100.0 * len(occupants) / minimum)
        coverage = _canvas_measure_result(
            value=coverage_value, status="ELIGIBLE",
            inputs=[f"minimum implementations: {minimum}", f"observed implementations: {len(occupants)}"],
            supporting_fact_ids=fact_ids, method="architecture-coverage/v1",
        )
        eligible_values.append(coverage_value)

    diversity = len({item.technology.id for item in occupants})
    if expectation.applicability == "NOT_APPLICABLE":
        standardisation = _canvas_measure_result(
            value=None, status="NOT_APPLICABLE", inputs=["cell applicability"],
            supporting_fact_ids=[], method="architecture-standardisation/v1",
        )
    elif observation.observed_subjects < 3:
        standardisation = _canvas_measure_result(
            value=None, status="INSUFFICIENT_DATA",
            inputs=[f"observed subjects: {observation.observed_subjects}", "minimum subjects: 3"],
            supporting_fact_ids=fact_ids, method="architecture-standardisation/v1",
        )
        missing_inputs.append("at least three observed subjects for standardisation")
    elif expectation.allowed_diversity is None:
        standardisation = _canvas_measure_result(
            value=None, status="NOT_CONFIGURED", inputs=["allowed diversity expectation"],
            supporting_fact_ids=fact_ids, method="architecture-standardisation/v1",
        )
    else:
        excess = max(0, diversity - expectation.allowed_diversity)
        standardisation_value = max(0.0, 100.0 - 25.0 * excess)
        standardisation = _canvas_measure_result(
            value=standardisation_value, status="ELIGIBLE",
            inputs=[
                f"unique implementations: {diversity}",
                f"allowed diversity: {expectation.allowed_diversity}",
            ],
            supporting_fact_ids=fact_ids, method="architecture-standardisation/v1",
        )
        eligible_values.append(standardisation_value)

    currency = _canvas_measure_result(
        value=None, status="NOT_CONFIGURED",
        inputs=["version and lifecycle attribution"], supporting_fact_ids=fact_ids,
        method="architecture-currency/v1",
    )
    risk = _canvas_measure_result(
        value=None, status="NOT_CONFIGURED",
        inputs=["cell-attributed deterministic insights"], supporting_fact_ids=fact_ids,
        method="architecture-risk/v1",
    )

    if expectation.applicability == "NOT_APPLICABLE":
        conformance = _canvas_measure_result(
            value=None, status="NOT_APPLICABLE", inputs=["cell applicability"],
            supporting_fact_ids=[], method="architecture-conformance/v1",
        )
    elif policy is None:
        conformance = _canvas_measure_result(
            value=None, status="NOT_CONFIGURED", inputs=["tenant cell policy"],
            supporting_fact_ids=fact_ids, method="architecture-conformance/v1",
        )
    elif state == "UNOBSERVED":
        conformance = _canvas_measure_result(
            value=None, status="INSUFFICIENT_DATA", inputs=["observation completeness"],
            supporting_fact_ids=fact_ids, method="architecture-conformance/v1",
        )
    else:
        prohibited = sum(item.policy_status == "PROHIBITED" for item in occupants)
        discouraged = sum(item.policy_status == "DISCOURAGED" for item in occupants)
        required_absent = (
            expectation.applicability == "REQUIRED"
            and len(occupants) < (expectation.minimum_implementations or 1)
        )
        conformance_value = max(
            0.0,
            100.0 - prohibited * 100.0 - discouraged * 25.0 - (100.0 if required_absent else 0.0),
        )
        conformance = _canvas_measure_result(
            value=conformance_value, status="ELIGIBLE",
            inputs=[
                f"prohibited in use: {prohibited}",
                f"discouraged in use: {discouraged}",
                f"required but absent: {str(required_absent).lower()}",
            ],
            supporting_fact_ids=fact_ids, method="architecture-conformance/v1",
        )
        eligible_values.append(conformance_value)

    overall = sum(eligible_values) / len(eligible_values) if len(eligible_values) >= 2 else None
    posture_band = None
    if overall is not None:
        if overall >= 85:
            posture_band = "STRONG"
        elif overall >= 65:
            posture_band = "ADEQUATE"
        elif overall >= 40:
            posture_band = "WEAK"
        else:
            posture_band = "AT_RISK"
    confidence = min((item.confidence for item in occupants), default=0.0)
    if observation.in_scope_subjects:
        confidence = min(
            confidence if occupants else 1.0,
            observation.observed_subjects / observation.in_scope_subjects,
        )
    return CanvasCellMeasuresModel(
        posture_band=posture_band,
        overall_score=overall,
        coverage=coverage,
        standardisation=standardisation,
        currency=currency,
        risk=risk,
        conformance=conformance,
        confidence=confidence,
        confidence_label=_confidence_label(confidence),
        method_version=CANVAS_MEASURE_METHOD_VERSION,
        missing_inputs=list(dict.fromkeys(missing_inputs)),
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


def _semantic_match_details(query: str, content: str) -> tuple[list[str], str]:
    query_terms = {term.casefold() for term in TOKEN_PATTERN.findall(query)}
    content_terms = [term.casefold() for term in TOKEN_PATTERN.findall(content)]
    matched = sorted(query_terms.intersection(content_terms))[:20]
    if not content:
        return matched, ""
    first = min(
        (content.casefold().find(term) for term in matched if content.casefold().find(term) >= 0),
        default=0,
    )
    start = max(0,first-120)
    end = min(len(content),start+400)
    excerpt = content[start:end].strip()
    if start:
        excerpt = "…"+excerpt
    if end<len(content):
        excerpt += "…"
    return matched,excerpt


def _aggregate_node_id(center_id: UUID, depth: int, namespace: str, entity_type: str) -> UUID:
    return uuid5(
        NAMESPACE_URL,
        f"stackgraph:aggregate:{center_id}:{depth}:{namespace}:{entity_type}",
    )


@dataclass(slots=True)
class GraphReadMetrics:
    neo4j_reads: int = 0
    age_reads: int = 0
    sql_reads: int = 0
    lag_fallbacks: int = 0
    unavailable_fallbacks: int = 0
    parity_fallbacks: int = 0
    discovery_limit_fallbacks: int = 0
    timeout_fallbacks: int = 0


class AgeParityError(RuntimeError):
    pass


class ReadModelStore(AdminReadModelsMixin):
    def __init__(
        self,
        database: Database,
        *,
        graph_read_mode: str = "sql",
        graph_discovery_limit: int = 5000,
        graph_age_timeout_seconds: float = 3.0,
        credential_encryption_key: str = "stackgraph-local-development-credential-key",
    ) -> None:
        self.database = database
        self.graph_read_mode = graph_read_mode
        self.age_graph = AgeGraphReader(database, discovery_limit=graph_discovery_limit)
        self.neo4j_graph = Neo4jGraphReader(
            database,
            encryption_key=credential_encryption_key,
            discovery_limit=graph_discovery_limit,
        )
        self.graph_age_timeout_seconds = graph_age_timeout_seconds
        self.graph_read_metrics = GraphReadMetrics()
        self.credential_encryption_key = credential_encryption_key

    async def estate_summary(
        self,
        *,
        tenant_id: UUID | None,
        cursor: str | None,
        limit: int,
        namespaces: list[str] | None = None,
        sort: str = "priority",
    ) -> EstateSummary:
        cursor_data = _decode_cursor(cursor, "estate")
        try:
            cursor_score = Decimal(str(cursor_data.get("value",cursor_data.get("score")))) if cursor_data else None
            cursor_name = str(cursor_data["name"]) if cursor_data else None
            cursor_id = UUID(cursor_data["id"]) if cursor_data else None
            cursor_sort = str(cursor_data.get("sort","priority")) if cursor_data else sort
        except (KeyError, TypeError, ValueError) as error:
            raise APIError(400, "INVALID_CURSOR", "The pagination cursor is invalid.") from error
        if cursor_sort!=sort:
            raise APIError(
                400,"CURSOR_SORT_MISMATCH","The pagination cursor belongs to a different sort.",
                {"cursor_sort":cursor_sort,"requested_sort":sort},
            )
        sort_expressions = {
            "priority":"coalesce(p.score,0)",
            "systemic_risk":"coalesce(risk.systemic_risk,0)",
            "upstream_impact":"coalesce(upstream.numeric_value,0)",
            "dependency_depth":"coalesce(depth_metric.numeric_value,0)",
        }
        sort_expression = sort_expressions[sort]
        snapshot_rows = await self._active_graph_snapshots(
            tenant_id,policy_key="runtime-dependency",
        )
        snapshot = self._graph_snapshot(snapshot_rows[0]) if snapshot_rows else None
        if sort!="priority" and snapshot is None:
            raise APIError(
                400,"GRAPH_SORT_UNAVAILABLE",
                "The requested graph ranking requires an active runtime-dependency snapshot.",
                {"sort":sort},
            )
        counts_row = await self.database.fetch_one(
            _OBSERVED_TECHNOLOGY_CTE + """
            SELECT
              count(*) FILTER (
                WHERE e.namespace='ENTERPRISE' AND e.entity_type='Application'
                  AND e.tenant_id=(SELECT tenant_id FROM tenant_scope)
              ) AS applications,
              count(*) FILTER (
                WHERE e.namespace='ENTERPRISE' AND e.entity_type='Repository'
                  AND e.tenant_id=(SELECT tenant_id FROM tenant_scope)
              ) AS repositories,
              count(*) FILTER (
                WHERE e.namespace='ENTERPRISE' AND e.entity_type='Service'
                  AND e.tenant_id=(SELECT tenant_id FROM tenant_scope)
              ) AS services,
              count(*) FILTER (
                WHERE e.namespace='TECHNOLOGY' AND e.entity_type<>'Capability'
                  AND e.id IN (SELECT id FROM observed_technology)
              ) AS technologies
            FROM entity e
            """,
            (tenant_id,),
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
            _OBSERVED_TECHNOLOGY_CTE + """
            SELECT 'technology.' || coalesce(e.properties->>'domain_id', lower(e.entity_type)) AS key,
                   count(*) AS value
            FROM entity e
            JOIN observed_technology observed ON observed.id=e.id
            WHERE e.namespace='TECHNOLOGY' AND e.entity_type<>'Capability'
            GROUP BY 1 ORDER BY 1
            """,
            (tenant_id,),
            tenant_id=tenant_id,
        )
        coverage_row = await self.database.fetch_one(
            """
            WITH tenant_scope AS (
              SELECT %s::uuid tenant_id
            )
            SELECT
              count(*) FILTER (
                WHERE entity.namespace='ENTERPRISE' AND entity.entity_type='Repository'
                  AND entity.tenant_id=(SELECT tenant_id FROM tenant_scope)
              ) AS repositories_total,
              count(*) FILTER (
                WHERE entity.namespace='ENTERPRISE' AND entity.entity_type='Repository'
                  AND entity.tenant_id=(SELECT tenant_id FROM tenant_scope)
                  AND entity.last_seen_at IS NOT NULL
              ) AS repositories_scanned,
              coalesce((
                SELECT count(DISTINCT evidence.fact_assertion_id)::numeric
                       / nullif(count(DISTINCT fact.id), 0)
                FROM current_fact fact
                LEFT JOIN evidence
                  ON evidence.fact_assertion_id=fact.id
                 AND evidence.tenant_id=(SELECT tenant_id FROM tenant_scope)
                WHERE fact.tenant_id=(SELECT tenant_id FROM tenant_scope)
              ), 0) AS evidence_ratio
            FROM entity
            """,
            (tenant_id,),
            tenant_id=tenant_id,
        )
        coverage_row = coverage_row or {}
        coverage = Coverage(
            repositories_total=coverage_row.get("repositories_total", 0),
            repositories_scanned=coverage_row.get("repositories_scanned", 0),
            facts_with_evidence_ratio=_number(coverage_row.get("evidence_ratio")),
        )

        rows = await self.database.fetch_all(
            _OBSERVED_TECHNOLOGY_CTE + f"""
            SELECT e.*, coalesce(e.last_seen_at,e.updated_at,e.created_at) observed_at,
                   p.id priority_id,p.score priority_score,p.confidence priority_confidence,p.method_version priority_method,
                   v.score viability_score,v.confidence viability_confidence,v.method_version viability_method,
                   dependency.dependency_tier,
                   parent_application.id parent_application_id,
                   parent_application.name parent_application_name,
                   risk.systemic_risk,upstream.numeric_value upstream_impact,
                   depth_metric.numeric_value dependency_depth,
                   community.community_key,{sort_expression} sort_value
            FROM entity e
            LEFT JOIN LATERAL (
              SELECT * FROM assessment a WHERE a.subject_entity_id=e.id AND a.status='CURRENT' AND lower(a.dimension)='priority'
              ORDER BY a.valid_from DESC LIMIT 1
            ) p ON true
            LEFT JOIN LATERAL (
              SELECT * FROM assessment a WHERE a.subject_entity_id=e.id AND a.status='CURRENT' AND lower(a.dimension)='viability'
              ORDER BY a.valid_from DESC LIMIT 1
            ) v ON true
            LEFT JOIN observed_technology dependency ON dependency.id=e.id
            LEFT JOIN LATERAL (
              SELECT application.id,application.name
              FROM current_relationship relationship
              JOIN entity application
                ON application.id=relationship.source_entity_id
               AND application.tenant_id=relationship.tenant_id
               AND application.namespace='ENTERPRISE'
               AND application.entity_type='Application'
              WHERE e.entity_type='Service'
                AND relationship.tenant_id=e.tenant_id
                AND relationship.relationship_type IN ('CONTAINS','IMPLEMENTED_BY')
                AND relationship.target_entity_id=e.id
              ORDER BY application.name,application.id
              LIMIT 1
            ) parent_application ON true
            LEFT JOIN graph_entity_risk risk
              ON risk.run_id=%s::uuid AND risk.tenant_id=%s AND risk.entity_id=e.id
            LEFT JOIN graph_entity_metric upstream
              ON upstream.run_id=%s::uuid AND upstream.tenant_id=%s AND upstream.entity_id=e.id
             AND upstream.metric_key='reachability.upstream_impact'
            LEFT JOIN graph_entity_metric depth_metric
              ON depth_metric.run_id=%s::uuid AND depth_metric.tenant_id=%s
             AND depth_metric.entity_id=e.id AND depth_metric.metric_key='reachability.upstream_depth'
            LEFT JOIN graph_community_membership community
              ON community.run_id=%s::uuid AND community.tenant_id=%s
             AND community.entity_id=e.id AND community.algorithm_key='wcc'
            WHERE (
                (e.namespace='ENTERPRISE' AND e.entity_type IN ('Application','Service')
                  AND e.tenant_id=(SELECT tenant_id FROM tenant_scope))
                OR (e.namespace='BUSINESS' AND e.entity_type='BusinessCapability'
                  AND e.tenant_id=(SELECT tenant_id FROM tenant_scope)
                  AND EXISTS (
                    SELECT 1
                    FROM current_capability_application_relationship mapping
                    WHERE mapping.tenant_id=e.tenant_id
                      AND mapping.capability_entity_id=e.id
                  ))
                OR (e.namespace IN ('TECHNOLOGY','OSS') AND e.entity_type<>'Capability'
                  AND e.id IN (SELECT id FROM observed_technology))
              )
              AND (%s::text[] IS NULL OR e.namespace=ANY(%s::text[]))
              AND (
                %s::numeric IS NULL
                OR {sort_expression}<%s::numeric
                OR ({sort_expression}=%s::numeric AND (e.name,e.id)>(%s::text,%s::uuid))
              )
            ORDER BY {sort_expression} DESC,e.name,e.id
            LIMIT %s
            """,
            (
                tenant_id,
                snapshot.analysis_run_id if snapshot else None,tenant_id,
                snapshot.analysis_run_id if snapshot else None,tenant_id,
                snapshot.analysis_run_id if snapshot else None,tenant_id,
                snapshot.analysis_run_id if snapshot else None,tenant_id,
                namespaces or None,
                namespaces or None,
                cursor_score,
                cursor_score,
                cursor_score,
                cursor_name,
                cursor_id,
                limit + 1,
            ),
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
                    parent_application_id=row.get("parent_application_id"),
                    parent_application_name=row.get("parent_application_name"),
                    dependency_tier=(
                        int(row["dependency_tier"])
                        if row.get("dependency_tier") is not None else None
                    ),
                    systemic_risk=(
                        _number(row["systemic_risk"])
                        if row.get("systemic_risk") is not None else None
                    ),
                    upstream_impact=(
                        _number(row["upstream_impact"])
                        if row.get("upstream_impact") is not None else None
                    ),
                    dependency_depth=(
                        int(row["dependency_depth"])
                        if row.get("dependency_depth") is not None else None
                    ),
                    community_key=row.get("community_key"),
                    structural_status=(
                        "STRUCTURALLY_CRITICAL" if _number(row.get("systemic_risk"))>=0.8
                        else "ELEVATED" if _number(row.get("systemic_risk"))>=0.6
                        else "TYPICAL" if row.get("systemic_risk") is not None else None
                    ),
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
                        sort=sort,
                        value=str(rows[-1].get("sort_value") or 0),
                        name=rows[-1]["name"],
                        id=str(rows[-1]["id"]),
                    )
                    if has_next else None
                ),
            ),
            limitations=(list(snapshot.limitations) if snapshot else [{
                "code":"NO_ACTIVE_GRAPH_SNAPSHOT",
                "message":"Graph ranking fields are omitted until a runtime-dependency snapshot is active.",
            }]),
        )

    async def application_detail(self, application_id: UUID, *, tenant_id: UUID | None) -> ApplicationDetail:
        application = await self._get_entity(application_id, tenant_id, namespace="ENTERPRISE", entity_type="Application")
        related = await self._application_related_entities(application_id, tenant_id)
        assessments = await self._assessments(application_id, tenant_id)
        recommendations = await self._recommendations(application_id, tenant_id)
        technology_rows = [row for row in related if row["namespace"] in {"TECHNOLOGY", "OSS"}]
        repository_rows = [row for row in related if row["entity_type"] == "Repository"]
        catalog_rows = await self._technology_classification_catalog(tenant_id) if technology_rows else []
        dependency_hierarchies = await self._application_dependency_hierarchies(
            repository_rows,
            tenant_id,
        )
        return ApplicationDetail(
            application=_entity(application),
            business_context=[_entity(row) for row in related if row["namespace"] == "BUSINESS"],
            repositories=[_entity(row) for row in repository_rows],
            services=[
                _entity(row) for row in related
                if row["namespace"] == "ENTERPRISE" and row["entity_type"] == "Service"
            ],
            technologies=[_entity(row) for row in technology_rows],
            technology_groups=_group_application_technologies(technology_rows, catalog_rows),
            dependency_hierarchies=dependency_hierarchies,
            deployments=[_entity(row) for row in related if row["namespace"] == "DEPLOYMENT"],
            assessments=assessments,
            recommendations=recommendations,
            freshness=_freshness(application.get("observed_at")),
            graph_intelligence=await self.entity_graph_metrics(
                application_id,tenant_id=tenant_id,entity_row=application,
            ),
        )

    @staticmethod
    def _graph_snapshot(row: Mapping[str, Any]) -> GraphAnalysisSnapshot:
        return GraphAnalysisSnapshot(
            analysis_run_id=row["analysis_run_id"],policy_key=row["policy_key"],
            policy_version=row["policy_version"],policy_hash=row["policy_hash"],
            status=row["status"],as_of=row["completed_at"],
            requested_change_watermark=row["requested_change_watermark"],
            neo4j_projection_watermark=row["neo4j_projection_watermark"],
            node_count=row["node_count"] or 0,edge_count=row["edge_count"] or 0,
            coverage=row.get("coverage") or {},limitations=row.get("limitations") or [],
        )

    async def _active_graph_snapshots(
        self,tenant_id: UUID | None,*,policy_key: str | None = None,
    ) -> list[dict[str, Any]]:
        if tenant_id is None:
            return []
        return await self.database.fetch_all(
            """
            SELECT run.id AS analysis_run_id,run.policy_key,policy.version AS policy_version,
                   policy.content_hash AS policy_hash,run.status,run.completed_at,
                   run.requested_change_watermark,run.neo4j_projection_watermark,
                   run.node_count,run.edge_count,run.coverage,run.limitations
            FROM active_graph_analysis_run active
            JOIN graph_analysis_run run ON run.id=active.run_id
            JOIN graph_analysis_policy policy ON policy.id=run.policy_id
            WHERE active.tenant_id=%s AND (%s::text IS NULL OR run.policy_key=%s)
              AND run.status IN ('SUCCEEDED','SUCCEEDED_WITH_LIMITATIONS')
            ORDER BY run.policy_key
            """,
            (tenant_id,policy_key,policy_key),tenant_id=tenant_id,
        )

    async def graph_intelligence_status(
        self,*,tenant_id: UUID | None,
    ) -> GraphIntelligenceStatus:
        now = datetime.now(UTC)
        if tenant_id is None:
            return GraphIntelligenceStatus(
                as_of=now,deployment_state="UNCONFIGURED",desired_change_watermark=0,
                neo4j_projection_watermark=0,projection_lag=0,pending_requests=0,
                running_requests=0,failed_requests=0,
                limitations=[{"code":"TENANT_REQUIRED","message":"Graph intelligence requires a tenant context."}],
            )
        state = await self.database.fetch_one(
            """
            SELECT deployment.deployment_state,deployment.desired_outbox_id,
                   deployment.projected_outbox_id,deployment.rebuild_state,
                   deployment.candidate_projected_outbox_id,deployment.rebuild_started_at,
                   (SELECT count(*) FROM graph_analysis_request request
                    WHERE request.tenant_id=deployment.tenant_id
                      AND request.status IN ('PENDING','WAITING_FOR_PROJECTION')) AS pending_requests,
                   (SELECT count(*) FROM graph_analysis_request request
                    WHERE request.tenant_id=deployment.tenant_id
                      AND request.status='RUNNING') AS running_requests,
                   (SELECT count(*) FROM graph_analysis_request failed
                    WHERE failed.tenant_id=deployment.tenant_id AND failed.status='FAILED'
                      AND NOT EXISTS (
                        SELECT 1 FROM graph_analysis_request recovered
                        WHERE recovered.tenant_id=failed.tenant_id
                          AND recovered.policy_id=failed.policy_id
                          AND recovered.status='SUCCEEDED'
                          AND recovered.completed_at>failed.completed_at
                      )) AS failed_requests,
                   (SELECT min(request.created_at) FROM graph_analysis_request request
                    WHERE request.tenant_id=deployment.tenant_id
                      AND request.status IN ('PENDING','WAITING_FOR_PROJECTION')) AS oldest_pending_at
            FROM tenant_graph_deployment deployment
            WHERE deployment.tenant_id=%s
            """,
            (tenant_id,),tenant_id=tenant_id,
        )
        snapshots = [
            self._graph_snapshot(row) for row in await self._active_graph_snapshots(tenant_id)
        ]
        if state is None:
            return GraphIntelligenceStatus(
                as_of=now,deployment_state="UNCONFIGURED",desired_change_watermark=0,
                neo4j_projection_watermark=0,projection_lag=0,pending_requests=0,
                running_requests=0,failed_requests=0,snapshots=snapshots,
                limitations=[{"code":"GRAPH_DEPLOYMENT_UNCONFIGURED","message":"No tenant graph deployment is configured."}],
            )
        desired = int(state["desired_outbox_id"] or 0)
        projected = int(state["projected_outbox_id"] or 0)
        limitations: list[dict[str, Any]] = []
        if desired > projected:
            limitations.append({
                "code":"PROJECTION_LAG","message":"Neo4j has not reached the authoritative change watermark.",
                "lag":desired-projected,
            })
        if state["rebuild_state"] == "RUNNING":
            limitations.append({
                "code":"GRAPH_REBUILD_IN_PROGRESS",
                "message":"A parity-gated Neo4j candidate is being rebuilt; SQL remains available.",
                "candidate_projection_watermark":int(state["candidate_projected_outbox_id"] or 0),
                "started_at":state["rebuild_started_at"].isoformat() if state["rebuild_started_at"] else None,
            })
        elif state["rebuild_state"] == "FAILED":
            limitations.append({
                "code":"GRAPH_REBUILD_FAILED",
                "message":"The last Neo4j candidate rebuild failed; the active graph pointer was unchanged.",
            })
        active_policy_keys = {snapshot.policy_key for snapshot in snapshots}
        if len(active_policy_keys) < 4:
            limitations.append({
                "code":"INCOMPLETE_POLICY_COVERAGE",
                "message":"Not every default graph policy has an active snapshot.",
                "active_policy_count":len(active_policy_keys),"expected_policy_count":4,
            })
        return GraphIntelligenceStatus(
            as_of=now,deployment_state=state["deployment_state"],
            desired_change_watermark=desired,neo4j_projection_watermark=projected,
            projection_lag=max(0,desired-projected),
            pending_requests=int(state["pending_requests"] or 0),
            running_requests=int(state["running_requests"] or 0),
            failed_requests=int(state["failed_requests"] or 0),
            oldest_pending_at=state.get("oldest_pending_at"),snapshots=snapshots,
            limitations=limitations,
        )

    async def entity_graph_metrics(
        self,entity_id: UUID,*,tenant_id: UUID | None,
        entity_row: Mapping[str, Any] | None = None,
    ) -> EntityGraphIntelligence:
        entity_data = entity_row or await self._get_entity(entity_id,tenant_id)
        snapshot_rows = await self._active_graph_snapshots(tenant_id)
        snapshots = [self._graph_snapshot(row) for row in snapshot_rows]
        if tenant_id is None or not snapshots:
            return EntityGraphIntelligence(
                entity=_entity(entity_data),primary_status="WAITING_FOR_DATA",as_of=datetime.now(UTC),
                reasons=["No completed graph-analysis snapshot is active."],
                limitations=[{"code":"NO_ACTIVE_GRAPH_SNAPSHOT","message":"Graph metrics are not ready for this tenant."}],
            )
        rows = await self.database.fetch_all(
            """
            SELECT metric.run_id AS analysis_run_id,run.policy_key,metric.metric_key,
                   metric.numeric_value,metric.percentile,metric.rank,
                   metric.components,metric.limitations
            FROM active_graph_analysis_run active
            JOIN graph_analysis_run run ON run.id=active.run_id
            JOIN graph_entity_metric metric
              ON metric.run_id=run.id AND metric.tenant_id=active.tenant_id
            WHERE active.tenant_id=%s AND metric.entity_id=%s
            ORDER BY run.policy_key,metric.metric_key
            """,
            (tenant_id,entity_id),tenant_id=tenant_id,
        )
        metrics = [
            GraphMetric(
                analysis_run_id=row["analysis_run_id"],policy_key=row["policy_key"],
                metric_key=row["metric_key"],numeric_value=row.get("numeric_value"),
                percentile=row.get("percentile"),rank=row.get("rank"),
                components=row.get("components") or {},limitations=row.get("limitations") or [],
            ) for row in rows
        ]
        community_rows = await self.database.fetch_all(
            """
            SELECT DISTINCT membership.algorithm_key||':'||membership.community_key AS community_key
            FROM active_graph_analysis_run active
            JOIN graph_community_membership membership
              ON membership.run_id=active.run_id AND membership.tenant_id=active.tenant_id
            WHERE active.tenant_id=%s AND membership.entity_id=%s
            ORDER BY community_key
            """,
            (tenant_id,entity_id),tenant_id=tenant_id,
        )
        metric_by_key: dict[str, GraphMetric] = {}
        for metric in metrics:
            current = metric_by_key.get(metric.metric_key)
            if current is None or (metric.percentile or 0) > (current.percentile or 0):
                metric_by_key[metric.metric_key] = metric
        reasons: list[str] = []
        spof = metric_by_key.get("spof.articulation")
        reach = metric_by_key.get("reachability.upstream_impact")
        betweenness = metric_by_key.get("betweenness")
        if spof and (spof.numeric_value or 0)>0:
            reasons.append("Removing this entity can disconnect parts of its policy graph.")
        if reach and reach.percentile is not None and reach.percentile>=0.9:
            reasons.append("Its upstream enterprise impact is in the estate's top decile.")
        if betweenness and betweenness.percentile is not None and betweenness.percentile>=0.9:
            reasons.append("A top-decile share of shortest dependency paths crosses this entity.")
        highest = max(
            (metric.percentile or 0 for metric in (reach,betweenness) if metric is not None),
            default=0,
        )
        if spof and (spof.numeric_value or 0)>0 or highest>=0.9:
            primary_status = "STRUCTURALLY_CRITICAL"
        elif highest>=0.75:
            primary_status = "ELEVATED"
        elif metrics:
            primary_status = "TYPICAL"
        else:
            primary_status = "WAITING_FOR_DATA"
            reasons.append("The active policies do not include this entity or have no matching data.")
        limitations = [
            limitation for snapshot in snapshots for limitation in snapshot.limitations
        ]
        limitations.extend(
            limitation for metric in metrics for limitation in metric.limitations
        )
        return EntityGraphIntelligence(
            entity=_entity(entity_data),primary_status=primary_status,
            reasons=reasons[:2],snapshots=snapshots,metrics=metrics,
            community_keys=[row["community_key"] for row in community_rows],
            as_of=max(snapshot.as_of for snapshot in snapshots),
            limitations=list({json.dumps(item,sort_keys=True):item for item in limitations}.values()),
        )

    async def graph_blast_radius(
        self,entity_id: UUID,*,tenant_id: UUID | None,
    ) -> GraphBlastRadius:
        entity_data = await self._get_entity(entity_id,tenant_id)
        snapshot_rows = await self._active_graph_snapshots(
            tenant_id,policy_key="runtime-dependency",
        )
        if not snapshot_rows or tenant_id is None:
            return GraphBlastRadius(
                entity=_entity(entity_data),affected_entity_count=0,maximum_depth=0,
                as_of=datetime.now(UTC),
                limitations=[{"code":"NO_ACTIVE_RUNTIME_SNAPSHOT","message":"Runtime dependency blast radius is not ready."}],
            )
        snapshot = self._graph_snapshot(snapshot_rows[0])
        rows = await self.database.fetch_all(
            """
            SELECT metric_key,numeric_value,limitations
            FROM graph_entity_metric
            WHERE run_id=%s AND tenant_id=%s AND entity_id=%s
              AND metric_key IN ('reachability.upstream_impact','reachability.upstream_depth')
            """,
            (snapshot.analysis_run_id,tenant_id,entity_id),tenant_id=tenant_id,
        )
        values = {row["metric_key"]:row for row in rows}
        limitations = list(snapshot.limitations)
        limitations.extend(
            limitation for row in rows for limitation in (row.get("limitations") or [])
        )
        path_rows = await self.database.fetch_all(
            """
            SELECT target.id,target.entity_type,target.name,target.canonical_key,
                   target.properties->>'summary' AS summary,path.distance,
                   path.minimum_confidence,path.path_entity_ids,path.path_fact_ids
            FROM graph_impact_path path
            JOIN entity target ON target.id=path.target_entity_id
            WHERE path.run_id=%s AND path.tenant_id=%s AND path.source_entity_id=%s
            ORDER BY path.distance,target.name,target.id
            LIMIT 100
            """,
            (snapshot.analysis_run_id,tenant_id,entity_id),tenant_id=tenant_id,
        )
        impacts = [GraphImpactPath(
            target=_entity(row),distance=row["distance"],
            minimum_confidence=row["minimum_confidence"],
            entity_ids=row["path_entity_ids"],supporting_fact_ids=row["path_fact_ids"],
        ) for row in path_rows]
        affected_count = int(
            (values.get("reachability.upstream_impact") or {}).get("numeric_value") or 0
        )
        if affected_count>len(impacts):
            limitations.append({
                "code":"IMPACT_PATH_SCOPE",
                "message":"Evidence paths list impacted applications and business capabilities; the count includes every affected graph entity.",
                "affected_entity_count":affected_count,"listed_impact_count":len(impacts),
            })
        return GraphBlastRadius(
            entity=_entity(entity_data),snapshot=snapshot,
            affected_entity_count=affected_count,
            maximum_depth=int((values.get("reachability.upstream_depth") or {}).get("numeric_value") or 0),
            impacts=impacts,as_of=snapshot.as_of,
            limitations=list({json.dumps(item,sort_keys=True):item for item in limitations}.values()),
        )

    async def _graph_risk_applications(
        self,entity_ids: list[UUID],tenant_id: UUID,
    ) -> dict[UUID,list[EntitySummary]]:
        if not entity_ids:
            return {}
        rows = await self.database.fetch_all(
            """
            WITH requested AS (
              SELECT unnest(%s::uuid[]) entity_id
            ), candidates AS (
              SELECT requested.entity_id,application.id,application.entity_type,
                     application.name,application.canonical_key,
                     application.properties->>'summary' summary,0 depth
              FROM requested
              JOIN entity application ON application.id=requested.entity_id
              WHERE application.tenant_id=%s
                AND application.namespace='ENTERPRISE'
                AND application.entity_type='Application'
              UNION ALL
              SELECT requested.entity_id,application.id,application.entity_type,
                     application.name,application.canonical_key,
                     application.properties->>'summary' summary,1 depth
              FROM requested
              JOIN current_relationship relationship
                ON relationship.tenant_id=%s
               AND (
                 relationship.source_entity_id=requested.entity_id
                 OR relationship.target_entity_id=requested.entity_id
               )
              JOIN entity application
                ON application.id=CASE
                  WHEN relationship.source_entity_id=requested.entity_id
                    THEN relationship.target_entity_id
                  ELSE relationship.source_entity_id
                END
              WHERE application.tenant_id=%s
                AND application.namespace='ENTERPRISE'
                AND application.entity_type='Application'
                AND relationship.relationship_type IN (
                  'CONTAINS','IMPLEMENTED_BY','IMPLEMENTS','DEPENDS_ON',
                  'USES','RUNS_ON','BUILT_ON','CONNECTS_TO'
                )
              UNION ALL
              SELECT requested.entity_id,application.id,application.entity_type,
                     application.name,application.canonical_key,
                     application.properties->>'summary' summary,2 depth
              FROM requested
              JOIN current_relationship usage
                ON usage.tenant_id=%s
               AND (
                 usage.source_entity_id=requested.entity_id
                 OR usage.target_entity_id=requested.entity_id
               )
              JOIN entity repository
                ON repository.id=CASE
                  WHEN usage.source_entity_id=requested.entity_id
                    THEN usage.target_entity_id
                  ELSE usage.source_entity_id
                END
               AND repository.tenant_id=%s
               AND repository.namespace='ENTERPRISE'
               AND repository.entity_type='Repository'
              JOIN current_relationship ownership
                ON ownership.tenant_id=%s
               AND (
                 ownership.source_entity_id=repository.id
                 OR ownership.target_entity_id=repository.id
               )
              JOIN entity application
                ON application.id=CASE
                  WHEN ownership.source_entity_id=repository.id
                    THEN ownership.target_entity_id
                  ELSE ownership.source_entity_id
                END
              WHERE application.tenant_id=%s
                AND application.namespace='ENTERPRISE'
                AND application.entity_type='Application'
                AND usage.relationship_type IN (
                  'CONTAINS','IMPLEMENTED_BY','IMPLEMENTS','DEPENDS_ON',
                  'USES','RUNS_ON','BUILT_ON','HAS_VERSION','CONNECTS_TO'
                )
                AND ownership.relationship_type IN (
                  'CONTAINS','IMPLEMENTED_BY','IMPLEMENTS'
                )
            ), unique_candidates AS (
              SELECT DISTINCT ON (entity_id,id)
                     entity_id,id,entity_type,name,canonical_key,summary,depth
              FROM candidates
              ORDER BY entity_id,id,depth
            ), ranked AS (
              SELECT *,row_number() OVER (
                PARTITION BY entity_id ORDER BY depth,name,id
              ) ordinal
              FROM unique_candidates
            )
            SELECT entity_id,id,entity_type,name,canonical_key,summary
            FROM ranked WHERE ordinal<=5
            ORDER BY entity_id,ordinal
            """,
            (
                entity_ids,tenant_id,tenant_id,tenant_id,
                tenant_id,tenant_id,tenant_id,tenant_id,
            ),tenant_id=tenant_id,
        )
        applications: dict[UUID,list[EntitySummary]] = {}
        for row in rows:
            applications.setdefault(row["entity_id"],[]).append(_entity(row))
        return applications

    async def graph_risks(
        self,*,tenant_id: UUID | None,entity_type: str | None=None,
        namespace: str | None=None,community_key: str | None=None,min_score: float=0,
        cursor: str | None=None,limit: int,
    ) -> GraphRiskList:
        snapshot_rows = await self._active_graph_snapshots(
            tenant_id,policy_key="runtime-dependency",
        )
        if not snapshot_rows or tenant_id is None:
            return GraphRiskList(
                as_of=datetime.now(UTC),
                limitations=[{"code":"NO_ACTIVE_RUNTIME_SNAPSHOT","message":"Systemic graph risk is not ready."}],
            )
        snapshot = self._graph_snapshot(snapshot_rows[0])
        cursor_data = _decode_cursor(cursor,"graph-risks")
        try:
            cursor_score = float(cursor_data["score"]) if cursor_data else None
            cursor_id = UUID(cursor_data["id"]) if cursor_data else None
        except (KeyError,TypeError,ValueError) as error:
            raise APIError(400,"INVALID_CURSOR","The pagination cursor is invalid.") from error
        rows = await self.database.fetch_all(
            """
            SELECT entity.id,entity.entity_type,entity.name,entity.canonical_key,
                   entity.properties->>'summary' AS summary,risk.systemic_risk,
                   risk.contributions,risk.renormalized_families,risk.method_version,
                   community.community_key
            FROM graph_entity_risk risk
            JOIN entity ON entity.id=risk.entity_id
            LEFT JOIN graph_community_membership community
              ON community.run_id=risk.run_id AND community.entity_id=risk.entity_id
             AND community.algorithm_key='wcc'
            WHERE risk.run_id=%s AND risk.tenant_id=%s
              AND (%s::text IS NULL OR entity.entity_type=%s)
              AND (%s::text IS NULL OR entity.namespace=%s)
              AND (%s::text IS NULL OR community.community_key=%s)
              AND risk.systemic_risk>=%s
              AND (
                %s::double precision IS NULL OR risk.systemic_risk<%s
                OR (risk.systemic_risk=%s AND risk.entity_id>%s::uuid)
              )
            ORDER BY risk.systemic_risk DESC,risk.entity_id LIMIT %s
            """,
            (
                snapshot.analysis_run_id,tenant_id,entity_type,entity_type,
                namespace,namespace,community_key,community_key,min_score,
                cursor_score,cursor_score,cursor_score,cursor_id,limit+1,
            ),tenant_id=tenant_id,
        )
        has_next = len(rows)>limit
        rows = rows[:limit]
        metric_rows = await self.database.fetch_all(
            """
            SELECT metric.* FROM graph_entity_metric metric
            WHERE metric.run_id=%s AND metric.tenant_id=%s
              AND metric.entity_id=ANY(%s::uuid[])
              AND metric.metric_key IN (
                'reachability.upstream_impact','betweenness','spof.articulation','pagerank'
              )
            ORDER BY metric.entity_id,metric.metric_key
            """,
            (snapshot.analysis_run_id,tenant_id,[row["id"] for row in rows]),tenant_id=tenant_id,
        ) if rows else []
        metrics_by_entity: dict[UUID,list[GraphMetric]] = defaultdict(list)
        for metric in metric_rows:
            metrics_by_entity[metric["entity_id"]].append(GraphMetric(
                analysis_run_id=snapshot.analysis_run_id,policy_key=snapshot.policy_key,
                metric_key=metric["metric_key"],numeric_value=metric.get("numeric_value"),
                percentile=metric.get("percentile"),rank=metric.get("rank"),
                components=metric.get("components") or {},limitations=metric.get("limitations") or [],
            ))
        risk_items = [GraphRiskItem(
            entity=_entity(row),systemic_risk=row["systemic_risk"],
            component_metrics=metrics_by_entity[row["id"]],
            component_contributions=row.get("contributions") or {},
            renormalized_families=row.get("renormalized_families") or [],
            method_version=row.get("method_version") or "graph-systemic-risk/v2",
            reasons=[
                f"{key.title()} contributes {round(float(value.get('normalized_contribution') or 0)*100)}% of the normalized score."
                for key,value in sorted(
                    (row.get("contributions") or {}).items(),
                    key=lambda item:float(item[1].get("normalized_contribution") or 0),reverse=True,
                )[:2]
            ],
        ) for row in rows]
        applications = await self._graph_risk_applications(
            [item.entity.id for item in risk_items],tenant_id,
        )
        risk_items = [
            item.model_copy(update={
                "impacted_applications":applications.get(item.entity.id,[]),
            })
            for item in risk_items
        ]
        return GraphRiskList(
            snapshot=snapshot,risks=risk_items,as_of=snapshot.as_of,
            limitations=list(snapshot.limitations)+([{
                "code":"RENORMALIZED_COMPOSITE",
                "message":"One or more signal families were absent for at least one result; configured weights were renormalized over observed families.",
                "method_version":"graph-systemic-risk/v2",
            }] if any(item.renormalized_families for item in risk_items) else []),
            page_info=PageInfo(
                has_next_page=has_next,
                next_cursor=(_encode_cursor(
                    "graph-risks",score=rows[-1]["systemic_risk"],id=str(rows[-1]["id"]),
                ) if has_next else None),
            ),
        )

    async def graph_communities(
        self,*,tenant_id: UUID | None,policy_key: str,limit: int,
    ) -> GraphCommunityList:
        snapshot_rows = await self._active_graph_snapshots(tenant_id,policy_key=policy_key)
        if not snapshot_rows or tenant_id is None:
            return GraphCommunityList(
                algorithm_key="wcc",as_of=datetime.now(UTC),
                limitations=[{"code":"NO_ACTIVE_POLICY_SNAPSHOT","message":"Community data is not ready for this policy."}],
            )
        snapshot = self._graph_snapshot(snapshot_rows[0])
        rows = await self.database.fetch_all(
            """
            WITH ranked AS (
              SELECT membership.community_key,entity.id,entity.entity_type,entity.name,
                     entity.canonical_key,entity.properties->>'summary' AS summary,
                     count(*) OVER(PARTITION BY membership.community_key) AS member_count,
                     row_number() OVER(PARTITION BY membership.community_key ORDER BY entity.name,entity.id) AS member_rank
              FROM graph_community_membership membership
              JOIN entity ON entity.id=membership.entity_id
              WHERE membership.run_id=%s AND membership.tenant_id=%s
                AND membership.algorithm_key='wcc'
            ), selected AS (
              SELECT * FROM ranked
              WHERE member_rank<=5
                AND community_key IN (
                  SELECT community_key FROM ranked GROUP BY community_key
                  ORDER BY max(member_count) DESC,community_key LIMIT %s
                )
            )
            SELECT * FROM selected ORDER BY member_count DESC,community_key,member_rank
            """,
            (snapshot.analysis_run_id,tenant_id,limit),tenant_id=tenant_id,
        )
        grouped: dict[str, GraphCommunity] = {}
        for row in rows:
            community = grouped.get(row["community_key"])
            if community is None:
                community = GraphCommunity(
                    community_key=row["community_key"],member_count=row["member_count"],
                )
                grouped[row["community_key"]] = community
            community.representative_entities.append(_entity(row))
        return GraphCommunityList(
            snapshot=snapshot,algorithm_key="wcc",communities=list(grouped.values()),
            as_of=snapshot.as_of,limitations=list(snapshot.limitations),
        )

    async def graph_anomalies(
        self,*,tenant_id: UUID | None,cohort_key: str | None,limit: int,
    ) -> GraphAnomalyList:
        snapshot_rows = await self._active_graph_snapshots(
            tenant_id,policy_key="runtime-dependency",
        )
        if not snapshot_rows or tenant_id is None:
            return GraphAnomalyList(
                as_of=datetime.now(UTC),limitations=[{
                    "code":"NO_ACTIVE_POLICY_SNAPSHOT",
                    "message":"Anomaly data is not ready for the runtime-dependency policy.",
                }],
            )
        snapshot = self._graph_snapshot(snapshot_rows[0])
        rows = await self.database.fetch_all(
            """
            SELECT anomaly.*,entity.id entity_id,entity.entity_type,entity.name,
                   entity.canonical_key,entity.properties->>'summary' summary
            FROM graph_anomaly anomaly
            JOIN entity ON entity.id=anomaly.entity_id
            WHERE anomaly.run_id=%s AND anomaly.tenant_id=%s
              AND (%s::text IS NULL OR anomaly.cohort_key=%s)
            ORDER BY anomaly.score DESC,entity.name,anomaly.id LIMIT %s
            """,
            (snapshot.analysis_run_id,tenant_id,cohort_key,cohort_key,limit),tenant_id=tenant_id,
        )
        provenance_limitation = {
            "code":"ANOMALY_FACT_PROVENANCE_UNAVAILABLE",
            "message":"This anomaly snapshot predates fact-level anomaly provenance; metric components are returned without invented evidence IDs.",
        }
        return GraphAnomalyList(
            snapshot=snapshot,
            anomalies=[GraphAnomaly(
                id=row["id"],entity=EntitySummary(
                    id=row["entity_id"],kind=row["entity_type"],name=row["name"],
                    canonical_key=row.get("canonical_key"),summary=row.get("summary"),
                ),anomaly_key=row["anomaly_key"],score=row["score"],
                cohort_key=row["cohort_key"],
                cohort_size=int((row.get("cohort_definition") or {}).get("cohort_size") or 1),
                percentile=row["score"],observed_components=row.get("observed_components") or {},
                reasons=row.get("reasons") or [],supporting_fact_ids=[],
                limitations=[*(row.get("limitations") or []),provenance_limitation],
            ) for row in rows],
            as_of=snapshot.as_of,
            limitations=[*snapshot.limitations,provenance_limitation],
        )

    async def graph_motifs(
        self,*,tenant_id: UUID | None,motif_key: str | None,limit: int,
    ) -> GraphMotifList:
        snapshot_rows = await self._active_graph_snapshots(
            tenant_id,policy_key="runtime-dependency",
        )
        if not snapshot_rows or tenant_id is None:
            return GraphMotifList(
                as_of=datetime.now(UTC),limitations=[{
                    "code":"NO_ACTIVE_POLICY_SNAPSHOT",
                    "message":"Motif data is not ready for the runtime-dependency policy.",
                }],
            )
        snapshot = self._graph_snapshot(snapshot_rows[0])
        rows = await self.database.fetch_all(
            """
            SELECT motif.*,
              jsonb_agg(jsonb_build_object(
                'id',entity.id,'entity_type',entity.entity_type,'name',entity.name,
                'canonical_key',entity.canonical_key,
                'summary',entity.properties->>'summary'
              ) ORDER BY member.ordinality) members
            FROM graph_motif motif
            CROSS JOIN LATERAL unnest(motif.entity_ids) WITH ORDINALITY member(entity_id,ordinality)
            JOIN entity ON entity.id=member.entity_id
            WHERE motif.run_id=%s AND motif.tenant_id=%s
              AND (%s::text IS NULL OR motif.motif_key=%s)
            GROUP BY motif.id,motif.run_id,motif.tenant_id,motif.motif_key,motif.entity_ids,
                     motif.supporting_fact_ids,motif.confidence,motif.components,
                     motif.limitations,motif.created_at
            ORDER BY motif.confidence DESC,motif.id LIMIT %s
            """,
            (snapshot.analysis_run_id,tenant_id,motif_key,motif_key,limit),tenant_id=tenant_id,
        )
        return GraphMotifList(
            snapshot=snapshot,motifs=[GraphMotif(
                id=row["id"],motif_key=row["motif_key"],
                members=[_entity(member) for member in row["members"]],
                supporting_fact_ids=row["supporting_fact_ids"],
                minimum_confidence=row["confidence"],components=row.get("components") or {},
                limitations=row.get("limitations") or [],
            ) for row in rows],as_of=snapshot.as_of,limitations=list(snapshot.limitations),
        )

    async def critical_edges(
        self,entity_id: UUID,*,tenant_id: UUID | None,
    ) -> CriticalGraphEdgeList:
        entity_row = await self._get_entity(entity_id,tenant_id)
        snapshot_rows = await self._active_graph_snapshots(
            tenant_id,policy_key="runtime-dependency",
        )
        if not snapshot_rows or tenant_id is None:
            return CriticalGraphEdgeList(
                entity=_entity(entity_row),as_of=datetime.now(UTC),limitations=[{
                    "code":"NO_ACTIVE_POLICY_SNAPSHOT",
                    "message":"Critical-edge data is not ready for the runtime-dependency policy.",
                }],
            )
        snapshot = self._graph_snapshot(snapshot_rows[0])
        rows = await self.database.fetch_all(
            """
            SELECT metric.*,source.entity_type source_type,source.name source_name,
                   source.canonical_key source_key,source.properties->>'summary' source_summary,
                   target.entity_type target_type,target.name target_name,
                   target.canonical_key target_key,target.properties->>'summary' target_summary
            FROM graph_edge_metric metric
            JOIN entity source ON source.id=metric.subject_entity_id
            JOIN entity target ON target.id=metric.object_entity_id
            WHERE metric.run_id=%s AND metric.tenant_id=%s AND metric.metric_key='spof.bridge'
              AND %s IN (metric.subject_entity_id,metric.object_entity_id)
            ORDER BY metric.numeric_value DESC NULLS LAST,metric.fact_assertion_id
            """,
            (snapshot.analysis_run_id,tenant_id,entity_id),tenant_id=tenant_id,
        )
        return CriticalGraphEdgeList(
            entity=_entity(entity_row),snapshot=snapshot,edges=[CriticalGraphEdge(
                fact_id=row["fact_assertion_id"],source=EntitySummary(
                    id=row["subject_entity_id"],kind=row["source_type"],name=row["source_name"],
                    canonical_key=row.get("source_key"),summary=row.get("source_summary"),
                ),target=EntitySummary(
                    id=row["object_entity_id"],kind=row["target_type"],name=row["target_name"],
                    canonical_key=row.get("target_key"),summary=row.get("target_summary"),
                ),score=_number(row.get("numeric_value")),components=row.get("components") or {},
                supporting_fact_ids=[row["fact_assertion_id"]],
                limitations=row.get("limitations") or [],
            ) for row in rows],as_of=snapshot.as_of,limitations=list(snapshot.limitations),
        )

    async def semantic_search(
        self,request: SemanticSearchRequest,*,tenant_id: UUID | None,
    ) -> SemanticSearchResponse:
        if tenant_id is None:
            raise APIError(400,"TENANT_REQUIRED","Semantic search requires a tenant context.")
        space = await self.database.fetch_one(
            """
            SELECT space.id,space.space_key,space.provider,space.model_or_algorithm,
                   space.dimensions,space.normalization,space.template_version,
                   policy.external_processing_allowed,policy.sensitive_content_allowed,
                   policy.provider_base_url,
                   CASE WHEN secret.id IS NULL THEN NULL
                        ELSE pgp_sym_decrypt(secret.ciphertext,%s)::text END AS api_key
            FROM active_embedding_space active
            JOIN embedding_space space ON space.id=active.embedding_space_id
              AND space.tenant_id=active.tenant_id
            JOIN tenant_embedding_policy policy ON policy.tenant_id=active.tenant_id
            LEFT JOIN tenant_secret secret ON secret.id=policy.credential_secret_id
              AND secret.tenant_id=policy.tenant_id
            WHERE active.tenant_id=%s AND active.space_kind='SEMANTIC_ENTITY'
              AND policy.enabled AND space.lifecycle_state='ACTIVE'
              AND space.coverage_ratio>=0.95
              AND coalesce((space.evaluation->>'passed')::boolean,false)
            """,
            (self.credential_encryption_key,tenant_id),tenant_id=tenant_id,
        )
        if space is None:
            raise APIError(503,"SEMANTIC_SPACE_UNAVAILABLE","No evaluated semantic embedding space is active.")
        provider = str(space["provider"])
        if provider == "LOCAL":
            adapter = LocalHashEmbeddingAdapter()
        else:
            if not space["external_processing_allowed"]:
                raise APIError(503,"SEMANTIC_PROVIDER_DISABLED","Tenant policy forbids external query embedding.")
            if not space.get("provider_base_url") or not space.get("api_key"):
                raise APIError(503,"SEMANTIC_PROVIDER_UNCONFIGURED","Semantic provider credentials are incomplete.")
            adapter = OpenAICompatibleEmbeddingAdapter(
                base_url=space["provider_base_url"],api_key=space["api_key"],
            )
        try:
            embedded = await asyncio.to_thread(
                adapter.embed,request.query,dimensions=int(space["dimensions"]),
                model=space["model_or_algorithm"],
            )
        except Exception as error:
            raise APIError(
                503,"SEMANTIC_PROVIDER_UNAVAILABLE","The configured semantic embedding provider is unavailable.",
                {"error_type":type(error).__name__},
            ) from error
        entity_types = sorted(set(request.entity_types))
        namespaces = sorted(set(request.namespace))
        rows = await self.database.fetch_all(
            """
            WITH scored AS (
              SELECT entity.id,entity.entity_type,entity.name,entity.canonical_key,
                     entity.properties->>'summary' AS summary,document.input_hash,
                     document.sensitivity,document.rendered_content,
                     document.source_fact_ids,
                     1-(embedding.embedding<=>%s::vector) AS score
              FROM entity_embedding embedding
              JOIN embedding_document document
                ON document.embedding_space_id=embedding.embedding_space_id
               AND document.entity_id=embedding.entity_id
              JOIN entity ON entity.id=embedding.entity_id
              WHERE embedding.tenant_id=%s AND embedding.embedding_space_id=%s
                AND (cardinality(%s::text[])=0 OR entity.entity_type=ANY(%s::text[]))
                AND (cardinality(%s::text[])=0 OR entity.namespace=ANY(%s::text[]))
            )
            SELECT * FROM scored WHERE score>=%s
            ORDER BY score DESC,id LIMIT %s
            """,
            (
                vector_literal(embedded.values),tenant_id,space["id"],entity_types,entity_types,
                namespaces,namespaces,request.min_score,request.limit,
            ),tenant_id=tenant_id,
        )
        hits: list[SemanticSearchHit] = []
        for row in rows:
            matched_terms,excerpt = _semantic_match_details(
                request.query,str(row.get("rendered_content") or ""),
            )
            restricted = row["sensitivity"]=="RESTRICTED"
            hits.append(SemanticSearchHit(
                entity=_entity(row),score=max(-1,min(1,_number(row["score"]))),
                input_hash=row["input_hash"],sensitivity=row["sensitivity"],
                matched_terms=matched_terms,excerpt=None if restricted else excerpt,
                source_fact_ids=row.get("source_fact_ids") or [],
                limitations=([{
                    "code":"RESTRICTED_EXCERPT_WITHHELD",
                    "message":"The matched document is restricted; text was not returned.",
                }] if restricted else []),
            ))
        return SemanticSearchResponse(
            space_id=space["id"],space_key=space["space_key"],
            model_or_algorithm=space["model_or_algorithm"],template_version=space["template_version"],
            query_hash=embedding_content_hash(request.query),
            hits=hits,
            as_of=datetime.now(UTC),
            limitations=[{
                "code":"EXACT_SEARCH","message":"Results use exact tenant-filtered cosine search; no approximate index was used."
            }],
        )

    async def embedding_status(self,*,tenant_id: UUID | None) -> EmbeddingStatus:
        if tenant_id is None:
            return EmbeddingStatus(
                as_of=datetime.now(UTC),enabled=False,provider="UNCONFIGURED",model="",
                pending_jobs=0,running_jobs=0,failed_jobs=0,
                limitations=[{"code":"TENANT_REQUIRED","message":"Embedding status requires a tenant context."}],
            )
        policy = await self.database.fetch_one(
            "SELECT enabled,provider,model FROM tenant_embedding_policy WHERE tenant_id=%s",
            (tenant_id,),tenant_id=tenant_id,
        )
        workload = await self.database.fetch_one(
            """
            SELECT count(*) FILTER(WHERE status IN ('PENDING','RETRY_WAIT')) pending_jobs,
                   count(*) FILTER(WHERE status='RUNNING') running_jobs,
                   count(*) FILTER(WHERE status='DEAD_LETTER') failed_jobs
            FROM embedding_job WHERE tenant_id=%s
            """,
            (tenant_id,),tenant_id=tenant_id,
        ) or {}
        rows = await self.database.fetch_all(
            """
            SELECT space.*,active.embedding_space_id IS NOT NULL AS is_active
            FROM embedding_space space
            LEFT JOIN active_embedding_space active ON active.embedding_space_id=space.id
            WHERE space.tenant_id=%s AND space.lifecycle_state IN ('ACTIVE','SHADOW')
            ORDER BY space.space_kind,space.created_at DESC
            """,
            (tenant_id,),tenant_id=tenant_id,
        )
        snapshots = [(EmbeddingSpaceSnapshot(
            id=row["id"],space_key=row["space_key"],space_kind=row["space_kind"],
            lifecycle_state=row["lifecycle_state"],provider=row["provider"],
            model_or_algorithm=row["model_or_algorithm"],dimensions=row["dimensions"],
            template_version=row["template_version"],coverage_ratio=row["coverage_ratio"],
            evaluation=row["evaluation"],updated_at=row["updated_at"],
        ),bool(row["is_active"])) for row in rows]
        limitations: list[dict[str,Any]] = []
        if policy is None:
            limitations.append({"code":"EMBEDDING_POLICY_UNCONFIGURED","message":"No tenant embedding policy is configured."})
        if not any(active for _,active in snapshots):
            limitations.append({"code":"NO_ACTIVE_EMBEDDING_SPACE","message":"Search remains unavailable until a shadow space passes its gates."})
        for snapshot,active in snapshots:
            if active and (
                snapshot.coverage_ratio<0.95 or snapshot.evaluation.get("passed") is not True
            ):
                limitations.append({
                    "code":"ACTIVE_EMBEDDING_SPACE_INVALIDATED",
                    "message":"The linked semantic space no longer passes its coverage or reviewed-relevance gate; search is fail-closed until reevaluation.",
                    "space_id":str(snapshot.id),
                })
        return EmbeddingStatus(
            as_of=datetime.now(UTC),enabled=bool(policy and policy["enabled"]),
            provider=str(policy["provider"] if policy else "UNCONFIGURED"),
            model=str(policy["model"] if policy else ""),
            pending_jobs=int(workload.get("pending_jobs") or 0),
            running_jobs=int(workload.get("running_jobs") or 0),
            failed_jobs=int(workload.get("failed_jobs") or 0),
            active_spaces=[snapshot for snapshot,active in snapshots if active],
            shadow_spaces=[snapshot for snapshot,active in snapshots if not active],
            limitations=limitations,
        )

    async def similar_applications(
        self,application_id: UUID,*,tenant_id: UUID | None,
        review_state: str | None=None,cursor: str | None=None,limit: int,
    ) -> ApplicationSimilarityList:
        subject_row = await self._get_entity(application_id,tenant_id)
        if subject_row["entity_type"] not in {
            "Application","Technology","Capability","BusinessCapability",
        }:
            raise APIError(
                400,"SIMILARITY_ENTITY_TYPE_UNSUPPORTED",
                "Similarity is available for applications, technologies, and capabilities.",
            )
        cursor_data = _decode_cursor(cursor,"similarity")
        try:
            cursor_score = float(cursor_data["score"]) if cursor_data else None
            cursor_id = UUID(cursor_data["id"]) if cursor_data else None
        except (KeyError,TypeError,ValueError) as error:
            raise APIError(400,"INVALID_CURSOR","The pagination cursor is invalid.") from error
        rows = await self.database.fetch_all(
            """
            SELECT candidate.id,candidate.score,candidate.method_version,candidate.components,
                   candidate.overlap_features,candidate.differences,candidate.coverage,
                   candidate.limitations,candidate.review_state,candidate.created_at,
                   peer.id AS peer_id,peer.entity_type AS peer_entity_type,peer.name AS peer_name,
                   peer.canonical_key AS peer_canonical_key,peer.properties->>'summary' AS peer_summary
            FROM application_similarity_candidate candidate
            JOIN entity peer ON peer.id=CASE WHEN candidate.left_entity_id=%s
              THEN candidate.right_entity_id ELSE candidate.left_entity_id END
            WHERE candidate.tenant_id=%s
              AND candidate.entity_kind=%s
              AND %s IN (candidate.left_entity_id,candidate.right_entity_id)
              AND (%s::text IS NULL OR candidate.review_state=%s)
              AND (
                %s::double precision IS NULL OR candidate.score<%s
                OR (candidate.score=%s AND candidate.id>%s::uuid)
              )
            ORDER BY candidate.score DESC,candidate.id LIMIT %s
            """,
            (
                application_id,tenant_id,subject_row["entity_type"],application_id,
                review_state,review_state,cursor_score,cursor_score,cursor_score,cursor_id,
                limit+1,
            ),tenant_id=tenant_id,
        )
        has_next = len(rows)>limit
        rows = rows[:limit]
        return ApplicationSimilarityList(
            subject=_entity(subject_row),
            candidates=[ApplicationSimilarityCandidate(
                id=row["id"],application=EntitySummary(
                    id=row["peer_id"],kind=row["peer_entity_type"],name=row["peer_name"],
                    canonical_key=row.get("peer_canonical_key"),summary=row.get("peer_summary"),
                ),score=row["score"],method_version=row["method_version"],
                components=row["components"],overlaps=row["overlap_features"],
                differences=row["differences"],coverage=row["coverage"],
                limitations=row["limitations"],review_state=row["review_state"],
                created_at=row["created_at"],
            ) for row in rows],
            as_of=datetime.now(UTC),
            limitations=[] if rows else [{
                "code":"SIMILARITY_NOT_EVALUATED","message":"No explainable similarity candidates are available for this entity and filter."
            }],
            page_info=PageInfo(
                has_next_page=has_next,
                next_cursor=(_encode_cursor(
                    "similarity",score=rows[-1]["score"],id=str(rows[-1]["id"]),
                ) if has_next else None),
            ),
        )

    async def review_application_similarity(
        self,candidate_id: UUID,review: ApplicationSimilarityReviewRequest,
        *,tenant_id: UUID | None,actor_key: str,
    ) -> ApplicationSimilarityReviewResult:
        if tenant_id is None:
            raise APIError(400,"TENANT_REQUIRED","Similarity review requires a tenant context.")
        async with self.database.session(tenant_id) as connection:
            cursor = await connection.execute(
                """SELECT id,score,method_version FROM application_similarity_candidate
                WHERE id=%s AND tenant_id=%s FOR UPDATE""",
                (candidate_id,tenant_id),
            )
            candidate = await cursor.fetchone()
            if candidate is None:
                raise APIError(404,"SIMILARITY_CANDIDATE_NOT_FOUND","The similarity candidate was not found.")
            await connection.execute(
                """
                INSERT INTO application_similarity_feedback(
                  tenant_id,candidate_id,decision,reason_code,rationale,
                  candidate_method_version,candidate_score,actor_key
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    tenant_id,candidate_id,review.decision,review.reason_code,review.rationale,
                    candidate["method_version"],candidate["score"],actor_key,
                ),
            )
            await connection.execute(
                "UPDATE application_similarity_candidate SET review_state=%s,updated_at=now() WHERE id=%s",
                ("UNREVIEWED" if review.decision=="REOPENED" else review.decision,candidate_id),
            )
        return ApplicationSimilarityReviewResult(
            candidate_id=candidate_id,
            review_state="UNREVIEWED" if review.decision=="REOPENED" else review.decision,
            reviewed_at=datetime.now(UTC),
        )

    async def architecture_taxonomy(self) -> ArchitectureTaxonomyResponse:
        return load_architecture_catalog().taxonomy

    async def architecture_reference_models(self) -> ArchitectureReferenceModelList:
        return load_architecture_catalog().reference_models()

    async def architecture_reference_model(
        self, key: str, *, version: str | None,
    ) -> ArchitectureReferenceModel:
        model = load_architecture_catalog().reference_model
        if key != model.key or (version is not None and version != model.version):
            raise APIError(404, "REFERENCE_MODEL_NOT_FOUND", "The architecture reference model was not found.")
        return model

    async def canvas_templates(self) -> CanvasTemplateList:
        return load_architecture_catalog().templates()

    async def _canvas_policy_state(
        self,
        *,
        tenant_id: UUID | None,
    ) -> tuple[ArchitectureProfileStateModel | None, str | None, list[str]]:
        if tenant_id is None:
            return None, None, []
        row = await self.database.fetch_one(
            """
            SELECT state,fingerprint
            FROM tenant_architecture_profile
            WHERE tenant_id=%s AND status='ACTIVE'
              AND reference_model_key='architecture.stackgraph.reference'
              AND reference_model_version='1.0.0'
            ORDER BY updated_at DESC,id DESC LIMIT 1
            """,
            (tenant_id,),
            tenant_id=tenant_id,
        )
        if row is not None:
            return (
                ArchitectureProfileStateModel.model_validate(row["state"]),
                str(row["fingerprint"]),
                [],
            )

        legacy_rows = await self.database.fetch_all(
            """
            SELECT function_key,allowed_technology_ids,prohibited_technology_ids,
                   policy_fingerprint
            FROM tenant_code_policy
            WHERE tenant_id=%s
            ORDER BY function_key
            """,
            (tenant_id,),
            tenant_id=tenant_id,
        )
        if not legacy_rows:
            return None, None, []

        catalog = load_architecture_catalog()
        capability_cells = {
            key: cell.key
            for cell in catalog.reference_model.cells
            for binding in cell.bindings
            if binding.kind == "CAPABILITY"
            for key in binding.keys
        }
        aggregated: dict[str, dict[str, set[UUID]]] = {}
        unresolved: list[str] = []
        for legacy in legacy_rows:
            canonical = catalog.canonical_capability_key(str(legacy["function_key"]))
            cell_key = capability_cells.get(canonical or "")
            if cell_key is None:
                unresolved.append(str(legacy["function_key"]))
                continue
            decisions = aggregated.setdefault(cell_key, {"allowed": set(), "prohibited": set()})
            decisions["allowed"].update(UUID(str(item)) for item in legacy["allowed_technology_ids"])
            decisions["prohibited"].update(
                UUID(str(item)) for item in legacy["prohibited_technology_ids"]
            )
        policies = []
        for cell_key, decisions in sorted(aggregated.items()):
            prohibited = decisions["prohibited"]
            policies.append(TenantCellPolicyModel(
                cell_key=cell_key,
                applicability="OPTIONAL",
                minimum_implementations=0,
                allowed_technology_ids=sorted(decisions["allowed"] - prohibited, key=str),
                prohibited_technology_ids=sorted(prohibited, key=str),
                rationale="Migrated read-only from tenant code policy v1.",
            ))
        state = ArchitectureProfileStateModel(
            name="Legacy code-policy overlay",
            reference_model_key=catalog.reference_model.key,
            reference_model_version=catalog.reference_model.version,
            cell_policies=policies,
        )
        fingerprint = sha256_fingerprint({
            "source": "tenant-code-policy/v1",
            "policies": [
                {
                    "function_key": str(item["function_key"]),
                    "fingerprint": str(item["policy_fingerprint"]),
                }
                for item in legacy_rows
            ],
        })
        return state, fingerprint, unresolved

    async def _canvas_scope_technology_rows(
        self,
        *,
        scope: str,
        subject_id: UUID | None,
        tenant_id: UUID | None,
    ) -> list[dict[str, Any]]:
        if tenant_id is None:
            return []
        return await self.database.fetch_all(
            """
            WITH scoped_repositories AS (
              SELECT repository.id
              FROM entity repository
              WHERE repository.tenant_id=%s
                AND repository.namespace='ENTERPRISE'
                AND repository.entity_type='Repository'
                AND (
                  %s='ESTATE'
                  OR (%s='REPOSITORY' AND repository.id=%s)
                  OR (%s='APPLICATION' AND EXISTS (
                    SELECT 1
                    FROM current_relationship relationship
                    JOIN entity application ON application.id=CASE
                      WHEN relationship.source_entity_id=repository.id
                        THEN relationship.target_entity_id
                      ELSE relationship.source_entity_id END
                    WHERE (relationship.source_entity_id=repository.id
                           OR relationship.target_entity_id=repository.id)
                      AND relationship.relationship_type IN ('IMPLEMENTED_BY','IMPLEMENTS','CONTAINS')
                      AND application.namespace='ENTERPRISE'
                      AND application.entity_type='Application'
                      AND application.id=%s
                  ))
                )
            ), repository_applications AS (
              SELECT DISTINCT repository.id repository_id,application.id application_id
              FROM scoped_repositories repository
              JOIN current_relationship relationship
                ON relationship.source_entity_id=repository.id
                OR relationship.target_entity_id=repository.id
              JOIN entity application ON application.id=CASE
                WHEN relationship.source_entity_id=repository.id
                  THEN relationship.target_entity_id
                ELSE relationship.source_entity_id END
              WHERE relationship.relationship_type IN ('IMPLEMENTED_BY','IMPLEMENTS','CONTAINS')
                AND application.namespace='ENTERPRISE'
                AND application.entity_type='Application'
            )
            SELECT technology.*,
                   array_agg(DISTINCT dependency.id) usage_fact_ids,
                   max(dependency.confidence) usage_confidence,
                   array_agg(DISTINCT dependency.properties)
                     FILTER (WHERE dependency.properties<>'{}'::jsonb) usage_property_sets,
                   array_agg(DISTINCT dependency.assertion_class) usage_assertion_classes,
                   count(DISTINCT repository.id)::integer adoption_repositories,
                   count(DISTINCT repository_applications.application_id)::integer adoption_applications,
                   0::integer adoption_deployments
            FROM scoped_repositories repository
            JOIN fact_assertion dependency
              ON dependency.subject_entity_id=repository.id
             AND dependency.system_to IS NULL
             AND dependency.predicate IN ('DEPENDS_ON','USES','RUNS_ON','BUILT_ON','HAS_VERSION')
            JOIN entity technology ON technology.id=dependency.object_entity_id
            LEFT JOIN repository_applications
              ON repository_applications.repository_id=repository.id
            WHERE technology.namespace IN ('TECHNOLOGY','OSS')
              AND technology.entity_type<>'Capability'
            GROUP BY technology.id
            ORDER BY technology.name,technology.id
            """,
            (
                tenant_id,
                scope,
                scope,
                subject_id,
                scope,
                subject_id,
            ),
            tenant_id=tenant_id,
        )

    async def _canvas_scope_deployment_rows(
        self,
        *,
        scope: str,
        subject_id: UUID | None,
        tenant_id: UUID | None,
    ) -> list[dict[str, Any]]:
        if tenant_id is None:
            return []
        return await self.database.fetch_all(
            """
            WITH scoped_repositories AS (
              SELECT repository.id
              FROM entity repository
              WHERE repository.tenant_id=%s
                AND repository.namespace='ENTERPRISE'
                AND repository.entity_type='Repository'
                AND (
                  %s='ESTATE'
                  OR (%s='REPOSITORY' AND repository.id=%s)
                  OR (%s='APPLICATION' AND EXISTS (
                    SELECT 1 FROM current_relationship relationship
                    WHERE (
                      (relationship.source_entity_id=%s AND relationship.target_entity_id=repository.id)
                      OR (relationship.target_entity_id=%s AND relationship.source_entity_id=repository.id)
                    )
                      AND relationship.relationship_type IN ('IMPLEMENTED_BY','IMPLEMENTS','CONTAINS')
                  ))
                )
            ), scoped_applications AS (
              SELECT DISTINCT application.id
              FROM scoped_repositories repository
              JOIN current_relationship relationship
                ON relationship.source_entity_id=repository.id
                OR relationship.target_entity_id=repository.id
              JOIN entity application ON application.id=CASE
                WHEN relationship.source_entity_id=repository.id
                  THEN relationship.target_entity_id
                ELSE relationship.source_entity_id END
              WHERE relationship.relationship_type IN ('IMPLEMENTED_BY','IMPLEMENTS','CONTAINS')
                AND application.namespace='ENTERPRISE'
                AND application.entity_type='Application'
              UNION
              SELECT %s::uuid WHERE %s='APPLICATION'
            ), scope_entities AS (
              SELECT id FROM scoped_repositories
              UNION SELECT id FROM scoped_applications
            ), direct_deployment AS (
              SELECT deployment.id,deployment_fact.id fact_id,deployment_fact.confidence
              FROM scope_entities scoped
              JOIN fact_assertion deployment_fact
                ON deployment_fact.system_to IS NULL
               AND (deployment_fact.subject_entity_id=scoped.id
                    OR deployment_fact.object_entity_id=scoped.id)
              JOIN entity deployment ON deployment.id=CASE
                WHEN deployment_fact.subject_entity_id=scoped.id
                  THEN deployment_fact.object_entity_id
                ELSE deployment_fact.subject_entity_id END
              WHERE deployment.namespace='DEPLOYMENT'
            ), expanded_deployment AS (
              SELECT * FROM direct_deployment
              UNION ALL
              SELECT related.id,relationship.id,relationship.confidence
              FROM direct_deployment direct
              JOIN fact_assertion relationship
                ON relationship.system_to IS NULL
               AND (relationship.subject_entity_id=direct.id
                    OR relationship.object_entity_id=direct.id)
              JOIN entity related ON related.id=CASE
                WHEN relationship.subject_entity_id=direct.id
                  THEN relationship.object_entity_id
                ELSE relationship.subject_entity_id END
              WHERE related.namespace='DEPLOYMENT'
            )
            SELECT deployment.*,
                   array_agg(DISTINCT expanded.fact_id) usage_fact_ids,
                   max(expanded.confidence) usage_confidence,
                   count(DISTINCT deployment.id)::integer adoption_deployments
            FROM expanded_deployment expanded
            JOIN entity deployment ON deployment.id=expanded.id
            GROUP BY deployment.id
            ORDER BY deployment.entity_type,deployment.name,deployment.id
            """,
            (
                tenant_id,
                scope,
                scope,
                subject_id,
                scope,
                subject_id,
                subject_id,
                subject_id,
                scope,
            ),
            tenant_id=tenant_id,
        )

    async def _canvas_scope_observation(
        self,
        *,
        scope: str,
        subject_id: UUID | None,
        tenant_id: UUID | None,
    ) -> dict[str, int]:
        if tenant_id is None:
            return {"in_scope": 0, "observed": 0, "fresh": 0}
        row = await self.database.fetch_one(
            """
            SELECT count(*)::integer in_scope,
                   count(*) FILTER (WHERE repository.last_seen_at IS NOT NULL)::integer observed,
                   count(*) FILTER (
                     WHERE repository.last_seen_at >= now()-interval '7 days'
                   )::integer fresh
            FROM entity repository
            WHERE repository.tenant_id=%s
              AND repository.namespace='ENTERPRISE'
              AND repository.entity_type='Repository'
              AND (
                %s='ESTATE'
                OR (%s='REPOSITORY' AND repository.id=%s)
                OR (%s='APPLICATION' AND EXISTS (
                  SELECT 1 FROM current_relationship relationship
                  WHERE (
                    (relationship.source_entity_id=%s AND relationship.target_entity_id=repository.id)
                    OR (relationship.target_entity_id=%s AND relationship.source_entity_id=repository.id)
                  )
                    AND relationship.relationship_type IN ('IMPLEMENTED_BY','IMPLEMENTS','CONTAINS')
                ))
              )
            """,
            (tenant_id, scope, scope, subject_id, scope, subject_id, subject_id),
            tenant_id=tenant_id,
        ) or {}
        return {
            "in_scope": int(row.get("in_scope") or 0),
            "observed": int(row.get("observed") or 0),
            "fresh": int(row.get("fresh") or 0),
        }

    async def canvas_projection(
        self,
        selector: CanvasProjectionSelectorModel,
        *,
        tenant_id: UUID | None,
        reference_model_key: str,
        template_key: str,
    ) -> CanvasProjection:
        as_of = datetime.now(UTC)
        catalog = load_architecture_catalog()
        if reference_model_key != catalog.reference_model.key:
            raise APIError(404, "REFERENCE_MODEL_NOT_FOUND", "The architecture reference model was not found.")
        if template_key != catalog.template.key:
            raise APIError(404, "CANVAS_TEMPLATE_NOT_FOUND", "The canvas template was not found.")

        scope = selector.scope
        subject_id = selector.subject_id
        subject = None
        if scope == "APPLICATION":
            assert subject_id is not None
            subject = _entity(await self._get_entity(
                subject_id, tenant_id, namespace="ENTERPRISE", entity_type="Application",
            ))
        elif scope == "REPOSITORY":
            assert subject_id is not None
            subject = _entity(await self._get_entity(
                subject_id, tenant_id, namespace="ENTERPRISE", entity_type="Repository",
            ))

        profile_state, profile_fingerprint, unresolved_policy_keys = await self._canvas_policy_state(
            tenant_id=tenant_id,
        )
        policies = {
            policy.cell_key: policy
            for policy in (profile_state.cell_policies if profile_state else [])
            if _canvas_policy_applies(policy, scope, subject_id, as_of)
        }
        cells_by_key = catalog.cells_by_key
        capability_cells: dict[str, str] = {}
        category_cells: dict[str, str] = {}
        resource_cells: dict[str, str] = {}
        entity_type_cells: dict[str, str] = {}
        for cell in catalog.reference_model.cells:
            for binding in cell.bindings:
                target = {
                    "CAPABILITY": capability_cells,
                    "CATEGORY": category_cells,
                    "RESOURCE_KIND": resource_cells,
                    "ENTITY_TYPE": entity_type_cells,
                }.get(binding.kind)
                if target is not None:
                    for key in binding.keys:
                        target[key] = cell.key

        observation_counts = (
            {"in_scope": 0, "observed": 0, "fresh": 0}
            if scope == "TARGET"
            else await self._canvas_scope_observation(
                scope=scope, subject_id=subject_id, tenant_id=tenant_id,
            )
        )
        technology_rows: list[dict[str, Any]] = []
        deployment_rows: list[dict[str, Any]] = []
        if scope != "TARGET":
            technology_rows = await self._canvas_scope_technology_rows(
                scope=scope, subject_id=subject_id, tenant_id=tenant_id,
            )
            deployment_rows = await self._canvas_scope_deployment_rows(
                scope=scope, subject_id=subject_id, tenant_id=tenant_id,
            )

        has_resource_evidence = False
        grouped = []
        row_by_id = {UUID(str(row["id"])): row for row in technology_rows}
        if technology_rows:
            catalog_rows = await self._technology_classification_catalog(tenant_id)
            grouped = _group_application_technologies(technology_rows, catalog_rows)
            has_resource_evidence = any(
                usage.resource_details is not None
                for group in grouped
                for function in group.functions
                for usage in function.technologies
            )

        supported_sensors = set()
        if observation_counts["observed"]:
            supported_sensors.update({"REPOSITORY_DEPENDENCY", "REPOSITORY_CODE"})
        if has_resource_evidence:
            supported_sensors.add("REPOSITORY_RESOURCE")
        if deployment_rows:
            supported_sensors.add("DEPLOYMENT")

        occupant_buckets: dict[str, dict[UUID, dict[str, Any]]] = defaultdict(dict)
        tray_items: dict[tuple[UUID, str], CanvasClassificationTrayItemModel] = {}

        def add_occupant(
            cell_key: str,
            *,
            technology: EntitySummary,
            placement_key: str,
            classification: str,
            confidence: float,
            citations: list[Citation],
            adoption_applications: int,
            adoption_repositories: int,
            adoption_deployments: int,
            policy_reference: str | None = None,
        ) -> None:
            bucket = occupant_buckets[cell_key].setdefault(technology.id, {
                "technology": technology,
                "placement_keys": set(),
                "classification": classification,
                "confidence": confidence,
                "citations": {},
                "adoption_applications": adoption_applications,
                "adoption_repositories": adoption_repositories,
                "adoption_deployments": adoption_deployments,
                "policy_reference": policy_reference,
            })
            bucket["placement_keys"].add(placement_key)
            bucket["confidence"] = min(bucket["confidence"], confidence)
            for citation in citations:
                bucket["citations"][citation.fact_id] = citation
            bucket["adoption_applications"] = max(
                bucket["adoption_applications"], adoption_applications,
            )
            bucket["adoption_repositories"] = max(
                bucket["adoption_repositories"], adoption_repositories,
            )
            bucket["adoption_deployments"] = max(
                bucket["adoption_deployments"], adoption_deployments,
            )

        if scope == "TARGET":
            technology_ids = {
                technology_id
                for policy in policies.values()
                for technology_id in (
                    *policy.preferred_technology_ids,
                    *policy.allowed_technology_ids,
                    *policy.discouraged_technology_ids,
                    *policy.prohibited_technology_ids,
                )
            }
            technology_entities = {}
            if technology_ids:
                rows = await self.database.fetch_all(
                    "SELECT * FROM entity WHERE id=ANY(%s::uuid[]) ORDER BY name,id",
                    (list(technology_ids),),
                    tenant_id=tenant_id,
                )
                technology_entities = {UUID(str(row["id"])): _entity(row) for row in rows}
            for cell_key, policy in policies.items():
                if cell_key not in cells_by_key:
                    continue
                for technology_id in technology_ids & {
                    *policy.preferred_technology_ids,
                    *policy.allowed_technology_ids,
                    *policy.discouraged_technology_ids,
                    *policy.prohibited_technology_ids,
                }:
                    technology = technology_entities.get(technology_id)
                    if technology is None:
                        technology = EntitySummary(
                            id=technology_id,
                            kind="Technology",
                            name=f"Unresolved technology {technology_id}",
                        )
                        tray_items[(technology_id, "UNRESOLVED_POLICY")] = (
                            CanvasClassificationTrayItemModel(
                                entity=technology,
                                reason="UNRESOLVED_POLICY",
                                detail=f"The active policy references a technology that is not visible: {technology_id}.",
                                citations=[],
                            )
                        )
                    add_occupant(
                        cell_key,
                        technology=technology,
                        placement_key=f"policy:{cell_key}",
                        classification="CURATED",
                        confidence=1.0,
                        citations=[],
                        adoption_applications=0,
                        adoption_repositories=0,
                        adoption_deployments=0,
                        policy_reference=profile_fingerprint,
                    )
        else:
            for group in grouped:
                for function in group.functions:
                    canonical = catalog.canonical_capability_key(function.function.key)
                    for usage in function.technologies:
                        row = row_by_id[usage.technology.id]
                        cell_keys: dict[str, str] = {}
                        if usage.resource_details is not None:
                            cell_key = resource_cells.get(usage.resource_details.resource_kind)
                            if cell_key:
                                cell_keys[cell_key] = f"resource:{usage.resource_details.resource_kind}"
                        if canonical:
                            cell_key = capability_cells.get(canonical)
                            if cell_key:
                                cell_keys[cell_key] = f"capability:{canonical}"
                        if not cell_keys and usage.category is not None:
                            cell_key = category_cells.get(usage.category.key)
                            if cell_key:
                                cell_keys[cell_key] = f"category:{usage.category.key}"
                        entity_type = str(row.get("entity_type") or usage.technology.kind)
                        entity_cell = entity_type_cells.get(entity_type)
                        if entity_cell:
                            cell_keys[entity_cell] = f"entity-type:{entity_type}"
                        if not cell_keys:
                            key = (usage.technology.id, "UNCLASSIFIED")
                            tray_items[key] = CanvasClassificationTrayItemModel(
                                entity=usage.technology,
                                reason="UNCLASSIFIED",
                                detail=(
                                    f"No canonical architecture binding resolved function "
                                    f"{function.function.key!r} and category "
                                    f"{usage.category.key if usage.category else 'none'!r}."
                                ),
                                citations=usage.citations,
                            )
                            continue
                        for cell_key, placement_key in cell_keys.items():
                            add_occupant(
                                cell_key,
                                technology=usage.technology,
                                placement_key=placement_key,
                                classification=usage.classification,
                                confidence=usage.confidence,
                                citations=usage.citations,
                                adoption_applications=int(row.get("adoption_applications") or 0),
                                adoption_repositories=int(row.get("adoption_repositories") or 0),
                                adoption_deployments=int(row.get("adoption_deployments") or 0),
                            )

            for row in deployment_rows:
                entity_type = str(row["entity_type"])
                cell_key = entity_type_cells.get(entity_type)
                fact_ids = [UUID(str(value)) for value in row.get("usage_fact_ids") or []]
                citations = [Citation(
                    fact_id=fact_id,
                    label="Deployment evidence",
                    href=f"/api/v1/facts/{fact_id}/evidence",
                ) for fact_id in fact_ids]
                deployment = _entity(row)
                if cell_key is None or not citations:
                    tray_items[(deployment.id, "UNCLASSIFIED")] = CanvasClassificationTrayItemModel(
                        entity=deployment,
                        reason="UNCLASSIFIED",
                        detail=f"Deployment entity type {entity_type!r} has no canonical canvas binding.",
                        citations=citations,
                    )
                    continue
                add_occupant(
                    cell_key,
                    technology=deployment,
                    placement_key=f"entity-type:{entity_type}",
                    classification="DETERMINISTIC",
                    confidence=_number(row.get("usage_confidence"), 1.0),
                    citations=citations,
                    adoption_applications=1 if scope == "APPLICATION" else 0,
                    adoption_repositories=1 if scope == "REPOSITORY" else 0,
                    adoption_deployments=int(row.get("adoption_deployments") or 1),
                )

        for function_key in unresolved_policy_keys:
            unresolved_id = uuid5(NAMESPACE_URL, f"stackgraph:unresolved-policy:{function_key}")
            tray_items[(unresolved_id, "UNRESOLVED_POLICY")] = CanvasClassificationTrayItemModel(
                entity=EntitySummary(
                    id=unresolved_id,
                    kind="PolicyFunction",
                    name=function_key,
                    canonical_key=f"tenant-code-function:{function_key}",
                ),
                reason="UNRESOLVED_POLICY",
                detail="The legacy tenant code-policy function does not map to a canonical architecture cell.",
                citations=[],
            )

        projected_cells: list[CanvasCellProjectionModel] = []
        for definition in catalog.reference_model.cells:
            policy = policies.get(definition.key)
            expectation = CellExpectationModel(
                applicability=policy.applicability if policy else definition.default_expectation.applicability,
                minimum_implementations=(
                    policy.minimum_implementations if policy else definition.default_expectation.minimum_implementations
                ),
                maximum_implementations=(
                    policy.maximum_implementations if policy else definition.default_expectation.maximum_implementations
                ),
                allowed_diversity=(
                    policy.allowed_diversity if policy else definition.default_expectation.allowed_diversity
                ),
            )
            required = set(definition.required_sensor_kinds)
            missing_sensors = sorted(required - supported_sensors)
            if scope == "TARGET":
                observation_status = "NOT_APPLICABLE"
                missing_inputs: list[str] = []
            elif not supported_sensors & required:
                observation_status = "MISSING"
                missing_inputs = [f"missing sensor: {sensor}" for sensor in missing_sensors]
            elif (
                missing_sensors
                or observation_counts["observed"] < observation_counts["in_scope"]
                or observation_counts["fresh"] < observation_counts["observed"]
            ):
                observation_status = "PARTIAL"
                missing_inputs = [f"missing sensor: {sensor}" for sensor in missing_sensors]
                if observation_counts["observed"] < observation_counts["in_scope"]:
                    missing_inputs.append("unscanned repositories in scope")
                if observation_counts["fresh"] < observation_counts["observed"]:
                    missing_inputs.append("stale repository evidence")
            else:
                observation_status = "COMPLETE"
                missing_inputs = []
            observation = CellObservationStatusModel(
                required_sensor_kinds=definition.required_sensor_kinds,
                supported_sensor_kinds=sorted(supported_sensors & required),
                in_scope_subjects=observation_counts["in_scope"],
                observed_subjects=observation_counts["observed"],
                fresh_subjects=observation_counts["fresh"],
                status=observation_status,
                missing_inputs=missing_inputs,
                method_version=CANVAS_OBSERVATION_METHOD_VERSION,
                input_fingerprint=sha256_fingerprint({
                    "cell": definition.key,
                    "scope": scope,
                    "subject": str(subject_id) if subject_id else None,
                    "required": sorted(required),
                    "supported": sorted(supported_sensors),
                    "counts": observation_counts,
                }),
            )
            occupants = []
            for value in occupant_buckets.get(definition.key, {}).values():
                technology_id = value["technology"].id
                occupants.append(CanvasOccupantModel(
                    technology=value["technology"],
                    placement_keys=sorted(value["placement_keys"]),
                    classification=value["classification"],
                    confidence=value["confidence"],
                    confidence_label=_confidence_label(value["confidence"]),
                    adoption_applications=value["adoption_applications"],
                    adoption_repositories=value["adoption_repositories"],
                    adoption_deployments=value["adoption_deployments"],
                    policy_status=_canvas_policy_status(technology_id, policy, subject_id, as_of),
                    citations=list(value["citations"].values()),
                    policy_reference=value["policy_reference"],
                ))
            occupants.sort(key=lambda item: (
                -item.adoption_repositories,
                item.technology.name.lower(),
                str(item.technology.id),
            ))
            unbound = all(binding.kind == "UNBOUND" for binding in definition.bindings)
            if expectation.applicability == "NOT_APPLICABLE":
                state = "NOT_APPLICABLE"
                state_reason = "The effective tenant policy marks this concern not applicable."
            elif occupants:
                state = "POPULATED"
                state_reason = f"{len(occupants)} evidenced implementation(s) resolved to this cell."
            elif scope == "TARGET":
                state = "UNBOUND" if unbound else "EMPTY"
                state_reason = (
                    next(binding.reason for binding in definition.bindings if binding.kind == "UNBOUND")
                    if unbound else "No target technology decision is configured for this cell."
                )
            elif unbound:
                state = "UNBOUND"
                state_reason = next(
                    binding.reason for binding in definition.bindings if binding.kind == "UNBOUND"
                ) or "StackGraph does not bind this concern."
            elif observation.status == "COMPLETE" and definition.absence_assertable:
                state = "EMPTY"
                state_reason = "Required evidence is complete and no implementation was found."
            else:
                state = "UNOBSERVED"
                state_reason = "; ".join(observation.missing_inputs) or (
                    "The available sensors cannot safely assert absence for this concern."
                )
            measures = _canvas_cell_measures(
                state=state,
                expectation=expectation,
                policy=policy,
                occupants=occupants,
                observation=observation,
            )
            citations = list({
                citation.fact_id: citation
                for occupant in occupants
                for citation in occupant.citations
            }.values())
            projected_cells.append(CanvasCellProjectionModel(
                cell_key=definition.key,
                state=state,
                state_reason=state_reason,
                occupants=occupants,
                occupant_total=len(occupants),
                unique_technology_total=len({item.technology.id for item in occupants}),
                observation=observation,
                expectation=expectation,
                measures=measures,
                policy=policy,
                insight_refs=[],
                citations=citations,
            ))

        sorted_tray_items = sorted(
            tray_items.values(),
            key=lambda item: (item.reason, item.entity.name.lower(), str(item.entity.id)),
        )
        tray = CanvasClassificationTrayModel(
            items=sorted_tray_items[:CANVAS_CLASSIFICATION_TRAY_LIMIT],
            total_count=len(sorted_tray_items),
            truncated=len(sorted_tray_items) > CANVAS_CLASSIFICATION_TRAY_LIMIT,
            unclassified_count=sum(item.reason == "UNCLASSIFIED" for item in tray_items.values()),
            ambiguous_count=sum(item.reason == "AMBIGUOUS" for item in tray_items.values()),
            unresolved_policy_count=sum(
                item.reason == "UNRESOLVED_POLICY" for item in tray_items.values()
            ),
            filtered_count=sum(item.reason == "FILTERED" for item in tray_items.values()),
        )
        unique_technologies = {
            occupant.technology.id
            for cell in projected_cells
            for occupant in cell.occupants
        }
        summary = CanvasProjectionSummaryModel(
            populated_cells=sum(cell.state == "POPULATED" for cell in projected_cells),
            empty_cells=sum(cell.state == "EMPTY" for cell in projected_cells),
            not_applicable_cells=sum(cell.state == "NOT_APPLICABLE" for cell in projected_cells),
            unobserved_cells=sum(cell.state == "UNOBSERVED" for cell in projected_cells),
            unbound_cells=sum(cell.state == "UNBOUND" for cell in projected_cells),
            governed_cells=sum(cell.policy is not None for cell in projected_cells),
            cells_with_violations=sum(
                any(item.policy_status == "PROHIBITED" for item in cell.occupants)
                or (
                    cell.expectation.applicability == "REQUIRED"
                    and cell.state == "EMPTY"
                )
                for cell in projected_cells
            ),
            strong=sum(cell.measures and cell.measures.posture_band == "STRONG" for cell in projected_cells),
            adequate=sum(cell.measures and cell.measures.posture_band == "ADEQUATE" for cell in projected_cells),
            weak=sum(cell.measures and cell.measures.posture_band == "WEAK" for cell in projected_cells),
            at_risk=sum(cell.measures and cell.measures.posture_band == "AT_RISK" for cell in projected_cells),
            unique_technologies=len(unique_technologies),
            technology_cell_placements=sum(len(cell.occupants) for cell in projected_cells),
        )
        input_fingerprint = sha256_fingerprint({
            "method": CANVAS_PROJECTION_METHOD_VERSION,
            "reference_model": catalog.reference_model.content_hash,
            "template": catalog.template.content_hash,
            "profile": profile_fingerprint,
            "scope": scope,
            "subject": str(subject_id) if subject_id else None,
            "fact_ids": sorted({
                str(citation.fact_id)
                for cell in projected_cells
                for citation in cell.citations
            }),
            "states": [(cell.cell_key, cell.state) for cell in projected_cells],
        })
        return CanvasProjection(
            as_of=as_of,
            method_version=CANVAS_PROJECTION_METHOD_VERSION,
            taxonomy_key=catalog.taxonomy.key,
            taxonomy_version=catalog.taxonomy.version,
            taxonomy_content_hash=catalog.taxonomy.content_hash,
            reference_model_key=catalog.reference_model.key,
            reference_model_version=catalog.reference_model.version,
            reference_model_content_hash=catalog.reference_model.content_hash,
            template_key=catalog.template.key,
            template_version=catalog.template.version,
            tenant_profile_fingerprint=profile_fingerprint,
            scope=scope,
            subject=subject,
            cells=projected_cells,
            classification_tray=tray,
            summary=summary,
            input_fingerprint=input_fingerprint,
        )

    async def canvas_comparison(
        self,
        request: CanvasComparisonRequest,
        *,
        tenant_id: UUID | None,
    ) -> CanvasComparison:
        actual = await self.canvas_projection(
            request.actual,
            tenant_id=tenant_id,
            reference_model_key=request.reference_model_key,
            template_key=request.template_key,
        )
        baseline = await self.canvas_projection(
            request.baseline,
            tenant_id=tenant_id,
            reference_model_key=request.reference_model_key,
            template_key=request.template_key,
        )
        baseline_by_key = {cell.cell_key: cell for cell in baseline.cells}
        comparisons = []
        for actual_cell in actual.cells:
            baseline_cell = baseline_by_key.get(actual_cell.cell_key)
            if baseline_cell is None:
                raise APIError(
                    409,
                    "INCOMPATIBLE_CANVAS_PROJECTIONS",
                    "The projections do not contain the same canonical cells.",
                )
            preferred = sum(item.policy_status == "PREFERRED" for item in actual_cell.occupants)
            allowed = sum(item.policy_status == "ALLOWED" for item in actual_cell.occupants)
            discouraged = sum(item.policy_status == "DISCOURAGED" for item in actual_cell.occupants)
            prohibited = sum(item.policy_status == "PROHIBITED" for item in actual_cell.occupants)
            ungoverned = sum(item.policy_status == "UNGOVERNED" for item in actual_cell.occupants)
            unevaluable = actual_cell.state in {"UNOBSERVED", "UNBOUND"}
            required_absent = (
                not unevaluable
                and actual_cell.expectation.applicability == "REQUIRED"
                and len(actual_cell.occupants) < (
                    actual_cell.expectation.minimum_implementations or 1
                )
            )
            comparisons.append(CanvasCellComparisonModel(
                cell_key=actual_cell.cell_key,
                actual_state=actual_cell.state,
                baseline_state=baseline_cell.state,
                preferred_in_use=preferred,
                allowed_in_use=allowed,
                discouraged_in_use=discouraged,
                prohibited_in_use=prohibited,
                required_but_absent=required_absent,
                ungoverned_in_use=ungoverned,
                unevaluable=unevaluable,
            ))
        summary = CanvasComparisonSummaryModel(
            compared_cells=len(comparisons),
            aligned_cells=sum(
                not item.unevaluable
                and not item.required_but_absent
                and item.prohibited_in_use == 0
                and item.discouraged_in_use == 0
                for item in comparisons
            ),
            cells_with_violations=sum(
                item.prohibited_in_use > 0 or item.required_but_absent
                for item in comparisons
            ),
            required_but_absent_cells=sum(item.required_but_absent for item in comparisons),
            ungoverned_cells=sum(item.ungoverned_in_use > 0 for item in comparisons),
            unevaluable_cells=sum(item.unevaluable for item in comparisons),
        )
        input_fingerprint = sha256_fingerprint({
            "method": CANVAS_COMPARISON_METHOD_VERSION,
            "kind": request.comparison_kind,
            "actual": actual.input_fingerprint,
            "baseline": baseline.input_fingerprint,
        })
        return CanvasComparison(
            comparison_kind=request.comparison_kind,
            actual_projection_fingerprint=actual.input_fingerprint,
            baseline_projection_fingerprint=baseline.input_fingerprint,
            cells=comparisons,
            summary=summary,
            method_version=CANVAS_COMPARISON_METHOD_VERSION,
            input_fingerprint=input_fingerprint,
        )

    async def repository_detail(
        self,
        repository_id: UUID,
        *,
        tenant_id: UUID | None,
    ) -> RepositoryDetail:
        repository = await self._get_entity(
            repository_id, tenant_id, namespace="ENTERPRISE", entity_type="Repository",
        )
        profile_row = await self.database.fetch_one(
            """
            SELECT fact.id,fact.object_value,fact.confidence,fact.source_revision,
                   fact.observed_at,source.source_key
            FROM current_fact fact
            JOIN source_snapshot snapshot ON snapshot.id=fact.source_snapshot_id
            JOIN ingest_target target ON target.id=snapshot.ingest_target_id
            JOIN source_system source ON source.id=target.source_system_id
            WHERE fact.subject_entity_id=%s AND fact.predicate='HAS_PROPERTY'
              AND fact.object_value->>'record_kind'='repository_profile'
            ORDER BY fact.observed_at DESC,fact.id DESC LIMIT 1
            """,
            (repository_id,),
            tenant_id=tenant_id,
        )
        profile = None
        repository_summary = _entity(repository)
        if profile_row is not None and isinstance(profile_row.get("object_value"), dict):
            value = profile_row["object_value"]
            purpose = value.get("purpose") if isinstance(value.get("purpose"), str) else None
            purpose_source = value.get("purpose_source")
            source_path = (
                purpose_source.get("path")
                if isinstance(purpose_source, dict) and isinstance(purpose_source.get("path"), str)
                else None
            )
            confidence = _number(profile_row.get("confidence"), 0.5)
            citation = Citation(
                fact_id=profile_row["id"],
                label=(f"Repository profile · {source_path}" if source_path else "Repository profile evidence"),
                href=f"/api/v1/facts/{profile_row['id']}/evidence",
            )
            profile = RepositoryProfile(
                purpose=purpose,
                purpose_source=source_path,
                descriptions=_string_list(value.get("descriptions")),
                languages=_string_list(value.get("languages")),
                components=_string_list(value.get("components")),
                key_files=_string_list(value.get("key_files")),
                operational_signals=_string_list(value.get("operational_signals")),
                limitations=_string_list(value.get("limitations")),
                source_revision=profile_row["source_revision"],
                confidence=confidence,
                confidence_label=_confidence_label(confidence),
                citations=[citation],
            )
            if purpose:
                repository_summary = repository_summary.model_copy(update={"summary": purpose})
        related = await self.database.fetch_all(
            """
            SELECT entity.*,relationship.relationship_type,
                   coalesce(entity.last_seen_at,entity.updated_at,entity.created_at) observed_at
            FROM current_relationship relationship
            JOIN entity ON entity.id=CASE
              WHEN relationship.source_entity_id=%s THEN relationship.target_entity_id
              ELSE relationship.source_entity_id END
            WHERE relationship.source_entity_id=%s OR relationship.target_entity_id=%s
            ORDER BY entity.namespace,entity.entity_type,entity.name,entity.id
            """,
            (repository_id, repository_id, repository_id),
            tenant_id=tenant_id,
        )
        applications = [
            _entity(row) for row in related
            if row["namespace"] == "ENTERPRISE" and row["entity_type"] == "Application"
            and row["relationship_type"] in {"IMPLEMENTED_BY", "IMPLEMENTS", "CONTAINS"}
        ]
        technologies = [
            _entity(row) for row in related
            if row["namespace"] in {"TECHNOLOGY", "OSS"}
            and row["relationship_type"] in {"DEPENDS_ON", "USES", "RUNS_ON", "BUILT_ON", "HAS_VERSION"}
        ]
        deployments = [
            _entity(row) for row in related
            if row["namespace"] == "DEPLOYMENT"
            and row["relationship_type"] in {"DEPLOYED_AS", "RUNS_ON", "USES", "LOCATED_IN"}
        ]
        observed_at = profile_row.get("observed_at") if profile_row else repository.get("observed_at")
        source_key = profile_row.get("source_key") if profile_row else None
        return RepositoryDetail(
            repository=repository_summary,
            profile=profile,
            applications=_dedupe_summaries(applications),
            technologies=_dedupe_summaries(technologies),
            deployments=_dedupe_summaries(deployments),
            freshness=_freshness(observed_at, source_key),
            graph_intelligence=await self.entity_graph_metrics(
                repository_id,tenant_id=tenant_id,entity_row=repository,
            ),
        )

    async def technology_estate_hierarchy(
        self,
        *,
        tenant_id: UUID | None,
    ) -> TechnologyEstateHierarchy:
        if tenant_id is None:
            return TechnologyEstateHierarchy(as_of=datetime.now(UTC), nodes=[])

        max_depth = 6
        max_nodes = 1000
        membership_rows = await self.database.fetch_all(
            """
            SELECT repository.id repository_id,
                   dependency.predicate relationship_type,
                   dependency.id fact_assertion_id,
                   dependency.confidence,
                   dependency.properties dependency_properties,
                   technology.*
            FROM entity repository
            JOIN fact_assertion dependency
              ON dependency.subject_entity_id=repository.id
             AND dependency.system_to IS NULL
             AND dependency.predicate IN ('DEPENDS_ON','USES','RUNS_ON','BUILT_ON')
            JOIN entity technology ON technology.id=dependency.object_entity_id
            WHERE repository.tenant_id=%s
              AND repository.namespace='ENTERPRISE'
              AND repository.entity_type='Repository'
              AND technology.namespace IN ('TECHNOLOGY','OSS')
              AND technology.entity_type<>'Capability'
            ORDER BY technology.name,technology.id,
                     dependency.confidence DESC,dependency.id
            """,
            (tenant_id,),
            tenant_id=tenant_id,
        )
        if not membership_rows:
            return TechnologyEstateHierarchy(as_of=datetime.now(UTC), nodes=[])

        technologies_by_id: dict[UUID, dict[str, Any]] = {}
        evidence_by_id: dict[UUID, dict[str, Any]] = {}
        root_evidence: dict[UUID, dict[str, Any]] = {}
        for row in membership_rows:
            technology_id = UUID(str(row["id"]))
            technologies_by_id[technology_id] = row
            existing = evidence_by_id.get(technology_id)
            if existing is None or _number(row.get("confidence")) > _number(existing.get("confidence")):
                evidence_by_id[technology_id] = row
            properties = (
                row.get("dependency_properties")
                if isinstance(row.get("dependency_properties"), dict) else {}
            )
            direct_marker = properties.get("direct")
            is_direct = (
                str(row["relationship_type"]) != "DEPENDS_ON"
                or direct_marker is None
                or direct_marker is True
                or (isinstance(direct_marker, str) and direct_marker.lower() == "true")
            )
            existing_root = root_evidence.get(technology_id)
            if is_direct and (
                existing_root is None
                or _number(row.get("confidence")) > _number(existing_root.get("confidence"))
            ):
                root_evidence[technology_id] = row

        technology_ids = list(technologies_by_id)
        edge_rows = await self.database.fetch_all(
            """
            SELECT DISTINCT ON (dependency.subject_entity_id,dependency.object_entity_id)
                   dependency.subject_entity_id source_id,
                   dependency.object_entity_id target_id,
                   dependency.predicate relationship_type,
                   dependency.id fact_assertion_id,
                   dependency.confidence,
                   dependency.properties dependency_properties
            FROM fact_assertion dependency
            WHERE dependency.predicate='DEPENDS_ON'
              AND dependency.system_to IS NULL
              AND dependency.subject_entity_id=ANY(%s::uuid[])
              AND dependency.object_entity_id=ANY(%s::uuid[])
            ORDER BY dependency.subject_entity_id,dependency.object_entity_id,
                     dependency.confidence DESC,dependency.id
            """,
            (technology_ids, technology_ids),
            tenant_id=tenant_id,
        )
        application_rows = await self.database.fetch_all(
            """
            WITH application_repositories AS (
              SELECT application.id application_id,repository.id repository_id
              FROM fact_assertion link
              JOIN entity application ON application.id=link.subject_entity_id
              JOIN entity repository ON repository.id=link.object_entity_id
              WHERE link.system_to IS NULL
                AND link.predicate IN ('IMPLEMENTED_BY','IMPLEMENTS','CONTAINS')
                AND application.tenant_id=%s
                AND application.namespace='ENTERPRISE'
                AND application.entity_type='Application'
                AND repository.entity_type='Repository'
              UNION
              SELECT application.id application_id,repository.id repository_id
              FROM fact_assertion link
              JOIN entity repository ON repository.id=link.subject_entity_id
              JOIN entity application ON application.id=link.object_entity_id
              WHERE link.system_to IS NULL
                AND link.predicate IN ('IMPLEMENTED_BY','IMPLEMENTS','CONTAINS')
                AND application.tenant_id=%s
                AND application.namespace='ENTERPRISE'
                AND application.entity_type='Application'
                AND repository.entity_type='Repository'
            )
            SELECT DISTINCT ON (dependency.object_entity_id,application.id)
                   dependency.object_entity_id technology_id,application.*
            FROM application_repositories linked
            JOIN fact_assertion dependency
              ON dependency.subject_entity_id=linked.repository_id
             AND dependency.system_to IS NULL
             AND dependency.predicate IN ('DEPENDS_ON','USES','RUNS_ON','BUILT_ON')
             AND dependency.object_entity_id=ANY(%s::uuid[])
            JOIN entity application ON application.id=linked.application_id
            ORDER BY dependency.object_entity_id,application.id,application.name
            """,
            (tenant_id, tenant_id, technology_ids),
            tenant_id=tenant_id,
        )

        adjacency: dict[UUID, list[dict[str, Any]]] = defaultdict(list)
        for row in edge_rows:
            adjacency[UUID(str(row["source_id"]))].append(row)
        for edges in adjacency.values():
            edges.sort(key=lambda row: (
                str(technologies_by_id[UUID(str(row["target_id"]))]["name"]).lower(),
                str(row["target_id"]),
            ))

        applications_by_technology: dict[UUID, list[EntitySummary]] = defaultdict(list)
        for row in application_rows:
            applications_by_technology[UUID(str(row["technology_id"]))].append(_entity(row))

        catalog_rows = await self._technology_classification_catalog(tenant_id)
        metadata_rows = await self._technology_catalog_metadata(technology_ids, tenant_id)
        catalog_profiles = _technology_catalog_profiles(
            list(technologies_by_id.values()), catalog_rows, metadata_rows,
        )

        selected: dict[UUID, tuple[UUID | None, int, bool, dict[str, Any]]] = {}
        queue: deque[UUID] = deque()
        truncated = False
        for technology_id, evidence in sorted(
            root_evidence.items(),
            key=lambda item: (
                str(technologies_by_id[item[0]]["name"]).lower(),
                str(item[0]),
            ),
        ):
            if len(selected) >= max_nodes:
                truncated = True
                break
            selected[technology_id] = (None, 1, True, evidence)
            queue.append(technology_id)

        while queue and not truncated:
            parent_id = queue.popleft()
            parent_depth = selected[parent_id][1]
            if parent_depth >= max_depth:
                continue
            for edge in adjacency.get(parent_id, []):
                child_id = UUID(str(edge["target_id"]))
                if child_id in selected:
                    continue
                if len(selected) >= max_nodes:
                    truncated = True
                    break
                selected[child_id] = (parent_id, parent_depth + 1, False, edge)
                queue.append(child_id)

        if not truncated:
            for technology_id, technology in sorted(
                technologies_by_id.items(),
                key=lambda item: (str(item[1]["name"]).lower(), str(item[0])),
            ):
                if technology_id in selected:
                    continue
                if len(selected) >= max_nodes:
                    truncated = True
                    break
                selected[technology_id] = (None, 1, False, evidence_by_id[technology_id])

        nodes: list[TechnologyEstateHierarchyNode] = []
        for technology_id, (parent_id, depth, direct, evidence) in selected.items():
            fact_id = UUID(str(evidence["fact_assertion_id"]))
            confidence = _number(evidence.get("confidence"), 0.0)
            nodes.append(TechnologyEstateHierarchyNode(
                technology=_entity(technologies_by_id[technology_id]),
                parent_technology_id=parent_id,
                depth=depth,
                direct=direct,
                relationship=str(evidence["relationship_type"]),
                confidence=confidence,
                confidence_label=_confidence_label(confidence),
                dependent_applications=applications_by_technology.get(technology_id, []),
                catalog_profile=catalog_profiles.get(technology_id),
                citations=[Citation(
                    fact_id=fact_id,
                    label=(
                        "Declared dependency evidence"
                        if direct else (
                            "Resolved dependency evidence"
                            if parent_id is not None else "Observed dependency evidence"
                        )
                    ),
                    href=f"/api/v1/facts/{fact_id}/evidence",
                )],
            ))
        return TechnologyEstateHierarchy(
            as_of=datetime.now(UTC),
            nodes=nodes,
            truncated=truncated,
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
        catalog_rows = await self._technology_classification_catalog(tenant_id)
        metadata_rows = await self._technology_catalog_metadata([technology_id], tenant_id)
        catalog_profile = _technology_catalog_profiles(
            [technology], catalog_rows, metadata_rows,
        ).get(technology_id)
        registry_rows = await self.database.fetch_all(
            """
            SELECT r.registry_key,min(r.origin_uri) origin_uri,
                   CASE min(CASE r.visibility
                     WHEN 'PRIVATE' THEN 0 WHEN 'PUBLIC' THEN 1 ELSE 2 END)
                     WHEN 0 THEN 'PRIVATE' WHEN 1 THEN 'PUBLIC' ELSE 'UNKNOWN'
                   END visibility,
                   bool_or(r.tenant_id IS NOT NULL) tenant_scoped,
                   max(coalesce(pri.last_seen_at,e.last_seen_at,e.updated_at)) observed_at,
                   min(ss.source_key) source_key
            FROM package_registry_identity pri
            JOIN package_registry r ON r.id=pri.package_registry_id
            JOIN source_system ss ON ss.id=r.source_system_id
            JOIN entity e ON e.id=pri.entity_id
            WHERE pri.entity_id = ANY(%s::uuid[])
            GROUP BY r.registry_key,regexp_replace(lower(trim(r.origin_uri)),'/+$','')
            ORDER BY r.registry_key,min(r.origin_uri)
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
            catalog_profile=catalog_profile,
            registry_sources=registry_sources,
            alternatives=[_entity(row) for row in alternatives],
            migration_patterns=[_entity(row) for row in migrations],
            assessments=await self._assessments(technology_id, tenant_id),
            recommendations=await self._recommendations(technology_id, tenant_id),
            freshness=_freshness(technology.get("observed_at")),
            graph_intelligence=await self.entity_graph_metrics(
                technology_id,tenant_id=tenant_id,entity_row=technology,
            ),
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
            cursor_score = float(cursor_data["score"]) if cursor_data else None
            cursor_id = UUID(cursor_data["id"]) if cursor_data else None
        except (KeyError, TypeError, ValueError) as error:
            raise APIError(400, "INVALID_CURSOR", "The pagination cursor is invalid.") from error
        scored = await self._governed_portfolio_scores(tenant_id)
        if cursor_score is not None and cursor_id is not None:
            scored = [
                item for item in scored
                if item[1].score < cursor_score
                or (item[1].score == cursor_score and item[0]["id"] > cursor_id)
            ]
        has_next = len(scored) > limit
        page = scored[:limit]
        opportunities: list[RankedItem] = []
        for row, portfolio_score in page:
            confidence = _number(row["recommendation_confidence"])
            citations = [
                Citation(
                    fact_id=fact_id,
                    label=f"Evidence for {row['title']}",
                    href=f"/api/v1/facts/{fact_id}/evidence",
                )
                for fact_id in row["supporting_fact_ids"]
            ]
            opportunities.append(
                RankedItem(
                    id=row["id"],
                    kind="ModernizationOpportunity",
                    name=row["title"],
                    domain="INTELLIGENCE",
                    priority=Score(
                        value=round(portfolio_score.score * 100, 2),
                        confidence=confidence,
                        confidence_label=_confidence_label(confidence),
                        method_version=portfolio_score.policy_version,
                    ),
                    summary=f"{row['repository_name']} · {row['rationale']}",
                    freshness=_freshness(row.get("updated_at") or row.get("created_at")),
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
                        score=page[-1][1].score,
                        id=str(page[-1][0]["id"]),
                    )
                    if has_next and page else None
                ),
            ),
        )

    async def deterministic_insights(
        self,
        *,
        tenant_id: UUID | None,
        scope_entity_id: UUID | None,
        rule_key: str | None,
        limit: int,
    ) -> DeterministicInsightList:
        return await list_deterministic_insights(
            self.database,
            tenant_id=tenant_id,
            scope_entity_id=scope_entity_id,
            rule_key=rule_key,
            limit=limit,
        )

    async def capability_footprints(
        self, *, tenant_id: UUID | None,
    ) -> CapabilityFootprintList:
        rows = await self.database.fetch_all(
            """
            SELECT footprint.*,entity.namespace,entity.entity_type,entity.canonical_key,
                   entity.name,entity.properties
            FROM capability_footprint footprint
            JOIN entity ON entity.id=footprint.capability_entity_id
            ORDER BY footprint.technology_entropy DESC,footprint.repository_count DESC,
                     entity.name,entity.id
            """,
            tenant_id=tenant_id,
        )
        return CapabilityFootprintList(
            as_of=datetime.now(UTC),
            footprints=[CapabilityFootprintModel(
                capability=_entity(row),
                application_count=row["application_count"],
                repository_count=row["repository_count"],
                technology_count=row["technology_count"],
                technology_counts={
                    str(key): int(value) for key, value in row["technology_counts"].items()
                },
                technology_entropy=_number(row["technology_entropy"]),
                reuse_signal=_number(row["reuse_signal"]),
            ) for row in rows],
        )

    async def modernization_scenario(
        self, request: ModernizationScenarioRequest, *, tenant_id: UUID | None,
    ) -> ModernizationScenarioResult:
        scored = [
            item for item in await self._governed_portfolio_scores(tenant_id)
            if item[0]["id"] not in set(request.excluded_recommendation_ids)
        ]
        selected = optimize_portfolio(
            (item[1] for item in scored), budget_points=request.budget_points,
        )
        selected_ids = {UUID(item.candidate.id) for item in selected}
        items = [ModernizationScenarioItem(
            recommendation_id=row["id"],
            repository=EntitySummary(
                id=row["repository_entity_id"], kind="Repository",
                name=row["repository_name"], canonical_key=row["repository_key"],
            ),
            title=row["title"], action=row["action"],
            score=round(value.score * 100, 2),
            score_components={key: round(component, 6) for key, component in value.components.items()},
            effort_points=value.candidate.effort_points,
            selected=row["id"] in selected_ids,
            policy_version=value.policy_version,
        ) for row, value in scored]
        return ModernizationScenarioResult(
            as_of=datetime.now(UTC), budget_points=request.budget_points,
            used_points=sum(item.effort_points for item in items if item.selected),
            total_score=round(sum(item.score for item in items if item.selected), 2),
            items=items,
        )

    async def _governed_portfolio_scores(self, tenant_id: UUID | None) -> list[tuple[dict[str, Any], Any]]:
        policy_row = await self.database.fetch_one(
            """
            SELECT * FROM modernization_portfolio_policy
            WHERE status='ACTIVE' ORDER BY updated_at DESC,id LIMIT 1
            """,
            tenant_id=tenant_id,
        )
        weights = dict(policy_row["weights"]) if policy_row else {}
        policy = PortfolioScoringPolicy(
            business_weight=_number(weights.get("business"), 0.25),
            viability_gap_weight=_number(weights.get("viability_gap"), 0.2),
            entropy_weight=_number(weights.get("entropy"), 0.2),
            reuse_weight=_number(weights.get("reuse"), 0.2),
            confidence_weight=_number(weights.get("confidence"), 0.15),
            effort_penalty_weight=_number(
                policy_row.get("effort_penalty_weight") if policy_row else None, 0.2,
            ),
            version=(
                f"{policy_row['policy_key']}/{policy_row['version']}"
                if policy_row else "modernization-portfolio/v1-unconfigured"
            ),
        )
        rows = await self.database.fetch_all(
            """
            SELECT recommendation.id,recommendation.title,recommendation.rationale,
                   recommendation.action,recommendation.confidence recommendation_confidence,
                   recommendation.review_state recommendation_review_state,
                   recommendation.supporting_fact_ids,recommendation.created_at,
                   recommendation.updated_at,candidate.confidence candidate_confidence,
                   candidate.capability_definition_id,candidate.candidate_kind,
                   candidate.review_state candidate_review_state,
                   definition.name capability_name,selected.name standard_target,
                   recommendation.affected_call_sites,recommendation.affected_files,
                   repository.id repository_entity_id,
                   repository.name repository_name,repository.canonical_key repository_key,
                   coalesce(impact.effort_points,
                     CASE recommendation.estimated_effort WHEN 'LOW' THEN 3 WHEN 'MEDIUM' THEN 8
                          WHEN 'HIGH' THEN 13 ELSE 21 END) effort_points,
                   coalesce(selected.score,0) selected_option_score,
                   coalesce(footprint.application_count,0) application_count,
                   coalesce(footprint.repository_count,0) repository_count,
                   coalesce(footprint.technology_counts,'{}'::jsonb) technology_counts
            FROM modernization_recommendation recommendation
            JOIN modernization_candidate candidate
              ON candidate.id=recommendation.modernization_candidate_id
             AND candidate.stale_at IS NULL AND candidate.review_state<>'REJECTED'
            JOIN entity repository ON repository.id=recommendation.repository_entity_id
            LEFT JOIN modernization_impact impact
              ON impact.modernization_candidate_id=candidate.id
            LEFT JOIN modernization_option selected ON selected.id=recommendation.selected_option_id
            LEFT JOIN capability_definition definition
              ON definition.id=candidate.capability_definition_id
            LEFT JOIN entity capability
              ON capability.tenant_id=recommendation.tenant_id
             AND capability.namespace='BUSINESS' AND capability.entity_type='BusinessCapability'
             AND capability.canonical_key='capability:'||definition.capability_key
            LEFT JOIN capability_footprint footprint
              ON footprint.capability_entity_id=capability.id
            WHERE recommendation.stale_at IS NULL
              AND recommendation.review_state NOT IN ('REJECTED','DISMISSED')
            ORDER BY recommendation.created_at DESC,recommendation.id
            LIMIT 5000
            """,
            tenant_id=tenant_id,
        )
        scored = []
        for row in rows:
            footprint = GovernedCapabilityFootprint(
                application_count=row["application_count"],
                repository_count=row["repository_count"],
                technology_counts={
                    str(key): int(value) for key, value in row["technology_counts"].items()
                },
            )
            value = score_portfolio_candidate(PortfolioCandidate(
                id=str(row["id"]),
                business_importance=min(1.0, row["application_count"] / 10.0),
                viability_gap=1.0 - _number(row["selected_option_score"]),
                confidence=min(
                    _number(row["candidate_confidence"]),
                    _number(row["recommendation_confidence"]),
                ),
                effort_points=row["effort_points"], footprint=footprint,
                mutually_exclusive_group=(
                    str(row["capability_definition_id"])
                    if row["capability_definition_id"] else None
                ),
            ), policy)
            scored.append((row, value))
        return sorted(scored, key=lambda item: (-item[1].score, item[0]["id"]))

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
        if self.graph_read_mode in {"auto", "neo4j"}:
            try:
                projection = await self.neo4j_graph.projection_state(tenant_id)
                if not projection.current:
                    if projection.configured:
                        self.graph_read_metrics.lag_fallbacks += 1
                        logger.info(
                            "graph read using SQL because Neo4j projection is unavailable or behind",
                            extra={"pending_events": projection.pending_events},
                        )
                else:
                    async with asyncio.timeout(self.graph_age_timeout_seconds):
                        graph = await self._try_neo4j_graph_neighborhood(
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
                        self.graph_read_metrics.neo4j_reads += 1
                        return graph
            except APIError:
                raise
            except TimeoutError:
                self.graph_read_metrics.timeout_fallbacks += 1
                logger.warning(
                    "graph read falling back to SQL because Neo4j exceeded its time budget",
                    extra={"timeout_seconds": self.graph_age_timeout_seconds},
                )
            except AgeParityError as error:
                self.graph_read_metrics.parity_fallbacks += 1
                logger.warning(
                    "graph read falling back to SQL because Neo4j differs from current SQL state",
                    extra={"reason": str(error)},
                )
            except Exception as error:
                self.graph_read_metrics.unavailable_fallbacks += 1
                logger.warning(
                    "graph read falling back to SQL because Neo4j is unavailable",
                    extra={"error_type": type(error).__name__},
                )
        elif self.graph_read_mode == "age":
            try:
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
            except Exception as error:
                self.graph_read_metrics.unavailable_fallbacks += 1
                logger.warning(
                    "legacy AGE graph read failed; using SQL",
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

    async def _try_neo4j_graph_neighborhood(
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
        topology = await self.neo4j_graph.neighborhood(
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
        return await self._build_projected_graph_neighborhood(
            center_id,
            topology,
            source="Neo4j",
            tenant_id=tenant_id,
            depth=depth,
            real_node_limit=real_node_limit,
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
        return await self._build_projected_graph_neighborhood(
            center_id,
            topology,
            source="AGE",
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
        neighborhood = GraphNeighborhood(
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
        return await self._with_graph_structure(neighborhood,tenant_id=tenant_id)

    async def _build_projected_graph_neighborhood(
        self,
        center_id: UUID,
        topology: AgeTopology | Neo4jTopology,
        *,
        source: str,
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
            raise AgeParityError(f"{len(missing_nodes)} {source} nodes are absent from SQL")

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
                f"{source} returned {len(topology.fact_ids)} facts but SQL hydrated {len(sql_fact_ids)}"
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
        neighborhood = GraphNeighborhood(
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
        return await self._with_graph_structure(neighborhood,tenant_id=tenant_id)

    async def _with_graph_structure(
        self,neighborhood: GraphNeighborhood,*,tenant_id: UUID | None,
    ) -> GraphNeighborhood:
        snapshot_rows = await self._active_graph_snapshots(
            tenant_id,policy_key="runtime-dependency",
        )
        if not snapshot_rows or tenant_id is None:
            return neighborhood
        run_id = snapshot_rows[0]["analysis_run_id"]
        real_node_ids = [node.id for node in neighborhood.nodes if not node.aggregate]
        rows = await self.database.fetch_all(
            """
            SELECT entity.id,risk.systemic_risk,community.community_key
            FROM entity
            LEFT JOIN graph_entity_risk risk
              ON risk.run_id=%s AND risk.tenant_id=%s AND risk.entity_id=entity.id
            LEFT JOIN graph_community_membership community
              ON community.run_id=%s AND community.tenant_id=%s
             AND community.entity_id=entity.id AND community.algorithm_key='wcc'
            WHERE entity.id=ANY(%s::uuid[])
            ORDER BY entity.id
            """,
            (run_id,tenant_id,run_id,tenant_id,real_node_ids),tenant_id=tenant_id,
        )
        structure = {row["id"]:row for row in rows}
        fact_ids = [
            edge.citation_fact_ids[0] for edge in neighborhood.edges
            if len(edge.citation_fact_ids)==1
        ]
        bridge_rows = await self.database.fetch_all(
            """
            SELECT fact_assertion_id FROM graph_edge_metric
            WHERE run_id=%s AND tenant_id=%s AND metric_key='spof.bridge'
              AND fact_assertion_id=ANY(%s::uuid[])
            """,
            (run_id,tenant_id,fact_ids),tenant_id=tenant_id,
        ) if fact_ids else []
        bridges = {row["fact_assertion_id"] for row in bridge_rows}
        real_ids = set(real_node_ids)
        return neighborhood.model_copy(update={
            "nodes":[node if node.aggregate else node.model_copy(update={
                "systemic_risk":(
                    _number(structure[node.id]["systemic_risk"])
                    if structure.get(node.id,{}).get("systemic_risk") is not None else None
                ),
                "community_key":structure.get(node.id,{}).get("community_key"),
                "structural_status":(
                    "STRUCTURALLY_CRITICAL"
                    if _number(structure.get(node.id,{}).get("systemic_risk"))>=0.8
                    else "ELEVATED"
                    if _number(structure.get(node.id,{}).get("systemic_risk"))>=0.6
                    else "TYPICAL"
                    if structure.get(node.id,{}).get("systemic_risk") is not None else None
                ),
            }) for node in neighborhood.nodes],
            "edges":[edge.model_copy(update={
                "is_bridge":edge.citation_fact_ids[0] in bridges,
            }) if (
                len(edge.citation_fact_ids)==1
                and edge.source in real_ids and edge.target in real_ids
            ) else edge for edge in neighborhood.edges],
        })

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

    async def enterprise_insight_reports(
        self, *, tenant_id: UUID | None,
    ) -> EnterpriseInsightReportList:
        """Materialize every executive report without invoking an AI provider."""
        phase2_ready, posture_ready = await asyncio.gather(
            self._phase2_report_readiness(tenant_id=tenant_id),
            posture_report_readiness(self.database, tenant_id=tenant_id),
        )
        phase2_ready = {**phase2_ready, **posture_ready}
        results = await asyncio.gather(*(
            self.ask(AskRequest(question=definition["question"]), tenant_id=tenant_id)
            for definition in _ENTERPRISE_INSIGHT_REPORTS
        ))
        reports: list[EnterpriseInsightReport] = []
        for definition, result in zip(_ENTERPRISE_INSIGHT_REPORTS, results, strict=True):
            rows = result.rows or []
            mapped_rows_required = definition.get("requires_mapped_rows") == "true"
            has_mapped_row = any(
                row.get("business_capability") not in (None, "UNMAPPED") for row in rows
            )
            empty_needs_data = (
                not rows
                and definition.get("empty_requires_data") == "true"
                and not phase2_ready.get(definition["key"], False)
            )
            waiting = result.result_kind == "UNSUPPORTED" or empty_needs_data or (
                mapped_rows_required and not has_mapped_row
            )
            status = (
                "WAITING_FOR_DATA" if waiting
                else definition["populated_status"] if rows
                else "HEALTHY"
            )
            posture = (
                assurance_report_presentation(rows)
                if not waiting and definition["key"] == ASSURANCE_COVERAGE else None
            )
            if posture is not None:
                status = posture[1]

            metric_field = definition["metric_field"]
            if waiting:
                metric_value = "—"
            elif posture is not None:
                metric_value = posture[0]
            elif metric_field == "row_count":
                metric_value = str(len(rows))
            else:
                values = [
                    value for row in rows
                    if isinstance((value := row.get(metric_field)), (int, float, Decimal))
                    and not isinstance(value, bool)
                ]
                metric = max((float(value) for value in values), default=0)
                metric_value = str(int(metric)) if metric.is_integer() else f"{metric:.2f}"

            confidence_values = [
                float(value) for row in rows
                if isinstance((value := row.get("confidence")), (int, float, Decimal))
                and not isinstance(value, bool) and 0 <= float(value) <= 1
            ]
            confidence = (
                round(sum(confidence_values) / len(confidence_values), 4)
                if confidence_values else None
            )
            reports.append(EnterpriseInsightReport(
                key=definition["key"], title=definition["title"],
                category=definition["category"], question=definition["question"],
                metric_value=metric_value, metric_label=definition["metric_label"],
                status=status, answerable=not waiting, confidence=confidence,
                evidence_count=len(result.citations), summary=result.text, response=result,
            ))

        return EnterpriseInsightReportList(
            method_version="enterprise-insights/v1", evaluated_at=datetime.now(UTC),
            answerable_reports=sum(report.answerable for report in reports),
            total_reports=len(reports), reports=reports,
        )

    async def _phase2_report_readiness(
        self, *, tenant_id: UUID | None,
    ) -> dict[str, bool]:
        """Distinguish a defensible zero from a result blocked by missing governance."""
        row = await self.database.fetch_one(
            """
            SELECT
              EXISTS(
                SELECT 1 FROM current_capability_application_relationship
              ) capability_mapped,
              EXISTS(
                SELECT 1 FROM current_capability_application_relationship
                WHERE criticality>=4
              ) tier1_mapped,
              EXISTS(
                SELECT 1 FROM modernization_internal_component
                WHERE tenant_id=%s AND review_state='APPROVED' AND status='APPROVED'
              ) internal_catalog_governed,
              EXISTS(
                SELECT 1
                FROM code_implementation_summary unit
                WHERE unit.tenant_id=%s AND NOT unit.vendored
                  AND unit.line_end-unit.line_start+1>=6
                GROUP BY unit.structural_fingerprint
                HAVING count(DISTINCT unit.repository_entity_id)>=2
              ) internal_clone_candidate,
              (
                EXISTS(
                  SELECT 1 FROM assessment lifecycle
                  JOIN fact_assertion relationship
                    ON relationship.object_entity_id=lifecycle.subject_entity_id
                   AND relationship.tenant_id=%s AND relationship.system_to IS NULL
                   AND relationship.predicate IN ('DEPENDS_ON','USES','HAS_VERSION')
                  WHERE lifecycle.status='CURRENT'
                    AND lower(lifecycle.dimension) IN ('supportability','runtime_support','package_support')
                ) OR (
                  EXISTS(
                    SELECT 1 FROM modernization_policy
                    WHERE tenant_id=%s AND status='ACTIVE' AND runtime_versions<>'{}'::jsonb
                  ) AND EXISTS(
                    SELECT 1 FROM fact_assertion runtime_fact
                    JOIN entity image ON image.id=runtime_fact.object_entity_id
                      AND image.entity_type='ContainerImage'
                    WHERE runtime_fact.tenant_id=%s AND runtime_fact.predicate='RUNS_ON'
                      AND runtime_fact.system_to IS NULL
                      AND (
                        lower(image.name) ~ '(^|/)node(js)?:'
                        OR lower(image.name) ~ '(^|/)python:'
                        OR lower(image.name) ~ '(^|/)dotnet:'
                        OR lower(image.name) LIKE '%%/dotnet/%%'
                      )
                  )
                )
              ) lifecycle_covered,
              coalesce((
                SELECT count(*)>0 AND bool_and(target.refresh_policy ? 'archived')
                FROM ingest_target target
                WHERE target.tenant_id=%s AND target.target_kind='REPOSITORY'
                  AND target.enabled
              ),false) archive_covered
            """,
            (tenant_id, tenant_id, tenant_id, tenant_id, tenant_id, tenant_id), tenant_id=tenant_id,
        ) or {}
        capability_mapped = bool(row.get("capability_mapped"))
        internal_catalog_governed = bool(row.get("internal_catalog_governed"))
        return {
            "reachable_vulnerabilities": bool(row.get("tier1_mapped")),
            "package_business_blast_radius": capability_mapped,
            "modernization_blockers": bool(row.get("lifecycle_covered")),
            "custom_to_internal_platform": internal_catalog_governed,
            "internal_library_standards": (
                internal_catalog_governed or bool(row.get("internal_clone_candidate"))
            ),
            "application_retirement_consolidation": (
                capability_mapped and bool(row.get("archive_covered"))
            ),
            # Standardization only needs analyzed candidates; a zero after analysis
            # is already defensible and the query normally returns scored rows.
            "standardization_initiatives": True,
        }

    async def ask(self, request: AskRequest, *, tenant_id: UUID | None) -> AskResponse:
        normalized = " ".join(request.question.lower().split())
        context_ids = request.context_entity_ids or []

        if "graph blast radius" in normalized:
            return await self._ask_graph_snapshot_query(
                "blast_radius",context_ids=context_ids,tenant_id=tenant_id,
            )
        if "graph structural criticality" in normalized:
            return await self._ask_graph_snapshot_query(
                "structural_criticality",context_ids=context_ids,tenant_id=tenant_id,
            )
        if "graph community membership" in normalized:
            return await self._ask_graph_snapshot_query(
                "community_membership",context_ids=context_ids,tenant_id=tenant_id,
            )
        if "graph circular dependencies" in normalized:
            return await self._ask_graph_snapshot_query(
                "circular_dependencies",context_ids=context_ids,tenant_id=tenant_id,
            )

        if "systemic dependency risk" in normalized or (
            "top" in normalized and "dependenc" in normalized and "enterprise risk" in normalized
        ):
            return await self._ask_systemic_dependency_risk(tenant_id=tenant_id)

        if "reachable" in normalized and "vulnerabil" in normalized and any(
            phrase in normalized for phrase in ("production", "tier-1", "tier 1")
        ):
            return await self._ask_reachable_vulnerabilities(tenant_id=tenant_id)

        if "independently implemented same capability" in normalized or (
            "same capability" in normalized and any(word in normalized for word in ("implement", "team", "independent"))
        ):
            return await self._ask_duplicate_capability_implementations(tenant_id=tenant_id)

        if "modernization blocker" in normalized or (
            "unsupported" in normalized and "block" in normalized
        ):
            return await self._ask_modernization_blockers(tenant_id=tenant_id)

        if "largest governed business-capability blast radius" in normalized:
            return await self._ask_top_package_business_blast_radius(tenant_id=tenant_id)

        if "package business capability blast radius" in normalized or (
            "package" in normalized and any(
                phrase in normalized for phrase in ("disappeared", "business capabilities", "blast radius")
            )
        ):
            return await self._ask_package_business_blast_radius(
                normalized, context_ids=context_ids, tenant_id=tenant_id,
            )

        if "technology diversity" in normalized and any(
            word in normalized for word in ("package", "category", "unnecessary")
        ):
            return await self._ask_technology_diversity(tenant_id=tenant_id)

        if "internal librar" in normalized and any(
            word in normalized for word in ("standard", "enterprise", "promote")
        ):
            return await self._ask_internal_library_standards(tenant_id=tenant_id)

        if "custom implementation" in normalized and "internal platform" in normalized:
            return await self._ask_custom_to_internal_platform(tenant_id=tenant_id)

        if ("retirement" in normalized or "retire" in normalized) and "consolidat" in normalized:
            return await self._ask_application_retirement_consolidation(tenant_id=tenant_id)

        if "standardization initiative" in normalized and any(
            word in normalized for word in ("payoff", "enterprise", "largest", "top 10")
        ):
            return await self._ask_standardization_initiatives(tenant_id=tenant_id)

        # Estate posture and outcome reports are matched after the older enterprise
        # templates so an existing question can never be re-routed by a new phrase.
        posture_key = match_posture_question(normalized)
        if posture_key is not None:
            return await answer_posture_report(
                self.database, posture_key, tenant_id=tenant_id,
            )

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

    async def _ask_graph_snapshot_query(
        self,kind: str,*,context_ids: list[UUID],tenant_id: UUID | None,
    ) -> AskResponse:
        if kind=="circular_dependencies":
            motifs = await self.graph_motifs(
                tenant_id=tenant_id,motif_key="CIRCULAR_DEPENDENCY",limit=50,
            )
            if motifs.snapshot is not None:
                selected = [
                    motif for motif in motifs.motifs
                    if not context_ids or any(member.id in context_ids for member in motif.members)
                ]
                citations = await self._ask_citations(
                    [fact_id for motif in selected for fact_id in motif.supporting_fact_ids],
                    tenant_id=tenant_id,
                )
                return AskResponse(
                    text=f"I found {len(selected)} circular dependency motifs in the active snapshot.",
                    citations=citations,result_kind="TABLE",rows=[{
                        "members":[member.name for member in motif.members],
                        "minimum_confidence":motif.minimum_confidence,
                        "analysis_run_id":str(motifs.snapshot.analysis_run_id),
                    } for motif in selected],
                )
        elif not context_ids:
            return AskResponse(
                text="This structural question needs a resolved or explicitly selected entity.",
                citations=[],result_kind="UNSUPPORTED",
            )
        elif kind=="blast_radius":
            result = await self.graph_blast_radius(context_ids[0],tenant_id=tenant_id)
            if result.snapshot is not None:
                citations = await self._ask_citations(
                    [fact_id for path in result.impacts for fact_id in path.supporting_fact_ids],
                    tenant_id=tenant_id,
                )
                return AskResponse(
                    text=f"{result.entity.name} can affect {result.affected_entity_count} graph entities across at most {result.maximum_depth} hops.",
                    citations=citations,result_kind="GRAPH",rows=[{
                        "entity":result.entity.name,"affected_entities":result.affected_entity_count,
                        "maximum_depth":result.maximum_depth,
                        "analysis_run_id":str(result.snapshot.analysis_run_id),
                    }],
                )
        elif kind=="structural_criticality":
            risks = await self.graph_risks(tenant_id=tenant_id,limit=100)
            if risks.snapshot is not None:
                selected = [item for item in risks.risks if item.entity.id in context_ids]
                return AskResponse(
                    text=f"I found structural risk scores for {len(selected)} selected entities.",
                    citations=[],result_kind="TABLE",rows=[{
                        "entity":item.entity.name,"systemic_risk":item.systemic_risk,
                        "renormalized_families":item.renormalized_families,
                        "analysis_run_id":str(risks.snapshot.analysis_run_id),
                    } for item in selected],
                )
        elif kind=="community_membership":
            result = await self.entity_graph_metrics(context_ids[0],tenant_id=tenant_id)
            if result.snapshots:
                return AskResponse(
                    text=f"{result.entity.name} belongs to {len(result.community_keys)} active graph communities.",
                    citations=[],result_kind="TABLE",rows=[{
                        "entity":result.entity.name,"community_keys":result.community_keys,
                        "structural_status":result.primary_status,
                    }],
                )

        # Snapshot coverage is incomplete: state the authoritative SQL fallback explicitly.
        rows = await self.database.fetch_all(
            """
            SELECT source.name source,target.name target,relationship.relationship_type,
                   relationship.fact_assertion_id fact_id
            FROM current_relationship relationship
            JOIN entity source ON source.id=relationship.source_entity_id
            JOIN entity target ON target.id=relationship.target_entity_id
            WHERE (%s::uuid[]='{}'::uuid[] OR relationship.source_entity_id=ANY(%s::uuid[])
                   OR relationship.target_entity_id=ANY(%s::uuid[]))
            ORDER BY source.name,target.name,relationship.fact_assertion_id LIMIT 100
            """,
            (context_ids,context_ids,context_ids),tenant_id=tenant_id,
        )
        citations = await self._ask_citations(
            [row["fact_id"] for row in rows],tenant_id=tenant_id,
        )
        return AskResponse(
            text=(
                "No complete active graph snapshot covered the question. "
                "These rows use the current tenant-scoped SQL relationship view and do not claim structural metrics."
            ),citations=citations,result_kind="TABLE",rows=[{
                "source":row["source"],"target":row["target"],
                "predicate":row["relationship_type"],"limitation":"SQL_FALLBACK_NO_STRUCTURAL_SNAPSHOT",
            } for row in rows],
        )

    async def _ask_systemic_dependency_risk(self, *, tenant_id: UUID | None) -> AskResponse:
        risk_list = await self.graph_risks(tenant_id=tenant_id,limit=20)
        fact_ids = [
            fact_id
            for item in risk_list.risks
            for contribution in item.component_contributions.values()
            for raw_id in contribution.get("fact_ids",[])
            if (fact_id := UUID(str(raw_id)))
        ]
        citations = await self._ask_citations(fact_ids,tenant_id=tenant_id)
        result_rows = [{
            "dependency":item.entity.name,
            "risk_score":round(item.systemic_risk*100,2),
            "impacted_applications":len(item.impacted_applications),
            "signal_families":sorted(item.component_contributions),
            "renormalized_families":item.renormalized_families,
            "method_version":item.method_version,
            "policy_hash":risk_list.snapshot.policy_hash if risk_list.snapshot else None,
        } for item in risk_list.risks]
        return AskResponse(
            text=(
                f"I ranked {len(result_rows)} dependencies with the governed graph systemic-risk composite."
                if result_rows else
                "I found no dependencies in an active graph-risk snapshot."
            ),citations=citations,result_kind="TABLE",rows=result_rows,
        )

    async def _ask_reachable_vulnerabilities(self, *, tenant_id: UUID | None) -> AskResponse:
        rows = await self.database.fetch_all(
            """
            WITH production_repository AS (
              SELECT deployment.subject_entity_id repository_id
              FROM fact_assertion deployment
              WHERE deployment.tenant_id=%s AND deployment.predicate='DEPLOYED_AS'
                AND deployment.system_to IS NULL
                AND coalesce(deployment.properties->>'source_kind','')
                    IN ('KUBERNETES','COMPOSE','DOCKERFILE')
              GROUP BY deployment.subject_entity_id
            ), critical_application AS (
              SELECT mapping.application_entity_id,max(mapping.criticality)::integer criticality,
                     string_agg(DISTINCT capability.name,', ' ORDER BY capability.name) capabilities
              FROM current_capability_application_relationship mapping
              JOIN entity capability ON capability.id=mapping.capability_entity_id
              GROUP BY mapping.application_entity_id
              HAVING max(mapping.criticality)>=4
            )
            SELECT vulnerability.id vulnerability_id,vulnerability.name vulnerability,
                   dependency.id dependency_id,dependency.name dependency,
                   repository.id repository_id,repository.name repository,
                   application.id application_id,application.name application,
                   critical_application.criticality,critical_application.capabilities,
                   dependency_fact.id dependency_fact_id,affected.id affected_fact_id
            FROM fact_assertion dependency_fact
            JOIN dependency_usage_summary usage
              ON usage.dependency_fact_assertion_id=dependency_fact.id
             AND usage.static_reachability='OBSERVED'
            JOIN entity repository ON repository.id=dependency_fact.subject_entity_id
              AND repository.namespace='ENTERPRISE' AND repository.entity_type='Repository'
            JOIN production_repository ON production_repository.repository_id=repository.id
            JOIN entity dependency ON dependency.id=dependency_fact.object_entity_id
            JOIN fact_assertion affected ON affected.subject_entity_id=dependency.id
              AND affected.predicate='AFFECTED_BY' AND affected.system_to IS NULL
              AND (affected.tenant_id IS NULL OR affected.tenant_id=%s)
            JOIN entity vulnerability ON vulnerability.id=affected.object_entity_id
              AND vulnerability.entity_type='Vulnerability'
            JOIN fact_assertion application_link ON application_link.object_entity_id=repository.id
              AND application_link.predicate='IMPLEMENTED_BY' AND application_link.system_to IS NULL
              AND application_link.tenant_id=%s
            JOIN entity application ON application.id=application_link.subject_entity_id
            JOIN critical_application ON critical_application.application_entity_id=application.id
            WHERE dependency_fact.tenant_id=%s AND dependency_fact.predicate='DEPENDS_ON'
              AND dependency_fact.system_to IS NULL
            ORDER BY critical_application.criticality DESC,vulnerability.name,application.name,repository.name
            LIMIT 100
            """,
            (tenant_id, tenant_id, tenant_id, tenant_id),
            tenant_id=tenant_id,
        )
        fact_ids = [
            fact_id for row in rows
            for fact_id in (row.get("dependency_fact_id"), row.get("affected_fact_id"))
            if fact_id is not None
        ]
        citations = await self._ask_citations(fact_ids, tenant_id=tenant_id)
        result_rows = [{
            "vulnerability": row["vulnerability"], "dependency": row["dependency"],
            "application": row["application"], "repository": row["repository"],
            "capabilities": row["capabilities"], "criticality": int(row["criticality"]),
            "production_basis": "DECLARED_IN_CODE",
        } for row in rows]
        return AskResponse(
            text=(
                f"I found {len(rows)} statically reachable vulnerability impact path"
                f"{'s' if len(rows) != 1 else ''} in code-declared deployable Tier-1 applications mapped to criticality 4–5 capabilities. "
                "This does not claim a live deployment is currently running."
                if rows else "I found no statically reachable vulnerabilities with both code-declared deployable evidence and criticality 4–5 capability mappings."
            ),
            citations=citations, result_kind="TABLE", rows=result_rows,
        )

    async def _ask_duplicate_capability_implementations(self, *, tenant_id: UUID | None) -> AskResponse:
        rows = await self.database.fetch_all(
            """
            SELECT capability.id capability_id,capability.name capability,
                   count(DISTINCT inference.repository_entity_id)::integer repositories,
                   string_agg(DISTINCT repository.name,', ' ORDER BY repository.name) repository_names,
                   round(avg(inference.confidence)::numeric,4) confidence,
                   count(*) FILTER (WHERE inference.review_state='CONFIRMED')::integer confirmed,
                   array_agg(DISTINCT fact_id) fact_ids
            FROM capability_inference inference
            JOIN capability_definition capability ON capability.id=inference.capability_definition_id
            JOIN entity repository ON repository.id=inference.repository_entity_id
            CROSS JOIN LATERAL unnest(inference.supporting_fact_ids) fact_id
            WHERE inference.tenant_id=%s AND inference.stale_at IS NULL
              AND inference.review_state<>'REJECTED'
              AND (inference.assertion_class='CURATED' OR inference.review_state='CONFIRMED')
            GROUP BY capability.id,capability.name
            HAVING count(DISTINCT inference.repository_entity_id)>=2
            ORDER BY repositories DESC,confidence DESC,capability.name
            LIMIT 50
            """,
            (tenant_id,), tenant_id=tenant_id,
        )
        fact_ids = [fact_id for row in rows for fact_id in (row.get("fact_ids") or [])]
        citations = await self._ask_citations(fact_ids, tenant_id=tenant_id)
        result_rows = [{
            "capability": row["capability"],
            "repositories": int(row["repositories"]), "repository_names": row["repository_names"],
            "confidence": float(row["confidence"]), "confirmed_inferences": int(row["confirmed"]),
            "ownership_basis": "REPOSITORIES; team ownership not curated",
        } for row in rows]
        return AskResponse(
            text=(
                f"I found {len(rows)} capabilities independently evidenced in multiple repositories. "
                "Results identify repository implementations; team attribution remains unknown until repository ownership is curated."
                if rows else "I found no non-rejected capability inferences spanning multiple repositories."
            ),
            citations=citations, result_kind="TABLE", rows=result_rows,
        )

    async def _ask_modernization_blockers(self, *, tenant_id: UUID | None) -> AskResponse:
        rows = await self.database.fetch_all(
            """
            WITH assessed_blocker AS (
              SELECT technology.id technology_id,technology.name technology,
                     technology.entity_type technology_kind,
                     coalesce(assessment.categorical_value,'UNSUPPORTED') support_state,
                     assessment.rationale,repository.id repository_id,
                     repository.name repository_name,relationship.id fact_id
              FROM assessment
              JOIN entity technology ON technology.id=assessment.subject_entity_id
                AND technology.entity_type IN ('Runtime','Package','PackageVersion','Framework')
              JOIN fact_assertion relationship ON relationship.object_entity_id=technology.id
                AND relationship.tenant_id=%s AND relationship.system_to IS NULL
                AND relationship.predicate IN ('DEPENDS_ON','USES','HAS_VERSION')
              JOIN entity repository ON repository.id=relationship.subject_entity_id
                AND repository.namespace='ENTERPRISE' AND repository.entity_type='Repository'
              WHERE assessment.status='CURRENT'
                AND lower(assessment.dimension) IN ('supportability','runtime_support','package_support')
                AND upper(coalesce(assessment.categorical_value,technology.properties->>'support_status',''))
                  IN ('UNSUPPORTED','END_OF_LIFE','EOL')
            ), runtime_observation AS (
              SELECT image.id technology_id,image.name technology,'ContainerImage' technology_kind,
                     repository.id repository_id,repository.name repository_name,
                     runtime_fact.id fact_id,
                     CASE
                       WHEN lower(image.name) ~ '(^|/)node(js)?:' THEN 'node'
                       WHEN lower(image.name) ~ '(^|/)python:' THEN 'python'
                       WHEN lower(image.name) ~ '(^|/)dotnet:'
                         OR lower(image.name) LIKE '%%/dotnet/%%' THEN 'dotnet'
                     END runtime_key,
                     substring(image.name from ':v?([0-9]+([.][0-9]+){0,2})') observed_version
              FROM fact_assertion deployment
              JOIN entity repository ON repository.id=deployment.subject_entity_id
                AND repository.namespace='ENTERPRISE' AND repository.entity_type='Repository'
              JOIN fact_assertion runtime_fact
                ON runtime_fact.subject_entity_id=deployment.object_entity_id
               AND runtime_fact.tenant_id=deployment.tenant_id
               AND runtime_fact.predicate='RUNS_ON' AND runtime_fact.system_to IS NULL
              JOIN entity image ON image.id=runtime_fact.object_entity_id
                AND image.entity_type='ContainerImage'
              WHERE deployment.tenant_id=%s AND deployment.predicate='DEPLOYED_AS'
                AND deployment.system_to IS NULL
            ), policy_baseline AS (
              SELECT lower(baseline.key) runtime_key,baseline.value baseline_value,
                     substring(baseline.value from '([0-9]+([.][0-9]+){0,2})') baseline_version
              FROM modernization_policy policy
              CROSS JOIN LATERAL jsonb_each_text(policy.runtime_versions) baseline
              WHERE policy.tenant_id=%s AND policy.status='ACTIVE'
            ), baseline_blocker AS (
              SELECT observation.technology_id,observation.technology,
                     observation.technology_kind,'UNSUPPORTED'::text support_state,
                     'Code-declared runtime ' || observation.observed_version
                       || ' is below tenant baseline ' || baseline.baseline_value || '.' rationale,
                     observation.repository_id,observation.repository_name,observation.fact_id
              FROM runtime_observation observation
              JOIN policy_baseline baseline USING(runtime_key)
              WHERE observation.runtime_key IS NOT NULL
                AND observation.observed_version IS NOT NULL
                AND baseline.baseline_version IS NOT NULL
                AND (
                  split_part(observation.observed_version,'.',1)::integer
                    < split_part(baseline.baseline_version,'.',1)::integer
                  OR (
                    split_part(observation.observed_version,'.',1)::integer
                      = split_part(baseline.baseline_version,'.',1)::integer
                    AND coalesce(nullif(split_part(observation.observed_version,'.',2),''),'0')::integer
                      < coalesce(nullif(split_part(baseline.baseline_version,'.',2),''),'0')::integer
                  )
                )
            ), blocker AS (
              SELECT * FROM assessed_blocker
              UNION ALL
              SELECT * FROM baseline_blocker
            )
            SELECT technology_id,technology,technology_kind,support_state,rationale,
                   count(DISTINCT repository_id)::integer repositories,
                   string_agg(DISTINCT repository_name,', ' ORDER BY repository_name) repository_names,
                   array_agg(DISTINCT fact_id) fact_ids
            FROM blocker
            GROUP BY technology_id,technology,technology_kind,support_state,rationale
            ORDER BY repositories DESC,technology
            LIMIT 100
            """,
            (tenant_id, tenant_id, tenant_id), tenant_id=tenant_id,
        )
        fact_ids = [fact_id for row in rows for fact_id in (row.get("fact_ids") or [])]
        citations = await self._ask_citations(fact_ids, tenant_id=tenant_id)
        def ecosystem(row: Mapping[str, Any]) -> str:
            value = f"{row['technology']}".casefold()
            if any(token in value for token in ("node", "npm", "javascript", "typescript")):
                return "NODE"
            if any(token in value for token in ("python", "pypi")):
                return "PYTHON"
            if any(token in value for token in (".net", "dotnet", "nuget")):
                return "DOTNET"
            return "OTHER"
        result_rows = [{
            "technology": row["technology"],
            "kind": row["technology_kind"], "ecosystem": ecosystem(row),
            "support_state": row["support_state"], "repositories": int(row["repositories"]),
            "repository_names": row["repository_names"], "rationale": row.get("rationale"),
        } for row in rows]
        return AskResponse(
            text=(
                f"I found {len(rows)} evidence-backed unsupported technology blocker"
                f"{'s' if len(rows) != 1 else ''} from lifecycle assessments or code-declared runtime images. .NET results appear only when NuGet or .NET runtime evidence has been ingested."
                if rows else "I found no runtime below the active tenant baseline and no current unsupported package assessment linked to a repository."
            ),
            citations=citations, result_kind="TABLE", rows=result_rows,
        )

    async def _ask_package_business_blast_radius(
        self, normalized: str, *, context_ids: list[UUID], tenant_id: UUID | None,
    ) -> AskResponse:
        rows = await self.database.fetch_all(
            """
            WITH target AS (
              SELECT entity.id,
                     coalesce(identity.package_name,entity.name) name,
                     entity.canonical_key
              FROM entity
              LEFT JOIN package_registry_identity identity ON identity.entity_id=entity.id
              WHERE entity.entity_type IN ('Package','PackageVersion')
                AND (
                  entity.id=ANY(%s::uuid[])
                  OR (cardinality(%s::uuid[])=0 AND %s LIKE '%%' || lower(
                    coalesce(identity.package_name,regexp_replace(entity.name,'@[^@]+$',''))
                  ) || '%%')
                )
              ORDER BY CASE WHEN entity.id=ANY(%s::uuid[]) THEN 0 ELSE 1 END,entity.name
              LIMIT 50
            ), dependency AS (
              SELECT target.id package_id,target.name package,
                     fact.subject_entity_id repository_id,fact.id fact_id
              FROM target
              JOIN fact_assertion fact ON fact.object_entity_id=target.id
                AND fact.tenant_id=%s AND fact.predicate='DEPENDS_ON' AND fact.system_to IS NULL
            ), impact AS (
              SELECT dependency.package_id,dependency.package,
                     repository.id repository_id,repository.name repository,
                     application.id application_id,application.name application,
                     capability.id capability_id,capability.name capability,
                     mapping.criticality,dependency.fact_id
              FROM dependency
              JOIN entity repository ON repository.id=dependency.repository_id
              LEFT JOIN fact_assertion application_link
                ON application_link.object_entity_id=repository.id
               AND application_link.predicate='IMPLEMENTED_BY' AND application_link.system_to IS NULL
               AND application_link.tenant_id=%s
              LEFT JOIN entity application ON application.id=application_link.subject_entity_id
              LEFT JOIN current_capability_application_relationship mapping
                ON mapping.application_entity_id=application.id
              LEFT JOIN entity capability ON capability.id=mapping.capability_entity_id
            )
            SELECT (array_agg(DISTINCT package_id))[1] package_id,package,
                   capability_id,capability,
                   max(criticality)::integer criticality,
                   count(DISTINCT repository_id)::integer repositories,
                   count(DISTINCT application_id)::integer applications,
                   string_agg(DISTINCT repository,', ' ORDER BY repository) repository_names,
                   string_agg(DISTINCT application,', ' ORDER BY application) application_names,
                   array_agg(DISTINCT fact_id) fact_ids
            FROM impact
            GROUP BY package,capability_id,capability
            ORDER BY criticality DESC NULLS LAST,applications DESC,repositories DESC,package,capability
            LIMIT 100
            """,
            (context_ids, context_ids, normalized, context_ids, tenant_id, tenant_id),
            tenant_id=tenant_id,
        )
        if not rows:
            return AskResponse(
                text="I could not resolve that package to an evidence-backed repository dependency. Select a package or include its exact package name.",
                citations=[], result_kind="UNSUPPORTED", rows=[],
            )
        fact_ids = [fact_id for row in rows for fact_id in (row.get("fact_ids") or [])]
        citations = await self._ask_citations(fact_ids, tenant_id=tenant_id)
        result_rows = [{
            "package": row["package"],
            "business_capability": row.get("capability") or "UNMAPPED",
            "criticality": int(row["criticality"]) if row.get("criticality") is not None else None,
            "repositories": int(row["repositories"]), "applications": int(row["applications"]),
            "repository_names": row.get("repository_names"), "application_names": row.get("application_names"),
        } for row in rows]
        mapped = sum(row.get("capability_id") is not None for row in rows)
        return AskResponse(
            text=(
                f"I found {len(rows)} package-to-enterprise impact group{'s' if len(rows) != 1 else ''}; "
                f"{mapped} include governed business-capability mappings. Unmapped applications remain explicit."
            ),
            citations=citations, result_kind="TABLE", rows=result_rows,
        )

    async def _ask_top_package_business_blast_radius(
        self, *, tenant_id: UUID | None,
    ) -> AskResponse:
        """Select the package with the largest governed capability impact.

        This is the gallery-card variant of package blast radius. Free-form Ask keeps
        resolving an explicit package name; the card must not bake in one package.
        """
        rows = await self.database.fetch_all(
            """
            WITH dependency AS (
              SELECT coalesce(identity.package_name,
                              regexp_replace(package.name,'@[^@]+$','')) package,
                     fact.subject_entity_id repository_id,fact.id fact_id
              FROM fact_assertion fact
              JOIN entity package ON package.id=fact.object_entity_id
                AND package.entity_type IN ('Package','PackageVersion')
              LEFT JOIN package_registry_identity identity ON identity.entity_id=package.id
              WHERE fact.tenant_id=%s AND fact.predicate='DEPENDS_ON'
                AND fact.system_to IS NULL
            ), impact AS (
              SELECT dependency.package,repository.id repository_id,
                     repository.name repository,application.id application_id,
                     application.name application,capability.id capability_id,
                     capability.name capability,mapping.criticality,dependency.fact_id
              FROM dependency
              JOIN entity repository ON repository.id=dependency.repository_id
              JOIN fact_assertion application_link
                ON application_link.object_entity_id=repository.id
               AND application_link.predicate='IMPLEMENTED_BY'
               AND application_link.system_to IS NULL
               AND application_link.tenant_id=%s
              JOIN entity application ON application.id=application_link.subject_entity_id
              JOIN current_capability_application_relationship mapping
                ON mapping.application_entity_id=application.id
              JOIN entity capability ON capability.id=mapping.capability_entity_id
            ), selected_package AS (
              SELECT package
              FROM impact
              GROUP BY package
              ORDER BY max(criticality) DESC,
                       count(DISTINCT capability_id) DESC,
                       count(DISTINCT application_id) DESC,
                       count(DISTINCT repository_id) DESC,package
              LIMIT 1
            )
            SELECT impact.package,capability_id,capability,
                   max(criticality)::integer criticality,
                   count(DISTINCT repository_id)::integer repositories,
                   count(DISTINCT application_id)::integer applications,
                   string_agg(DISTINCT repository,', ' ORDER BY repository) repository_names,
                   string_agg(DISTINCT application,', ' ORDER BY application) application_names,
                   array_agg(DISTINCT fact_id) fact_ids
            FROM impact JOIN selected_package USING(package)
            GROUP BY impact.package,capability_id,capability
            ORDER BY criticality DESC,applications DESC,repositories DESC,capability
            LIMIT 100
            """,
            (tenant_id, tenant_id), tenant_id=tenant_id,
        )
        fact_ids = [fact_id for row in rows for fact_id in (row.get("fact_ids") or [])]
        citations = await self._ask_citations(fact_ids, tenant_id=tenant_id)
        result_rows = [{
            "package": row["package"],
            "business_capability": row["capability"],
            "criticality": int(row["criticality"]),
            "repositories": int(row["repositories"]),
            "applications": int(row["applications"]),
            "repository_names": row.get("repository_names"),
            "application_names": row.get("application_names"),
        } for row in rows]
        return AskResponse(
            text=(
                f"{rows[0]['package']} has the largest governed package blast radius, "
                f"spanning {len(rows)} business-capability impact group"
                f"{'s' if len(rows) != 1 else ''}."
                if rows else
                "I found no package dependency connected to a governed application-to-capability mapping."
            ),
            citations=citations, result_kind="TABLE", rows=result_rows,
        )

    async def _ask_technology_diversity(self, *, tenant_id: UUID | None) -> AskResponse:
        rows = await self.database.fetch_all(
            """
            WITH accepted AS (
              SELECT inference.repository_entity_id,inference.subject_entity_id,
                     inference.capability_definition_id,inference.confidence,
                     inference.supporting_fact_ids
              FROM capability_inference inference
              WHERE inference.tenant_id=%s AND inference.stale_at IS NULL
                AND (inference.assertion_class='CURATED' OR inference.review_state='CONFIRMED')
                AND inference.review_state<>'REJECTED'
            ), family AS (
              SELECT accepted.*,capability.name category,
                     coalesce(registry.ecosystem,
                       CASE
                         WHEN technology.canonical_key LIKE 'pkg:npm/%%' THEN 'NPM'
                         WHEN technology.canonical_key LIKE 'pkg:pypi/%%' THEN 'PYPI'
                         WHEN technology.canonical_key LIKE 'pkg:maven/%%' THEN 'MAVEN'
                         WHEN technology.canonical_key LIKE 'pkg:nuget/%%' THEN 'NUGET'
                         ELSE 'UNKNOWN'
                       END) ecosystem,
                     coalesce(identity.package_name,
                       regexp_replace(
                         regexp_replace(technology.name,'@[^@]+$',''),
                         '[[:space:]]+v?[0-9]+([.][0-9A-Za-z_-]+)*$',''
                       )) package_name
              FROM accepted
              JOIN capability_definition capability
                ON capability.id=accepted.capability_definition_id
              JOIN entity technology ON technology.id=accepted.subject_entity_id
              LEFT JOIN package_registry_identity identity
                ON identity.entity_id=accepted.subject_entity_id
              LEFT JOIN package_registry registry ON registry.id=identity.package_registry_id
            ), package_stat AS (
              SELECT capability_definition_id,category,ecosystem,package_name,
                     count(DISTINCT repository_entity_id)::integer repositories,
                     avg(confidence) confidence
              FROM family
              GROUP BY capability_definition_id,category,ecosystem,package_name
            ), category_stat AS (
              SELECT capability_definition_id,ecosystem,
                     count(DISTINCT repository_entity_id)::integer repositories
              FROM family GROUP BY capability_definition_id,ecosystem
            ), evidence AS (
              SELECT family.capability_definition_id,family.ecosystem,
                     family.package_name,fact_id
              FROM family CROSS JOIN LATERAL unnest(family.supporting_fact_ids) fact_id
            )
            SELECT package_stat.capability_definition_id,package_stat.category,
                   package_stat.ecosystem,
                   count(DISTINCT package_stat.package_name)::integer packages,
                   category_stat.repositories,
                   count(DISTINCT package_stat.package_name)
                     FILTER (WHERE package_stat.repositories=1)::integer low_adoption_packages,
                   max(package_stat.repositories)::integer leading_package_repositories,
                   string_agg(DISTINCT package_stat.package_name,', '
                     ORDER BY package_stat.package_name) package_names,
                   round(min(package_stat.confidence)::numeric,4) confidence,
                   array_agg(DISTINCT evidence.fact_id) fact_ids
            FROM package_stat
            JOIN category_stat USING(capability_definition_id,ecosystem)
            JOIN evidence ON evidence.capability_definition_id=package_stat.capability_definition_id
              AND evidence.ecosystem=package_stat.ecosystem
              AND evidence.package_name=package_stat.package_name
            GROUP BY package_stat.capability_definition_id,package_stat.category,
                     package_stat.ecosystem,category_stat.repositories
            HAVING count(DISTINCT package_stat.package_name)>1
            ORDER BY packages DESC,low_adoption_packages DESC,category,ecosystem
            LIMIT 50
            """,
            (tenant_id,), tenant_id=tenant_id,
        )
        fact_ids = [fact_id for row in rows for fact_id in (row.get("fact_ids") or [])]
        citations = await self._ask_citations(fact_ids, tenant_id=tenant_id)
        result_rows = [{
            "package_category": row["category"],
            "ecosystem": row["ecosystem"],
            "diversity_score": min(
                100,
                (int(row["packages"]) - 1) * 12
                + int(row["low_adoption_packages"]) * 7
                + int(row["repositories"]) * 4,
            ),
            "package_families": int(row["packages"]),
            "repositories": int(row["repositories"]),
            "low_adoption_packages": int(row["low_adoption_packages"]),
            "leading_package_repositories": int(row["leading_package_repositories"]),
            "packages": row["package_names"],
            "confidence": float(row["confidence"]),
        } for row in rows]
        result_rows.sort(key=lambda row: (
            -row["diversity_score"], row["package_category"], row["ecosystem"],
        ))
        return AskResponse(
            text=(
                f"I found {len(rows)} governed package-category and ecosystem combinations with multiple implementations. "
                "The deterministic score increases with package-family count, one-repository choices, and estate breadth; it does not assume all diversity is harmful."
                if rows else "I found no within-ecosystem package category with multiple curated or confirmed implementations. Cross-language choices are not treated as unnecessary diversity."
            ),
            citations=citations, result_kind="TABLE", rows=result_rows,
        )

    async def _ask_internal_library_standards(self, *, tenant_id: UUID | None) -> AskResponse:
        governed_rows = await self.database.fetch_all(
            """
            WITH criticality AS (
              SELECT application_link.object_entity_id repository_id,
                     max(mapping.criticality)::integer criticality
              FROM fact_assertion application_link
              JOIN current_capability_application_relationship mapping
                ON mapping.application_entity_id=application_link.subject_entity_id
              WHERE application_link.tenant_id=%s
                AND application_link.predicate='IMPLEMENTED_BY'
                AND application_link.system_to IS NULL
              GROUP BY application_link.object_entity_id
            ), production AS (
              SELECT deployment.subject_entity_id repository_id,
                     true code_production
              FROM fact_assertion deployment
              WHERE deployment.tenant_id=%s AND deployment.predicate='DEPLOYED_AS'
                AND deployment.system_to IS NULL
                AND coalesce(deployment.properties->>'source_kind','')
                    IN ('KUBERNETES','COMPOSE','DOCKERFILE')
              GROUP BY deployment.subject_entity_id
            )
            SELECT component.component_key,component.version,entity.name,
                   capability.name capability,component.owner,component.security_status,
                   count(DISTINCT repository.id)::integer repositories,
                   count(DISTINCT repository.id) FILTER
                     (WHERE usage.static_reachability='OBSERVED')::integer reachable_repositories,
                   count(DISTINCT repository.id) FILTER
                     (WHERE production.code_production)::integer code_production_repositories,
                   count(DISTINCT repository.id) FILTER
                     (WHERE criticality.criticality>=4)::integer critical_repositories,
                   array_remove(array_agg(DISTINCT relationship.id),NULL)
                     ||component.supporting_fact_ids fact_ids
            FROM modernization_internal_component component
            JOIN entity ON entity.id=component.component_entity_id
            JOIN capability_definition capability
              ON capability.id=component.capability_definition_id
            LEFT JOIN fact_assertion relationship
              ON relationship.object_entity_id=component.component_entity_id
             AND relationship.tenant_id=%s AND relationship.system_to IS NULL
             AND relationship.predicate IN ('DEPENDS_ON','USES')
            LEFT JOIN entity repository ON repository.id=relationship.subject_entity_id
              AND repository.namespace='ENTERPRISE' AND repository.entity_type='Repository'
            LEFT JOIN dependency_usage_summary usage
              ON usage.dependency_fact_assertion_id=relationship.id
            LEFT JOIN production ON production.repository_id=repository.id
            LEFT JOIN criticality ON criticality.repository_id=repository.id
            WHERE component.tenant_id=%s AND component.review_state='APPROVED'
              AND component.status='APPROVED'
            GROUP BY component.id,component.component_key,component.version,entity.name,
                     capability.name,component.owner,component.security_status,
                     component.supporting_fact_ids
            HAVING count(DISTINCT repository.id)>0
            ORDER BY repositories DESC,reachable_repositories DESC,entity.name
            LIMIT 50
            """,
            (tenant_id, tenant_id, tenant_id, tenant_id), tenant_id=tenant_id,
        )
        clone_rows = await self.database.fetch_all(
            """
            WITH repeated AS (
              SELECT structural_fingerprint
              FROM code_implementation_summary
              WHERE tenant_id=%s AND NOT vendored
                AND line_end-line_start+1>=6
              GROUP BY structural_fingerprint
              HAVING count(DISTINCT repository_entity_id)>=2
            ), candidate AS (
              SELECT unit.*,repository.name repository_name,
                     application.subject_entity_id application_id,
                     mapping.capability_entity_id capability_id,
                     mapping.criticality
              FROM code_implementation_summary unit
              JOIN repeated USING(structural_fingerprint)
              JOIN entity repository ON repository.id=unit.repository_entity_id
                AND repository.namespace='ENTERPRISE'
                AND repository.entity_type='Repository'
              LEFT JOIN fact_assertion application
                ON application.object_entity_id=unit.repository_entity_id
               AND application.tenant_id=unit.tenant_id
               AND application.predicate='IMPLEMENTED_BY'
               AND application.system_to IS NULL
              LEFT JOIN current_capability_application_relationship mapping
                ON mapping.application_entity_id=application.subject_entity_id
              WHERE unit.tenant_id=%s
            )
            SELECT structural_fingerprint,min(qualified_name) name,
                   count(DISTINCT repository_entity_id)::integer repositories,
                   count(DISTINCT capability_id)::integer capabilities,
                   count(DISTINCT repository_entity_id) FILTER
                     (WHERE criticality>=4)::integer critical_repositories,
                   array_agg(DISTINCT fact_assertion_id) fact_ids
            FROM candidate
            GROUP BY structural_fingerprint
            ORDER BY capabilities DESC,repositories DESC,name
            LIMIT 50
            """,
            (tenant_id, tenant_id), tenant_id=tenant_id,
        )
        rows = list(governed_rows) + list(clone_rows)
        fact_ids = [fact_id for row in rows for fact_id in (row.get("fact_ids") or [])]
        citations = await self._ask_citations(fact_ids, tenant_id=tenant_id)
        result_rows = [{
            "internal_library": row["name"], "version": row["version"],
            "capability": row["capability"],
            "standardization_score": min(
                100,
                int(row["repositories"]) * 12
                + int(row["reachable_repositories"]) * 10
                + int(row["code_production_repositories"]) * 8
                + int(row["critical_repositories"]) * 10
                + (10 if row["security_status"] == "CLEAR" else 0)
                + (5 if row.get("owner") else 0),
            ),
            "repositories": int(row["repositories"]),
            "reachable_repositories": int(row["reachable_repositories"]),
            "code_deployable_repositories": int(row["code_production_repositories"]),
            "critical_repositories": int(row["critical_repositories"]),
            "owner": row.get("owner"), "security_status": row["security_status"],
            "governance_status": "APPROVED",
        } for row in governed_rows]
        result_rows.extend({
            "internal_library": row["name"], "version": "—",
            "capability": f"{int(row['capabilities'])} mapped business capabilities",
            "standardization_score": min(
                90,
                int(row["repositories"]) * 12
                + int(row["capabilities"]) * 10
                + int(row["critical_repositories"]) * 10,
            ),
            "repositories": int(row["repositories"]),
            "reachable_repositories": 0,
            "code_deployable_repositories": 0,
            "critical_repositories": int(row["critical_repositories"]),
            "owner": None, "security_status": "REVIEW_REQUIRED",
            "governance_status": "CANDIDATE",
        } for row in clone_rows)
        result_rows.sort(key=lambda row: (-row["standardization_score"], row["internal_library"]))
        return AskResponse(
            text=(
                f"I ranked {len(result_rows)} enterprise-library candidates. Approved components use adoption, reachability, code-declared deployability, criticality, ownership, and security status; structural clones add repository and business-capability breadth but remain governance candidates."
                if rows else "I found no adopted, approved internal component to rank. Govern candidates in Admin → Governance → Modernization before StackGraph recommends them as enterprise standards."
            ),
            citations=citations, result_kind="TABLE", rows=result_rows,
        )

    async def _ask_custom_to_internal_platform(self, *, tenant_id: UUID | None) -> AskResponse:
        rows = await self.database.fetch_all(
            """
            WITH business_context AS (
              SELECT application_link.object_entity_id repository_id,
                     max(mapping.criticality)::integer criticality
              FROM fact_assertion application_link
              JOIN current_capability_application_relationship mapping
                ON mapping.application_entity_id=application_link.subject_entity_id
              WHERE application_link.tenant_id=%s
                AND application_link.predicate='IMPLEMENTED_BY'
                AND application_link.system_to IS NULL
              GROUP BY application_link.object_entity_id
            )
            SELECT DISTINCT ON (candidate.id)
                   candidate.id,repository.name repository,capability.name capability,
                   component_entity.name internal_platform,component.owner,
                   option.compatibility,option.score option_score,
                   impact.affected_call_sites,impact.affected_files,impact.effort_points,
                   candidate.confidence,candidate.review_state,
                   coalesce(business_context.criticality,0)::integer criticality,
                   coalesce(recommendation.title,candidate.summary) initiative,
                   candidate.supporting_fact_ids||option.supporting_fact_ids
                     ||component.supporting_fact_ids fact_ids
            FROM modernization_candidate candidate
            JOIN entity repository ON repository.id=candidate.repository_entity_id
            JOIN capability_definition capability
              ON capability.id=candidate.capability_definition_id
            JOIN modernization_option option
              ON option.modernization_candidate_id=candidate.id
             AND option.option_kind='INTERNAL'
            JOIN modernization_option_evaluation evaluation
              ON evaluation.modernization_option_id=option.id AND evaluation.eligible
            JOIN modernization_internal_component component
              ON component.component_entity_id=option.target_entity_id
             AND component.capability_definition_id=candidate.capability_definition_id
             AND component.review_state='APPROVED' AND component.status='APPROVED'
            JOIN entity component_entity ON component_entity.id=component.component_entity_id
            LEFT JOIN modernization_impact impact
              ON impact.modernization_candidate_id=candidate.id
            LEFT JOIN LATERAL (
              SELECT value.title FROM modernization_recommendation value
              WHERE value.modernization_candidate_id=candidate.id
                AND value.stale_at IS NULL
                AND value.review_state NOT IN ('REJECTED','DISMISSED')
              ORDER BY value.updated_at DESC,value.id LIMIT 1
            ) recommendation ON true
            LEFT JOIN business_context ON business_context.repository_id=repository.id
            WHERE candidate.tenant_id=%s AND candidate.stale_at IS NULL
              AND candidate.review_state<>'REJECTED'
              AND candidate.candidate_kind IN ('INTERNAL_DUPLICATION','NATIVE_REPLACEMENT')
            ORDER BY candidate.id,option.score DESC,option.rank,option.id
            LIMIT 100
            """,
            (tenant_id, tenant_id), tenant_id=tenant_id,
        )
        coverage = await self.database.fetch_one(
            """
            SELECT count(*)::integer internal_code_options,
                   count(*) FILTER (WHERE component.id IS NOT NULL)::integer governed_platform_options
            FROM modernization_option option
            JOIN modernization_candidate candidate
              ON candidate.id=option.modernization_candidate_id
             AND candidate.stale_at IS NULL AND candidate.review_state<>'REJECTED'
            LEFT JOIN modernization_internal_component component
              ON component.component_entity_id=option.target_entity_id
             AND component.capability_definition_id=candidate.capability_definition_id
             AND component.review_state='APPROVED' AND component.status='APPROVED'
            WHERE candidate.tenant_id=%s AND option.option_kind='INTERNAL'
            """,
            (tenant_id,), tenant_id=tenant_id,
        ) or {"internal_code_options": 0, "governed_platform_options": 0}
        fact_ids = [fact_id for row in rows for fact_id in (row.get("fact_ids") or [])]
        citations = await self._ask_citations(fact_ids, tenant_id=tenant_id)
        result_rows = [{
            "initiative": row["initiative"], "repository": row["repository"],
            "capability": row["capability"], "internal_platform": row["internal_platform"],
            "platform_owner": row.get("owner"), "compatibility": row["compatibility"],
            "option_score": float(row["option_score"]),
            "affected_call_sites": int(row.get("affected_call_sites") or 0),
            "affected_files": int(row.get("affected_files") or 0),
            "criticality": int(row["criticality"]), "review_state": row["review_state"],
        } for row in rows]
        return AskResponse(
            text=(
                f"I found {len(rows)} custom implementations with an eligible, governed internal-platform replacement. Candidate review state remains visible before action."
                if rows else
                f"I found no eligible governed internal-platform replacement. StackGraph has {int(coverage['internal_code_options'])} internal code-reuse options, but {int(coverage['governed_platform_options'])} point to approved platform catalog entries; govern platforms in Admin before treating them as replacement standards."
            ),
            citations=citations, result_kind="TABLE", rows=result_rows,
        )

    async def _ask_application_retirement_consolidation(
        self, *, tenant_id: UUID | None,
    ) -> AskResponse:
        rows = await self.database.fetch_all(
            """
            WITH app_repository AS (
              SELECT link.subject_entity_id application_id,link.object_entity_id repository_id,
                     link.id link_fact_id
              FROM fact_assertion link
              WHERE link.tenant_id=%s AND link.predicate='IMPLEMENTED_BY'
                AND link.system_to IS NULL
            ), app_criticality AS (
              SELECT application_entity_id application_id,
                     max(criticality)::integer criticality
              FROM current_capability_application_relationship
              GROUP BY application_entity_id
            ), retirement AS (
              SELECT application.id application_id,application.name application,
                     repository.name repository,
                     greatest(0,90-coalesce(app_criticality.criticality,3)*10)::integer score,
                     coalesce(app_criticality.criticality,3)::integer criticality,
                     ARRAY[app_repository.link_fact_id] fact_ids
              FROM ingest_target target
              JOIN entity repository ON repository.canonical_key=target.target_key
                AND repository.namespace='ENTERPRISE' AND repository.entity_type='Repository'
              JOIN app_repository ON app_repository.repository_id=repository.id
              JOIN entity application ON application.id=app_repository.application_id
              LEFT JOIN app_criticality ON app_criticality.application_id=application.id
              WHERE target.tenant_id=%s AND target.target_kind='REPOSITORY'
                AND coalesce((target.refresh_policy->>'archived')::boolean,false)
            ), capability_pair AS (
              SELECT left_map.application_entity_id left_application_id,
                     right_map.application_entity_id right_application_id,
                     count(DISTINCT left_map.capability_entity_id)::integer shared_capabilities
              FROM current_capability_application_relationship left_map
              JOIN current_capability_application_relationship right_map
                ON right_map.capability_entity_id=left_map.capability_entity_id
               AND right_map.application_entity_id>left_map.application_entity_id
              GROUP BY left_map.application_entity_id,right_map.application_entity_id
            ), dependency_family AS (
              SELECT app_repository.application_id,dependency.id fact_id,
                     coalesce(identity.package_name,
                       regexp_replace(
                         regexp_replace(package.name,'@[^@]+$',''),
                         '[[:space:]]+v?[0-9]+([.][0-9A-Za-z_-]+)*$',''
                       )) package_name
              FROM app_repository
              JOIN fact_assertion dependency
                ON dependency.subject_entity_id=app_repository.repository_id
               AND dependency.predicate='DEPENDS_ON' AND dependency.system_to IS NULL
               AND dependency.tenant_id=%s
              JOIN entity package ON package.id=dependency.object_entity_id
              LEFT JOIN package_registry_identity identity ON identity.entity_id=package.id
            ), dependency_pair AS (
              SELECT left_dep.application_id left_application_id,
                     right_dep.application_id right_application_id,
                     count(DISTINCT left_dep.package_name)::integer shared_packages,
                     array_agg(DISTINCT left_dep.fact_id)
                       ||array_agg(DISTINCT right_dep.fact_id) fact_ids
              FROM dependency_family left_dep
              JOIN dependency_family right_dep
                ON right_dep.package_name=left_dep.package_name
               AND right_dep.application_id>left_dep.application_id
              GROUP BY left_dep.application_id,right_dep.application_id
            ), consolidation AS (
              SELECT left_app.name application,right_app.name comparison_application,
                     least(100,capability_pair.shared_capabilities*25
                       +dependency_pair.shared_packages*3
                       +greatest(0,20-coalesce(greatest(left_criticality.criticality,
                         right_criticality.criticality),3)*4))::integer score,
                     capability_pair.shared_capabilities,dependency_pair.shared_packages,
                     coalesce(greatest(left_criticality.criticality,
                       right_criticality.criticality),3)::integer criticality,
                     dependency_pair.fact_ids
              FROM capability_pair
              JOIN dependency_pair USING(left_application_id,right_application_id)
              JOIN entity left_app ON left_app.id=left_application_id
              JOIN entity right_app ON right_app.id=right_application_id
              LEFT JOIN app_criticality left_criticality
                ON left_criticality.application_id=left_application_id
              LEFT JOIN app_criticality right_criticality
                ON right_criticality.application_id=right_application_id
              WHERE capability_pair.shared_capabilities>0
                AND dependency_pair.shared_packages>0
            )
            SELECT 'RETIRE' candidate_kind,application candidate,
                   NULL::text comparison_application,score opportunity_score,
                   0::integer shared_capabilities,0::integer shared_packages,
                   criticality,'Git repository is archived; validate ownership and runtime absence' basis,
                   fact_ids
            FROM retirement
            UNION ALL
            SELECT 'CONSOLIDATE',application,comparison_application,score,
                   shared_capabilities,shared_packages,criticality,
                   'Shared governed capabilities and overlapping package families',fact_ids
            FROM consolidation
            ORDER BY opportunity_score DESC,candidate,comparison_application NULLS FIRST
            LIMIT 50
            """,
            (tenant_id, tenant_id, tenant_id), tenant_id=tenant_id,
        )
        fact_ids = [fact_id for row in rows for fact_id in (row.get("fact_ids") or [])]
        citations = await self._ask_citations(fact_ids, tenant_id=tenant_id)
        result_rows = [{
            "candidate_kind": row["candidate_kind"], "application": row["candidate"],
            "comparison_application": row.get("comparison_application"),
            "opportunity_score": int(row["opportunity_score"]),
            "shared_capabilities": int(row["shared_capabilities"]),
            "shared_packages": int(row["shared_packages"]),
            "max_criticality": int(row["criticality"]), "basis": row["basis"],
        } for row in rows]
        retirement_count = sum(row["candidate_kind"] == "RETIRE" for row in rows)
        consolidation_count = len(rows) - retirement_count
        return AskResponse(
            text=(
                f"I found {retirement_count} retirement and {consolidation_count} consolidation candidates. Retirement requires a Git-archived repository; consolidation requires shared governed capabilities plus package overlap. Neither is an automatic action."
                if rows else "I found no defensible retirement or consolidation candidate. Retirement needs a Git-archived repository; consolidation needs overlapping Business Map capabilities and package evidence."
            ),
            citations=citations, result_kind="TABLE", rows=result_rows,
        )

    async def _ask_standardization_initiatives(self, *, tenant_id: UUID | None) -> AskResponse:
        scored = (await self._governed_portfolio_scores(tenant_id))[:10]
        fact_ids = [
            fact_id for row, _value in scored
            for fact_id in (row.get("supporting_fact_ids") or [])
        ]
        citations = await self._ask_citations(fact_ids, tenant_id=tenant_id)
        result_rows = [{
            "initiative": row["title"].replace(
                " implementation implementations", " implementations",
            ),
            "category": row["candidate_kind"],
            "repository": row["repository_name"],
            "proposed_target": row.get("standard_target"),
            "enterprise_payoff": round(value.score * 100, 2),
            "affected_call_sites": int(row.get("affected_call_sites") or 0),
            "affected_files": int(row.get("affected_files") or 0),
            "effort_points": int(row["effort_points"]),
            "confidence": round(value.candidate.confidence, 4),
            "governance_state": (
                f"candidate:{row['candidate_review_state']} / "
                f"recommendation:{row['recommendation_review_state']}"
            ),
            "policy_version": value.policy_version,
        } for row, value in scored]
        policy_version = scored[0][1].policy_version if scored else None
        policy_basis = (
            "the active governed modernization portfolio policy"
            if policy_version and not policy_version.endswith("unconfigured")
            else "deterministic default portfolio weights; publish a portfolio policy in Admin to govern the weights"
        )
        return AskResponse(
            text=(
                f"I ranked {len(scored)} engineering standardization initiatives using {policy_basis}. Payoff combines business footprint, viability gap, technology entropy, reuse, confidence, and effort penalty."
                if scored else "I found no active evidence-backed modernization recommendation to rank as a standardization initiative."
            ),
            citations=citations, result_kind="TABLE", rows=result_rows,
        )

    async def _ask_citations(
        self, fact_ids: list[UUID], *, tenant_id: UUID | None,
    ) -> list[Citation]:
        unique_ids = list(dict.fromkeys(fact_ids))[:200]
        if not unique_ids:
            return []
        rows = await self.database.fetch_all(
            """
            SELECT DISTINCT ON (fact.id) fact.id fact_id,
                   coalesce(artifact.name,artifact.external_key,fact.predicate) label
            FROM fact_assertion fact
            LEFT JOIN evidence ON evidence.fact_assertion_id=fact.id
            LEFT JOIN source_artifact artifact ON artifact.id=evidence.source_artifact_id
            WHERE fact.id=ANY(%s::uuid[])
            ORDER BY fact.id,evidence.observed_at DESC
            """,
            (unique_ids,), tenant_id=tenant_id,
        )
        return [Citation(
            fact_id=row["fact_id"], label=row["label"],
            href=f"/api/v1/facts/{row['fact_id']}/evidence",
        ) for row in rows]

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
            invalidate_deterministic_insight_cache(tenant_id)
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
            invalidate_deterministic_insight_cache(tenant_id)
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
        for assignment in state.application_assignments:
            require(
                assignment.capability_id in capability_keys,
                "application_assignment.capability_id",
                assignment.capability_id,
            )

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
                        INSERT INTO entity
                          (tenant_id,namespace,entity_type,canonical_key,name,properties,first_seen_at,last_seen_at)
                        VALUES (%s,'BUSINESS','BusinessCapability',%s,%s,%s::jsonb,now(),now())
                        ON CONFLICT(tenant_id,namespace,entity_type,canonical_key) DO UPDATE
                        SET name=EXCLUDED.name,
                            properties=entity.properties||EXCLUDED.properties,
                            last_seen_at=now(),updated_at=now()
                        RETURNING id
                        """,
                        (
                            tenant_id,
                            f"capability:{capability.id}",
                            capability.name,
                            json.dumps({
                                "description": capability.description,
                                "tags": capability.tags,
                                "owner": capability.owner,
                                "criticality": capability.criticality,
                                "governance": "CURATED",
                            }),
                        ),
                    )
                    capability_entity_id = (await cursor.fetchone())["id"]
                    cursor = await connection.execute(
                        """
                        INSERT INTO business_map_capability
                          (tenant_id,business_map_id,business_map_process_id,capability_key,entity_id,name,description,tags,kpis,owner,criticality,position)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id
                        """,
                        (
                            tenant_id, map_id, process_id, capability.id, capability_entity_id,
                            capability.name, capability.description, capability.tags, capability.kpis,
                            capability.owner, capability.criticality, capability_order,
                        ),
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
        if state.application_assignments:
            requested_application_ids = sorted(
                {assignment.application_id for assignment in state.application_assignments},
                key=str,
            )
            cursor = await connection.execute(
                """
                SELECT id FROM entity
                WHERE id=ANY(%s::uuid[]) AND tenant_id=%s
                  AND namespace='ENTERPRISE' AND entity_type='Application'
                """,
                (requested_application_ids, tenant_id),
            )
            found_application_ids = {row["id"] for row in await cursor.fetchall()}
            missing_application_ids = [
                str(application_id)
                for application_id in requested_application_ids
                if application_id not in found_application_ids
            ]
            if missing_application_ids:
                raise APIError(
                    422,
                    "BUSINESS_MAP_INVALID_APPLICATION",
                    "A business capability can only be linked to an application in this tenant's estate.",
                    {"application_ids": missing_application_ids},
                )
            for assignment in state.application_assignments:
                await connection.execute(
                    """
                    INSERT INTO business_map_application_assignment
                      (tenant_id,business_map_id,business_map_capability_id,application_entity_id)
                    VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING
                    """,
                    (
                        tenant_id,
                        map_id,
                        capability_ids[assignment.capability_id],
                        assignment.application_id,
                    ),
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
                                criticality=cap["criticality"],
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

        cursor = await connection.execute(
            """
            SELECT assignment.business_map_capability_id,
                   assignment.application_entity_id,application.name application_name
            FROM business_map_application_assignment assignment
            JOIN entity application ON application.id=assignment.application_entity_id
            WHERE assignment.business_map_id=%s
            ORDER BY application.name,application.id
            """,
            (map_id,),
        )
        application_assignments = [
            BusinessMapApplicationAssignment(
                capability_id=capability_key_by_id[assignment["business_map_capability_id"]],
                application_id=assignment["application_entity_id"],
                application_name=assignment["application_name"],
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
                function_assignments=assignments, application_assignments=application_assignments,
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
              SELECT r.fact_assertion_id,r.relationship_type,r.confidence,
                     fact.properties relationship_properties,
                     fact.assertion_class,
                     CASE WHEN r.source_entity_id=%s THEN r.target_entity_id ELSE r.source_entity_id END id
              FROM current_relationship r
              JOIN fact_assertion fact ON fact.id=r.fact_assertion_id
              WHERE r.source_entity_id=%s OR r.target_entity_id=%s
            ), repositories AS (
              SELECT d.id FROM direct d JOIN entity e ON e.id=d.id
              WHERE e.namespace='ENTERPRISE' AND e.entity_type='Repository'
                AND d.relationship_type IN ('IMPLEMENTED_BY','IMPLEMENTS','CONTAINS')
            ), repository_related AS (
              SELECT r.fact_assertion_id,r.relationship_type,r.confidence,
                     fact.properties relationship_properties,
                     fact.assertion_class,
                     CASE WHEN r.source_entity_id=repositories.id
                       THEN r.target_entity_id ELSE r.source_entity_id END id
              FROM repositories JOIN current_relationship r
                ON r.source_entity_id=repositories.id OR r.target_entity_id=repositories.id
              JOIN fact_assertion fact ON fact.id=r.fact_assertion_id
              WHERE r.relationship_type IN (
                'DEPENDS_ON','USES','RUNS_ON','DEPLOYED_AS','BUILT_ON','HAS_VERSION'
              )
            ), selected AS (
              SELECT d.id,1 depth,d.fact_assertion_id,d.confidence,
                     d.relationship_properties,d.assertion_class
              FROM direct d JOIN entity e ON e.id=d.id
              WHERE (
                e.namespace='BUSINESS'
                AND d.relationship_type IN ('ENABLED_BY','REQUIRES','PROVIDED_BY','CONTAINS')
              ) OR (
                e.namespace='ENTERPRISE' AND e.entity_type='Repository'
                AND d.relationship_type IN ('IMPLEMENTED_BY','IMPLEMENTS','CONTAINS')
              ) OR (
                e.namespace='ENTERPRISE' AND e.entity_type='Service'
                AND d.relationship_type IN ('CONTAINS','IMPLEMENTED_BY','IMPLEMENTS')
              ) OR (
                e.namespace='DEPLOYMENT'
                AND d.relationship_type IN ('DEPLOYED_AS','RUNS_ON','HOSTED_IN','HOSTED_AT')
              ) OR (
                e.namespace IN ('TECHNOLOGY','OSS')
                AND d.relationship_type IN ('DEPENDS_ON','USES','RUNS_ON','BUILT_ON','HAS_VERSION')
              )
              UNION ALL
              SELECT rr.id,2,rr.fact_assertion_id,rr.confidence,
                     rr.relationship_properties,rr.assertion_class
              FROM repository_related rr JOIN entity e ON e.id=rr.id
              WHERE e.namespace IN ('TECHNOLOGY','OSS','DEPLOYMENT')
            )
            SELECT e.*,min(selected.depth) depth,
                   array_agg(DISTINCT selected.fact_assertion_id) usage_fact_ids,
                   max(selected.confidence) usage_confidence,
                   array_agg(DISTINCT selected.relationship_properties)
                     FILTER (WHERE selected.relationship_properties<>'{}'::jsonb)
                     usage_property_sets,
                   array_agg(DISTINCT selected.assertion_class)
                     usage_assertion_classes,
                   coalesce(e.last_seen_at,e.updated_at,e.created_at) observed_at
            FROM selected JOIN entity e ON e.id=selected.id
            GROUP BY e.id ORDER BY min(selected.depth),e.namespace,e.entity_type,e.name,e.id
            """,
            (application_id, application_id, application_id),
            tenant_id=tenant_id,
        )

    async def _application_dependency_hierarchies(
        self,
        repository_rows: list[dict[str, Any]],
        tenant_id: UUID | None,
    ) -> list[ApplicationRepositoryDependencyHierarchy]:
        if not repository_rows:
            return []

        max_depth = 6
        max_nodes_per_component = 250
        membership_rows = await self.database.fetch_all(
            """
            WITH repositories AS (
              SELECT unnest(%s::uuid[]) id
            )
            SELECT repositories.id repository_id,
                   relationship.predicate relationship_type,
                   relationship.id fact_assertion_id,
                   relationship.confidence,
                   relationship.properties dependency_properties,
                   technology.*
            FROM repositories
            JOIN fact_assertion relationship
              ON relationship.subject_entity_id=repositories.id
             AND relationship.system_to IS NULL
            JOIN entity technology ON technology.id=relationship.object_entity_id
            WHERE technology.namespace IN ('TECHNOLOGY','OSS')
              AND relationship.predicate IN ('DEPENDS_ON','USES','RUNS_ON','BUILT_ON')
            ORDER BY repositories.id,technology.name,technology.id,
                     relationship.confidence DESC,relationship.id
            """,
            ([row["id"] for row in repository_rows],),
            tenant_id=tenant_id,
        )

        repositories_by_id = {UUID(str(row["id"])): row for row in repository_rows}
        technologies_by_id: dict[UUID, dict[str, Any]] = {}
        members_by_repository: dict[UUID, set[UUID]] = defaultdict(set)
        roots: dict[tuple[UUID, str], dict[UUID, dict[str, Any]]] = defaultdict(dict)
        for row in membership_rows:
            repository_id = UUID(str(row["repository_id"]))
            technology_id = UUID(str(row["id"]))
            technologies_by_id[technology_id] = row
            members_by_repository[repository_id].add(technology_id)
            properties = (
                row.get("dependency_properties")
                if isinstance(row.get("dependency_properties"), dict) else {}
            )
            direct_marker = properties.get("direct")
            is_direct = (
                str(row["relationship_type"]) != "DEPENDS_ON"
                or direct_marker is None
                or direct_marker is True
                or (isinstance(direct_marker, str) and direct_marker.lower() == "true")
            )
            if not is_direct:
                continue
            component_path = _optional_string(properties.get("component_path")) or "."
            component_roots = roots[(repository_id, component_path)]
            existing = component_roots.get(technology_id)
            if existing is None or _number(row.get("confidence")) > _number(existing.get("confidence")):
                component_roots[technology_id] = row

        technology_ids = list(technologies_by_id)
        edge_rows = await self.database.fetch_all(
            """
            SELECT DISTINCT ON (relationship.subject_entity_id,relationship.object_entity_id)
                   relationship.subject_entity_id source_id,
                   relationship.object_entity_id target_id,
                   relationship.predicate relationship_type,
                   relationship.id fact_assertion_id,
                   relationship.confidence,
                   relationship.properties dependency_properties
            FROM fact_assertion relationship
            WHERE relationship.predicate='DEPENDS_ON'
              AND relationship.system_to IS NULL
              AND relationship.subject_entity_id=ANY(%s::uuid[])
              AND relationship.object_entity_id=ANY(%s::uuid[])
            ORDER BY relationship.subject_entity_id,relationship.object_entity_id,
                     relationship.confidence DESC,relationship.id
            """,
            (technology_ids, technology_ids),
            tenant_id=tenant_id,
        ) if technology_ids else []
        adjacency: dict[UUID, list[dict[str, Any]]] = defaultdict(list)
        for row in edge_rows:
            adjacency[UUID(str(row["source_id"]))].append(row)
        for edges in adjacency.values():
            edges.sort(key=lambda row: (str(row["target_id"]), str(row["fact_assertion_id"])))

        grouped: dict[UUID, list[ApplicationComponentDependencyHierarchy]] = defaultdict(list)
        for (repository_id, component_path), component_roots in sorted(
            roots.items(), key=lambda item: (str(item[0][0]), item[0][1].lower())
        ):
            repository_members = members_by_repository[repository_id]
            selected: dict[UUID, tuple[UUID | None, int, dict[str, Any]]] = {}
            queue: deque[UUID] = deque()
            truncated = False
            for technology_id, row in sorted(
                component_roots.items(),
                key=lambda item: (
                    str(item[1]["name"]).lower(),
                    str(item[0]),
                ),
            ):
                if len(selected) >= max_nodes_per_component:
                    truncated = True
                    break
                selected[technology_id] = (None, 1, row)
                queue.append(technology_id)

            while queue and not truncated:
                parent_id = queue.popleft()
                parent_depth = selected[parent_id][1]
                if parent_depth >= max_depth:
                    continue
                for edge in adjacency.get(parent_id, []):
                    child_id = UUID(str(edge["target_id"]))
                    if child_id not in repository_members or child_id in selected:
                        continue
                    if len(selected) >= max_nodes_per_component:
                        truncated = True
                        break
                    selected[child_id] = (parent_id, parent_depth + 1, edge)
                    queue.append(child_id)

            dependencies: list[ApplicationDependencyNode] = []
            for technology_id, (parent_id, depth, evidence_row) in selected.items():
                properties = (
                    evidence_row.get("dependency_properties")
                    if isinstance(evidence_row.get("dependency_properties"), dict) else {}
                )
                fact_id = UUID(str(evidence_row["fact_assertion_id"]))
                confidence = _number(evidence_row.get("confidence"), 0.0)
                dependencies.append(ApplicationDependencyNode(
                    technology=_entity(technologies_by_id[technology_id]),
                    parent_technology_id=parent_id,
                    depth=depth,
                    direct=depth == 1,
                    relationship=str(evidence_row["relationship_type"]),
                    scope=_optional_string(properties.get("scope")),
                    requirement=_optional_string(
                        properties.get("requirement") or properties.get("requested_spec")
                    ),
                    dependency_relation=_optional_string(properties.get("dependency_relation")),
                    confidence=confidence,
                    confidence_label=_confidence_label(confidence),
                    citations=[Citation(
                        fact_id=fact_id,
                        label=(
                            "Declared dependency evidence"
                            if depth == 1 else "Resolved dependency evidence"
                        ),
                        href=f"/api/v1/facts/{fact_id}/evidence",
                    )],
                ))
            grouped[repository_id].append(ApplicationComponentDependencyHierarchy(
                component_path=component_path,
                dependencies=dependencies,
                truncated=truncated,
            ))

        return [
            ApplicationRepositoryDependencyHierarchy(
                repository=_entity(repositories_by_id[repository_id]),
                components=components,
            )
            for repository_id, components in sorted(
                grouped.items(),
                key=lambda item: (
                    str(repositories_by_id[item[0]]["name"]).lower(),
                    str(item[0]),
                ),
            )
        ]

    async def _technology_classification_catalog(
        self,
        tenant_id: UUID | None,
    ) -> list[dict[str, Any]]:
        return await self.database.fetch_all(
            """
            SELECT technology.*,
                   capability.id capability_id,
                   coalesce(
                     capability.properties->>'capability_key',
                     replace(capability.canonical_key,'stackgraph:capability:','')
                   ) capability_key,
                   capability.name capability_name,
                   capability.properties->>'definition' capability_summary,
                   catalog_fact.fact_assertion_id catalog_fact_id,
                   provides.id classification_fact_id,
                   provides.confidence classification_confidence
            FROM entity technology
            LEFT JOIN fact_assertion provides
              ON provides.subject_entity_id=technology.id
             AND provides.predicate='PROVIDES'
             AND provides.system_to IS NULL
            LEFT JOIN LATERAL (
              SELECT fact.id fact_assertion_id
              FROM fact_assertion fact
              WHERE fact.subject_entity_id=technology.id
                AND fact.predicate='HAS_PROPERTY'
                AND fact.object_value->>'record_kind'='technology_catalog_entry'
                AND fact.system_to IS NULL
              ORDER BY fact.observed_at DESC,fact.id DESC
              LIMIT 1
            ) catalog_fact ON true
            LEFT JOIN entity capability
              ON capability.id=provides.object_entity_id
             AND capability.entity_type='Capability'
            WHERE technology.namespace='TECHNOLOGY'
              AND technology.entity_type='Technology'
              AND technology.properties ? 'domain_id'
            ORDER BY technology.name,capability.name,technology.id,capability.id
            """,
            tenant_id=tenant_id,
        )

    async def _technology_catalog_metadata(
        self,
        technology_ids: list[UUID],
        tenant_id: UUID | None,
    ) -> list[dict[str, Any]]:
        if not technology_ids:
            return []
        return await self.database.fetch_all(
            """
            WITH selected AS (
              SELECT unnest(%s::uuid[]) selected_technology_id
            ), candidates AS (
              SELECT selected.selected_technology_id,selected.selected_technology_id candidate_id,0 priority
              FROM selected
              UNION ALL
              SELECT selected.selected_technology_id,relationship.object_entity_id,1
              FROM selected
              JOIN fact_assertion relationship
                ON relationship.subject_entity_id=selected.selected_technology_id
               AND relationship.system_to IS NULL
               AND relationship.predicate IN ('HAS_VERSION','PUBLISHES','PUBLISHED_BY')
              WHERE relationship.object_entity_id IS NOT NULL
              UNION ALL
              SELECT selected.selected_technology_id,relationship.subject_entity_id,1
              FROM selected
              JOIN fact_assertion relationship
                ON relationship.object_entity_id=selected.selected_technology_id
               AND relationship.system_to IS NULL
               AND relationship.predicate IN ('HAS_VERSION','PUBLISHES','PUBLISHED_BY')
            ), ranked_metadata AS (
              SELECT candidates.selected_technology_id,entity.*,
                     row_number() OVER (
                       PARTITION BY candidates.selected_technology_id
                       ORDER BY candidates.priority,
                                CASE entity.entity_type
                                  WHEN 'Package' THEN 0 WHEN 'OSSProject' THEN 1 ELSE 2 END,
                                entity.id
                     ) metadata_rank
              FROM candidates
              JOIN entity ON entity.id=candidates.candidate_id
              WHERE entity.namespace IN ('TECHNOLOGY','OSS')
                AND entity.properties ? 'catalog_metadata'
            ), metadata_entities AS (
              SELECT * FROM ranked_metadata WHERE metadata_rank=1
            )
            SELECT metadata.selected_technology_id,
                   metadata.properties catalog_properties,
                   catalog_fact.id catalog_fact_id
            FROM metadata_entities metadata
            LEFT JOIN LATERAL (
              SELECT fact.id
              FROM fact_assertion fact
              WHERE fact.subject_entity_id=metadata.id
                AND fact.predicate='HAS_PROPERTY'
                AND fact.object_value->>'record_kind' IN (
                  'huggingface_top_npm_package','technology_catalog_entry'
                )
                AND fact.system_to IS NULL
              ORDER BY fact.observed_at DESC,fact.id DESC
              LIMIT 1
            ) catalog_fact ON true
            ORDER BY metadata.selected_technology_id
            """,
            (technology_ids,),
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
