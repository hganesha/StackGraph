# AuthenticationApi

All URIs are relative to */api/v1*

| Method | HTTP request | Description |
|------------- | ------------- | -------------|
| [**callbackAuthCallbackGet**](AuthenticationApi.md#callbackAuthCallbackGet) | **GET** /auth/callback | Callback |
| [**loginAuthLoginGet**](AuthenticationApi.md#loginAuthLoginGet) | **GET** /auth/login | Login |
| [**logoutAuthLogoutPost**](AuthenticationApi.md#logoutAuthLogoutPost) | **POST** /auth/logout | Logout |
| [**refreshAuthRefreshPost**](AuthenticationApi.md#refreshAuthRefreshPost) | **POST** /auth/refresh | Refresh |


<a name="callbackAuthCallbackGet"></a>
# **callbackAuthCallbackGet**
> oas_any_type_not_mapped callbackAuthCallbackGet(code, state)

Callback

### Parameters

|Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **code** | **String**|  | [default to null] |
| **state** | **String**|  | [default to null] |

### Return type

[**oas_any_type_not_mapped**](../Models/AnyType.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: application/json

<a name="loginAuthLoginGet"></a>
# **loginAuthLoginGet**
> oas_any_type_not_mapped loginAuthLoginGet(return\_to)

Login

### Parameters

|Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **return\_to** | **String**|  | [optional] [default to null] |

### Return type

[**oas_any_type_not_mapped**](../Models/AnyType.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: application/json

<a name="logoutAuthLogoutPost"></a>
# **logoutAuthLogoutPost**
> oas_any_type_not_mapped logoutAuthLogoutPost()

Logout

### Parameters
This endpoint does not need any parameter.

### Return type

[**oas_any_type_not_mapped**](../Models/AnyType.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: application/json

<a name="refreshAuthRefreshPost"></a>
# **refreshAuthRefreshPost**
> oas_any_type_not_mapped refreshAuthRefreshPost()

Refresh

### Parameters
This endpoint does not need any parameter.

### Return type

[**oas_any_type_not_mapped**](../Models/AnyType.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: application/json

