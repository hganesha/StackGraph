# IdentityApi

All URIs are relative to */api/v1*

| Method | HTTP request | Description |
|------------- | ------------- | -------------|
| [**reviewIdentityAssertion**](IdentityApi.md#reviewIdentityAssertion) | **POST** /identity-assertions/{id}/review | Review Identity Assertion |


<a name="reviewIdentityAssertion"></a>
# **reviewIdentityAssertion**
> IdentityReviewResult reviewIdentityAssertion(id, IdentityReviewRequest)

Review Identity Assertion

### Parameters

|Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **id** | **UUID**|  | [default to null] |
| **IdentityReviewRequest** | [**IdentityReviewRequest**](../Models/IdentityReviewRequest.md)|  | |

### Return type

[**IdentityReviewResult**](../Models/IdentityReviewResult.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: application/json
- **Accept**: application/json

