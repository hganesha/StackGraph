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


class ErrorResponse(ContractModel):
    code: str
    message: str
    request_id: str
    details: dict[str, Any] | None = None
