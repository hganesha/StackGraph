// Contract types for StackGraph read models — mirrors
// stackgraph-foundation/contracts/v1/schemas/{read-models,common}.schema.json.
// TODO(build): replace with codegen (json-schema-to-typescript) so contract drift breaks the build.

export type UUID = string;
export type Timestamp = string;
export type Confidence = number; // 0..1
export type ConfidenceLabel = "HIGH" | "MEDIUM" | "LOW";

export type Namespace =
  | "BUSINESS"
  | "ENTERPRISE"
  | "TECHNOLOGY"
  | "OSS"
  | "DEPLOYMENT"
  | "INTELLIGENCE";

export type AssertionClass =
  | "DECLARED"
  | "OBSERVED"
  | "INFERRED"
  | "CURATED"
  | "EXTERNAL_MEASURED";

export type FreshnessStatus = "FRESH" | "STALE" | "UNKNOWN";

export interface Freshness {
  observed_at: Timestamp;
  effective_at?: Timestamp;
  status: FreshnessStatus;
  source_key?: string;
}

export interface PageInfo {
  has_next_page: boolean;
  next_cursor?: string | null;
}

export interface Citation {
  fact_id: UUID;
  label: string;
  href?: string;
}

export interface Score {
  value: number;
  confidence: Confidence;
  confidence_label: ConfidenceLabel;
  method_version: string;
}

export interface RankedItem {
  id: UUID;
  kind: string;
  name: string;
  domain: Namespace;
  priority: Score;
  viability?: Score;
  summary?: string;
  freshness: Freshness;
  citations?: Citation[];
}

export interface EstateCounts {
  applications: number;
  repositories: number;
  services: number;
  technologies: number;
}

export interface EstateCoverage {
  repositories_total: number;
  repositories_scanned: number;
  facts_with_evidence_ratio: number;
}

export interface EstateSummary {
  contract_version: "1.0.0";
  as_of: Timestamp;
  counts: EstateCounts;
  distributions: Record<string, number>;
  ranked_items: RankedItem[];
  coverage: EstateCoverage;
  page_info?: PageInfo;
}

export interface EntitySummary {
  id: UUID;
  kind: string;
  name: string;
  canonical_key?: string;
  summary?: string;
}

export interface AssessmentSummary {
  id: UUID;
  dimension: string;
  score?: number;
  categorical_value?: string;
  confidence: Confidence;
  confidence_label: ConfidenceLabel;
  method_version: string;
  rationale?: string;
  citations: Citation[];
}

export type RecommendationAction =
  | "RETAIN"
  | "UPGRADE"
  | "REMOVE"
  | "REPLACE"
  | "CONSOLIDATE"
  | "REFACTOR"
  | "REBUILD"
  | "REPLATFORM"
  | "RETIRE"
  | "INVESTIGATE";

export type RecommendationStatus =
  | "PROPOSED"
  | "ACCEPTED"
  | "REJECTED"
  | "PLANNED"
  | "IN_PROGRESS"
  | "COMPLETED"
  | "DISMISSED";

export type Effort = "LOW" | "MEDIUM" | "HIGH" | "UNKNOWN";

export interface RecommendationSummary {
  id: UUID;
  action: RecommendationAction;
  title: string;
  rationale: string;
  confidence: Confidence;
  confidence_label: ConfidenceLabel;
  status: RecommendationStatus;
  estimated_effort?: Effort;
  counter_signals?: string[];
  target?: EntitySummary;
  citations: Citation[];
}

export interface ApplicationDetail {
  contract_version: "1.0.0";
  application: EntitySummary;
  business_context: EntitySummary[];
  repositories: EntitySummary[];
  technologies: EntitySummary[];
  deployments: EntitySummary[];
  assessments: AssessmentSummary[];
  recommendations: RecommendationSummary[];
  freshness: Freshness;
}

export interface PackageSource {
  registry_key: string;
  origin: string;
  visibility: "PUBLIC" | "PRIVATE" | "UNKNOWN";
  tenant_scoped: boolean;
  freshness: Freshness;
}

export interface TechnologyDetail {
  contract_version: "1.0.0";
  technology: EntitySummary;
  internal_usage: {
    repository_count: number;
    application_count: number;
    repositories?: EntitySummary[];
  };
  packages: EntitySummary[];
  projects: EntitySummary[];
  registry_sources?: PackageSource[];
  alternatives?: EntitySummary[];
  migration_patterns?: EntitySummary[];
  assessments: AssessmentSummary[];
  recommendations: RecommendationSummary[];
  freshness: Freshness;
}

export interface ModernizationList {
  contract_version: "1.0.0";
  as_of: Timestamp;
  opportunities: RankedItem[];
  page_info: PageInfo;
}

export interface GraphNode {
  id: UUID;
  namespace: Namespace;
  type: string;
  key: string;
  label: string;
  aggregate: boolean;
  member_count?: number;
  confidence?: Confidence;
}

export type ReviewState = "CONFIRMED" | "POSSIBLE" | "REJECTED" | "NOT_APPLICABLE";

export interface GraphEdge {
  id: UUID;
  source: UUID;
  target: UUID;
  predicate: string;
  confidence: Confidence;
  assertion_class: AssertionClass;
  review_state: ReviewState;
  citation_fact_ids: UUID[];
}

export interface GraphNeighborhood {
  contract_version: "1.0.0";
  center_id: UUID;
  nodes: GraphNode[];
  edges: GraphEdge[];
  highlighted_path?: UUID[];
  truncated: boolean;
  truncation_reason?: string | null;
}

export interface EvidenceDetail {
  contract_version: "1.0.0";
  fact_id: UUID;
  assertion_class: AssertionClass;
  confidence: Confidence;
  predicate: string;
  source_revision: string;
  extractor: { key: string; version: string };
  properties?: Record<string, unknown>;
  evidence: Array<Record<string, unknown>>;
  observed_at: Timestamp;
  effective_at?: Timestamp;
  closed_at?: string | null;
}

export interface AskRequest {
  question: string;
  context_entity_ids?: UUID[];
}

export type AskResultKind = "ANSWER" | "TABLE" | "GRAPH" | "UNSUPPORTED";

export interface AskResponse {
  contract_version: "1.0.0";
  text: string;
  citations: Citation[];
  result_kind: AskResultKind;
  rows?: Array<Record<string, unknown>>;
  graph_highlight?: GraphNeighborhood;
}

export interface IdentityReviewRequest {
  decision: "CONFIRM" | "REJECT";
  rationale: string;
  expected_version: number;
}

export interface IdentityReviewResult {
  contract_version: "1.0.0";
  identity_assertion_id: UUID;
  review_state: "CONFIRMED" | "REJECTED";
  version: number;
  reviewed_at: Timestamp;
}

export interface CapabilityDefinition {
  key: string;
  name: string;
  description: string;
  parent_key?: string;
  aliases: string[];
}

export interface CapabilityTaxonomy {
  contract_version: "1.0.0";
  key: string;
  version: string;
  name: string;
  description: string;
  content_hash: string;
  capabilities: CapabilityDefinition[];
}

export interface CapabilityInference {
  id: UUID;
  subject: EntitySummary;
  capability: CapabilityDefinition;
  source_revision: string;
  assertion_class: "CURATED" | "INFERRED";
  confidence: Confidence;
  confidence_band: ConfidenceLabel;
  supporting_fact_ids: UUID[];
  counter_evidence_fact_ids: UUID[];
  taxonomy_key: string;
  taxonomy_version: string;
  analyzer: { key: string; version: string };
  model_provider?: string;
  model_name?: string;
  policy_version: string;
  rationale: string;
  review_state: "UNREVIEWED" | "CONFIRMED" | "REJECTED";
  version: number;
  stale: boolean;
  created_at: Timestamp;
}

export interface DuplicateCapabilityCandidate {
  id: UUID;
  capability: CapabilityDefinition;
  source_revision: string;
  dependencies: EntitySummary[];
  capability_inference_ids: UUID[];
  supporting_fact_ids: UUID[];
  confidence: Confidence;
  summary: string;
  limitations: string[];
  review_state: "UNREVIEWED" | "CONFIRMED" | "REJECTED";
  version: number;
  stale: boolean;
}

export interface RepositoryCapabilityIntelligence {
  contract_version: "1.0.0";
  repository: EntitySummary;
  taxonomy_key?: string;
  taxonomy_version?: string;
  inferences: CapabilityInference[];
  duplicate_candidates: DuplicateCapabilityCandidate[];
}

export interface OptimisticReviewRequest {
  decision: "CONFIRM" | "REJECT";
  rationale: string;
  expected_version: number;
}

export interface CapabilityInferenceReviewResult {
  contract_version: "1.0.0";
  capability_inference_id: UUID;
  review_state: "CONFIRMED" | "REJECTED";
  version: number;
  reviewed_at: Timestamp;
}

export interface DuplicateCapabilityReviewResult {
  contract_version: "1.0.0";
  duplicate_capability_candidate_id: UUID;
  review_state: "CONFIRMED" | "REJECTED";
  version: number;
  reviewed_at: Timestamp;
}

export interface ModernizationOption {
  id: UUID;
  kind: "NATIVE" | "INTERNAL" | "UPGRADE" | "PACKAGE";
  canonical_key: string;
  name: string;
  target_entity?: EntitySummary;
  compatibility: "OBSERVED" | "COMPATIBLE" | "UNKNOWN" | "INCOMPATIBLE";
  rank: number;
  score: Confidence;
  score_components: Record<string, number>;
  rationale: string;
  tradeoffs: string[];
  disqualifiers: string[];
  validation_gaps: string[];
  supporting_fact_ids: UUID[];
}

export interface ModernizationRecommendation {
  id: UUID;
  selected_option_id?: UUID;
  action: "CONSOLIDATE" | "REPLACE" | "UPGRADE" | "REFACTOR" | "INVESTIGATE";
  objective: string;
  title: string;
  rationale: string;
  confidence: Confidence;
  estimated_effort: Effort;
  affected_call_sites: number;
  affected_files: number;
  validation_gaps: string[];
  migration_plan: string[];
  rollback_plan: string[];
  supporting_fact_ids: UUID[];
  counter_evidence_fact_ids: UUID[];
  counter_signals: string[];
  policy_version: string;
  review_state: "UNREVIEWED" | "ACCEPTED" | "REJECTED" | "DISMISSED";
  version: number;
  stale: boolean;
  created_at: Timestamp;
}

export interface ModernizationCandidate {
  id: UUID;
  source_revision: string;
  capability?: CapabilityDefinition;
  kind: "DEPENDENCY_CONSOLIDATION" | "INTERNAL_DUPLICATION" | "VENDORED_DUPLICATION" | "NATIVE_REPLACEMENT";
  subjects: EntitySummary[];
  confidence: Confidence;
  summary: string;
  supporting_fact_ids: UUID[];
  counter_evidence_fact_ids: UUID[];
  source_locations: Array<Record<string, unknown>>;
  validation_gaps: string[];
  analyzer: { key: string; version: string };
  review_state: "UNREVIEWED" | "CONFIRMED" | "REJECTED";
  version: number;
  stale: boolean;
  options: ModernizationOption[];
  recommendation?: ModernizationRecommendation;
}

export interface RepositoryModernizationIntelligence {
  contract_version: "1.0.0";
  repository: EntitySummary;
  source_revision?: string;
  candidates: ModernizationCandidate[];
  truncated: boolean;
}

export interface ModernizationRecommendationReviewRequest {
  decision: "ACCEPT" | "REJECT" | "DISMISS";
  rationale: string;
  expected_version: number;
}

export interface ModernizationRecommendationReviewResult {
  contract_version: "1.0.0";
  modernization_recommendation_id: UUID;
  review_state: "ACCEPTED" | "REJECTED" | "DISMISSED";
  version: number;
  reviewed_at: Timestamp;
}

export interface ApiError {
  code: string;
  message: string;
  request_id: string;
  details?: Record<string, unknown>;
}
