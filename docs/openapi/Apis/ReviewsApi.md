# ReviewsApi

All URIs are relative to */api/v1*

| Method | HTTP request | Description |
|------------- | ------------- | -------------|
| [**getReviewQueue**](ReviewsApi.md#getReviewQueue) | **GET** /reviews/queue | Get Review Queue |


<a name="getReviewQueue"></a>
# **getReviewQueue**
> ReviewQueue getReviewQueue(type, repository, cursor, limit)

Get Review Queue

### Parameters

|Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **type** | [**List**](../Models/String.md)|  | [optional] [default to null] [enum: IDENTITY_ASSERTION, CAPABILITY_INFERENCE, DUPLICATE_CAPABILITY, MODERNIZATION_CANDIDATE, MODERNIZATION_RECOMMENDATION, APPLICATION_SIMILARITY] |
| **repository** | **UUID**|  | [optional] [default to null] |
| **cursor** | **String**|  | [optional] [default to null] |
| **limit** | **Integer**|  | [optional] [default to 50] |

### Return type

[**ReviewQueue**](../Models/ReviewQueue.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: application/json

