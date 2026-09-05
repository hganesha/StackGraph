# ApplicationsApi

All URIs are relative to */api/v1*

| Method | HTTP request | Description |
|------------- | ------------- | -------------|
| [**getApplication**](ApplicationsApi.md#getApplication) | **GET** /applications/{id} | Get Application |
| [**updateApplication**](ApplicationsApi.md#updateApplication) | **PUT** /applications/{id} | Update Application |


<a name="getApplication"></a>
# **getApplication**
> ApplicationDetail getApplication(id)

Get Application

### Parameters

|Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **id** | **UUID**|  | [default to null] |

### Return type

[**ApplicationDetail**](../Models/ApplicationDetail.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: application/json

<a name="updateApplication"></a>
# **updateApplication**
> EntitySummary updateApplication(id, EntityDescriptionUpdateRequest)

Update Application

### Parameters

|Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **id** | **UUID**|  | [default to null] |
| **EntityDescriptionUpdateRequest** | [**EntityDescriptionUpdateRequest**](../Models/EntityDescriptionUpdateRequest.md)|  | |

### Return type

[**EntitySummary**](../Models/EntitySummary.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: application/json
- **Accept**: application/json

