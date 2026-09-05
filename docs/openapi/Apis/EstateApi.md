# EstateApi

All URIs are relative to */api/v1*

| Method | HTTP request | Description |
|------------- | ------------- | -------------|
| [**getEstateSummary**](EstateApi.md#getEstateSummary) | **GET** /estate/summary | Get Estate Summary |


<a name="getEstateSummary"></a>
# **getEstateSummary**
> EstateSummary getEstateSummary(cursor, limit, domain, sort)

Get Estate Summary

### Parameters

|Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **cursor** | **String**|  | [optional] [default to null] |
| **limit** | **Integer**|  | [optional] [default to 50] |
| **domain** | [**List**](../Models/String.md)|  | [optional] [default to null] [enum: BUSINESS, ENTERPRISE, TECHNOLOGY, OSS, DEPLOYMENT, INTELLIGENCE] |
| **sort** | **String**|  | [optional] [default to priority] [enum: priority, systemic_risk, upstream_impact, dependency_depth] |

### Return type

[**EstateSummary**](../Models/EstateSummary.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: application/json

