"""Error types and agent-facing error formatting."""

from __future__ import annotations

import json
from typing import Any

import httpx


class ConfigurationError(RuntimeError):
    """Raised when the server is started with unusable settings."""


class ToolInputError(ValueError):
    """Raised when tool arguments fail validation against the operation schema."""


class UnknownToolError(LookupError):
    """Raised when a client calls a tool this server does not expose."""


def _response_detail(response: httpx.Response) -> str:
    """Pull the most useful human-readable detail out of an API error body."""
    try:
        payload: Any = response.json()
    except (json.JSONDecodeError, ValueError):
        body = response.text.strip()
        return body[:500] if body else "<empty response body>"

    if isinstance(payload, dict):
        # The API returns {"error": {"code": ..., "message": ...}} for APIError and
        # {"detail": [...]} for FastAPI request validation failures.
        error = payload.get("error")
        if isinstance(error, dict):
            code = error.get("code")
            message = error.get("message")
            if code or message:
                return f"{code or 'ERROR'}: {message or ''}".strip().rstrip(":")
        detail = payload.get("detail")
        if detail is not None:
            return json.dumps(detail)[:500]
    return json.dumps(payload)[:500]


def format_http_error(exc: Exception, *, method: str, path: str) -> str:
    """Turn a transport or status error into a message that tells an agent what to do next.

    Args:
        exc: The exception raised while calling the StackGraph API.
        method: Upper-case HTTP method of the attempted call (e.g. "GET").
        path: Concrete request path of the attempted call (e.g. "/entities/abc/similar").

    Returns:
        str: A single-line ``Error: ...`` message naming the cause and the remedy.
    """
    where = f"{method} {path}"

    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        detail = _response_detail(exc.response)
        remedies = {
            400: "Check the argument values against the operation schema.",
            401: (
                "Authentication failed. Set STACKGRAPH_MCP_API_TOKEN to a valid bearer token "
                "(or STACKGRAPH_MCP_SESSION_COOKIE to a stackgraph_session cookie value)."
            ),
            403: (
                "The principal lacks the required capability. StackGraph capabilities escalate "
                "view -> review -> execute -> admin; admin/* operations need 'admin'."
            ),
            404: "No such resource. List the parent collection first to obtain a valid id.",
            409: "The resource changed concurrently. Re-read it and retry with the current revision.",
            422: "The request body or query failed validation. Re-read the schema and correct the fields.",
            429: "Rate limit exceeded. Wait for the window to reset before retrying.",
        }
        remedy = remedies.get(status)
        if remedy is None:
            remedy = (
                "The StackGraph API is failing. Check service health with stackgraph_health_ready."
                if status >= 500
                else "Check the request against the operation schema."
            )
        return f"Error: {where} failed with HTTP {status}. {detail} {remedy}"

    if isinstance(exc, httpx.TimeoutException):
        return (
            f"Error: {where} timed out. Retry, narrow the query (lower 'limit' or 'depth'), "
            "or raise STACKGRAPH_MCP_TIMEOUT_SECONDS."
        )

    if isinstance(exc, httpx.ConnectError):
        return (
            f"Error: cannot reach the StackGraph API for {where}. Confirm the service is running "
            "and that STACKGRAPH_MCP_API_BASE_URL points at it."
        )

    if isinstance(exc, httpx.HTTPError):
        return f"Error: {where} failed at the transport layer: {type(exc).__name__}: {exc}"

    return f"Error: {where} failed unexpectedly: {type(exc).__name__}: {exc}"
