# RepositoriesApi

All URIs are relative to */api/v1*

| Method | HTTP request | Description |
|------------- | ------------- | -------------|
| [**getRepository**](RepositoriesApi.md#getRepository) | **GET** /repositories/{id} | Get Repository |
| [**getRepositoryActivity**](RepositoriesApi.md#getRepositoryActivity) | **GET** /repositories/{id}/activity | Get Repository Activity |
| [**updateRepository**](RepositoriesApi.md#updateRepository) | **PUT** /repositories/{id} | Update Repository |


<a name="getRepository"></a>
# **getRepository**
> RepositoryDetail getRepository(id)

Get Repository

### Parameters

|Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **id** | **UUID**|  | [default to null] |

### Return type

[**RepositoryDetail**](../Models/RepositoryDetail.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: application/json

<a name="getRepositoryActivity"></a>
# **getRepositoryActivity**
> RepositoryActivity getRepositoryActivity(id, window, cursor, limit)

Get Repository Activity

### Parameters

|Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **id** | **UUID**|  | [default to null] |
| **window** | **String**|  | [optional] [default to 30d] [enum: 7d, 30d, 90d] |
| **cursor** | **String**|  | [optional] [default to null] |
| **limit** | **Integer**|  | [optional] [default to 10] |

### Return type

[**RepositoryActivity**](../Models/RepositoryActivity.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: application/json

<a name="updateRepository"></a>
# **updateRepository**
> EntitySummary updateRepository(id, EntityDescriptionUpdateRequest)

Update Repository

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

