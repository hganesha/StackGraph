# TechnologiesApi

All URIs are relative to */api/v1*

| Method | HTTP request | Description |
|------------- | ------------- | -------------|
| [**getTechnology**](TechnologiesApi.md#getTechnology) | **GET** /technologies/{id} | Get Technology |
| [**getTechnologyEstateHierarchy**](TechnologiesApi.md#getTechnologyEstateHierarchy) | **GET** /technologies/hierarchy | Get Technology Estate Hierarchy |


<a name="getTechnology"></a>
# **getTechnology**
> TechnologyDetail getTechnology(id)

Get Technology

### Parameters

|Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **id** | **UUID**|  | [default to null] |

### Return type

[**TechnologyDetail**](../Models/TechnologyDetail.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: application/json

<a name="getTechnologyEstateHierarchy"></a>
# **getTechnologyEstateHierarchy**
> TechnologyEstateHierarchy getTechnologyEstateHierarchy()

Get Technology Estate Hierarchy

### Parameters
This endpoint does not need any parameter.

### Return type

[**TechnologyEstateHierarchy**](../Models/TechnologyEstateHierarchy.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: application/json

