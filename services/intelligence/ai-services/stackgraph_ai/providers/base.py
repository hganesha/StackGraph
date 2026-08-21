from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any

import httpx

from stackgraph_ai.errors import ProviderRequestError, ProviderResponseError


_JSON_FENCE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.IGNORECASE | re.DOTALL)


def provider_error_code(status_code: int) -> tuple[str, bool]:
    if status_code in {401, 403}:
        return "AUTH_FAILURE", False
    if status_code == 408:
        return "TIMEOUT", True
    if status_code == 409:
        return "CONFLICT", True
    if status_code == 429:
        return "RATE_LIMIT", True
    if status_code in {400, 404, 413, 422}:
        return "INVALID_REQUEST", False
    if status_code >= 500:
        return "PROVIDER_UNAVAILABLE", True
    return "PROVIDER_ERROR", False


def raise_for_provider_status(provider: str, response: httpx.Response) -> None:
    if response.is_success:
        return
    code, retryable = provider_error_code(response.status_code)
    try:
        payload = response.json()
    except json.JSONDecodeError:
        payload = None
    message = _error_message(payload) or response.text[:500] or response.reason_phrase
    raise ProviderRequestError(
        provider=provider,
        code=code,
        message=f"{provider} request failed ({response.status_code}): {message}",
        retryable=retryable,
        status_code=response.status_code,
    )


def _error_message(payload: Any) -> str | None:
    if not isinstance(payload, Mapping):
        return None
    error = payload.get("error")
    if isinstance(error, str):
        return error[:500]
    if isinstance(error, Mapping):
        message = error.get("message") or error.get("detail") or error.get("type")
        if message:
            return str(message)[:500]
    message = payload.get("message") or payload.get("detail")
    return str(message)[:500] if message else None


def json_mapping(value: Any, *, provider: str, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ProviderResponseError(f"{provider} returned an invalid {context}")
    return value


def parse_tool_arguments(value: Any, *, provider: str) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    if not isinstance(value, str):
        raise ProviderResponseError(f"{provider} returned non-object tool arguments")
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError as error:
        raise ProviderResponseError(f"{provider} returned malformed tool arguments") from error
    if not isinstance(decoded, Mapping):
        raise ProviderResponseError(f"{provider} returned non-object tool arguments")
    return decoded


def parse_structured_text(text: str | None, *, provider: str) -> Mapping[str, Any] | list[Any] | None:
    if text is None:
        return None
    stripped = text.strip()
    try:
        decoded = json.loads(stripped)
    except json.JSONDecodeError as direct_error:
        fenced = _JSON_FENCE.findall(stripped)
        if len(fenced) != 1:
            raise ProviderResponseError(
                f"{provider} returned malformed structured output "
                "(expected one JSON object or one fenced JSON block)"
            ) from direct_error
        try:
            decoded = json.loads(fenced[0].strip())
        except json.JSONDecodeError as fenced_error:
            raise ProviderResponseError(
                f"{provider} returned malformed JSON inside its structured-output fence"
            ) from fenced_error
    if not isinstance(decoded, (Mapping, list)):
        raise ProviderResponseError(f"{provider} structured output must be an object or array")
    return decoded


class HTTPProvider:
    def __init__(self, *, client: httpx.AsyncClient | None = None, timeout_seconds: float = 45) -> None:
        self._client = client
        self._timeout_seconds = timeout_seconds

    async def _post(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        payload: Mapping[str, Any],
    ) -> httpx.Response:
        try:
            if self._client is not None:
                return await self._client.post(url, headers=headers, json=payload)
            async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                return await client.post(url, headers=headers, json=payload)
        except httpx.TimeoutException as error:
            raise ProviderRequestError(
                provider=self.provider_name,
                code="TIMEOUT",
                message=f"{self.provider_name} request timed out",
                retryable=True,
            ) from error
        except httpx.HTTPError as error:
            raise ProviderRequestError(
                provider=self.provider_name,
                code="TRANSPORT_ERROR",
                message=f"{self.provider_name} transport error: {type(error).__name__}",
                retryable=True,
            ) from error
