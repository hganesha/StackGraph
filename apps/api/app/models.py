from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


Namespace = Literal["BUSINESS", "ENTERPRISE", "TECHNOLOGY", "OSS", "DEPLOYMENT", "INTELLIGENCE"]
ConfidenceLabel = Literal["HIGH", "MEDIUM", "LOW"]
FreshnessStatus = Literal["FRESH", "STALE", "UNKNOWN"]


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Citation(ContractModel):
    fact_id: UUID
    label: str = Field(min_length=1)
    href: str | None = None


class Score(ContractModel):
    value: float
    confidence: float = Field(ge=0, le=1)
    confidence_label: ConfidenceLabel
    method_version: str = Field(min_length=1)


class Freshness(ContractModel):
    observed_at: datetime
    effective_at: datetime | None = None
    status: FreshnessStatus
    source_key: str | None = None


class PageInfo(ContractModel):
    has_next_page: bool
    next_cursor: str | None = None


class SessionInfo(ContractModel):
    contract_version: Literal["1.0.0"] = "1.0.0"
    actor_key: str = Field(min_length=1)
    tenant_id: UUID | None = None
    capabilities: list[str]


class RankedItem(ContractModel):
    id: UUID
    kind: str = Field(min_length=1)
    name: str = Field(min_length=1)
    domain: Namespace
    priority: Score
    viability: Score | None = None
    summary: str | None = None
    parent_application_id: UUID | None = None
    parent_application_name: str | None = None
    dependency_tier: int | None = Field(default=None, ge=1, le=2)
    systemic_risk: float | None = Field(default=None, ge=0, le=1)
    upstream_impact: float | None = Field(default=None, ge=0)
    dependency_depth: int | None = Field(default=None, ge=0)
    community_key: str | None = None
    structural_status: Literal[
        "STRUCTURALLY_CRITICAL", "ELEVATED", "TYPICAL", "WAITING_FOR_DATA",
    ] | None = None
    freshness: Freshness
    citations: list[Citation] | None = None


class EstateCounts(ContractModel):
    applications: int = Field(ge=0)
    repositories: int = Field(ge=0)
    services: int = Field(ge=0)
    technologies: int = Field(ge=0)


class Coverage(ContractModel):
    repositories_total: int = Field(ge=0)
    repositories_scanned: int = Field(ge=0)
    facts_with_evidence_ratio: float = Field(ge=0, le=1)


class EstateSummary(ContractModel):
    contract_version: Literal["1.0.0"] = "1.0.0"
    as_of: datetime
    counts: EstateCounts
    distributions: dict[str, float]
    ranked_items: list[RankedItem]
    coverage: Coverage
    page_info: PageInfo | None = None
    limitations: list[dict[str, Any]] = Field(default_factory=list)


class EntitySummary(ContractModel):
    id: UUID
    kind: str = Field(min_length=1)
    name: str = Field(min_length=1)
    canonical_key: str | None = None
    summary: str | None = None


class EntityDescriptionUpdateRequest(ContractModel):
    """A human-curated description, distinct from `summary` values discovery infers
    (package metadata, catalog definitions) — those stay read-only; this is the only
    field an owner can edit directly. Empty string clears the override."""

    description: str = Field(max_length=2000)


class TaxonomySummary(ContractModel):
    key: str = Field(min_length=1)
    name: str = Field(min_length=1)
    summary: str | None = None


TechnologyClassification = Literal[
    "CURATED", "CATALOG_MATCH", "DETERMINISTIC", "UNCLASSIFIED",
]


class TechnologyCatalogProfile(ContractModel):
    summary: str | None = None
    package_name: str | None = None
    ecosystem: str | None = None
    license: str | None = None
    homepage: str | None = None
    repository_url: str | None = None
    package_url: str | None = None
    latest_version: str | None = None
    weekly_downloads: int | None = Field(default=None, ge=0)
    dependents: int | None = Field(default=None, ge=0)
    versions: int | None = Field(default=None, ge=0)
    installation_command: str | None = None
    catalog_technology: EntitySummary | None = None
    domain: TaxonomySummary | None = None
    category: TaxonomySummary | None = None
    functions: list[TaxonomySummary] = Field(default_factory=list)
    classification: TechnologyClassification
    citations: list[Citation] = Field(min_length=1)


class ApplicationTechnologyResourceDetails(ContractModel):
    resource_kind: Literal["DATABASE", "CACHE", "OBJECT_STORAGE"]
    engine: str = Field(min_length=1)
    providers: list[str] = Field(default_factory=list)
    signal_kinds: list[str] = Field(default_factory=list)
    package_dependencies: list[str] = Field(default_factory=list)
    config_keys: list[str] = Field(default_factory=list)
    source_referenced: bool = False
    inference_method: str | None = None
    assertion_class: Literal[
        "DECLARED", "OBSERVED", "INFERRED", "CURATED", "EXTERNAL_MEASURED",
    ]
    limitations: list[str] = Field(default_factory=list)


class ApplicationTechnologyUsage(ContractModel):
    technology: EntitySummary
    category: TaxonomySummary | None = None
    classification: TechnologyClassification
    confidence: float = Field(ge=0, le=1)
    confidence_label: ConfidenceLabel
    resource_details: ApplicationTechnologyResourceDetails | None = None
    citations: list[Citation] = Field(min_length=1)


class ApplicationTechnologyFunction(ContractModel):
    function: TaxonomySummary
    technologies: list[ApplicationTechnologyUsage] = Field(min_length=1)


class ApplicationTechnologyGroup(ContractModel):
    domain: TaxonomySummary
    functions: list[ApplicationTechnologyFunction] = Field(min_length=1)


class ApplicationDependencyNode(ContractModel):
    technology: EntitySummary
    parent_technology_id: UUID | None = None
    depth: int = Field(ge=1)
    direct: bool
    relationship: str = Field(min_length=1)
    scope: str | None = None
    requirement: str | None = None
    dependency_relation: str | None = None
    confidence: float = Field(ge=0, le=1)
    confidence_label: ConfidenceLabel
    citations: list[Citation] = Field(min_length=1)


class ApplicationComponentDependencyHierarchy(ContractModel):
    component_path: str = Field(min_length=1)
    dependencies: list[ApplicationDependencyNode] = Field(min_length=1)
    truncated: bool = False


class ApplicationRepositoryDependencyHierarchy(ContractModel):
    repository: EntitySummary
    components: list[ApplicationComponentDependencyHierarchy] = Field(min_length=1)


class TechnologyEstateHierarchyNode(ContractModel):
    technology: EntitySummary
    parent_technology_id: UUID | None = None
    depth: int = Field(ge=1)
    direct: bool
    relationship: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)
    confidence_label: ConfidenceLabel
    dependent_applications: list[EntitySummary]
    catalog_profile: TechnologyCatalogProfile | None = None
    citations: list[Citation] = Field(min_length=1)


class TechnologyEstateHierarchy(ContractModel):
    contract_version: Literal["1.0.0"] = "1.0.0"
    as_of: datetime
    nodes: list[TechnologyEstateHierarchyNode]
    truncated: bool = False


class AssessmentSummary(ContractModel):
    id: UUID
    dimension: str = Field(min_length=1)
    score: float | None = None
    categorical_value: str | None = None
    confidence: float = Field(ge=0, le=1)
    confidence_label: ConfidenceLabel
    method_version: str = Field(min_length=1)
    rationale: str | None = None
    citations: list[Citation] = Field(min_length=1)

    @model_validator(mode="after")
    def require_one_value(self) -> AssessmentSummary:
        if (self.score is None) == (self.categorical_value is None):
            raise ValueError("exactly one of score or categorical_value is required")
        return self


Action = Literal[
    "RETAIN", "UPGRADE", "REMOVE", "REPLACE", "CONSOLIDATE", "REFACTOR",
    "REBUILD", "REPLATFORM", "RETIRE", "INVESTIGATE",
]
RecommendationStatus = Literal[
    "PROPOSED", "ACCEPTED", "REJECTED", "PLANNED", "IN_PROGRESS", "COMPLETED", "DISMISSED",
]


class RecommendationSummary(ContractModel):
    id: UUID
    action: Action
    title: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)
    confidence_label: ConfidenceLabel
    status: RecommendationStatus
    estimated_effort: Literal["LOW", "MEDIUM", "HIGH", "UNKNOWN"] | None = None
    counter_signals: list[str] | None = None
    target: EntitySummary | None = None
    citations: list[Citation] = Field(min_length=1)


class GraphAnalysisSnapshot(ContractModel):
    analysis_run_id: UUID
    policy_key: str = Field(min_length=1)
    policy_version: int = Field(ge=1)
    policy_hash: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    status: Literal["SUCCEEDED", "SUCCEEDED_WITH_LIMITATIONS"]
    as_of: datetime
    requested_change_watermark: int = Field(ge=0)
    neo4j_projection_watermark: int = Field(ge=0)
    node_count: int = Field(ge=0)
    edge_count: int = Field(ge=0)
    coverage: dict[str, Any] = Field(default_factory=dict)
    limitations: list[dict[str, Any]] = Field(default_factory=list)


class GraphMetric(ContractModel):
    analysis_run_id: UUID
    policy_key: str = Field(min_length=1)
    metric_key: str = Field(min_length=1)
    numeric_value: float | None = None
    percentile: float | None = Field(default=None, ge=0, le=1)
    rank: int | None = Field(default=None, ge=1)
    components: dict[str, Any] = Field(default_factory=dict)
    limitations: list[dict[str, Any]] = Field(default_factory=list)


class EntityGraphIntelligence(ContractModel):
    contract_version: Literal["1.0.0"] = "1.0.0"
    entity: EntitySummary
    primary_status: Literal["STRUCTURALLY_CRITICAL", "ELEVATED", "TYPICAL", "WAITING_FOR_DATA"]
    reasons: list[str] = Field(default_factory=list)
    snapshots: list[GraphAnalysisSnapshot] = Field(default_factory=list)
    metrics: list[GraphMetric] = Field(default_factory=list)
    community_keys: list[str] = Field(default_factory=list)
    as_of: datetime
    limitations: list[dict[str, Any]] = Field(default_factory=list)


class ApplicationDetail(ContractModel):
    contract_version: Literal["1.0.0"] = "1.0.0"
    application: EntitySummary
    business_context: list[EntitySummary]
    repositories: list[EntitySummary]
    services: list[EntitySummary]
    technologies: list[EntitySummary]
    technology_groups: list[ApplicationTechnologyGroup]
    dependency_hierarchies: list[ApplicationRepositoryDependencyHierarchy] = Field(default_factory=list)
    deployments: list[EntitySummary]
    assessments: list[AssessmentSummary]
    recommendations: list[RecommendationSummary]
    freshness: Freshness
    graph_intelligence: EntityGraphIntelligence | None = None


class GraphIntelligenceStatus(ContractModel):
    contract_version: Literal["1.0.0"] = "1.0.0"
    as_of: datetime
    deployment_state: Literal["PROVISIONING", "ACTIVE", "SUSPENDED", "ERROR", "UNCONFIGURED"]
    desired_change_watermark: int = Field(ge=0)
    neo4j_projection_watermark: int = Field(ge=0)
    projection_lag: int = Field(ge=0)
    pending_requests: int = Field(ge=0)
    running_requests: int = Field(ge=0)
    failed_requests: int = Field(ge=0)
    oldest_pending_at: datetime | None = None
    snapshots: list[GraphAnalysisSnapshot] = Field(default_factory=list)
    limitations: list[dict[str, Any]] = Field(default_factory=list)


class GraphImpactPath(ContractModel):
    target: EntitySummary
    distance: int = Field(ge=1)
    minimum_confidence: float = Field(ge=0, le=1)
    entity_ids: list[UUID] = Field(min_length=2)
    supporting_fact_ids: list[UUID] = Field(min_length=1)


class GraphBlastRadius(ContractModel):
    contract_version: Literal["1.0.0"] = "1.0.0"
    entity: EntitySummary
    snapshot: GraphAnalysisSnapshot | None = None
    affected_entity_count: int = Field(ge=0)
    maximum_depth: int = Field(ge=0)
    impacts: list[GraphImpactPath] = Field(default_factory=list)
    as_of: datetime
    limitations: list[dict[str, Any]] = Field(default_factory=list)


class GraphRiskItem(ContractModel):
    entity: EntitySummary
    impacted_applications: list[EntitySummary] = Field(default_factory=list)
    systemic_risk: float = Field(ge=0, le=1)
    component_metrics: list[GraphMetric] = Field(default_factory=list)
    component_contributions: dict[str, dict[str, Any]] = Field(default_factory=dict)
    renormalized_families: list[str] = Field(default_factory=list)
    method_version: str = "graph-systemic-risk/v2"
    reasons: list[str] = Field(default_factory=list)


class GraphRiskList(ContractModel):
    contract_version: Literal["1.0.0"] = "1.0.0"
    snapshot: GraphAnalysisSnapshot | None = None
    risks: list[GraphRiskItem] = Field(default_factory=list)
    as_of: datetime
    limitations: list[dict[str, Any]] = Field(default_factory=list)
    page_info: PageInfo | None = None


class GraphCommunity(ContractModel):
    community_key: str = Field(min_length=1)
    member_count: int = Field(ge=1)
    representative_entities: list[EntitySummary] = Field(default_factory=list)


class GraphCommunityList(ContractModel):
    contract_version: Literal["1.0.0"] = "1.0.0"
    snapshot: GraphAnalysisSnapshot | None = None
    algorithm_key: str = Field(min_length=1)
    communities: list[GraphCommunity] = Field(default_factory=list)
    as_of: datetime
    limitations: list[dict[str, Any]] = Field(default_factory=list)


class GraphAnomaly(ContractModel):
    id: UUID
    entity: EntitySummary
    anomaly_key: str = Field(min_length=1)
    score: float = Field(ge=0, le=1)
    cohort_key: str = Field(min_length=1)
    cohort_size: int = Field(ge=1)
    percentile: float = Field(ge=0, le=1)
    observed_components: dict[str, Any] = Field(default_factory=dict)
    reasons: list[str] = Field(default_factory=list)
    supporting_fact_ids: list[UUID] = Field(default_factory=list)
    limitations: list[dict[str, Any]] = Field(default_factory=list)


class GraphAnomalyList(ContractModel):
    contract_version: Literal["1.0.0"] = "1.0.0"
    snapshot: GraphAnalysisSnapshot | None = None
    anomalies: list[GraphAnomaly] = Field(default_factory=list)
    as_of: datetime
    limitations: list[dict[str, Any]] = Field(default_factory=list)


class GraphMotif(ContractModel):
    id: UUID
    motif_key: str = Field(min_length=1)
    members: list[EntitySummary] = Field(min_length=2)
    supporting_fact_ids: list[UUID] = Field(min_length=1)
    minimum_confidence: float = Field(ge=0, le=1)
    components: dict[str, Any] = Field(default_factory=dict)
    limitations: list[dict[str, Any]] = Field(default_factory=list)


class GraphMotifList(ContractModel):
    contract_version: Literal["1.0.0"] = "1.0.0"
    snapshot: GraphAnalysisSnapshot | None = None
    motifs: list[GraphMotif] = Field(default_factory=list)
    as_of: datetime
    limitations: list[dict[str, Any]] = Field(default_factory=list)


class CriticalGraphEdge(ContractModel):
    fact_id: UUID
    source: EntitySummary
    target: EntitySummary
    metric_key: str = "spof.bridge"
    score: float = Field(ge=0)
    components: dict[str, Any] = Field(default_factory=dict)
    supporting_fact_ids: list[UUID] = Field(min_length=1)
    limitations: list[dict[str, Any]] = Field(default_factory=list)


class CriticalGraphEdgeList(ContractModel):
    contract_version: Literal["1.0.0"] = "1.0.0"
    entity: EntitySummary
    snapshot: GraphAnalysisSnapshot | None = None
    edges: list[CriticalGraphEdge] = Field(default_factory=list)
    as_of: datetime
    limitations: list[dict[str, Any]] = Field(default_factory=list)


class SemanticSearchRequest(ContractModel):
    query: str = Field(min_length=2,max_length=2000)
    entity_types: list[str] = Field(default_factory=list,max_length=20)
    namespace: list[Namespace] = Field(default_factory=list,max_length=6)
    min_score: float = Field(default=-1,ge=-1,le=1)
    limit: int = Field(default=20,ge=1,le=100)


class SemanticSearchHit(ContractModel):
    entity: EntitySummary
    score: float = Field(ge=-1,le=1)
    input_hash: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    sensitivity: Literal["PUBLIC","INTERNAL","CONFIDENTIAL","RESTRICTED"]
    matched_terms: list[str] = Field(default_factory=list)
    excerpt: str | None = Field(default=None,max_length=500)
    source_fact_ids: list[UUID] = Field(default_factory=list)
    limitations: list[dict[str, Any]] = Field(default_factory=list)


class SemanticSearchResponse(ContractModel):
    contract_version: Literal["1.0.0"] = "1.0.0"
    space_id: UUID
    space_key: str
    model_or_algorithm: str
    template_version: str
    query_hash: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    hits: list[SemanticSearchHit] = Field(default_factory=list)
    as_of: datetime
    limitations: list[dict[str,Any]] = Field(default_factory=list)


class EmbeddingSpaceSnapshot(ContractModel):
    id: UUID
    space_key: str
    space_kind: Literal["SEMANTIC_ENTITY","STRUCTURAL_GRAPH","CODE"]
    lifecycle_state: Literal["SHADOW","ACTIVE","RETIRED","FAILED"]
    provider: str
    model_or_algorithm: str
    dimensions: int = Field(ge=8,le=4096)
    template_version: str
    coverage_ratio: float = Field(ge=0,le=1)
    evaluation: dict[str,Any] = Field(default_factory=dict)
    updated_at: datetime


class EmbeddingStatus(ContractModel):
    contract_version: Literal["1.0.0"] = "1.0.0"
    as_of: datetime
    enabled: bool
    provider: str
    model: str
    pending_jobs: int = Field(ge=0)
    running_jobs: int = Field(ge=0)
    failed_jobs: int = Field(ge=0)
    active_spaces: list[EmbeddingSpaceSnapshot] = Field(default_factory=list)
    shadow_spaces: list[EmbeddingSpaceSnapshot] = Field(default_factory=list)
    limitations: list[dict[str,Any]] = Field(default_factory=list)


SimilarityReviewState = Literal[
    "UNREVIEWED","CONFIRMED_SIMILAR","CONFIRMED_DISTINCT",
    "CONSOLIDATION_CANDIDATE","DISMISSED",
]


class ApplicationSimilarityCandidate(ContractModel):
    id: UUID
    application: EntitySummary
    score: float = Field(ge=0,le=1)
    method_version: str
    components: dict[str,Any]
    overlaps: dict[str,Any]
    differences: dict[str,Any]
    coverage: dict[str,Any]
    limitations: list[dict[str,Any]] = Field(default_factory=list)
    review_state: SimilarityReviewState
    created_at: datetime


class ApplicationSimilarityList(ContractModel):
    contract_version: Literal["1.0.0"] = "1.0.0"
    subject: EntitySummary
    candidates: list[ApplicationSimilarityCandidate] = Field(default_factory=list)
    as_of: datetime
    limitations: list[dict[str,Any]] = Field(default_factory=list)
    page_info: PageInfo | None = None


class ApplicationSimilarityReviewRequest(ContractModel):
    decision: Literal[
        "CONFIRMED_SIMILAR","CONFIRMED_DISTINCT","CONSOLIDATION_CANDIDATE","DISMISSED","REOPENED",
    ]
    reason_code: str = Field(min_length=1,max_length=100)
    rationale: str = Field(default="",max_length=4000)


class ApplicationSimilarityReviewResult(ContractModel):
    contract_version: Literal["1.0.0"] = "1.0.0"
    candidate_id: UUID
    review_state: SimilarityReviewState
    reviewed_at: datetime


class RepositoryProfile(ContractModel):
    purpose: str | None = None
    purpose_source: str | None = None
    descriptions: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    components: list[str] = Field(default_factory=list)
    key_files: list[str] = Field(default_factory=list)
    operational_signals: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    source_revision: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)
    confidence_label: ConfidenceLabel
    citations: list[Citation] = Field(min_length=1)


class RepositoryDetail(ContractModel):
    contract_version: Literal["1.0.0"] = "1.0.0"
    repository: EntitySummary
    profile: RepositoryProfile | None = None
    applications: list[EntitySummary]
    technologies: list[EntitySummary]
    deployments: list[EntitySummary]
    freshness: Freshness
    graph_intelligence: EntityGraphIntelligence | None = None


RepositoryActivityWindow = Literal["7d", "30d", "90d"]
RepositoryActivityCoverageStatus = Literal[
    "AVAILABLE", "PARTIAL", "NOT_COLLECTED", "PERMISSION_REQUIRED", "ERROR",
]


class RepositoryActivityActor(ContractModel):
    actor_key: str = Field(min_length=1)
    login: str = Field(min_length=1)
    avatar_url: str | None = None
    is_bot: bool = False
    classification: Literal[
        "HUMAN", "BOT", "DEPENDENCY_BOT", "CI_AUTOMATION",
        "AI_AGENT", "AI_ASSISTED_HUMAN", "UNKNOWN",
    ] = "UNKNOWN"
    classification_confidence: float = Field(default=0, ge=0, le=1)
    classification_basis: str | None = None


class RepositoryActivityEvent(ContractModel):
    id: UUID
    event_type: Literal[
        "COMMIT", "PULL_REQUEST_OPENED", "PULL_REQUEST_MERGED", "RELEASE", "DEPLOYMENT",
        "DEPENDENCY_CHANGE", "ARCHITECTURE_CHANGE", "INCIDENT", "INTERVENTION", "ROLLBACK",
    ]
    title: str = Field(min_length=1)
    occurred_at: datetime
    actor: RepositoryActivityActor | None = None
    revision: str | None = None
    branch: str | None = None
    pull_request_number: int | None = Field(default=None, ge=1)
    source_url: str | None = None


class RepositoryActivityContributor(ContractModel):
    actor: RepositoryActivityActor
    commits: int = Field(ge=0)
    pull_requests_merged: int = Field(ge=0)
    total_events: int = Field(ge=0)


class RepositoryActivitySummary(ContractModel):
    commits: int | None = Field(default=None, ge=0)
    pull_requests_merged: int | None = Field(default=None, ge=0)
    contributors: int | None = Field(default=None, ge=0)
    last_change_at: datetime | None = None
    releases: int | None = Field(default=None, ge=0)
    deployments: int | None = Field(default=None, ge=0)


class RepositoryActivityCoverage(ContractModel):
    commits: RepositoryActivityCoverageStatus
    pull_requests: RepositoryActivityCoverageStatus
    contributors: RepositoryActivityCoverageStatus
    releases: RepositoryActivityCoverageStatus = "NOT_COLLECTED"
    deployments: RepositoryActivityCoverageStatus = "NOT_COLLECTED"


class RepositoryActivitySource(ContractModel):
    provider: Literal["GITHUB"] = "GITHUB"
    full_name: str | None = None
    default_branch: str | None = None
    visibility: Literal["PUBLIC", "PRIVATE", "INTERNAL", "UNKNOWN"] = "UNKNOWN"
    archived: bool | None = None


class RepositoryActivity(ContractModel):
    contract_version: Literal["1.0.0"] = "1.0.0"
    repository: EntitySummary
    source: RepositoryActivitySource
    window: RepositoryActivityWindow
    window_started_at: datetime
    window_ended_at: datetime
    summary: RepositoryActivitySummary
    coverage: RepositoryActivityCoverage
    top_contributors: list[RepositoryActivityContributor]
    events: list[RepositoryActivityEvent]
    page_info: PageInfo
    freshness: Freshness
    limitations: list[str] = Field(default_factory=list)


class InternalUsage(ContractModel):
    repository_count: int = Field(ge=0)
    application_count: int = Field(ge=0)
    repositories: list[EntitySummary] | None = None


class PackageSource(ContractModel):
    registry_key: str = Field(min_length=1)
    origin: str
    visibility: Literal["PUBLIC", "PRIVATE", "UNKNOWN"]
    tenant_scoped: bool
    freshness: Freshness


class TechnologyDetail(ContractModel):
    contract_version: Literal["1.0.0"] = "1.0.0"
    technology: EntitySummary
    internal_usage: InternalUsage
    packages: list[EntitySummary]
    projects: list[EntitySummary]
    catalog_profile: TechnologyCatalogProfile | None = None
    registry_sources: list[PackageSource] | None = None
    alternatives: list[EntitySummary] | None = None
    migration_patterns: list[EntitySummary] | None = None
    assessments: list[AssessmentSummary]
    recommendations: list[RecommendationSummary]
    freshness: Freshness
    graph_intelligence: EntityGraphIntelligence | None = None


class ModernizationList(ContractModel):
    contract_version: Literal["1.0.0"] = "1.0.0"
    as_of: datetime
    opportunities: list[RankedItem]
    page_info: PageInfo


InsightSeverity = Literal["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"]
InsightKind = Literal[
    "VULNERABLE_DIRECT_DEPENDENCY",
    "VULNERABLE_TRANSITIVE_DEPENDENCY",
    "DEPRECATED_DEPENDENCY",
    "UNUSED_DIRECT_DEPENDENCY",
    "VERSION_FRAGMENTATION",
    "CAPABILITY_DIVERSITY",
    "DEPENDENCY_CONFUSION",
    "LICENSE_OBLIGATION",
    "CROSS_REPOSITORY_CLONE",
    "VENDORED_SOURCE_OUTSIDE_MANAGEMENT",
    "MISSING_README",
    "MISSING_LICENSE",
    "MISSING_CODEOWNERS",
    "MISSING_CI_CONFIGURATION",
    "MISSING_DEPENDENCY_LOCKFILE",
    "MISSING_TESTS",
]


class InsightImpactStages(ContractModel):
    present: int = Field(ge=0)
    referenced: int = Field(ge=0)
    statically_reachable: int = Field(ge=0)
    runtime_observed: int = Field(ge=0)
    deployed: int = Field(ge=0)
    production: int | None = Field(default=None, ge=0)
    externally_exposed: int | None = Field(default=None, ge=0)
    business_critical: int | None = Field(default=None, ge=0)


class DeterministicInsightRecommendation(ContractModel):
    action: Literal["UPGRADE", "REMOVE", "CONSOLIDATE", "REPLACE", "INVESTIGATE"]
    title: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    target: EntitySummary | None = None
    estimated_effort: Literal["LOW", "MEDIUM", "HIGH", "UNKNOWN"]


class DeterministicInsight(ContractModel):
    id: UUID
    rule_key: str = Field(min_length=1)
    rule_version: str = Field(min_length=1)
    kind: InsightKind
    severity: InsightSeverity
    title: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    priority_score: float = Field(ge=0, le=100)
    evidence_coverage: float = Field(ge=0, le=1)
    subject: EntitySummary
    affected_repository_count: int = Field(ge=0)
    affected_application_count: int = Field(ge=0)
    affected_deployment_count: int = Field(ge=0)
    affected_repositories: list[EntitySummary]
    scope_entity_ids: list[UUID]
    stages: InsightImpactStages
    supporting_fact_ids: list[UUID] = Field(min_length=1)
    missing_inputs: list[str]
    recommendation: DeterministicInsightRecommendation | None = None
    input_fingerprint: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    detected_at: datetime


class DeterministicInsightSummary(ContractModel):
    total: int = Field(ge=0)
    critical: int = Field(ge=0)
    high: int = Field(ge=0)
    affected_repositories: int = Field(ge=0)
    runtime_observed: int = Field(ge=0)
    deployed: int = Field(ge=0)


class DeterministicInsightList(ContractModel):
    contract_version: Literal["1.0.0"] = "1.0.0"
    as_of: datetime
    summary: DeterministicInsightSummary
    insights: list[DeterministicInsight]
    page_info: PageInfo


class GraphNode(ContractModel):
    id: UUID
    namespace: Namespace
    type: str
    key: str
    label: str
    aggregate: bool
    member_count: int | None = Field(default=None, ge=1)
    confidence: float | None = Field(default=None, ge=0, le=1)
    structural_status: Literal[
        "STRUCTURALLY_CRITICAL", "ELEVATED", "TYPICAL", "WAITING_FOR_DATA",
    ] | None = None
    systemic_risk: float | None = Field(default=None, ge=0, le=1)
    community_key: str | None = None


class GraphEdge(ContractModel):
    id: UUID
    source: UUID
    target: UUID
    predicate: str
    confidence: float = Field(ge=0, le=1)
    assertion_class: Literal["DECLARED", "OBSERVED", "INFERRED", "CURATED", "EXTERNAL_MEASURED"]
    review_state: Literal["CONFIRMED", "POSSIBLE", "REJECTED", "NOT_APPLICABLE"]
    citation_fact_ids: list[UUID] = Field(min_length=1)
    is_bridge: bool | None = None


class GraphNeighborhood(ContractModel):
    contract_version: Literal["1.0.0"] = "1.0.0"
    center_id: UUID
    nodes: list[GraphNode] = Field(max_length=50)
    edges: list[GraphEdge]
    highlighted_path: list[UUID] | None = None
    truncated: bool
    truncation_reason: str | None = None


class Extractor(ContractModel):
    key: str = Field(min_length=1)
    version: str = Field(min_length=1)


class EvidenceDetail(ContractModel):
    contract_version: Literal["1.0.0"] = "1.0.0"
    fact_id: UUID
    assertion_class: Literal["DECLARED", "OBSERVED", "INFERRED", "CURATED", "EXTERNAL_MEASURED"]
    confidence: float = Field(ge=0, le=1)
    predicate: str
    source_revision: str
    extractor: Extractor
    properties: dict[str, Any] | None = None
    evidence: list[dict[str, Any]] = Field(min_length=1)
    observed_at: datetime
    effective_at: datetime | None = None
    closed_at: datetime | None = None


class AskRequest(ContractModel):
    question: str = Field(min_length=1, max_length=4000)
    context_entity_ids: list[UUID] | None = Field(default=None, max_length=20)


class ResolvedEntity(ContractModel):
    entity: EntitySummary
    score: float = Field(ge=-1,le=1)
    matched_terms: list[str] = Field(default_factory=list)


class AskResponse(ContractModel):
    contract_version: Literal["1.0.0"] = "1.0.0"
    text: str = Field(min_length=1)
    citations: list[Citation]
    result_kind: Literal["ANSWER", "TABLE", "GRAPH", "UNSUPPORTED"]
    rows: list[dict[str, Any]] | None = None
    graph_highlight: GraphNeighborhood | None = None
    resolved_entities: list[ResolvedEntity] = Field(default_factory=list)


EnterpriseInsightCategory = Literal[
    "ENTERPRISE_RISK", "TECHNOLOGY_RATIONALIZATION", "PORTFOLIO_DECISIONS",
]
EnterpriseInsightStatus = Literal[
    "ACTION_REQUIRED", "WATCH", "HEALTHY", "WAITING_FOR_DATA",
]


class EnterpriseInsightReport(ContractModel):
    key: str = Field(min_length=1)
    title: str = Field(min_length=1)
    category: EnterpriseInsightCategory
    question: str = Field(min_length=1)
    metric_value: str = Field(min_length=1)
    metric_label: str = Field(min_length=1)
    status: EnterpriseInsightStatus
    answerable: bool
    confidence: float | None = Field(default=None, ge=0, le=1)
    evidence_count: int = Field(ge=0)
    summary: str = Field(min_length=1)
    response: AskResponse


class EnterpriseInsightReportList(ContractModel):
    contract_version: Literal["1.0.0"] = "1.0.0"
    method_version: str = Field(min_length=1)
    evaluated_at: datetime
    answerable_reports: int = Field(ge=0)
    total_reports: int = Field(ge=1)
    reports: list[EnterpriseInsightReport] = Field(min_length=1)


class IdentityReviewRequest(ContractModel):
    decision: Literal["CONFIRM", "REJECT"]
    rationale: str = Field(min_length=1)
    expected_version: int = Field(ge=1)


class IdentityReviewResult(ContractModel):
    contract_version: Literal["1.0.0"] = "1.0.0"
    identity_assertion_id: UUID
    review_state: Literal["CONFIRMED", "REJECTED"]
    version: int = Field(ge=2)
    reviewed_at: datetime


class CapabilityDefinitionModel(ContractModel):
    key: str = Field(min_length=2)
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    parent_key: str | None = None
    aliases: list[str] = Field(default_factory=list)


class CapabilityTaxonomyResponse(ContractModel):
    contract_version: Literal["1.0.0"] = "1.0.0"
    key: str = Field(min_length=3)
    version: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    content_hash: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    capabilities: list[CapabilityDefinitionModel] = Field(min_length=1)


class CapabilityInferenceSummary(ContractModel):
    id: UUID
    subject: EntitySummary
    capability: CapabilityDefinitionModel
    source_revision: str = Field(min_length=1)
    assertion_class: Literal["CURATED", "INFERRED"]
    confidence: float = Field(ge=0, le=1)
    confidence_band: ConfidenceLabel
    supporting_fact_ids: list[UUID] = Field(min_length=1)
    counter_evidence_fact_ids: list[UUID]
    taxonomy_key: str
    taxonomy_version: str
    analyzer: Extractor
    model_provider: str | None = None
    model_name: str | None = None
    policy_version: str
    rationale: str = Field(min_length=1)
    review_state: Literal["UNREVIEWED", "CONFIRMED", "REJECTED"]
    version: int = Field(ge=1)
    stale: bool
    created_at: datetime


class DuplicateCapabilityCandidateSummary(ContractModel):
    id: UUID
    capability: CapabilityDefinitionModel
    source_revision: str = Field(min_length=1)
    dependencies: list[EntitySummary] = Field(min_length=2)
    capability_inference_ids: list[UUID] = Field(min_length=2)
    supporting_fact_ids: list[UUID] = Field(min_length=2)
    confidence: float = Field(ge=0, le=1)
    summary: str = Field(min_length=1)
    limitations: list[str] = Field(min_length=1)
    review_state: Literal["UNREVIEWED", "CONFIRMED", "REJECTED"]
    version: int = Field(ge=1)
    stale: bool


class RepositoryCapabilityIntelligence(ContractModel):
    contract_version: Literal["1.0.0"] = "1.0.0"
    repository: EntitySummary
    taxonomy_key: str | None = None
    taxonomy_version: str | None = None
    inferences: list[CapabilityInferenceSummary]
    duplicate_candidates: list[DuplicateCapabilityCandidateSummary]


class CapabilityInferenceReviewRequest(ContractModel):
    decision: Literal["CONFIRM", "REJECT"]
    rationale: str = Field(min_length=1)
    expected_version: int = Field(ge=1)


class CapabilityInferenceReviewResult(ContractModel):
    contract_version: Literal["1.0.0"] = "1.0.0"
    capability_inference_id: UUID
    review_state: Literal["CONFIRMED", "REJECTED"]
    version: int = Field(ge=2)
    reviewed_at: datetime


class DuplicateCapabilityReviewRequest(ContractModel):
    decision: Literal["CONFIRM", "REJECT"]
    rationale: str = Field(min_length=1)
    expected_version: int = Field(ge=1)


class DuplicateCapabilityReviewResult(ContractModel):
    contract_version: Literal["1.0.0"] = "1.0.0"
    duplicate_capability_candidate_id: UUID
    review_state: Literal["CONFIRMED", "REJECTED"]
    version: int = Field(ge=2)
    reviewed_at: datetime


class ModernizationOptionEligibilityModel(ContractModel):
    capability_fit: Literal["PASS", "FAIL", "UNKNOWN"]
    api_fit: Literal["PASS", "FAIL", "UNKNOWN"]
    behavior_fit: Literal["PASS", "FAIL", "UNKNOWN"]
    runtime_fit: Literal["PASS", "FAIL", "UNKNOWN"]
    license_fit: Literal["PASS", "FAIL", "UNKNOWN"]
    security_fit: Literal["PASS", "FAIL", "UNKNOWN"]
    policy_fit: Literal["PASS", "FAIL", "UNKNOWN"]
    eligible: bool
    evidence: dict[str, Any]
    disqualifiers: list[str]
    unknowns: list[str]


class ModernizationOptionModel(ContractModel):
    id: UUID
    kind: Literal["NATIVE", "INTERNAL", "UPGRADE", "PACKAGE"]
    canonical_key: str = Field(min_length=1)
    name: str = Field(min_length=1)
    target_entity: EntitySummary | None = None
    compatibility: Literal["OBSERVED", "COMPATIBLE", "UNKNOWN", "INCOMPATIBLE"]
    rank: int = Field(ge=1)
    score: float = Field(ge=0, le=1)
    score_components: dict[str, float]
    rationale: str = Field(min_length=1)
    tradeoffs: list[str]
    disqualifiers: list[str]
    validation_gaps: list[str]
    supporting_fact_ids: list[UUID]
    eligibility: ModernizationOptionEligibilityModel | None = None


class ModernizationImpactModel(ContractModel):
    affected_call_sites: int = Field(ge=0)
    affected_files: int = Field(ge=0)
    covered_call_sites: int = Field(ge=0)
    uncovered_call_sites: int = Field(ge=0)
    affected_test_files: list[str]
    dynamic_signals: list[str]
    configuration_touchpoints: list[dict[str, Any]]
    build_touchpoints: list[dict[str, Any]]
    deployment_touchpoints: list[dict[str, Any]]
    evidence_locations: list[dict[str, Any]]
    confidence: float = Field(ge=0, le=1)
    effort_points: int = Field(ge=0)
    effort_model_version: str = Field(min_length=1)
    limitations: list[str]


class ModernizationRecommendationModel(ContractModel):
    id: UUID
    selected_option_id: UUID | None = None
    action: Literal["CONSOLIDATE", "REPLACE", "UPGRADE", "REFACTOR", "INVESTIGATE"]
    objective: str = Field(min_length=1)
    title: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)
    estimated_effort: Literal["LOW", "MEDIUM", "HIGH", "UNKNOWN"]
    affected_call_sites: int = Field(ge=0)
    affected_files: int = Field(ge=0)
    validation_gaps: list[str]
    migration_plan: list[str] = Field(min_length=1)
    rollback_plan: list[str] = Field(min_length=1)
    supporting_fact_ids: list[UUID] = Field(min_length=1)
    counter_evidence_fact_ids: list[UUID]
    counter_signals: list[str]
    policy_version: str = Field(min_length=1)
    review_state: Literal["UNREVIEWED", "ACCEPTED", "REJECTED", "DISMISSED"]
    version: int = Field(ge=1)
    stale: bool
    created_at: datetime
    proposed_change_set_id: UUID | None = None
    simulation_eligibility: Literal["ELIGIBLE", "NOT_SIMULATABLE", "UNKNOWN"] = "UNKNOWN"
    not_simulatable_reason: dict[str, Any] | None = None


class ModernizationCandidateModel(ContractModel):
    id: UUID
    source_revision: str = Field(min_length=1)
    capability: CapabilityDefinitionModel | None = None
    kind: Literal[
        "DEPENDENCY_CONSOLIDATION", "INTERNAL_DUPLICATION",
        "VENDORED_DUPLICATION", "NATIVE_REPLACEMENT",
    ]
    subjects: list[EntitySummary] = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)
    summary: str = Field(min_length=1)
    supporting_fact_ids: list[UUID] = Field(min_length=1)
    counter_evidence_fact_ids: list[UUID]
    source_locations: list[dict[str, Any]]
    validation_gaps: list[str]
    analyzer: Extractor
    review_state: Literal["UNREVIEWED", "CONFIRMED", "REJECTED"]
    version: int = Field(ge=1)
    stale: bool
    options: list[ModernizationOptionModel]
    recommendation: ModernizationRecommendationModel | None = None
    impact: ModernizationImpactModel | None = None


class RepositoryModernizationIntelligence(ContractModel):
    contract_version: Literal["1.0.0"] = "1.0.0"
    repository: EntitySummary
    source_revision: str | None = None
    candidates: list[ModernizationCandidateModel]
    truncated: bool


class ModernizationCandidateReviewRequest(ContractModel):
    decision: Literal["CONFIRM", "REJECT"]
    rationale: str = Field(min_length=1)
    expected_version: int = Field(ge=1)


class ModernizationCandidateReviewResult(ContractModel):
    contract_version: Literal["1.0.0"] = "1.0.0"
    modernization_candidate_id: UUID
    review_state: Literal["CONFIRMED", "REJECTED"]
    version: int = Field(ge=2)
    reviewed_at: datetime


class ModernizationRecommendationReviewRequest(ContractModel):
    decision: Literal["ACCEPT", "REJECT", "DISMISS"]
    rationale: str = Field(min_length=1)
    expected_version: int = Field(ge=1)


class ModernizationRecommendationReviewResult(ContractModel):
    contract_version: Literal["1.0.0"] = "1.0.0"
    modernization_recommendation_id: UUID
    review_state: Literal["ACCEPTED", "REJECTED", "DISMISSED"]
    version: int = Field(ge=2)
    reviewed_at: datetime


class ModernizationValidationOutcomeRequest(ContractModel):
    validation_status: Literal["SUCCEEDED", "PARTIAL", "FAILED"]
    actual_call_sites: int | None = Field(default=None, ge=0)
    actual_files: int | None = Field(default=None, ge=0)
    actual_effort: Literal["LOW", "MEDIUM", "HIGH", "UNKNOWN"] | None = None
    successful_checks: list[str] = Field(default_factory=list)
    failed_checks: list[str] = Field(default_factory=list)
    notes: str = Field(min_length=1)


class ModernizationValidationOutcomeResult(ContractModel):
    contract_version: Literal["1.0.0"] = "1.0.0"
    id: UUID
    modernization_recommendation_id: UUID
    validation_status: Literal["SUCCEEDED", "PARTIAL", "FAILED"]
    reported_at: datetime


class Phase3IntelligenceMetrics(ContractModel):
    contract_version: Literal["1.0.0"] = "1.0.0"
    as_of: datetime
    candidate_counts: dict[str, int]
    recommendation_counts: dict[str, int]
    job_counts: dict[str, int]
    candidate_review_precision: float | None = Field(default=None, ge=0, le=1)
    recommendation_acceptance_rate: float | None = Field(default=None, ge=0, le=1)
    successful_validation_rate: float | None = Field(default=None, ge=0, le=1)
    affected_call_site_mae: float | None = Field(default=None, ge=0)
    affected_files_mae: float | None = Field(default=None, ge=0)
    effort_band_accuracy: float | None = Field(default=None, ge=0, le=1)
    evidence_completeness_rate: float | None = Field(default=None, ge=0, le=1)
    queue_lag_seconds_p50: float | None = Field(default=None, ge=0)
    queue_lag_seconds_p95: float | None = Field(default=None, ge=0)
    job_latency_ms_p50: float | None = Field(default=None, ge=0)
    job_latency_ms_p95: float | None = Field(default=None, ge=0)
    retry_count: int = Field(ge=0)
    dead_letter_count: int = Field(ge=0)
    stale_candidate_count: int = Field(ge=0)
    stale_recommendation_count: int = Field(ge=0)
    model_invocation_count: int = Field(ge=0)
    model_cost_usd: float = Field(ge=0)
    model_latency_ms_p95: float | None = Field(default=None, ge=0)


class ModernizationPolicyPublishRequest(ContractModel):
    policy_key: str = Field(default="modernization.default", pattern=r"^[a-z][a-z0-9_.-]{2,127}$")
    version: str = Field(min_length=1)
    runtime_versions: dict[str, str] = Field(default_factory=dict)
    allowed_licenses: list[str] = Field(default_factory=list)
    denied_option_keys: list[str] = Field(default_factory=list)
    allowed_security_statuses: list[Literal["CLEAR", "WARN", "BLOCKED", "UNKNOWN"]] = Field(
        default_factory=lambda: ["CLEAR", "UNKNOWN"]
    )
    required_policy_tags: list[str] = Field(default_factory=list)


class ModernizationPolicySummary(ContractModel):
    id: UUID
    policy_key: str
    version: str
    status: Literal["DRAFT", "ACTIVE", "RETIRED"]
    runtime_versions: dict[str, str]
    allowed_licenses: list[str]
    denied_option_keys: list[str]
    allowed_security_statuses: list[str]
    required_policy_tags: list[str]
    configuration_fingerprint: str
    activated_by: str
    activated_at: datetime


class InternalCatalogComponentUpsertRequest(ContractModel):
    component_entity_id: UUID
    capability_definition_id: UUID
    version: str = Field(min_length=1)
    status: Literal["APPROVED", "DEPRECATED", "BLOCKED"] = "APPROVED"
    api_symbols: list[str] = Field(default_factory=list)
    runtime_constraints: dict[str, str] = Field(default_factory=dict)
    behavior_claims: list[dict[str, Any]] = Field(default_factory=list)
    license: str | None = None
    security_status: Literal["CLEAR", "WARN", "BLOCKED", "UNKNOWN"] = "UNKNOWN"
    policy_tags: list[str] = Field(default_factory=list)
    supporting_fact_ids: list[UUID] = Field(min_length=1)
    owner: str = Field(min_length=1)
    decision: Literal["APPROVE", "REJECT"]


class InternalCatalogComponentSummary(ContractModel):
    id: UUID
    component_key: str
    version: str
    name: str
    status: Literal["APPROVED", "DEPRECATED", "BLOCKED"]
    review_state: Literal["UNREVIEWED", "APPROVED", "REJECTED"]
    owner: str | None = None
    catalog_fingerprint: str
    supporting_fact_ids: list[UUID]
    governed_by: str | None = None
    governed_at: datetime | None = None


class InternalCatalogCandidateSummary(ContractModel):
    candidate_id: UUID
    component_entity_id: UUID
    component_key: str
    name: str
    repository_name: str
    capability_definition_id: UUID
    capability: str
    confidence: float = Field(ge=0, le=1)
    affected_call_sites: int = Field(ge=0)
    affected_files: int = Field(ge=0)
    supporting_fact_ids: list[UUID] = Field(min_length=1)


class CalibrationCorpusPublishRequest(ContractModel):
    corpus_key: str = Field(default="modernization.pilot", pattern=r"^[a-z][a-z0-9_.-]{2,127}$")
    version: str = Field(min_length=1)
    case_fingerprints: list[str] = Field(min_length=1)
    minimum_candidate_precision: float = Field(default=0.8, ge=0, le=1)
    minimum_recommendation_acceptance: float = Field(default=0.5, ge=0, le=1)
    minimum_validation_success: float = Field(default=0.8, ge=0, le=1)
    maximum_affected_scope_mae: float = Field(default=0.25, ge=0)
    minimum_effort_accuracy: float = Field(default=0.7, ge=0, le=1)
    minimum_reviewed_cases: int = Field(default=20, ge=1)


class CalibrationObservedMetrics(ContractModel):
    candidate_precision: float | None = Field(default=None, ge=0, le=1)
    recommendation_acceptance: float | None = Field(default=None, ge=0, le=1)
    validation_success: float | None = Field(default=None, ge=0, le=1)
    affected_scope_mae: float | None = Field(default=None, ge=0)
    effort_accuracy: float | None = Field(default=None, ge=0, le=1)
    reviewed_cases: int = Field(ge=0)


class CalibrationCorpusSummary(ContractModel):
    id: UUID
    corpus_key: str
    version: str
    case_count: int = Field(ge=0)
    corpus_fingerprint: str
    observed_metrics: CalibrationObservedMetrics
    metrics_source_version: str
    promotion_passed: bool
    promotion_failures: list[str]
    evaluation_fingerprint: str
    evaluated_at: datetime


EcosystemName = Literal["PYPI", "MAVEN", "CARGO", "NUGET"]


class EcosystemAdmissionEvaluateRequest(ContractModel):
    minimum_repositories: int = Field(default=10, ge=1, le=100_000)
    minimum_dependency_share: float = Field(default=0.02, ge=0, le=1)


class EcosystemAdmissionSummary(ContractModel):
    ecosystem: EcosystemName
    sequence: int = Field(ge=1, le=4)
    status: Literal["NOT_EVALUATED", "PROPOSED", "ADMITTED", "RETIRED", "STALE"]
    observed_repositories: int = Field(ge=0)
    observed_dependency_share: float = Field(ge=0, le=1)
    minimum_repositories: int = Field(ge=1)
    minimum_dependency_share: float = Field(ge=0, le=1)
    predecessor_admitted: bool
    metadata_parity: bool
    calibration_gate_passed: bool
    reasons: list[str]
    decision_fingerprint: str
    decided_by: str | None = None
    decided_at: datetime | None = None


class ModernizationGovernanceState(ContractModel):
    contract_version: Literal["1.0.0"] = "1.0.0"
    active_policy: ModernizationPolicySummary | None = None
    internal_components: list[InternalCatalogComponentSummary]
    internal_component_candidates: list[InternalCatalogCandidateSummary] = Field(default_factory=list)
    active_calibration: CalibrationCorpusSummary | None = None
    ecosystem_admissions: list[EcosystemAdmissionSummary]


class DeterministicInsightRuleUpdateRequest(ContractModel):
    enabled: bool
    severity: InsightSeverity
    minimum_repositories: int = Field(default=1, ge=1, le=100_000)
    configuration: dict[str, Any] = Field(default_factory=dict)
    expected_version: int = Field(default=0, ge=0)


class DeterministicInsightRuleSummary(ContractModel):
    rule_key: str
    name: str
    description: str
    phase: Literal[1, 2, 3]
    readiness: Literal["ACTIVE", "NEEDS_DATA"]
    enabled: bool
    severity: InsightSeverity
    minimum_repositories: int = Field(ge=1)
    configuration: dict[str, Any]
    version: int = Field(ge=0)
    finding_count: int = Field(ge=0)
    missing_inputs: list[str]
    updated_by: str | None = None
    updated_at: datetime | None = None


class DeterministicInsightGovernanceState(ContractModel):
    contract_version: Literal["1.0.0"] = "1.0.0"
    method_version: str
    rules: list[DeterministicInsightRuleSummary]
    active_rule_count: int = Field(ge=0)
    needs_data_rule_count: int = Field(ge=0)
    finding_count: int = Field(ge=0)
    evidence_coverage: float = Field(ge=0, le=1)
    last_evaluated_at: datetime


# --- Tenant code-policy governance ---------------------------------------

CodeFunctionSource = Literal["PRIMARY", "CUSTOM"]
CodeFunctionStatus = Literal["ACTIVE", "RETIRED"]


class CodePolicyTechnologySummary(ContractModel):
    technology: EntitySummary
    classification: TechnologyClassification
    domain_key: str | None = None
    category_key: str | None = None
    detected_repository_count: int = Field(ge=0)


class TenantCodeFunctionPolicySummary(ContractModel):
    id: UUID
    allowed_technology_ids: list[UUID]
    prohibited_technology_ids: list[UUID]
    policy_fingerprint: str
    updated_by: str
    updated_at: datetime


class TenantCodeFunctionSummary(ContractModel):
    function_key: str
    name: str
    description: str
    domain_key: str
    source: CodeFunctionSource
    status: CodeFunctionStatus
    policy: TenantCodeFunctionPolicySummary | None = None


class TenantCodeFunctionUpsertRequest(ContractModel):
    source: CodeFunctionSource
    name: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=4000)
    domain_key: str = Field(pattern=r"^[a-z][a-z0-9.-]{1,127}$")
    status: CodeFunctionStatus = "ACTIVE"
    allowed_technology_ids: list[UUID] = Field(default_factory=list, max_length=2000)
    prohibited_technology_ids: list[UUID] = Field(default_factory=list, max_length=2000)

    @model_validator(mode="after")
    def technology_decisions_do_not_overlap(self) -> TenantCodeFunctionUpsertRequest:
        overlap = set(self.allowed_technology_ids) & set(self.prohibited_technology_ids)
        if overlap:
            raise ValueError("a technology cannot be both allowed and prohibited")
        return self


class CodePolicyViolation(ContractModel):
    rule: Literal["PROHIBITED", "NOT_ALLOWED"]
    function_key: str
    function_name: str
    technology: EntitySummary
    matched_technology_id: UUID
    fact_ids: list[UUID] = Field(min_length=1)
    message: str


class RepositoryCodePolicyEvaluation(ContractModel):
    id: UUID
    repository: EntitySummary
    status: Literal["COMPLIANT", "MISALIGNED", "UNASSESSED", "STALE"]
    violations: list[CodePolicyViolation]
    unclassified_technologies: list[EntitySummary]
    policy_set_fingerprint: str
    evidence_fingerprint: str
    evaluated_by: str
    evaluated_at: datetime


class TenantCodePolicySummary(ContractModel):
    governed_functions: int = Field(ge=0)
    custom_functions: int = Field(ge=0)
    evaluated_repositories: int = Field(ge=0)
    compliant_repositories: int = Field(ge=0)
    misaligned_repositories: int = Field(ge=0)
    stale_repositories: int = Field(ge=0)


class TenantCodePolicyState(ContractModel):
    contract_version: Literal["1.0.0"] = "1.0.0"
    policy_set_fingerprint: str
    functions: list[TenantCodeFunctionSummary]
    available_technologies: list[CodePolicyTechnologySummary]
    technology_catalog_truncated: bool = False
    evaluations: list[RepositoryCodePolicyEvaluation]
    summary: TenantCodePolicySummary


class CapabilityFootprintModel(ContractModel):
    capability: EntitySummary
    application_count: int = Field(ge=0)
    repository_count: int = Field(ge=0)
    technology_count: int = Field(ge=0)
    technology_counts: dict[str, int]
    technology_entropy: float = Field(ge=0, le=1)
    reuse_signal: float = Field(ge=0, le=1)


class CapabilityFootprintList(ContractModel):
    contract_version: Literal["1.0.0"] = "1.0.0"
    as_of: datetime
    footprints: list[CapabilityFootprintModel]


# --- Architecture canvas -------------------------------------------------

ArchitectureDomainKey = Literal[
    "experience", "application", "integration", "data", "platform", "delivery",
]
ArchitectureProfileStatus = Literal["DRAFT", "ACTIVE", "ARCHIVED"]
CanvasProjectionScope = Literal["ESTATE", "APPLICATION", "REPOSITORY", "TARGET"]
CanvasCellState = Literal[
    "POPULATED", "EMPTY", "NOT_APPLICABLE", "UNOBSERVED", "UNBOUND",
]
CellApplicability = Literal["REQUIRED", "RECOMMENDED", "OPTIONAL", "NOT_APPLICABLE"]
CanvasPolicyStatus = Literal[
    "PREFERRED", "ALLOWED", "DISCOURAGED", "PROHIBITED", "EXEMPTED", "UNGOVERNED",
]
MeasureStatus = Literal[
    "ELIGIBLE", "INSUFFICIENT_DATA", "NOT_APPLICABLE", "NOT_CONFIGURED",
]


class ArchitectureDomainModel(ContractModel):
    key: ArchitectureDomainKey
    label: str = Field(min_length=1)
    definition: str = Field(min_length=1)
    question: str = Field(min_length=1)
    order: int = Field(ge=0)


class ArchitectureConcernModel(ContractModel):
    key: str = Field(pattern=r"^[a-z][a-z0-9.-]{1,127}$")
    domain_key: ArchitectureDomainKey
    label: str = Field(min_length=1)
    definition: str = Field(min_length=1)
    order: int = Field(ge=0)


class ArchitectureCapabilityModel(ContractModel):
    key: str = Field(pattern=r"^[a-z][a-z0-9.-]{1,127}$")
    concern_key: str = Field(pattern=r"^[a-z][a-z0-9.-]{1,127}$")
    name: str = Field(min_length=1)
    definition: str = Field(min_length=1)
    aliases: list[str] = Field(default_factory=list)


class ArchitectureAspectModel(ContractModel):
    key: str = Field(pattern=r"^[a-z][a-z0-9.-]{1,127}$")
    label: str = Field(min_length=1)
    definition: str = Field(min_length=1)


class ArchitectureTaxonomyResponse(ContractModel):
    contract_version: Literal["1.0.0"] = "1.0.0"
    key: str = Field(min_length=1)
    version: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    content_hash: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    domains: list[ArchitectureDomainModel] = Field(min_length=1)
    concerns: list[ArchitectureConcernModel] = Field(min_length=1)
    capabilities: list[ArchitectureCapabilityModel] = Field(min_length=1)
    aspects: list[ArchitectureAspectModel]


class CanvasBindingModel(ContractModel):
    kind: Literal[
        "CAPABILITY", "CATEGORY", "RESOURCE_KIND", "ENTITY_TYPE",
        "ARCHITECTURE_ROLE", "UNBOUND",
    ]
    keys: list[str] = Field(default_factory=list)
    reason: str | None = None

    @model_validator(mode="after")
    def binding_shape_is_valid(self) -> "CanvasBindingModel":
        if self.kind == "UNBOUND":
            if self.keys or not self.reason:
                raise ValueError("an UNBOUND binding requires a reason and no keys")
        elif not self.keys or self.reason is not None:
            raise ValueError("a bound binding requires keys and no reason")
        return self


class CellExpectationModel(ContractModel):
    applicability: CellApplicability = "OPTIONAL"
    minimum_implementations: int | None = Field(default=None, ge=0)
    maximum_implementations: int | None = Field(default=None, ge=0)
    allowed_diversity: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def cardinality_is_ordered(self) -> "CellExpectationModel":
        if (
            self.minimum_implementations is not None
            and self.maximum_implementations is not None
            and self.minimum_implementations > self.maximum_implementations
        ):
            raise ValueError("minimum_implementations cannot exceed maximum_implementations")
        if self.applicability == "NOT_APPLICABLE" and any(
            value not in (None, 0)
            for value in (self.minimum_implementations, self.maximum_implementations)
        ):
            raise ValueError("NOT_APPLICABLE expectations cannot require implementations")
        return self


class ArchitectureCellDefinitionModel(ContractModel):
    key: str = Field(pattern=r"^cell\.[a-z][a-z0-9.-]{1,127}$")
    concern_key: str = Field(pattern=r"^[a-z][a-z0-9.-]{1,127}$")
    label: str = Field(min_length=1)
    definition: str = Field(min_length=1, max_length=500)
    bindings: list[CanvasBindingModel] = Field(min_length=1)
    aspect_keys: list[str] = Field(default_factory=list)
    default_expectation: CellExpectationModel
    observation_rule_key: str = Field(min_length=1)
    required_sensor_kinds: list[str] = Field(min_length=1)
    absence_assertable: bool = False


class ArchitectureReferenceModel(ContractModel):
    contract_version: Literal["1.0.0"] = "1.0.0"
    key: str = Field(min_length=1)
    version: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    taxonomy_key: str = Field(min_length=1)
    taxonomy_version: str = Field(min_length=1)
    taxonomy_content_hash: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    content_hash: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    cells: list[ArchitectureCellDefinitionModel] = Field(min_length=1)


class ArchitectureReferenceModelList(ContractModel):
    contract_version: Literal["1.0.0"] = "1.0.0"
    models: list[ArchitectureReferenceModel]


class CanvasCellLayoutModel(ContractModel):
    cell_key: str = Field(pattern=r"^cell\.[a-z][a-z0-9.-]{1,127}$")
    span: Literal[1, 2, 3] = 1


class CanvasBandLayoutModel(ContractModel):
    domain_key: ArchitectureDomainKey
    order: int = Field(ge=0)
    columns: int = Field(ge=1, le=8)
    cells: list[CanvasCellLayoutModel] = Field(min_length=1)


class CanvasTemplateModel(ContractModel):
    contract_version: Literal["1.0.0"] = "1.0.0"
    key: str = Field(min_length=1)
    version: str = Field(min_length=1)
    name: str = Field(min_length=1)
    reference_model_key: str = Field(min_length=1)
    reference_model_version: str = Field(min_length=1)
    content_hash: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    bands: list[CanvasBandLayoutModel] = Field(min_length=1)


class CanvasTemplateList(ContractModel):
    contract_version: Literal["1.0.0"] = "1.0.0"
    templates: list[CanvasTemplateModel]


class CanvasScopeSelectorModel(ContractModel):
    application_ids: list[UUID] = Field(default_factory=list)
    repository_ids: list[UUID] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class CanvasPolicyExceptionModel(ContractModel):
    key: str = Field(min_length=1, max_length=128)
    rationale: str = Field(min_length=1, max_length=2000)
    subject_ids: list[UUID] = Field(min_length=1)
    effective_from: datetime | None = None
    effective_to: datetime | None = None

    @model_validator(mode="after")
    def exception_dates_are_ordered(self) -> "CanvasPolicyExceptionModel":
        if self.effective_from and self.effective_to and self.effective_from >= self.effective_to:
            raise ValueError("effective_from must precede effective_to")
        return self


class TenantCellPolicyModel(CellExpectationModel):
    cell_key: str = Field(pattern=r"^cell\.[a-z][a-z0-9.-]{1,127}$")
    scope_selector: CanvasScopeSelectorModel = Field(default_factory=CanvasScopeSelectorModel)
    preferred_technology_ids: list[UUID] = Field(default_factory=list, max_length=2000)
    allowed_technology_ids: list[UUID] = Field(default_factory=list, max_length=2000)
    discouraged_technology_ids: list[UUID] = Field(default_factory=list, max_length=2000)
    prohibited_technology_ids: list[UUID] = Field(default_factory=list, max_length=2000)
    rationale: str = Field(default="", max_length=4000)
    owner: str | None = Field(default=None, max_length=255)
    effective_from: datetime | None = None
    effective_to: datetime | None = None
    exceptions: list[CanvasPolicyExceptionModel] = Field(default_factory=list)

    @model_validator(mode="after")
    def technology_decisions_do_not_overlap(self) -> "TenantCellPolicyModel":
        decisions = (
            self.preferred_technology_ids,
            self.allowed_technology_ids,
            self.discouraged_technology_ids,
            self.prohibited_technology_ids,
        )
        seen: set[UUID] = set()
        for values in decisions:
            overlap = seen & set(values)
            if overlap:
                raise ValueError("a technology may have only one decision state per cell")
            seen.update(values)
        if self.effective_from and self.effective_to and self.effective_from >= self.effective_to:
            raise ValueError("effective_from must precede effective_to")
        return self


class TenantExtensionCellModel(ContractModel):
    key: str = Field(pattern=r"^tenant\.[a-z0-9][a-z0-9.-]{2,127}$")
    domain_key: ArchitectureDomainKey
    label: str = Field(min_length=1, max_length=255)
    definition: str = Field(min_length=1, max_length=500)
    bindings: list[CanvasBindingModel] = Field(min_length=1)
    aspect_keys: list[str] = Field(default_factory=list)
    default_expectation: CellExpectationModel


class ArchitectureProfileStateModel(ContractModel):
    name: str = Field(min_length=1, max_length=255)
    reference_model_key: str = Field(min_length=1)
    reference_model_version: str = Field(min_length=1)
    cell_policies: list[TenantCellPolicyModel] = Field(default_factory=list)
    extension_cells: list[TenantExtensionCellModel] = Field(default_factory=list)

    @model_validator(mode="after")
    def policy_and_extension_keys_are_unique(self) -> "ArchitectureProfileStateModel":
        policy_keys = [item.cell_key for item in self.cell_policies]
        extension_keys = [item.key for item in self.extension_cells]
        if len(policy_keys) != len(set(policy_keys)):
            raise ValueError("cell_policies contains duplicate cell keys")
        if len(extension_keys) != len(set(extension_keys)):
            raise ValueError("extension_cells contains duplicate keys")
        return self


class ArchitectureProfileCreateRequest(ContractModel):
    profile_key: str = Field(pattern=r"^[a-z][a-z0-9_.-]{2,127}$")
    state: ArchitectureProfileStateModel


class ArchitectureProfileUpdateRequest(ContractModel):
    expected_version: int = Field(ge=1)
    state: ArchitectureProfileStateModel


class ArchitectureProfilePublishRequest(ContractModel):
    expected_version: int = Field(ge=1)


class ArchitectureProfileSummary(ContractModel):
    id: UUID
    profile_key: str
    name: str
    reference_model_key: str
    reference_model_version: str
    version: int = Field(ge=1)
    status: ArchitectureProfileStatus
    fingerprint: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    created_at: datetime
    updated_at: datetime


class ArchitectureProfileDetail(ArchitectureProfileSummary):
    state: ArchitectureProfileStateModel


class ArchitectureProfileList(ContractModel):
    contract_version: Literal["1.0.0"] = "1.0.0"
    profiles: list[ArchitectureProfileSummary]


class CellObservationStatusModel(ContractModel):
    required_sensor_kinds: list[str]
    supported_sensor_kinds: list[str]
    in_scope_subjects: int = Field(ge=0)
    observed_subjects: int = Field(ge=0)
    fresh_subjects: int = Field(ge=0)
    status: Literal["COMPLETE", "PARTIAL", "MISSING", "NOT_APPLICABLE"]
    missing_inputs: list[str]
    method_version: str = Field(min_length=1)
    input_fingerprint: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")


class CanvasOccupantModel(ContractModel):
    technology: EntitySummary
    placement_keys: list[str] = Field(min_length=1)
    classification: TechnologyClassification
    confidence: float = Field(ge=0, le=1)
    confidence_label: ConfidenceLabel
    adoption_applications: int = Field(ge=0)
    adoption_repositories: int = Field(ge=0)
    adoption_deployments: int = Field(ge=0)
    policy_status: CanvasPolicyStatus
    citations: list[Citation] = Field(default_factory=list)
    policy_reference: str | None = None


class MeasureResultModel(ContractModel):
    value: float | None = Field(default=None, ge=0, le=100)
    status: MeasureStatus
    inputs: list[str]
    supporting_fact_ids: list[UUID]
    method_version: str = Field(min_length=1)


class CanvasCellMeasuresModel(ContractModel):
    posture_band: Literal["STRONG", "ADEQUATE", "WEAK", "AT_RISK"] | None = None
    overall_score: float | None = Field(default=None, ge=0, le=100)
    coverage: MeasureResultModel
    standardisation: MeasureResultModel
    currency: MeasureResultModel
    risk: MeasureResultModel
    conformance: MeasureResultModel
    confidence: float = Field(ge=0, le=1)
    confidence_label: ConfidenceLabel
    method_version: str = Field(min_length=1)
    missing_inputs: list[str]


class CanvasCellProjectionModel(ContractModel):
    cell_key: str
    state: CanvasCellState
    state_reason: str = Field(min_length=1)
    occupants: list[CanvasOccupantModel]
    occupant_total: int = Field(ge=0)
    unique_technology_total: int = Field(ge=0)
    observation: CellObservationStatusModel
    expectation: CellExpectationModel
    measures: CanvasCellMeasuresModel | None = None
    policy: TenantCellPolicyModel | None = None
    insight_refs: list[UUID]
    citations: list[Citation]


class CanvasClassificationTrayItemModel(ContractModel):
    entity: EntitySummary
    reason: Literal["UNCLASSIFIED", "AMBIGUOUS", "UNRESOLVED_POLICY", "FILTERED"]
    detail: str = Field(min_length=1)
    citations: list[Citation]


class CanvasClassificationTrayModel(ContractModel):
    items: list[CanvasClassificationTrayItemModel]
    total_count: int = Field(ge=0)
    truncated: bool
    unclassified_count: int = Field(ge=0)
    ambiguous_count: int = Field(ge=0)
    unresolved_policy_count: int = Field(ge=0)
    filtered_count: int = Field(ge=0)


class CanvasProjectionSummaryModel(ContractModel):
    populated_cells: int = Field(ge=0)
    empty_cells: int = Field(ge=0)
    not_applicable_cells: int = Field(ge=0)
    unobserved_cells: int = Field(ge=0)
    unbound_cells: int = Field(ge=0)
    governed_cells: int = Field(ge=0)
    cells_with_violations: int = Field(ge=0)
    strong: int = Field(ge=0)
    adequate: int = Field(ge=0)
    weak: int = Field(ge=0)
    at_risk: int = Field(ge=0)
    unique_technologies: int = Field(ge=0)
    technology_cell_placements: int = Field(ge=0)


class CanvasProjection(ContractModel):
    contract_version: Literal["1.0.0"] = "1.0.0"
    as_of: datetime
    method_version: str = Field(min_length=1)
    taxonomy_key: str
    taxonomy_version: str
    taxonomy_content_hash: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    reference_model_key: str
    reference_model_version: str
    reference_model_content_hash: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    template_key: str
    template_version: str
    tenant_profile_fingerprint: str | None = Field(
        default=None, pattern=r"^sha256:[a-f0-9]{64}$",
    )
    scope: CanvasProjectionScope
    subject: EntitySummary | None = None
    cells: list[CanvasCellProjectionModel]
    classification_tray: CanvasClassificationTrayModel
    summary: CanvasProjectionSummaryModel
    input_fingerprint: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")

    @model_validator(mode="after")
    def observed_occupants_are_cited(self) -> "CanvasProjection":
        if self.scope != "TARGET":
            for cell in self.cells:
                if cell.state == "POPULATED" and any(
                    not occupant.citations for occupant in cell.occupants
                ):
                    raise ValueError("every observed canvas occupant requires a citation")
        return self


class CanvasProjectionSelectorModel(ContractModel):
    scope: CanvasProjectionScope
    subject_id: UUID | None = None

    @model_validator(mode="after")
    def subject_matches_scope(self) -> "CanvasProjectionSelectorModel":
        if self.scope in {"APPLICATION", "REPOSITORY"} and self.subject_id is None:
            raise ValueError("APPLICATION and REPOSITORY selectors require subject_id")
        if self.scope in {"ESTATE", "TARGET"} and self.subject_id is not None:
            raise ValueError("ESTATE and TARGET selectors do not accept subject_id")
        return self


class CanvasComparisonRequest(ContractModel):
    comparison_kind: Literal["ACTUAL_TO_TARGET", "ACTUAL_TO_ACTUAL", "TIME_TO_TIME"]
    actual: CanvasProjectionSelectorModel
    baseline: CanvasProjectionSelectorModel
    reference_model_key: str = "architecture.stackgraph.reference"
    template_key: str = "canvas.stackgraph.reference"

    @model_validator(mode="after")
    def comparison_selectors_match_kind(self) -> "CanvasComparisonRequest":
        if self.comparison_kind == "ACTUAL_TO_TARGET" and self.baseline.scope != "TARGET":
            raise ValueError("ACTUAL_TO_TARGET comparisons require a TARGET baseline")
        if self.comparison_kind == "TIME_TO_TIME":
            raise ValueError("TIME_TO_TIME comparison is reserved until historical projections ship")
        return self


class CanvasCellComparisonModel(ContractModel):
    cell_key: str
    actual_state: CanvasCellState
    baseline_state: CanvasCellState
    preferred_in_use: int = Field(ge=0)
    allowed_in_use: int = Field(ge=0)
    discouraged_in_use: int = Field(ge=0)
    prohibited_in_use: int = Field(ge=0)
    required_but_absent: bool
    ungoverned_in_use: int = Field(ge=0)
    unevaluable: bool


class CanvasComparisonSummaryModel(ContractModel):
    compared_cells: int = Field(ge=0)
    aligned_cells: int = Field(ge=0)
    cells_with_violations: int = Field(ge=0)
    required_but_absent_cells: int = Field(ge=0)
    ungoverned_cells: int = Field(ge=0)
    unevaluable_cells: int = Field(ge=0)


class CanvasComparison(ContractModel):
    contract_version: Literal["1.0.0"] = "1.0.0"
    comparison_kind: Literal["ACTUAL_TO_TARGET", "ACTUAL_TO_ACTUAL"]
    actual_projection_fingerprint: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    baseline_projection_fingerprint: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    cells: list[CanvasCellComparisonModel]
    summary: CanvasComparisonSummaryModel
    method_version: str = Field(min_length=1)
    input_fingerprint: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")


class ModernizationScenarioRequest(ContractModel):
    budget_points: int = Field(ge=0, le=100000)
    excluded_recommendation_ids: list[UUID] = Field(default_factory=list)


class ModernizationScenarioItem(ContractModel):
    recommendation_id: UUID
    repository: EntitySummary
    title: str
    action: Literal["CONSOLIDATE", "REPLACE", "UPGRADE", "REFACTOR", "INVESTIGATE"]
    score: float = Field(ge=0, le=100)
    score_components: dict[str, float]
    effort_points: int = Field(ge=0)
    selected: bool
    policy_version: str


class ModernizationScenarioResult(ContractModel):
    contract_version: Literal["1.0.0"] = "1.0.0"
    as_of: datetime
    budget_points: int = Field(ge=0)
    used_points: int = Field(ge=0)
    total_score: float = Field(ge=0)
    items: list[ModernizationScenarioItem]


# --- Business Map -----------------------------------------------------------
# The contract mirrors the workspace's client state (kebab view modes, string keys as ids)
# so the UI serializes with a thin adapter and no reducer changes. The store maps these
# keys to the persisted UUIDs and the DB's uppercase enums.

MaturityLevel = Literal[1, 2, 3, 4, 5]
BusinessMapViewMode = Literal["value-chain", "organization"]
BusinessMapStatus = Literal["DRAFT", "ACTIVE", "ARCHIVED"]


class BusinessMapLane(ContractModel):
    id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    sublabel: str = ""
    color: str = ""
    gradient: str = ""
    icon: str = ""
    order: int = Field(ge=0)


class BusinessMapCapabilityNode(ContractModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    kpis: list[str] = Field(default_factory=list)
    owner: str | None = None
    criticality: MaturityLevel = 3


class BusinessMapProcessNode(ContractModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = ""
    capabilities: list[BusinessMapCapabilityNode] = Field(default_factory=list)


class BusinessMapFunctionNode(ContractModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = ""
    color: str = ""
    gradient: str = ""
    icon: str = ""
    processes: list[BusinessMapProcessNode] = Field(default_factory=list)


class BusinessMapPlacement(ContractModel):
    capability_id: str = Field(min_length=1)
    stage_id: str | None = None
    maturity: MaturityLevel
    source_function_id: str | None = None


class BusinessMapSharedGroup(ContractModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = ""
    capability_ids: list[str] = Field(default_factory=list)
    start_stage_id: str = Field(min_length=1)
    end_stage_id: str = Field(min_length=1)


class BusinessMapFunctionAssignment(ContractModel):
    function_id: str = Field(min_length=1)
    unit_id: str = Field(min_length=1)


class BusinessMapApplicationAssignment(ContractModel):
    capability_id: str = Field(min_length=1)
    application_id: UUID
    application_name: str = Field(min_length=1)


class BusinessMapStateModel(ContractModel):
    title: str = Field(min_length=1)
    view_mode: BusinessMapViewMode = "value-chain"
    template_id: str = Field(min_length=1)
    stages: list[BusinessMapLane] = Field(default_factory=list)
    organization_units: list[BusinessMapLane] = Field(default_factory=list)
    catalog: list[BusinessMapFunctionNode] = Field(default_factory=list)
    placements: list[BusinessMapPlacement] = Field(default_factory=list)
    shared_groups: list[BusinessMapSharedGroup] = Field(default_factory=list)
    function_assignments: list[BusinessMapFunctionAssignment] = Field(default_factory=list)
    application_assignments: list[BusinessMapApplicationAssignment] = Field(default_factory=list)


class BusinessMapSummary(ContractModel):
    id: UUID
    map_key: str = Field(min_length=1)
    title: str = Field(min_length=1)
    view_mode: BusinessMapViewMode
    template_id: str = Field(min_length=1)
    status: BusinessMapStatus
    version: int = Field(ge=1)
    created_at: datetime
    updated_at: datetime


class BusinessMapList(ContractModel):
    contract_version: Literal["1.0.0"] = "1.0.0"
    as_of: datetime
    maps: list[BusinessMapSummary]
    page_info: PageInfo


class BusinessMapDetail(ContractModel):
    contract_version: Literal["1.0.0"] = "1.0.0"
    id: UUID
    map_key: str = Field(min_length=1)
    status: BusinessMapStatus
    version: int = Field(ge=1)
    created_at: datetime
    updated_at: datetime
    state: BusinessMapStateModel


class BusinessMapCreateRequest(ContractModel):
    map_key: str = Field(pattern=r"^[a-z][a-z0-9_.-]{2,127}$")
    state: BusinessMapStateModel


class BusinessMapSaveRequest(ContractModel):
    expected_version: int = Field(ge=1)
    state: BusinessMapStateModel


class BusinessMapRevisionSummary(ContractModel):
    version: int = Field(ge=1)
    actor_key: str = Field(min_length=1)
    created_at: datetime


class BusinessMapRevisionList(ContractModel):
    contract_version: Literal["1.0.0"] = "1.0.0"
    business_map_id: UUID
    revisions: list[BusinessMapRevisionSummary]


# --- Review queue --------------------------------------------------------
# One normalized view over the five reviewable sources so the Reviews page can list every
# pending item across the estate without knowing each source's shape. Submission still goes
# to each source's own /review route (see `review_path`).

ReviewQueueItemType = Literal[
    "IDENTITY_ASSERTION",
    "CAPABILITY_INFERENCE",
    "DUPLICATE_CAPABILITY",
    "MODERNIZATION_CANDIDATE",
    "MODERNIZATION_RECOMMENDATION",
    "APPLICATION_SIMILARITY",
]


class ReviewQueueItem(ContractModel):
    item_id: UUID
    item_type: ReviewQueueItemType
    review_state: str = Field(min_length=1)
    title: str = Field(min_length=1)
    summary: str | None = None
    confidence: float = Field(ge=0, le=1)
    confidence_band: ConfidenceLabel
    repository_id: UUID | None = None
    version: int = Field(ge=1)
    created_at: datetime
    # The endpoint that accepts a decision for this item, e.g. "/identity-assertions/{id}/review".
    review_path: str = Field(min_length=1)


class ReviewQueue(ContractModel):
    contract_version: Literal["1.0.0"] = "1.0.0"
    as_of: datetime
    # Per-type pending totals for the whole tenant, independent of the type/repository/cursor
    # filters, so the UI's tab badges stay stable while a filtered page is shown.
    counts: dict[ReviewQueueItemType, int]
    items: list[ReviewQueueItem]
    page_info: PageInfo


# --- Admin: members & roles ---------------------------------------------

MemberRole = Literal["view", "review", "execute", "admin"]
MemberStatus = Literal["INVITED", "ACTIVE", "SUSPENDED"]


class TenantMember(ContractModel):
    id: UUID
    actor_key: str = Field(min_length=1)
    display_name: str = ""
    email: str = ""
    role: MemberRole
    status: MemberStatus
    created_at: datetime
    updated_at: datetime


class TenantMemberList(ContractModel):
    contract_version: Literal["1.0.0"] = "1.0.0"
    members: list[TenantMember]


class MemberInviteRequest(ContractModel):
    actor_key: str = Field(min_length=1, max_length=255)
    display_name: str = Field(default="", max_length=255)
    email: str = Field(default="", max_length=320)
    role: MemberRole = "view"


class MemberUpdateRequest(ContractModel):
    role: MemberRole | None = None
    status: MemberStatus | None = None

    @model_validator(mode="after")
    def _at_least_one_field(self) -> "MemberUpdateRequest":
        if self.role is None and self.status is None:
            raise ValueError("at least one of role or status is required")
        return self


# --- Admin: connectors ---------------------------------------------------

ConnectorProvider = Literal["GITHUB_APP", "PACKAGE_REGISTRY", "DEPS_DEV", "OSV", "OTHER"]
ConnectorStatus = Literal["CONNECTED", "NEEDS_REAUTH", "DISABLED", "REVOKED"]


class Connector(ContractModel):
    # A registered source/registry connection. The stored credential_reference is a secret-store
    # pointer and is deliberately never surfaced here.
    id: UUID
    provider: ConnectorProvider
    display_name: str = Field(min_length=1)
    external_account_key: str = ""
    scopes: list[str] = Field(default_factory=list)
    status: ConnectorStatus
    last_synced_at: datetime | None = None
    last_error: str | None = None
    created_at: datetime
    updated_at: datetime


class ConnectorList(ContractModel):
    contract_version: Literal["1.0.0"] = "1.0.0"
    connectors: list[Connector]


class ConnectorRegisterRequest(ContractModel):
    provider: ConnectorProvider
    display_name: str = Field(min_length=1, max_length=255)
    external_account_key: str = Field(default="", max_length=255)
    # An opaque reference into the secret store. A raw token/PAT/password is rejected.
    credential_reference: str = Field(default="", max_length=512)
    scopes: list[str] = Field(default_factory=list)


class GitHubRepositoryConnectRequest(ContractModel):
    """Register one repository for the self-hosted GitHub ingestion worker.

    The browser supplies repository identity only. The credential value remains in the
    worker environment and this contract stores only its reference.
    """

    repository: str = Field(
        min_length=3,
        max_length=201,
        pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$",
    )
    credential_reference: Literal["env://GITHUB_TOKEN"] = "env://GITHUB_TOKEN"


class GitHubRepositoryOption(ContractModel):
    full_name: str = Field(min_length=3, max_length=201)
    visibility: Literal["public", "private", "internal"]
    archived: bool = False
    default_branch: str | None = Field(default=None, max_length=255)


class GitHubRepositoryOptionList(ContractModel):
    contract_version: Literal["1.0.0"] = "1.0.0"
    token_configured: bool
    repositories: list[GitHubRepositoryOption]
    truncated: bool = False


class GitHubTokenConfiguration(ContractModel):
    """Write-only tenant GitHub token status.

    The token value is encrypted at rest and is never returned by the API.
    """

    contract_version: Literal["1.0.0"] = "1.0.0"
    configured: bool = False
    fingerprint: str | None = None
    source: Literal["TENANT_SECRET", "ENVIRONMENT", "NONE"] = "NONE"
    updated_by: str | None = None
    updated_at: datetime | None = None


class GitHubTokenUpdateRequest(ContractModel):
    token: str = Field(min_length=8, max_length=8192)


class GitHubInstallationConnectRequest(ContractModel):
    """Bind an already-authorized GitHub App installation to this tenant.

    The App private key and short-lived installation tokens remain in the deployment
    secret boundary. The browser supplies only GitHub's public installation identifier.
    """

    installation_id: str = Field(
        min_length=1,
        max_length=20,
        pattern=r"^[1-9][0-9]{0,19}$",
    )
    display_name: str | None = Field(default=None, min_length=1, max_length=255)
    pilot_manual_binding_acknowledged: Literal[True] = Field(
        description=(
            "Confirms that an operator verified the installation belongs to this pilot tenant; "
            "hosted setup callback binding remains required for general availability."
        )
    )


class GitHubInstallationSetupRequest(ContractModel):
    return_to: str = Field(default="/admin", min_length=1, max_length=1024)

    @model_validator(mode="after")
    def _safe_return_path(self) -> "GitHubInstallationSetupRequest":
        parsed = urlsplit(self.return_to)
        if (
            not self.return_to.startswith("/")
            or self.return_to.startswith("//")
            or parsed.scheme
            or parsed.netloc
            or "\\" in self.return_to
            or any(ord(character) < 32 for character in self.return_to)
        ):
            raise ValueError("return_to must be a safe absolute path")
        return self


class GitHubInstallationSetupResponse(ContractModel):
    setup_url: str
    expires_at: datetime


class ConnectorUpdateRequest(ContractModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=255)
    status: ConnectorStatus | None = None
    scopes: list[str] | None = None
    credential_reference: str | None = Field(default=None, max_length=512)

    @model_validator(mode="after")
    def _at_least_one_field(self) -> "ConnectorUpdateRequest":
        if (
            self.display_name is None
            and self.status is None
            and self.scopes is None
            and self.credential_reference is None
        ):
            raise ValueError("at least one field is required")
        return self


# --- Admin: AI provider configuration -----------------------------------

AIProvider = Literal["openrouter", "openai", "anthropic"]
AIConnectionTestStatus = Literal["NOT_TESTED", "SUCCEEDED", "FAILED"]
AIEnrichmentStatus = Literal["DISABLED", "READY", "QUEUED", "RUNNING", "ACTIVE", "DEGRADED"]


class AIProviderConfiguration(ContractModel):
    contract_version: Literal["1.0.0"] = "1.0.0"
    provider: AIProvider
    model: str = ""
    enabled: bool = True
    key_configured: bool = False
    key_fingerprint: str | None = None
    test_status: AIConnectionTestStatus = "NOT_TESTED"
    tested_at: datetime | None = None
    last_error: str | None = None
    enrichment_status: AIEnrichmentStatus = "DISABLED"
    pending_enrichment_jobs: int = Field(default=0, ge=0)
    running_enrichment_jobs: int = Field(default=0, ge=0)
    failed_enrichment_jobs: int = Field(default=0, ge=0)
    last_enrichment_at: datetime | None = None
    updated_by: str | None = None
    updated_at: datetime | None = None


class AIProviderConfigurationUpdateRequest(ContractModel):
    provider: AIProvider
    model: str = Field(default="", max_length=255)
    api_key: str | None = Field(default=None, min_length=8, max_length=8192)
    enabled: bool = True


class AIProviderConnectionTest(ContractModel):
    contract_version: Literal["1.0.0"] = "1.0.0"
    provider: AIProvider
    status: Literal["SUCCEEDED"] = "SUCCEEDED"
    models: list[str] = Field(default_factory=list)


# --- Admin: scan policy, rescans, and quota ------------------------------

ScanCadence = Literal["HOURLY", "DAILY", "WEEKLY", "MANUAL"]


class ScanPolicy(ContractModel):
    contract_version: Literal["1.0.0"] = "1.0.0"
    cadence: ScanCadence
    enabled: bool
    updated_by: str | None = None
    updated_at: datetime | None = None


class ScanPolicyUpdateRequest(ContractModel):
    cadence: ScanCadence
    enabled: bool = True


RescanJobStatus = Literal["PENDING", "RUNNING", "SUCCEEDED", "FAILED"]


class RescanRequest(ContractModel):
    # NULL connector_id (omitted) means a full-estate rescan. `idempotency_key` makes a repeated
    # POST return the existing job rather than enqueueing a duplicate.
    connector_id: UUID | None = None
    idempotency_key: str = Field(min_length=1, max_length=255)
    reason: str = Field(default="", max_length=1000)


class RescanJob(ContractModel):
    id: UUID
    connector_id: UUID | None = None
    status: RescanJobStatus
    reason: str = ""
    requested_by: str = Field(min_length=1)
    last_error: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None


class RescanJobList(ContractModel):
    contract_version: Literal["1.0.0"] = "1.0.0"
    jobs: list[RescanJob]
    page_info: PageInfo


class GraphAnalysisRequestCreate(ContractModel):
    policy_key: str = Field(default="runtime-dependency",pattern=r"^[a-z][a-z0-9-]{2,63}$")
    reason: str = Field(default="OPERATOR_REQUEST",min_length=1,max_length=500)


class GraphAnalysisRequestResult(ContractModel):
    id: UUID
    policy_key: str
    requested_change_watermark: int = Field(ge=0)
    status: Literal["PENDING","WAITING_FOR_PROJECTION"]
    created_at: datetime


class EmbeddingBackfillRequest(ContractModel):
    embedding_space_id: UUID | None = None
    entity_ids: list[UUID] = Field(default_factory=list,max_length=500)
    entity_types: list[str] = Field(default_factory=list,max_length=20)
    limit: int = Field(default=500,ge=1,le=500)


class EmbeddingBackfillResult(ContractModel):
    embedding_space_id: UUID
    queued_jobs: int = Field(ge=0)
    requested_at: datetime


class EmbeddingSpacePromotionRequest(ContractModel):
    action: Literal["PROMOTE","ROLLBACK"] = "PROMOTE"


class EmbeddingSpacePromotionResult(ContractModel):
    embedding_space_id: UUID
    space_kind: Literal["SEMANTIC_ENTITY","STRUCTURAL_GRAPH","CODE"]
    action: Literal["PROMOTE","ROLLBACK"]
    activated_at: datetime


QuotaStatus = Literal["OK", "THROTTLED", "EXHAUSTED"]


class ProviderQuota(ContractModel):
    provider: ConnectorProvider
    used: int = Field(ge=0)
    limit: int | None = Field(default=None, ge=0)
    status: QuotaStatus
    resets_at: datetime | None = None
    backoff_until: datetime | None = None
    observed_at: datetime


class ScanStatus(ContractModel):
    contract_version: Literal["1.0.0"] = "1.0.0"
    as_of: datetime
    policy: ScanPolicy
    quotas: list[ProviderQuota]
    recent_jobs: list[RescanJob]


ServiceState = Literal["RUNNING", "IDLE", "WAITING", "DEGRADED", "OFFLINE", "STOPPING", "STOPPED"]
ServiceCategory = Literal["CORE", "INGESTION", "ENRICHMENT", "GRAPH", "INTELLIGENCE"]
ServiceDesiredState = Literal["RUNNING", "STOPPED"]


class ServiceStatus(ContractModel):
    key: str = Field(min_length=1)
    name: str = Field(min_length=1)
    category: ServiceCategory
    state: ServiceState
    desired_state: ServiceDesiredState = "RUNNING"
    controllable: bool = False
    management_scope: str = "Externally managed"
    detail: str = ""
    configured: bool = True
    pending: int = Field(default=0, ge=0)
    running: int = Field(default=0, ge=0)
    failed: int = Field(default=0, ge=0)
    last_activity_at: datetime | None = None
    last_heartbeat_at: datetime | None = None


class ServiceControlRequest(ContractModel):
    desired_state: ServiceDesiredState


class ServiceStatusList(ContractModel):
    contract_version: Literal["1.0.0"] = "1.0.0"
    as_of: datetime
    services: list[ServiceStatus]


class ErrorResponse(ContractModel):
    code: str
    message: str
    request_id: str
    details: dict[str, Any] | None = None


# --- Phase 2 change compiler and simulator ---------------------------------

ResolutionState = Literal["RESOLVED", "INFERRED", "UNRESOLVED"]
GateState = Literal["BLOCKED", "ESCALATE", "CONSTRAIN", "CLEAR"]
ActionPredicate = Literal["UPGRADE", "REPLACE", "REMOVE", "DEPRECATE", "MIGRATE", "MOVE"]
MutationLifecycle = Literal[
    "DRAFT", "VALIDATED", "REJECTED", "SUPERSEDED", "SUBMITTED", "EXECUTED", "CANCELLED",
]
SimulationStatus = Literal[
    "QUEUED", "RUNNING", "SUCCEEDED", "LIMITED", "NOT_SIMULATABLE", "FAILED", "CANCELLED",
]
ImpactClassification = Literal["DIRECT", "TRANSITIVE", "CONTEXT", "STOP", "INFORMATIONAL"]


class GateReason(ContractModel):
    code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{2,63}$")
    message: str = Field(min_length=1)
    evidence_fact_ids: list[UUID] = Field(default_factory=list)


class ChangeGate(ContractModel):
    state: GateState
    reasons: list[GateReason] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_gate_reasons(self) -> "ChangeGate":
        if self.state == "CLEAR" and self.reasons:
            raise ValueError("CLEAR gates cannot carry blocking reasons")
        if self.state != "CLEAR" and not self.reasons:
            raise ValueError("non-clear gates must name at least one reason")
        return self


class ResolutionCandidate(ContractModel):
    entity: EntitySummary
    confidence: float = Field(ge=0, le=1)
    method: str = Field(min_length=1)


class EntityResolution(ContractModel):
    state: ResolutionState
    entity: EntitySummary | None = None
    candidates: list[ResolutionCandidate] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
    method: str = Field(min_length=1)
    method_version: str = Field(min_length=1)
    evidence_fact_ids: list[UUID] = Field(default_factory=list)


class ActionSubjectCapability(ContractModel):
    """One subject type a predicate may apply to, and whether it can compile today.

    §4 wants the bounded grammar visible rather than hidden until it works. A predicate with
    one active subject type and three planned ones is a different thing from a predicate that
    does not exist, and only a per-subject lifecycle can express the difference.
    """

    subject_type: str = Field(min_length=1)
    lifecycle: Literal["ACTIVE", "DISABLED", "RETIRED"]
    enabled: bool


class ActionTypeSummary(ContractModel):
    predicate: ActionPredicate
    label: str = Field(min_length=1)
    description: str = Field(min_length=1)
    subject_types: list[str] = Field(min_length=1)
    subjects: list[ActionSubjectCapability] = Field(default_factory=list)
    # True when at least one subject type can compile. A predicate is offerable if anything can
    # be done with it, not only if everything can.
    enabled: bool
    lifecycle: Literal["ACTIVE", "DISABLED", "RETIRED"]
    ontology_version: str = Field(min_length=1)


class ActionTypeList(ContractModel):
    contract_version: Literal["1.0.0"] = "1.0.0"
    action_types: list[ActionTypeSummary]
    policy_version: str = Field(min_length=1)


class ActionSubject(ContractModel):
    entity: EntitySummary
    resolution: Literal["RESOLVED"] = "RESOLVED"
    observed_versions: list[str] = Field(default_factory=list)
    dependent_count: int = Field(default=0, ge=0)
    evidence_fact_ids: list[UUID] = Field(default_factory=list)


class ActionSubjectList(ContractModel):
    contract_version: Literal["1.0.0"] = "1.0.0"
    predicate: ActionPredicate
    subjects: list[ActionSubject]
    page_info: PageInfo


class ValidTarget(ContractModel):
    # None for a version the registry offers that no repository runs. The estate has no entity
    # for it because the estate does not contain it; one is minted only if a change to it is
    # actually compiled. Fabricating an id here would put a package the estate never had into
    # every count taken over the estate.
    entity_id: UUID | None = None
    version: str = Field(min_length=1)
    canonical_key: str = Field(min_length=1)
    source: str = Field(min_length=1)
    observed_at: datetime
    freshness: FreshnessStatus
    support: Literal["SUPPORTED", "UNKNOWN", "UNSUPPORTED", "END_OF_LIFE"] = "UNKNOWN"
    # §6 asks the target list to say why each candidate is worth choosing rather than
    # presenting an undifferentiated list of version strings.
    recommendation: Literal["CONSOLIDATE", "CANDIDATE", "LATEST_KNOWN", "NONE"] = "NONE"
    recommendation_detail: str | None = None
    observed_repository_count: int = Field(default=0, ge=0)
    # Where this option came from. A reader choosing a target should know whether the estate has
    # ever exercised it or whether it is only on offer.
    origin: Literal["ESTATE", "REGISTRY_CATALOG"] = "ESTATE"
    is_prerelease: bool = False


class TargetCoverage(ContractModel):
    """What the target list was drawn from, so a short list is not read as a short registry.

    §9.1 forbids partial input from asserting absence. The estate is not a registry, and a
    version nobody in the estate runs is missing from this list because it was never collected,
    not because it does not exist.
    """

    source: Literal["ESTATE_OBSERVED", "REGISTRY_ENUMERATED", "MIXED"]
    registry_enumeration: Literal["AVAILABLE", "NOT_COLLECTED"] = "NOT_COLLECTED"
    detail: str


class ValidTargetList(ContractModel):
    contract_version: Literal["1.0.0"] = "1.0.0"
    subject: EntitySummary
    targets: list[ValidTarget]
    policy_version: str = Field(min_length=1)
    page_info: PageInfo
    coverage: TargetCoverage | None = None
    limitations: list[GateReason] = Field(default_factory=list)


class VersionDistribution(ContractModel):
    version: str = Field(min_length=1)
    count: int = Field(ge=1)


class ChangeScope(ContractModel):
    id: str = Field(min_length=1)
    kind: Literal["ESTATE", "REPOSITORY", "COMPONENT"]
    label: str = Field(min_length=1)
    entity_id: UUID | None = None
    component_path: str | None = None
    affected_count: int = Field(ge=1)
    version_distribution: list[VersionDistribution]
    evidence_fact_ids: list[UUID] = Field(min_length=1)


class ChangeScopeList(ContractModel):
    contract_version: Literal["1.0.0"] = "1.0.0"
    subject: EntitySummary
    scopes: list[ChangeScope]
    policy_version: str = Field(min_length=1)


class MutationCompileRequest(ContractModel):
    intent: str | None = Field(default=None, min_length=3, max_length=500)
    predicate: ActionPredicate | None = None
    subject_id: UUID | None = None
    subject_query: str | None = Field(default=None, min_length=1, max_length=255)
    target_version: str | None = Field(default=None, min_length=1, max_length=255)
    scope_id: str | None = Field(default=None, min_length=1, max_length=500)
    idempotency_key: str = Field(min_length=1, max_length=255)

    @model_validator(mode="after")
    def validate_input_mode(self) -> "MutationCompileRequest":
        if not self.intent and not self.predicate:
            raise ValueError("intent or predicate is required")
        if self.intent and any((self.predicate, self.subject_id, self.subject_query, self.target_version, self.scope_id)):
            raise ValueError("intent cannot be combined with structured mutation fields")
        if self.predicate and not (self.subject_id or self.subject_query):
            raise ValueError("structured mutations require subject_id or subject_query")
        return self


class ChangeSetMutationRequest(ContractModel):
    """One mutation inside a multi-mutation ChangeSet.

    Deliberately not `MutationCompileRequest`: an idempotency key belongs to the set, not to
    each member, and free-form intent is not accepted here. A pull request or ticket states
    what it changes structurally, so accepting prose per member would put natural language back
    inside a deterministic path that §9 keeps it out of.
    """

    predicate: ActionPredicate
    subject_id: UUID | None = None
    subject_query: str | None = Field(default=None, min_length=1, max_length=255)
    target_version: str | None = Field(default=None, min_length=1, max_length=255)
    scope_id: str | None = Field(default=None, min_length=1, max_length=500)

    @model_validator(mode="after")
    def validate_subject(self) -> "ChangeSetMutationRequest":
        if not (self.subject_id or self.subject_query):
            raise ValueError("each mutation requires subject_id or subject_query")
        return self


class ChangeSetCompileRequest(ContractModel):
    """Compile an ordered ChangeSet from any structured entry point.

    §7 asks that a pull request, change ticket, architecture change, or agent proposal reach the
    simulator through the same Mutation IR as the command bar. They do so here: the caller
    states what its source proposes, StackGraph resolves every subject and target against the
    estate, and refuses the whole set if any member does not ground.
    """

    entry_point: Literal[
        "API", "PULL_REQUEST", "CHANGE_TICKET", "ARCHITECTURE_CHANGE", "AGENT_PROPOSAL",
    ] = "API"
    external_reference: str | None = Field(default=None, min_length=1, max_length=500)
    mutations: list[ChangeSetMutationRequest] = Field(min_length=1, max_length=20)
    idempotency_key: str = Field(min_length=1, max_length=255)
    atomic: bool = True


class MutationValidationError(ContractModel):
    code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{2,63}$")
    field: str = Field(min_length=1)
    message: str = Field(min_length=1)
    evidence_fact_ids: list[UUID] = Field(default_factory=list)


class MutationIR(ContractModel):
    id: UUID | None = None
    schema_version: Literal["mutation/1.0.0"] = "mutation/1.0.0"
    predicate: ActionPredicate
    subject: EntityResolution
    before: dict[str, Any]
    after: dict[str, Any]
    scope: ChangeScope | None = None
    constraints: dict[str, Any] = Field(default_factory=dict)
    provenance: dict[str, Any]
    input_fingerprint: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    lifecycle: MutationLifecycle
    validation_errors: list[MutationValidationError] = Field(default_factory=list)


class ChangeSetModel(ContractModel):
    id: UUID | None = None
    schema_version: Literal["changeset/1.0.0"] = "changeset/1.0.0"
    atomic: bool = True
    mutations: list[MutationIR] = Field(min_length=1, max_length=20)
    lifecycle: MutationLifecycle
    input_fingerprint: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    created_at: datetime | None = None


class MutationCompileResult(ContractModel):
    contract_version: Literal["1.0.0"] = "1.0.0"
    command_state: Literal["EMPTY", "RESOLVING", "TOKENISED", "COMPILED"]
    change_set: ChangeSetModel | None = None
    draft: MutationIR
    gate: ChangeGate
    replayed: bool = False


class MutationValidateRequest(ContractModel):
    change_set_id: UUID


class RecommendationCompileRequest(ContractModel):
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=255)


class RepositoryFingerprintSnapshot(ContractModel):
    fact_id: UUID
    source_revision: str = Field(min_length=1)
    observed_at: datetime
    system_from: datetime
    system_to: datetime | None = None
    confidence: float = Field(ge=0, le=1)
    fingerprint: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    profile: dict[str, Any]


class RepositoryFingerprintList(ContractModel):
    contract_version: Literal["1.0.0"] = "1.0.0"
    repository: EntitySummary
    snapshots: list[RepositoryFingerprintSnapshot]
    page_info: PageInfo


class ObservedMutationCreateRequest(ContractModel):
    correlation_key: str = Field(min_length=1, max_length=255)
    source_kind: Literal[
        "PULL_REQUEST", "COMMIT", "DEPLOYMENT", "TICKET", "INCIDENT", "POSTMORTEM", "MANUAL",
    ]
    predicate: ActionPredicate
    subject_entity_id: UUID
    before: dict[str, Any]
    after: dict[str, Any]
    scope: dict[str, Any]
    observed_impact: dict[str, Any]
    unexpected_impact: dict[str, Any] = Field(default_factory=dict)
    success: bool | None = None
    intervention_required: bool = False
    rolled_back: bool = False
    evidence_fact_ids: list[UUID] = Field(min_length=1)
    graph_watermark_before: str | None = None
    predicted_simulation_run_id: UUID | None = None
    resolution: str | None = Field(default=None, max_length=2000)
    confidence: float = Field(ge=0, le=1)
    observed_at: datetime


class ObservedMutationModel(ContractModel):
    id: UUID
    correlation_key: str
    source_kind: str
    predicate: ActionPredicate
    subject: EntitySummary
    before: dict[str, Any]
    after: dict[str, Any]
    scope: dict[str, Any]
    observed_impact: dict[str, Any]
    unexpected_impact: dict[str, Any]
    success: bool | None = None
    intervention_required: bool
    rolled_back: bool
    evidence_fact_ids: list[UUID]
    graph_watermark_before: str | None = None
    predicted_simulation_run_id: UUID | None = None
    predicted_finding_count: int | None = Field(default=None, ge=0)
    observed_impact_count: int = Field(default=0, ge=0)
    unexpected_impact_count: int = Field(default=0, ge=0)
    resolution: str | None = None
    confidence: float = Field(ge=0, le=1)
    input_fingerprint: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    observed_at: datetime
    created_at: datetime


class ObservedMutationList(ContractModel):
    contract_version: Literal["1.0.0"] = "1.0.0"
    subject: EntitySummary
    outcomes: list[ObservedMutationModel]
    similar_outcomes: list[ObservedMutationModel] = Field(default_factory=list)
    similarity_method: Literal["ENTITY_TYPE_AND_PREDICATE/1.0.0"] = "ENTITY_TYPE_AND_PREDICATE/1.0.0"
    minimum_predictor_sample: int = Field(default=5, ge=1)
    limitations: list[GateReason] = Field(default_factory=list)
    page_info: PageInfo


class SimulationCreateRequest(ContractModel):
    change_set_id: UUID
    idempotency_key: str = Field(min_length=1, max_length=255)


class SimulationFinding(ContractModel):
    id: UUID
    rule_key: str = Field(min_length=1)
    rule_version: str = Field(min_length=1)
    classification: ImpactClassification
    severity: Literal["INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL"]
    title: str = Field(min_length=1)
    detail: str = Field(min_length=1)
    affected_entity: EntitySummary | None = None
    confidence: float = Field(ge=0, le=1)
    evidence_fact_ids: list[UUID] = Field(default_factory=list)
    path: list[EntitySummary] = Field(default_factory=list)


class QuarantinedClaim(ContractModel):
    """Interpretation output that cited no finding this run produced.

    Kept visible and structurally separate. §9.1 forbids hiding an uncited claim and forbids
    letting one influence risk, the gate, or any deterministic result.
    """

    reason: Literal["UNCITED_OUTPUT", "CITED_UNKNOWN_FINDING"]
    detail: str
    values: list[str] = Field(default_factory=list)


class SimulationInterpretation(ContractModel):
    status: Literal["AVAILABLE", "UNAVAILABLE", "QUARANTINED"]
    risk: str | None = None
    explanation: str | None = None
    rollout: list[str] = Field(default_factory=list)
    remediation: list[str] = Field(default_factory=list)
    verification: list[str] = Field(default_factory=list)
    cited_finding_ids: list[UUID] = Field(default_factory=list)
    quarantined_claims: list[QuarantinedClaim] = Field(default_factory=list)
    limitation: str | None = None


class SimulationRunModel(ContractModel):
    contract_version: Literal["1.0.0"] = "1.0.0"
    id: UUID
    change_set_id: UUID
    status: SimulationStatus
    gate: ChangeGate
    estate_watermark: str
    policy_version: str
    provider_version: str
    scanner_versions: list[str]
    findings: list[SimulationFinding]
    interpretation: SimulationInterpretation
    limitations: list[GateReason]
    result_hash: str | None = Field(default=None, pattern=r"^sha256:[a-f0-9]{64}$")
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    replayed: bool = False


# --- Estate fidelity read models (S1-S3 / R4') ------------------------------

ReadModelAvailability = Literal["AVAILABLE", "PARTIAL", "NOT_COLLECTED"]


class ComponentProfile(ContractModel):
    """Typed scanner reading for an estate component.

    A component path is a locator, not its durable identity. The enclosing
    ``EntitySummary.id`` remains the canonical route and review key.
    """

    component_path: str | None = Field(default=None, min_length=1)
    classifications: list[str] = Field(default_factory=list)
    independently_deployable: bool | None = None
    runtime: str | None = None
    status: ReadModelAvailability
    confidence: float = Field(ge=0, le=1)
    confidence_label: ConfidenceLabel
    freshness: Freshness
    evidence_fact_ids: list[UUID] = Field(default_factory=list)
    limitations: list[GateReason] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_available_profile(self) -> "ComponentProfile":
        if self.status == "AVAILABLE" and (self.component_path is None or not self.evidence_fact_ids):
            raise ValueError("available component profiles require a path and supporting evidence")
        return self


class EstateComponentSummary(ContractModel):
    component: EntitySummary
    repository: EntitySummary | None = None
    profile: ComponentProfile

    @model_validator(mode="after")
    def validate_entity_kinds(self) -> "EstateComponentSummary":
        if self.component.kind != "Component":
            raise ValueError("component summaries require a Component entity")
        if self.repository is not None and self.repository.kind != "Repository":
            raise ValueError("component repositories require a Repository entity")
        return self


class EstateComponentList(ContractModel):
    contract_version: Literal["1.0.0"] = "1.0.0"
    as_of: datetime
    components: list[EstateComponentSummary]
    page_info: PageInfo
    limitations: list[GateReason] = Field(default_factory=list)


class EstateComponentDetail(ContractModel):
    contract_version: Literal["1.0.0"] = "1.0.0"
    as_of: datetime
    component: EstateComponentSummary
    technologies: list[EntitySummary] = Field(default_factory=list)
    deployments: list[EntitySummary] = Field(default_factory=list)
    container_images: list[EntitySummary] = Field(default_factory=list)
    limitations: list[GateReason] = Field(default_factory=list)


class ContainerImageIdentity(ContractModel):
    state: ResolutionState
    canonical_reference: str | None = None
    digest: str | None = Field(default=None, pattern=r"^sha256:[a-f0-9]{64}$")
    observed_tags: list[str] = Field(default_factory=list)
    registry: str | None = None

    @model_validator(mode="after")
    def validate_resolution(self) -> "ContainerImageIdentity":
        if self.state == "RESOLVED" and self.digest is None:
            raise ValueError("resolved container identities require an immutable digest")
        if self.state == "UNRESOLVED" and self.canonical_reference is not None:
            raise ValueError("unresolved container identities cannot claim a canonical reference")
        return self


class ContainerLayer(ContractModel):
    index: int = Field(ge=0)
    digest: str | None = Field(default=None, pattern=r"^sha256:[a-f0-9]{64}$")
    command: str | None = None
    size_bytes: int | None = Field(default=None, ge=0)


class ContainerPackage(ContractModel):
    name: str = Field(min_length=1)
    version: str | None = None
    ecosystem: str | None = None


class ContainerImageComposition(ContractModel):
    image: EntitySummary
    identity: ContainerImageIdentity
    architecture: str | None = None
    operating_system: str | None = None
    layers: list[ContainerLayer] = Field(default_factory=list)
    packages: list[ContainerPackage] = Field(default_factory=list)
    scan_status: ReadModelAvailability
    freshness: Freshness
    evidence_fact_ids: list[UUID] = Field(default_factory=list)
    limitations: list[GateReason] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_available_composition(self) -> "ContainerImageComposition":
        if self.scan_status == "AVAILABLE":
            if self.identity.state != "RESOLVED" or not (self.layers or self.packages):
                raise ValueError("available compositions require a resolved digest and collected contents")
        return self


class ContainerCompositionList(ContractModel):
    contract_version: Literal["1.0.0"] = "1.0.0"
    repository: EntitySummary
    status: ReadModelAvailability
    images: list[ContainerImageComposition]
    as_of: datetime
    limitations: list[GateReason] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_collection_status(self) -> "ContainerCompositionList":
        if self.status == "NOT_COLLECTED" and self.images:
            raise ValueError("not-collected container responses cannot include images")
        if self.status == "AVAILABLE" and any(image.scan_status != "AVAILABLE" for image in self.images):
            raise ValueError("available container responses cannot include partial images")
        return self


class DeploymentAction(ContractModel):
    verb: str = Field(min_length=1)
    target: str = Field(min_length=1)
    target_kind: str | None = None


class DeploymentProfile(ContractModel):
    deployment: EntitySummary
    provider: str | None = None
    workload_kind: str | None = None
    environment: str | None = None
    region: str | None = None
    actions: list[DeploymentAction] = Field(default_factory=list)
    status: ReadModelAvailability
    confidence: float = Field(ge=0, le=1)
    confidence_label: ConfidenceLabel
    freshness: Freshness
    evidence_fact_ids: list[UUID] = Field(default_factory=list)
    limitations: list[GateReason] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_available_profile(self) -> "DeploymentProfile":
        if self.status == "AVAILABLE" and (self.provider is None or not self.actions):
            raise ValueError("available deployment profiles require a provider and actions")
        return self


class DeploymentProfileList(ContractModel):
    contract_version: Literal["1.0.0"] = "1.0.0"
    repository: EntitySummary
    profiles: list[DeploymentProfile]
    as_of: datetime
    limitations: list[GateReason] = Field(default_factory=list)


class EstateStratumLayer(ContractModel):
    key: Literal["BUSINESS", "ENTERPRISE", "TECHNOLOGY", "OSS", "DEPLOYMENT", "AI"]
    label: str = Field(min_length=1)
    status: ReadModelAvailability
    population_count: int | None = Field(default=None, ge=0)
    observed_count: int | None = Field(default=None, ge=0)
    coverage_ratio: float | None = Field(default=None, ge=0, le=1)
    corroboration_ratio: float | None = Field(default=None, ge=0, le=1)
    as_of: datetime | None = None
    limitations: list[GateReason] = Field(default_factory=list)


class EstateStrata(ContractModel):
    contract_version: Literal["1.0.0"] = "1.0.0"
    as_of: datetime
    method_version: Literal["estate-strata/1.0.0"] = "estate-strata/1.0.0"
    layers: list[EstateStratumLayer] = Field(min_length=6, max_length=6)

    @model_validator(mode="after")
    def validate_layer_order(self) -> "EstateStrata":
        expected = ["BUSINESS", "ENTERPRISE", "TECHNOLOGY", "OSS", "DEPLOYMENT", "AI"]
        if [layer.key for layer in self.layers] != expected:
            raise ValueError("estate strata require all six layers in canonical order")
        return self


class ContradictionClaim(ContractModel):
    claim_key: str = Field(min_length=1)
    display_value: str = Field(min_length=1)
    source_key: str = Field(min_length=1)
    assertion_class: Literal["DECLARED", "OBSERVED", "INFERRED", "CURATED", "EXTERNAL_MEASURED"]
    confidence: float = Field(ge=0, le=1)
    observed_at: datetime
    evidence_fact_ids: list[UUID] = Field(min_length=1)


class ContradictionLedgerItem(ContractModel):
    id: str = Field(min_length=1)
    subject: EntitySummary
    predicate: str = Field(min_length=1)
    status: Literal["OPEN"] = "OPEN"
    claims: list[ContradictionClaim] = Field(min_length=2)
    affected_entity_count: int = Field(ge=0)
    last_verified_at: datetime
    version: int = Field(default=1, ge=1)
    limitations: list[GateReason] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_disagreement(self) -> "ContradictionLedgerItem":
        if len({claim.claim_key for claim in self.claims}) < 2:
            raise ValueError("contradictions require at least two distinct claims")
        return self


class ContradictionLedger(ContractModel):
    contract_version: Literal["1.0.0"] = "1.0.0"
    as_of: datetime
    method_version: Literal[
        "current-fact-disagreement/1.0.0", "assumption-registry/1.0.0",
    ] = "current-fact-disagreement/1.0.0"
    contradictions: list[ContradictionLedgerItem]
    page_info: PageInfo
    limitations: list[GateReason] = Field(default_factory=list)


# --- E1 governed estate fidelity -------------------------------------------

AssumptionStatus = Literal["OPEN", "ACCEPTED", "REJECTED", "SUPERSEDED"]
ContradictionStatus = Literal["OPEN", "RESOLVED", "DISMISSED"]


class AssumptionClaimCreateRequest(ContractModel):
    claim_key: str = Field(min_length=1, max_length=255)
    display_value: str = Field(min_length=1, max_length=2000)
    source_key: str = Field(min_length=1, max_length=255)
    assertion_class: Literal["DECLARED", "OBSERVED", "INFERRED", "CURATED", "EXTERNAL_MEASURED"]
    confidence: float = Field(ge=0, le=1)
    observed_at: datetime
    supporting_fact_ids: list[UUID] = Field(default_factory=list)
    opposing_fact_ids: list[UUID] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_evidence(self) -> "AssumptionClaimCreateRequest":
        if not self.supporting_fact_ids and not self.opposing_fact_ids:
            raise ValueError("assumption claims require supporting or opposing evidence")
        if set(self.supporting_fact_ids) & set(self.opposing_fact_ids):
            raise ValueError("a fact cannot both support and oppose the same claim")
        return self


class AssumptionCreateRequest(ContractModel):
    subject_entity_id: UUID
    dimension: str = Field(min_length=1, max_length=255)
    statement: str = Field(min_length=1, max_length=4000)
    authority: str = Field(min_length=1, max_length=255)
    confidence: float = Field(ge=0, le=1)
    last_verified_at: datetime
    dependent_entity_ids: list[UUID] = Field(default_factory=list)
    claims: list[AssumptionClaimCreateRequest] = Field(default_factory=list)


class AssumptionClaimModel(ContractModel):
    id: UUID
    claim_key: str
    display_value: str
    source_key: str
    assertion_class: Literal["DECLARED", "OBSERVED", "INFERRED", "CURATED", "EXTERNAL_MEASURED"]
    confidence: float = Field(ge=0, le=1)
    observed_at: datetime
    supporting_fact_ids: list[UUID] = Field(default_factory=list)
    opposing_fact_ids: list[UUID] = Field(default_factory=list)


class AssumptionModel(ContractModel):
    id: UUID
    subject: EntitySummary
    dimension: str
    statement: str
    status: AssumptionStatus
    authority: str
    confidence: float = Field(ge=0, le=1)
    last_verified_at: datetime
    version: int = Field(ge=1)
    claims: list[AssumptionClaimModel] = Field(default_factory=list)
    dependent_entity_ids: list[UUID] = Field(default_factory=list)
    contradiction_ids: list[UUID] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class AssumptionList(ContractModel):
    contract_version: Literal["1.0.0"] = "1.0.0"
    assumptions: list[AssumptionModel]
    page_info: PageInfo


class ContradictionResolveRequest(ContractModel):
    status: Literal["RESOLVED", "DISMISSED"]
    rationale: str = Field(min_length=1, max_length=4000)
    expected_version: int = Field(ge=1)


class EstateLineageEdgeModel(ContractModel):
    id: UUID
    upstream: EntitySummary
    downstream: EntitySummary
    lineage_kind: Literal[
        "COLUMN_TO_TABLE", "TABLE_TO_PIPELINE", "PIPELINE_TO_FEATURE", "FEATURE_TO_MODEL",
        "MODEL_TO_AGENT", "AGENT_TO_API", "API_TO_PROCESS", "DATASET_TO_CAPABILITY", "OTHER",
    ]
    confidence: float = Field(ge=0, le=1)
    evidence_fact_id: UUID
    observed_at: datetime


class EstateLineageList(ContractModel):
    contract_version: Literal["1.0.0"] = "1.0.0"
    edges: list[EstateLineageEdgeModel]
    page_info: PageInfo
    limitations: list[GateReason] = Field(default_factory=list)


class AISupplyChainLink(ContractModel):
    predicate: str = Field(min_length=1)
    subject: EntitySummary
    object: EntitySummary
    confidence: float = Field(ge=0, le=1)
    evidence_fact_ids: list[UUID] = Field(min_length=1)


class AISupplyChain(ContractModel):
    contract_version: Literal["1.0.0"] = "1.0.0"
    as_of: datetime
    status: ReadModelAvailability
    entities: list[EntitySummary] = Field(default_factory=list)
    links: list[AISupplyChainLink] = Field(default_factory=list)
    coverage_ratio: float | None = Field(default=None, ge=0, le=1)
    limitations: list[GateReason] = Field(default_factory=list)


# --- R16 governed agent control plane --------------------------------------

CapabilityBand = Literal["READ", "EXECUTE", "CONDITIONAL", "PROHIBITED", "ESCALATE"]
AgentDecision = Literal["ALLOW", "CONSTRAIN", "ESCALATE", "DENY"]
AgentRiskTier = Literal["TIER_0", "TIER_1", "TIER_2", "TIER_3"]


class AgentOperationRequest(ContractModel):
    operation_key: str = Field(pattern=r"^[a-z][a-z0-9._:-]{2,127}$")
    requested_band: CapabilityBand
    destructive: bool = False
    constraints: dict[str, Any] = Field(default_factory=dict)


class CapabilityEnvelopeCompileRequest(ContractModel):
    objective: str = Field(min_length=1, max_length=4000)
    environment: str = Field(min_length=1, max_length=255)
    estate_watermark: str = Field(min_length=1, max_length=255)
    risk_tier: AgentRiskTier
    context_confidence: float = Field(ge=0, le=1)
    operations: list[AgentOperationRequest] = Field(min_length=1, max_length=100)
    evidence_fact_ids: list[UUID] = Field(default_factory=list)
    subject_entity_ids: list[UUID] = Field(default_factory=list)
    ttl_seconds: int | None = Field(default=None, ge=30, le=3600)

    @model_validator(mode="after")
    def validate_unique_operations(self) -> "CapabilityEnvelopeCompileRequest":
        keys = [item.operation_key for item in self.operations]
        if len(keys) != len(set(keys)):
            raise ValueError("capability envelope operation keys must be unique")
        return self


class CapabilityEnvelopeOperation(ContractModel):
    operation_key: str
    band: CapabilityBand
    constraints: dict[str, Any] = Field(default_factory=dict)


class CapabilityBandModel(ContractModel):
    band: CapabilityBand
    operations: list[CapabilityEnvelopeOperation] = Field(default_factory=list)


class CapabilityEnvelopeModel(ContractModel):
    contract_version: Literal["1.0.0"] = "1.0.0"
    id: UUID
    actor_key: str
    objective: str
    environment: str
    estate_watermark: str
    risk_tier: AgentRiskTier
    context_confidence: float = Field(ge=0, le=1)
    decision: AgentDecision
    decision_reasons: list[GateReason] = Field(default_factory=list)
    constraints: dict[str, Any] = Field(default_factory=dict)
    evidence_fact_ids: list[UUID] = Field(default_factory=list)
    contradiction_ids: list[UUID] = Field(default_factory=list)
    bands: list[CapabilityBandModel] = Field(min_length=5, max_length=5)
    status: Literal["ACTIVE", "EXPIRED", "REVOKED", "CONSUMED"]
    valid_until: datetime
    compiled_hash: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    created_at: datetime

    @model_validator(mode="after")
    def validate_canonical_bands(self) -> "CapabilityEnvelopeModel":
        expected = ["READ", "EXECUTE", "CONDITIONAL", "PROHIBITED", "ESCALATE"]
        if [item.band for item in self.bands] != expected:
            raise ValueError("capability envelopes require all five bands in canonical order")
        return self


class AgentAuthorizeRequest(ContractModel):
    operation_key: str = Field(pattern=r"^[a-z][a-z0-9._:-]{2,127}$")
    request_payload: dict[str, Any] = Field(default_factory=dict)


class AgentAuthorizationDecisionModel(ContractModel):
    id: UUID
    envelope_id: UUID
    operation_key: str
    decision: AgentDecision
    reason_codes: list[str]
    approval_id: UUID | None = None
    request_fingerprint: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    decided_at: datetime


class AgentApprovalDecisionRequest(ContractModel):
    decision: Literal["APPROVED", "REJECTED"]
    rationale: str = Field(min_length=1, max_length=4000)
    expected_version: int = Field(ge=1)


class AgentApprovalModel(ContractModel):
    id: UUID
    envelope_id: UUID
    operation_key: str
    reason_code: str
    status: Literal["PENDING", "APPROVED", "REJECTED", "EXPIRED"]
    requested_by: str
    decided_by: str | None = None
    rationale: str | None = None
    version: int = Field(ge=1)
    expires_at: datetime
    created_at: datetime
    decided_at: datetime | None = None


class AgentKillSwitchUpdateRequest(ContractModel):
    engaged: bool
    reason: str = Field(min_length=1, max_length=2000)
    expected_version: int = Field(ge=0)


class AgentKillSwitchModel(ContractModel):
    contract_version: Literal["1.0.0"] = "1.0.0"
    engaged: bool
    reason: str
    version: int = Field(ge=0)
    updated_by: str
    updated_at: datetime


FlightEventType = Literal[
    "OBJECTIVE", "CONTEXT", "TOOL", "CALL", "DECISION", "ACTION", "ASSET",
    "VERIFICATION", "OUTCOME",
]


class FlightRecordCreateRequest(ContractModel):
    envelope_id: UUID
    objective: str = Field(min_length=1, max_length=4000)


class FlightEventCreateRequest(ContractModel):
    event_type: FlightEventType
    system_boundary: str = Field(min_length=1, max_length=255)
    payload: dict[str, Any]
    occurred_at: datetime


class FlightEventModel(ContractModel):
    id: UUID
    sequence: int = Field(ge=1)
    event_type: FlightEventType
    system_boundary: str
    payload: dict[str, Any]
    previous_hash: str | None = Field(default=None, pattern=r"^sha256:[a-f0-9]{64}$")
    event_hash: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    occurred_at: datetime
    recorded_at: datetime


class FlightRecordFinalizeRequest(ContractModel):
    status: Literal["SUCCEEDED", "FAILED", "ABORTED"]
    outcome: dict[str, Any]


class FlightRecordModel(ContractModel):
    contract_version: Literal["1.0.0"] = "1.0.0"
    id: UUID
    envelope_id: UUID
    objective: str
    status: Literal["ACTIVE", "SUCCEEDED", "FAILED", "ABORTED"]
    event_count: int = Field(ge=0)
    chain_head: str | None = Field(default=None, pattern=r"^sha256:[a-f0-9]{64}$")
    outcome: dict[str, Any] | None = None
    started_by: str
    started_at: datetime
    completed_at: datetime | None = None
    events: list[FlightEventModel] = Field(default_factory=list)


class AgentControlDrillRequest(ContractModel):
    drill_kind: Literal["KILL_SWITCH", "ROLLBACK", "AUDIT_RECONSTRUCTION"]
    envelope_id: UUID | None = None
    flight_record_id: UUID | None = None


class AgentControlDrillResult(ContractModel):
    id: UUID
    drill_kind: Literal["KILL_SWITCH", "ROLLBACK", "AUDIT_RECONSTRUCTION"]
    status: Literal["PASSED", "FAILED"]
    checks: list[dict[str, Any]]
    performed_by: str
    performed_at: datetime
