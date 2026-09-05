# AdminApi

All URIs are relative to */api/v1*

| Method | HTTP request | Description |
|------------- | ------------- | -------------|
| [**completeGitHubInstallationSetup**](AdminApi.md#completeGitHubInstallationSetup) | **GET** /admin/github/installations/setup/callback | Complete Github Installation Setup |
| [**connectGitHubInstallation**](AdminApi.md#connectGitHubInstallation) | **POST** /admin/github/installations | Connect Github Installation |
| [**connectGitHubRepository**](AdminApi.md#connectGitHubRepository) | **POST** /admin/github/repositories | Connect Github Repository |
| [**createArchitectureProfile**](AdminApi.md#createArchitectureProfile) | **POST** /admin/architecture-profiles | Create Architecture Profile |
| [**evaluateEcosystemAdmission**](AdminApi.md#evaluateEcosystemAdmission) | **PUT** /admin/modernization-governance/ecosystems/{ecosystem} | Evaluate Ecosystem Admission |
| [**evaluateTenantCodePolicies**](AdminApi.md#evaluateTenantCodePolicies) | **POST** /admin/code-policies/evaluations | Evaluate Tenant Code Policies |
| [**getAIProviderConfiguration**](AdminApi.md#getAIProviderConfiguration) | **GET** /admin/ai-configuration | Get Ai Provider Configuration |
| [**getDeterministicInsightGovernance**](AdminApi.md#getDeterministicInsightGovernance) | **GET** /admin/deterministic-insight-governance | Get Deterministic Insight Governance |
| [**getGitHubTokenConfiguration**](AdminApi.md#getGitHubTokenConfiguration) | **GET** /admin/github/token | Get Github Token Configuration |
| [**getModernizationGovernance**](AdminApi.md#getModernizationGovernance) | **GET** /admin/modernization-governance | Get Modernization Governance |
| [**getScanPolicy**](AdminApi.md#getScanPolicy) | **GET** /admin/scan-policy | Get Scan Policy |
| [**getScanStatus**](AdminApi.md#getScanStatus) | **GET** /admin/scan-status | Get Scan Status |
| [**getServiceStatus**](AdminApi.md#getServiceStatus) | **GET** /admin/services | Get Service Status |
| [**getTenantCodePolicies**](AdminApi.md#getTenantCodePolicies) | **GET** /admin/code-policies | Get Tenant Code Policies |
| [**governInternalCatalogComponent**](AdminApi.md#governInternalCatalogComponent) | **PUT** /admin/modernization-governance/internal-components/{component_key} | Govern Internal Catalog Component |
| [**inviteMember**](AdminApi.md#inviteMember) | **POST** /admin/members | Invite Member |
| [**listArchitectureProfiles**](AdminApi.md#listArchitectureProfiles) | **GET** /admin/architecture-profiles | List Architecture Profiles |
| [**listAvailableGitHubRepositories**](AdminApi.md#listAvailableGitHubRepositories) | **GET** /admin/github/repositories/available | List Available Github Repositories |
| [**listConnectors**](AdminApi.md#listConnectors) | **GET** /admin/connectors | List Connectors |
| [**listMembers**](AdminApi.md#listMembers) | **GET** /admin/members | List Members |
| [**listRescans**](AdminApi.md#listRescans) | **GET** /admin/rescans | List Rescans |
| [**publishArchitectureProfile**](AdminApi.md#publishArchitectureProfile) | **POST** /admin/architecture-profiles/{id}/publish | Publish Architecture Profile |
| [**publishCalibrationCorpus**](AdminApi.md#publishCalibrationCorpus) | **PUT** /admin/modernization-governance/calibration | Publish Calibration Corpus |
| [**publishModernizationPolicy**](AdminApi.md#publishModernizationPolicy) | **PUT** /admin/modernization-governance/policy | Publish Modernization Policy |
| [**registerConnector**](AdminApi.md#registerConnector) | **POST** /admin/connectors | Register Connector |
| [**removeAIProviderKey**](AdminApi.md#removeAIProviderKey) | **DELETE** /admin/ai-configuration/key | Remove Ai Provider Key |
| [**removeConnector**](AdminApi.md#removeConnector) | **DELETE** /admin/connectors/{id} | Remove Connector |
| [**removeGitHubToken**](AdminApi.md#removeGitHubToken) | **DELETE** /admin/github/token | Remove Github Token |
| [**removeMember**](AdminApi.md#removeMember) | **DELETE** /admin/members/{id} | Remove Member |
| [**requestRescan**](AdminApi.md#requestRescan) | **POST** /admin/rescans | Request Rescan |
| [**startGitHubInstallationSetup**](AdminApi.md#startGitHubInstallationSetup) | **POST** /admin/github/installations/setup | Start Github Installation Setup |
| [**testAIProviderConnection**](AdminApi.md#testAIProviderConnection) | **POST** /admin/ai-configuration/test | Test Ai Provider Connection |
| [**updateAIProviderConfiguration**](AdminApi.md#updateAIProviderConfiguration) | **PUT** /admin/ai-configuration | Update Ai Provider Configuration |
| [**updateArchitectureProfile**](AdminApi.md#updateArchitectureProfile) | **PUT** /admin/architecture-profiles/{id} | Update Architecture Profile |
| [**updateConnector**](AdminApi.md#updateConnector) | **PUT** /admin/connectors/{id} | Update Connector |
| [**updateDeterministicInsightRule**](AdminApi.md#updateDeterministicInsightRule) | **PUT** /admin/deterministic-insight-governance/rules/{rule_key} | Update Deterministic Insight Rule |
| [**updateGitHubToken**](AdminApi.md#updateGitHubToken) | **PUT** /admin/github/token | Update Github Token |
| [**updateMember**](AdminApi.md#updateMember) | **PUT** /admin/members/{id} | Update Member |
| [**updateScanPolicy**](AdminApi.md#updateScanPolicy) | **PUT** /admin/scan-policy | Update Scan Policy |
| [**updateServiceControl**](AdminApi.md#updateServiceControl) | **PUT** /admin/services/{service_key} | Update Service Control |
| [**upsertTenantCodeFunction**](AdminApi.md#upsertTenantCodeFunction) | **PUT** /admin/code-policies/functions/{function_key} | Upsert Tenant Code Function |


<a name="completeGitHubInstallationSetup"></a>
# **completeGitHubInstallationSetup**
> oas_any_type_not_mapped completeGitHubInstallationSetup(code, state, installation\_id, setup\_action)

Complete Github Installation Setup

### Parameters

|Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **code** | **String**|  | [default to null] |
| **state** | **String**|  | [default to null] |
| **installation\_id** | **String**|  | [default to null] |
| **setup\_action** | **String**|  | [optional] [default to null] |

### Return type

[**oas_any_type_not_mapped**](../Models/AnyType.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: application/json

<a name="connectGitHubInstallation"></a>
# **connectGitHubInstallation**
> Connector connectGitHubInstallation(GitHubInstallationConnectRequest)

Connect Github Installation

### Parameters

|Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **GitHubInstallationConnectRequest** | [**GitHubInstallationConnectRequest**](../Models/GitHubInstallationConnectRequest.md)|  | |

### Return type

[**Connector**](../Models/Connector.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: application/json
- **Accept**: application/json

<a name="connectGitHubRepository"></a>
# **connectGitHubRepository**
> Connector connectGitHubRepository(GitHubRepositoryConnectRequest)

Connect Github Repository

### Parameters

|Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **GitHubRepositoryConnectRequest** | [**GitHubRepositoryConnectRequest**](../Models/GitHubRepositoryConnectRequest.md)|  | |

### Return type

[**Connector**](../Models/Connector.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: application/json
- **Accept**: application/json

<a name="createArchitectureProfile"></a>
# **createArchitectureProfile**
> ArchitectureProfileDetail createArchitectureProfile(ArchitectureProfileCreateRequest)

Create Architecture Profile

### Parameters

|Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **ArchitectureProfileCreateRequest** | [**ArchitectureProfileCreateRequest**](../Models/ArchitectureProfileCreateRequest.md)|  | |

### Return type

[**ArchitectureProfileDetail**](../Models/ArchitectureProfileDetail.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: application/json
- **Accept**: application/json

<a name="evaluateEcosystemAdmission"></a>
# **evaluateEcosystemAdmission**
> ModernizationGovernanceState evaluateEcosystemAdmission(ecosystem, EcosystemAdmissionEvaluateRequest)

Evaluate Ecosystem Admission

### Parameters

|Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **ecosystem** | **String**|  | [default to null] [enum: PYPI, MAVEN, CARGO, NUGET] |
| **EcosystemAdmissionEvaluateRequest** | [**EcosystemAdmissionEvaluateRequest**](../Models/EcosystemAdmissionEvaluateRequest.md)|  | |

### Return type

[**ModernizationGovernanceState**](../Models/ModernizationGovernanceState.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: application/json
- **Accept**: application/json

<a name="evaluateTenantCodePolicies"></a>
# **evaluateTenantCodePolicies**
> TenantCodePolicyState evaluateTenantCodePolicies()

Evaluate Tenant Code Policies

### Parameters
This endpoint does not need any parameter.

### Return type

[**TenantCodePolicyState**](../Models/TenantCodePolicyState.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: application/json

<a name="getAIProviderConfiguration"></a>
# **getAIProviderConfiguration**
> AIProviderConfiguration getAIProviderConfiguration()

Get Ai Provider Configuration

### Parameters
This endpoint does not need any parameter.

### Return type

[**AIProviderConfiguration**](../Models/AIProviderConfiguration.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: application/json

<a name="getDeterministicInsightGovernance"></a>
# **getDeterministicInsightGovernance**
> DeterministicInsightGovernanceState getDeterministicInsightGovernance()

Get Deterministic Insight Governance

### Parameters
This endpoint does not need any parameter.

### Return type

[**DeterministicInsightGovernanceState**](../Models/DeterministicInsightGovernanceState.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: application/json

<a name="getGitHubTokenConfiguration"></a>
# **getGitHubTokenConfiguration**
> GitHubTokenConfiguration getGitHubTokenConfiguration()

Get Github Token Configuration

### Parameters
This endpoint does not need any parameter.

### Return type

[**GitHubTokenConfiguration**](../Models/GitHubTokenConfiguration.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: application/json

<a name="getModernizationGovernance"></a>
# **getModernizationGovernance**
> ModernizationGovernanceState getModernizationGovernance()

Get Modernization Governance

### Parameters
This endpoint does not need any parameter.

### Return type

[**ModernizationGovernanceState**](../Models/ModernizationGovernanceState.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: application/json

<a name="getScanPolicy"></a>
# **getScanPolicy**
> ScanPolicy getScanPolicy()

Get Scan Policy

### Parameters
This endpoint does not need any parameter.

### Return type

[**ScanPolicy**](../Models/ScanPolicy.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: application/json

<a name="getScanStatus"></a>
# **getScanStatus**
> ScanStatus getScanStatus()

Get Scan Status

### Parameters
This endpoint does not need any parameter.

### Return type

[**ScanStatus**](../Models/ScanStatus.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: application/json

<a name="getServiceStatus"></a>
# **getServiceStatus**
> ServiceStatusList getServiceStatus()

Get Service Status

### Parameters
This endpoint does not need any parameter.

### Return type

[**ServiceStatusList**](../Models/ServiceStatusList.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: application/json

<a name="getTenantCodePolicies"></a>
# **getTenantCodePolicies**
> TenantCodePolicyState getTenantCodePolicies()

Get Tenant Code Policies

### Parameters
This endpoint does not need any parameter.

### Return type

[**TenantCodePolicyState**](../Models/TenantCodePolicyState.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: application/json

<a name="governInternalCatalogComponent"></a>
# **governInternalCatalogComponent**
> ModernizationGovernanceState governInternalCatalogComponent(component\_key, InternalCatalogComponentUpsertRequest)

Govern Internal Catalog Component

### Parameters

|Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **component\_key** | **String**|  | [default to null] |
| **InternalCatalogComponentUpsertRequest** | [**InternalCatalogComponentUpsertRequest**](../Models/InternalCatalogComponentUpsertRequest.md)|  | |

### Return type

[**ModernizationGovernanceState**](../Models/ModernizationGovernanceState.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: application/json
- **Accept**: application/json

<a name="inviteMember"></a>
# **inviteMember**
> TenantMember inviteMember(MemberInviteRequest)

Invite Member

### Parameters

|Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **MemberInviteRequest** | [**MemberInviteRequest**](../Models/MemberInviteRequest.md)|  | |

### Return type

[**TenantMember**](../Models/TenantMember.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: application/json
- **Accept**: application/json

<a name="listArchitectureProfiles"></a>
# **listArchitectureProfiles**
> ArchitectureProfileList listArchitectureProfiles()

List Architecture Profiles

### Parameters
This endpoint does not need any parameter.

### Return type

[**ArchitectureProfileList**](../Models/ArchitectureProfileList.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: application/json

<a name="listAvailableGitHubRepositories"></a>
# **listAvailableGitHubRepositories**
> GitHubRepositoryOptionList listAvailableGitHubRepositories()

List Available Github Repositories

### Parameters
This endpoint does not need any parameter.

### Return type

[**GitHubRepositoryOptionList**](../Models/GitHubRepositoryOptionList.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: application/json

<a name="listConnectors"></a>
# **listConnectors**
> ConnectorList listConnectors()

List Connectors

### Parameters
This endpoint does not need any parameter.

### Return type

[**ConnectorList**](../Models/ConnectorList.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: application/json

<a name="listMembers"></a>
# **listMembers**
> TenantMemberList listMembers()

List Members

### Parameters
This endpoint does not need any parameter.

### Return type

[**TenantMemberList**](../Models/TenantMemberList.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: application/json

<a name="listRescans"></a>
# **listRescans**
> RescanJobList listRescans(cursor, limit)

List Rescans

### Parameters

|Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **cursor** | **String**|  | [optional] [default to null] |
| **limit** | **Integer**|  | [optional] [default to 50] |

### Return type

[**RescanJobList**](../Models/RescanJobList.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: application/json

<a name="publishArchitectureProfile"></a>
# **publishArchitectureProfile**
> ArchitectureProfileDetail publishArchitectureProfile(id, ArchitectureProfilePublishRequest)

Publish Architecture Profile

### Parameters

|Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **id** | **UUID**|  | [default to null] |
| **ArchitectureProfilePublishRequest** | [**ArchitectureProfilePublishRequest**](../Models/ArchitectureProfilePublishRequest.md)|  | |

### Return type

[**ArchitectureProfileDetail**](../Models/ArchitectureProfileDetail.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: application/json
- **Accept**: application/json

<a name="publishCalibrationCorpus"></a>
# **publishCalibrationCorpus**
> ModernizationGovernanceState publishCalibrationCorpus(CalibrationCorpusPublishRequest)

Publish Calibration Corpus

### Parameters

|Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **CalibrationCorpusPublishRequest** | [**CalibrationCorpusPublishRequest**](../Models/CalibrationCorpusPublishRequest.md)|  | |

### Return type

[**ModernizationGovernanceState**](../Models/ModernizationGovernanceState.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: application/json
- **Accept**: application/json

<a name="publishModernizationPolicy"></a>
# **publishModernizationPolicy**
> ModernizationGovernanceState publishModernizationPolicy(ModernizationPolicyPublishRequest)

Publish Modernization Policy

### Parameters

|Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **ModernizationPolicyPublishRequest** | [**ModernizationPolicyPublishRequest**](../Models/ModernizationPolicyPublishRequest.md)|  | |

### Return type

[**ModernizationGovernanceState**](../Models/ModernizationGovernanceState.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: application/json
- **Accept**: application/json

<a name="registerConnector"></a>
# **registerConnector**
> Connector registerConnector(ConnectorRegisterRequest)

Register Connector

### Parameters

|Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **ConnectorRegisterRequest** | [**ConnectorRegisterRequest**](../Models/ConnectorRegisterRequest.md)|  | |

### Return type

[**Connector**](../Models/Connector.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: application/json
- **Accept**: application/json

<a name="removeAIProviderKey"></a>
# **removeAIProviderKey**
> AIProviderConfiguration removeAIProviderKey()

Remove Ai Provider Key

### Parameters
This endpoint does not need any parameter.

### Return type

[**AIProviderConfiguration**](../Models/AIProviderConfiguration.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: application/json

<a name="removeConnector"></a>
# **removeConnector**
> Connector removeConnector(id)

Remove Connector

### Parameters

|Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **id** | **UUID**|  | [default to null] |

### Return type

[**Connector**](../Models/Connector.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: application/json

<a name="removeGitHubToken"></a>
# **removeGitHubToken**
> GitHubTokenConfiguration removeGitHubToken()

Remove Github Token

### Parameters
This endpoint does not need any parameter.

### Return type

[**GitHubTokenConfiguration**](../Models/GitHubTokenConfiguration.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: application/json

<a name="removeMember"></a>
# **removeMember**
> TenantMember removeMember(id)

Remove Member

### Parameters

|Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **id** | **UUID**|  | [default to null] |

### Return type

[**TenantMember**](../Models/TenantMember.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: application/json

<a name="requestRescan"></a>
# **requestRescan**
> RescanJob requestRescan(RescanRequest)

Request Rescan

### Parameters

|Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **RescanRequest** | [**RescanRequest**](../Models/RescanRequest.md)|  | |

### Return type

[**RescanJob**](../Models/RescanJob.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: application/json
- **Accept**: application/json

<a name="startGitHubInstallationSetup"></a>
# **startGitHubInstallationSetup**
> GitHubInstallationSetupResponse startGitHubInstallationSetup(GitHubInstallationSetupRequest)

Start Github Installation Setup

### Parameters

|Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **GitHubInstallationSetupRequest** | [**GitHubInstallationSetupRequest**](../Models/GitHubInstallationSetupRequest.md)|  | |

### Return type

[**GitHubInstallationSetupResponse**](../Models/GitHubInstallationSetupResponse.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: application/json
- **Accept**: application/json

<a name="testAIProviderConnection"></a>
# **testAIProviderConnection**
> AIProviderConnectionTest testAIProviderConnection()

Test Ai Provider Connection

### Parameters
This endpoint does not need any parameter.

### Return type

[**AIProviderConnectionTest**](../Models/AIProviderConnectionTest.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: application/json

<a name="updateAIProviderConfiguration"></a>
# **updateAIProviderConfiguration**
> AIProviderConfiguration updateAIProviderConfiguration(AIProviderConfigurationUpdateRequest)

Update Ai Provider Configuration

### Parameters

|Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **AIProviderConfigurationUpdateRequest** | [**AIProviderConfigurationUpdateRequest**](../Models/AIProviderConfigurationUpdateRequest.md)|  | |

### Return type

[**AIProviderConfiguration**](../Models/AIProviderConfiguration.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: application/json
- **Accept**: application/json

<a name="updateArchitectureProfile"></a>
# **updateArchitectureProfile**
> ArchitectureProfileDetail updateArchitectureProfile(id, ArchitectureProfileUpdateRequest)

Update Architecture Profile

### Parameters

|Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **id** | **UUID**|  | [default to null] |
| **ArchitectureProfileUpdateRequest** | [**ArchitectureProfileUpdateRequest**](../Models/ArchitectureProfileUpdateRequest.md)|  | |

### Return type

[**ArchitectureProfileDetail**](../Models/ArchitectureProfileDetail.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: application/json
- **Accept**: application/json

<a name="updateConnector"></a>
# **updateConnector**
> Connector updateConnector(id, ConnectorUpdateRequest)

Update Connector

### Parameters

|Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **id** | **UUID**|  | [default to null] |
| **ConnectorUpdateRequest** | [**ConnectorUpdateRequest**](../Models/ConnectorUpdateRequest.md)|  | |

### Return type

[**Connector**](../Models/Connector.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: application/json
- **Accept**: application/json

<a name="updateDeterministicInsightRule"></a>
# **updateDeterministicInsightRule**
> DeterministicInsightGovernanceState updateDeterministicInsightRule(rule\_key, DeterministicInsightRuleUpdateRequest)

Update Deterministic Insight Rule

### Parameters

|Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **rule\_key** | **String**|  | [default to null] |
| **DeterministicInsightRuleUpdateRequest** | [**DeterministicInsightRuleUpdateRequest**](../Models/DeterministicInsightRuleUpdateRequest.md)|  | |

### Return type

[**DeterministicInsightGovernanceState**](../Models/DeterministicInsightGovernanceState.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: application/json
- **Accept**: application/json

<a name="updateGitHubToken"></a>
# **updateGitHubToken**
> GitHubTokenConfiguration updateGitHubToken(GitHubTokenUpdateRequest)

Update Github Token

### Parameters

|Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **GitHubTokenUpdateRequest** | [**GitHubTokenUpdateRequest**](../Models/GitHubTokenUpdateRequest.md)|  | |

### Return type

[**GitHubTokenConfiguration**](../Models/GitHubTokenConfiguration.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: application/json
- **Accept**: application/json

<a name="updateMember"></a>
# **updateMember**
> TenantMember updateMember(id, MemberUpdateRequest)

Update Member

### Parameters

|Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **id** | **UUID**|  | [default to null] |
| **MemberUpdateRequest** | [**MemberUpdateRequest**](../Models/MemberUpdateRequest.md)|  | |

### Return type

[**TenantMember**](../Models/TenantMember.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: application/json
- **Accept**: application/json

<a name="updateScanPolicy"></a>
# **updateScanPolicy**
> ScanPolicy updateScanPolicy(ScanPolicyUpdateRequest)

Update Scan Policy

### Parameters

|Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **ScanPolicyUpdateRequest** | [**ScanPolicyUpdateRequest**](../Models/ScanPolicyUpdateRequest.md)|  | |

### Return type

[**ScanPolicy**](../Models/ScanPolicy.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: application/json
- **Accept**: application/json

<a name="updateServiceControl"></a>
# **updateServiceControl**
> ServiceStatus updateServiceControl(service\_key, ServiceControlRequest)

Update Service Control

### Parameters

|Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **service\_key** | **String**|  | [default to null] |
| **ServiceControlRequest** | [**ServiceControlRequest**](../Models/ServiceControlRequest.md)|  | |

### Return type

[**ServiceStatus**](../Models/ServiceStatus.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: application/json
- **Accept**: application/json

<a name="upsertTenantCodeFunction"></a>
# **upsertTenantCodeFunction**
> TenantCodePolicyState upsertTenantCodeFunction(function\_key, TenantCodeFunctionUpsertRequest)

Upsert Tenant Code Function

### Parameters

|Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **function\_key** | **String**|  | [default to null] |
| **TenantCodeFunctionUpsertRequest** | [**TenantCodeFunctionUpsertRequest**](../Models/TenantCodeFunctionUpsertRequest.md)|  | |

### Return type

[**TenantCodePolicyState**](../Models/TenantCodePolicyState.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: application/json
- **Accept**: application/json

