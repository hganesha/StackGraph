# ArchitectureCanvasApi

All URIs are relative to */api/v1*

| Method | HTTP request | Description |
|------------- | ------------- | -------------|
| [**compareCanvasProjections**](ArchitectureCanvasApi.md#compareCanvasProjections) | **POST** /canvas/comparisons | Compare Canvas Projections |
| [**getArchitectureReferenceModel**](ArchitectureCanvasApi.md#getArchitectureReferenceModel) | **GET** /canvas/reference-models/{key} | Get Architecture Reference Model |
| [**getArchitectureTaxonomy**](ArchitectureCanvasApi.md#getArchitectureTaxonomy) | **GET** /canvas/taxonomy | Get Architecture Taxonomy |
| [**getCanvasProjection**](ArchitectureCanvasApi.md#getCanvasProjection) | **GET** /canvas/projection | Get Canvas Projection |
| [**getCanvasTemplate**](ArchitectureCanvasApi.md#getCanvasTemplate) | **GET** /canvas/templates/{key} | Get Canvas Template |
| [**getTargetCanvasProjection**](ArchitectureCanvasApi.md#getTargetCanvasProjection) | **GET** /canvas/target-projection | Get Target Canvas Projection |
| [**listArchitectureReferenceModels**](ArchitectureCanvasApi.md#listArchitectureReferenceModels) | **GET** /canvas/reference-models | List Architecture Reference Models |
| [**listCanvasTemplates**](ArchitectureCanvasApi.md#listCanvasTemplates) | **GET** /canvas/templates | List Canvas Templates |


<a name="compareCanvasProjections"></a>
# **compareCanvasProjections**
> CanvasComparison compareCanvasProjections(CanvasComparisonRequest)

Compare Canvas Projections

### Parameters

|Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **CanvasComparisonRequest** | [**CanvasComparisonRequest**](../Models/CanvasComparisonRequest.md)|  | |

### Return type

[**CanvasComparison**](../Models/CanvasComparison.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: application/json
- **Accept**: application/json

<a name="getArchitectureReferenceModel"></a>
# **getArchitectureReferenceModel**
> ArchitectureReferenceModel getArchitectureReferenceModel(key, version)

Get Architecture Reference Model

### Parameters

|Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **key** | **String**|  | [default to null] |
| **version** | **String**|  | [optional] [default to null] |

### Return type

[**ArchitectureReferenceModel**](../Models/ArchitectureReferenceModel.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: application/json

<a name="getArchitectureTaxonomy"></a>
# **getArchitectureTaxonomy**
> ArchitectureTaxonomyResponse getArchitectureTaxonomy()

Get Architecture Taxonomy

### Parameters
This endpoint does not need any parameter.

### Return type

[**ArchitectureTaxonomyResponse**](../Models/ArchitectureTaxonomyResponse.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: application/json

<a name="getCanvasProjection"></a>
# **getCanvasProjection**
> CanvasProjection getCanvasProjection(scope, subject\_id, reference\_model\_key, template\_key)

Get Canvas Projection

### Parameters

|Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **scope** | **String**|  | [optional] [default to ESTATE] [enum: ESTATE, APPLICATION, REPOSITORY, TARGET] |
| **subject\_id** | **UUID**|  | [optional] [default to null] |
| **reference\_model\_key** | **String**|  | [optional] [default to architecture.stackgraph.reference] |
| **template\_key** | **String**|  | [optional] [default to canvas.stackgraph.reference] |

### Return type

[**CanvasProjection**](../Models/CanvasProjection.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: application/json

<a name="getCanvasTemplate"></a>
# **getCanvasTemplate**
> CanvasTemplateModel getCanvasTemplate(key, version)

Get Canvas Template

### Parameters

|Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **key** | **String**|  | [default to null] |
| **version** | **String**|  | [optional] [default to null] |

### Return type

[**CanvasTemplateModel**](../Models/CanvasTemplateModel.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: application/json

<a name="getTargetCanvasProjection"></a>
# **getTargetCanvasProjection**
> CanvasProjection getTargetCanvasProjection(reference\_model\_key, template\_key)

Get Target Canvas Projection

### Parameters

|Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **reference\_model\_key** | **String**|  | [optional] [default to architecture.stackgraph.reference] |
| **template\_key** | **String**|  | [optional] [default to canvas.stackgraph.reference] |

### Return type

[**CanvasProjection**](../Models/CanvasProjection.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: application/json

<a name="listArchitectureReferenceModels"></a>
# **listArchitectureReferenceModels**
> ArchitectureReferenceModelList listArchitectureReferenceModels()

List Architecture Reference Models

### Parameters
This endpoint does not need any parameter.

### Return type

[**ArchitectureReferenceModelList**](../Models/ArchitectureReferenceModelList.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: application/json

<a name="listCanvasTemplates"></a>
# **listCanvasTemplates**
> CanvasTemplateList listCanvasTemplates()

List Canvas Templates

### Parameters
This endpoint does not need any parameter.

### Return type

[**CanvasTemplateList**](../Models/CanvasTemplateList.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: application/json

