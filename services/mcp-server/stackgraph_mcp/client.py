"""Async HTTP client that invokes StackGraph API operations."""

from __future__ import annotations

from types import TracebackType
from typing import Any
from urllib.parse import quote

import httpx

from .config import Settings
from .spec import Operation
from . import __version__

BODY_KEYS = ("body", "request_body")


def _query_value(value: Any) -> Any:
    """Render one argument as an httpx query value, keeping lists as repeated params."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, tuple)):
        return [_query_value(item) for item in value]
    return value


class StackGraphClient:
    """Calls contract operations against a StackGraph deployment.

    The client is transport-only: it maps validated tool arguments onto a request and
    returns the decoded response. Argument validation lives in the server layer and
    error formatting in :mod:`stackgraph_mcp.errors`.
    """

    def __init__(self, settings: Settings, *, base_url: str, transport: httpx.AsyncBaseTransport | None = None) -> None:
        headers = {
            "Accept": "application/json",
            "User-Agent": f"stackgraph-mcp/{__version__}",
        }
        if settings.api_token:
            headers["Authorization"] = f"Bearer {settings.api_token}"
        cookies = {"stackgraph_session": settings.session_cookie} if settings.session_cookie else None

        self._base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers=headers,
            cookies=cookies,
            timeout=settings.timeout_seconds,
            verify=settings.verify_tls,
            follow_redirects=True,
            transport=transport,
        )

    @property
    def base_url(self) -> str:
        return self._base_url

    async def __aenter__(self) -> StackGraphClient:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        """Close the underlying connection pool."""
        await self._client.aclose()

    def build_path(self, operation: Operation, arguments: dict[str, Any]) -> str:
        """Substitute path parameters into the operation template.

        Args:
            operation: The operation being invoked.
            arguments: Validated tool arguments.

        Returns:
            str: The concrete request path (e.g. "/entities/9f1.../similar").

        Raises:
            KeyError: If a required path parameter is absent from ``arguments``.
        """
        path = operation.path
        for parameter in operation.path_parameters:
            value = arguments[parameter.name]
            path = path.replace(f"{{{parameter.name}}}", quote(str(value), safe=""))
        return path

    def build_query(self, operation: Operation, arguments: dict[str, Any]) -> dict[str, Any]:
        """Collect the query parameters present in ``arguments``, dropping nulls."""
        query: dict[str, Any] = {}
        for parameter in operation.query_parameters:
            if parameter.name not in arguments:
                continue
            value = arguments[parameter.name]
            if value is None:
                continue
            query[parameter.name] = _query_value(value)
        return query

    async def call(self, operation: Operation, arguments: dict[str, Any]) -> tuple[str, httpx.Response]:
        """Invoke one operation.

        Args:
            operation: The operation to invoke.
            arguments: Tool arguments already validated against the operation schema.

        Returns:
            tuple[str, httpx.Response]: The concrete path called (for error messages) and
            the response, which has already been checked for a non-2xx status.

        Raises:
            httpx.HTTPStatusError: If the API returned a non-2xx status.
            httpx.HTTPError: If the request could not be completed.
        """
        path = self.build_path(operation, arguments)
        body = next((arguments[key] for key in BODY_KEYS if key in arguments), None)

        response = await self._client.request(
            operation.method,
            path,
            params=self.build_query(operation, arguments) or None,
            json=body,
        )
        response.raise_for_status()
        return path, response
