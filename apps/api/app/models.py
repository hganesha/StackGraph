from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
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


class EntitySummary(ContractModel):
    id: UUID
    kind: str = Field(min_length=1)
    name: str = Field(min_length=1)
    canonical_key: str | None = None
    summary: str | None = None


class TaxonomySummary(ContractModel):
    key: str = Field(min_length=1)
    name: str = Field(min_length=1)
    summary: str | None = None


TechnologyClassification = Literal["CURATED", "CATALOG_MATCH", "UNCLASSIFIED"]


class ApplicationTechnologyUsage(ContractModel):
    technology: EntitySummary
    category: TaxonomySummary | None = None
    classification: TechnologyClassification
    confidence: float = Field(ge=0, le=1)
    confidence_label: ConfidenceLabel
    citations: list[Citation] = Field(min_length=1)


class ApplicationTechnologyFunction(ContractModel):
    function: TaxonomySummary
    technologies: list[ApplicationTechnologyUsage] = Field(min_length=1)


class ApplicationTechnologyGroup(ContractModel):
    domain: TaxonomySummary
    functions: list[ApplicationTechnologyFunction] = Field(min_length=1)


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


class ApplicationDetail(ContractModel):
    contract_version: Literal["1.0.0"] = "1.0.0"
    application: EntitySummary
    business_context: list[EntitySummary]
    repositories: list[EntitySummary]
    technologies: list[EntitySummary]
    technology_groups: list[ApplicationTechnologyGroup]
    deployments: list[EntitySummary]
    assessments: list[AssessmentSummary]
    recommendations: list[RecommendationSummary]
    freshness: Freshness


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
    registry_sources: list[PackageSource] | None = None
    alternatives: list[EntitySummary] | None = None
    migration_patterns: list[EntitySummary] | None = None
    assessments: list[AssessmentSummary]
    recommendations: list[RecommendationSummary]
    freshness: Freshness


class ModernizationList(ContractModel):
    contract_version: Literal["1.0.0"] = "1.0.0"
    as_of: datetime
    opportunities: list[RankedItem]
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


class GraphEdge(ContractModel):
    id: UUID
    source: UUID
    target: UUID
    predicate: str
    confidence: float = Field(ge=0, le=1)
    assertion_class: Literal["DECLARED", "OBSERVED", "INFERRED", "CURATED", "EXTERNAL_MEASURED"]
    review_state: Literal["CONFIRMED", "POSSIBLE", "REJECTED", "NOT_APPLICABLE"]
    citation_fact_ids: list[UUID] = Field(min_length=1)


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


class AskResponse(ContractModel):
    contract_version: Literal["1.0.0"] = "1.0.0"
    text: str = Field(min_length=1)
    citations: list[Citation]
    result_kind: Literal["ANSWER", "TABLE", "GRAPH", "UNSUPPORTED"]
    rows: list[dict[str, Any]] | None = None
    graph_highlight: GraphNeighborhood | None = None


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
