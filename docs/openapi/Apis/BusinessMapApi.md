# BusinessMapApi

All URIs are relative to */api/v1*

| Method | HTTP request | Description |
|------------- | ------------- | -------------|
| [**archiveBusinessMap**](BusinessMapApi.md#archiveBusinessMap) | **DELETE** /business-maps/{id} | Archive Business Map |
| [**createBusinessMap**](BusinessMapApi.md#createBusinessMap) | **POST** /business-maps | Create Business Map |
| [**getBusinessMap**](BusinessMapApi.md#getBusinessMap) | **GET** /business-maps/{id} | Get Business Map |
| [**listBusinessMapRevisions**](BusinessMapApi.md#listBusinessMapRevisions) | **GET** /business-maps/{id}/revisions | List Business Map Revisions |
| [**listBusinessMaps**](BusinessMapApi.md#listBusinessMaps) | **GET** /business-maps | List Business Maps |
| [**saveBusinessMap**](BusinessMapApi.md#saveBusinessMap) | **PUT** /business-maps/{id} | Save Business Map |


<a name="archiveBusinessMap"></a>
# **archiveBusinessMap**
> BusinessMapSummary archiveBusinessMap(id)

Archive Business Map

### Parameters

|Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **id** | **UUID**|  | [default to null] |

### Return type

[**BusinessMapSummary**](../Models/BusinessMapSummary.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: application/json

<a name="createBusinessMap"></a>
# **createBusinessMap**
> BusinessMapDetail createBusinessMap(BusinessMapCreateRequest)

Create Business Map

### Parameters

|Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **BusinessMapCreateRequest** | [**BusinessMapCreateRequest**](../Models/BusinessMapCreateRequest.md)|  | |

### Return type

[**BusinessMapDetail**](../Models/BusinessMapDetail.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: application/json
- **Accept**: application/json

<a name="getBusinessMap"></a>
# **getBusinessMap**
> BusinessMapDetail getBusinessMap(id)

Get Business Map

### Parameters

|Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **id** | **UUID**|  | [default to null] |

### Return type

[**BusinessMapDetail**](../Models/BusinessMapDetail.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: application/json

<a name="listBusinessMapRevisions"></a>
# **listBusinessMapRevisions**
> BusinessMapRevisionList listBusinessMapRevisions(id)

List Business Map Revisions

### Parameters

|Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **id** | **UUID**|  | [default to null] |

### Return type

[**BusinessMapRevisionList**](../Models/BusinessMapRevisionList.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: application/json

<a name="listBusinessMaps"></a>
# **listBusinessMaps**
> BusinessMapList listBusinessMaps(cursor, limit)

List Business Maps

### Parameters

|Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **cursor** | **String**|  | [optional] [default to null] |
| **limit** | **Integer**|  | [optional] [default to 50] |

### Return type

[**BusinessMapList**](../Models/BusinessMapList.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: application/json

<a name="saveBusinessMap"></a>
# **saveBusinessMap**
> BusinessMapDetail saveBusinessMap(id, BusinessMapSaveRequest)

Save Business Map

### Parameters

|Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **id** | **UUID**|  | [default to null] |
| **BusinessMapSaveRequest** | [**BusinessMapSaveRequest**](../Models/BusinessMapSaveRequest.md)|  | |

### Return type

[**BusinessMapDetail**](../Models/BusinessMapDetail.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: application/json
- **Accept**: application/json

