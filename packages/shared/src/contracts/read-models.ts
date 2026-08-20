// Application-facing contract types for StackGraph read models. The complete wire-level
// model is generated from the canonical OpenAPI document in openapi.generated.ts and
// compiled beside this curated facade; CI fails when the generated artifact drifts.

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

export type Capability = "view" | "review" | "execute" | "admin";

export interface SessionInfo {
  contract_version: "1.0.0";
  actor_key: string;
  tenant_id?: string | null;
  capabilities: Capability[];
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
  eligibility?: ModernizationOptionEligibility;
}

export interface ModernizationOptionEligibility {
  capability_fit: "PASS" | "FAIL" | "UNKNOWN";
  api_fit: "PASS" | "FAIL" | "UNKNOWN";
  behavior_fit: "PASS" | "FAIL" | "UNKNOWN";
  runtime_fit: "PASS" | "FAIL" | "UNKNOWN";
  license_fit: "PASS" | "FAIL" | "UNKNOWN";
  security_fit: "PASS" | "FAIL" | "UNKNOWN";
  policy_fit: "PASS" | "FAIL" | "UNKNOWN";
  eligible: boolean;
  evidence: Record<string, unknown>;
  disqualifiers: string[];
  unknowns: string[];
}

export interface ModernizationImpact {
  affected_call_sites: number;
  affected_files: number;
  covered_call_sites: number;
  uncovered_call_sites: number;
  affected_test_files: string[];
  dynamic_signals: string[];
  configuration_touchpoints: Array<Record<string, unknown>>;
  build_touchpoints: Array<Record<string, unknown>>;
  deployment_touchpoints: Array<Record<string, unknown>>;
  evidence_locations: Array<Record<string, unknown>>;
  confidence: Confidence;
  effort_points: number;
  effort_model_version: string;
  limitations: string[];
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
  impact?: ModernizationImpact;
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

export interface ModernizationCandidateReviewResult {
  contract_version: "1.0.0";
  modernization_candidate_id: UUID;
  review_state: "CONFIRMED" | "REJECTED";
  version: number;
  reviewed_at: Timestamp;
}

export interface ModernizationValidationOutcomeRequest {
  validation_status: "SUCCEEDED" | "PARTIAL" | "FAILED";
  actual_call_sites?: number;
  actual_files?: number;
  actual_effort?: Effort;
  successful_checks?: string[];
  failed_checks?: string[];
  notes: string;
}

export interface ModernizationValidationOutcomeResult {
  contract_version: "1.0.0";
  id: UUID;
  modernization_recommendation_id: UUID;
  validation_status: "SUCCEEDED" | "PARTIAL" | "FAILED";
  reported_at: Timestamp;
}

export interface Phase3IntelligenceMetrics {
  contract_version: "1.0.0";
  as_of: Timestamp;
  candidate_counts: Record<string, number>;
  recommendation_counts: Record<string, number>;
  job_counts: Record<string, number>;
  candidate_review_precision?: number;
  recommendation_acceptance_rate?: number;
  successful_validation_rate?: number;
  affected_call_site_mae?: number;
  affected_files_mae?: number;
  effort_band_accuracy?: number;
  evidence_completeness_rate?: number;
  queue_lag_seconds_p50?: number;
  queue_lag_seconds_p95?: number;
  job_latency_ms_p50?: number;
  job_latency_ms_p95?: number;
  retry_count: number;
  dead_letter_count: number;
  stale_candidate_count: number;
  stale_recommendation_count: number;
  model_invocation_count: number;
  model_cost_usd: number;
  model_latency_ms_p95?: number;
}

export interface ApiError {
  code: string;
  message: string;
  request_id: string;
  details?: Record<string, unknown>;
}

// --- Business Map -----------------------------------------------------------

export type MaturityLevel = 1 | 2 | 3 | 4 | 5;
export type BusinessMapViewMode = "value-chain" | "organization";
export type BusinessMapStatus = "DRAFT" | "ACTIVE" | "ARCHIVED";

export interface BusinessMapLane {
  id: string;
  label: string;
  sublabel: string;
  color: string;
  gradient: string;
  icon: string;
  order: number;
}

export interface BusinessMapCapabilityNode {
  id: string;
  name: string;
  description: string;
  tags: string[];
  kpis: string[];
  owner?: string | null;
}

export interface BusinessMapProcessNode {
  id: string;
  name: string;
  description: string;
  capabilities: BusinessMapCapabilityNode[];
}

export interface BusinessMapFunctionNode {
  id: string;
  name: string;
  description: string;
  color: string;
  gradient: string;
  icon: string;
  processes: BusinessMapProcessNode[];
}

export interface BusinessMapPlacement {
  capability_id: string;
  stage_id: string | null;
  maturity: MaturityLevel;
  source_function_id: string | null;
}

export interface BusinessMapSharedGroup {
  id: string;
  name: string;
  description: string;
  capability_ids: string[];
  start_stage_id: string;
  end_stage_id: string;
}

export interface BusinessMapFunctionAssignment {
  function_id: string;
  unit_id: string;
}

export interface BusinessMapStateModel {
  title: string;
  view_mode: BusinessMapViewMode;
  template_id: string;
  stages: BusinessMapLane[];
  organization_units: BusinessMapLane[];
  catalog: BusinessMapFunctionNode[];
  placements: BusinessMapPlacement[];
  shared_groups: BusinessMapSharedGroup[];
  function_assignments: BusinessMapFunctionAssignment[];
}

export interface BusinessMapSummary {
  id: string;
  map_key: string;
  title: string;
  view_mode: BusinessMapViewMode;
  template_id: string;
  status: BusinessMapStatus;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface BusinessMapList {
  contract_version: "1.0.0";
  as_of: string;
  maps: BusinessMapSummary[];
  page_info: PageInfo;
}

export interface BusinessMapDetail {
  contract_version: "1.0.0";
  id: string;
  map_key: string;
  status: BusinessMapStatus;
  version: number;
  created_at: string;
  updated_at: string;
  state: BusinessMapStateModel;
}

export interface BusinessMapCreateRequest {
  map_key: string;
  state: BusinessMapStateModel;
}

export interface BusinessMapSaveRequest {
  expected_version: number;
  state: BusinessMapStateModel;
}

export interface BusinessMapRevisionSummary {
  version: number;
  actor_key: string;
  created_at: string;
}

export interface BusinessMapRevisionList {
  contract_version: "1.0.0";
  business_map_id: string;
  revisions: BusinessMapRevisionSummary[];
}

// --- Review queue --------------------------------------------------------

export type ReviewQueueItemType =
  | "IDENTITY_ASSERTION"
  | "CAPABILITY_INFERENCE"
  | "DUPLICATE_CAPABILITY"
  | "MODERNIZATION_CANDIDATE"
  | "MODERNIZATION_RECOMMENDATION";

export interface ReviewQueueItem {
  item_id: string;
  item_type: ReviewQueueItemType;
  review_state: string;
  title: string;
  summary?: string | null;
  confidence: number;
  confidence_band: ConfidenceLabel;
  repository_id?: string | null;
  version: number;
  created_at: string;
  /** The endpoint that accepts a decision for this item. */
  review_path: string;
}

export interface ReviewQueue {
  contract_version: "1.0.0";
  as_of: string;
  counts: Record<ReviewQueueItemType, number>;
  items: ReviewQueueItem[];
  page_info: PageInfo;
}

// --- Admin: members & roles ---------------------------------------------

export type MemberRole = Capability;
export type MemberStatus = "INVITED" | "ACTIVE" | "SUSPENDED";

export interface TenantMember {
  id: string;
  actor_key: string;
  display_name: string;
  email: string;
  role: MemberRole;
  status: MemberStatus;
  created_at: string;
  updated_at: string;
}

export interface TenantMemberList {
  contract_version: "1.0.0";
  members: TenantMember[];
}

export interface MemberInviteRequest {
  actor_key: string;
  display_name?: string;
  email?: string;
  role?: MemberRole;
}

export interface MemberUpdateRequest {
  role?: MemberRole;
  status?: MemberStatus;
}

// --- Admin: connectors ---------------------------------------------------

export type ConnectorProvider =
  | "GITHUB_APP"
  | "PACKAGE_REGISTRY"
  | "DEPS_DEV"
  | "OSV"
  | "OTHER";
export type ConnectorStatus = "CONNECTED" | "NEEDS_REAUTH" | "DISABLED" | "REVOKED";

export interface Connector {
  id: string;
  provider: ConnectorProvider;
  display_name: string;
  external_account_key: string;
  scopes: string[];
  status: ConnectorStatus;
  last_synced_at?: string | null;
  last_error?: string | null;
  created_at: string;
  updated_at: string;
}

export interface ConnectorList {
  contract_version: "1.0.0";
  connectors: Connector[];
}

export interface ConnectorRegisterRequest {
  provider: ConnectorProvider;
  display_name: string;
  external_account_key?: string;
  /** An opaque secret-store reference; a raw token/PAT/password is rejected server-side. */
  credential_reference?: string;
  scopes?: string[];
}

export interface GitHubRepositoryConnectRequest {
  /** GitHub's owner/repository identity. A token is never accepted by this contract. */
  repository: string;
  credential_reference?: "env://GITHUB_TOKEN";
}

export interface ConnectorUpdateRequest {
  display_name?: string;
  status?: ConnectorStatus;
  scopes?: string[];
  credential_reference?: string;
}

// --- Admin: AI provider configuration -----------------------------------

export type AIProvider = "openrouter" | "openai" | "anthropic";
export type AIConnectionTestStatus = "NOT_TESTED" | "SUCCEEDED" | "FAILED";
export type AIEnrichmentStatus = "DISABLED" | "READY" | "QUEUED" | "RUNNING" | "ACTIVE" | "DEGRADED";

export interface AIProviderConfiguration {
  contract_version: "1.0.0";
  provider: AIProvider;
  model: string;
  enabled: boolean;
  key_configured: boolean;
  key_fingerprint?: string | null;
  test_status: AIConnectionTestStatus;
  tested_at?: string | null;
  last_error?: string | null;
  enrichment_status: AIEnrichmentStatus;
  pending_enrichment_jobs: number;
  running_enrichment_jobs: number;
  failed_enrichment_jobs: number;
  last_enrichment_at?: string | null;
  updated_by?: string | null;
  updated_at?: string | null;
}

export interface AIProviderConfigurationUpdateRequest {
  provider: AIProvider;
  model?: string;
  api_key?: string;
  enabled?: boolean;
}

export interface AIProviderConnectionTest {
  contract_version: "1.0.0";
  provider: AIProvider;
  status: "SUCCEEDED";
  models: string[];
}

// --- Admin: scan policy, rescans, and quota ------------------------------

export type ScanCadence = "HOURLY" | "DAILY" | "WEEKLY" | "MANUAL";

export interface ScanPolicy {
  contract_version: "1.0.0";
  cadence: ScanCadence;
  enabled: boolean;
  updated_by?: string | null;
  updated_at?: string | null;
}

export interface ScanPolicyUpdateRequest {
  cadence: ScanCadence;
  enabled?: boolean;
}

export type RescanJobStatus = "PENDING" | "RUNNING" | "SUCCEEDED" | "FAILED";

export interface RescanRequest {
  connector_id?: string | null;
  idempotency_key: string;
  reason?: string;
}

export interface RescanJob {
  id: string;
  connector_id?: string | null;
  status: RescanJobStatus;
  reason: string;
  requested_by: string;
  last_error?: string | null;
  created_at: string;
  started_at?: string | null;
  completed_at?: string | null;
}

export interface RescanJobList {
  contract_version: "1.0.0";
  jobs: RescanJob[];
  page_info: PageInfo;
}

export type QuotaStatus = "OK" | "THROTTLED" | "EXHAUSTED";

export interface ProviderQuota {
  provider: ConnectorProvider;
  used: number;
  limit?: number | null;
  status: QuotaStatus;
  resets_at?: string | null;
  backoff_until?: string | null;
  observed_at: string;
}

export interface ScanStatus {
  contract_version: "1.0.0";
  as_of: string;
  policy: ScanPolicy;
  quotas: ProviderQuota[];
  recent_jobs: RescanJob[];
}
