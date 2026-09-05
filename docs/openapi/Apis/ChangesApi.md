# ChangesApi

All URIs are relative to */api/v1*

| Method | HTTP request | Description |
|------------- | ------------- | -------------|
| [**cancelSimulation**](ChangesApi.md#cancelSimulation) | **DELETE** /simulations/{id} | Cancel Simulation |
| [**compileMutation**](ChangesApi.md#compileMutation) | **POST** /mutations/compile | Compile Mutation |
| [**createSimulation**](ChangesApi.md#createSimulation) | **POST** /simulations | Create Simulation |
| [**getSimulation**](ChangesApi.md#getSimulation) | **GET** /simulations/{id} | Get Simulation |
| [**listActionSubjects**](ChangesApi.md#listActionSubjects) | **GET** /action-types/{predicate}/subjects | List Action Subjects |
| [**listActionTypes**](ChangesApi.md#listActionTypes) | **GET** /action-types | List Action Types |
| [**listChangeScopes**](ChangesApi.md#listChangeScopes) | **GET** /entities/{id}/scopes | List Change Scopes |
| [**listValidTargets**](ChangesApi.md#listValidTargets) | **GET** /entities/{id}/valid-targets | List Valid Targets |
| [**validateMutation**](ChangesApi.md#validateMutation) | **POST** /mutations/validate | Validate Mutation |


<a name="cancelSimulation"></a>
# **cancelSimulation**
> SimulationRunModel cancelSimulation(id)

Cancel Simulation

### Parameters

|Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **id** | **UUID**|  | [default to null] |

### Return type

[**SimulationRunModel**](../Models/SimulationRunModel.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: application/json

<a name="compileMutation"></a>
# **compileMutation**
> MutationCompileResult compileMutation(MutationCompileRequest)

Compile Mutation

### Parameters

|Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **MutationCompileRequest** | [**MutationCompileRequest**](../Models/MutationCompileRequest.md)|  | |

### Return type

[**MutationCompileResult**](../Models/MutationCompileResult.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: application/json
- **Accept**: application/json

<a name="createSimulation"></a>
# **createSimulation**
> SimulationRunModel createSimulation(SimulationCreateRequest)

Create Simulation

### Parameters

|Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **SimulationCreateRequest** | [**SimulationCreateRequest**](../Models/SimulationCreateRequest.md)|  | |

### Return type

[**SimulationRunModel**](../Models/SimulationRunModel.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: application/json
- **Accept**: application/json

<a name="getSimulation"></a>
# **getSimulation**
> SimulationRunModel getSimulation(id)

Get Simulation

### Parameters

|Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **id** | **UUID**|  | [default to null] |

### Return type

[**SimulationRunModel**](../Models/SimulationRunModel.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: application/json

<a name="listActionSubjects"></a>
# **listActionSubjects**
> ActionSubjectList listActionSubjects(predicate, query, limit)

List Action Subjects

### Parameters

|Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **predicate** | **String**|  | [default to null] [enum: UPGRADE, REPLACE, REMOVE, DEPRECATE, MIGRATE, MOVE] |
| **query** | **String**|  | [optional] [default to null] |
| **limit** | **Integer**|  | [optional] [default to 25] |

### Return type

[**ActionSubjectList**](../Models/ActionSubjectList.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: application/json

<a name="listActionTypes"></a>
# **listActionTypes**
> ActionTypeList listActionTypes()

List Action Types

### Parameters
This endpoint does not need any parameter.

### Return type

[**ActionTypeList**](../Models/ActionTypeList.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: application/json

<a name="listChangeScopes"></a>
# **listChangeScopes**
> ChangeScopeList listChangeScopes(id)

List Change Scopes

### Parameters

|Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **id** | **UUID**|  | [default to null] |

### Return type

[**ChangeScopeList**](../Models/ChangeScopeList.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: application/json

<a name="listValidTargets"></a>
# **listValidTargets**
> ValidTargetList listValidTargets(id, limit)

List Valid Targets

### Parameters

|Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **id** | **UUID**|  | [default to null] |
| **limit** | **Integer**|  | [optional] [default to 50] |

### Return type

[**ValidTargetList**](../Models/ValidTargetList.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: application/json

<a name="validateMutation"></a>
# **validateMutation**
> MutationCompileResult validateMutation(MutationValidateRequest)

Validate Mutation

### Parameters

|Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **MutationValidateRequest** | [**MutationValidateRequest**](../Models/MutationValidateRequest.md)|  | |

### Return type

[**MutationCompileResult**](../Models/MutationCompileResult.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: application/json
- **Accept**: application/json

