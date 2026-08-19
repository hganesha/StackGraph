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

export interface ApiError {
  code: string;
  message: string;
  request_id: string;
  details?: Record<string, unknown>;
}
