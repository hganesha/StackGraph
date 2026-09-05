# IntelligenceApi

All URIs are relative to */api/v1*

| Method | HTTP request | Description |
|------------- | ------------- | -------------|
| [**askEstate**](IntelligenceApi.md#askEstate) | **POST** /ask | Ask Estate |
| [**getCapabilityTaxonomy**](IntelligenceApi.md#getCapabilityTaxonomy) | **GET** /capabilities/taxonomy | Get Capability Taxonomy |
| [**getPhase3IntelligenceMetrics**](IntelligenceApi.md#getPhase3IntelligenceMetrics) | **GET** /intelligence/phase-3/metrics | Get Phase3 Intelligence Metrics |
| [**getRepositoryCapabilities**](IntelligenceApi.md#getRepositoryCapabilities) | **GET** /repositories/{id}/capabilities | Get Repository Capabilities |
| [**getRepositoryModernizationIntelligence**](IntelligenceApi.md#getRepositoryModernizationIntelligence) | **GET** /repositories/{id}/modernization-intelligence | Get Repository Modernization Intelligence |
| [**listCapabilityFootprints**](IntelligenceApi.md#listCapabilityFootprints) | **GET** /capabilities/footprints | List Capability Footprints |
| [**listDeterministicInsights**](IntelligenceApi.md#listDeterministicInsights) | **GET** /insights/deterministic | List Deterministic Insights |
| [**listEnterpriseInsightReports**](IntelligenceApi.md#listEnterpriseInsightReports) | **GET** /insights/reports | List Enterprise Insight Reports |
| [**listModernizationOpportunities**](IntelligenceApi.md#listModernizationOpportunities) | **GET** /modernization | List Modernization |
| [**optimizeModernizationScenario**](IntelligenceApi.md#optimizeModernizationScenario) | **POST** /modernization/scenarios | Optimize Modernization Scenario |
| [**recordModernizationValidationOutcome**](IntelligenceApi.md#recordModernizationValidationOutcome) | **POST** /modernization-recommendations/{id}/validation-outcomes | Record Modernization Validation Outcome |
| [**reviewCapabilityInference**](IntelligenceApi.md#reviewCapabilityInference) | **POST** /capability-inferences/{id}/review | Review Capability Inference |
| [**reviewDuplicateCapabilityCandidate**](IntelligenceApi.md#reviewDuplicateCapabilityCandidate) | **POST** /duplicate-capability-candidates/{id}/review | Review Duplicate Capability Candidate |
| [**reviewModernizationCandidate**](IntelligenceApi.md#reviewModernizationCandidate) | **POST** /modernization-candidates/{id}/review | Review Modernization Candidate |
| [**reviewModernizationRecommendation**](IntelligenceApi.md#reviewModernizationRecommendation) | **POST** /modernization-recommendations/{id}/review | Review Modernization Recommendation |


<a name="askEstate"></a>
# **askEstate**
> AskResponse askEstate(AskRequest)

Ask Estate

### Parameters

|Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **AskRequest** | [**AskRequest**](../Models/AskRequest.md)|  | |

### Return type

[**AskResponse**](../Models/AskResponse.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: application/json
- **Accept**: application/json

<a name="getCapabilityTaxonomy"></a>
# **getCapabilityTaxonomy**
> CapabilityTaxonomyResponse getCapabilityTaxonomy(version)

Get Capability Taxonomy

### Parameters

|Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **version** | **String**|  | [optional] [default to null] |

### Return type

[**CapabilityTaxonomyResponse**](../Models/CapabilityTaxonomyResponse.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: application/json

<a name="getPhase3IntelligenceMetrics"></a>
# **getPhase3IntelligenceMetrics**
> Phase3IntelligenceMetrics getPhase3IntelligenceMetrics()

Get Phase3 Intelligence Metrics

### Parameters
This endpoint does not need any parameter.

### Return type

[**Phase3IntelligenceMetrics**](../Models/Phase3IntelligenceMetrics.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: application/json

<a name="getRepositoryCapabilities"></a>
# **getRepositoryCapabilities**
> RepositoryCapabilityIntelligence getRepositoryCapabilities(id)

Get Repository Capabilities

### Parameters

|Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **id** | **UUID**|  | [default to null] |

### Return type

[**RepositoryCapabilityIntelligence**](../Models/RepositoryCapabilityIntelligence.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: application/json

<a name="getRepositoryModernizationIntelligence"></a>
# **getRepositoryModernizationIntelligence**
> RepositoryModernizationIntelligence getRepositoryModernizationIntelligence(id, limit)

Get Repository Modernization Intelligence

### Parameters

|Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **id** | **UUID**|  | [default to null] |
| **limit** | **Integer**|  | [optional] [default to 50] |

### Return type

[**RepositoryModernizationIntelligence**](../Models/RepositoryModernizationIntelligence.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: application/json

<a name="listCapabilityFootprints"></a>
# **listCapabilityFootprints**
> CapabilityFootprintList listCapabilityFootprints()

List Capability Footprints

### Parameters
This endpoint does not need any parameter.

### Return type

[**CapabilityFootprintList**](../Models/CapabilityFootprintList.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: application/json

<a name="listDeterministicInsights"></a>
# **listDeterministicInsights**
> DeterministicInsightList listDeterministicInsights(scope\_entity\_id, rule\_key, limit)

List Deterministic Insights

### Parameters

|Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **scope\_entity\_id** | **UUID**|  | [optional] [default to null] |
| **rule\_key** | **String**|  | [optional] [default to null] |
| **limit** | **Integer**|  | [optional] [default to 100] |

### Return type

[**DeterministicInsightList**](../Models/DeterministicInsightList.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: application/json

<a name="listEnterpriseInsightReports"></a>
# **listEnterpriseInsightReports**
> EnterpriseInsightReportList listEnterpriseInsightReports()

List Enterprise Insight Reports

### Parameters
This endpoint does not need any parameter.

### Return type

[**EnterpriseInsightReportList**](../Models/EnterpriseInsightReportList.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: application/json

<a name="listModernizationOpportunities"></a>
# **listModernizationOpportunities**
> ModernizationList listModernizationOpportunities(cursor, limit)

List Modernization

### Parameters

|Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **cursor** | **String**|  | [optional] [default to null] |
| **limit** | **Integer**|  | [optional] [default to 50] |

### Return type

[**ModernizationList**](../Models/ModernizationList.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: application/json

<a name="optimizeModernizationScenario"></a>
# **optimizeModernizationScenario**
> ModernizationScenarioResult optimizeModernizationScenario(ModernizationScenarioRequest)

Optimize Modernization Scenario

### Parameters

|Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **ModernizationScenarioRequest** | [**ModernizationScenarioRequest**](../Models/ModernizationScenarioRequest.md)|  | |

### Return type

[**ModernizationScenarioResult**](../Models/ModernizationScenarioResult.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: application/json
- **Accept**: application/json

<a name="recordModernizationValidationOutcome"></a>
# **recordModernizationValidationOutcome**
> ModernizationValidationOutcomeResult recordModernizationValidationOutcome(id, ModernizationValidationOutcomeRequest)

Record Modernization Validation Outcome

### Parameters

|Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **id** | **UUID**|  | [default to null] |
| **ModernizationValidationOutcomeRequest** | [**ModernizationValidationOutcomeRequest**](../Models/ModernizationValidationOutcomeRequest.md)|  | |

### Return type

[**ModernizationValidationOutcomeResult**](../Models/ModernizationValidationOutcomeResult.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: application/json
- **Accept**: application/json

<a name="reviewCapabilityInference"></a>
# **reviewCapabilityInference**
> CapabilityInferenceReviewResult reviewCapabilityInference(id, CapabilityInferenceReviewRequest)

Review Capability Inference

### Parameters

|Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **id** | **UUID**|  | [default to null] |
| **CapabilityInferenceReviewRequest** | [**CapabilityInferenceReviewRequest**](../Models/CapabilityInferenceReviewRequest.md)|  | |

### Return type

[**CapabilityInferenceReviewResult**](../Models/CapabilityInferenceReviewResult.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: application/json
- **Accept**: application/json

<a name="reviewDuplicateCapabilityCandidate"></a>
# **reviewDuplicateCapabilityCandidate**
> DuplicateCapabilityReviewResult reviewDuplicateCapabilityCandidate(id, DuplicateCapabilityReviewRequest)

Review Duplicate Capability Candidate

### Parameters

|Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **id** | **UUID**|  | [default to null] |
| **DuplicateCapabilityReviewRequest** | [**DuplicateCapabilityReviewRequest**](../Models/DuplicateCapabilityReviewRequest.md)|  | |

### Return type

[**DuplicateCapabilityReviewResult**](../Models/DuplicateCapabilityReviewResult.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: application/json
- **Accept**: application/json

<a name="reviewModernizationCandidate"></a>
# **reviewModernizationCandidate**
> ModernizationCandidateReviewResult reviewModernizationCandidate(id, ModernizationCandidateReviewRequest)

Review Modernization Candidate

### Parameters

|Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **id** | **UUID**|  | [default to null] |
| **ModernizationCandidateReviewRequest** | [**ModernizationCandidateReviewRequest**](../Models/ModernizationCandidateReviewRequest.md)|  | |

### Return type

[**ModernizationCandidateReviewResult**](../Models/ModernizationCandidateReviewResult.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: application/json
- **Accept**: application/json

<a name="reviewModernizationRecommendation"></a>
# **reviewModernizationRecommendation**
> ModernizationRecommendationReviewResult reviewModernizationRecommendation(id, ModernizationRecommendationReviewRequest)

Review Modernization Recommendation

### Parameters

|Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **id** | **UUID**|  | [default to null] |
| **ModernizationRecommendationReviewRequest** | [**ModernizationRecommendationReviewRequest**](../Models/ModernizationRecommendationReviewRequest.md)|  | |

### Return type

[**ModernizationRecommendationReviewResult**](../Models/ModernizationRecommendationReviewResult.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: application/json
- **Accept**: application/json

