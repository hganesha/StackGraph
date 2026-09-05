# GraphApi

All URIs are relative to */api/v1*

| Method | HTTP request | Description |
|------------- | ------------- | -------------|
| [**getGraphNeighborhood**](GraphApi.md#getGraphNeighborhood) | **GET** /graph/neighborhood | Get Graph Neighborhood |


<a name="getGraphNeighborhood"></a>
# **getGraphNeighborhood**
> GraphNeighborhood getGraphNeighborhood(center\_id, depth, real\_node\_limit, predicate, namespace, min\_confidence, highlight\_to)

Get Graph Neighborhood

### Parameters

|Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **center\_id** | **UUID**|  | [default to null] |
| **depth** | **Integer**|  | [optional] [default to 1] |
| **real\_node\_limit** | **Integer**|  | [optional] [default to 50] |
| **predicate** | [**List**](../Models/String.md)|  | [optional] [default to null] |
| **namespace** | [**List**](../Models/String.md)|  | [optional] [default to null] [enum: BUSINESS, ENTERPRISE, TECHNOLOGY, OSS, DEPLOYMENT, INTELLIGENCE] |
| **min\_confidence** | **BigDecimal**|  | [optional] [default to 0] |
| **highlight\_to** | **UUID**|  | [optional] [default to null] |

### Return type

[**GraphNeighborhood**](../Models/GraphNeighborhood.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: application/json

