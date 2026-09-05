# EmbeddingsApi

All URIs are relative to */api/v1*

| Method | HTTP request | Description |
|------------- | ------------- | -------------|
| [**getEmbeddingStatus**](EmbeddingsApi.md#getEmbeddingStatus) | **GET** /embeddings/status | Get Embedding Status |
| [**listSimilarApplications**](EmbeddingsApi.md#listSimilarApplications) | **GET** /entities/{id}/similar | List Similar Applications |
| [**promoteEmbeddingSpace**](EmbeddingsApi.md#promoteEmbeddingSpace) | **POST** /embedding-spaces/{id}/promotion | Promote Embedding Space |
| [**requestEmbeddingBackfill**](EmbeddingsApi.md#requestEmbeddingBackfill) | **POST** /embeddings/backfill | Request Embedding Backfill |
| [**reviewApplicationSimilarity**](EmbeddingsApi.md#reviewApplicationSimilarity) | **POST** /similarity-candidates/{id}/review | Review Application Similarity |
| [**semanticSearch**](EmbeddingsApi.md#semanticSearch) | **POST** /search/semantic | Semantic Search |


<a name="getEmbeddingStatus"></a>
# **getEmbeddingStatus**
> EmbeddingStatus getEmbeddingStatus()

Get Embedding Status

### Parameters
This endpoint does not need any parameter.

### Return type

[**EmbeddingStatus**](../Models/EmbeddingStatus.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: application/json

<a name="listSimilarApplications"></a>
# **listSimilarApplications**
> ApplicationSimilarityList listSimilarApplications(id, review\_state, cursor, limit)

List Similar Applications

### Parameters

|Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **id** | **UUID**|  | [default to null] |
| **review\_state** | **String**|  | [optional] [default to null] [enum: UNREVIEWED, CONFIRMED_SIMILAR, CONFIRMED_DISTINCT, CONSOLIDATION_CANDIDATE, DISMISSED] |
| **cursor** | **String**|  | [optional] [default to null] |
| **limit** | **Integer**|  | [optional] [default to 10] |

### Return type

[**ApplicationSimilarityList**](../Models/ApplicationSimilarityList.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: application/json

<a name="promoteEmbeddingSpace"></a>
# **promoteEmbeddingSpace**
> EmbeddingSpacePromotionResult promoteEmbeddingSpace(id, EmbeddingSpacePromotionRequest)

Promote Embedding Space

### Parameters

|Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **id** | **UUID**|  | [default to null] |
| **EmbeddingSpacePromotionRequest** | [**EmbeddingSpacePromotionRequest**](../Models/EmbeddingSpacePromotionRequest.md)|  | |

### Return type

[**EmbeddingSpacePromotionResult**](../Models/EmbeddingSpacePromotionResult.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: application/json
- **Accept**: application/json

<a name="requestEmbeddingBackfill"></a>
# **requestEmbeddingBackfill**
> EmbeddingBackfillResult requestEmbeddingBackfill(EmbeddingBackfillRequest)

Request Embedding Backfill

### Parameters

|Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **EmbeddingBackfillRequest** | [**EmbeddingBackfillRequest**](../Models/EmbeddingBackfillRequest.md)|  | |

### Return type

[**EmbeddingBackfillResult**](../Models/EmbeddingBackfillResult.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: application/json
- **Accept**: application/json

<a name="reviewApplicationSimilarity"></a>
# **reviewApplicationSimilarity**
> ApplicationSimilarityReviewResult reviewApplicationSimilarity(id, ApplicationSimilarityReviewRequest)

Review Application Similarity

### Parameters

|Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **id** | **UUID**|  | [default to null] |
| **ApplicationSimilarityReviewRequest** | [**ApplicationSimilarityReviewRequest**](../Models/ApplicationSimilarityReviewRequest.md)|  | |

### Return type

[**ApplicationSimilarityReviewResult**](../Models/ApplicationSimilarityReviewResult.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: application/json
- **Accept**: application/json

<a name="semanticSearch"></a>
# **semanticSearch**
> SemanticSearchResponse semanticSearch(SemanticSearchRequest)

Semantic Search

### Parameters

|Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **SemanticSearchRequest** | [**SemanticSearchRequest**](../Models/SemanticSearchRequest.md)|  | |

### Return type

[**SemanticSearchResponse**](../Models/SemanticSearchResponse.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: application/json
- **Accept**: application/json

