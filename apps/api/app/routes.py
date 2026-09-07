from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Literal, Protocol
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import RedirectResponse

from app.auth import Principal
from app.errors import APIError
from app.models import (
    AdversarialScenarioClass,
    AdversarialScenarioGenerateRequest,
    AdversarialScenarioList,
    ApplicationDetail,
    ApplicationSimilarityList,
    ApplicationSimilarityReviewRequest,
    ApplicationSimilarityReviewResult,
    AIProviderConfiguration,
    HarnessEvaluationCompleteRequest,
    HarnessEvaluationModel,
    HarnessEvaluationRecordRequest,
    HarnessEvaluationStartRequest,
    HarnessChampionList,
    HarnessPromotionDecisionRequest,
    HarnessPromotionModel,
    HarnessPromotionProposeRequest,
    HarnessPromotionRollbackRequest,
    AIProviderConfigurationUpdateRequest,
    AIProviderConnectionTest,
    AskRequest,
    AskResponse,
    ArchitectureProfileCreateRequest,
    ArchitectureProfileDetail,
    ArchitectureProfileList,
    ArchitectureProfilePublishRequest,
    ArchitectureProfileUpdateRequest,
    ArchitectureReferenceModel,
    ArchitectureReferenceModelList,
    ArchitectureTaxonomyResponse,
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
    BusinessMapCreateRequest,
    BusinessMapDetail,
    BusinessMapList,
    BusinessMapRevisionList,
    BusinessMapSaveRequest,
    BusinessMapSummary,
    CapabilityInferenceReviewRequest,
    CapabilityInferenceReviewResult,
    CapabilityTaxonomyResponse,
    CapabilityFootprintList,
    CapabilityEnvelopeCompileRequest,
    CapabilityEnvelopeModel,
    CanvasComparison,
    CanvasComparisonRequest,
    CanvasProjection,
    CanvasProjectionScope,
    CanvasProjectionSelectorModel,
    CanvasTemplateList,
    CanvasTemplateModel,
    DuplicateCapabilityReviewRequest,
    DuplicateCapabilityReviewResult,
    DeterministicInsightList,
    DeterministicInsightGovernanceState,
    DeterministicInsightRuleUpdateRequest,
    EnterpriseInsightReportList,
    EmbeddingStatus,
    EntityDescriptionUpdateRequest,
    EntitySummary,
    EstateSummary,
    EvidenceDetail,
    EntityGraphIntelligence,
    GraphBlastRadius,
    GraphCommunityList,
    GraphAnomalyList,
    GraphMotifList,
    CriticalGraphEdgeList,
    GraphIntelligenceStatus,
    GraphNeighborhood,
    GraphRiskList,
    GraphAnalysisRequestCreate,
    GraphAnalysisRequestResult,
    EmbeddingBackfillRequest,
    EmbeddingBackfillResult,
    EmbeddingSpacePromotionRequest,
    EmbeddingSpacePromotionResult,
    ContainerCompositionList,
    ContradictionLedger,
    DeploymentProfileList,
    EstateComponentDetail,
    EstateComponentList,
    EstateStrata,
    EstateLineageList,
    IdentityReviewRequest,
    IdentityReviewResult,
    ModernizationList,
    ModernizationScenarioRequest,
    ModernizationScenarioResult,
    ModernizationCandidateReviewRequest,
    ModernizationCandidateReviewResult,
    ModernizationRecommendationReviewRequest,
    ModernizationRecommendationReviewResult,
    ModernizationValidationOutcomeRequest,
    ModernizationValidationOutcomeResult,
    Namespace,
    RepositoryCapabilityIntelligence,
    RepositoryActivity,
    RepositoryDetail,
    RepositoryModernizationIntelligence,
    Phase3IntelligenceMetrics,
    ModernizationGovernanceState,
    ModernizationPolicyPublishRequest,
    InternalCatalogComponentUpsertRequest,
    CalibrationCorpusPublishRequest,
    EcosystemAdmissionEvaluateRequest,
    EcosystemName,
    TenantCodeFunctionUpsertRequest,
    TenantCodePolicyState,
    SessionInfo,
    TechnologyEstateHierarchy,
    TechnologyDetail,
    ReviewQueue,
    ReviewQueueItemType,
    TenantMember,
    TenantMemberList,
    MemberInviteRequest,
    MemberUpdateRequest,
    Connector,
    ConnectorList,
    ConnectorRegisterRequest,
    GitHubRepositoryConnectRequest,
    GitHubRepositoryOptionList,
    GitHubTokenConfiguration,
    GitHubTokenUpdateRequest,
    ConnectorUpdateRequest,
    GitHubInstallationConnectRequest,
    GitHubInstallationSetupRequest,
    GitHubInstallationSetupResponse,
    ScanPolicy,
    ScanPolicyUpdateRequest,
    RescanRequest,
    RescanJob,
    RescanJobList,
    ScanStatus,
    ServiceControlRequest,
    ServiceStatus,
    ServiceStatusList,
    SemanticSearchRequest,
    SemanticSearchResponse,
    ActionTypeList,
    ActionSubjectList,
    ValidTargetList,
    ChangeScopeList,
    ChangeSetCompileRequest,
    MutationCompileRequest,
    MutationCompileResult,
    MutationValidateRequest,
    ObservedMutationCreateRequest,
    ObservedMutationList,
    ObservedMutationModel,
    RecommendationCompileRequest,
    RepositoryFingerprintList,
    SimulationCreateRequest,
    SimulationRunModel,
    ContradictionResolveRequest,
    FlightEventCreateRequest,
    FlightRecordCreateRequest,
    FlightRecordFinalizeRequest,
    FlightRecordModel,
)


class ReadModelsProtocol(Protocol):
    async def phase2_feature_enabled(
        self, flag_key: str, *, tenant_id: UUID | None,
    ) -> bool: ...
    async def action_types(self, *, tenant_id: UUID | None) -> ActionTypeList: ...
    async def action_subjects(
        self, predicate: str, *, tenant_id: UUID | None, query: str | None, limit: int,
    ) -> ActionSubjectList: ...
    async def valid_targets(
        self, entity_id: UUID, *, tenant_id: UUID | None, limit: int,
    ) -> ValidTargetList: ...
    async def scopes(self, entity_id: UUID, *, tenant_id: UUID | None) -> ChangeScopeList: ...
    async def repository_fingerprints(
        self, repository_id: UUID, *, tenant_id: UUID | None, limit: int,
    ) -> RepositoryFingerprintList: ...
    async def record_observed_mutation(
        self, request: ObservedMutationCreateRequest, *, tenant_id: UUID | None, actor_key: str,
    ) -> ObservedMutationModel: ...
    async def change_history(
        self, subject_id: UUID, *, tenant_id: UUID | None, limit: int,
    ) -> ObservedMutationList: ...
    async def compile_mutation(
        self, request: MutationCompileRequest, *, tenant_id: UUID | None, actor_key: str,
    ) -> MutationCompileResult: ...
    async def validate_mutation(
        self, request: MutationValidateRequest, *, tenant_id: UUID | None, actor_key: str,
    ) -> MutationCompileResult: ...
    async def compile_modernization_recommendation(
        self, recommendation_id: UUID, request: RecommendationCompileRequest,
        *, tenant_id: UUID | None, actor_key: str,
    ) -> MutationCompileResult: ...
    async def submit_simulation(
        self, request: SimulationCreateRequest, *, tenant_id: UUID | None, actor_key: str,
    ) -> SimulationRunModel: ...
    async def simulation(
        self, run_id: UUID, *, tenant_id: UUID | None,
    ) -> SimulationRunModel: ...
    async def cancel_simulation(
        self, run_id: UUID, *, tenant_id: UUID | None, actor_key: str,
    ) -> SimulationRunModel: ...
    async def estate_summary(
        self, *, tenant_id: UUID | None, cursor: str | None, limit: int,
        namespaces: list[str] | None = None, sort: str = "priority",
    ) -> EstateSummary: ...
    async def estate_strata(self, *, tenant_id: UUID | None) -> EstateStrata: ...
    async def contradiction_ledger(
        self, *, tenant_id: UUID | None, subject_id: UUID | None, limit: int,
    ) -> ContradictionLedger: ...
    async def create_assumption(
        self, request: AssumptionCreateRequest, *, tenant_id: UUID | None, actor_key: str,
    ) -> AssumptionModel: ...
    async def assumption(
        self, assumption_id: UUID, *, tenant_id: UUID | None,
    ) -> AssumptionModel: ...
    async def assumptions(
        self, *, tenant_id: UUID | None, subject_id: UUID | None, status: str | None, limit: int,
    ) -> AssumptionList: ...
    async def resolve_contradiction(
        self, contradiction_id: UUID, request: ContradictionResolveRequest, *,
        tenant_id: UUID | None, actor_key: str,
    ) -> None: ...
    async def estate_lineage(
        self, *, tenant_id: UUID | None, entity_id: UUID | None, limit: int,
    ) -> EstateLineageList: ...
    async def ai_supply_chain(self, *, tenant_id: UUID | None) -> AISupplyChain: ...
    async def compile_capability_envelope(
        self, request: CapabilityEnvelopeCompileRequest, *, tenant_id: UUID | None,
        actor_key: str,
    ) -> CapabilityEnvelopeModel: ...
    async def capability_envelope(
        self, envelope_id: UUID, *, tenant_id: UUID | None,
    ) -> CapabilityEnvelopeModel: ...
    async def authorize_agent_operation(
        self, envelope_id: UUID, request: AgentAuthorizeRequest, *, tenant_id: UUID | None,
        actor_key: str,
    ) -> AgentAuthorizationDecisionModel: ...
    async def decide_agent_approval(
        self, approval_id: UUID, request: AgentApprovalDecisionRequest, *,
        tenant_id: UUID | None, actor_key: str,
    ) -> AgentApprovalModel: ...
    async def agent_kill_switch(self, *, tenant_id: UUID | None) -> AgentKillSwitchModel: ...
    async def update_agent_kill_switch(
        self, request: AgentKillSwitchUpdateRequest, *, tenant_id: UUID | None, actor_key: str,
    ) -> AgentKillSwitchModel: ...
    async def create_flight_record(
        self, request: FlightRecordCreateRequest, *, tenant_id: UUID | None, actor_key: str,
    ) -> FlightRecordModel: ...
    async def append_flight_event(
        self, record_id: UUID, request: FlightEventCreateRequest, *, tenant_id: UUID | None,
    ) -> FlightRecordModel: ...
    async def finalize_flight_record(
        self, record_id: UUID, request: FlightRecordFinalizeRequest, *, tenant_id: UUID | None,
    ) -> FlightRecordModel: ...
    async def flight_record(
        self, record_id: UUID, *, tenant_id: UUID | None,
    ) -> FlightRecordModel: ...
    async def run_agent_control_drill(
        self, request: AgentControlDrillRequest, *, tenant_id: UUID | None, actor_key: str,
    ) -> AgentControlDrillResult: ...
    async def generate_adversarial_scenarios(
        self, request: AdversarialScenarioGenerateRequest, *, tenant_id: UUID | None,
        actor_key: str,
    ) -> AdversarialScenarioList: ...
    async def adversarial_scenarios(
        self, *, tenant_id: UUID | None, scenario_class: str | None, limit: int,
    ) -> AdversarialScenarioList: ...
    async def start_harness_evaluation(
        self, request: HarnessEvaluationStartRequest, *, tenant_id: UUID | None, actor_key: str,
    ) -> HarnessEvaluationModel: ...
    async def record_harness_evaluation_result(
        self, evaluation_id: UUID, request: HarnessEvaluationRecordRequest, *,
        tenant_id: UUID | None,
    ) -> HarnessEvaluationModel: ...
    async def complete_harness_evaluation(
        self, evaluation_id: UUID, request: HarnessEvaluationCompleteRequest, *,
        tenant_id: UUID | None, actor_key: str,
    ) -> HarnessEvaluationModel: ...
    async def harness_evaluation(
        self, evaluation_id: UUID, *, tenant_id: UUID | None,
    ) -> HarnessEvaluationModel: ...
    async def propose_harness_promotion(
        self, request: HarnessPromotionProposeRequest, *, tenant_id: UUID | None, actor_key: str,
    ) -> HarnessPromotionModel: ...
    async def decide_harness_promotion(
        self, promotion_id: UUID, request: HarnessPromotionDecisionRequest, *,
        tenant_id: UUID | None, actor_key: str,
    ) -> HarnessPromotionModel: ...
    async def roll_back_harness_promotion(
        self, promotion_id: UUID, request: HarnessPromotionRollbackRequest, *,
        tenant_id: UUID | None, actor_key: str,
    ) -> HarnessPromotionModel: ...
    async def harness_promotion(
        self, promotion_id: UUID, *, tenant_id: UUID | None,
    ) -> HarnessPromotionModel: ...
    async def harness_champions(self, *, tenant_id: UUID | None) -> HarnessChampionList: ...
    async def estate_components(
        self, *, tenant_id: UUID | None, cursor: UUID | None, limit: int,
    ) -> EstateComponentList: ...
    async def component_detail(
        self, component_id: UUID, *, tenant_id: UUID | None,
    ) -> EstateComponentDetail: ...
    async def repository_container_compositions(
        self, repository_id: UUID, *, tenant_id: UUID | None,
    ) -> ContainerCompositionList: ...
    async def repository_deployment_profiles(
        self, repository_id: UUID, *, tenant_id: UUID | None,
    ) -> DeploymentProfileList: ...
    async def application_detail(self, application_id: UUID, *, tenant_id: UUID | None) -> ApplicationDetail: ...
    async def architecture_taxonomy(self) -> ArchitectureTaxonomyResponse: ...
    async def architecture_reference_models(self) -> ArchitectureReferenceModelList: ...
    async def architecture_reference_model(
        self, key: str, *, version: str | None,
    ) -> ArchitectureReferenceModel: ...
    async def canvas_templates(self) -> CanvasTemplateList: ...
    async def canvas_projection(
        self, selector: CanvasProjectionSelectorModel, *, tenant_id: UUID | None,
        reference_model_key: str, template_key: str,
    ) -> CanvasProjection: ...
    async def canvas_comparison(
        self, request: CanvasComparisonRequest, *, tenant_id: UUID | None,
    ) -> CanvasComparison: ...
    async def repository_detail(self, repository_id: UUID, *, tenant_id: UUID | None) -> RepositoryDetail: ...
    async def repository_activity(
        self, repository_id: UUID, *, tenant_id: UUID | None, window: str,
        cursor: str | None, limit: int,
    ) -> RepositoryActivity: ...
    async def technology_detail(self, technology_id: UUID, *, tenant_id: UUID | None) -> TechnologyDetail: ...
    async def technology_estate_hierarchy(self, *, tenant_id: UUID | None) -> TechnologyEstateHierarchy: ...
    async def modernization(self, *, tenant_id: UUID | None, cursor: str | None, limit: int) -> ModernizationList: ...
    async def deterministic_insights(
        self, *, tenant_id: UUID | None, scope_entity_id: UUID | None,
        rule_key: str | None, limit: int,
    ) -> DeterministicInsightList: ...
    async def enterprise_insight_reports(
        self, *, tenant_id: UUID | None,
    ) -> EnterpriseInsightReportList: ...
    async def capability_footprints(self, *, tenant_id: UUID | None) -> CapabilityFootprintList: ...
    async def modernization_scenario(
        self, request: ModernizationScenarioRequest, *, tenant_id: UUID | None,
    ) -> ModernizationScenarioResult: ...
    async def graph_neighborhood(
        self, center_id: UUID, *, tenant_id: UUID | None, depth: int, real_node_limit: int,
        predicates: list[str] | None, namespaces: list[str] | None,
        min_confidence: float, highlight_to: UUID | None,
    ) -> GraphNeighborhood: ...
    async def graph_intelligence_status(
        self, *, tenant_id: UUID | None,
    ) -> GraphIntelligenceStatus: ...
    async def entity_graph_metrics(
        self, entity_id: UUID, *, tenant_id: UUID | None,
    ) -> EntityGraphIntelligence: ...
    async def graph_blast_radius(
        self, entity_id: UUID, *, tenant_id: UUID | None,
    ) -> GraphBlastRadius: ...
    async def graph_risks(
        self, *, tenant_id: UUID | None, entity_type: str | None,
        namespace: str | None, community_key: str | None, min_score: float,
        cursor: str | None, limit: int,
    ) -> GraphRiskList: ...
    async def graph_anomalies(
        self, *, tenant_id: UUID | None, cohort_key: str | None, limit: int,
    ) -> GraphAnomalyList: ...
    async def graph_motifs(
        self, *, tenant_id: UUID | None, motif_key: str | None, limit: int,
    ) -> GraphMotifList: ...
    async def critical_edges(
        self, entity_id: UUID, *, tenant_id: UUID | None,
    ) -> CriticalGraphEdgeList: ...
    async def graph_communities(
        self, *, tenant_id: UUID | None, policy_key: str, limit: int,
    ) -> GraphCommunityList: ...
    async def semantic_search(
        self, request: SemanticSearchRequest, *, tenant_id: UUID | None,
    ) -> SemanticSearchResponse: ...
    async def embedding_status(self, *, tenant_id: UUID | None) -> EmbeddingStatus: ...
    async def similar_applications(
        self, application_id: UUID, *, tenant_id: UUID | None,
        review_state: str | None, cursor: str | None, limit: int,
    ) -> ApplicationSimilarityList: ...
    async def review_application_similarity(
        self, candidate_id: UUID, review: ApplicationSimilarityReviewRequest,
        *, tenant_id: UUID | None, actor_key: str,
    ) -> ApplicationSimilarityReviewResult: ...
    async def request_graph_analysis(
        self, request: GraphAnalysisRequestCreate, *, tenant_id: UUID | None, actor_key: str,
    ) -> tuple[GraphAnalysisRequestResult,bool]: ...
    async def request_embedding_backfill(
        self, request: EmbeddingBackfillRequest, *, tenant_id: UUID | None, actor_key: str,
    ) -> EmbeddingBackfillResult: ...
    async def promote_embedding_space(
        self, space_id: UUID, request: EmbeddingSpacePromotionRequest,
        *, tenant_id: UUID | None, actor_key: str,
    ) -> EmbeddingSpacePromotionResult: ...
    async def evidence_detail(self, fact_id: UUID, *, tenant_id: UUID | None) -> EvidenceDetail: ...
    async def ask(self, request: AskRequest, *, tenant_id: UUID | None) -> AskResponse: ...
    async def review_identity_assertion(
        self, assertion_id: UUID, review: IdentityReviewRequest, *, tenant_id: UUID | None, actor_key: str,
    ) -> IdentityReviewResult: ...
    async def capability_taxonomy(
        self, *, tenant_id: UUID | None, version: str | None,
    ) -> CapabilityTaxonomyResponse: ...
    async def repository_capabilities(
        self, repository_id: UUID, *, tenant_id: UUID | None,
    ) -> RepositoryCapabilityIntelligence: ...
    async def review_capability_inference(
        self, inference_id: UUID, review: CapabilityInferenceReviewRequest,
        *, tenant_id: UUID | None, actor_key: str,
    ) -> CapabilityInferenceReviewResult: ...
    async def review_duplicate_capability_candidate(
        self, candidate_id: UUID, review: DuplicateCapabilityReviewRequest,
        *, tenant_id: UUID | None, actor_key: str,
    ) -> DuplicateCapabilityReviewResult: ...
    async def repository_modernization_intelligence(
        self, repository_id: UUID, *, tenant_id: UUID | None, limit: int,
    ) -> RepositoryModernizationIntelligence: ...
    async def review_modernization_recommendation(
        self, recommendation_id: UUID, review: ModernizationRecommendationReviewRequest,
        *, tenant_id: UUID | None, actor_key: str,
    ) -> ModernizationRecommendationReviewResult: ...
    async def review_modernization_candidate(
        self, candidate_id: UUID, review: ModernizationCandidateReviewRequest,
        *, tenant_id: UUID | None, actor_key: str,
    ) -> ModernizationCandidateReviewResult: ...
    async def record_modernization_validation_outcome(
        self, recommendation_id: UUID, outcome: ModernizationValidationOutcomeRequest,
        *, tenant_id: UUID | None, actor_key: str,
    ) -> ModernizationValidationOutcomeResult: ...
    async def phase3_intelligence_metrics(
        self, *, tenant_id: UUID | None,
    ) -> Phase3IntelligenceMetrics: ...
    async def get_modernization_governance(
        self, *, tenant_id: UUID | None,
    ) -> ModernizationGovernanceState: ...
    async def get_deterministic_insight_governance(
        self, *, tenant_id: UUID | None,
    ) -> DeterministicInsightGovernanceState: ...
    async def update_deterministic_insight_rule(
        self, rule_key: str, request: DeterministicInsightRuleUpdateRequest,
        *, tenant_id: UUID | None, actor_key: str,
    ) -> DeterministicInsightGovernanceState: ...
    async def publish_modernization_policy(
        self, request: ModernizationPolicyPublishRequest,
        *, tenant_id: UUID | None, actor_key: str,
    ) -> ModernizationGovernanceState: ...
    async def govern_internal_component(
        self, component_key: str, request: InternalCatalogComponentUpsertRequest,
        *, tenant_id: UUID | None, actor_key: str,
    ) -> ModernizationGovernanceState: ...
    async def publish_calibration_corpus(
        self, request: CalibrationCorpusPublishRequest,
        *, tenant_id: UUID | None, actor_key: str,
    ) -> ModernizationGovernanceState: ...
    async def evaluate_ecosystem_admission(
        self, ecosystem: EcosystemName, request: EcosystemAdmissionEvaluateRequest,
        *, tenant_id: UUID | None, actor_key: str,
    ) -> ModernizationGovernanceState: ...
    async def get_tenant_code_policies(
        self, *, tenant_id: UUID | None,
    ) -> TenantCodePolicyState: ...
    async def upsert_tenant_code_function(
        self, function_key: str, request: TenantCodeFunctionUpsertRequest,
        *, tenant_id: UUID | None, actor_key: str,
    ) -> TenantCodePolicyState: ...
    async def evaluate_tenant_code_policies(
        self, *, tenant_id: UUID | None, actor_key: str,
    ) -> TenantCodePolicyState: ...
    async def list_business_maps(
        self, *, tenant_id: UUID | None, cursor: str | None, limit: int,
    ) -> BusinessMapList: ...
    async def create_business_map(
        self, request: BusinessMapCreateRequest, *, tenant_id: UUID | None, actor_key: str,
    ) -> BusinessMapDetail: ...
    async def business_map_detail(
        self, map_id: UUID, *, tenant_id: UUID | None,
    ) -> BusinessMapDetail: ...
    async def save_business_map(
        self, map_id: UUID, request: BusinessMapSaveRequest, *, tenant_id: UUID | None, actor_key: str,
    ) -> BusinessMapDetail: ...
    async def archive_business_map(
        self, map_id: UUID, *, tenant_id: UUID | None, actor_key: str,
    ) -> BusinessMapSummary: ...
    async def business_map_revisions(
        self, map_id: UUID, *, tenant_id: UUID | None,
    ) -> BusinessMapRevisionList: ...
    async def list_architecture_profiles(
        self, *, tenant_id: UUID | None,
    ) -> ArchitectureProfileList: ...
    async def create_architecture_profile(
        self, request: ArchitectureProfileCreateRequest,
        *, tenant_id: UUID | None, actor_key: str,
    ) -> ArchitectureProfileDetail: ...
    async def update_architecture_profile(
        self, profile_id: UUID, request: ArchitectureProfileUpdateRequest,
        *, tenant_id: UUID | None, actor_key: str,
    ) -> ArchitectureProfileDetail: ...
    async def publish_architecture_profile(
        self, profile_id: UUID, request: ArchitectureProfilePublishRequest,
        *, tenant_id: UUID | None, actor_key: str,
    ) -> ArchitectureProfileDetail: ...
    async def review_queue(
        self, *, tenant_id: UUID | None, item_types: list[ReviewQueueItemType] | None,
        repository_id: UUID | None, cursor: str | None, limit: int,
    ) -> ReviewQueue: ...
    async def list_tenant_members(self, *, tenant_id: UUID | None) -> TenantMemberList: ...
    async def invite_tenant_member(
        self, request: MemberInviteRequest, *, tenant_id: UUID | None, actor_key: str,
    ) -> TenantMember: ...
    async def update_tenant_member(
        self, member_id: UUID, request: MemberUpdateRequest, *, tenant_id: UUID | None, actor_key: str,
    ) -> TenantMember: ...
    async def remove_tenant_member(
        self, member_id: UUID, *, tenant_id: UUID | None, actor_key: str,
    ) -> TenantMember: ...
    async def list_connectors(self, *, tenant_id: UUID | None) -> ConnectorList: ...
    async def register_connector(
        self, request: ConnectorRegisterRequest, *, tenant_id: UUID | None, actor_key: str,
    ) -> Connector: ...
    async def connect_github_repository(
        self, request: GitHubRepositoryConnectRequest, *, tenant_id: UUID | None, actor_key: str,
    ) -> Connector: ...
    async def list_available_github_repositories(
        self, *, tenant_id: UUID | None,
    ) -> GitHubRepositoryOptionList: ...
    async def get_github_token_configuration(
        self, *, tenant_id: UUID | None,
    ) -> GitHubTokenConfiguration: ...
    async def update_github_token(
        self, request: GitHubTokenUpdateRequest, *, tenant_id: UUID | None, actor_key: str,
    ) -> GitHubTokenConfiguration: ...
    async def remove_github_token(
        self, *, tenant_id: UUID | None, actor_key: str,
    ) -> GitHubTokenConfiguration: ...
    async def connect_github_installation(
        self, request: GitHubInstallationConnectRequest, *, tenant_id: UUID | None, actor_key: str,
    ) -> Connector: ...
    async def begin_github_installation_setup(
        self, *, state_hash: str, return_to: str, expires_at: datetime,
        tenant_id: UUID | None, actor_key: str,
    ) -> None: ...
    async def validate_github_installation_setup(
        self, *, state_hash: str, tenant_id: UUID | None, actor_key: str,
    ) -> str: ...
    async def complete_hosted_github_installation(
        self, *, state_hash: str, installation_id: str, account_login: str,
        account_id: int, target_type: str, scopes: list[str], tenant_id: UUID | None,
        actor_key: str,
    ) -> Connector: ...
    async def update_connector(
        self, connector_id: UUID, request: ConnectorUpdateRequest, *, tenant_id: UUID | None, actor_key: str,
    ) -> Connector: ...
    async def remove_connector(
        self, connector_id: UUID, *, tenant_id: UUID | None, actor_key: str,
    ) -> Connector: ...
    async def get_ai_provider_configuration(
        self, *, tenant_id: UUID | None,
    ) -> AIProviderConfiguration: ...
    async def update_ai_provider_configuration(
        self, request: AIProviderConfigurationUpdateRequest,
        *, tenant_id: UUID | None, actor_key: str,
    ) -> AIProviderConfiguration: ...
    async def remove_ai_provider_key(
        self, *, tenant_id: UUID | None, actor_key: str,
    ) -> AIProviderConfiguration: ...
    async def test_ai_provider_connection(
        self, *, tenant_id: UUID | None, actor_key: str,
    ) -> AIProviderConnectionTest: ...
    async def get_scan_policy(self, *, tenant_id: UUID | None) -> ScanPolicy: ...
    async def update_scan_policy(
        self, request: ScanPolicyUpdateRequest, *, tenant_id: UUID | None, actor_key: str,
    ) -> ScanPolicy: ...
    async def request_rescan(
        self, request: RescanRequest, *, tenant_id: UUID | None, actor_key: str,
    ) -> tuple[RescanJob, bool]: ...
    async def list_rescan_jobs(
        self, *, tenant_id: UUID | None, cursor: str | None, limit: int,
    ) -> RescanJobList: ...
    async def scan_status(self, *, tenant_id: UUID | None) -> ScanStatus: ...
    async def service_status(self, *, tenant_id: UUID | None) -> ServiceStatusList: ...
    async def update_service_control(
        self, service_key: str, request: ServiceControlRequest,
        *, tenant_id: UUID | None, actor_key: str,
    ) -> ServiceStatus: ...


class AskServiceProtocol(Protocol):
    async def ask(self, request: AskRequest, *, tenant_id: UUID | None) -> AskResponse: ...


router = APIRouter()


async def _principal(request: Request) -> Principal:
    principal = getattr(request.state, "principal", None)
    if principal is None:
        principal = await request.app.state.authenticator.authenticate(
            request.headers.get("Authorization"),
            request.cookies.get("stackgraph_session"),
        )
        request.state.principal = principal
    return principal


def _store(request: Request) -> ReadModelsProtocol:
    return request.app.state.read_models


def _require(principal: Principal, capability: str) -> None:
    """Enforce a capability on the ladder; raise 403 when the principal lacks it."""
    if not principal.has_capability(capability):
        raise APIError(
            403, "FORBIDDEN",
            f"This action requires the '{capability}' capability.",
            {"required_capability": capability},
        )


def _ask_service(request: Request) -> AskServiceProtocol:
    return request.app.state.ask_service


async def _require_phase2_feature(
    request: Request, *, tenant_id: UUID | None, setting: str, flag_key: str, code: str,
) -> None:
    if not getattr(request.app.state.settings, setting, False):
        raise APIError(503, code, "This change capability is disabled by the active feature policy.")
    if not await _store(request).phase2_feature_enabled(flag_key, tenant_id=tenant_id):
        raise APIError(503, code, "This change capability is disabled by the active feature policy.")


@router.get(
    "/action-types", response_model=ActionTypeList,
    response_model_exclude_none=True, operation_id="listActionTypes", tags=["changes"],
)
async def list_action_types(request: Request) -> ActionTypeList:
    principal = await _principal(request)
    await _require_phase2_feature(
        request, tenant_id=principal.tenant_id, setting="change_compiler_enabled",
        flag_key="CHANGE_COMPILER", code="CHANGE_COMPILER_DISABLED",
    )
    return await _store(request).action_types(tenant_id=principal.tenant_id)


@router.get(
    "/action-types/{predicate}/subjects", response_model=ActionSubjectList,
    response_model_exclude_none=True, operation_id="listActionSubjects", tags=["changes"],
)
async def list_action_subjects(
    predicate: Literal["UPGRADE", "REPLACE", "REMOVE", "DEPRECATE", "MIGRATE", "MOVE"],
    request: Request,
    query: str | None = Query(default=None, max_length=255),
    limit: int = Query(default=25, ge=1, le=100),
) -> ActionSubjectList:
    principal = await _principal(request)
    await _require_phase2_feature(
        request, tenant_id=principal.tenant_id, setting="change_compiler_enabled",
        flag_key="CHANGE_COMPILER", code="CHANGE_COMPILER_DISABLED",
    )
    return await _store(request).action_subjects(
        predicate, tenant_id=principal.tenant_id, query=query, limit=limit,
    )


@router.get(
    "/entities/{id}/valid-targets", response_model=ValidTargetList,
    response_model_exclude_none=True, operation_id="listValidTargets", tags=["changes"],
)
async def list_valid_targets(
    id: UUID, request: Request, limit: int = Query(default=50, ge=1, le=200),
) -> ValidTargetList:
    principal = await _principal(request)
    await _require_phase2_feature(
        request, tenant_id=principal.tenant_id, setting="change_compiler_enabled",
        flag_key="CHANGE_COMPILER", code="CHANGE_COMPILER_DISABLED",
    )
    return await _store(request).valid_targets(id, tenant_id=principal.tenant_id, limit=limit)


@router.get(
    "/entities/{id}/scopes", response_model=ChangeScopeList,
    response_model_exclude_none=True, operation_id="listChangeScopes", tags=["changes"],
)
async def list_change_scopes(id: UUID, request: Request) -> ChangeScopeList:
    principal = await _principal(request)
    await _require_phase2_feature(
        request, tenant_id=principal.tenant_id, setting="change_compiler_enabled",
        flag_key="CHANGE_COMPILER", code="CHANGE_COMPILER_DISABLED",
    )
    return await _store(request).scopes(id, tenant_id=principal.tenant_id)


@router.get(
    "/repositories/{id}/fingerprints", response_model=RepositoryFingerprintList,
    response_model_exclude_none=True, operation_id="listRepositoryFingerprints",
    tags=["repositories", "intelligence"],
)
async def list_repository_fingerprints(
    id: UUID, request: Request, limit: int = Query(default=20, ge=1, le=100),
) -> RepositoryFingerprintList:
    principal = await _principal(request)
    return await _store(request).repository_fingerprints(
        id, tenant_id=principal.tenant_id, limit=limit,
    )


@router.post(
    "/observed-mutations", response_model=ObservedMutationModel, status_code=201,
    response_model_exclude_none=True, operation_id="recordObservedMutation", tags=["changes"],
)
async def record_observed_mutation(
    body: ObservedMutationCreateRequest, request: Request,
) -> ObservedMutationModel:
    principal = await _principal(request)
    _require(principal, "review")
    return await _store(request).record_observed_mutation(
        body, tenant_id=principal.tenant_id, actor_key=principal.actor_key,
    )


@router.get(
    "/entities/{id}/change-history", response_model=ObservedMutationList,
    response_model_exclude_none=True, operation_id="listEntityChangeHistory", tags=["changes"],
)
async def list_entity_change_history(
    id: UUID, request: Request, limit: int = Query(default=20, ge=1, le=100),
) -> ObservedMutationList:
    principal = await _principal(request)
    return await _store(request).change_history(id, tenant_id=principal.tenant_id, limit=limit)


@router.post(
    "/mutations/compile", response_model=MutationCompileResult,
    response_model_exclude_none=True, operation_id="compileMutation", tags=["changes"],
)
async def compile_mutation(
    body: MutationCompileRequest, request: Request, response: Response,
) -> MutationCompileResult:
    principal = await _principal(request)
    await _require_phase2_feature(
        request, tenant_id=principal.tenant_id, setting="change_compiler_enabled",
        flag_key="CHANGE_COMPILER", code="CHANGE_COMPILER_DISABLED",
    )
    result = await _store(request).compile_mutation(
        body, tenant_id=principal.tenant_id, actor_key=principal.actor_key,
    )
    response.status_code = 200 if result.replayed or result.gate.state != "CLEAR" else 201
    return result


@router.post(
    "/insights/deterministic/{id}/compile", response_model=MutationCompileResult,
    response_model_exclude_none=True, operation_id="compileDeterministicInsight",
    tags=["changes"],
)
async def compile_deterministic_insight(
    id: UUID, body: RecommendationCompileRequest, request: Request, response: Response,
) -> MutationCompileResult:
    """Turn an estate finding into a simulatable ChangeSet without manual re-entry (R1)."""
    principal = await _principal(request)
    await _require_phase2_feature(
        request, tenant_id=principal.tenant_id, setting="change_compiler_enabled",
        flag_key="CHANGE_COMPILER", code="CHANGE_COMPILER_DISABLED",
    )
    result = await _store(request).compile_deterministic_insight(
        id, body, tenant_id=principal.tenant_id, actor_key=principal.actor_key,
    )
    response.status_code = 200 if result.replayed or result.gate.state != "CLEAR" else 201
    return result


@router.post(
    "/change-sets/compile", response_model=MutationCompileResult,
    response_model_exclude_none=True, operation_id="compileChangeSet", tags=["changes"],
)
async def compile_change_set(
    body: ChangeSetCompileRequest, request: Request, response: Response,
) -> MutationCompileResult:
    """Compile an ordered ChangeSet from a pull request, ticket, architecture change, or agent.

    §7's alternative entry points all reach the deterministic engine through this one contract,
    so no source gets its own compiler and none of them consumes natural language.
    """
    principal = await _principal(request)
    await _require_phase2_feature(
        request, tenant_id=principal.tenant_id, setting="change_compiler_enabled",
        flag_key="CHANGE_COMPILER", code="CHANGE_COMPILER_DISABLED",
    )
    result = await _store(request).compile_change_set(
        body, tenant_id=principal.tenant_id, actor_key=principal.actor_key,
    )
    response.status_code = 200 if result.replayed or result.gate.state != "CLEAR" else 201
    return result


@router.post(
    "/mutations/validate", response_model=MutationCompileResult,
    response_model_exclude_none=True, operation_id="validateMutation", tags=["changes"],
)
async def validate_mutation(body: MutationValidateRequest, request: Request) -> MutationCompileResult:
    principal = await _principal(request)
    await _require_phase2_feature(
        request, tenant_id=principal.tenant_id, setting="change_compiler_enabled",
        flag_key="CHANGE_COMPILER", code="CHANGE_COMPILER_DISABLED",
    )
    return await _store(request).validate_mutation(
        body, tenant_id=principal.tenant_id, actor_key=principal.actor_key,
    )


@router.post(
    "/simulations", response_model=SimulationRunModel, status_code=202,
    response_model_exclude_none=True, operation_id="createSimulation", tags=["changes"],
)
async def create_simulation(
    body: SimulationCreateRequest, request: Request, response: Response,
) -> SimulationRunModel:
    principal = await _principal(request)
    await _require_phase2_feature(
        request, tenant_id=principal.tenant_id, setting="change_simulation_enabled",
        flag_key="CHANGE_SIMULATION", code="CHANGE_SIMULATION_DISABLED",
    )
    result = await _store(request).submit_simulation(
        body, tenant_id=principal.tenant_id, actor_key=principal.actor_key,
    )
    response.status_code = 200 if result.replayed else 202
    return result


@router.get(
    "/simulations/{id}", response_model=SimulationRunModel,
    response_model_exclude_none=True, operation_id="getSimulation", tags=["changes"],
)
async def get_simulation(id: UUID, request: Request) -> SimulationRunModel:
    principal = await _principal(request)
    await _require_phase2_feature(
        request, tenant_id=principal.tenant_id, setting="change_simulation_enabled",
        flag_key="CHANGE_SIMULATION", code="CHANGE_SIMULATION_DISABLED",
    )
    return await _store(request).simulation(id, tenant_id=principal.tenant_id)


@router.delete(
    "/simulations/{id}", response_model=SimulationRunModel,
    response_model_exclude_none=True, operation_id="cancelSimulation", tags=["changes"],
)
async def cancel_simulation(id: UUID, request: Request) -> SimulationRunModel:
    principal = await _principal(request)
    await _require_phase2_feature(
        request, tenant_id=principal.tenant_id, setting="change_simulation_enabled",
        flag_key="CHANGE_SIMULATION", code="CHANGE_SIMULATION_DISABLED",
    )
    _require(principal, "review")
    return await _store(request).cancel_simulation(
        id, tenant_id=principal.tenant_id, actor_key=principal.actor_key,
    )


@router.post(
    "/agent-control/envelopes", response_model=CapabilityEnvelopeModel, status_code=201,
    response_model_exclude_none=True, operation_id="compileCapabilityEnvelope",
    tags=["agent-control"],
)
async def compile_capability_envelope(
    body: CapabilityEnvelopeCompileRequest, request: Request,
) -> CapabilityEnvelopeModel:
    principal = await _principal(request)
    _require(principal, "execute")
    return await _store(request).compile_capability_envelope(
        body, tenant_id=principal.tenant_id, actor_key=principal.actor_key,
    )


@router.get(
    "/agent-control/envelopes/{id}", response_model=CapabilityEnvelopeModel,
    response_model_exclude_none=True, operation_id="getCapabilityEnvelope",
    tags=["agent-control"],
)
async def get_capability_envelope(id: UUID, request: Request) -> CapabilityEnvelopeModel:
    principal = await _principal(request)
    return await _store(request).capability_envelope(id, tenant_id=principal.tenant_id)


@router.post(
    "/agent-control/envelopes/{id}/authorize",
    response_model=AgentAuthorizationDecisionModel,
    response_model_exclude_none=True, operation_id="authorizeAgentOperation",
    tags=["agent-control"],
)
async def authorize_agent_operation(
    id: UUID, body: AgentAuthorizeRequest, request: Request,
) -> AgentAuthorizationDecisionModel:
    principal = await _principal(request)
    _require(principal, "execute")
    return await _store(request).authorize_agent_operation(
        id, body, tenant_id=principal.tenant_id, actor_key=principal.actor_key,
    )


@router.post(
    "/agent-control/approvals/{id}/decision", response_model=AgentApprovalModel,
    response_model_exclude_none=True, operation_id="decideAgentApproval",
    tags=["agent-control"],
)
async def decide_agent_approval(
    id: UUID, body: AgentApprovalDecisionRequest, request: Request,
) -> AgentApprovalModel:
    principal = await _principal(request)
    _require(principal, "review")
    return await _store(request).decide_agent_approval(
        id, body, tenant_id=principal.tenant_id, actor_key=principal.actor_key,
    )


@router.get(
    "/agent-control/kill-switch", response_model=AgentKillSwitchModel,
    response_model_exclude_none=True, operation_id="getAgentKillSwitch",
    tags=["agent-control"],
)
async def get_agent_kill_switch(request: Request) -> AgentKillSwitchModel:
    principal = await _principal(request)
    return await _store(request).agent_kill_switch(tenant_id=principal.tenant_id)


@router.put(
    "/agent-control/kill-switch", response_model=AgentKillSwitchModel,
    response_model_exclude_none=True, operation_id="updateAgentKillSwitch",
    tags=["agent-control"],
)
async def update_agent_kill_switch(
    body: AgentKillSwitchUpdateRequest, request: Request,
) -> AgentKillSwitchModel:
    principal = await _principal(request)
    _require(principal, "admin")
    return await _store(request).update_agent_kill_switch(
        body, tenant_id=principal.tenant_id, actor_key=principal.actor_key,
    )


@router.post(
    "/agent-control/flight-records", response_model=FlightRecordModel, status_code=201,
    response_model_exclude_none=True, operation_id="createFlightRecord",
    tags=["agent-control"],
)
async def create_flight_record(
    body: FlightRecordCreateRequest, request: Request,
) -> FlightRecordModel:
    principal = await _principal(request)
    _require(principal, "execute")
    return await _store(request).create_flight_record(
        body, tenant_id=principal.tenant_id, actor_key=principal.actor_key,
    )


@router.get(
    "/agent-control/flight-records/{id}", response_model=FlightRecordModel,
    response_model_exclude_none=True, operation_id="getFlightRecord",
    tags=["agent-control"],
)
async def get_flight_record(id: UUID, request: Request) -> FlightRecordModel:
    principal = await _principal(request)
    return await _store(request).flight_record(id, tenant_id=principal.tenant_id)


@router.post(
    "/agent-control/flight-records/{id}/events", response_model=FlightRecordModel,
    response_model_exclude_none=True, operation_id="appendFlightEvent",
    tags=["agent-control"],
)
async def append_flight_event(
    id: UUID, body: FlightEventCreateRequest, request: Request,
) -> FlightRecordModel:
    principal = await _principal(request)
    _require(principal, "execute")
    return await _store(request).append_flight_event(id, body, tenant_id=principal.tenant_id)


@router.post(
    "/agent-control/flight-records/{id}/finalize", response_model=FlightRecordModel,
    response_model_exclude_none=True, operation_id="finalizeFlightRecord",
    tags=["agent-control"],
)
async def finalize_flight_record(
    id: UUID, body: FlightRecordFinalizeRequest, request: Request,
) -> FlightRecordModel:
    principal = await _principal(request)
    _require(principal, "execute")
    return await _store(request).finalize_flight_record(id, body, tenant_id=principal.tenant_id)


@router.post(
    "/agent-control/drills", response_model=AgentControlDrillResult,
    response_model_exclude_none=True, operation_id="runAgentControlDrill",
    tags=["agent-control"],
)
async def run_agent_control_drill(
    body: AgentControlDrillRequest, request: Request,
) -> AgentControlDrillResult:
    principal = await _principal(request)
    _require(principal, "admin")
    return await _store(request).run_agent_control_drill(
        body, tenant_id=principal.tenant_id, actor_key=principal.actor_key,
    )


@router.post(
    "/immune-system/scenarios", response_model=AdversarialScenarioList,
    response_model_exclude_none=True, operation_id="generateAdversarialScenarios",
    tags=["immune-system"],
)
async def generate_adversarial_scenarios(
    body: AdversarialScenarioGenerateRequest, request: Request,
) -> AdversarialScenarioList:
    principal = await _principal(request)
    _require(principal, "admin")
    return await _store(request).generate_adversarial_scenarios(
        body, tenant_id=principal.tenant_id, actor_key=principal.actor_key,
    )


@router.get(
    "/immune-system/scenarios", response_model=AdversarialScenarioList,
    response_model_exclude_none=True, operation_id="listAdversarialScenarios",
    tags=["immune-system"],
)
async def list_adversarial_scenarios(
    request: Request,
    scenario_class: AdversarialScenarioClass | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> AdversarialScenarioList:
    principal = await _principal(request)
    return await _store(request).adversarial_scenarios(
        tenant_id=principal.tenant_id, scenario_class=scenario_class, limit=limit,
    )


@router.post(
    "/immune-system/evaluations", response_model=HarnessEvaluationModel, status_code=201,
    response_model_exclude_none=True, operation_id="startHarnessEvaluation",
    tags=["immune-system"],
)
async def start_harness_evaluation(
    body: HarnessEvaluationStartRequest, request: Request,
) -> HarnessEvaluationModel:
    principal = await _principal(request)
    _require(principal, "admin")
    return await _store(request).start_harness_evaluation(
        body, tenant_id=principal.tenant_id, actor_key=principal.actor_key,
    )


@router.get(
    "/immune-system/evaluations/{id}", response_model=HarnessEvaluationModel,
    response_model_exclude_none=True, operation_id="getHarnessEvaluation",
    tags=["immune-system"],
)
async def get_harness_evaluation(id: UUID, request: Request) -> HarnessEvaluationModel:
    principal = await _principal(request)
    return await _store(request).harness_evaluation(id, tenant_id=principal.tenant_id)


@router.post(
    "/immune-system/evaluations/{id}/results", response_model=HarnessEvaluationModel,
    response_model_exclude_none=True, operation_id="recordHarnessEvaluationResult",
    tags=["immune-system"],
)
async def record_harness_evaluation_result(
    id: UUID, body: HarnessEvaluationRecordRequest, request: Request,
) -> HarnessEvaluationModel:
    principal = await _principal(request)
    _require(principal, "admin")
    return await _store(request).record_harness_evaluation_result(
        id, body, tenant_id=principal.tenant_id,
    )


@router.post(
    "/immune-system/evaluations/{id}/finish", response_model=HarnessEvaluationModel,
    response_model_exclude_none=True, operation_id="finishHarnessEvaluation",
    tags=["immune-system"],
)
async def finish_harness_evaluation(
    id: UUID, body: HarnessEvaluationCompleteRequest, request: Request,
) -> HarnessEvaluationModel:
    principal = await _principal(request)
    _require(principal, "admin")
    return await _store(request).complete_harness_evaluation(
        id, body, tenant_id=principal.tenant_id, actor_key=principal.actor_key,
    )


@router.get(
    "/immune-system/champions", response_model=HarnessChampionList,
    response_model_exclude_none=True, operation_id="listHarnessChampions",
    tags=["immune-system"],
)
async def list_harness_champions(request: Request) -> HarnessChampionList:
    principal = await _principal(request)
    return await _store(request).harness_champions(tenant_id=principal.tenant_id)


@router.post(
    "/immune-system/promotions", response_model=HarnessPromotionModel, status_code=201,
    response_model_exclude_none=True, operation_id="proposeHarnessPromotion",
    tags=["immune-system"],
)
async def propose_harness_promotion(
    body: HarnessPromotionProposeRequest, request: Request,
) -> HarnessPromotionModel:
    principal = await _principal(request)
    _require(principal, "admin")
    return await _store(request).propose_harness_promotion(
        body, tenant_id=principal.tenant_id, actor_key=principal.actor_key,
    )


@router.get(
    "/immune-system/promotions/{id}", response_model=HarnessPromotionModel,
    response_model_exclude_none=True, operation_id="getHarnessPromotion",
    tags=["immune-system"],
)
async def get_harness_promotion(id: UUID, request: Request) -> HarnessPromotionModel:
    principal = await _principal(request)
    return await _store(request).harness_promotion(id, tenant_id=principal.tenant_id)


@router.post(
    "/immune-system/promotions/{id}/decision", response_model=HarnessPromotionModel,
    response_model_exclude_none=True, operation_id="decideHarnessPromotion",
    tags=["immune-system"],
)
async def decide_harness_promotion(
    id: UUID, body: HarnessPromotionDecisionRequest, request: Request,
) -> HarnessPromotionModel:
    principal = await _principal(request)
    _require(principal, "admin")
    return await _store(request).decide_harness_promotion(
        id, body, tenant_id=principal.tenant_id, actor_key=principal.actor_key,
    )


@router.post(
    "/immune-system/promotions/{id}/rollback", response_model=HarnessPromotionModel,
    response_model_exclude_none=True, operation_id="rollBackHarnessPromotion",
    tags=["immune-system"],
)
async def roll_back_harness_promotion(
    id: UUID, body: HarnessPromotionRollbackRequest, request: Request,
) -> HarnessPromotionModel:
    principal = await _principal(request)
    _require(principal, "admin")
    return await _store(request).roll_back_harness_promotion(
        id, body, tenant_id=principal.tenant_id, actor_key=principal.actor_key,
    )


@router.get(
    "/estate/summary", response_model=EstateSummary,
    response_model_exclude_none=True, operation_id="getEstateSummary", tags=["estate"],
)
async def get_estate_summary(
    request: Request,
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    domain: list[Namespace] | None = Query(default=None),
    sort: Literal["priority", "systemic_risk", "upstream_impact", "dependency_depth"] = "priority",
) -> EstateSummary:
    principal = await _principal(request)
    return await _store(request).estate_summary(
        tenant_id=principal.tenant_id, cursor=cursor, limit=limit,
        namespaces=domain,
        sort=sort,
    )


@router.get(
    "/estate/strata", response_model=EstateStrata,
    response_model_exclude_none=True, operation_id="getEstateStrata", tags=["estate"],
)
async def get_estate_strata(request: Request) -> EstateStrata:
    principal = await _principal(request)
    return await _store(request).estate_strata(tenant_id=principal.tenant_id)


@router.get(
    "/contradictions", response_model=ContradictionLedger,
    response_model_exclude_none=True, operation_id="listContradictions",
    tags=["intelligence", "changes"],
)
async def list_contradictions(
    request: Request,
    subject_id: UUID | None = None,
    limit: int = Query(default=50, ge=1, le=100),
) -> ContradictionLedger:
    principal = await _principal(request)
    return await _store(request).contradiction_ledger(
        tenant_id=principal.tenant_id, subject_id=subject_id, limit=limit,
    )


@router.post(
    "/assumptions", response_model=AssumptionModel, status_code=201,
    response_model_exclude_none=True, operation_id="createAssumption",
    tags=["intelligence", "changes"],
)
async def create_assumption(body: AssumptionCreateRequest, request: Request) -> AssumptionModel:
    principal = await _principal(request)
    _require(principal, "review")
    return await _store(request).create_assumption(
        body, tenant_id=principal.tenant_id, actor_key=principal.actor_key,
    )


@router.get(
    "/assumptions", response_model=AssumptionList,
    response_model_exclude_none=True, operation_id="listAssumptions",
    tags=["intelligence", "changes"],
)
async def list_assumptions(
    request: Request,
    subject_id: UUID | None = None,
    status: Literal["OPEN", "ACCEPTED", "REJECTED", "SUPERSEDED"] | None = None,
    limit: int = Query(default=50, ge=1, le=100),
) -> AssumptionList:
    principal = await _principal(request)
    return await _store(request).assumptions(
        tenant_id=principal.tenant_id, subject_id=subject_id, status=status, limit=limit,
    )


@router.get(
    "/assumptions/{id}", response_model=AssumptionModel,
    response_model_exclude_none=True, operation_id="getAssumption",
    tags=["intelligence", "changes"],
)
async def get_assumption(id: UUID, request: Request) -> AssumptionModel:
    principal = await _principal(request)
    return await _store(request).assumption(id, tenant_id=principal.tenant_id)


@router.post(
    "/contradictions/{id}/resolve", status_code=204,
    operation_id="resolveContradiction", tags=["intelligence", "changes"],
)
async def resolve_contradiction(
    id: UUID, body: ContradictionResolveRequest, request: Request,
) -> Response:
    principal = await _principal(request)
    _require(principal, "review")
    await _store(request).resolve_contradiction(
        id, body, tenant_id=principal.tenant_id, actor_key=principal.actor_key,
    )
    return Response(status_code=204)


@router.get(
    "/estate/lineage", response_model=EstateLineageList,
    response_model_exclude_none=True, operation_id="listEstateLineage", tags=["estate"],
)
async def list_estate_lineage(
    request: Request, entity_id: UUID | None = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> EstateLineageList:
    principal = await _principal(request)
    return await _store(request).estate_lineage(
        tenant_id=principal.tenant_id, entity_id=entity_id, limit=limit,
    )


@router.get(
    "/estate/ai-supply-chain", response_model=AISupplyChain,
    response_model_exclude_none=True, operation_id="getAISupplyChain", tags=["estate"],
)
async def get_ai_supply_chain(request: Request) -> AISupplyChain:
    principal = await _principal(request)
    return await _store(request).ai_supply_chain(tenant_id=principal.tenant_id)


@router.get(
    "/components", response_model=EstateComponentList,
    response_model_exclude_none=True, operation_id="listComponents", tags=["components"],
)
async def list_components(
    request: Request,
    cursor: UUID | None = None,
    limit: int = Query(default=50, ge=1, le=100),
) -> EstateComponentList:
    principal = await _principal(request)
    return await _store(request).estate_components(
        tenant_id=principal.tenant_id, cursor=cursor, limit=limit,
    )


@router.get(
    "/components/{id}", response_model=EstateComponentDetail,
    response_model_exclude_none=True, operation_id="getComponent", tags=["components"],
)
async def get_component(id: UUID, request: Request) -> EstateComponentDetail:
    principal = await _principal(request)
    return await _store(request).component_detail(id, tenant_id=principal.tenant_id)


@router.get(
    "/applications/{id}", response_model=ApplicationDetail,
    response_model_exclude_none=True, operation_id="getApplication", tags=["applications"],
)
async def get_application(id: UUID, request: Request) -> ApplicationDetail:
    principal = await _principal(request)
    return await _store(request).application_detail(id, tenant_id=principal.tenant_id)


@router.put(
    "/applications/{id}", response_model=EntitySummary,
    response_model_exclude_none=True, operation_id="updateApplication", tags=["applications"],
)
async def update_application(id: UUID, body: EntityDescriptionUpdateRequest, request: Request) -> EntitySummary:
    principal = await _principal(request)
    _require(principal, "execute")
    return await _store(request).update_application(id, body, tenant_id=principal.tenant_id)


@router.get(
    "/technologies/hierarchy", response_model=TechnologyEstateHierarchy,
    response_model_exclude_none=True, operation_id="getTechnologyEstateHierarchy", tags=["technologies"],
)
async def get_technology_estate_hierarchy(request: Request) -> TechnologyEstateHierarchy:
    principal = await _principal(request)
    return await _store(request).technology_estate_hierarchy(tenant_id=principal.tenant_id)


@router.get(
    "/repositories/{id}", response_model=RepositoryDetail,
    response_model_exclude_none=True, operation_id="getRepository", tags=["repositories"],
)
async def get_repository(id: UUID, request: Request) -> RepositoryDetail:
    principal = await _principal(request)
    return await _store(request).repository_detail(id, tenant_id=principal.tenant_id)


@router.get(
    "/repositories/{id}/container-compositions", response_model=ContainerCompositionList,
    response_model_exclude_none=True, operation_id="listRepositoryContainerCompositions",
    tags=["repositories", "components"],
)
async def list_repository_container_compositions(
    id: UUID, request: Request,
) -> ContainerCompositionList:
    principal = await _principal(request)
    return await _store(request).repository_container_compositions(
        id, tenant_id=principal.tenant_id,
    )


@router.get(
    "/repositories/{id}/deployment-profiles", response_model=DeploymentProfileList,
    response_model_exclude_none=True, operation_id="listRepositoryDeploymentProfiles",
    tags=["repositories", "components"],
)
async def list_repository_deployment_profiles(
    id: UUID, request: Request,
) -> DeploymentProfileList:
    principal = await _principal(request)
    return await _store(request).repository_deployment_profiles(
        id, tenant_id=principal.tenant_id,
    )


@router.put(
    "/repositories/{id}", response_model=EntitySummary,
    response_model_exclude_none=True, operation_id="updateRepository", tags=["repositories"],
)
async def update_repository(id: UUID, body: EntityDescriptionUpdateRequest, request: Request) -> EntitySummary:
    principal = await _principal(request)
    _require(principal, "execute")
    return await _store(request).update_repository(id, body, tenant_id=principal.tenant_id)


@router.get(
    "/repositories/{id}/activity", response_model=RepositoryActivity,
    response_model_exclude_none=True, operation_id="getRepositoryActivity",
    tags=["repositories"],
)
async def get_repository_activity(
    id: UUID,
    request: Request,
    window: Literal["7d", "30d", "90d"] = "30d",
    cursor: str | None = None,
    limit: int = Query(default=10, ge=1, le=100),
) -> RepositoryActivity:
    principal = await _principal(request)
    return await _store(request).repository_activity(
        id, tenant_id=principal.tenant_id, window=window, cursor=cursor, limit=limit,
    )


@router.get(
    "/technologies/{id}", response_model=TechnologyDetail,
    response_model_exclude_none=True, operation_id="getTechnology", tags=["technologies"],
)
async def get_technology(id: UUID, request: Request) -> TechnologyDetail:
    principal = await _principal(request)
    return await _store(request).technology_detail(id, tenant_id=principal.tenant_id)


@router.get(
    "/modernization", response_model=ModernizationList,
    response_model_exclude_none=True, operation_id="listModernizationOpportunities", tags=["intelligence"],
)
async def list_modernization(
    request: Request,
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
) -> ModernizationList:
    principal = await _principal(request)
    return await _store(request).modernization(
        tenant_id=principal.tenant_id, cursor=cursor, limit=limit,
    )


@router.get(
    "/insights/deterministic", response_model=DeterministicInsightList,
    response_model_exclude_none=True, operation_id="listDeterministicInsights",
    tags=["intelligence"],
)
async def list_deterministic_insights(
    request: Request,
    scope_entity_id: UUID | None = Query(default=None),
    rule_key: str | None = Query(default=None, min_length=3, max_length=128),
    limit: int = Query(default=100, ge=1, le=500),
) -> DeterministicInsightList:
    principal = await _principal(request)
    return await _store(request).deterministic_insights(
        tenant_id=principal.tenant_id,
        scope_entity_id=scope_entity_id,
        rule_key=rule_key,
        limit=limit,
    )


@router.get(
    "/capabilities/footprints", response_model=CapabilityFootprintList,
    response_model_exclude_none=True, operation_id="listCapabilityFootprints",
    tags=["intelligence"],
)
async def list_capability_footprints(request: Request) -> CapabilityFootprintList:
    principal = await _principal(request)
    return await _store(request).capability_footprints(tenant_id=principal.tenant_id)


@router.post(
    "/modernization/scenarios", response_model=ModernizationScenarioResult,
    response_model_exclude_none=True, operation_id="optimizeModernizationScenario",
    tags=["intelligence"],
)
async def optimize_modernization_scenario(
    body: ModernizationScenarioRequest, request: Request,
) -> ModernizationScenarioResult:
    principal = await _principal(request)
    return await _store(request).modernization_scenario(body, tenant_id=principal.tenant_id)


@router.post(
    "/ask", response_model=AskResponse,
    response_model_exclude_none=True, operation_id="askEstate", tags=["intelligence"],
)
async def ask_estate(body: AskRequest, request: Request) -> AskResponse:
    principal = await _principal(request)
    return await _ask_service(request).ask(body, tenant_id=principal.tenant_id)


@router.get(
    "/insights/reports", response_model=EnterpriseInsightReportList,
    response_model_exclude_none=True, operation_id="listEnterpriseInsightReports",
    tags=["intelligence"],
)
async def list_enterprise_insight_reports(request: Request) -> EnterpriseInsightReportList:
    principal = await _principal(request)
    return await _store(request).enterprise_insight_reports(tenant_id=principal.tenant_id)


@router.get(
    "/graph/neighborhood", response_model=GraphNeighborhood,
    response_model_exclude_none=True, operation_id="getGraphNeighborhood", tags=["graph"],
)
async def get_graph_neighborhood(
    request: Request,
    center_id: UUID,
    depth: int = Query(default=1, ge=1, le=2),
    real_node_limit: int = Query(default=50, ge=1, le=50),
    predicate: list[str] | None = Query(default=None, min_length=1),
    namespace: list[Namespace] | None = Query(default=None),
    min_confidence: float = Query(default=0, ge=0, le=1),
    highlight_to: UUID | None = None,
) -> GraphNeighborhood:
    principal = await _principal(request)
    return await _store(request).graph_neighborhood(
        center_id,
        tenant_id=principal.tenant_id,
        depth=depth,
        real_node_limit=real_node_limit,
        predicates=predicate,
        namespaces=namespace,
        min_confidence=min_confidence,
        highlight_to=highlight_to,
    )


@router.get(
    "/graph-intelligence/status", response_model=GraphIntelligenceStatus,
    response_model_exclude_none=True, operation_id="getGraphIntelligenceStatus",
    tags=["graph-intelligence"],
)
async def get_graph_intelligence_status(request: Request) -> GraphIntelligenceStatus:
    principal = await _principal(request)
    return await _store(request).graph_intelligence_status(tenant_id=principal.tenant_id)


@router.post(
    "/graph-intelligence/analysis-requests",response_model=GraphAnalysisRequestResult,
    response_model_exclude_none=True,operation_id="requestGraphAnalysis",
    tags=["graph-intelligence"],
)
async def request_graph_analysis(
    body: GraphAnalysisRequestCreate,request: Request,response: Response,
) -> GraphAnalysisRequestResult:
    principal = await _principal(request)
    _require(principal,"admin")
    result,created = await _store(request).request_graph_analysis(
        body,tenant_id=principal.tenant_id,actor_key=principal.actor_key,
    )
    response.status_code=201 if created else 200
    return result


@router.get(
    "/entities/{id}/graph-metrics", response_model=EntityGraphIntelligence,
    response_model_exclude_none=True, operation_id="getEntityGraphMetrics",
    tags=["graph-intelligence"],
)
async def get_entity_graph_metrics(id: UUID, request: Request) -> EntityGraphIntelligence:
    principal = await _principal(request)
    return await _store(request).entity_graph_metrics(id,tenant_id=principal.tenant_id)


@router.get(
    "/entities/{id}/blast-radius", response_model=GraphBlastRadius,
    response_model_exclude_none=True, operation_id="getEntityBlastRadius",
    tags=["graph-intelligence"],
)
async def get_entity_blast_radius(id: UUID, request: Request) -> GraphBlastRadius:
    principal = await _principal(request)
    return await _store(request).graph_blast_radius(id,tenant_id=principal.tenant_id)


@router.get(
    "/graph-intelligence/risks", response_model=GraphRiskList,
    response_model_exclude_none=True, operation_id="listGraphIntelligenceRisks",
    tags=["graph-intelligence"],
)
async def list_graph_intelligence_risks(
    request: Request,
    entity_type: str | None = Query(default=None,min_length=1,max_length=100),
    namespace: Namespace | None = None,
    community_key: str | None = Query(default=None,min_length=1,max_length=200),
    min_score: float = Query(default=0,ge=0,le=1),
    cursor: str | None = None,
    limit: int = Query(default=20,ge=1,le=100),
) -> GraphRiskList:
    principal = await _principal(request)
    return await _store(request).graph_risks(
        tenant_id=principal.tenant_id,entity_type=entity_type,namespace=namespace,
        community_key=community_key,min_score=min_score,cursor=cursor,limit=limit,
    )


@router.get(
    "/graph-intelligence/anomalies", response_model=GraphAnomalyList,
    response_model_exclude_none=True, operation_id="listGraphIntelligenceAnomalies",
    tags=["graph-intelligence"],
)
async def list_graph_intelligence_anomalies(
    request: Request, cohort_key: str | None = None,
    limit: int = Query(default=50,ge=1,le=100),
) -> GraphAnomalyList:
    principal = await _principal(request)
    return await _store(request).graph_anomalies(
        tenant_id=principal.tenant_id,cohort_key=cohort_key,limit=limit,
    )


@router.get(
    "/graph-intelligence/motifs", response_model=GraphMotifList,
    response_model_exclude_none=True, operation_id="listGraphIntelligenceMotifs",
    tags=["graph-intelligence"],
)
async def list_graph_intelligence_motifs(
    request: Request, motif_key: str | None = None,
    limit: int = Query(default=50,ge=1,le=100),
) -> GraphMotifList:
    principal = await _principal(request)
    return await _store(request).graph_motifs(
        tenant_id=principal.tenant_id,motif_key=motif_key,limit=limit,
    )


@router.get(
    "/entities/{id}/critical-edges", response_model=CriticalGraphEdgeList,
    response_model_exclude_none=True, operation_id="listEntityCriticalEdges",
    tags=["graph-intelligence"],
)
async def list_entity_critical_edges(id: UUID, request: Request) -> CriticalGraphEdgeList:
    principal = await _principal(request)
    return await _store(request).critical_edges(id,tenant_id=principal.tenant_id)


@router.get(
    "/graph-intelligence/communities", response_model=GraphCommunityList,
    response_model_exclude_none=True, operation_id="listGraphIntelligenceCommunities",
    tags=["graph-intelligence"],
)
async def list_graph_intelligence_communities(
    request: Request,
    policy_key: str = Query(default="runtime-dependency",pattern=r"^[a-z][a-z0-9-]{2,63}$"),
    limit: int = Query(default=50,ge=1,le=100),
) -> GraphCommunityList:
    principal = await _principal(request)
    return await _store(request).graph_communities(
        tenant_id=principal.tenant_id,policy_key=policy_key,limit=limit,
    )


@router.post(
    "/search/semantic",response_model=SemanticSearchResponse,
    response_model_exclude_none=True,operation_id="semanticSearch",tags=["embeddings"],
)
async def semantic_search(body: SemanticSearchRequest,request: Request) -> SemanticSearchResponse:
    principal = await _principal(request)
    return await _store(request).semantic_search(body,tenant_id=principal.tenant_id)


@router.get(
    "/embeddings/status",response_model=EmbeddingStatus,
    response_model_exclude_none=True,operation_id="getEmbeddingStatus",tags=["embeddings"],
)
async def get_embedding_status(request: Request) -> EmbeddingStatus:
    principal = await _principal(request)
    return await _store(request).embedding_status(tenant_id=principal.tenant_id)


@router.post(
    "/embeddings/backfill",response_model=EmbeddingBackfillResult,
    response_model_exclude_none=True,operation_id="requestEmbeddingBackfill",tags=["embeddings"],
)
async def request_embedding_backfill(
    body: EmbeddingBackfillRequest,request: Request,
) -> EmbeddingBackfillResult:
    principal = await _principal(request)
    _require(principal,"admin")
    return await _store(request).request_embedding_backfill(
        body,tenant_id=principal.tenant_id,actor_key=principal.actor_key,
    )


@router.post(
    "/embedding-spaces/{id}/promotion",response_model=EmbeddingSpacePromotionResult,
    response_model_exclude_none=True,operation_id="promoteEmbeddingSpace",tags=["embeddings"],
)
async def promote_embedding_space(
    id: UUID,body: EmbeddingSpacePromotionRequest,request: Request,
) -> EmbeddingSpacePromotionResult:
    principal = await _principal(request)
    _require(principal,"admin")
    return await _store(request).promote_embedding_space(
        id,body,tenant_id=principal.tenant_id,actor_key=principal.actor_key,
    )


@router.get(
    "/entities/{id}/similar",response_model=ApplicationSimilarityList,
    response_model_exclude_none=True,operation_id="listSimilarApplications",tags=["embeddings"],
)
async def list_similar_applications(
    id: UUID,request: Request,
    review_state: Literal[
        "UNREVIEWED","CONFIRMED_SIMILAR","CONFIRMED_DISTINCT",
        "CONSOLIDATION_CANDIDATE","DISMISSED",
    ] | None = None,
    cursor: str | None = None,
    limit: int=Query(default=10,ge=1,le=50),
) -> ApplicationSimilarityList:
    principal = await _principal(request)
    return await _store(request).similar_applications(
        id,tenant_id=principal.tenant_id,review_state=review_state,cursor=cursor,limit=limit,
    )


@router.post(
    "/similarity-candidates/{id}/review",response_model=ApplicationSimilarityReviewResult,
    response_model_exclude_none=True,operation_id="reviewApplicationSimilarity",tags=["embeddings"],
)
async def review_application_similarity(
    id: UUID,body: ApplicationSimilarityReviewRequest,request: Request,
) -> ApplicationSimilarityReviewResult:
    principal = await _principal(request)
    _require(principal,"review")
    return await _store(request).review_application_similarity(
        id,body,tenant_id=principal.tenant_id,actor_key=principal.actor_key,
    )


@router.get(
    "/facts/{id}/evidence", response_model=EvidenceDetail,
    response_model_exclude_none=True, operation_id="getFactEvidence", tags=["evidence"],
)
async def get_fact_evidence(id: UUID, request: Request) -> EvidenceDetail:
    principal = await _principal(request)
    return await _store(request).evidence_detail(id, tenant_id=principal.tenant_id)


@router.post(
    "/identity-assertions/{id}/review", response_model=IdentityReviewResult,
    response_model_exclude_none=True, operation_id="reviewIdentityAssertion", tags=["identity"],
)
async def review_identity_assertion(
    id: UUID,
    body: IdentityReviewRequest,
    request: Request,
) -> IdentityReviewResult:
    principal = await _principal(request)
    _require(principal, "review")
    return await _store(request).review_identity_assertion(
        id, body, tenant_id=principal.tenant_id, actor_key=principal.actor_key,
    )


@router.get(
    "/capabilities/taxonomy", response_model=CapabilityTaxonomyResponse,
    response_model_exclude_none=True, operation_id="getCapabilityTaxonomy",
    tags=["intelligence"],
)
async def get_capability_taxonomy(
    request: Request,
    version: str | None = None,
) -> CapabilityTaxonomyResponse:
    principal = await _principal(request)
    return await _store(request).capability_taxonomy(
        tenant_id=principal.tenant_id, version=version,
    )


@router.get(
    "/repositories/{id}/capabilities", response_model=RepositoryCapabilityIntelligence,
    response_model_exclude_none=True, operation_id="getRepositoryCapabilities",
    tags=["intelligence"],
)
async def get_repository_capabilities(
    id: UUID,
    request: Request,
) -> RepositoryCapabilityIntelligence:
    principal = await _principal(request)
    return await _store(request).repository_capabilities(
        id, tenant_id=principal.tenant_id,
    )


@router.post(
    "/capability-inferences/{id}/review", response_model=CapabilityInferenceReviewResult,
    response_model_exclude_none=True, operation_id="reviewCapabilityInference",
    tags=["intelligence"],
)
async def review_capability_inference(
    id: UUID,
    body: CapabilityInferenceReviewRequest,
    request: Request,
) -> CapabilityInferenceReviewResult:
    principal = await _principal(request)
    _require(principal, "review")
    return await _store(request).review_capability_inference(
        id, body, tenant_id=principal.tenant_id, actor_key=principal.actor_key,
    )


@router.post(
    "/duplicate-capability-candidates/{id}/review", response_model=DuplicateCapabilityReviewResult,
    response_model_exclude_none=True, operation_id="reviewDuplicateCapabilityCandidate",
    tags=["intelligence"],
)
async def review_duplicate_capability_candidate(
    id: UUID,
    body: DuplicateCapabilityReviewRequest,
    request: Request,
) -> DuplicateCapabilityReviewResult:
    principal = await _principal(request)
    _require(principal, "review")
    return await _store(request).review_duplicate_capability_candidate(
        id, body, tenant_id=principal.tenant_id, actor_key=principal.actor_key,
    )


@router.get(
    "/repositories/{id}/modernization-intelligence",
    response_model=RepositoryModernizationIntelligence,
    response_model_exclude_none=True, operation_id="getRepositoryModernizationIntelligence",
    tags=["intelligence"],
)
async def get_repository_modernization_intelligence(
    id: UUID,
    request: Request,
    limit: int = Query(default=50, ge=1, le=100),
) -> RepositoryModernizationIntelligence:
    principal = await _principal(request)
    return await _store(request).repository_modernization_intelligence(
        id, tenant_id=principal.tenant_id, limit=limit,
    )


@router.post(
    "/modernization-candidates/{id}/review",
    response_model=ModernizationCandidateReviewResult,
    response_model_exclude_none=True, operation_id="reviewModernizationCandidate",
    tags=["intelligence"],
)
async def review_modernization_candidate(
    id: UUID,
    body: ModernizationCandidateReviewRequest,
    request: Request,
) -> ModernizationCandidateReviewResult:
    principal = await _principal(request)
    _require(principal, "review")
    return await _store(request).review_modernization_candidate(
        id, body, tenant_id=principal.tenant_id, actor_key=principal.actor_key,
    )


@router.post(
    "/modernization-recommendations/{id}/compile", response_model=MutationCompileResult,
    response_model_exclude_none=True, operation_id="compileModernizationRecommendation",
    tags=["changes", "intelligence"],
)
async def compile_modernization_recommendation(
    id: UUID, body: RecommendationCompileRequest, request: Request, response: Response,
) -> MutationCompileResult:
    principal = await _principal(request)
    await _require_phase2_feature(
        request, tenant_id=principal.tenant_id, setting="change_compiler_enabled",
        flag_key="CHANGE_COMPILER", code="CHANGE_COMPILER_DISABLED",
    )
    result = await _store(request).compile_modernization_recommendation(
        id, body, tenant_id=principal.tenant_id, actor_key=principal.actor_key,
    )
    response.status_code = 200 if result.replayed or result.gate.state != "CLEAR" else 201
    return result


@router.post(
    "/modernization-recommendations/{id}/review",
    response_model=ModernizationRecommendationReviewResult,
    response_model_exclude_none=True, operation_id="reviewModernizationRecommendation",
    tags=["intelligence"],
)
async def review_modernization_recommendation(
    id: UUID,
    body: ModernizationRecommendationReviewRequest,
    request: Request,
) -> ModernizationRecommendationReviewResult:
    principal = await _principal(request)
    _require(principal, "review")
    return await _store(request).review_modernization_recommendation(
        id, body, tenant_id=principal.tenant_id, actor_key=principal.actor_key,
    )


@router.post(
    "/modernization-recommendations/{id}/validation-outcomes",
    response_model=ModernizationValidationOutcomeResult,
    response_model_exclude_none=True, operation_id="recordModernizationValidationOutcome",
    tags=["intelligence"],
)
async def record_modernization_validation_outcome(
    id: UUID,
    body: ModernizationValidationOutcomeRequest,
    request: Request,
) -> ModernizationValidationOutcomeResult:
    principal = await _principal(request)
    _require(principal, "review")
    return await _store(request).record_modernization_validation_outcome(
        id, body, tenant_id=principal.tenant_id, actor_key=principal.actor_key,
    )


@router.get(
    "/intelligence/phase-3/metrics",
    response_model=Phase3IntelligenceMetrics,
    response_model_exclude_none=True, operation_id="getPhase3IntelligenceMetrics",
    tags=["intelligence"],
)
async def get_phase3_intelligence_metrics(request: Request) -> Phase3IntelligenceMetrics:
    principal = await _principal(request)
    return await _store(request).phase3_intelligence_metrics(tenant_id=principal.tenant_id)


@router.get(
    "/session", response_model=SessionInfo,
    response_model_exclude_none=True, operation_id="getSession", tags=["session"],
)
async def get_session(request: Request) -> SessionInfo:
    principal = await _principal(request)
    return SessionInfo(
        actor_key=principal.actor_key,
        tenant_id=principal.tenant_id,
        capabilities=sorted(principal.capabilities),
    )


@router.get(
    "/canvas/taxonomy", response_model=ArchitectureTaxonomyResponse,
    response_model_exclude_none=True, operation_id="getArchitectureTaxonomy",
    tags=["architecture-canvas"],
)
async def get_architecture_taxonomy(request: Request) -> ArchitectureTaxonomyResponse:
    principal = await _principal(request)
    _require(principal, "view")
    return await _store(request).architecture_taxonomy()


@router.get(
    "/canvas/reference-models", response_model=ArchitectureReferenceModelList,
    response_model_exclude_none=True, operation_id="listArchitectureReferenceModels",
    tags=["architecture-canvas"],
)
async def list_architecture_reference_models(request: Request) -> ArchitectureReferenceModelList:
    principal = await _principal(request)
    _require(principal, "view")
    return await _store(request).architecture_reference_models()


@router.get(
    "/canvas/reference-models/{key}", response_model=ArchitectureReferenceModel,
    response_model_exclude_none=True, operation_id="getArchitectureReferenceModel",
    tags=["architecture-canvas"],
)
async def get_architecture_reference_model(
    key: str, request: Request, version: str | None = None,
) -> ArchitectureReferenceModel:
    principal = await _principal(request)
    _require(principal, "view")
    return await _store(request).architecture_reference_model(key, version=version)


@router.get(
    "/canvas/templates", response_model=CanvasTemplateList,
    response_model_exclude_none=True, operation_id="listCanvasTemplates",
    tags=["architecture-canvas"],
)
async def list_canvas_templates(request: Request) -> CanvasTemplateList:
    principal = await _principal(request)
    _require(principal, "view")
    return await _store(request).canvas_templates()


@router.get(
    "/canvas/templates/{key}", response_model=CanvasTemplateModel,
    response_model_exclude_none=True, operation_id="getCanvasTemplate",
    tags=["architecture-canvas"],
)
async def get_canvas_template(
    key: str, request: Request, version: str | None = None,
) -> CanvasTemplateModel:
    principal = await _principal(request)
    _require(principal, "view")
    templates = await _store(request).canvas_templates()
    template = next(
        (
            item for item in templates.templates
            if item.key == key and (version is None or item.version == version)
        ),
        None,
    )
    if template is None:
        raise APIError(404, "CANVAS_TEMPLATE_NOT_FOUND", "The canvas template was not found.")
    return template


@router.get(
    "/canvas/projection", response_model=CanvasProjection,
    response_model_exclude_none=True, operation_id="getCanvasProjection",
    tags=["architecture-canvas"],
)
async def get_canvas_projection(
    request: Request,
    scope: CanvasProjectionScope = Query(default="ESTATE"),
    subject_id: UUID | None = None,
    reference_model_key: str = "architecture.stackgraph.reference",
    template_key: str = "canvas.stackgraph.reference",
) -> CanvasProjection:
    principal = await _principal(request)
    _require(principal, "view")
    if scope == "TARGET":
        raise APIError(
            400, "TARGET_PROJECTION_REQUIRES_REVIEW",
            "Use the target-projection endpoint for governed target state.",
        )
    if scope in {"APPLICATION", "REPOSITORY"} and subject_id is None:
        raise APIError(
            422, "CANVAS_SUBJECT_REQUIRED",
            "Application and repository canvas projections require subject_id.",
        )
    if scope == "ESTATE" and subject_id is not None:
        raise APIError(
            422, "CANVAS_SUBJECT_NOT_ALLOWED",
            "Estate canvas projections do not accept subject_id.",
        )
    selector = CanvasProjectionSelectorModel(scope=scope, subject_id=subject_id)
    return await _store(request).canvas_projection(
        selector, tenant_id=principal.tenant_id,
        reference_model_key=reference_model_key, template_key=template_key,
    )


@router.get(
    "/canvas/target-projection", response_model=CanvasProjection,
    response_model_exclude_none=True, operation_id="getTargetCanvasProjection",
    tags=["architecture-canvas"],
)
async def get_target_canvas_projection(
    request: Request,
    reference_model_key: str = "architecture.stackgraph.reference",
    template_key: str = "canvas.stackgraph.reference",
) -> CanvasProjection:
    principal = await _principal(request)
    _require(principal, "review")
    return await _store(request).canvas_projection(
        CanvasProjectionSelectorModel(scope="TARGET"), tenant_id=principal.tenant_id,
        reference_model_key=reference_model_key, template_key=template_key,
    )


@router.post(
    "/canvas/comparisons", response_model=CanvasComparison,
    response_model_exclude_none=True, operation_id="compareCanvasProjections",
    tags=["architecture-canvas"],
)
async def compare_canvas_projections(
    body: CanvasComparisonRequest, request: Request,
) -> CanvasComparison:
    principal = await _principal(request)
    _require(principal, "review")
    return await _store(request).canvas_comparison(body, tenant_id=principal.tenant_id)


@router.get(
    "/business-maps", response_model=BusinessMapList,
    response_model_exclude_none=True, operation_id="listBusinessMaps", tags=["business-map"],
)
async def list_business_maps(
    request: Request,
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
) -> BusinessMapList:
    principal = await _principal(request)
    _require(principal, "view")
    return await _store(request).list_business_maps(
        tenant_id=principal.tenant_id, cursor=cursor, limit=limit,
    )


@router.post(
    "/business-maps", response_model=BusinessMapDetail, status_code=201,
    response_model_exclude_none=True, operation_id="createBusinessMap", tags=["business-map"],
)
async def create_business_map(body: BusinessMapCreateRequest, request: Request) -> BusinessMapDetail:
    principal = await _principal(request)
    _require(principal, "execute")
    return await _store(request).create_business_map(
        body, tenant_id=principal.tenant_id, actor_key=principal.actor_key,
    )


@router.get(
    "/business-maps/{id}", response_model=BusinessMapDetail,
    response_model_exclude_none=True, operation_id="getBusinessMap", tags=["business-map"],
)
async def get_business_map(id: UUID, request: Request) -> BusinessMapDetail:
    principal = await _principal(request)
    _require(principal, "view")
    return await _store(request).business_map_detail(id, tenant_id=principal.tenant_id)


@router.put(
    "/business-maps/{id}", response_model=BusinessMapDetail,
    response_model_exclude_none=True, operation_id="saveBusinessMap", tags=["business-map"],
)
async def save_business_map(id: UUID, body: BusinessMapSaveRequest, request: Request) -> BusinessMapDetail:
    principal = await _principal(request)
    _require(principal, "execute")
    return await _store(request).save_business_map(
        id, body, tenant_id=principal.tenant_id, actor_key=principal.actor_key,
    )


@router.delete(
    "/business-maps/{id}", response_model=BusinessMapSummary,
    response_model_exclude_none=True, operation_id="archiveBusinessMap", tags=["business-map"],
)
async def archive_business_map(id: UUID, request: Request) -> BusinessMapSummary:
    principal = await _principal(request)
    _require(principal, "execute")
    return await _store(request).archive_business_map(
        id, tenant_id=principal.tenant_id, actor_key=principal.actor_key,
    )


@router.get(
    "/business-maps/{id}/revisions", response_model=BusinessMapRevisionList,
    response_model_exclude_none=True, operation_id="listBusinessMapRevisions", tags=["business-map"],
)
async def list_business_map_revisions(id: UUID, request: Request) -> BusinessMapRevisionList:
    principal = await _principal(request)
    _require(principal, "view")
    return await _store(request).business_map_revisions(id, tenant_id=principal.tenant_id)


@router.get(
    "/admin/architecture-profiles", response_model=ArchitectureProfileList,
    response_model_exclude_none=True, operation_id="listArchitectureProfiles", tags=["admin"],
)
async def list_architecture_profiles(request: Request) -> ArchitectureProfileList:
    principal = await _principal(request)
    _require(principal, "admin")
    return await _store(request).list_architecture_profiles(tenant_id=principal.tenant_id)


@router.post(
    "/admin/architecture-profiles", response_model=ArchitectureProfileDetail, status_code=201,
    response_model_exclude_none=True, operation_id="createArchitectureProfile", tags=["admin"],
)
async def create_architecture_profile(
    body: ArchitectureProfileCreateRequest, request: Request,
) -> ArchitectureProfileDetail:
    principal = await _principal(request)
    _require(principal, "admin")
    return await _store(request).create_architecture_profile(
        body, tenant_id=principal.tenant_id, actor_key=principal.actor_key,
    )


@router.put(
    "/admin/architecture-profiles/{id}", response_model=ArchitectureProfileDetail,
    response_model_exclude_none=True, operation_id="updateArchitectureProfile", tags=["admin"],
)
async def update_architecture_profile(
    id: UUID, body: ArchitectureProfileUpdateRequest, request: Request,
) -> ArchitectureProfileDetail:
    principal = await _principal(request)
    _require(principal, "admin")
    return await _store(request).update_architecture_profile(
        id, body, tenant_id=principal.tenant_id, actor_key=principal.actor_key,
    )


@router.post(
    "/admin/architecture-profiles/{id}/publish", response_model=ArchitectureProfileDetail,
    response_model_exclude_none=True, operation_id="publishArchitectureProfile", tags=["admin"],
)
async def publish_architecture_profile(
    id: UUID, body: ArchitectureProfilePublishRequest, request: Request,
) -> ArchitectureProfileDetail:
    principal = await _principal(request)
    _require(principal, "admin")
    return await _store(request).publish_architecture_profile(
        id, body, tenant_id=principal.tenant_id, actor_key=principal.actor_key,
    )


@router.get(
    "/reviews/queue", response_model=ReviewQueue,
    response_model_exclude_none=True, operation_id="getReviewQueue", tags=["reviews"],
)
async def get_review_queue(
    request: Request,
    type: list[ReviewQueueItemType] | None = Query(default=None),
    repository: UUID | None = None,
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
) -> ReviewQueue:
    principal = await _principal(request)
    _require(principal, "review")
    return await _store(request).review_queue(
        tenant_id=principal.tenant_id, item_types=type, repository_id=repository,
        cursor=cursor, limit=limit,
    )


# --- Admin: members & roles ---------------------------------------------

@router.get(
    "/admin/members", response_model=TenantMemberList,
    response_model_exclude_none=True, operation_id="listMembers", tags=["admin"],
)
async def list_members(request: Request) -> TenantMemberList:
    principal = await _principal(request)
    _require(principal, "admin")
    return await _store(request).list_tenant_members(tenant_id=principal.tenant_id)


@router.post(
    "/admin/members", response_model=TenantMember, status_code=201,
    response_model_exclude_none=True, operation_id="inviteMember", tags=["admin"],
)
async def invite_member(body: MemberInviteRequest, request: Request) -> TenantMember:
    principal = await _principal(request)
    _require(principal, "admin")
    return await _store(request).invite_tenant_member(
        body, tenant_id=principal.tenant_id, actor_key=principal.actor_key,
    )


@router.put(
    "/admin/members/{id}", response_model=TenantMember,
    response_model_exclude_none=True, operation_id="updateMember", tags=["admin"],
)
async def update_member(id: UUID, body: MemberUpdateRequest, request: Request) -> TenantMember:
    principal = await _principal(request)
    _require(principal, "admin")
    return await _store(request).update_tenant_member(
        id, body, tenant_id=principal.tenant_id, actor_key=principal.actor_key,
    )


@router.delete(
    "/admin/members/{id}", response_model=TenantMember,
    response_model_exclude_none=True, operation_id="removeMember", tags=["admin"],
)
async def remove_member(id: UUID, request: Request) -> TenantMember:
    principal = await _principal(request)
    _require(principal, "admin")
    return await _store(request).remove_tenant_member(
        id, tenant_id=principal.tenant_id, actor_key=principal.actor_key,
    )


# --- Admin: connectors ---------------------------------------------------

@router.get(
    "/admin/connectors", response_model=ConnectorList,
    response_model_exclude_none=True, operation_id="listConnectors", tags=["admin"],
)
async def list_connectors(request: Request) -> ConnectorList:
    principal = await _principal(request)
    _require(principal, "admin")
    return await _store(request).list_connectors(tenant_id=principal.tenant_id)


@router.post(
    "/admin/connectors", response_model=Connector, status_code=201,
    response_model_exclude_none=True, operation_id="registerConnector", tags=["admin"],
)
async def register_connector(body: ConnectorRegisterRequest, request: Request) -> Connector:
    principal = await _principal(request)
    _require(principal, "admin")
    return await _store(request).register_connector(
        body, tenant_id=principal.tenant_id, actor_key=principal.actor_key,
    )


@router.post(
    "/admin/github/repositories", response_model=Connector, status_code=201,
    response_model_exclude_none=True, operation_id="connectGitHubRepository", tags=["admin"],
)
async def connect_github_repository(
    body: GitHubRepositoryConnectRequest, request: Request,
) -> Connector:
    principal = await _principal(request)
    _require(principal, "admin")
    return await _store(request).connect_github_repository(
        body, tenant_id=principal.tenant_id, actor_key=principal.actor_key,
    )


@router.get(
    "/admin/github/repositories/available", response_model=GitHubRepositoryOptionList,
    response_model_exclude_none=True, operation_id="listAvailableGitHubRepositories", tags=["admin"],
)
async def list_available_github_repositories(request: Request) -> GitHubRepositoryOptionList:
    principal = await _principal(request)
    _require(principal, "admin")
    return await _store(request).list_available_github_repositories(
        tenant_id=principal.tenant_id,
    )


@router.get(
    "/admin/github/token", response_model=GitHubTokenConfiguration,
    response_model_exclude_none=True, operation_id="getGitHubTokenConfiguration", tags=["admin"],
)
async def get_github_token_configuration(request: Request) -> GitHubTokenConfiguration:
    principal = await _principal(request)
    _require(principal, "admin")
    return await _store(request).get_github_token_configuration(tenant_id=principal.tenant_id)


@router.put(
    "/admin/github/token", response_model=GitHubTokenConfiguration,
    response_model_exclude_none=True, operation_id="updateGitHubToken", tags=["admin"],
)
async def update_github_token(
    body: GitHubTokenUpdateRequest, request: Request,
) -> GitHubTokenConfiguration:
    principal = await _principal(request)
    _require(principal, "admin")
    return await _store(request).update_github_token(
        body, tenant_id=principal.tenant_id, actor_key=principal.actor_key,
    )


@router.delete(
    "/admin/github/token", response_model=GitHubTokenConfiguration,
    response_model_exclude_none=True, operation_id="removeGitHubToken", tags=["admin"],
)
async def remove_github_token(request: Request) -> GitHubTokenConfiguration:
    principal = await _principal(request)
    _require(principal, "admin")
    return await _store(request).remove_github_token(
        tenant_id=principal.tenant_id, actor_key=principal.actor_key,
    )


@router.post(
    "/admin/github/installations", response_model=Connector, status_code=201,
    response_model_exclude_none=True, operation_id="connectGitHubInstallation", tags=["admin"],
)
async def connect_github_installation(
    body: GitHubInstallationConnectRequest, request: Request,
) -> Connector:
    principal = await _principal(request)
    _require(principal, "admin")
    if not request.app.state.settings.github_manual_binding_enabled:
        raise APIError(
            404,
            "GITHUB_MANUAL_BINDING_DISABLED",
            "Manual GitHub installation binding is disabled; use hosted GitHub setup.",
        )
    return await _store(request).connect_github_installation(
        body, tenant_id=principal.tenant_id, actor_key=principal.actor_key,
    )


@router.post(
    "/admin/github/installations/setup", response_model=GitHubInstallationSetupResponse,
    status_code=201, operation_id="startGitHubInstallationSetup", tags=["admin"],
)
async def start_github_installation_setup(
    body: GitHubInstallationSetupRequest,
    request: Request,
) -> GitHubInstallationSetupResponse:
    principal = await _principal(request)
    _require(principal, "admin")
    client = request.app.state.github_app_client
    if not client.enabled:
        raise APIError(404, "GITHUB_APP_SETUP_DISABLED", "Hosted GitHub App setup is not enabled.")
    state = secrets.token_urlsafe(48)
    state_hash = "sha256:" + hashlib.sha256(state.encode("utf-8")).hexdigest()
    expires_at = datetime.now(UTC) + timedelta(minutes=10)
    await _store(request).begin_github_installation_setup(
        state_hash=state_hash,
        return_to=body.return_to,
        expires_at=expires_at,
        tenant_id=principal.tenant_id,
        actor_key=principal.actor_key,
    )
    return GitHubInstallationSetupResponse(
        setup_url=client.installation_url(state),
        expires_at=expires_at,
    )


@router.get(
    "/admin/github/installations/setup/callback", response_model=None,
    operation_id="completeGitHubInstallationSetup", tags=["admin"],
)
async def complete_github_installation_setup(
    request: Request,
    code: str = Query(min_length=1, max_length=1024),
    state: str = Query(min_length=16, max_length=1024),
    installation_id: str = Query(pattern=r"^[1-9][0-9]{0,19}$"),
    setup_action: str | None = Query(default=None, pattern=r"^(install|update)$"),
) -> RedirectResponse:
    del setup_action
    principal = await _principal(request)
    _require(principal, "admin")
    state_hash = "sha256:" + hashlib.sha256(state.encode("utf-8")).hexdigest()
    return_to = await _store(request).validate_github_installation_setup(
        state_hash=state_hash,
        tenant_id=principal.tenant_id,
        actor_key=principal.actor_key,
    )
    verified = await request.app.state.github_app_client.verify_installation(
        code=code,
        installation_id=installation_id,
    )
    await _store(request).complete_hosted_github_installation(
        state_hash=state_hash,
        installation_id=verified.installation_id,
        account_login=verified.account_login,
        account_id=verified.account_id,
        target_type=verified.target_type,
        scopes=list(verified.permissions),
        tenant_id=principal.tenant_id,
        actor_key=principal.actor_key,
    )
    parsed = urlsplit(return_to)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query.update({"github": "connected", "installation_id": installation_id})
    destination = urlunsplit(("", "", parsed.path, urlencode(query), parsed.fragment))
    return RedirectResponse(destination, status_code=303, headers={"Cache-Control": "no-store"})


@router.put(
    "/admin/connectors/{id}", response_model=Connector,
    response_model_exclude_none=True, operation_id="updateConnector", tags=["admin"],
)
async def update_connector(id: UUID, body: ConnectorUpdateRequest, request: Request) -> Connector:
    principal = await _principal(request)
    _require(principal, "admin")
    return await _store(request).update_connector(
        id, body, tenant_id=principal.tenant_id, actor_key=principal.actor_key,
    )


@router.delete(
    "/admin/connectors/{id}", response_model=Connector,
    response_model_exclude_none=True, operation_id="removeConnector", tags=["admin"],
)
async def remove_connector(id: UUID, request: Request) -> Connector:
    principal = await _principal(request)
    _require(principal, "admin")
    return await _store(request).remove_connector(
        id, tenant_id=principal.tenant_id, actor_key=principal.actor_key,
    )


# --- Admin: modernization governance ------------------------------------

@router.get(
    "/admin/deterministic-insight-governance",
    response_model=DeterministicInsightGovernanceState,
    response_model_exclude_none=True, operation_id="getDeterministicInsightGovernance",
    tags=["admin"],
)
async def get_deterministic_insight_governance(
    request: Request,
) -> DeterministicInsightGovernanceState:
    principal = await _principal(request)
    _require(principal, "admin")
    return await _store(request).get_deterministic_insight_governance(
        tenant_id=principal.tenant_id,
    )


@router.put(
    "/admin/deterministic-insight-governance/rules/{rule_key}",
    response_model=DeterministicInsightGovernanceState,
    response_model_exclude_none=True, operation_id="updateDeterministicInsightRule",
    tags=["admin"],
)
async def update_deterministic_insight_rule(
    rule_key: str, body: DeterministicInsightRuleUpdateRequest, request: Request,
) -> DeterministicInsightGovernanceState:
    principal = await _principal(request)
    _require(principal, "admin")
    return await _store(request).update_deterministic_insight_rule(
        rule_key, body, tenant_id=principal.tenant_id, actor_key=principal.actor_key,
    )

@router.get(
    "/admin/modernization-governance", response_model=ModernizationGovernanceState,
    response_model_exclude_none=True, operation_id="getModernizationGovernance", tags=["admin"],
)
async def get_modernization_governance(request: Request) -> ModernizationGovernanceState:
    principal = await _principal(request)
    _require(principal, "admin")
    return await _store(request).get_modernization_governance(tenant_id=principal.tenant_id)


@router.put(
    "/admin/modernization-governance/policy", response_model=ModernizationGovernanceState,
    response_model_exclude_none=True, operation_id="publishModernizationPolicy", tags=["admin"],
)
async def publish_modernization_policy(
    body: ModernizationPolicyPublishRequest, request: Request,
) -> ModernizationGovernanceState:
    principal = await _principal(request)
    _require(principal, "admin")
    return await _store(request).publish_modernization_policy(
        body, tenant_id=principal.tenant_id, actor_key=principal.actor_key,
    )


@router.put(
    "/admin/modernization-governance/internal-components/{component_key}",
    response_model=ModernizationGovernanceState, response_model_exclude_none=True,
    operation_id="governInternalCatalogComponent", tags=["admin"],
)
async def govern_internal_catalog_component(
    component_key: str, body: InternalCatalogComponentUpsertRequest, request: Request,
) -> ModernizationGovernanceState:
    principal = await _principal(request)
    _require(principal, "admin")
    return await _store(request).govern_internal_component(
        component_key, body, tenant_id=principal.tenant_id, actor_key=principal.actor_key,
    )


@router.put(
    "/admin/modernization-governance/calibration", response_model=ModernizationGovernanceState,
    response_model_exclude_none=True, operation_id="publishCalibrationCorpus", tags=["admin"],
)
async def publish_calibration_corpus(
    body: CalibrationCorpusPublishRequest, request: Request,
) -> ModernizationGovernanceState:
    principal = await _principal(request)
    _require(principal, "admin")
    return await _store(request).publish_calibration_corpus(
        body, tenant_id=principal.tenant_id, actor_key=principal.actor_key,
    )


@router.put(
    "/admin/modernization-governance/ecosystems/{ecosystem}",
    response_model=ModernizationGovernanceState, response_model_exclude_none=True,
    operation_id="evaluateEcosystemAdmission", tags=["admin"],
)
async def evaluate_ecosystem_admission(
    ecosystem: EcosystemName, body: EcosystemAdmissionEvaluateRequest, request: Request,
) -> ModernizationGovernanceState:
    principal = await _principal(request)
    _require(principal, "admin")
    return await _store(request).evaluate_ecosystem_admission(
        ecosystem, body, tenant_id=principal.tenant_id, actor_key=principal.actor_key,
    )


# --- Admin: tenant code policies ----------------------------------------

@router.get(
    "/admin/code-policies", response_model=TenantCodePolicyState,
    response_model_exclude_none=True, operation_id="getTenantCodePolicies", tags=["admin"],
)
async def get_tenant_code_policies(request: Request) -> TenantCodePolicyState:
    principal = await _principal(request)
    _require(principal, "admin")
    return await _store(request).get_tenant_code_policies(tenant_id=principal.tenant_id)


@router.put(
    "/admin/code-policies/functions/{function_key}", response_model=TenantCodePolicyState,
    response_model_exclude_none=True, operation_id="upsertTenantCodeFunction", tags=["admin"],
)
async def upsert_tenant_code_function(
    function_key: str, body: TenantCodeFunctionUpsertRequest, request: Request,
) -> TenantCodePolicyState:
    principal = await _principal(request)
    _require(principal, "admin")
    return await _store(request).upsert_tenant_code_function(
        function_key, body, tenant_id=principal.tenant_id, actor_key=principal.actor_key,
    )


@router.post(
    "/admin/code-policies/evaluations", response_model=TenantCodePolicyState,
    response_model_exclude_none=True, operation_id="evaluateTenantCodePolicies", tags=["admin"],
)
async def evaluate_tenant_code_policies(request: Request) -> TenantCodePolicyState:
    principal = await _principal(request)
    _require(principal, "admin")
    return await _store(request).evaluate_tenant_code_policies(
        tenant_id=principal.tenant_id, actor_key=principal.actor_key,
    )


# --- Admin: AI provider configuration -----------------------------------

@router.get(
    "/admin/ai-configuration", response_model=AIProviderConfiguration,
    response_model_exclude_none=True, operation_id="getAIProviderConfiguration", tags=["admin"],
)
async def get_ai_provider_configuration(request: Request) -> AIProviderConfiguration:
    principal = await _principal(request)
    _require(principal, "admin")
    return await _store(request).get_ai_provider_configuration(tenant_id=principal.tenant_id)


@router.put(
    "/admin/ai-configuration", response_model=AIProviderConfiguration,
    response_model_exclude_none=True, operation_id="updateAIProviderConfiguration", tags=["admin"],
)
async def update_ai_provider_configuration(
    body: AIProviderConfigurationUpdateRequest, request: Request,
) -> AIProviderConfiguration:
    principal = await _principal(request)
    _require(principal, "admin")
    return await _store(request).update_ai_provider_configuration(
        body, tenant_id=principal.tenant_id, actor_key=principal.actor_key,
    )


@router.delete(
    "/admin/ai-configuration/key", response_model=AIProviderConfiguration,
    response_model_exclude_none=True, operation_id="removeAIProviderKey", tags=["admin"],
)
async def remove_ai_provider_key(request: Request) -> AIProviderConfiguration:
    principal = await _principal(request)
    _require(principal, "admin")
    return await _store(request).remove_ai_provider_key(
        tenant_id=principal.tenant_id, actor_key=principal.actor_key,
    )


@router.post(
    "/admin/ai-configuration/test", response_model=AIProviderConnectionTest,
    response_model_exclude_none=True, operation_id="testAIProviderConnection", tags=["admin"],
)
async def test_ai_provider_connection(request: Request) -> AIProviderConnectionTest:
    principal = await _principal(request)
    _require(principal, "admin")
    return await _store(request).test_ai_provider_connection(
        tenant_id=principal.tenant_id, actor_key=principal.actor_key,
    )


# --- Admin: scan policy, rescans, and status -----------------------------

@router.get(
    "/admin/scan-policy", response_model=ScanPolicy,
    response_model_exclude_none=True, operation_id="getScanPolicy", tags=["admin"],
)
async def get_scan_policy(request: Request) -> ScanPolicy:
    principal = await _principal(request)
    _require(principal, "admin")
    return await _store(request).get_scan_policy(tenant_id=principal.tenant_id)


@router.put(
    "/admin/scan-policy", response_model=ScanPolicy,
    response_model_exclude_none=True, operation_id="updateScanPolicy", tags=["admin"],
)
async def update_scan_policy(body: ScanPolicyUpdateRequest, request: Request) -> ScanPolicy:
    principal = await _principal(request)
    _require(principal, "admin")
    return await _store(request).update_scan_policy(
        body, tenant_id=principal.tenant_id, actor_key=principal.actor_key,
    )


@router.get(
    "/admin/scan-status", response_model=ScanStatus,
    response_model_exclude_none=True, operation_id="getScanStatus", tags=["admin"],
)
async def get_scan_status(request: Request) -> ScanStatus:
    principal = await _principal(request)
    _require(principal, "admin")
    return await _store(request).scan_status(tenant_id=principal.tenant_id)


@router.get(
    "/admin/services", response_model=ServiceStatusList,
    response_model_exclude_none=True, operation_id="getServiceStatus", tags=["admin"],
)
async def get_service_status(request: Request) -> ServiceStatusList:
    principal = await _principal(request)
    _require(principal, "admin")
    return await _store(request).service_status(tenant_id=principal.tenant_id)


@router.put(
    "/admin/services/{service_key}", response_model=ServiceStatus,
    response_model_exclude_none=True, operation_id="updateServiceControl", tags=["admin"],
)
async def update_service_control(
    service_key: str, body: ServiceControlRequest, request: Request,
) -> ServiceStatus:
    principal = await _principal(request)
    _require(principal, "admin")
    return await _store(request).update_service_control(
        service_key, body, tenant_id=principal.tenant_id, actor_key=principal.actor_key,
    )


@router.post(
    "/admin/rescans", response_model=RescanJob,
    response_model_exclude_none=True, operation_id="requestRescan", tags=["admin"],
)
async def request_rescan(body: RescanRequest, request: Request, response: Response) -> RescanJob:
    principal = await _principal(request)
    _require(principal, "admin")
    job, created = await _store(request).request_rescan(
        body, tenant_id=principal.tenant_id, actor_key=principal.actor_key,
    )
    # A fresh job is 201 Created; an idempotent replay returns the existing job as 200 OK.
    response.status_code = 201 if created else 200
    return job


@router.get(
    "/admin/rescans", response_model=RescanJobList,
    response_model_exclude_none=True, operation_id="listRescans", tags=["admin"],
)
async def list_rescans(
    request: Request,
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
) -> RescanJobList:
    principal = await _principal(request)
    _require(principal, "admin")
    return await _store(request).list_rescan_jobs(
        tenant_id=principal.tenant_id, cursor=cursor, limit=limit,
    )
