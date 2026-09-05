# GraphIntelligenceApi

All URIs are relative to */api/v1*

| Method | HTTP request | Description |
|------------- | ------------- | -------------|
| [**getEntityBlastRadius**](GraphIntelligenceApi.md#getEntityBlastRadius) | **GET** /entities/{id}/blast-radius | Get Entity Blast Radius |
| [**getEntityGraphMetrics**](GraphIntelligenceApi.md#getEntityGraphMetrics) | **GET** /entities/{id}/graph-metrics | Get Entity Graph Metrics |
| [**getGraphIntelligenceStatus**](GraphIntelligenceApi.md#getGraphIntelligenceStatus) | **GET** /graph-intelligence/status | Get Graph Intelligence Status |
| [**listEntityCriticalEdges**](GraphIntelligenceApi.md#listEntityCriticalEdges) | **GET** /entities/{id}/critical-edges | List Entity Critical Edges |
| [**listGraphIntelligenceAnomalies**](GraphIntelligenceApi.md#listGraphIntelligenceAnomalies) | **GET** /graph-intelligence/anomalies | List Graph Intelligence Anomalies |
| [**listGraphIntelligenceCommunities**](GraphIntelligenceApi.md#listGraphIntelligenceCommunities) | **GET** /graph-intelligence/communities | List Graph Intelligence Communities |
| [**listGraphIntelligenceMotifs**](GraphIntelligenceApi.md#listGraphIntelligenceMotifs) | **GET** /graph-intelligence/motifs | List Graph Intelligence Motifs |
| [**listGraphIntelligenceRisks**](GraphIntelligenceApi.md#listGraphIntelligenceRisks) | **GET** /graph-intelligence/risks | List Graph Intelligence Risks |
| [**requestGraphAnalysis**](GraphIntelligenceApi.md#requestGraphAnalysis) | **POST** /graph-intelligence/analysis-requests | Request Graph Analysis |


<a name="getEntityBlastRadius"></a>
# **getEntityBlastRadius**
> GraphBlastRadius getEntityBlastRadius(id)

Get Entity Blast Radius

### Parameters

|Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **id** | **UUID**|  | [default to null] |

### Return type

[**GraphBlastRadius**](../Models/GraphBlastRadius.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: application/json

<a name="getEntityGraphMetrics"></a>
# **getEntityGraphMetrics**
> EntityGraphIntelligence getEntityGraphMetrics(id)

Get Entity Graph Metrics

### Parameters

|Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **id** | **UUID**|  | [default to null] |

### Return type

[**EntityGraphIntelligence**](../Models/EntityGraphIntelligence.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: application/json

<a name="getGraphIntelligenceStatus"></a>
# **getGraphIntelligenceStatus**
> GraphIntelligenceStatus getGraphIntelligenceStatus()

Get Graph Intelligence Status

### Parameters
This endpoint does not need any parameter.

### Return type

[**GraphIntelligenceStatus**](../Models/GraphIntelligenceStatus.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: application/json

<a name="listEntityCriticalEdges"></a>
# **listEntityCriticalEdges**
> CriticalGraphEdgeList listEntityCriticalEdges(id)

List Entity Critical Edges

### Parameters

|Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **id** | **UUID**|  | [default to null] |

### Return type

[**CriticalGraphEdgeList**](../Models/CriticalGraphEdgeList.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: application/json

<a name="listGraphIntelligenceAnomalies"></a>
# **listGraphIntelligenceAnomalies**
> GraphAnomalyList listGraphIntelligenceAnomalies(cohort\_key, limit)

List Graph Intelligence Anomalies

### Parameters

|Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **cohort\_key** | **String**|  | [optional] [default to null] |
| **limit** | **Integer**|  | [optional] [default to 50] |

### Return type

[**GraphAnomalyList**](../Models/GraphAnomalyList.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: application/json

<a name="listGraphIntelligenceCommunities"></a>
# **listGraphIntelligenceCommunities**
> GraphCommunityList listGraphIntelligenceCommunities(policy\_key, limit)

List Graph Intelligence Communities

### Parameters

|Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **policy\_key** | **String**|  | [optional] [default to runtime-dependency] |
| **limit** | **Integer**|  | [optional] [default to 50] |

### Return type

[**GraphCommunityList**](../Models/GraphCommunityList.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: application/json

<a name="listGraphIntelligenceMotifs"></a>
# **listGraphIntelligenceMotifs**
> GraphMotifList listGraphIntelligenceMotifs(motif\_key, limit)

List Graph Intelligence Motifs

### Parameters

|Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **motif\_key** | **String**|  | [optional] [default to null] |
| **limit** | **Integer**|  | [optional] [default to 50] |

### Return type

[**GraphMotifList**](../Models/GraphMotifList.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: application/json

<a name="listGraphIntelligenceRisks"></a>
# **listGraphIntelligenceRisks**
> GraphRiskList listGraphIntelligenceRisks(entity\_type, namespace, community\_key, min\_score, cursor, limit)

List Graph Intelligence Risks

### Parameters

|Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **entity\_type** | **String**|  | [optional] [default to null] |
| **namespace** | **String**|  | [optional] [default to null] [enum: BUSINESS, ENTERPRISE, TECHNOLOGY, OSS, DEPLOYMENT, INTELLIGENCE] |
| **community\_key** | **String**|  | [optional] [default to null] |
| **min\_score** | **BigDecimal**|  | [optional] [default to 0] |
| **cursor** | **String**|  | [optional] [default to null] |
| **limit** | **Integer**|  | [optional] [default to 20] |

### Return type

[**GraphRiskList**](../Models/GraphRiskList.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: application/json

<a name="requestGraphAnalysis"></a>
# **requestGraphAnalysis**
> GraphAnalysisRequestResult requestGraphAnalysis(GraphAnalysisRequestCreate)

Request Graph Analysis

### Parameters

|Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **GraphAnalysisRequestCreate** | [**GraphAnalysisRequestCreate**](../Models/GraphAnalysisRequestCreate.md)|  | |

### Return type

[**GraphAnalysisRequestResult**](../Models/GraphAnalysisRequestResult.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: application/json
- **Accept**: application/json

