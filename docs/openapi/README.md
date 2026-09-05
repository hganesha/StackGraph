# Documentation for StackGraph API

<a name="documentation-for-api-endpoints"></a>
## Documentation for API Endpoints

All URIs are relative to */api/v1*

| Class | Method | HTTP request | Description |
|------------ | ------------- | ------------- | -------------|
| *AdminApi* | [**completeGitHubInstallationSetup**](Apis/AdminApi.md#completeGitHubInstallationSetup) | **GET** /admin/github/installations/setup/callback | Complete Github Installation Setup |
*AdminApi* | [**connectGitHubInstallation**](Apis/AdminApi.md#connectGitHubInstallation) | **POST** /admin/github/installations | Connect Github Installation |
*AdminApi* | [**connectGitHubRepository**](Apis/AdminApi.md#connectGitHubRepository) | **POST** /admin/github/repositories | Connect Github Repository |
*AdminApi* | [**createArchitectureProfile**](Apis/AdminApi.md#createArchitectureProfile) | **POST** /admin/architecture-profiles | Create Architecture Profile |
*AdminApi* | [**evaluateEcosystemAdmission**](Apis/AdminApi.md#evaluateEcosystemAdmission) | **PUT** /admin/modernization-governance/ecosystems/{ecosystem} | Evaluate Ecosystem Admission |
*AdminApi* | [**evaluateTenantCodePolicies**](Apis/AdminApi.md#evaluateTenantCodePolicies) | **POST** /admin/code-policies/evaluations | Evaluate Tenant Code Policies |
*AdminApi* | [**getAIProviderConfiguration**](Apis/AdminApi.md#getAIProviderConfiguration) | **GET** /admin/ai-configuration | Get Ai Provider Configuration |
*AdminApi* | [**getDeterministicInsightGovernance**](Apis/AdminApi.md#getDeterministicInsightGovernance) | **GET** /admin/deterministic-insight-governance | Get Deterministic Insight Governance |
*AdminApi* | [**getGitHubTokenConfiguration**](Apis/AdminApi.md#getGitHubTokenConfiguration) | **GET** /admin/github/token | Get Github Token Configuration |
*AdminApi* | [**getModernizationGovernance**](Apis/AdminApi.md#getModernizationGovernance) | **GET** /admin/modernization-governance | Get Modernization Governance |
*AdminApi* | [**getScanPolicy**](Apis/AdminApi.md#getScanPolicy) | **GET** /admin/scan-policy | Get Scan Policy |
*AdminApi* | [**getScanStatus**](Apis/AdminApi.md#getScanStatus) | **GET** /admin/scan-status | Get Scan Status |
*AdminApi* | [**getServiceStatus**](Apis/AdminApi.md#getServiceStatus) | **GET** /admin/services | Get Service Status |
*AdminApi* | [**getTenantCodePolicies**](Apis/AdminApi.md#getTenantCodePolicies) | **GET** /admin/code-policies | Get Tenant Code Policies |
*AdminApi* | [**governInternalCatalogComponent**](Apis/AdminApi.md#governInternalCatalogComponent) | **PUT** /admin/modernization-governance/internal-components/{component_key} | Govern Internal Catalog Component |
*AdminApi* | [**inviteMember**](Apis/AdminApi.md#inviteMember) | **POST** /admin/members | Invite Member |
*AdminApi* | [**listArchitectureProfiles**](Apis/AdminApi.md#listArchitectureProfiles) | **GET** /admin/architecture-profiles | List Architecture Profiles |
*AdminApi* | [**listAvailableGitHubRepositories**](Apis/AdminApi.md#listAvailableGitHubRepositories) | **GET** /admin/github/repositories/available | List Available Github Repositories |
*AdminApi* | [**listConnectors**](Apis/AdminApi.md#listConnectors) | **GET** /admin/connectors | List Connectors |
*AdminApi* | [**listMembers**](Apis/AdminApi.md#listMembers) | **GET** /admin/members | List Members |
*AdminApi* | [**listRescans**](Apis/AdminApi.md#listRescans) | **GET** /admin/rescans | List Rescans |
*AdminApi* | [**publishArchitectureProfile**](Apis/AdminApi.md#publishArchitectureProfile) | **POST** /admin/architecture-profiles/{id}/publish | Publish Architecture Profile |
*AdminApi* | [**publishCalibrationCorpus**](Apis/AdminApi.md#publishCalibrationCorpus) | **PUT** /admin/modernization-governance/calibration | Publish Calibration Corpus |
*AdminApi* | [**publishModernizationPolicy**](Apis/AdminApi.md#publishModernizationPolicy) | **PUT** /admin/modernization-governance/policy | Publish Modernization Policy |
*AdminApi* | [**registerConnector**](Apis/AdminApi.md#registerConnector) | **POST** /admin/connectors | Register Connector |
*AdminApi* | [**removeAIProviderKey**](Apis/AdminApi.md#removeAIProviderKey) | **DELETE** /admin/ai-configuration/key | Remove Ai Provider Key |
*AdminApi* | [**removeConnector**](Apis/AdminApi.md#removeConnector) | **DELETE** /admin/connectors/{id} | Remove Connector |
*AdminApi* | [**removeGitHubToken**](Apis/AdminApi.md#removeGitHubToken) | **DELETE** /admin/github/token | Remove Github Token |
*AdminApi* | [**removeMember**](Apis/AdminApi.md#removeMember) | **DELETE** /admin/members/{id} | Remove Member |
*AdminApi* | [**requestRescan**](Apis/AdminApi.md#requestRescan) | **POST** /admin/rescans | Request Rescan |
*AdminApi* | [**startGitHubInstallationSetup**](Apis/AdminApi.md#startGitHubInstallationSetup) | **POST** /admin/github/installations/setup | Start Github Installation Setup |
*AdminApi* | [**testAIProviderConnection**](Apis/AdminApi.md#testAIProviderConnection) | **POST** /admin/ai-configuration/test | Test Ai Provider Connection |
*AdminApi* | [**updateAIProviderConfiguration**](Apis/AdminApi.md#updateAIProviderConfiguration) | **PUT** /admin/ai-configuration | Update Ai Provider Configuration |
*AdminApi* | [**updateArchitectureProfile**](Apis/AdminApi.md#updateArchitectureProfile) | **PUT** /admin/architecture-profiles/{id} | Update Architecture Profile |
*AdminApi* | [**updateConnector**](Apis/AdminApi.md#updateConnector) | **PUT** /admin/connectors/{id} | Update Connector |
*AdminApi* | [**updateDeterministicInsightRule**](Apis/AdminApi.md#updateDeterministicInsightRule) | **PUT** /admin/deterministic-insight-governance/rules/{rule_key} | Update Deterministic Insight Rule |
*AdminApi* | [**updateGitHubToken**](Apis/AdminApi.md#updateGitHubToken) | **PUT** /admin/github/token | Update Github Token |
*AdminApi* | [**updateMember**](Apis/AdminApi.md#updateMember) | **PUT** /admin/members/{id} | Update Member |
*AdminApi* | [**updateScanPolicy**](Apis/AdminApi.md#updateScanPolicy) | **PUT** /admin/scan-policy | Update Scan Policy |
*AdminApi* | [**updateServiceControl**](Apis/AdminApi.md#updateServiceControl) | **PUT** /admin/services/{service_key} | Update Service Control |
*AdminApi* | [**upsertTenantCodeFunction**](Apis/AdminApi.md#upsertTenantCodeFunction) | **PUT** /admin/code-policies/functions/{function_key} | Upsert Tenant Code Function |
| *ApplicationsApi* | [**getApplication**](Apis/ApplicationsApi.md#getApplication) | **GET** /applications/{id} | Get Application |
*ApplicationsApi* | [**updateApplication**](Apis/ApplicationsApi.md#updateApplication) | **PUT** /applications/{id} | Update Application |
| *ArchitectureCanvasApi* | [**compareCanvasProjections**](Apis/ArchitectureCanvasApi.md#compareCanvasProjections) | **POST** /canvas/comparisons | Compare Canvas Projections |
*ArchitectureCanvasApi* | [**getArchitectureReferenceModel**](Apis/ArchitectureCanvasApi.md#getArchitectureReferenceModel) | **GET** /canvas/reference-models/{key} | Get Architecture Reference Model |
*ArchitectureCanvasApi* | [**getArchitectureTaxonomy**](Apis/ArchitectureCanvasApi.md#getArchitectureTaxonomy) | **GET** /canvas/taxonomy | Get Architecture Taxonomy |
*ArchitectureCanvasApi* | [**getCanvasProjection**](Apis/ArchitectureCanvasApi.md#getCanvasProjection) | **GET** /canvas/projection | Get Canvas Projection |
*ArchitectureCanvasApi* | [**getCanvasTemplate**](Apis/ArchitectureCanvasApi.md#getCanvasTemplate) | **GET** /canvas/templates/{key} | Get Canvas Template |
*ArchitectureCanvasApi* | [**getTargetCanvasProjection**](Apis/ArchitectureCanvasApi.md#getTargetCanvasProjection) | **GET** /canvas/target-projection | Get Target Canvas Projection |
*ArchitectureCanvasApi* | [**listArchitectureReferenceModels**](Apis/ArchitectureCanvasApi.md#listArchitectureReferenceModels) | **GET** /canvas/reference-models | List Architecture Reference Models |
*ArchitectureCanvasApi* | [**listCanvasTemplates**](Apis/ArchitectureCanvasApi.md#listCanvasTemplates) | **GET** /canvas/templates | List Canvas Templates |
| *AuthenticationApi* | [**callbackAuthCallbackGet**](Apis/AuthenticationApi.md#callbackAuthCallbackGet) | **GET** /auth/callback | Callback |
*AuthenticationApi* | [**loginAuthLoginGet**](Apis/AuthenticationApi.md#loginAuthLoginGet) | **GET** /auth/login | Login |
*AuthenticationApi* | [**logoutAuthLogoutPost**](Apis/AuthenticationApi.md#logoutAuthLogoutPost) | **POST** /auth/logout | Logout |
*AuthenticationApi* | [**refreshAuthRefreshPost**](Apis/AuthenticationApi.md#refreshAuthRefreshPost) | **POST** /auth/refresh | Refresh |
| *BusinessMapApi* | [**archiveBusinessMap**](Apis/BusinessMapApi.md#archiveBusinessMap) | **DELETE** /business-maps/{id} | Archive Business Map |
*BusinessMapApi* | [**createBusinessMap**](Apis/BusinessMapApi.md#createBusinessMap) | **POST** /business-maps | Create Business Map |
*BusinessMapApi* | [**getBusinessMap**](Apis/BusinessMapApi.md#getBusinessMap) | **GET** /business-maps/{id} | Get Business Map |
*BusinessMapApi* | [**listBusinessMapRevisions**](Apis/BusinessMapApi.md#listBusinessMapRevisions) | **GET** /business-maps/{id}/revisions | List Business Map Revisions |
*BusinessMapApi* | [**listBusinessMaps**](Apis/BusinessMapApi.md#listBusinessMaps) | **GET** /business-maps | List Business Maps |
*BusinessMapApi* | [**saveBusinessMap**](Apis/BusinessMapApi.md#saveBusinessMap) | **PUT** /business-maps/{id} | Save Business Map |
| *ChangesApi* | [**cancelSimulation**](Apis/ChangesApi.md#cancelSimulation) | **DELETE** /simulations/{id} | Cancel Simulation |
*ChangesApi* | [**compileMutation**](Apis/ChangesApi.md#compileMutation) | **POST** /mutations/compile | Compile Mutation |
*ChangesApi* | [**createSimulation**](Apis/ChangesApi.md#createSimulation) | **POST** /simulations | Create Simulation |
*ChangesApi* | [**getSimulation**](Apis/ChangesApi.md#getSimulation) | **GET** /simulations/{id} | Get Simulation |
*ChangesApi* | [**listActionSubjects**](Apis/ChangesApi.md#listActionSubjects) | **GET** /action-types/{predicate}/subjects | List Action Subjects |
*ChangesApi* | [**listActionTypes**](Apis/ChangesApi.md#listActionTypes) | **GET** /action-types | List Action Types |
*ChangesApi* | [**listChangeScopes**](Apis/ChangesApi.md#listChangeScopes) | **GET** /entities/{id}/scopes | List Change Scopes |
*ChangesApi* | [**listValidTargets**](Apis/ChangesApi.md#listValidTargets) | **GET** /entities/{id}/valid-targets | List Valid Targets |
*ChangesApi* | [**validateMutation**](Apis/ChangesApi.md#validateMutation) | **POST** /mutations/validate | Validate Mutation |
| *EmbeddingsApi* | [**getEmbeddingStatus**](Apis/EmbeddingsApi.md#getEmbeddingStatus) | **GET** /embeddings/status | Get Embedding Status |
*EmbeddingsApi* | [**listSimilarApplications**](Apis/EmbeddingsApi.md#listSimilarApplications) | **GET** /entities/{id}/similar | List Similar Applications |
*EmbeddingsApi* | [**promoteEmbeddingSpace**](Apis/EmbeddingsApi.md#promoteEmbeddingSpace) | **POST** /embedding-spaces/{id}/promotion | Promote Embedding Space |
*EmbeddingsApi* | [**requestEmbeddingBackfill**](Apis/EmbeddingsApi.md#requestEmbeddingBackfill) | **POST** /embeddings/backfill | Request Embedding Backfill |
*EmbeddingsApi* | [**reviewApplicationSimilarity**](Apis/EmbeddingsApi.md#reviewApplicationSimilarity) | **POST** /similarity-candidates/{id}/review | Review Application Similarity |
*EmbeddingsApi* | [**semanticSearch**](Apis/EmbeddingsApi.md#semanticSearch) | **POST** /search/semantic | Semantic Search |
| *EstateApi* | [**getEstateSummary**](Apis/EstateApi.md#getEstateSummary) | **GET** /estate/summary | Get Estate Summary |
| *EvidenceApi* | [**getFactEvidence**](Apis/EvidenceApi.md#getFactEvidence) | **GET** /facts/{id}/evidence | Get Fact Evidence |
| *GraphApi* | [**getGraphNeighborhood**](Apis/GraphApi.md#getGraphNeighborhood) | **GET** /graph/neighborhood | Get Graph Neighborhood |
| *GraphIntelligenceApi* | [**getEntityBlastRadius**](Apis/GraphIntelligenceApi.md#getEntityBlastRadius) | **GET** /entities/{id}/blast-radius | Get Entity Blast Radius |
*GraphIntelligenceApi* | [**getEntityGraphMetrics**](Apis/GraphIntelligenceApi.md#getEntityGraphMetrics) | **GET** /entities/{id}/graph-metrics | Get Entity Graph Metrics |
*GraphIntelligenceApi* | [**getGraphIntelligenceStatus**](Apis/GraphIntelligenceApi.md#getGraphIntelligenceStatus) | **GET** /graph-intelligence/status | Get Graph Intelligence Status |
*GraphIntelligenceApi* | [**listEntityCriticalEdges**](Apis/GraphIntelligenceApi.md#listEntityCriticalEdges) | **GET** /entities/{id}/critical-edges | List Entity Critical Edges |
*GraphIntelligenceApi* | [**listGraphIntelligenceAnomalies**](Apis/GraphIntelligenceApi.md#listGraphIntelligenceAnomalies) | **GET** /graph-intelligence/anomalies | List Graph Intelligence Anomalies |
*GraphIntelligenceApi* | [**listGraphIntelligenceCommunities**](Apis/GraphIntelligenceApi.md#listGraphIntelligenceCommunities) | **GET** /graph-intelligence/communities | List Graph Intelligence Communities |
*GraphIntelligenceApi* | [**listGraphIntelligenceMotifs**](Apis/GraphIntelligenceApi.md#listGraphIntelligenceMotifs) | **GET** /graph-intelligence/motifs | List Graph Intelligence Motifs |
*GraphIntelligenceApi* | [**listGraphIntelligenceRisks**](Apis/GraphIntelligenceApi.md#listGraphIntelligenceRisks) | **GET** /graph-intelligence/risks | List Graph Intelligence Risks |
*GraphIntelligenceApi* | [**requestGraphAnalysis**](Apis/GraphIntelligenceApi.md#requestGraphAnalysis) | **POST** /graph-intelligence/analysis-requests | Request Graph Analysis |
| *IdentityApi* | [**reviewIdentityAssertion**](Apis/IdentityApi.md#reviewIdentityAssertion) | **POST** /identity-assertions/{id}/review | Review Identity Assertion |
| *IntelligenceApi* | [**askEstate**](Apis/IntelligenceApi.md#askEstate) | **POST** /ask | Ask Estate |
*IntelligenceApi* | [**getCapabilityTaxonomy**](Apis/IntelligenceApi.md#getCapabilityTaxonomy) | **GET** /capabilities/taxonomy | Get Capability Taxonomy |
*IntelligenceApi* | [**getPhase3IntelligenceMetrics**](Apis/IntelligenceApi.md#getPhase3IntelligenceMetrics) | **GET** /intelligence/phase-3/metrics | Get Phase3 Intelligence Metrics |
*IntelligenceApi* | [**getRepositoryCapabilities**](Apis/IntelligenceApi.md#getRepositoryCapabilities) | **GET** /repositories/{id}/capabilities | Get Repository Capabilities |
*IntelligenceApi* | [**getRepositoryModernizationIntelligence**](Apis/IntelligenceApi.md#getRepositoryModernizationIntelligence) | **GET** /repositories/{id}/modernization-intelligence | Get Repository Modernization Intelligence |
*IntelligenceApi* | [**listCapabilityFootprints**](Apis/IntelligenceApi.md#listCapabilityFootprints) | **GET** /capabilities/footprints | List Capability Footprints |
*IntelligenceApi* | [**listDeterministicInsights**](Apis/IntelligenceApi.md#listDeterministicInsights) | **GET** /insights/deterministic | List Deterministic Insights |
*IntelligenceApi* | [**listEnterpriseInsightReports**](Apis/IntelligenceApi.md#listEnterpriseInsightReports) | **GET** /insights/reports | List Enterprise Insight Reports |
*IntelligenceApi* | [**listModernizationOpportunities**](Apis/IntelligenceApi.md#listModernizationOpportunities) | **GET** /modernization | List Modernization |
*IntelligenceApi* | [**optimizeModernizationScenario**](Apis/IntelligenceApi.md#optimizeModernizationScenario) | **POST** /modernization/scenarios | Optimize Modernization Scenario |
*IntelligenceApi* | [**recordModernizationValidationOutcome**](Apis/IntelligenceApi.md#recordModernizationValidationOutcome) | **POST** /modernization-recommendations/{id}/validation-outcomes | Record Modernization Validation Outcome |
*IntelligenceApi* | [**reviewCapabilityInference**](Apis/IntelligenceApi.md#reviewCapabilityInference) | **POST** /capability-inferences/{id}/review | Review Capability Inference |
*IntelligenceApi* | [**reviewDuplicateCapabilityCandidate**](Apis/IntelligenceApi.md#reviewDuplicateCapabilityCandidate) | **POST** /duplicate-capability-candidates/{id}/review | Review Duplicate Capability Candidate |
*IntelligenceApi* | [**reviewModernizationCandidate**](Apis/IntelligenceApi.md#reviewModernizationCandidate) | **POST** /modernization-candidates/{id}/review | Review Modernization Candidate |
*IntelligenceApi* | [**reviewModernizationRecommendation**](Apis/IntelligenceApi.md#reviewModernizationRecommendation) | **POST** /modernization-recommendations/{id}/review | Review Modernization Recommendation |
| *OperationsApi* | [**liveHealthLiveGet**](Apis/OperationsApi.md#liveHealthLiveGet) | **GET** /health/live | Live |
*OperationsApi* | [**readyHealthReadyGet**](Apis/OperationsApi.md#readyHealthReadyGet) | **GET** /health/ready | Ready |
| *RepositoriesApi* | [**getRepository**](Apis/RepositoriesApi.md#getRepository) | **GET** /repositories/{id} | Get Repository |
*RepositoriesApi* | [**getRepositoryActivity**](Apis/RepositoriesApi.md#getRepositoryActivity) | **GET** /repositories/{id}/activity | Get Repository Activity |
*RepositoriesApi* | [**updateRepository**](Apis/RepositoriesApi.md#updateRepository) | **PUT** /repositories/{id} | Update Repository |
| *ReviewsApi* | [**getReviewQueue**](Apis/ReviewsApi.md#getReviewQueue) | **GET** /reviews/queue | Get Review Queue |
| *SessionApi* | [**getSession**](Apis/SessionApi.md#getSession) | **GET** /session | Get Session |
| *TechnologiesApi* | [**getTechnology**](Apis/TechnologiesApi.md#getTechnology) | **GET** /technologies/{id} | Get Technology |
*TechnologiesApi* | [**getTechnologyEstateHierarchy**](Apis/TechnologiesApi.md#getTechnologyEstateHierarchy) | **GET** /technologies/hierarchy | Get Technology Estate Hierarchy |


<a name="documentation-for-models"></a>
## Documentation for Models

 - [AIProviderConfiguration](./Models/AIProviderConfiguration.md)
 - [AIProviderConfigurationUpdateRequest](./Models/AIProviderConfigurationUpdateRequest.md)
 - [AIProviderConnectionTest](./Models/AIProviderConnectionTest.md)
 - [ActionSubject](./Models/ActionSubject.md)
 - [ActionSubjectList](./Models/ActionSubjectList.md)
 - [ActionTypeList](./Models/ActionTypeList.md)
 - [ActionTypeSummary](./Models/ActionTypeSummary.md)
 - [ApplicationComponentDependencyHierarchy](./Models/ApplicationComponentDependencyHierarchy.md)
 - [ApplicationDependencyNode](./Models/ApplicationDependencyNode.md)
 - [ApplicationDetail](./Models/ApplicationDetail.md)
 - [ApplicationRepositoryDependencyHierarchy](./Models/ApplicationRepositoryDependencyHierarchy.md)
 - [ApplicationSimilarityCandidate](./Models/ApplicationSimilarityCandidate.md)
 - [ApplicationSimilarityList](./Models/ApplicationSimilarityList.md)
 - [ApplicationSimilarityReviewRequest](./Models/ApplicationSimilarityReviewRequest.md)
 - [ApplicationSimilarityReviewResult](./Models/ApplicationSimilarityReviewResult.md)
 - [ApplicationTechnologyFunction](./Models/ApplicationTechnologyFunction.md)
 - [ApplicationTechnologyGroup](./Models/ApplicationTechnologyGroup.md)
 - [ApplicationTechnologyResourceDetails](./Models/ApplicationTechnologyResourceDetails.md)
 - [ApplicationTechnologyUsage](./Models/ApplicationTechnologyUsage.md)
 - [ArchitectureAspectModel](./Models/ArchitectureAspectModel.md)
 - [ArchitectureCapabilityModel](./Models/ArchitectureCapabilityModel.md)
 - [ArchitectureCellDefinitionModel](./Models/ArchitectureCellDefinitionModel.md)
 - [ArchitectureConcernModel](./Models/ArchitectureConcernModel.md)
 - [ArchitectureDomainModel](./Models/ArchitectureDomainModel.md)
 - [ArchitectureProfileCreateRequest](./Models/ArchitectureProfileCreateRequest.md)
 - [ArchitectureProfileDetail](./Models/ArchitectureProfileDetail.md)
 - [ArchitectureProfileList](./Models/ArchitectureProfileList.md)
 - [ArchitectureProfilePublishRequest](./Models/ArchitectureProfilePublishRequest.md)
 - [ArchitectureProfileStateModel](./Models/ArchitectureProfileStateModel.md)
 - [ArchitectureProfileSummary](./Models/ArchitectureProfileSummary.md)
 - [ArchitectureProfileUpdateRequest](./Models/ArchitectureProfileUpdateRequest.md)
 - [ArchitectureReferenceModel](./Models/ArchitectureReferenceModel.md)
 - [ArchitectureReferenceModelList](./Models/ArchitectureReferenceModelList.md)
 - [ArchitectureTaxonomyResponse](./Models/ArchitectureTaxonomyResponse.md)
 - [AskRequest](./Models/AskRequest.md)
 - [AskResponse](./Models/AskResponse.md)
 - [AssessmentSummary](./Models/AssessmentSummary.md)
 - [BusinessMapApplicationAssignment](./Models/BusinessMapApplicationAssignment.md)
 - [BusinessMapCapabilityNode](./Models/BusinessMapCapabilityNode.md)
 - [BusinessMapCreateRequest](./Models/BusinessMapCreateRequest.md)
 - [BusinessMapDetail](./Models/BusinessMapDetail.md)
 - [BusinessMapFunctionAssignment](./Models/BusinessMapFunctionAssignment.md)
 - [BusinessMapFunctionNode](./Models/BusinessMapFunctionNode.md)
 - [BusinessMapLane](./Models/BusinessMapLane.md)
 - [BusinessMapList](./Models/BusinessMapList.md)
 - [BusinessMapPlacement](./Models/BusinessMapPlacement.md)
 - [BusinessMapProcessNode](./Models/BusinessMapProcessNode.md)
 - [BusinessMapRevisionList](./Models/BusinessMapRevisionList.md)
 - [BusinessMapRevisionSummary](./Models/BusinessMapRevisionSummary.md)
 - [BusinessMapSaveRequest](./Models/BusinessMapSaveRequest.md)
 - [BusinessMapSharedGroup](./Models/BusinessMapSharedGroup.md)
 - [BusinessMapStateModel](./Models/BusinessMapStateModel.md)
 - [BusinessMapSummary](./Models/BusinessMapSummary.md)
 - [CalibrationCorpusPublishRequest](./Models/CalibrationCorpusPublishRequest.md)
 - [CalibrationCorpusSummary](./Models/CalibrationCorpusSummary.md)
 - [CalibrationObservedMetrics](./Models/CalibrationObservedMetrics.md)
 - [CanvasBandLayoutModel](./Models/CanvasBandLayoutModel.md)
 - [CanvasBindingModel](./Models/CanvasBindingModel.md)
 - [CanvasCellComparisonModel](./Models/CanvasCellComparisonModel.md)
 - [CanvasCellLayoutModel](./Models/CanvasCellLayoutModel.md)
 - [CanvasCellMeasuresModel](./Models/CanvasCellMeasuresModel.md)
 - [CanvasCellProjectionModel](./Models/CanvasCellProjectionModel.md)
 - [CanvasClassificationTrayItemModel](./Models/CanvasClassificationTrayItemModel.md)
 - [CanvasClassificationTrayModel](./Models/CanvasClassificationTrayModel.md)
 - [CanvasComparison](./Models/CanvasComparison.md)
 - [CanvasComparisonRequest](./Models/CanvasComparisonRequest.md)
 - [CanvasComparisonSummaryModel](./Models/CanvasComparisonSummaryModel.md)
 - [CanvasOccupantModel](./Models/CanvasOccupantModel.md)
 - [CanvasPolicyExceptionModel](./Models/CanvasPolicyExceptionModel.md)
 - [CanvasProjection](./Models/CanvasProjection.md)
 - [CanvasProjectionSelectorModel](./Models/CanvasProjectionSelectorModel.md)
 - [CanvasProjectionSummaryModel](./Models/CanvasProjectionSummaryModel.md)
 - [CanvasScopeSelectorModel](./Models/CanvasScopeSelectorModel.md)
 - [CanvasTemplateList](./Models/CanvasTemplateList.md)
 - [CanvasTemplateModel](./Models/CanvasTemplateModel.md)
 - [CapabilityDefinitionModel](./Models/CapabilityDefinitionModel.md)
 - [CapabilityFootprintList](./Models/CapabilityFootprintList.md)
 - [CapabilityFootprintModel](./Models/CapabilityFootprintModel.md)
 - [CapabilityInferenceReviewRequest](./Models/CapabilityInferenceReviewRequest.md)
 - [CapabilityInferenceReviewResult](./Models/CapabilityInferenceReviewResult.md)
 - [CapabilityInferenceSummary](./Models/CapabilityInferenceSummary.md)
 - [CapabilityTaxonomyResponse](./Models/CapabilityTaxonomyResponse.md)
 - [CellExpectationModel](./Models/CellExpectationModel.md)
 - [CellObservationStatusModel](./Models/CellObservationStatusModel.md)
 - [ChangeGate](./Models/ChangeGate.md)
 - [ChangeScope](./Models/ChangeScope.md)
 - [ChangeScopeList](./Models/ChangeScopeList.md)
 - [ChangeSetModel](./Models/ChangeSetModel.md)
 - [Citation](./Models/Citation.md)
 - [CodePolicyTechnologySummary](./Models/CodePolicyTechnologySummary.md)
 - [CodePolicyViolation](./Models/CodePolicyViolation.md)
 - [Connector](./Models/Connector.md)
 - [ConnectorList](./Models/ConnectorList.md)
 - [ConnectorRegisterRequest](./Models/ConnectorRegisterRequest.md)
 - [ConnectorUpdateRequest](./Models/ConnectorUpdateRequest.md)
 - [Coverage](./Models/Coverage.md)
 - [CriticalGraphEdge](./Models/CriticalGraphEdge.md)
 - [CriticalGraphEdgeList](./Models/CriticalGraphEdgeList.md)
 - [DeterministicInsight](./Models/DeterministicInsight.md)
 - [DeterministicInsightGovernanceState](./Models/DeterministicInsightGovernanceState.md)
 - [DeterministicInsightList](./Models/DeterministicInsightList.md)
 - [DeterministicInsightRecommendation](./Models/DeterministicInsightRecommendation.md)
 - [DeterministicInsightRuleSummary](./Models/DeterministicInsightRuleSummary.md)
 - [DeterministicInsightRuleUpdateRequest](./Models/DeterministicInsightRuleUpdateRequest.md)
 - [DeterministicInsightSummary](./Models/DeterministicInsightSummary.md)
 - [DuplicateCapabilityCandidateSummary](./Models/DuplicateCapabilityCandidateSummary.md)
 - [DuplicateCapabilityReviewRequest](./Models/DuplicateCapabilityReviewRequest.md)
 - [DuplicateCapabilityReviewResult](./Models/DuplicateCapabilityReviewResult.md)
 - [EcosystemAdmissionEvaluateRequest](./Models/EcosystemAdmissionEvaluateRequest.md)
 - [EcosystemAdmissionSummary](./Models/EcosystemAdmissionSummary.md)
 - [EmbeddingBackfillRequest](./Models/EmbeddingBackfillRequest.md)
 - [EmbeddingBackfillResult](./Models/EmbeddingBackfillResult.md)
 - [EmbeddingSpacePromotionRequest](./Models/EmbeddingSpacePromotionRequest.md)
 - [EmbeddingSpacePromotionResult](./Models/EmbeddingSpacePromotionResult.md)
 - [EmbeddingSpaceSnapshot](./Models/EmbeddingSpaceSnapshot.md)
 - [EmbeddingStatus](./Models/EmbeddingStatus.md)
 - [EnterpriseInsightReport](./Models/EnterpriseInsightReport.md)
 - [EnterpriseInsightReportList](./Models/EnterpriseInsightReportList.md)
 - [EntityDescriptionUpdateRequest](./Models/EntityDescriptionUpdateRequest.md)
 - [EntityGraphIntelligence](./Models/EntityGraphIntelligence.md)
 - [EntityResolution](./Models/EntityResolution.md)
 - [EntitySummary](./Models/EntitySummary.md)
 - [EstateCounts](./Models/EstateCounts.md)
 - [EstateSummary](./Models/EstateSummary.md)
 - [EvidenceDetail](./Models/EvidenceDetail.md)
 - [Extractor](./Models/Extractor.md)
 - [Freshness](./Models/Freshness.md)
 - [GateReason](./Models/GateReason.md)
 - [GitHubInstallationConnectRequest](./Models/GitHubInstallationConnectRequest.md)
 - [GitHubInstallationSetupRequest](./Models/GitHubInstallationSetupRequest.md)
 - [GitHubInstallationSetupResponse](./Models/GitHubInstallationSetupResponse.md)
 - [GitHubRepositoryConnectRequest](./Models/GitHubRepositoryConnectRequest.md)
 - [GitHubRepositoryOption](./Models/GitHubRepositoryOption.md)
 - [GitHubRepositoryOptionList](./Models/GitHubRepositoryOptionList.md)
 - [GitHubTokenConfiguration](./Models/GitHubTokenConfiguration.md)
 - [GitHubTokenUpdateRequest](./Models/GitHubTokenUpdateRequest.md)
 - [GraphAnalysisRequestCreate](./Models/GraphAnalysisRequestCreate.md)
 - [GraphAnalysisRequestResult](./Models/GraphAnalysisRequestResult.md)
 - [GraphAnalysisSnapshot](./Models/GraphAnalysisSnapshot.md)
 - [GraphAnomaly](./Models/GraphAnomaly.md)
 - [GraphAnomalyList](./Models/GraphAnomalyList.md)
 - [GraphBlastRadius](./Models/GraphBlastRadius.md)
 - [GraphCommunity](./Models/GraphCommunity.md)
 - [GraphCommunityList](./Models/GraphCommunityList.md)
 - [GraphEdge](./Models/GraphEdge.md)
 - [GraphImpactPath](./Models/GraphImpactPath.md)
 - [GraphIntelligenceStatus](./Models/GraphIntelligenceStatus.md)
 - [GraphMetric](./Models/GraphMetric.md)
 - [GraphMotif](./Models/GraphMotif.md)
 - [GraphMotifList](./Models/GraphMotifList.md)
 - [GraphNeighborhood](./Models/GraphNeighborhood.md)
 - [GraphNode](./Models/GraphNode.md)
 - [GraphRiskItem](./Models/GraphRiskItem.md)
 - [GraphRiskList](./Models/GraphRiskList.md)
 - [HTTPValidationError](./Models/HTTPValidationError.md)
 - [IdentityReviewRequest](./Models/IdentityReviewRequest.md)
 - [IdentityReviewResult](./Models/IdentityReviewResult.md)
 - [InsightImpactStages](./Models/InsightImpactStages.md)
 - [InternalCatalogCandidateSummary](./Models/InternalCatalogCandidateSummary.md)
 - [InternalCatalogComponentSummary](./Models/InternalCatalogComponentSummary.md)
 - [InternalCatalogComponentUpsertRequest](./Models/InternalCatalogComponentUpsertRequest.md)
 - [InternalUsage](./Models/InternalUsage.md)
 - [Location_inner](./Models/Location_inner.md)
 - [MeasureResultModel](./Models/MeasureResultModel.md)
 - [MemberInviteRequest](./Models/MemberInviteRequest.md)
 - [MemberUpdateRequest](./Models/MemberUpdateRequest.md)
 - [ModernizationCandidateModel](./Models/ModernizationCandidateModel.md)
 - [ModernizationCandidateReviewRequest](./Models/ModernizationCandidateReviewRequest.md)
 - [ModernizationCandidateReviewResult](./Models/ModernizationCandidateReviewResult.md)
 - [ModernizationGovernanceState](./Models/ModernizationGovernanceState.md)
 - [ModernizationImpactModel](./Models/ModernizationImpactModel.md)
 - [ModernizationList](./Models/ModernizationList.md)
 - [ModernizationOptionEligibilityModel](./Models/ModernizationOptionEligibilityModel.md)
 - [ModernizationOptionModel](./Models/ModernizationOptionModel.md)
 - [ModernizationPolicyPublishRequest](./Models/ModernizationPolicyPublishRequest.md)
 - [ModernizationPolicySummary](./Models/ModernizationPolicySummary.md)
 - [ModernizationRecommendationModel](./Models/ModernizationRecommendationModel.md)
 - [ModernizationRecommendationReviewRequest](./Models/ModernizationRecommendationReviewRequest.md)
 - [ModernizationRecommendationReviewResult](./Models/ModernizationRecommendationReviewResult.md)
 - [ModernizationScenarioItem](./Models/ModernizationScenarioItem.md)
 - [ModernizationScenarioRequest](./Models/ModernizationScenarioRequest.md)
 - [ModernizationScenarioResult](./Models/ModernizationScenarioResult.md)
 - [ModernizationValidationOutcomeRequest](./Models/ModernizationValidationOutcomeRequest.md)
 - [ModernizationValidationOutcomeResult](./Models/ModernizationValidationOutcomeResult.md)
 - [MutationCompileRequest](./Models/MutationCompileRequest.md)
 - [MutationCompileResult](./Models/MutationCompileResult.md)
 - [MutationIR](./Models/MutationIR.md)
 - [MutationValidateRequest](./Models/MutationValidateRequest.md)
 - [MutationValidationError](./Models/MutationValidationError.md)
 - [PackageSource](./Models/PackageSource.md)
 - [PageInfo](./Models/PageInfo.md)
 - [Phase3IntelligenceMetrics](./Models/Phase3IntelligenceMetrics.md)
 - [ProviderQuota](./Models/ProviderQuota.md)
 - [RankedItem](./Models/RankedItem.md)
 - [RecommendationSummary](./Models/RecommendationSummary.md)
 - [RepositoryActivity](./Models/RepositoryActivity.md)
 - [RepositoryActivityActor](./Models/RepositoryActivityActor.md)
 - [RepositoryActivityContributor](./Models/RepositoryActivityContributor.md)
 - [RepositoryActivityCoverage](./Models/RepositoryActivityCoverage.md)
 - [RepositoryActivityEvent](./Models/RepositoryActivityEvent.md)
 - [RepositoryActivitySource](./Models/RepositoryActivitySource.md)
 - [RepositoryActivitySummary](./Models/RepositoryActivitySummary.md)
 - [RepositoryCapabilityIntelligence](./Models/RepositoryCapabilityIntelligence.md)
 - [RepositoryCodePolicyEvaluation](./Models/RepositoryCodePolicyEvaluation.md)
 - [RepositoryDetail](./Models/RepositoryDetail.md)
 - [RepositoryModernizationIntelligence](./Models/RepositoryModernizationIntelligence.md)
 - [RepositoryProfile](./Models/RepositoryProfile.md)
 - [RescanJob](./Models/RescanJob.md)
 - [RescanJobList](./Models/RescanJobList.md)
 - [RescanRequest](./Models/RescanRequest.md)
 - [ResolutionCandidate](./Models/ResolutionCandidate.md)
 - [ResolvedEntity](./Models/ResolvedEntity.md)
 - [ReviewQueue](./Models/ReviewQueue.md)
 - [ReviewQueueItem](./Models/ReviewQueueItem.md)
 - [ScanPolicy](./Models/ScanPolicy.md)
 - [ScanPolicyUpdateRequest](./Models/ScanPolicyUpdateRequest.md)
 - [ScanStatus](./Models/ScanStatus.md)
 - [Score](./Models/Score.md)
 - [SemanticSearchHit](./Models/SemanticSearchHit.md)
 - [SemanticSearchRequest](./Models/SemanticSearchRequest.md)
 - [SemanticSearchResponse](./Models/SemanticSearchResponse.md)
 - [ServiceControlRequest](./Models/ServiceControlRequest.md)
 - [ServiceStatus](./Models/ServiceStatus.md)
 - [ServiceStatusList](./Models/ServiceStatusList.md)
 - [SessionInfo](./Models/SessionInfo.md)
 - [SimulationCreateRequest](./Models/SimulationCreateRequest.md)
 - [SimulationFinding](./Models/SimulationFinding.md)
 - [SimulationInterpretation](./Models/SimulationInterpretation.md)
 - [SimulationRunModel](./Models/SimulationRunModel.md)
 - [TaxonomySummary](./Models/TaxonomySummary.md)
 - [TechnologyCatalogProfile](./Models/TechnologyCatalogProfile.md)
 - [TechnologyDetail](./Models/TechnologyDetail.md)
 - [TechnologyEstateHierarchy](./Models/TechnologyEstateHierarchy.md)
 - [TechnologyEstateHierarchyNode](./Models/TechnologyEstateHierarchyNode.md)
 - [TenantCellPolicyModel](./Models/TenantCellPolicyModel.md)
 - [TenantCodeFunctionPolicySummary](./Models/TenantCodeFunctionPolicySummary.md)
 - [TenantCodeFunctionSummary](./Models/TenantCodeFunctionSummary.md)
 - [TenantCodeFunctionUpsertRequest](./Models/TenantCodeFunctionUpsertRequest.md)
 - [TenantCodePolicyState](./Models/TenantCodePolicyState.md)
 - [TenantCodePolicySummary](./Models/TenantCodePolicySummary.md)
 - [TenantExtensionCellModel](./Models/TenantExtensionCellModel.md)
 - [TenantMember](./Models/TenantMember.md)
 - [TenantMemberList](./Models/TenantMemberList.md)
 - [ValidTarget](./Models/ValidTarget.md)
 - [ValidTargetList](./Models/ValidTargetList.md)
 - [ValidationError](./Models/ValidationError.md)
 - [VersionDistribution](./Models/VersionDistribution.md)


<a name="documentation-for-authorization"></a>
## Documentation for Authorization

All endpoints do not require authorization.
