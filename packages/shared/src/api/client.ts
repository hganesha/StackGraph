// StackGraph read-API client with a pluggable transport.
//
//   fixtures  → resolves from bundled contracts/v1 fixtures (no backend required)
//   live      → fetches /api/v1/* from the real API
//
// Components depend ONLY on this interface, so flipping NEXT_PUBLIC_DATA_SOURCE
// requires no component rewrite. Fixture-first, per plan §7.1.

import { config, isFixtureMode } from "../config";
import type {
  ApplicationDetail,
  RepositoryDetail,
  RepositoryActivity,
  RepositoryActivityWindow,
  AskRequest,
  AskResponse,
  EnterpriseInsightReportList,
  EstateSummary,
  EvidenceDetail,
  GraphNeighborhood,
  IdentityReviewRequest,
  IdentityReviewResult,
  CapabilityTaxonomy,
  RepositoryCapabilityIntelligence,
  OptimisticReviewRequest,
  CapabilityInferenceReviewResult,
  DuplicateCapabilityReviewResult,
  RepositoryModernizationIntelligence,
  ModernizationCandidate,
  ModernizationCandidateReviewResult,
  ModernizationRecommendationReviewRequest,
  ModernizationRecommendationReviewResult,
  ModernizationValidationOutcomeRequest,
  ModernizationValidationOutcomeResult,
  Phase3IntelligenceMetrics,
  ModernizationList,
  DeterministicInsightList,
  DeterministicInsightGovernanceState,
  DeterministicInsightRuleUpdateRequest,
  CapabilityFootprintList,
  ModernizationScenarioRequest,
  ModernizationScenarioResult,
  ModernizationGovernanceState,
  ModernizationPolicyPublishRequest,
  InternalCatalogComponentUpsertRequest,
  CalibrationCorpusPublishRequest,
  EcosystemAdmissionEvaluateRequest,
  EcosystemName,
  TenantCodeFunctionUpsertRequest,
  TenantCodePolicyState,
  TechnologyDetail,
  TechnologyEstateHierarchy,
  BusinessMapList,
  BusinessMapDetail,
  BusinessMapSummary,
  BusinessMapCreateRequest,
  BusinessMapSaveRequest,
  BusinessMapRevisionList,
  SessionInfo,
  ReviewQueue,
  ReviewQueueItemType,
  TenantMemberList,
  TenantMember,
  MemberInviteRequest,
  MemberUpdateRequest,
  ConnectorList,
  Connector,
  ConnectorRegisterRequest,
  GitHubRepositoryConnectRequest,
  GitHubRepositoryOptionList,
  GitHubTokenConfiguration,
  GitHubTokenUpdateRequest,
  GitHubInstallationConnectRequest,
  GitHubInstallationSetupRequest,
  GitHubInstallationSetupResponse,
  ConnectorUpdateRequest,
  AIProviderConfiguration,
  AIProviderConfigurationUpdateRequest,
  AIProviderConnectionTest,
  ScanPolicy,
  ScanPolicyUpdateRequest,
  ScanStatus,
  ServiceStatusList,
  ServiceStatus,
  ServiceControlRequest,
  RescanRequest,
  RescanJob,
  RescanJobList,
  Namespace,
  EntitySummary,
  EntityGraphIntelligence,
  GraphBlastRadius,
  GraphCommunityList,
  GraphIntelligenceStatus,
  GraphRiskList,
  SemanticSearchRequest,
  SemanticSearchResponse,
  EmbeddingStatus,
  ApplicationSimilarityList,
  ApplicationSimilarityReviewRequest,
  ApplicationSimilarityReviewResult,
  ActionPredicate,
  AISupplyChain,
  AgentApprovalDecisionRequest,
  AgentApprovalModel,
  AgentAuthorizationDecisionModel,
  AgentAuthorizeRequest,
  AgentControlDrillRequest,
  AgentControlDrillResult,
  AgentKillSwitchModel,
  AgentKillSwitchUpdateRequest,
  AssumptionCreateRequest,
  AssumptionList,
  AssumptionModel,
  ActionSubjectList,
  ActionTypeList,
  ChangeScopeList,
  CapabilityEnvelopeCompileRequest,
  CapabilityEnvelopeModel,
  ContainerCompositionList,
  ContradictionLedger,
  CriticalGraphEdgeList,
  DeploymentProfileList,
  EstateComponentDetail,
  EstateComponentList,
  EstateStrata,
  EstateLineageList,
  FlightEventCreateRequest,
  FlightRecordCreateRequest,
  FlightRecordFinalizeRequest,
  FlightRecordModel,
  ContradictionResolveRequest,
  GraphAnalysisRequestCreate,
  GraphAnalysisRequestResult,
  GraphAnomalyList,
  GraphMotifList,
  MutationCompileRequest,
  MutationCompileResult,
  MutationValidateRequest,
  ObservedMutationCreateRequest,
  ObservedMutationList,
  ObservedMutationModel,
  ChangeSetCompileRequest,
  RecommendationCompileRequest,
  RepositoryFingerprintList,
  SimulationCreateRequest,
  SimulationRunModel,
  ValidTargetList,
} from "../contracts/read-models";
import type {
  ArchitectureProfileCreateRequest,
  ArchitectureProfileDetail,
  ArchitectureProfileList,
  ArchitectureProfilePublishRequest,
  ArchitectureProfileStateModel,
  ArchitectureProfileSummary,
  ArchitectureProfileUpdateRequest,
  ArchitectureReferenceModel,
  ArchitectureReferenceModelList,
  ArchitectureTaxonomyResponse,
  CanvasComparison,
  CanvasComparisonRequest,
  CanvasProjection,
  CanvasTemplateList,
  CanvasTemplateModel,
  EntityDescriptionUpdateRequest,
} from "../contracts/openapi.generated";

// UI-demo estate (several ranked items across domains) so filter/sort/lens UI is exercisable.
// The golden fixture is contracts/v1/fixtures/estate-summary.json.
import estateSummary from "../fixtures/estate-summary.demo.json";
import applicationDetail from "../fixtures/application-detail.json";
import repositoryDetail from "../fixtures/repository-detail.json";
import repositoryActivity from "../fixtures/repository-activity.json";
import technologyDetail from "../fixtures/technology-detail.json";
import modernizationList from "../fixtures/modernization-list.json";
import askResponse from "../fixtures/ask-response.json";
// UI-demo neighborhood (richer than the golden fixture) so the uncertain-bridge and
// aggregate-cluster UI can be exercised in fixture mode. See the file's _comment.
import graphNeighborhood from "../fixtures/graph-neighborhood.demo.json";
import evidenceDetail from "../fixtures/evidence-detail.json";
import identityReview from "../fixtures/identity-review-result.json";
import capabilityTaxonomy from "../fixtures/capability-taxonomy.json";
import repositoryCapabilities from "../fixtures/repository-capabilities.json";
import repositoryModernization from "../fixtures/repository-modernization-intelligence.json";
import phase3Metrics from "../fixtures/phase3-intelligence-metrics.json";
import businessMapDetail from "../fixtures/business-map-detail.json";
import technologyEstateHierarchy from "../fixtures/technology-estate-hierarchy.json";
import capabilityFootprints from "../fixtures/capability-footprints.json";
import modernizationScenario from "../fixtures/modernization-scenario.json";
import modernizationGovernance from "../fixtures/modernization-governance.json";
import deterministicInsights from "../fixtures/deterministic-insights.json";
import deterministicInsightGovernance from "../fixtures/deterministic-insight-governance.json";
import phase2ActionTypes from "../fixtures/phase2-action-types.json";
import phase2ActionSubjects from "../fixtures/phase2-action-subjects.json";
import phase2ValidTargets from "../fixtures/phase2-valid-targets.json";
import phase2ChangeScopes from "../fixtures/phase2-change-scopes.json";
import phase2MutationCompile from "../fixtures/phase2-mutation-compile.json";
import phase2SimulationRun from "../fixtures/phase2-simulation-run.json";
import phase2ChangeHistory from "../fixtures/phase2-change-history.json";
import phase2RepositoryFingerprints from "../fixtures/phase2-repository-fingerprints.json";
import phase2CriticalEdges from "../fixtures/phase2-critical-edges.json";
import phase2Anomalies from "../fixtures/phase2-anomalies.json";
import phase2Motifs from "../fixtures/phase2-motifs.json";
import phase2AnalysisRequest from "../fixtures/phase2-analysis-request.json";

export interface CanvasProjectionParams {
  scope: "ESTATE" | "APPLICATION" | "REPOSITORY" | "TARGET";
  subjectId?: string;
  referenceModelKey?: string;
  templateKey?: string;
}

export interface CanvasTargetProjectionParams {
  referenceModelKey?: string;
  templateKey?: string;
}

export interface EstateSummaryParams {
  cursor?: string;
  limit?: number;
  domains?: Namespace[];
}

export interface StackGraphClient {
  getEstateSummary(params?: EstateSummaryParams): Promise<EstateSummary>;
  getEstateStrata(): Promise<EstateStrata>;
  getAISupplyChain(): Promise<AISupplyChain>;
  listEstateLineage(entityId?: string, limit?: number): Promise<EstateLineageList>;
  listContradictions(subjectId?: string, limit?: number): Promise<ContradictionLedger>;
  listAssumptions(subjectId?: string, status?: string, limit?: number): Promise<AssumptionList>;
  getAssumption(id: string): Promise<AssumptionModel>;
  createAssumption(body: AssumptionCreateRequest): Promise<AssumptionModel>;
  resolveContradiction(id: string, body: ContradictionResolveRequest): Promise<void>;
  compileCapabilityEnvelope(body: CapabilityEnvelopeCompileRequest): Promise<CapabilityEnvelopeModel>;
  getCapabilityEnvelope(id: string): Promise<CapabilityEnvelopeModel>;
  authorizeAgentOperation(
    id: string, body: AgentAuthorizeRequest,
  ): Promise<AgentAuthorizationDecisionModel>;
  decideAgentApproval(id: string, body: AgentApprovalDecisionRequest): Promise<AgentApprovalModel>;
  getAgentKillSwitch(): Promise<AgentKillSwitchModel>;
  updateAgentKillSwitch(body: AgentKillSwitchUpdateRequest): Promise<AgentKillSwitchModel>;
  createFlightRecord(body: FlightRecordCreateRequest): Promise<FlightRecordModel>;
  getFlightRecord(id: string): Promise<FlightRecordModel>;
  appendFlightEvent(id: string, body: FlightEventCreateRequest): Promise<FlightRecordModel>;
  finalizeFlightRecord(id: string, body: FlightRecordFinalizeRequest): Promise<FlightRecordModel>;
  runAgentControlDrill(body: AgentControlDrillRequest): Promise<AgentControlDrillResult>;
  listComponents(cursor?: string, limit?: number): Promise<EstateComponentList>;
  getComponent(id: string): Promise<EstateComponentDetail>;
  getApplication(id: string): Promise<ApplicationDetail>;
  updateApplication(id: string, body: EntityDescriptionUpdateRequest): Promise<EntitySummary>;
  getRepository(id: string): Promise<RepositoryDetail>;
  listRepositoryContainerCompositions(id: string): Promise<ContainerCompositionList>;
  listRepositoryDeploymentProfiles(id: string): Promise<DeploymentProfileList>;
  updateRepository(id: string, body: EntityDescriptionUpdateRequest): Promise<EntitySummary>;
  getRepositoryActivity(
    id: string,
    params?: { window?: RepositoryActivityWindow; cursor?: string; limit?: number },
  ): Promise<RepositoryActivity>;
  getTechnology(id: string): Promise<TechnologyDetail>;
  getTechnologyEstateHierarchy(): Promise<TechnologyEstateHierarchy>;
  listModernization(): Promise<ModernizationList>;
  listDeterministicInsights(params?: {
    scopeEntityId?: string;
    ruleKey?: string;
    limit?: number;
  }): Promise<DeterministicInsightList>;
  listEnterpriseInsightReports(): Promise<EnterpriseInsightReportList>;
  listCapabilityFootprints(): Promise<CapabilityFootprintList>;
  optimizeModernizationScenario(body: ModernizationScenarioRequest): Promise<ModernizationScenarioResult>;
  ask(body: AskRequest): Promise<AskResponse>;
  getGraphNeighborhood(centerId: string, depth?: number): Promise<GraphNeighborhood>;
  getGraphIntelligenceStatus(): Promise<GraphIntelligenceStatus>;
  getEntityGraphMetrics(id: string): Promise<EntityGraphIntelligence>;
  getEntityBlastRadius(id: string): Promise<GraphBlastRadius>;
  listGraphIntelligenceRisks(limit?: number): Promise<GraphRiskList>;
  listGraphIntelligenceCommunities(policyKey?: string, limit?: number): Promise<GraphCommunityList>;
  semanticSearch(body: SemanticSearchRequest): Promise<SemanticSearchResponse>;
  getEmbeddingStatus(): Promise<EmbeddingStatus>;
  listSimilarApplications(id: string, limit?: number): Promise<ApplicationSimilarityList>;
  reviewApplicationSimilarity(id: string, body: ApplicationSimilarityReviewRequest): Promise<ApplicationSimilarityReviewResult>;
  getFactEvidence(factId: string): Promise<EvidenceDetail>;
  reviewIdentityAssertion(id: string, body: IdentityReviewRequest): Promise<IdentityReviewResult>;
  getCapabilityTaxonomy(version?: string): Promise<CapabilityTaxonomy>;
  getRepositoryCapabilities(id: string): Promise<RepositoryCapabilityIntelligence>;
  reviewCapabilityInference(id: string, body: OptimisticReviewRequest): Promise<CapabilityInferenceReviewResult>;
  reviewDuplicateCapabilityCandidate(id: string, body: OptimisticReviewRequest): Promise<DuplicateCapabilityReviewResult>;
  getRepositoryModernizationIntelligence(id: string, limit?: number): Promise<RepositoryModernizationIntelligence>;
  reviewModernizationCandidate(id: string, body: OptimisticReviewRequest): Promise<ModernizationCandidateReviewResult>;
  reviewModernizationRecommendation(id: string, body: ModernizationRecommendationReviewRequest): Promise<ModernizationRecommendationReviewResult>;
  recordModernizationValidationOutcome(id: string, body: ModernizationValidationOutcomeRequest): Promise<ModernizationValidationOutcomeResult>;
  getPhase3IntelligenceMetrics(): Promise<Phase3IntelligenceMetrics>;
  listBusinessMaps(cursor?: string, limit?: number): Promise<BusinessMapList>;
  createBusinessMap(body: BusinessMapCreateRequest): Promise<BusinessMapDetail>;
  getBusinessMap(id: string): Promise<BusinessMapDetail>;
  saveBusinessMap(id: string, body: BusinessMapSaveRequest): Promise<BusinessMapDetail>;
  archiveBusinessMap(id: string): Promise<BusinessMapSummary>;
  getBusinessMapRevisions(id: string): Promise<BusinessMapRevisionList>;
  getSession(): Promise<SessionInfo>;
  getReviewQueue(params?: {
    types?: ReviewQueueItemType[];
    repository?: string;
    cursor?: string;
    limit?: number;
  }): Promise<ReviewQueue>;
  listMembers(): Promise<TenantMemberList>;
  inviteMember(body: MemberInviteRequest): Promise<TenantMember>;
  updateMember(id: string, body: MemberUpdateRequest): Promise<TenantMember>;
  removeMember(id: string): Promise<TenantMember>;
  listConnectors(): Promise<ConnectorList>;
  registerConnector(body: ConnectorRegisterRequest): Promise<Connector>;
  listAvailableGitHubRepositories(): Promise<GitHubRepositoryOptionList>;
  getGitHubTokenConfiguration(): Promise<GitHubTokenConfiguration>;
  updateGitHubToken(body: GitHubTokenUpdateRequest): Promise<GitHubTokenConfiguration>;
  removeGitHubToken(): Promise<GitHubTokenConfiguration>;
  connectGitHubRepository(body: GitHubRepositoryConnectRequest): Promise<Connector>;
  connectGitHubInstallation(body: GitHubInstallationConnectRequest): Promise<Connector>;
  startGitHubInstallationSetup(body: GitHubInstallationSetupRequest): Promise<GitHubInstallationSetupResponse>;
  updateConnector(id: string, body: ConnectorUpdateRequest): Promise<Connector>;
  removeConnector(id: string): Promise<Connector>;
  getModernizationGovernance(): Promise<ModernizationGovernanceState>;
  getDeterministicInsightGovernance(): Promise<DeterministicInsightGovernanceState>;
  updateDeterministicInsightRule(ruleKey: string, body: DeterministicInsightRuleUpdateRequest): Promise<DeterministicInsightGovernanceState>;
  publishModernizationPolicy(body: ModernizationPolicyPublishRequest): Promise<ModernizationGovernanceState>;
  governInternalCatalogComponent(componentKey: string, body: InternalCatalogComponentUpsertRequest): Promise<ModernizationGovernanceState>;
  publishCalibrationCorpus(body: CalibrationCorpusPublishRequest): Promise<ModernizationGovernanceState>;
  evaluateEcosystemAdmission(ecosystem: EcosystemName, body: EcosystemAdmissionEvaluateRequest): Promise<ModernizationGovernanceState>;
  getTenantCodePolicies(): Promise<TenantCodePolicyState>;
  upsertTenantCodeFunction(functionKey: string, body: TenantCodeFunctionUpsertRequest): Promise<TenantCodePolicyState>;
  evaluateTenantCodePolicies(): Promise<TenantCodePolicyState>;
  getAIProviderConfiguration(): Promise<AIProviderConfiguration>;
  updateAIProviderConfiguration(body: AIProviderConfigurationUpdateRequest): Promise<AIProviderConfiguration>;
  removeAIProviderKey(): Promise<AIProviderConfiguration>;
  testAIProviderConnection(): Promise<AIProviderConnectionTest>;
  getScanPolicy(): Promise<ScanPolicy>;
  updateScanPolicy(body: ScanPolicyUpdateRequest): Promise<ScanPolicy>;
  getScanStatus(): Promise<ScanStatus>;
  getServiceStatus(): Promise<ServiceStatusList>;
  updateServiceControl(serviceKey: string, body: ServiceControlRequest): Promise<ServiceStatus>;
  requestRescan(body: RescanRequest): Promise<RescanJob>;
  listRescans(cursor?: string, limit?: number): Promise<RescanJobList>;

  // ── Phase 2 change compiler and simulation ───────────────────────────────
  listActionTypes(): Promise<ActionTypeList>;
  listActionSubjects(predicate: ActionPredicate, query?: string, limit?: number): Promise<ActionSubjectList>;
  listValidTargets(id: string, limit?: number): Promise<ValidTargetList>;
  listChangeScopes(id: string): Promise<ChangeScopeList>;
  listEntityChangeHistory(id: string, limit?: number): Promise<ObservedMutationList>;
  compileMutation(body: MutationCompileRequest): Promise<MutationCompileResult>;
  validateMutation(body: MutationValidateRequest): Promise<MutationCompileResult>;
  compileModernizationRecommendation(id: string, body: RecommendationCompileRequest): Promise<MutationCompileResult>;
  compileDeterministicInsight(id: string, body: RecommendationCompileRequest): Promise<MutationCompileResult>;
  compileChangeSet(body: ChangeSetCompileRequest): Promise<MutationCompileResult>;
  createSimulation(body: SimulationCreateRequest): Promise<SimulationRunModel>;
  getSimulation(id: string): Promise<SimulationRunModel>;
  cancelSimulation(id: string): Promise<SimulationRunModel>;
  recordObservedMutation(body: ObservedMutationCreateRequest): Promise<ObservedMutationModel>;
  listRepositoryFingerprints(id: string, limit?: number): Promise<RepositoryFingerprintList>;

  // Previously shipped graph-intelligence paths that were not client-reachable.
  listEntityCriticalEdges(id: string): Promise<CriticalGraphEdgeList>;
  listGraphIntelligenceAnomalies(cohortKey?: string, limit?: number): Promise<GraphAnomalyList>;
  listGraphIntelligenceMotifs(motifKey?: string, limit?: number): Promise<GraphMotifList>;
  requestGraphAnalysis(body: GraphAnalysisRequestCreate): Promise<GraphAnalysisRequestResult>;

  // ── Architecture Canvas ──────────────────────────────────────────────────
  // Canvas fixtures are an order of magnitude larger than every other fixture, so the
  // fixture transport loads them through dynamic import(). They land in their own
  // async chunk instead of the shared-by-all bundle the perf budget guards.
  getArchitectureTaxonomy(): Promise<ArchitectureTaxonomyResponse>;
  listCanvasReferenceModels(): Promise<ArchitectureReferenceModelList>;
  getCanvasReferenceModel(key: string, version?: string): Promise<ArchitectureReferenceModel>;
  listCanvasTemplates(): Promise<CanvasTemplateList>;
  getCanvasTemplate(key: string, version?: string): Promise<CanvasTemplateModel>;
  getCanvasProjection(params: CanvasProjectionParams): Promise<CanvasProjection>;
  getCanvasTargetProjection(params?: CanvasTargetProjectionParams): Promise<CanvasProjection>;
  createCanvasComparison(body: CanvasComparisonRequest): Promise<CanvasComparison>;
  listArchitectureProfiles(): Promise<ArchitectureProfileList>;
  createArchitectureProfile(body: ArchitectureProfileCreateRequest): Promise<ArchitectureProfileDetail>;
  updateArchitectureProfile(id: string, body: ArchitectureProfileUpdateRequest): Promise<ArchitectureProfileDetail>;
  publishArchitectureProfile(id: string, body: ArchitectureProfilePublishRequest): Promise<ArchitectureProfileDetail>;
}

/** Simulated latency so loading/skeleton states are exercised in fixture mode. */
const delay = (ms = 120) => new Promise((r) => setTimeout(r, ms));

// Fixture mode keeps the Business Map in memory so the workspace's create/save/list flow is
// fully exercisable without a backend. It mirrors the server's optimistic-concurrency contract.
class FixtureApiError extends Error {
  constructor(public status: number, public detail: unknown) {
    super(`StackGraph API ${status}`);
    this.name = "ApiRequestError";
  }
}
const clone = <T,>(value: T): T => JSON.parse(JSON.stringify(value)) as T;

// The assurance-coverage report scores each scan dimension on its own row, so the
// fixture carries a real coverage table rather than the shared Ask fixture.
const assuranceCoverageResponse = (): AskResponse => ({
  contract_version: "1.0.0",
  text:
    "78% of the 18 repositories in this estate are analytically covered. Scan freshness, " +
    "analyzable ecosystems, evidence completeness, connector health, and repository " +
    "availability are scored separately so a gap can be attributed to the dimension that caused it.",
  citations: [],
  result_kind: "TABLE",
  rows: [
    { dimension: "Analytically covered estate", scope: "Repositories", covered: 14, in_scope: 18, coverage_percent: 78, status: "PARTIAL", detail: "Repositories that are scanned, fresh, free of unanalyzable ecosystems, backed by evidence, and reachable." },
    { dimension: "Scan freshness", scope: "Repositories", covered: 17, in_scope: 18, coverage_percent: 94, status: "PARTIAL", detail: "Connector freshness state is FRESH and not past its expected refresh." },
    { dimension: "Analyzable ecosystems", scope: "Repositories", covered: 15, in_scope: 18, coverage_percent: 83, status: "UNSUPPORTED", detail: "Analyzable: NPM, PYPI. Not yet analyzable: CARGO, MAVEN." },
    { dimension: "Evidence completeness", scope: "Current facts", covered: 2140, in_scope: 2204, coverage_percent: 97, status: "PARTIAL", detail: "Current facts that carry at least one evidence locator." },
    { dimension: "Connector health", scope: "Connectors", covered: 3, in_scope: 3, coverage_percent: 100, status: "COVERED", detail: "Connectors reporting CONNECTED without a recorded error." },
    { dimension: "Repository availability", scope: "Repositories", covered: 18, in_scope: 18, coverage_percent: 100, status: "COVERED", detail: "Repositories whose ingest target is enabled and unarchived, with no failed run since the last success." },
  ],
});

// The golden contract fixture for repository-modernization-intelligence carries an empty
// candidates array (it exists to validate the schema, not to demo a page). Its recommendation
// id matches modernization-scenario.json's "Consolidate billing HTTP clients" item, so the
// dashboard's recommended-plan link and the Reviews queue's MODERNIZATION_RECOMMENDATION row
// both resolve to this candidate, exercising the recommendation focus page end to end.
const demoModernizationCandidate: ModernizationCandidate = {
  id: "00000000-0000-4000-8000-000000000910",
  source_revision: "revision-1",
  kind: "INTERNAL_DUPLICATION",
  subjects: [{ id: "00000000-0000-4000-8000-000000000701", kind: "Repository", name: "billing-api", canonical_key: "github:repo:billing-api" }],
  confidence: 0.9,
  summary: "Three internal HTTP client wrappers implement the same retry and auth logic.",
  supporting_fact_ids: ["70000000-0000-4000-8000-000000000021", "70000000-0000-4000-8000-000000000022"],
  counter_evidence_fact_ids: [],
  source_locations: [
    { path: "src/billing/http/retryClient.ts", repository_id: "00000000-0000-4000-8000-000000000701", symbol: "RetryClient" },
    { path: "src/billing/http/authWrapper.ts", repository_id: "00000000-0000-4000-8000-000000000701", symbol: "AuthWrapper" },
  ],
  validation_gaps: ["2 affected call sites have no statically linked test file."],
  analyzer: { key: "modernization.consolidation", version: "1.0.0" },
  review_state: "CONFIRMED",
  version: 1,
  stale: false,
  options: [],
  recommendation: {
    id: "00000000-0000-4000-8000-000000000911",
    action: "CONSOLIDATE",
    objective: "Reduce duplicated HTTP client implementations",
    title: "Consolidate billing HTTP clients",
    rationale: "Three internal wrappers duplicate the platform HTTP client's retry and auth behavior.",
    confidence: 0.9,
    estimated_effort: "MEDIUM",
    affected_call_sites: 14,
    affected_files: 6,
    validation_gaps: ["2 affected call sites have no statically linked test file."],
    migration_plan: [
      "Inventory call sites of RetryClient and AuthWrapper across billing-service.",
      "Swap call sites to the platform HTTP client one module at a time, starting with read-only endpoints.",
      "Remove the vendored wrappers once no call sites remain.",
    ],
    rollback_plan: [
      "Revert the call-site swap commit for the affected module.",
      "Re-add the vendored wrapper import until the platform client issue is resolved.",
    ],
    supporting_fact_ids: ["70000000-0000-4000-8000-000000000021", "70000000-0000-4000-8000-000000000022"],
    counter_evidence_fact_ids: [],
    counter_signals: [],
    policy_version: "modernization.portfolio/1.0.0",
    review_state: "UNREVIEWED",
    version: 1,
    stale: false,
    created_at: "2026-08-21T14:00:00.000Z",
  },
};

// Fixture-mode: a human-set description overrides the golden fixture's summary, same
// as `curated_description` overriding discovery in the real properties column.
let applicationDescriptionOverride: string | null = null;
let repositoryDescriptionOverride: string | null = null;

// Fixture-mode admin state so the Admin surface's CRUD is exercisable without a backend.
// Seeded to mirror the previous mock sections so the demo looks unchanged on first load.
const adminMembers = new Map<string, TenantMember>();
const adminConnectors = new Map<string, Connector>();
const adminRescans = new Map<string, { idempotencyKey: string; job: RescanJob }>();
const adminServiceStates = new Map<string, "RUNNING" | "STOPPED">();
let adminScanPolicy: ScanPolicy = { contract_version: "1.0.0", cadence: "DAILY", enabled: true };
let adminAIConfiguration: AIProviderConfiguration = {
  contract_version: "1.0.0", provider: "anthropic", model: "", enabled: true,
  key_configured: false, test_status: "NOT_TESTED", enrichment_status: "DISABLED",
  pending_enrichment_jobs: 0, running_enrichment_jobs: 0, failed_enrichment_jobs: 0,
};
let adminGitHubTokenConfiguration: GitHubTokenConfiguration = {
  contract_version: "1.0.0", configured: true, fingerprint: "demo",
  source: "ENVIRONMENT",
};
let adminModernizationGovernance = clone(
  modernizationGovernance as ModernizationGovernanceState,
);
let adminDeterministicInsightGovernance = clone(
  deterministicInsightGovernance as DeterministicInsightGovernanceState,
);
let adminCodePolicies: TenantCodePolicyState = {
  contract_version: "1.0.0",
  policy_set_fingerprint: "sha256:1111111111111111111111111111111111111111111111111111111111111111",
  functions: [
    {
      function_key: "client-state-management", name: "Client state management",
      description: "Manage UI-local state that is not authoritative server data.",
      domain_key: "frontend", source: "PRIMARY", status: "ACTIVE",
      policy: {
        id: "00000000-0000-4000-8000-000000000c01",
        allowed_technology_ids: ["00000000-0000-4000-8000-000000000c11"],
        prohibited_technology_ids: ["00000000-0000-4000-8000-000000000c12"],
        policy_fingerprint: "sha256:2222222222222222222222222222222222222222222222222222222222222222",
        updated_by: "fixture-admin", updated_at: "2026-08-21T12:00:00.000Z",
      },
    },
    {
      function_key: "tenant-design-tokens", name: "Tenant design tokens",
      description: "Distribute tenant-approved visual design decisions.",
      domain_key: "frontend", source: "CUSTOM", status: "ACTIVE",
    },
  ],
  available_technologies: [
    {
      technology: { id: "00000000-0000-4000-8000-000000000c11", kind: "Technology", name: "Zustand", canonical_key: "stackgraph:technology:zustand" },
      classification: "CURATED", domain_key: "frontend", category_key: "client-state", detected_repository_count: 4,
    },
    {
      technology: { id: "00000000-0000-4000-8000-000000000c12", kind: "Technology", name: "Redux", canonical_key: "stackgraph:technology:redux" },
      classification: "CURATED", domain_key: "frontend", category_key: "client-state", detected_repository_count: 2,
    },
  ],
  technology_catalog_truncated: false,
  evaluations: [],
  summary: {
    governed_functions: 1, custom_functions: 1, evaluated_repositories: 0,
    compliant_repositories: 0, misaligned_repositories: 0, stale_repositories: 0,
  },
};

// Phase 2 fixture state models the public lifecycle instead of returning a finished
// result from POST. This keeps polling, cancellation, replay, and non-terminal UI
// states testable without a running worker.
const fixtureSimulations = new Map<string, { run: SimulationRunModel; reads: number }>();
const fixtureSimulationByKey = new Map<string, string>();
const fixtureEnvelopes = new Map<string, CapabilityEnvelopeModel>();
const fixtureFlights = new Map<string, FlightRecordModel>();
const fixtureAssumptions = new Map<string, AssumptionModel>();
let fixtureKillSwitch: AgentKillSwitchModel = {
  contract_version: "1.0.0", engaged: true,
  reason: "Agent execution is disabled until explicitly enabled.", version: 0,
  updated_by: "system:default-deny", updated_at: "2026-09-05T18:00:00Z",
};

function fixtureBlockedCompile(
  request: MutationCompileRequest,
  code: string,
  field: string,
  message: string,
  candidates: ActionSubjectList["subjects"] = [],
): MutationCompileResult {
  const base = clone(phase2MutationCompile as MutationCompileResult);
  const subjectLabel = request.subject_query?.trim() || request.intent?.trim() || "Unresolved subject";
  base.command_state = candidates.length ? "TOKENISED" : "RESOLVING";
  base.change_set = null;
  base.gate = { state: "BLOCKED", reasons: [{ code, message, evidence_fact_ids: [] }] };
  base.draft.lifecycle = "REJECTED";
  base.draft.validation_errors = [{ code, field, message, evidence_fact_ids: [] }];
  base.draft.subject = {
    state: candidates.length ? "INFERRED" : "UNRESOLVED",
    entity: null,
    confidence: candidates.length ? 0.68 : 0,
    method: candidates.length ? "structural_match" : "no_match",
    method_version: "identity/2.1.0",
    evidence_fact_ids: candidates.flatMap((item) => item.evidence_fact_ids ?? []),
    candidates: candidates.map((item, index) => ({
      entity: item.entity,
      confidence: Math.max(0.5, 0.78 - index * 0.08),
      method: `estate_${item.entity.kind.toLowerCase()}_match`,
    })),
  };
  base.draft.provenance = { entry_point: request.intent ? "COMMAND" : "API", input: subjectLabel };
  return base;
}

function fixtureCompile(request: MutationCompileRequest): MutationCompileResult {
  const intent = request.intent?.trim();
  if (intent) {
    const match = /^upgrade\s+(.+?)\s+to\s+([^\s]+)(?:\s+(?:in|within)\s+(.+))?$/i.exec(intent);
    if (!match) {
      return fixtureBlockedCompile(
        request,
        "UNSUPPORTED_INTENT",
        "intent",
        "Use the bounded form ‘Upgrade <package> to <exact version> [in <scope>]’.",
      );
    }
    const subjectText = match[1].trim();
    const subjects = (phase2ActionSubjects as ActionSubjectList).subjects.filter((item) =>
      item.entity.name.toLowerCase().includes(subjectText.toLowerCase()),
    );
    if (subjects.length !== 1) {
      return fixtureBlockedCompile(
        { ...request, subject_query: subjectText },
        "SUBJECT_NOT_RESOLVED",
        "subject",
        subjects.length
          ? "Choose one exact canonical package; inferred candidates cannot compile."
          : `No estate entity matches ‘${subjectText}’. StackGraph can only change things it has found.`,
        subjects,
      );
    }
    request = {
      ...request,
      predicate: "UPGRADE",
      subject_id: subjects[0].entity.id,
      target_version: match[2],
      scope_id: match[3]?.toLowerCase() === "estate" || !match[3] ? "scope:estate" : match[3],
    };
  }
  const target = (phase2ValidTargets as ValidTargetList).targets.find(
    (item) => item.version === request.target_version && item.version !== "latest",
  );
  if (!request.subject_id) {
    return fixtureBlockedCompile(request, "SUBJECT_NOT_RESOLVED", "subject", "Choose one exact canonical package.");
  }
  if (!target) {
    return fixtureBlockedCompile(
      request,
      "TARGET_NOT_RESOLVED",
      "target_version",
      request.target_version === "latest"
        ? "Latest is a mutable alias. Choose an exact immutable version before simulation."
        : "Choose an exact registry-backed target version.",
    );
  }
  const scope = (phase2ChangeScopes as ChangeScopeList).scopes.find((item) => item.id === request.scope_id);
  if (!scope) {
    return fixtureBlockedCompile(request, "SCOPE_NOT_RESOLVED", "scope_id", "Choose a scope backed by current dependency evidence.");
  }
  const result = clone(phase2MutationCompile as MutationCompileResult);
  result.draft.scope = clone(scope);
  result.draft.after = { version: target.version, target_entity_id: target.entity_id, canonical_key: target.canonical_key };
  result.draft.before = { versions: clone(scope.version_distribution) };
  if (result.change_set) {
    result.change_set.mutations = [clone(result.draft)];
    result.change_set.input_fingerprint = `sha256:fixture-${request.subject_id}-${target.version}-${scope.id}`;
  }
  result.replayed = request.idempotency_key.startsWith("replay:");
  return result;
}

function fixtureSimulationVariant(id: string): SimulationRunModel | null {
  const match = /^25000000-0000-4000-8000-00000000000([1-8])$/.exec(id);
  if (!match) return null;
  const run = clone(phase2SimulationRun as SimulationRunModel);
  run.id = id;
  const variant = Number(match[1]);
  if (variant === 2) {
    run.status = "LIMITED";
    run.limitations = [{
      code: "PARTIAL_SCAN",
      message: "Seven repositories were beyond the active scan freshness policy.",
      evidence_fact_ids: ["70000000-0000-4000-8000-000000000121"],
    }];
    run.gate = { state: "CONSTRAIN", reasons: clone(run.limitations) };
  } else if (variant === 3) {
    run.status = "NOT_SIMULATABLE";
    run.findings = [];
    run.result_hash = null;
    run.limitations = [{ code: "GRAPH_WATERMARK_STALE", message: "No eligible graph snapshot covers this ChangeSet.", evidence_fact_ids: [] }];
    run.gate = { state: "BLOCKED", reasons: clone(run.limitations) };
    run.interpretation = { status: "UNAVAILABLE", limitation: "Interpretation did not run because deterministic simulation was unavailable." };
  } else if (variant === 4) {
    run.status = "FAILED";
    run.findings = [];
    run.result_hash = null;
    run.limitations = [{ code: "WORKER_FAILURE", message: "The simulation worker ended before producing a stable result.", evidence_fact_ids: [] }];
    run.gate = { state: "BLOCKED", reasons: clone(run.limitations) };
    run.interpretation = { status: "UNAVAILABLE", limitation: "No completed deterministic result was available to interpret." };
  } else if (variant === 5) {
    run.status = "CANCELLED";
    run.findings = [];
    run.result_hash = null;
    run.limitations = [{ code: "RUN_CANCELLED", message: "The run was cancelled before traversal completed.", evidence_fact_ids: [] }];
    run.gate = { state: "BLOCKED", reasons: clone(run.limitations) };
    run.interpretation = { status: "UNAVAILABLE", limitation: "Cancelled runs are not interpreted." };
  } else if (variant === 6) {
    run.interpretation = { status: "QUARANTINED", limitation: "Generated claims did not cite the deterministic findings above.", cited_finding_ids: [] };
  } else if (variant === 7) {
    run.interpretation = { status: "UNAVAILABLE", limitation: "AI interpretation is disabled for this tenant.", cited_finding_ids: [] };
  } else if (variant === 8) {
    run.replayed = true;
  }
  return run;
}
{
  const now = "2026-08-19T12:00:00.000Z";
  for (const seed of [
    { actor_key: "hariganesh@msn.com", display_name: "You", role: "admin", status: "ACTIVE" },
    { actor_key: "dana@acme.example", display_name: "Dana Okafor", role: "execute", status: "ACTIVE" },
    { actor_key: "priya@acme.example", display_name: "Priya Raman", role: "review", status: "ACTIVE" },
    { actor_key: "sam@acme.example", display_name: "Sam Lee", role: "view", status: "ACTIVE" },
  ] as const) {
    const id = `seed-${seed.actor_key}`;
    adminMembers.set(id, {
      id, actor_key: seed.actor_key, display_name: seed.display_name, email: seed.actor_key,
      role: seed.role, status: seed.status, created_at: now, updated_at: now,
    });
  }
  for (const seed of [
    { provider: "GITHUB_APP", display_name: "acme-corp (GitHub org)", scopes: ["repo:read", "metadata:read"], status: "CONNECTED" },
    { provider: "PACKAGE_REGISTRY", display_name: "npm-public", scopes: ["PUBLIC"], status: "CONNECTED" },
    { provider: "PACKAGE_REGISTRY", display_name: "artifactory-internal", scopes: ["PRIVATE"], status: "NEEDS_REAUTH" },
  ] as const) {
    const id = `seed-${seed.display_name}`;
    adminConnectors.set(id, {
      id, provider: seed.provider, display_name: seed.display_name, external_account_key: "",
      scopes: [...seed.scopes], status: seed.status, created_at: now, updated_at: now,
    });
  }
}
const businessMaps = new Map<string, BusinessMapDetail>();
const businessMapRevisions = new Map<string, BusinessMapRevisionList["revisions"]>();
{
  const seed = clone(businessMapDetail as BusinessMapDetail);
  businessMaps.set(seed.id, seed);
  businessMapRevisions.set(seed.id, [
    { version: 1, actor_key: "fixture", created_at: seed.created_at },
  ]);
}
const summarize = (m: BusinessMapDetail): BusinessMapSummary => ({
  id: m.id,
  map_key: m.map_key,
  title: m.state.title,
  view_mode: m.state.view_mode,
  template_id: m.state.template_id,
  status: m.status,
  version: m.version,
  created_at: m.created_at,
  updated_at: m.updated_at,
});


// ─── Architecture Canvas fixture state ───────────────────────────────────────
// These fixtures are generated from the SERVER's canonical catalog by
// scripts/generate_canvas_fixtures.mjs, so fixture mode cannot drift from the shapes
// and cell keys the API actually publishes. They load through dynamic import() and
// land in their own async chunk rather than the shared-by-all bundle.

interface CanvasFixtureBundle {
  taxonomy: ArchitectureTaxonomyResponse;
  referenceModel: ArchitectureReferenceModel;
  template: CanvasTemplateModel;
  estate: CanvasProjection;
  application: CanvasProjection;
  target: CanvasProjection;
  comparison: CanvasComparison;
  /** Revision history, newest last. The Admin surface exists to show this. */
  profiles: ArchitectureProfileDetail[];
}

let canvasBundle: Promise<CanvasFixtureBundle> | null = null;

function loadCanvasFixtures(): Promise<CanvasFixtureBundle> {
  canvasBundle ??= Promise.all([
    import("../fixtures/canvas-taxonomy.json"),
    import("../fixtures/canvas-reference-model.json"),
    import("../fixtures/canvas-template.json"),
    import("../fixtures/canvas-projection-estate.json"),
    import("../fixtures/canvas-projection-application.json"),
    import("../fixtures/canvas-projection-target.json"),
    import("../fixtures/canvas-comparison.json"),
    import("../fixtures/canvas-architecture-profile.json"),
  ]).then(([taxonomy, model, template, estate, application, target, comparison, profile]) => ({
    taxonomy: clone(taxonomy.default as unknown as ArchitectureTaxonomyResponse),
    referenceModel: clone(model.default as unknown as ArchitectureReferenceModel),
    template: clone(template.default as unknown as CanvasTemplateModel),
    estate: clone(estate.default as unknown as CanvasProjection),
    application: clone(application.default as unknown as CanvasProjection),
    target: clone(target.default as unknown as CanvasProjection),
    comparison: clone(comparison.default as unknown as CanvasComparison),
    profiles: [clone(profile.default as unknown as ArchitectureProfileDetail)],
  }));
  return canvasBundle;
}

/** Deterministic v4-shaped identifier, so fixture ids look like the real ones. */
const uuidFromSeed = (seed: string) => {
  let hash = 2166136261;
  const bytes: string[] = [];
  for (let index = 0; index < 32; index += 1) {
    hash ^= seed.charCodeAt(index % seed.length) + index;
    hash = Math.imul(hash, 16777619);
    bytes.push(((hash >>> 24) & 0xf).toString(16));
  }
  const hex = bytes.join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-4${hex.slice(13, 16)}-8${hex.slice(17, 20)}-${hex.slice(20, 32)}`;
};

const canvasFingerprint = (seed: string) => {
  let hash = 2166136261;
  for (let index = 0; index < seed.length; index += 1) {
    hash ^= seed.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return `sha256:${(hash >>> 0).toString(16).repeat(8).slice(0, 64)}`;
};

/** The revision in force, which is what every projection resolves against. */
function activeProfile(bundle: CanvasFixtureBundle): ArchitectureProfileDetail {
  return (
    bundle.profiles.find((entry) => entry.status === "ACTIVE") ??
    bundle.profiles[bundle.profiles.length - 1]
  );
}

const CANVAS_DECISION_FIELDS = [
  ["PREFERRED", "preferred_technology_ids"],
  ["ALLOWED", "allowed_technology_ids"],
  ["DISCOURAGED", "discouraged_technology_ids"],
  ["PROHIBITED", "prohibited_technology_ids"],
] as const;

/**
 * Re-derives the target projection from a profile's cell policies. The server does
 * this properly; the fixture keeps the two consistent enough that the UI's
 * mutate-then-refetch path is exercised for real.
 */
function applyProfileToTarget(
  target: CanvasProjection,
  profile: ArchitectureProfileDetail,
): CanvasProjection {
  // Every technology a policy references has to resolve to a name. The tray matters
  // here specifically: a policy migrated off the tray onto a cell names technologies
  // that appear in no cell yet.
  const known = new Map<string, CanvasProjection["cells"][number]["occupants"][number]["technology"]>();
  for (const cell of target.cells) {
    for (const occupant of cell.occupants) known.set(occupant.technology.id, occupant.technology);
  }
  for (const item of target.classification_tray.items ?? []) known.set(item.entity.id, item.entity);

  const policies = new Map(
    (profile.state.cell_policies ?? []).map((policy) => [policy.cell_key, policy]),
  );

  const cells = target.cells.map((cell) => {
    const policy = policies.get(cell.cell_key);
    if (!policy) {
      return {
        ...clone(cell),
        state: "EMPTY" as const,
        state_reason: "No target decision has been recorded for this concern.",
        occupants: [],
        occupant_total: 0,
        unique_technology_total: 0,
        policy: null,
      };
    }
    const decisions = CANVAS_DECISION_FIELDS.flatMap(([decision, field]) =>
      (policy[field] ?? []).map((id) => ({ id, decision })),
    );
    const notApplicable = policy.applicability === "NOT_APPLICABLE";
    return {
      ...clone(cell),
      state: (notApplicable ? "NOT_APPLICABLE" : decisions.length ? "POPULATED" : "EMPTY") as
        CanvasProjection["cells"][number]["state"],
      state_reason: notApplicable
        ? "The active profile marks this concern not applicable for this scope."
        : decisions.length
          ? `${decisions.length} governed technology decision${decisions.length === 1 ? "" : "s"}.`
          : "No target decision has been recorded for this concern.",
      occupants: decisions.map(({ id, decision }) => ({
        technology: known.get(id) ?? { id, kind: "Technology", name: `Unnamed technology · ${id.slice(0, 8)}` },
        placement_keys: [],
        classification: "CURATED" as const,
        confidence: 1,
        confidence_label: "HIGH" as const,
        adoption_applications: 0,
        adoption_repositories: 0,
        adoption_deployments: 0,
        policy_status: decision,
        policy_reference: null,
        citations: [{ fact_id: profile.id, label: "Tenant architecture profile decision" }],
      })),
      occupant_total: decisions.length,
      unique_technology_total: new Set(decisions.map((d) => d.id)).size,
      expectation: {
        applicability: policy.applicability,
        minimum_implementations: policy.minimum_implementations,
        maximum_implementations: policy.maximum_implementations,
        allowed_diversity: policy.allowed_diversity,
      },
      policy: clone(policy),
    };
  });

  const count = (state: string) => cells.filter((cell) => cell.state === state).length;
  return {
    ...target,
    tenant_profile_fingerprint: profile.fingerprint,
    cells,
    summary: {
      ...target.summary,
      populated_cells: count("POPULATED"),
      empty_cells: count("EMPTY"),
      not_applicable_cells: count("NOT_APPLICABLE"),
      unobserved_cells: count("UNOBSERVED"),
      unbound_cells: count("UNBOUND"),
      governed_cells: cells.filter((cell) => cell.policy).length,
      technology_cell_placements: cells.reduce((sum, cell) => sum + cell.occupants.length, 0),
    },
  };
}


function fixtureEntityGraphIntelligence(id: string): EntityGraphIntelligence {
  const asOf = "2026-08-23T12:00:00Z";
  const entity = { ...applicationDetail.application, id };
  const snapshot = {
    analysis_run_id: "90000000-0000-4000-8000-000000000001",
    policy_key: "runtime-dependency",
    policy_version: 2,
    policy_hash: `sha256:${"a".repeat(64)}`,
    status: "SUCCEEDED" as const,
    as_of: asOf,
    requested_change_watermark: 142,
    neo4j_projection_watermark: 142,
    node_count: 148,
    edge_count: 231,
    coverage: { entity_types: ["Application", "Repository", "Service", "Technology"] },
    limitations: [],
  };
  return {
    contract_version: "1.0.0",
    entity,
    primary_status: "STRUCTURALLY_CRITICAL",
    reasons: [
      "Upstream impact is in the top 10% of the observed estate.",
      "This application bridges otherwise separate runtime components.",
    ],
    snapshots: [snapshot],
    metrics: [
      { analysis_run_id: snapshot.analysis_run_id, policy_key: snapshot.policy_key, metric_key: "reachability.upstream_impact", numeric_value: 24, percentile: 0.92, rank: 3, components: { maximum_depth: 4 }, limitations: [] },
      { analysis_run_id: snapshot.analysis_run_id, policy_key: snapshot.policy_key, metric_key: "reachability.downstream_dependencies", numeric_value: 17, percentile: 0.81, rank: 7, components: { maximum_depth: 3 }, limitations: [] },
      { analysis_run_id: snapshot.analysis_run_id, policy_key: snapshot.policy_key, metric_key: "centrality.pagerank", numeric_value: 0.031, percentile: 0.88, rank: 5, components: {}, limitations: [] },
      { analysis_run_id: snapshot.analysis_run_id, policy_key: snapshot.policy_key, metric_key: "structure.articulation_point", numeric_value: 1, percentile: 0.95, rank: 2, components: {}, limitations: [] },
    ],
    community_keys: ["runtime:12"],
    as_of: asOf,
    limitations: [],
  };
}

function fixtureGraphStatus(): GraphIntelligenceStatus {
  const intelligence = fixtureEntityGraphIntelligence(applicationDetail.application.id);
  return {
    contract_version: "1.0.0",
    as_of: intelligence.as_of,
    deployment_state: "ACTIVE",
    desired_change_watermark: 142,
    neo4j_projection_watermark: 142,
    projection_lag: 0,
    pending_requests: 0,
    running_requests: 0,
    failed_requests: 0,
    oldest_pending_at: null,
    snapshots: intelligence.snapshots,
    limitations: [],
  };
}

function fixtureEmbeddingStatus(): EmbeddingStatus {
  const now = new Date().toISOString();
  return {
    contract_version: "1.0.0",
    as_of: now,
    enabled: true,
    provider: "deterministic-local",
    model: "hash-embedding-v1",
    pending_jobs: 0,
    running_jobs: 0,
    failed_jobs: 0,
    active_spaces: [{
      id: "00000000-0000-4000-8000-000000000701",
      space_key: "entity-semantic",
      space_kind: "SEMANTIC_ENTITY",
      lifecycle_state: "ACTIVE",
      provider: "deterministic-local",
      model_or_algorithm: "hash-embedding-v1",
      dimensions: 384,
      template_version: "entity-document/v1",
      coverage_ratio: 1,
      evaluation: { passed: true, fixture: true },
      updated_at: now,
    }],
    shadow_spaces: [],
    limitations: [],
  };
}

function fixtureApplicationSimilarity(id: string): ApplicationSimilarityList {
  const now = new Date().toISOString();
  return {
    contract_version: "1.0.0",
    subject: { ...applicationDetail.application, id },
    candidates: [{
      id: "00000000-0000-4000-8000-000000000702",
      application: {
        id: "00000000-0000-4000-8000-000000000703",
        kind: "Application",
        name: "Ledger API",
        canonical_key: "application:ledger-api",
      },
      score: 0.82,
      method_version: "application-similarity/v1",
      components: { semantic: 0.79, dependencies: 0.88, capabilities: 0.8 },
      overlaps: {
        capabilities: ["Billing and invoicing"],
        technologies: ["Node.js", "PostgreSQL"],
        dependencies: ["payments-events"],
      },
      differences: {
        capabilities: ["Ledger API also owns financial reconciliation"],
        technologies: ["Ledger API uses Kafka; Billing API uses SQS"],
      },
      coverage: { semantic: 1, dependencies: 1, capabilities: 1 },
      limitations: [],
      review_state: "UNREVIEWED",
      created_at: now,
    }],
    as_of: now,
    limitations: [],
  };
}

const fixtureClient: StackGraphClient = {
  async getEstateSummary(params) {
    await delay();
    const summary = clone(estateSummary as EstateSummary);
    if (params?.domains?.length) {
      summary.ranked_items = summary.ranked_items.filter((item) =>
        params.domains?.includes(item.domain),
      );
    }
    const start = Number.parseInt(params?.cursor ?? "0", 10) || 0;
    const limit = params?.limit ?? summary.ranked_items.length;
    const allItems = summary.ranked_items;
    const end = Math.min(start + limit, allItems.length);
    summary.ranked_items = allItems.slice(start, end);
    summary.page_info = {
      has_next_page: end < allItems.length,
      next_cursor: end < allItems.length ? String(end) : null,
    };
    return summary;
  },
  async getEstateStrata() {
    await delay();
    const fixture = await import("../fixtures/phase2-estate-strata.json");
    return clone(fixture.default as EstateStrata);
  },
  async getAISupplyChain() {
    await delay();
    const fixture = await import("../fixtures/phase2-ai-supply-chain.json");
    return clone(fixture.default as AISupplyChain);
  },
  async listEstateLineage(entityId, limit = 100) {
    await delay();
    const fixture = await import("../fixtures/phase2-estate-lineage.json");
    const result = clone(fixture.default as EstateLineageList);
    result.edges = result.edges
      .filter((edge) => !entityId || edge.upstream.id === entityId || edge.downstream.id === entityId)
      .slice(0, limit);
    return result;
  },
  async listAssumptions(subjectId, status, limit = 50) {
    await delay();
    const fixture = await import("../fixtures/phase2-assumptions.json");
    const result = clone(fixture.default as AssumptionList);
    result.assumptions = [...fixtureAssumptions.values(), ...result.assumptions]
      .filter((item) => !subjectId || item.subject.id === subjectId)
      .filter((item) => !status || item.status === status)
      .slice(0, limit)
      .map(clone);
    return result;
  },
  async getAssumption(id) {
    await delay();
    const assumption = fixtureAssumptions.get(id);
    if (!assumption) {
      throw new FixtureApiError(404, { code: "ASSUMPTION_NOT_FOUND", message: "The assumption was not found." });
    }
    return clone(assumption);
  },
  async createAssumption(body) {
    await delay();
    const now = new Date().toISOString();
    const id = globalThis.crypto?.randomUUID?.() ?? `fixture-assumption-${fixtureAssumptions.size + 1}`;
    const assumption: AssumptionModel = {
      id,
      authority: body.authority,
      confidence: body.confidence,
      dependent_entity_ids: body.dependent_entity_ids ?? [],
      dimension: body.dimension,
      statement: body.statement,
      last_verified_at: body.last_verified_at,
      status: "OPEN",
      subject: { ...applicationDetail.application, id: body.subject_entity_id },
      claims: (body.claims ?? []).map((claim, index) => ({
        ...claim, id: `${id}:claim:${index + 1}`,
      })),
      contradiction_ids: [],
      created_at: now,
      updated_at: now,
      version: 1,
    };
    fixtureAssumptions.set(id, assumption);
    return clone(assumption);
  },
  async resolveContradiction() {
    await delay();
  },
  async compileCapabilityEnvelope(body) {
    await delay();
    const fixture = await import("../fixtures/phase2-capability-envelope.json");
    const id = globalThis.crypto?.randomUUID?.() ?? `fixture-envelope-${fixtureEnvelopes.size + 1}`;
    const now = new Date();
    const envelope: CapabilityEnvelopeModel = {
      ...clone(fixture.default as CapabilityEnvelopeModel),
      id,
      objective: body.objective,
      environment: body.environment,
      estate_watermark: body.estate_watermark,
      risk_tier: body.risk_tier,
      context_confidence: body.context_confidence,
      evidence_fact_ids: body.evidence_fact_ids ?? [],
      bands: (["READ", "EXECUTE", "CONDITIONAL", "PROHIBITED", "ESCALATE"] as const).map((band) => ({
        band,
        operations: body.operations
          .filter((operation) => operation.requested_band === band)
          .map((operation) => ({ operation_key: operation.operation_key, band, constraints: operation.constraints ?? {} })),
      })),
      created_at: now.toISOString(),
      valid_until: new Date(now.getTime() + (body.ttl_seconds ?? 900) * 1000).toISOString(),
    };
    fixtureEnvelopes.set(id, envelope);
    return clone(envelope);
  },
  async getCapabilityEnvelope(id) {
    await delay();
    const envelope = fixtureEnvelopes.get(id);
    if (!envelope) throw new FixtureApiError(404, { code: "ENVELOPE_NOT_FOUND", message: "The capability envelope was not found." });
    return clone(envelope);
  },
  async authorizeAgentOperation(id, body) {
    await delay();
    const envelope = fixtureEnvelopes.get(id);
    if (!envelope) throw new FixtureApiError(404, { code: "ENVELOPE_NOT_FOUND", message: "The capability envelope was not found." });
    const operation = envelope.bands.flatMap((band) => band.operations ?? []).find((item) => item.operation_key === body.operation_key);
    const decision = fixtureKillSwitch.engaged ? "DENY" : operation?.band === "READ" ? "ALLOW" : "ESCALATE";
    return {
      id: globalThis.crypto?.randomUUID?.() ?? `fixture-authorization-${Date.now()}`,
      envelope_id: id,
      operation_key: body.operation_key,
      decision,
      reason_codes: fixtureKillSwitch.engaged ? ["KILL_SWITCH_ENGAGED"] : operation ? [] : ["OPERATION_NOT_IN_ENVELOPE"],
      request_fingerprint: `fixture:${body.operation_key}`,
      decided_at: new Date().toISOString(),
    } satisfies AgentAuthorizationDecisionModel;
  },
  async decideAgentApproval(id, body) {
    await delay();
    const now = new Date().toISOString();
    return {
      id,
      envelope_id: fixtureEnvelopes.keys().next().value ?? "fixture-envelope",
      operation_key: "fixture.operation",
      reason_code: "HUMAN_REVIEW_REQUIRED",
      requested_by: "fixture-agent",
      status: body.decision,
      rationale: body.rationale,
      version: body.expected_version + 1,
      created_at: now,
      decided_at: now,
      decided_by: "fixture-reviewer",
      expires_at: new Date(Date.now() + 900_000).toISOString(),
    } satisfies AgentApprovalModel;
  },
  async getAgentKillSwitch() {
    await delay();
    return clone(fixtureKillSwitch);
  },
  async updateAgentKillSwitch(body) {
    await delay();
    if (body.expected_version !== fixtureKillSwitch.version) {
      throw new FixtureApiError(409, { code: "VERSION_CONFLICT", message: "The kill switch changed; reload and try again." });
    }
    fixtureKillSwitch = {
      ...fixtureKillSwitch,
      engaged: body.engaged,
      reason: body.reason,
      version: fixtureKillSwitch.version + 1,
      updated_by: "fixture-admin",
      updated_at: new Date().toISOString(),
    };
    return clone(fixtureKillSwitch);
  },
  async createFlightRecord(body) {
    await delay();
    const id = globalThis.crypto?.randomUUID?.() ?? `fixture-flight-${fixtureFlights.size + 1}`;
    const record: FlightRecordModel = {
      contract_version: "1.0.0",
      id,
      envelope_id: body.envelope_id,
      objective: body.objective,
      status: "ACTIVE",
      event_count: 0,
      outcome: null,
      started_by: "fixture-agent",
      started_at: new Date().toISOString(),
      completed_at: null,
      events: [],
    };
    fixtureFlights.set(id, record);
    return clone(record);
  },
  async getFlightRecord(id) {
    await delay();
    const record = fixtureFlights.get(id);
    if (!record) throw new FixtureApiError(404, { code: "FLIGHT_RECORD_NOT_FOUND", message: "The flight record was not found." });
    return clone(record);
  },
  async appendFlightEvent(id, body) {
    await delay();
    const record = fixtureFlights.get(id);
    if (!record) throw new FixtureApiError(404, { code: "FLIGHT_RECORD_NOT_FOUND", message: "The flight record was not found." });
    const sequence = record.event_count + 1;
    const previousHash = record.chain_head ?? null;
    const eventHash = `fixture:event:${sequence}`;
    record.events = [...(record.events ?? []), {
      id: globalThis.crypto?.randomUUID?.() ?? `${id}:event:${sequence}`,
      ...body,
      sequence,
      previous_hash: previousHash,
      event_hash: eventHash,
      recorded_at: new Date().toISOString(),
    }];
    record.event_count = sequence;
    record.chain_head = eventHash;
    fixtureFlights.set(id, record);
    return clone(record);
  },
  async finalizeFlightRecord(id, body) {
    await delay();
    const record = fixtureFlights.get(id);
    if (!record) throw new FixtureApiError(404, { code: "FLIGHT_RECORD_NOT_FOUND", message: "The flight record was not found." });
    record.status = body.status;
    record.outcome = body.outcome;
    record.completed_at = new Date().toISOString();
    fixtureFlights.set(id, record);
    return clone(record);
  },
  async runAgentControlDrill(body) {
    await delay();
    return {
      id: globalThis.crypto?.randomUUID?.() ?? `fixture-drill-${Date.now()}`,
      drill_kind: body.drill_kind,
      status: "PASSED",
      checks: [{ name: "fixture_control_path", passed: true }],
      performed_at: new Date().toISOString(),
      performed_by: "fixture-admin",
    } satisfies AgentControlDrillResult;
  },
  async listContradictions(subjectId, limit = 50) {
    await delay();
    const fixture = await import("../fixtures/phase2-contradictions.json");
    const result = clone(fixture.default as ContradictionLedger);
    result.contradictions = result.contradictions
      .filter((item) => !subjectId || item.subject.id === subjectId)
      .slice(0, limit);
    return result;
  },
  async listComponents(cursor, limit = 50) {
    await delay();
    const fixture = await import("../fixtures/phase2-estate-components.json");
    const result = clone(fixture.default as EstateComponentList);
    const start = cursor
      ? Math.max(0, result.components.findIndex((item) => item.component.id === cursor) + 1)
      : 0;
    const all = result.components;
    result.components = all.slice(start, start + limit);
    result.page_info = {
      has_next_page: start + limit < all.length,
      next_cursor: start + limit < all.length
        ? result.components.at(-1)?.component.id ?? null
        : null,
    };
    return result;
  },
  async getComponent(id) {
    await delay();
    const componentFixture = await import("../fixtures/phase2-estate-components.json");
    const summary = clone(componentFixture.default as EstateComponentList)
      .components.find((item) => item.component.id === id);
    if (!summary) {
      throw new FixtureApiError(404, {
        code: "COMPONENT_NOT_FOUND", message: "The component was not found.",
      });
    }
    const [deploymentFixture, containerFixture] = await Promise.all([
      import("../fixtures/phase2-deployment-profiles.json"),
      import("../fixtures/phase2-container-compositions.json"),
    ]);
    return {
      contract_version: "1.0.0",
      as_of: summary.profile.freshness.observed_at,
      component: summary,
      technologies: [{
        id: "20000000-0000-4000-8000-000000000001",
        kind: "Package", name: "Newtonsoft.Json", canonical_key: "pkg:nuget/Newtonsoft.Json",
      }],
      deployments: id.endsWith("001")
        ? [clone((deploymentFixture.default as DeploymentProfileList).profiles[0].deployment)]
        : [],
      container_images: id.endsWith("001")
        ? [clone((containerFixture.default as ContainerCompositionList).images[0].image)]
        : [],
      limitations: [],
    } satisfies EstateComponentDetail;
  },
  async listRepositoryContainerCompositions(id) {
    await delay();
    const fixture = await import("../fixtures/phase2-container-compositions.json");
    const result = clone(fixture.default as ContainerCompositionList);
    result.repository.id = id;
    return result;
  },
  async listRepositoryDeploymentProfiles(id) {
    await delay();
    const fixture = await import("../fixtures/phase2-deployment-profiles.json");
    const result = clone(fixture.default as DeploymentProfileList);
    result.repository.id = id;
    return result;
  },
  async listActionTypes() {
    await delay();
    return clone(phase2ActionTypes as ActionTypeList);
  },
  async listActionSubjects(predicate, query, limit = 25) {
    await delay();
    const result = clone(phase2ActionSubjects as ActionSubjectList);
    result.predicate = predicate;
    result.subjects = predicate === "UPGRADE"
      ? result.subjects.filter((item) => !query || item.entity.name.toLowerCase().includes(query.toLowerCase())).slice(0, limit)
      : [];
    result.page_info.has_next_page = false;
    return result;
  },
  async listValidTargets(_id, limit = 50) {
    await delay();
    const result = clone(phase2ValidTargets as ValidTargetList);
    result.targets = result.targets.slice(0, limit);
    return result;
  },
  async listChangeScopes() {
    await delay();
    return clone(phase2ChangeScopes as ChangeScopeList);
  },
  async listEntityChangeHistory(_id, limit = 20) {
    await delay();
    const result = clone(phase2ChangeHistory as ObservedMutationList);
    result.outcomes = result.outcomes.slice(0, limit);
    return result;
  },
  async compileMutation(body) {
    await delay(220);
    return fixtureCompile(clone(body));
  },
  async validateMutation(body) {
    await delay();
    const result = clone(phase2MutationCompile as MutationCompileResult);
    result.replayed = true;
    if (result.change_set) result.change_set.id = body.change_set_id;
    return result;
  },
  async compileDeterministicInsight(_id, body) {
    await delay();
    return fixtureCompile({
      idempotency_key: body.idempotency_key ?? "fixture-insight",
      predicate: "UPGRADE",
      subject_id: "20000000-0000-4000-8000-000000000001",
      target_version: "14.0.1",
      scope_id: "estate",
    });
  },
  async compileChangeSet(body) {
    await delay();
    return fixtureCompile({
      idempotency_key: body.idempotency_key,
      predicate: "UPGRADE",
      subject_id: "20000000-0000-4000-8000-000000000001",
      target_version: "14.0.1",
      scope_id: "estate",
    });
  },
  async compileModernizationRecommendation(_id, body) {
    await delay();
    return fixtureCompile({
      idempotency_key: body.idempotency_key ?? "fixture-recommendation",
      predicate: "UPGRADE",
      subject_id: "20000000-0000-4000-8000-000000000001",
      target_version: "14.0.1",
      scope_id: "scope:repository:billing",
    });
  },
  async createSimulation(body) {
    await delay();
    const existingId = fixtureSimulationByKey.get(body.idempotency_key);
    if (existingId) {
      const existing = fixtureSimulations.get(existingId)!;
      return { ...clone(existing.run), replayed: true };
    }
    const template = clone(phase2SimulationRun as SimulationRunModel);
    const id = body.idempotency_key.startsWith("fixture:")
      ? template.id
      : (globalThis.crypto?.randomUUID?.() ?? "25000000-0000-4000-8000-000000000099");
    const run: SimulationRunModel = {
      ...template,
      id,
      change_set_id: body.change_set_id,
      status: "QUEUED",
      started_at: null,
      completed_at: null,
      findings: [],
      interpretation: { status: "UNAVAILABLE", cited_finding_ids: [], limitation: "Interpretation begins after deterministic findings complete." },
      result_hash: null,
    };
    fixtureSimulations.set(id, { run, reads: 0 });
    fixtureSimulationByKey.set(body.idempotency_key, id);
    return clone(run);
  },
  async getSimulation(id) {
    await delay(180);
    const state = fixtureSimulations.get(id);
    if (!state) {
      const variant = fixtureSimulationVariant(id);
      if (variant) return variant;
      throw new FixtureApiError(404, { code: "SIMULATION_NOT_FOUND", message: "The simulation run was not found." });
    }
    state.reads += 1;
    if (state.run.status === "QUEUED" && state.reads >= 1) {
      state.run.status = "RUNNING";
      state.run.started_at = new Date().toISOString();
    } else if (state.run.status === "RUNNING" && state.reads >= 3) {
      const completed = clone(phase2SimulationRun as SimulationRunModel);
      state.run = { ...completed, id, change_set_id: state.run.change_set_id, replayed: state.run.replayed };
    }
    fixtureSimulations.set(id, state);
    return clone(state.run);
  },
  async cancelSimulation(id) {
    await delay();
    const state = fixtureSimulations.get(id);
    if (!state) throw new FixtureApiError(404, { code: "SIMULATION_NOT_FOUND", message: "The simulation run was not found." });
    state.run.status = "CANCELLED";
    state.run.completed_at = new Date().toISOString();
    fixtureSimulations.set(id, state);
    return clone(state.run);
  },
  async recordObservedMutation(body) {
    await delay();
    const template = clone((phase2ChangeHistory as ObservedMutationList).outcomes[0]);
    return {
      ...template,
      id: globalThis.crypto?.randomUUID?.() ?? "29000000-0000-4000-8000-000000000099",
      predicate: body.predicate,
      before: body.before,
      after: body.after,
      scope: body.scope,
      observed_impact: body.observed_impact,
      unexpected_impact: body.unexpected_impact ?? {},
      success: body.success ?? null,
      intervention_required: body.intervention_required ?? false,
      rolled_back: body.rolled_back ?? false,
      source_kind: body.source_kind,
      confidence: body.confidence,
      correlation_key: body.correlation_key,
      evidence_fact_ids: body.evidence_fact_ids,
      graph_watermark_before: body.graph_watermark_before ?? null,
      predicted_simulation_run_id: body.predicted_simulation_run_id ?? null,
      resolution: body.resolution ?? null,
      observed_at: body.observed_at,
      created_at: new Date().toISOString(),
      subject: { ...template.subject, id: body.subject_entity_id },
    };
  },
  async listRepositoryFingerprints(_id, limit = 20) {
    await delay();
    const result = clone(phase2RepositoryFingerprints as RepositoryFingerprintList);
    result.snapshots = result.snapshots.slice(0, limit);
    return result;
  },
  async listEntityCriticalEdges() {
    await delay();
    return clone(phase2CriticalEdges as CriticalGraphEdgeList);
  },
  async listGraphIntelligenceAnomalies(cohortKey, limit = 50) {
    await delay();
    const result = clone(phase2Anomalies as GraphAnomalyList);
    result.anomalies = (result.anomalies ?? []).filter((item) => !cohortKey || item.cohort_key === cohortKey).slice(0, limit);
    return result;
  },
  async listGraphIntelligenceMotifs(motifKey, limit = 50) {
    await delay();
    const result = clone(phase2Motifs as GraphMotifList);
    result.motifs = (result.motifs ?? []).filter((item) => !motifKey || item.motif_key === motifKey).slice(0, limit);
    return result;
  },
  async requestGraphAnalysis() {
    await delay();
    return clone(phase2AnalysisRequest as GraphAnalysisRequestResult);
  },
  async getApplication() {
    await delay();
    const detail = clone(applicationDetail as ApplicationDetail);
    if (applicationDescriptionOverride !== null) detail.application.summary = applicationDescriptionOverride || undefined;
    return {
      ...detail,
      graph_intelligence: fixtureEntityGraphIntelligence(applicationDetail.application.id),
    };
  },
  async updateApplication(id, body) {
    await delay();
    applicationDescriptionOverride = body.description;
    return {
      ...(applicationDetail as ApplicationDetail).application,
      id,
      summary: body.description || undefined,
    };
  },
  async getRepository() {
    await delay();
    const detail = clone(repositoryDetail as RepositoryDetail);
    if (repositoryDescriptionOverride !== null) detail.repository.summary = repositoryDescriptionOverride || undefined;
    return detail;
  },
  async updateRepository(id, body) {
    await delay();
    repositoryDescriptionOverride = body.description;
    return {
      ...(repositoryDetail as RepositoryDetail).repository,
      id,
      summary: body.description || undefined,
    };
  },
  async getRepositoryActivity(_id, params) {
    await delay();
    const result = clone(repositoryActivity as RepositoryActivity);
    if (params?.window && params.window !== result.window) {
      const days = Number.parseInt(params.window, 10);
      result.window = params.window;
      result.window_started_at = new Date(
        new Date(result.window_ended_at).getTime() - days * 86_400_000,
      ).toISOString();
      if (params.window === "7d") {
        result.summary = {
          commits: 11,
          pull_requests_merged: 2,
          contributors: 3,
          last_change_at: result.summary.last_change_at,
        };
        result.events = result.events.slice(0, 3);
        result.top_contributors = result.top_contributors.slice(0, 3);
      } else if (params.window === "90d") {
        result.summary = {
          commits: 129,
          pull_requests_merged: 24,
          contributors: 9,
          last_change_at: result.summary.last_change_at,
        };
      }
    }
    if (params?.limit != null) {
      const eventCount = result.events.length;
      result.events = result.events.slice(0, params.limit);
      result.page_info = {
        has_next_page: eventCount > params.limit,
        next_cursor: eventCount > params.limit ? "fixture-next" : null,
      };
    }
    return result;
  },
  async getTechnology() {
    await delay();
    return technologyDetail as TechnologyDetail;
  },
  async getTechnologyEstateHierarchy() {
    await delay();
    return technologyEstateHierarchy as TechnologyEstateHierarchy;
  },
  async listModernization() {
    await delay();
    return modernizationList as ModernizationList;
  },
  async listDeterministicInsights(params) {
    await delay();
    const result = clone(deterministicInsights as DeterministicInsightList);
    if (params?.ruleKey) result.insights = result.insights.filter((item) => item.rule_key === params.ruleKey);
    if (params?.scopeEntityId) {
      result.insights = result.insights.filter((item) =>
        item.subject.id === params.scopeEntityId
        || item.scope_entity_ids.includes(params.scopeEntityId!)
        || item.affected_repositories.some((repository) => repository.id === params.scopeEntityId),
      );
    }
    result.insights = result.insights.slice(0, params?.limit ?? 100);
    result.summary = {
      total: result.insights.length,
      critical: result.insights.filter((item) => item.severity === "CRITICAL").length,
      high: result.insights.filter((item) => item.severity === "HIGH").length,
      affected_repositories: new Set(result.insights.flatMap((item) => item.affected_repositories.map((repository) => repository.id))).size,
      runtime_observed: result.insights.reduce((total, item) => total + item.stages.runtime_observed, 0),
      deployed: result.insights.reduce((total, item) => total + item.stages.deployed, 0),
    };
    return result;
  },
  async listEnterpriseInsightReports() {
    await delay();
    const evaluatedAt = new Date().toISOString();
    const definitions = [
      ["systemic_dependency_risk", "Systemic dependency risk", "ENTERPRISE_RISK", "87", "highest risk score", "ACTION_REQUIRED"],
      ["reachable_vulnerabilities", "Reachable Tier-1 vulnerabilities", "ENTERPRISE_RISK", "3", "reachable impact paths", "ACTION_REQUIRED"],
      ["package_business_blast_radius", "Largest package blast radius", "ENTERPRISE_RISK", "4", "enterprise impact groups", "WATCH"],
      ["duplicate_capability_implementations", "Duplicated capabilities", "TECHNOLOGY_RATIONALIZATION", "6", "duplicated capabilities", "WATCH"],
      ["technology_diversity", "Unnecessary technology diversity", "TECHNOLOGY_RATIONALIZATION", "2", "diverse package categories", "WATCH"],
      ["modernization_blockers", "Modernization blockers", "TECHNOLOGY_RATIONALIZATION", "5", "unsupported blockers", "ACTION_REQUIRED"],
      ["custom_to_internal_platform", "Internal platform replacements", "TECHNOLOGY_RATIONALIZATION", "—", "replacement candidates", "WAITING_FOR_DATA"],
      ["internal_library_standards", "Enterprise library standards", "PORTFOLIO_DECISIONS", "—", "standard candidates", "WAITING_FOR_DATA"],
      ["application_retirement_consolidation", "Retirement & consolidation", "PORTFOLIO_DECISIONS", "—", "portfolio candidates", "WAITING_FOR_DATA"],
      ["standardization_initiatives", "Standardization payoff", "PORTFOLIO_DECISIONS", "72.50", "highest payoff score", "ACTION_REQUIRED"],
      ["assurance_coverage", "Analytical assurance coverage", "ENTERPRISE_RISK", "78%", "of the estate analytically covered", "WATCH"],
      ["technology_introduction", "Technologies introduced", "TECHNOLOGY_RATIONALIZATION", "4", "technologies introduced (90 days)", "WATCH"],
      ["business_dark_capability", "Dark business capabilities", "PORTFOLIO_DECISIONS", "2", "critical capabilities without applications", "ACTION_REQUIRED"],
      ["decision_lag", "Decision implementation lag", "PORTFOLIO_DECISIONS", "46", "longest wait in days", "ACTION_REQUIRED"],
    ] as const;
    return {
      contract_version: "1.0.0", method_version: "enterprise-insights/v1",
      evaluated_at: evaluatedAt, answerable_reports: 11, total_reports: 14,
      reports: definitions.map(([key, title, category, metricValue, metricLabel, status]) => ({
        key, title, category, question: title, metric_value: metricValue,
        metric_label: metricLabel, status, answerable: status !== "WAITING_FOR_DATA",
        confidence: status === "WAITING_FOR_DATA" ? null : 0.86,
        evidence_count: status === "WAITING_FOR_DATA" ? 0 : 12,
        summary: status === "WAITING_FOR_DATA"
          ? "More governed data is needed before this report can produce a recommendation."
          : "Derived from current graph facts. Open the report for its ranked evidence and citations.",
        response: key === "assurance_coverage"
          ? assuranceCoverageResponse()
          : clone(askResponse as AskResponse),
      })),
    };
  },
  async listCapabilityFootprints() {
    await delay();
    return capabilityFootprints as CapabilityFootprintList;
  },
  async optimizeModernizationScenario() {
    await delay();
    return modernizationScenario as ModernizationScenarioResult;
  },
  async ask() {
    await delay(300);
    return askResponse as AskResponse;
  },
  async getGraphNeighborhood() {
    await delay();
    return graphNeighborhood as GraphNeighborhood;
  },
  async getGraphIntelligenceStatus() {
    await delay();
    return fixtureGraphStatus();
  },
  async getEntityGraphMetrics(id) {
    await delay();
    return fixtureEntityGraphIntelligence(id);
  },
  async getEntityBlastRadius(id) {
    await delay();
    const intelligence = fixtureEntityGraphIntelligence(id);
    // A path with its supporting facts, because the empty case exercised none of the
    // rendering that matters here — the hops, the confidence floor, and the evidence
    // that has to open on top of the drawer showing it.
    return {
      contract_version: "1.0.0",
      entity: intelligence.entity,
      snapshot: intelligence.snapshots[0] ?? null,
      affected_entity_count: 4,
      maximum_depth: 3,
      impacts: [
        {
          target: applicationDetail.application,
          distance: 2,
          minimum_confidence: 0.78,
          entity_ids: [id, repositoryDetail.repository.id, applicationDetail.application.id],
          supporting_fact_ids: [
            "70000000-0000-4000-8000-000000000011",
            "70000000-0000-4000-8000-000000000012",
          ],
        },
      ],
      as_of: intelligence.as_of,
      limitations: [{
        code: "PARTIAL_COVERAGE",
        message: "Deployment relationships were not covered by this snapshot, so runtime-only impact may be understated.",
      }],
    };
  },
  async listGraphIntelligenceRisks(limit = 20) {
    await delay();
    const intelligence = fixtureEntityGraphIntelligence(applicationDetail.application.id);
    return {
      contract_version: "1.0.0",
      snapshot: intelligence.snapshots[0] ?? null,
      risks: [{
        entity: repositoryDetail.repository,
        impacted_applications: [applicationDetail.application],
        systemic_risk: 0.86,
        component_metrics: intelligence.metrics,
        reasons: intelligence.reasons,
      }].slice(0, limit),
      as_of: intelligence.as_of,
      limitations: [],
    };
  },
  async listGraphIntelligenceCommunities() {
    await delay();
    const intelligence = fixtureEntityGraphIntelligence(applicationDetail.application.id);
    return {
      contract_version: "1.0.0",
      snapshot: intelligence.snapshots[0] ?? null,
      algorithm_key: "wcc",
      // Representatives include the subject and its peers; with the subject alone the
      // "alongside" half of the community line never rendered.
      communities: [{
        community_key: intelligence.community_keys[0] ?? "runtime:0",
        member_count: 14,
        representative_entities: [
          intelligence.entity,
          { id: "00000000-0000-4000-8000-000000000703", kind: "Application", name: "Ledger API", canonical_key: "application:ledger-api" },
          repositoryDetail.repository,
        ],
      }],
      as_of: intelligence.as_of,
      limitations: [],
    };
  },
  async semanticSearch(body) {
    await delay();
    const now = new Date().toISOString();
    // Scored against a small pool rather than returning one constant hit, so both the
    // "found something a name filter would miss" and the "found nothing" states are
    // reachable. Each entry carries the words it would be retrieved by, standing in for
    // the rendered document a real space embeds.
    const pool: Array<{ entity: EntitySummary; terms: string[]; score: number }> = [
      {
        entity: { id: "00000000-0000-4000-8000-000000000703", kind: "Application", name: "Ledger API", canonical_key: "application:ledger-api", summary: "Posts and reconciles financial ledger entries" },
        terms: ["ledger", "billing", "invoice", "payment", "finance", "reconcile"],
        score: 0.86,
      },
      {
        entity: applicationDetail.application,
        terms: ["billing", "invoice", "payment", "charge", "subscription"],
        score: 0.81,
      },
      {
        entity: repositoryDetail.repository,
        terms: ["billing", "service", "repository", "node"],
        score: 0.74,
      },
    ];
    const needles = body.query.toLowerCase().split(/[^a-z0-9]+/).filter(Boolean);
    const hits = pool
      .filter((candidate) => needles.some((needle) =>
        candidate.terms.some((term) => term.startsWith(needle) || needle.startsWith(term)),
      ))
      .slice(0, body.limit)
      .map((candidate) => ({
        entity: candidate.entity,
        score: candidate.score,
        input_hash: `sha256:${"b".repeat(64)}`,
        sensitivity: "INTERNAL" as const,
      }));
    return {
      contract_version: "1.0.0",
      space_id: fixtureEmbeddingStatus().active_spaces[0]!.id,
      space_key: "entity-semantic",
      model_or_algorithm: "hash-embedding-v1",
      template_version: "entity-document/v1",
      query_hash: `sha256:${"c".repeat(64)}`,
      hits,
      as_of: now,
      limitations: [{
        code: "EXACT_SEARCH",
        message: "Results use exact tenant-filtered cosine search; no approximate index was used.",
      }],
    };
  },
  async getEmbeddingStatus() {
    await delay();
    return fixtureEmbeddingStatus();
  },
  async listSimilarApplications(id) {
    await delay();
    return fixtureApplicationSimilarity(id);
  },
  async reviewApplicationSimilarity(id, body) {
    await delay();
    return {
      contract_version: "1.0.0", candidate_id: id,
      review_state: body.decision === "REOPENED" ? "UNREVIEWED" : body.decision,
      reviewed_at: new Date().toISOString(),
    };
  },
  async getFactEvidence() {
    await delay();
    return evidenceDetail as EvidenceDetail;
  },
  async reviewIdentityAssertion() {
    await delay();
    return identityReview as IdentityReviewResult;
  },
  async getCapabilityTaxonomy() {
    await delay();
    return capabilityTaxonomy as CapabilityTaxonomy;
  },
  async getRepositoryCapabilities() {
    await delay();
    return repositoryCapabilities as RepositoryCapabilityIntelligence;
  },
  async reviewCapabilityInference(id, body) {
    await delay();
    return {contract_version: "1.0.0", capability_inference_id: id, review_state: body.decision === "CONFIRM" ? "CONFIRMED" : "REJECTED", version: body.expected_version + 1, reviewed_at: new Date().toISOString()};
  },
  async reviewDuplicateCapabilityCandidate(id, body) {
    await delay();
    return {contract_version: "1.0.0", duplicate_capability_candidate_id: id, review_state: body.decision === "CONFIRM" ? "CONFIRMED" : "REJECTED", version: body.expected_version + 1, reviewed_at: new Date().toISOString()};
  },
  async getRepositoryModernizationIntelligence() {
    await delay();
    const golden = repositoryModernization as RepositoryModernizationIntelligence;
    return { ...golden, candidates: [...golden.candidates, demoModernizationCandidate] };
  },
  async reviewModernizationCandidate(id, body) {
    await delay();
    return {contract_version: "1.0.0", modernization_candidate_id: id, review_state: body.decision === "CONFIRM" ? "CONFIRMED" : "REJECTED", version: body.expected_version + 1, reviewed_at: new Date().toISOString()};
  },
  async reviewModernizationRecommendation(id, body) {
    await delay();
    return {contract_version: "1.0.0", modernization_recommendation_id: id, review_state: body.decision === "ACCEPT" ? "ACCEPTED" : body.decision === "REJECT" ? "REJECTED" : "DISMISSED", version: body.expected_version + 1, reviewed_at: new Date().toISOString()};
  },
  async recordModernizationValidationOutcome(id, body) {
    await delay();
    return {contract_version: "1.0.0", id: "00000000-0000-4000-8000-000000000799", modernization_recommendation_id: id, validation_status: body.validation_status, reported_at: new Date().toISOString()};
  },
  async getPhase3IntelligenceMetrics() {
    await delay();
    return phase3Metrics as Phase3IntelligenceMetrics;
  },
  async getDeterministicInsightGovernance() {
    await delay();
    return clone(adminDeterministicInsightGovernance);
  },
  async updateDeterministicInsightRule(ruleKey, body) {
    await delay();
    adminDeterministicInsightGovernance = {
      ...adminDeterministicInsightGovernance,
      rules: adminDeterministicInsightGovernance.rules.map((rule) => rule.rule_key === ruleKey ? {
        ...rule,
        enabled: body.enabled,
        severity: body.severity,
        minimum_repositories: body.minimum_repositories ?? rule.minimum_repositories,
        configuration: body.configuration ?? rule.configuration,
        version: rule.version + 1,
        updated_by: "fixture-admin",
        updated_at: new Date().toISOString(),
      } : rule),
    };
    adminDeterministicInsightGovernance.active_rule_count = adminDeterministicInsightGovernance.rules.filter(
      (rule) => rule.enabled && rule.readiness === "ACTIVE",
    ).length;
    return clone(adminDeterministicInsightGovernance);
  },
  async listBusinessMaps() {
    await delay();
    const maps = [...businessMaps.values()]
      .filter((m) => m.status !== "ARCHIVED")
      .sort((a, b) => b.updated_at.localeCompare(a.updated_at))
      .map(summarize);
    return { contract_version: "1.0.0", as_of: new Date().toISOString(), maps, page_info: { has_next_page: false } };
  },
  async createBusinessMap(body) {
    await delay();
    for (const existing of businessMaps.values()) {
      if (existing.map_key === body.map_key) {
        throw new FixtureApiError(409, { code: "BUSINESS_MAP_EXISTS", map_key: body.map_key });
      }
    }
    const now = new Date().toISOString();
    const id = (globalThis.crypto?.randomUUID?.() ?? `fixture-${businessMaps.size + 1}`);
    const detail: BusinessMapDetail = {
      contract_version: "1.0.0", id, map_key: body.map_key, status: "ACTIVE", version: 1,
      created_at: now, updated_at: now, state: clone(body.state),
    };
    businessMaps.set(id, detail);
    businessMapRevisions.set(id, [{ version: 1, actor_key: "fixture", created_at: now }]);
    return clone(detail);
  },
  async getBusinessMap(id) {
    await delay();
    const detail = businessMaps.get(id);
    if (!detail) throw new FixtureApiError(404, { code: "BUSINESS_MAP_NOT_FOUND" });
    return clone(detail);
  },
  async saveBusinessMap(id, body) {
    await delay();
    const detail = businessMaps.get(id);
    if (!detail) throw new FixtureApiError(404, { code: "BUSINESS_MAP_NOT_FOUND" });
    if (detail.status === "ARCHIVED") throw new FixtureApiError(409, { code: "BUSINESS_MAP_ARCHIVED" });
    if (detail.version !== body.expected_version) {
      throw new FixtureApiError(409, {
        code: "VERSION_CONFLICT", expected_version: body.expected_version, actual_version: detail.version,
      });
    }
    const now = new Date().toISOString();
    const next: BusinessMapDetail = { ...detail, version: detail.version + 1, updated_at: now, state: clone(body.state) };
    businessMaps.set(id, next);
    businessMapRevisions.get(id)?.unshift({ version: next.version, actor_key: "fixture", created_at: now });
    return clone(next);
  },
  async archiveBusinessMap(id) {
    await delay();
    const detail = businessMaps.get(id);
    if (!detail) throw new FixtureApiError(404, { code: "BUSINESS_MAP_NOT_FOUND" });
    detail.status = "ARCHIVED";
    detail.updated_at = new Date().toISOString();
    return summarize(detail);
  },
  async getBusinessMapRevisions(id) {
    await delay();
    if (!businessMaps.has(id)) throw new FixtureApiError(404, { code: "BUSINESS_MAP_NOT_FOUND" });
    return { contract_version: "1.0.0", business_map_id: id, revisions: clone(businessMapRevisions.get(id) ?? []) };
  },
  async getSession() {
    await delay();
    // Fixture/demo runs as a full-capability admin so every surface is exercisable.
    return { contract_version: "1.0.0", actor_key: "fixture-admin", tenant_id: null, capabilities: ["admin"] };
  },
  async getReviewQueue() {
    await delay();
    const now = new Date().toISOString();
    return {
      contract_version: "1.0.0",
      as_of: now,
      counts: {
        IDENTITY_ASSERTION: 1, CAPABILITY_INFERENCE: 1, DUPLICATE_CAPABILITY: 1,
        MODERNIZATION_CANDIDATE: 1, MODERNIZATION_RECOMMENDATION: 1,
        APPLICATION_SIMILARITY: 1,
      },
      items: [{
        item_id: "00000000-0000-4000-8000-000000000501",
        item_type: "IDENTITY_ASSERTION", review_state: "POSSIBLE",
        title: "stripe ↔ stripe-node", confidence: 0.72, confidence_band: "MEDIUM",
        version: 1, created_at: now,
        review_path: "/identity-assertions/00000000-0000-4000-8000-000000000501/review",
      }, {
        item_id: "00000000-0000-4000-8000-000000000502",
        item_type: "APPLICATION_SIMILARITY", review_state: "UNREVIEWED",
        title: "Billing API ↔ Ledger API", confidence: 0.83, confidence_band: "MEDIUM",
        summary: "Explainable application similarity 83 percent",
        version: 1, created_at: now,
        review_path: "/similarity-candidates/00000000-0000-4000-8000-000000000502/review",
      }, {
        item_id: "00000000-0000-4000-8000-000000000503",
        item_type: "MODERNIZATION_RECOMMENDATION", review_state: "UNREVIEWED",
        title: "Replace bespoke retry helper with the platform client",
        summary: "Consolidates three internal implementations onto one supported client",
        confidence: 0.66, confidence_band: "MEDIUM",
        repository_id: repositoryDetail.repository.id,
        version: 1, created_at: now,
        review_path: "/modernization-recommendations/00000000-0000-4000-8000-000000000503/review",
      }, {
        item_id: "00000000-0000-4000-8000-000000000504",
        item_type: "CAPABILITY_INFERENCE", review_state: "UNREVIEWED",
        title: "Payment retry logic implements Rate limiting",
        summary: "Inferred from call-site and dependency evidence in this repository",
        confidence: 0.78, confidence_band: "MEDIUM",
        repository_id: repositoryDetail.repository.id,
        version: 1, created_at: now,
        review_path: "/capability-inferences/00000000-0000-4000-8000-000000000504/review",
      }, {
        item_id: "00000000-0000-4000-8000-000000000505",
        item_type: "DUPLICATE_CAPABILITY", review_state: "UNREVIEWED",
        title: "Rate limiting implemented in 3 repositories",
        summary: "Matching structural fingerprint across three repositories",
        confidence: 0.69, confidence_band: "MEDIUM",
        repository_id: repositoryDetail.repository.id,
        version: 1, created_at: now,
        review_path: "/duplicate-capability-candidates/00000000-0000-4000-8000-000000000505/review",
      }, {
        item_id: "00000000-0000-4000-8000-000000000506",
        item_type: "MODERNIZATION_CANDIDATE", review_state: "UNREVIEWED",
        title: "Vendored retry helper duplicates the platform client",
        summary: "Vendored duplication candidate flagged by the modernization analyzer",
        confidence: 0.61, confidence_band: "MEDIUM",
        repository_id: repositoryDetail.repository.id,
        version: 1, created_at: now,
        review_path: "/modernization-candidates/00000000-0000-4000-8000-000000000506/review",
      }],
      page_info: { has_next_page: false },
    };
  },
  async listMembers() {
    await delay();
    return { contract_version: "1.0.0", members: clone([...adminMembers.values()]) };
  },
  async inviteMember(body) {
    await delay();
    const now = new Date().toISOString();
    const id = globalThis.crypto?.randomUUID?.() ?? `member-${adminMembers.size + 1}`;
    const member: TenantMember = {
      id, actor_key: body.actor_key, display_name: body.display_name ?? "",
      email: body.email ?? "", role: body.role ?? "view", status: "INVITED",
      created_at: now, updated_at: now,
    };
    adminMembers.set(id, member);
    return clone(member);
  },
  async updateMember(id, body) {
    await delay();
    const member = adminMembers.get(id);
    if (!member) throw new FixtureApiError(404, { code: "MEMBER_NOT_FOUND" });
    if (body.role) member.role = body.role;
    if (body.status) member.status = body.status;
    member.updated_at = new Date().toISOString();
    return clone(member);
  },
  async removeMember(id) {
    await delay();
    const member = adminMembers.get(id);
    if (!member) throw new FixtureApiError(404, { code: "MEMBER_NOT_FOUND" });
    adminMembers.delete(id);
    return clone(member);
  },
  async listConnectors() {
    await delay();
    return { contract_version: "1.0.0", connectors: clone([...adminConnectors.values()]) };
  },
  async registerConnector(body) {
    await delay();
    const now = new Date().toISOString();
    const id = globalThis.crypto?.randomUUID?.() ?? `connector-${adminConnectors.size + 1}`;
    const connector: Connector = {
      id, provider: body.provider, display_name: body.display_name,
      external_account_key: body.external_account_key ?? "", scopes: body.scopes ?? [],
      status: "CONNECTED", created_at: now, updated_at: now,
    };
    adminConnectors.set(id, connector);
    return clone(connector);
  },
  async connectGitHubRepository(body) {
    return this.registerConnector({
      provider: "GITHUB_APP",
      display_name: body.repository,
      external_account_key: `github:repository:${body.repository.toLowerCase()}`,
      credential_reference: body.credential_reference ?? "env://GITHUB_TOKEN",
      scopes: ["contents:read", "metadata:read"],
    });
  },
  async listAvailableGitHubRepositories() {
    await delay();
    const connected = new Set(
      [...adminConnectors.values()]
        .filter((connector) => connector.external_account_key.startsWith("github:repository:"))
        .map((connector) => connector.external_account_key.slice("github:repository:".length).toLowerCase()),
    );
    return {
      contract_version: "1.0.0",
      token_configured: true,
      truncated: false,
      repositories: [
        { full_name: "acme/billing", visibility: "private" as const, archived: false, default_branch: "main" },
        { full_name: "acme/platform", visibility: "private" as const, archived: false, default_branch: "main" },
        { full_name: "acme/public-design-system", visibility: "public" as const, archived: false, default_branch: "main" },
      ].filter((repository) => !connected.has(repository.full_name.toLowerCase())),
    };
  },
  async getGitHubTokenConfiguration() {
    await delay();
    return clone(adminGitHubTokenConfiguration);
  },
  async updateGitHubToken(body) {
    await delay();
    adminGitHubTokenConfiguration = {
      contract_version: "1.0.0",
      configured: true,
      fingerprint: body.token.slice(-4),
      source: "TENANT_SECRET",
      updated_by: "fixture-admin",
      updated_at: new Date().toISOString(),
    };
    return clone(adminGitHubTokenConfiguration);
  },
  async removeGitHubToken() {
    await delay();
    adminGitHubTokenConfiguration = {
      contract_version: "1.0.0", configured: false, source: "NONE",
    };
    return clone(adminGitHubTokenConfiguration);
  },
  async connectGitHubInstallation(body) {
    return this.registerConnector({
      provider: "GITHUB_APP",
      display_name: body.display_name ?? `GitHub installation ${body.installation_id}`,
      external_account_key: `github:installation:${body.installation_id}`,
      credential_reference: `github-app://installation/${body.installation_id}`,
      scopes: ["contents:read", "metadata:read"],
    });
  },
  async startGitHubInstallationSetup() {
    await delay();
    return {
      setup_url: "https://github.com/apps/stackgraph/installations/new?state=fixture-state",
      expires_at: new Date(Date.now() + 600_000).toISOString(),
    };
  },
  async updateConnector(id, body) {
    await delay();
    const connector = adminConnectors.get(id);
    if (!connector) throw new FixtureApiError(404, { code: "CONNECTOR_NOT_FOUND" });
    if (body.display_name) connector.display_name = body.display_name;
    if (body.status) connector.status = body.status;
    if (body.scopes) connector.scopes = body.scopes;
    connector.updated_at = new Date().toISOString();
    return clone(connector);
  },
  async removeConnector(id) {
    await delay();
    const connector = adminConnectors.get(id);
    if (!connector) throw new FixtureApiError(404, { code: "CONNECTOR_NOT_FOUND" });
    adminConnectors.delete(id);
    return clone(connector);
  },
  async getModernizationGovernance() {
    await delay();
    return clone(adminModernizationGovernance);
  },
  async publishModernizationPolicy(body) {
    await delay();
    const now = new Date().toISOString();
    adminModernizationGovernance = {
      ...adminModernizationGovernance,
      active_policy: {
        id: adminModernizationGovernance.active_policy?.id ?? "00000000-0000-4000-8000-000000000921",
        policy_key: body.policy_key ?? "modernization.default",
        version: body.version,
        status: "ACTIVE",
        runtime_versions: body.runtime_versions ?? {},
        allowed_licenses: body.allowed_licenses ?? [],
        denied_option_keys: body.denied_option_keys ?? [],
        allowed_security_statuses: body.allowed_security_statuses ?? ["CLEAR", "UNKNOWN"],
        required_policy_tags: body.required_policy_tags ?? [],
        configuration_fingerprint: `sha256:${"5".repeat(64)}`,
        activated_by: "fixture-admin",
        activated_at: now,
      },
    };
    return clone(adminModernizationGovernance);
  },
  async governInternalCatalogComponent(componentKey, body) {
    await delay();
    adminModernizationGovernance = {
      ...adminModernizationGovernance,
      internal_components: [
        ...adminModernizationGovernance.internal_components.filter(
          (item) => item.component_key !== componentKey || item.version !== body.version,
        ),
        {
          id: `fixture-${componentKey}-${body.version}`,
          component_key: componentKey,
          version: body.version,
          name: componentKey,
          status: body.status ?? "APPROVED",
          review_state: body.decision === "APPROVE" ? "APPROVED" : "REJECTED",
          owner: body.owner,
          catalog_fingerprint: `sha256:${"6".repeat(64)}`,
          supporting_fact_ids: body.supporting_fact_ids,
          governed_by: "fixture-admin",
          governed_at: new Date().toISOString(),
        },
      ],
    };
    return clone(adminModernizationGovernance);
  },
  async publishCalibrationCorpus(body) {
    await delay();
    const minimumReviewedCases = body.minimum_reviewed_cases ?? 20;
    const observed = {
      candidate_precision: 0.9,
      recommendation_acceptance: 0.6,
      validation_success: 0.9,
      affected_scope_mae: 0.1,
      effort_accuracy: 0.8,
      reviewed_cases: body.case_fingerprints.length,
    };
    const failures = [
      ...(body.case_fingerprints.length >= minimumReviewedCases
        ? [] : [`reviewed_cases ${body.case_fingerprints.length} < ${minimumReviewedCases}`]),
      ...(observed.candidate_precision >= (body.minimum_candidate_precision ?? 0.8)
        ? [] : ["candidate_precision is unavailable or below threshold"]),
      ...(observed.recommendation_acceptance >= (body.minimum_recommendation_acceptance ?? 0.5)
        ? [] : ["recommendation_acceptance is unavailable or below threshold"]),
      ...(observed.validation_success >= (body.minimum_validation_success ?? 0.8)
        ? [] : ["validation_success is unavailable or below threshold"]),
      ...(observed.affected_scope_mae <= (body.maximum_affected_scope_mae ?? 0.25)
        ? [] : ["affected_scope_mae is unavailable or above threshold"]),
      ...(observed.effort_accuracy >= (body.minimum_effort_accuracy ?? 0.7)
        ? [] : ["effort_accuracy is unavailable or below threshold"]),
    ];
    const promotionPassed = failures.length === 0;
    adminModernizationGovernance = {
      ...adminModernizationGovernance,
      active_calibration: {
        id: "00000000-0000-4000-8000-000000000922",
        corpus_key: body.corpus_key ?? "modernization.pilot",
        version: body.version,
        case_count: body.case_fingerprints.length,
        corpus_fingerprint: `sha256:${"7".repeat(64)}`,
        observed_metrics: observed,
        metrics_source_version: "persisted-review-outcomes/v1",
        promotion_passed: promotionPassed,
        promotion_failures: failures,
        evaluation_fingerprint: `sha256:${"8".repeat(64)}`,
        evaluated_at: new Date().toISOString(),
      },
      ecosystem_admissions: adminModernizationGovernance.ecosystem_admissions.map((item) => ({
        ...item,
        status: item.status === "NOT_EVALUATED" ? item.status : "STALE",
        calibration_gate_passed: promotionPassed,
      })),
    };
    return clone(adminModernizationGovernance);
  },
  async evaluateEcosystemAdmission(ecosystem, body) {
    await delay();
    const admission = adminModernizationGovernance.ecosystem_admissions.find(
      (item) => item.ecosystem === ecosystem,
    );
    if (!admission) throw new FixtureApiError(404, { code: "ECOSYSTEM_NOT_FOUND" });
    const minimumRepositories = body.minimum_repositories ?? admission.minimum_repositories;
    const minimumDependencyShare = body.minimum_dependency_share ?? admission.minimum_dependency_share;
    const predecessor = adminModernizationGovernance.ecosystem_admissions.find(
      (item) => item.sequence === admission.sequence - 1,
    );
    const predecessorAdmitted = admission.sequence === 1 || predecessor?.status === "ADMITTED";
    const reasons = [
      ...(predecessorAdmitted ? [] : ["predecessor ecosystem has not been admitted"]),
      ...(admission.observed_repositories >= minimumRepositories ? [] : ["observed repository demand is below threshold"]),
      ...(admission.observed_dependency_share >= minimumDependencyShare ? [] : ["observed dependency share is below threshold"]),
      ...(admission.metadata_parity ? [] : ["metadata parity is incomplete"]),
      ...(admission.calibration_gate_passed ? [] : ["calibration promotion gate has not passed"]),
    ];
    adminModernizationGovernance = {
      ...adminModernizationGovernance,
      ecosystem_admissions: adminModernizationGovernance.ecosystem_admissions.map((item) => (
        item.ecosystem === ecosystem
          ? {
              ...item,
              status: reasons.length === 0 ? "ADMITTED" : "PROPOSED",
              minimum_repositories: minimumRepositories,
              minimum_dependency_share: minimumDependencyShare,
              predecessor_admitted: predecessorAdmitted,
              reasons,
              decision_fingerprint: `sha256:${String(item.sequence).repeat(64)}`,
              decided_by: "fixture-admin",
              decided_at: new Date().toISOString(),
            }
          : item
      )),
    };
    return clone(adminModernizationGovernance);
  },
  async getTenantCodePolicies() {
    await delay();
    return clone(adminCodePolicies);
  },
  async upsertTenantCodeFunction(functionKey, body) {
    await delay();
    const now = new Date().toISOString();
    const existing = adminCodePolicies.functions.find((item) => item.function_key === functionKey);
    const next = {
      function_key: functionKey,
      name: body.name,
      description: body.description ?? "",
      domain_key: body.domain_key,
      source: body.source,
      status: body.status ?? "ACTIVE",
      policy: {
        id: existing?.policy?.id ?? (globalThis.crypto?.randomUUID?.() ?? `policy-${functionKey}`),
        allowed_technology_ids: body.allowed_technology_ids ?? [],
        prohibited_technology_ids: body.prohibited_technology_ids ?? [],
        policy_fingerprint: `sha256:${"3".repeat(64)}`,
        updated_by: "fixture-admin",
        updated_at: now,
      },
    } satisfies TenantCodePolicyState["functions"][number];
    adminCodePolicies = {
      ...adminCodePolicies,
      functions: existing
        ? adminCodePolicies.functions.map((item) => item.function_key === functionKey ? next : item)
        : [...adminCodePolicies.functions, next],
      policy_set_fingerprint: `sha256:${"4".repeat(64)}`,
      evaluations: adminCodePolicies.evaluations.map((item) => ({ ...item, status: "STALE" })),
      summary: {
        ...adminCodePolicies.summary,
        governed_functions: existing?.policy ? adminCodePolicies.summary.governed_functions : adminCodePolicies.summary.governed_functions + 1,
        custom_functions: !existing && body.source === "CUSTOM" ? adminCodePolicies.summary.custom_functions + 1 : adminCodePolicies.summary.custom_functions,
        stale_repositories: adminCodePolicies.evaluations.length,
      },
    };
    return clone(adminCodePolicies);
  },
  async evaluateTenantCodePolicies() {
    await delay();
    const now = new Date().toISOString();
    const prohibited = adminCodePolicies.available_technologies[1];
    adminCodePolicies = {
      ...adminCodePolicies,
      evaluations: prohibited ? [{
        id: "00000000-0000-4000-8000-000000000c21",
        repository: { id: "00000000-0000-4000-8000-000000000701", kind: "Repository", name: "billing-api", canonical_key: "github:repo:billing-api" },
        status: "MISALIGNED",
        violations: [{
          rule: "PROHIBITED", function_key: "client-state-management",
          function_name: "Client state management", technology: prohibited.technology,
          matched_technology_id: prohibited.technology.id,
          fact_ids: ["00000000-0000-4000-8000-000000000c31"],
          message: "Redux is strictly prohibited for Client state management.",
        }],
        unclassified_technologies: [],
        policy_set_fingerprint: adminCodePolicies.policy_set_fingerprint,
        evidence_fingerprint: `sha256:${"5".repeat(64)}`,
        evaluated_by: "fixture-admin", evaluated_at: now,
      }] : [],
      summary: {
        ...adminCodePolicies.summary,
        evaluated_repositories: prohibited ? 1 : 0,
        compliant_repositories: 0,
        misaligned_repositories: prohibited ? 1 : 0,
        stale_repositories: 0,
      },
    };
    return clone(adminCodePolicies);
  },
  async getAIProviderConfiguration() {
    await delay();
    return clone(adminAIConfiguration);
  },
  async updateAIProviderConfiguration(body) {
    await delay();
    adminAIConfiguration = {
      ...adminAIConfiguration,
      provider: body.provider,
      model: body.model ?? "",
      enabled: body.enabled ?? true,
      key_configured: body.api_key ? true : adminAIConfiguration.key_configured,
      key_fingerprint: body.api_key ? body.api_key.slice(-4) : adminAIConfiguration.key_fingerprint,
      test_status: "NOT_TESTED",
      enrichment_status: body.enabled !== false && Boolean(body.model) && Boolean(body.api_key || adminAIConfiguration.key_configured)
        ? "READY" : "DISABLED",
      pending_enrichment_jobs: 0,
      running_enrichment_jobs: 0,
      failed_enrichment_jobs: 0,
      last_enrichment_at: null,
      tested_at: null,
      last_error: null,
      updated_by: "fixture-admin",
      updated_at: new Date().toISOString(),
    };
    return clone(adminAIConfiguration);
  },
  async removeAIProviderKey() {
    await delay();
    adminAIConfiguration = {
      ...adminAIConfiguration, key_configured: false, key_fingerprint: null,
      test_status: "NOT_TESTED", tested_at: null, last_error: null,
      enrichment_status: "DISABLED", pending_enrichment_jobs: 0,
      running_enrichment_jobs: 0, failed_enrichment_jobs: 0, last_enrichment_at: null,
    };
    return clone(adminAIConfiguration);
  },
  async testAIProviderConnection() {
    await delay();
    if (!adminAIConfiguration.key_configured) {
      throw new FixtureApiError(422, { message: "Save a provider API key before testing the connection." });
    }
    adminAIConfiguration = {
      ...adminAIConfiguration, test_status: "SUCCEEDED", tested_at: new Date().toISOString(), last_error: null,
    };
    return { contract_version: "1.0.0", provider: adminAIConfiguration.provider, status: "SUCCEEDED", models: [] };
  },
  async getScanPolicy() {
    await delay();
    return clone(adminScanPolicy);
  },
  async updateScanPolicy(body) {
    await delay();
    adminScanPolicy = {
      contract_version: "1.0.0", cadence: body.cadence, enabled: body.enabled ?? true,
      updated_by: "fixture-admin", updated_at: new Date().toISOString(),
    };
    return clone(adminScanPolicy);
  },
  async getScanStatus() {
    await delay();
    return {
      contract_version: "1.0.0", as_of: new Date().toISOString(), policy: clone(adminScanPolicy),
      quotas: [
        { provider: "GITHUB_APP", used: 4200, limit: 5000, status: "OK", observed_at: new Date().toISOString() },
      ],
      recent_jobs: clone([...adminRescans.values()].map((r) => r.job).slice(-10).reverse()),
    };
  },
  async getServiceStatus() {
    await delay();
    const now = new Date().toISOString();
    return {
      contract_version: "1.0.0", as_of: now,
      services: [
        ["web", "Web UI", "CORE"], ["api", "API", "CORE"],
        ["database", "PostgreSQL / pgvector", "CORE"],
        ["github-webhook", "GitHub webhooks", "INGESTION"],
        ["github-control-loop", "GitHub discovery", "INGESTION"],
        ["depsdev", "deps.dev enrichment", "ENRICHMENT"],
        ["osv", "OSV vulnerability enrichment", "ENRICHMENT"],
        ["projection", "Graph projection", "GRAPH"],
        ["graph-intelligence", "Graph intelligence", "GRAPH"],
        ["intelligence", "Modernization intelligence", "INTELLIGENCE"],
        ["embeddings", "Semantic embeddings", "INTELLIGENCE"],
      ].map(([key, name, category]) => ({
        key, name, category: category as ServiceStatusList["services"][number]["category"],
        state: (adminServiceStates.get(key) === "STOPPED" ? "STOPPED" : "IDLE") as ServiceStatus["state"],
        desired_state: adminServiceStates.get(key) ?? "RUNNING",
        controllable: [
          "github-webhook", "github-control-loop", "projection", "intelligence",
          "graph-intelligence", "embeddings",
        ].includes(key),
        management_scope: [
          "github-webhook", "github-control-loop", "projection", "intelligence",
          "graph-intelligence", "embeddings",
        ].includes(key)
          ? "This workspace" : category === "CORE" ? "Docker / deployment platform" : "Shared OSS catalog pipeline",
        detail: adminServiceStates.get(key) === "STOPPED"
          ? "Stopped for this workspace; durable queued work is preserved."
          : "Worker is online and the durable queue is clear.",
        configured: true, pending: 0, running: 0, failed: 0,
        last_heartbeat_at: now,
      })),
    };
  },
  async updateServiceControl(serviceKey, body) {
    await delay();
    adminServiceStates.set(serviceKey, body.desired_state);
    const status = await this.getServiceStatus();
    const service = status.services.find((item) => item.key === serviceKey);
    if (!service) throw new FixtureApiError(404, { code: "SERVICE_NOT_FOUND" });
    return service;
  },
  async requestRescan(body) {
    await delay();
    const existing = [...adminRescans.values()].find((j) => j.idempotencyKey === body.idempotency_key);
    if (existing) return clone(existing.job);
    const now = new Date().toISOString();
    const id = globalThis.crypto?.randomUUID?.() ?? `rescan-${adminRescans.size + 1}`;
    const job: RescanJob = {
      id, connector_id: body.connector_id ?? null, status: "PENDING",
      reason: body.reason ?? "", requested_by: "fixture-admin", created_at: now,
    };
    adminRescans.set(id, { idempotencyKey: body.idempotency_key, job });
    return clone(job);
  },
  async listRescans() {
    await delay();
    return {
      contract_version: "1.0.0",
      jobs: clone([...adminRescans.values()].map((r) => r.job).reverse()),
      page_info: { has_next_page: false },
    };
  },
  // ── Architecture Canvas ──────────────────────────────────────────────────
  getArchitectureTaxonomy: async () => {
    const { taxonomy } = await loadCanvasFixtures();
    await delay();
    return clone(taxonomy);
  },
  listCanvasReferenceModels: async () => {
    const { referenceModel } = await loadCanvasFixtures();
    await delay();
    return { contract_version: "1.0.0" as const, models: [clone(referenceModel)] };
  },
  getCanvasReferenceModel: async (key) => {
    const { referenceModel } = await loadCanvasFixtures();
    await delay();
    if (key !== referenceModel.key) throw new FixtureApiError(404, { detail: "Unknown reference model" });
    return clone(referenceModel);
  },
  listCanvasTemplates: async () => {
    const { template } = await loadCanvasFixtures();
    await delay();
    return { contract_version: "1.0.0" as const, templates: [clone(template)] };
  },
  getCanvasTemplate: async (key, version) => {
    const { template } = await loadCanvasFixtures();
    await delay();
    if (key !== template.key || (version && version !== template.version)) {
      throw new FixtureApiError(404, {
        code: "CANVAS_TEMPLATE_NOT_FOUND",
        message: "The canvas template was not found.",
      });
    }
    return clone(template);
  },
  getCanvasProjection: async (params) => {
    const bundle = await loadCanvasFixtures();
    await delay(180);
    if (params.scope === "TARGET") return applyProfileToTarget(bundle.target, activeProfile(bundle));
    if (params.scope === "APPLICATION" || params.scope === "REPOSITORY") {
      const projection = clone(bundle.application);
      projection.scope = params.scope;
      if (params.subjectId && projection.subject) projection.subject.id = params.subjectId;
      return projection;
    }
    return clone(bundle.estate);
  },
  getCanvasTargetProjection: async () => {
    const bundle = await loadCanvasFixtures();
    await delay(180);
    // Mirrors the published route, which takes no profile selector: the target is
    // always the revision in force. See the draft-preview note in canvasQueries.ts.
    return applyProfileToTarget(bundle.target, activeProfile(bundle));
  },
  createCanvasComparison: async (body) => {
    const bundle = await loadCanvasFixtures();
    await delay(220);
    // The contract reserves TIME_TO_TIME but the server rejects it at validation, so
    // the fixture refuses it too rather than quietly returning a comparison.
    if (body.comparison_kind === "TIME_TO_TIME") {
      throw new FixtureApiError(422, {
        code: "UNSUPPORTED_COMPARISON",
        message: "Time-to-time comparison is reserved and not yet implemented.",
      });
    }
    return { ...clone(bundle.comparison), comparison_kind: body.comparison_kind };
  },
  listArchitectureProfiles: async () => {
    const bundle = await loadCanvasFixtures();
    await delay();
    // The published list returns summaries: no `state`, matching the real contract.
    const summaries: ArchitectureProfileSummary[] = bundle.profiles.map((profile) => ({
      id: profile.id,
      profile_key: profile.profile_key,
      name: profile.name,
      reference_model_key: profile.reference_model_key,
      reference_model_version: profile.reference_model_version,
      version: profile.version,
      status: profile.status,
      fingerprint: profile.fingerprint,
      created_at: profile.created_at,
      updated_at: profile.updated_at,
    }));
    return { contract_version: "1.0.0" as const, profiles: clone(summaries) };
  },
  createArchitectureProfile: async (body) => {
    const bundle = await loadCanvasFixtures();
    await delay();
    // A draft is a NEW revision. Earlier ones stay, and the active one stays active
    // until the draft is published.
    const highest = Math.max(...bundle.profiles.map((entry) => entry.version), 0);
    const draft: ArchitectureProfileDetail = {
      id: uuidFromSeed(`${body.profile_key}:${highest + 1}`),
      profile_key: body.profile_key,
      name: body.state.name,
      reference_model_key: body.state.reference_model_key,
      reference_model_version: body.state.reference_model_version,
      version: highest + 1,
      status: "DRAFT",
      fingerprint: canvasFingerprint(JSON.stringify(body.state)),
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      state: clone(body.state),
    };
    bundle.profiles = [...bundle.profiles, draft];
    return clone(draft);
  },
  updateArchitectureProfile: async (id, body) => {
    const bundle = await loadCanvasFixtures();
    await delay();
    const index = bundle.profiles.findIndex((entry) => entry.id === id);
    if (index === -1) throw new FixtureApiError(404, { detail: "Unknown profile" });
    const current = bundle.profiles[index];
    // Version-based optimistic concurrency, exactly as the API enforces it.
    if (body.expected_version !== current.version) {
      throw new FixtureApiError(409, {
        code: "VERSION_CONFLICT",
        message: "The profile changed before this update was applied.",
      });
    }
    const next: ArchitectureProfileDetail = {
      ...current,
      name: body.state.name,
      version: current.version + 1,
      state: clone(body.state),
      fingerprint: canvasFingerprint(JSON.stringify(body.state)),
      updated_at: new Date().toISOString(),
    };
    bundle.profiles = bundle.profiles.map((entry, position) => (position === index ? next : entry));
    return clone(next);
  },
  publishArchitectureProfile: async (id, body) => {
    const bundle = await loadCanvasFixtures();
    await delay();
    const target = bundle.profiles.find((entry) => entry.id === id);
    if (!target) throw new FixtureApiError(404, { detail: "Unknown profile" });
    if (body.expected_version !== target.version) {
      throw new FixtureApiError(409, {
        code: "VERSION_CONFLICT",
        message: "The profile changed before this publish was applied.",
      });
    }
    // Exactly one revision is ever in force: publishing archives what it replaces.
    bundle.profiles = bundle.profiles.map((entry) =>
      entry.id === id
        ? { ...entry, status: "ACTIVE" as const, version: entry.version + 1, updated_at: new Date().toISOString() }
        : entry.status === "ACTIVE"
          ? { ...entry, status: "ARCHIVED" as const }
          : entry,
    );
    return clone(bundle.profiles.find((entry) => entry.id === id)!);
  },

};

async function req<T>(path: string, init?: RequestInit, allowRefresh = true): Promise<T> {
  const res = await fetch(`${config.apiBaseUrl}/api/v1${path}`, {
    ...init,
    headers: { Accept: "application/json", ...(init?.headers ?? {}) },
    // Tenant comes from the session cookie, never a client-supplied field (contract §31 / plan §7).
    credentials: "include",
  });
  if (res.status === 401 && allowRefresh && !path.startsWith("/auth/")) {
    const refreshed = await fetch(`${config.apiBaseUrl}/api/v1/auth/refresh`, {
      method: "POST",
      credentials: "include",
      headers: { Accept: "application/json" },
    });
    if (refreshed.ok) return req<T>(path, init, false);
  }
  if (!res.ok) {
    let detail: unknown;
    try {
      detail = await res.json();
    } catch {
      detail = { message: res.statusText };
    }
    throw new ApiRequestError(res.status, detail);
  }
  return (await res.json()) as T;
}

/**
 * Carries the server's own explanation into `message`.
 *
 * It used to read `StackGraph API 422` and nothing else, which told a user that
 * something was rejected but never what — and a 422 from a whole-state write is
 * exactly the case where the field path is the entire diagnosis.
 */
export class ApiRequestError extends Error {
  constructor(
    public status: number,
    public detail: unknown,
  ) {
    super(`StackGraph API ${status}${describeApiDetail(detail)}`);
    this.name = "ApiRequestError";
  }
}

/** Renders a FastAPI error body — either the house `{code, message}` or a 422's `detail[]`. */
function describeApiDetail(detail: unknown): string {
  if (!detail || typeof detail !== "object") return "";
  const body = detail as Record<string, unknown>;
  if (typeof body.message === "string" && body.message) {
    return `: ${body.message}`;
  }
  const issues = body.detail;
  if (Array.isArray(issues) && issues.length) {
    const rendered = issues
      .slice(0, 3)
      .map((issue) => {
        const entry = issue as { loc?: unknown[]; msg?: string };
        const path = Array.isArray(entry.loc)
          ? entry.loc.filter((part) => part !== "body").join(".")
          : "";
        return path ? `${path} — ${entry.msg ?? "invalid"}` : entry.msg ?? "invalid";
      })
      .join("; ");
    return `: ${rendered}${issues.length > 3 ? ` (and ${issues.length - 3} more)` : ""}`;
  }
  if (typeof issues === "string" && issues) return `: ${issues}`;
  return "";
}

const liveClient: StackGraphClient = {
  getEstateSummary: (params) => {
    const query = new URLSearchParams();
    if (params?.cursor) query.set("cursor", params.cursor);
    if (params?.limit) query.set("limit", String(params.limit));
    for (const domain of params?.domains ?? []) query.append("domain", domain);
    const suffix = query.size ? `?${query.toString()}` : "";
    return req(`/estate/summary${suffix}`);
  },
  getEstateStrata: () => req("/estate/strata"),
  getAISupplyChain: () => req("/estate/ai-supply-chain"),
  listEstateLineage: (entityId, limit = 100) => {
    const query = new URLSearchParams({ limit: String(limit) });
    if (entityId) query.set("entity_id", entityId);
    return req(`/estate/lineage?${query.toString()}`);
  },
  listAssumptions: (subjectId, status, limit = 50) => {
    const query = new URLSearchParams({ limit: String(limit) });
    if (subjectId) query.set("subject_id", subjectId);
    if (status) query.set("status", status);
    return req(`/assumptions?${query.toString()}`);
  },
  getAssumption: (id) => req(`/assumptions/${encodeURIComponent(id)}`),
  createAssumption: (body) =>
    req("/assumptions", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  resolveContradiction: (id, body) =>
    req(`/contradictions/${encodeURIComponent(id)}/resolve`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  compileCapabilityEnvelope: (body) =>
    req("/agent-control/envelopes", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  getCapabilityEnvelope: (id) => req(`/agent-control/envelopes/${encodeURIComponent(id)}`),
  authorizeAgentOperation: (id, body) =>
    req(`/agent-control/envelopes/${encodeURIComponent(id)}/authorize`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  decideAgentApproval: (id, body) =>
    req(`/agent-control/approvals/${encodeURIComponent(id)}/decision`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  getAgentKillSwitch: () => req("/agent-control/kill-switch"),
  updateAgentKillSwitch: (body) =>
    req("/agent-control/kill-switch", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  createFlightRecord: (body) =>
    req("/agent-control/flight-records", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  getFlightRecord: (id) => req(`/agent-control/flight-records/${encodeURIComponent(id)}`),
  appendFlightEvent: (id, body) =>
    req(`/agent-control/flight-records/${encodeURIComponent(id)}/events`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  finalizeFlightRecord: (id, body) =>
    req(`/agent-control/flight-records/${encodeURIComponent(id)}/finalize`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  runAgentControlDrill: (body) =>
    req("/agent-control/drills", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  listContradictions: (subjectId, limit = 50) => {
    const query = new URLSearchParams({ limit: String(limit) });
    if (subjectId) query.set("subject_id", subjectId);
    return req(`/contradictions?${query.toString()}`);
  },
  listComponents: (cursor, limit = 50) =>
    req(`/components?limit=${limit}${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ""}`),
  getComponent: (id) => req(`/components/${encodeURIComponent(id)}`),
  getApplication: (id) => req(`/applications/${id}`),
  updateApplication: (id, body) =>
    req(`/applications/${id}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  getRepository: (id) => req(`/repositories/${id}`),
  listRepositoryContainerCompositions: (id) =>
    req(`/repositories/${encodeURIComponent(id)}/container-compositions`),
  listRepositoryDeploymentProfiles: (id) =>
    req(`/repositories/${encodeURIComponent(id)}/deployment-profiles`),
  updateRepository: (id, body) =>
    req(`/repositories/${id}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  getRepositoryActivity: (id, params) => {
    const query = new URLSearchParams();
    if (params?.window) query.set("window", params.window);
    if (params?.cursor) query.set("cursor", params.cursor);
    if (params?.limit != null) query.set("limit", String(params.limit));
    return req(`/repositories/${id}/activity${query.size ? `?${query.toString()}` : ""}`);
  },
  getTechnology: (id) => req(`/technologies/${id}`),
  getTechnologyEstateHierarchy: () => req("/technologies/hierarchy"),
  listModernization: () => req("/modernization"),
  listDeterministicInsights: (params) => {
    const query = new URLSearchParams();
    if (params?.scopeEntityId) query.set("scope_entity_id", params.scopeEntityId);
    if (params?.ruleKey) query.set("rule_key", params.ruleKey);
    if (params?.limit) query.set("limit", String(params.limit));
    return req(`/insights/deterministic${query.size ? `?${query.toString()}` : ""}`);
  },
  listEnterpriseInsightReports: () => req("/insights/reports"),
  listCapabilityFootprints: () => req("/capabilities/footprints"),
  optimizeModernizationScenario: (body) =>
    req("/modernization/scenarios", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    }),
  ask: (body) => req("/ask", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  getGraphNeighborhood: (centerId, depth = 1) =>
    req(`/graph/neighborhood?center_id=${encodeURIComponent(centerId)}&depth=${depth}`),
  getGraphIntelligenceStatus: () => req("/graph-intelligence/status"),
  getEntityGraphMetrics: (id) => req(`/entities/${encodeURIComponent(id)}/graph-metrics`),
  getEntityBlastRadius: (id) => req(`/entities/${encodeURIComponent(id)}/blast-radius`),
  listGraphIntelligenceRisks: (limit = 20) => req(`/graph-intelligence/risks?limit=${limit}`),
  listGraphIntelligenceCommunities: (policyKey = "runtime-dependency", limit = 50) =>
    req(`/graph-intelligence/communities?policy_key=${encodeURIComponent(policyKey)}&limit=${limit}`),
  semanticSearch: (body) => req("/search/semantic", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  }),
  getEmbeddingStatus: () => req("/embeddings/status"),
  listSimilarApplications: (id, limit = 10) =>
    req(`/entities/${encodeURIComponent(id)}/similar?limit=${limit}`),
  reviewApplicationSimilarity: (id, body) =>
    req(`/similarity-candidates/${encodeURIComponent(id)}/review`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    }),
  getFactEvidence: (factId) => req(`/facts/${factId}/evidence`),
  reviewIdentityAssertion: (id, body) =>
    req(`/identity-assertions/${id}/review`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  getCapabilityTaxonomy: (version) =>
    req(`/capabilities/taxonomy${version ? `?version=${encodeURIComponent(version)}` : ""}`),
  getRepositoryCapabilities: (id) => req(`/repositories/${id}/capabilities`),
  reviewCapabilityInference: (id, body) =>
    req(`/capability-inferences/${id}/review`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    }),
  reviewDuplicateCapabilityCandidate: (id, body) =>
    req(`/duplicate-capability-candidates/${id}/review`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    }),
  getRepositoryModernizationIntelligence: (id, limit = 50) =>
    req(`/repositories/${id}/modernization-intelligence?limit=${limit}`),
  reviewModernizationCandidate: (id, body) =>
    req(`/modernization-candidates/${id}/review`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    }),
  reviewModernizationRecommendation: (id, body) =>
    req(`/modernization-recommendations/${id}/review`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    }),
  recordModernizationValidationOutcome: (id, body) =>
    req(`/modernization-recommendations/${id}/validation-outcomes`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    }),
  getPhase3IntelligenceMetrics: () => req("/intelligence/phase-3/metrics"),
  listBusinessMaps: (cursor, limit = 50) =>
    req(`/business-maps?limit=${limit}${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ""}`),
  createBusinessMap: (body) =>
    req("/business-maps", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  getBusinessMap: (id) => req(`/business-maps/${id}`),
  saveBusinessMap: (id, body) =>
    req(`/business-maps/${id}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  archiveBusinessMap: (id) => req(`/business-maps/${id}`, { method: "DELETE" }),
  getBusinessMapRevisions: (id) => req(`/business-maps/${id}/revisions`),
  getSession: () => req("/session"),
  getReviewQueue: (params) => {
    const search = new URLSearchParams();
    for (const type of params?.types ?? []) search.append("type", type);
    if (params?.repository) search.set("repository", params.repository);
    if (params?.cursor) search.set("cursor", params.cursor);
    if (params?.limit != null) search.set("limit", String(params.limit));
    const query = search.toString();
    return req(`/reviews/queue${query ? `?${query}` : ""}`);
  },
  listMembers: () => req("/admin/members"),
  inviteMember: (body) =>
    req("/admin/members", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  updateMember: (id, body) =>
    req(`/admin/members/${id}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  removeMember: (id) => req(`/admin/members/${id}`, { method: "DELETE" }),
  listConnectors: () => req("/admin/connectors"),
  registerConnector: (body) =>
    req("/admin/connectors", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  listAvailableGitHubRepositories: () => req("/admin/github/repositories/available"),
  getGitHubTokenConfiguration: () => req("/admin/github/token"),
  updateGitHubToken: (body) =>
    req("/admin/github/token", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  removeGitHubToken: () => req("/admin/github/token", { method: "DELETE" }),
  connectGitHubRepository: (body) =>
    req("/admin/github/repositories", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  connectGitHubInstallation: (body) =>
    req("/admin/github/installations", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  startGitHubInstallationSetup: (body) =>
    req("/admin/github/installations/setup", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  updateConnector: (id, body) =>
    req(`/admin/connectors/${id}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  removeConnector: (id) => req(`/admin/connectors/${id}`, { method: "DELETE" }),
  getModernizationGovernance: () => req("/admin/modernization-governance"),
  getDeterministicInsightGovernance: () => req("/admin/deterministic-insight-governance"),
  updateDeterministicInsightRule: (ruleKey, body) =>
    req(`/admin/deterministic-insight-governance/rules/${encodeURIComponent(ruleKey)}`, {
      method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    }),
  publishModernizationPolicy: (body) =>
    req("/admin/modernization-governance/policy", {
      method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    }),
  governInternalCatalogComponent: (componentKey, body) =>
    req(`/admin/modernization-governance/internal-components/${encodeURIComponent(componentKey)}`, {
      method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    }),
  publishCalibrationCorpus: (body) =>
    req("/admin/modernization-governance/calibration", {
      method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    }),
  evaluateEcosystemAdmission: (ecosystem, body) =>
    req(`/admin/modernization-governance/ecosystems/${encodeURIComponent(ecosystem)}`, {
      method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    }),
  getTenantCodePolicies: () => req("/admin/code-policies"),
  upsertTenantCodeFunction: (functionKey, body) =>
    req(`/admin/code-policies/functions/${encodeURIComponent(functionKey)}`, {
      method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    }),
  evaluateTenantCodePolicies: () =>
    req("/admin/code-policies/evaluations", { method: "POST" }),
  getAIProviderConfiguration: () => req("/admin/ai-configuration"),
  updateAIProviderConfiguration: (body) =>
    req("/admin/ai-configuration", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  removeAIProviderKey: () => req("/admin/ai-configuration/key", { method: "DELETE" }),
  testAIProviderConnection: () => req("/admin/ai-configuration/test", { method: "POST" }),
  getScanPolicy: () => req("/admin/scan-policy"),
  updateScanPolicy: (body) =>
    req("/admin/scan-policy", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  getScanStatus: () => req("/admin/scan-status"),
  getServiceStatus: () => req("/admin/services"),
  updateServiceControl: (serviceKey, body) =>
    req(`/admin/services/${encodeURIComponent(serviceKey)}`, {
      method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    }),
  requestRescan: (body) =>
    req("/admin/rescans", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  listRescans: (cursor, limit = 50) =>
    req(`/admin/rescans?limit=${limit}${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ""}`),
  // ── Phase 2 change compiler and simulation ───────────────────────────────
  listActionTypes: () => req("/action-types"),
  listActionSubjects: (predicate, query, limit = 25) => {
    const search = new URLSearchParams({ limit: String(limit) });
    if (query) search.set("query", query);
    return req(`/action-types/${encodeURIComponent(predicate)}/subjects?${search.toString()}`);
  },
  listValidTargets: (id, limit = 50) =>
    req(`/entities/${encodeURIComponent(id)}/valid-targets?limit=${limit}`),
  listChangeScopes: (id) => req(`/entities/${encodeURIComponent(id)}/scopes`),
  listEntityChangeHistory: (id, limit = 20) =>
    req(`/entities/${encodeURIComponent(id)}/change-history?limit=${limit}`),
  compileMutation: (body) =>
    req("/mutations/compile", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    }),
  validateMutation: (body) =>
    req("/mutations/validate", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    }),
  compileModernizationRecommendation: (id, body) =>
    req(`/modernization-recommendations/${encodeURIComponent(id)}/compile`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    }),
  compileDeterministicInsight: (id, body) =>
    req(`/insights/deterministic/${encodeURIComponent(id)}/compile`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    }),
  compileChangeSet: (body) =>
    req("/change-sets/compile", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    }),
  createSimulation: (body) =>
    req("/simulations", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    }),
  getSimulation: (id) => req(`/simulations/${encodeURIComponent(id)}`),
  cancelSimulation: (id) => req(`/simulations/${encodeURIComponent(id)}`, { method: "DELETE" }),
  recordObservedMutation: (body) =>
    req("/observed-mutations", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    }),
  listRepositoryFingerprints: (id, limit = 20) =>
    req(`/repositories/${encodeURIComponent(id)}/fingerprints?limit=${limit}`),
  // ── Graph-intelligence reachability gaps ─────────────────────────────────
  listEntityCriticalEdges: (id) => req(`/entities/${encodeURIComponent(id)}/critical-edges`),
  listGraphIntelligenceAnomalies: (cohortKey, limit = 50) => {
    const search = new URLSearchParams({ limit: String(limit) });
    if (cohortKey) search.set("cohort_key", cohortKey);
    return req(`/graph-intelligence/anomalies?${search.toString()}`);
  },
  listGraphIntelligenceMotifs: (motifKey, limit = 50) => {
    const search = new URLSearchParams({ limit: String(limit) });
    if (motifKey) search.set("motif_key", motifKey);
    return req(`/graph-intelligence/motifs?${search.toString()}`);
  },
  requestGraphAnalysis: (body) =>
    req("/graph-intelligence/analysis-requests", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    }),
  // ── Architecture Canvas ──────────────────────────────────────────────────
  getArchitectureTaxonomy: () => req("/canvas/taxonomy"),
  listCanvasReferenceModels: () => req("/canvas/reference-models"),
  getCanvasReferenceModel: (key, version) =>
    req(`/canvas/reference-models/${encodeURIComponent(key)}${version ? `?version=${encodeURIComponent(version)}` : ""}`),
  listCanvasTemplates: () => req("/canvas/templates"),
  getCanvasTemplate: (key, version) =>
    req(`/canvas/templates/${encodeURIComponent(key)}${version ? `?version=${encodeURIComponent(version)}` : ""}`),
  getCanvasProjection: (params) => {
    const query = new URLSearchParams({ scope: params.scope });
    if (params.subjectId) query.set("subject_id", params.subjectId);
    if (params.referenceModelKey) query.set("reference_model_key", params.referenceModelKey);
    if (params.templateKey) query.set("template_key", params.templateKey);
    return req(`/canvas/projection?${query.toString()}`);
  },
  getCanvasTargetProjection: (params) => {
    const query = new URLSearchParams();
    if (params?.referenceModelKey) query.set("reference_model_key", params.referenceModelKey);
    if (params?.templateKey) query.set("template_key", params.templateKey);
    return req(`/canvas/target-projection${query.size ? `?${query.toString()}` : ""}`);
  },
  createCanvasComparison: (body) =>
    req("/canvas/comparisons", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    }),
  listArchitectureProfiles: () => req("/admin/architecture-profiles"),
  createArchitectureProfile: (body) =>
    req("/admin/architecture-profiles", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    }),
  updateArchitectureProfile: (id, body) =>
    req(`/admin/architecture-profiles/${encodeURIComponent(id)}`, {
      method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    }),
  publishArchitectureProfile: (id, body) =>
    req(`/admin/architecture-profiles/${encodeURIComponent(id)}/publish`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    }),
};

export const stackGraphClient: StackGraphClient = isFixtureMode() ? fixtureClient : liveClient;
