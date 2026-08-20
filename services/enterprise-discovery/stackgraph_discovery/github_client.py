from __future__ import annotations

import json
import socket
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


JsonObject = dict[str, Any]


@dataclass(frozen=True, slots=True)
class HttpResponse:
    status: int
    headers: Mapping[str, str]
    body: bytes


class HttpTransport(Protocol):
    def request(
        self,
        url: str,
        headers: Mapping[str, str],
        timeout_seconds: float,
    ) -> HttpResponse: ...


class UrlLibTransport:
    def __init__(self) -> None:
        self._opener = build_opener(_SameOriginRedirectHandler())

    def request(
        self,
        url: str,
        headers: Mapping[str, str],
        timeout_seconds: float,
    ) -> HttpResponse:
        request = Request(url, headers=dict(headers), method="GET")
        try:
            with self._opener.open(request, timeout=timeout_seconds) as response:
                return HttpResponse(
                    status=response.status,
                    headers=dict(response.headers.items()),
                    body=response.read(),
                )
        except HTTPError as error:
            return HttpResponse(
                status=error.code,
                headers=dict(error.headers.items()) if error.headers else {},
                body=error.read(),
            )
        except (URLError, TimeoutError, socket.timeout) as error:
            reason = getattr(error, "reason", error)
            raise GitHubTransportError(f"GitHub request failed: {reason}") from error


class _SameOriginRedirectHandler(HTTPRedirectHandler):
    def redirect_request(
        self,
        request: Request,
        file_pointer: Any,
        code: int,
        message: str,
        headers: Mapping[str, str],
        new_url: str,
    ) -> Request | None:
        original = urlsplit(request.full_url)
        redirected = urlsplit(new_url)
        if (original.scheme, original.hostname, original.port) != (
            redirected.scheme,
            redirected.hostname,
            redirected.port,
        ):
            return None
        return super().redirect_request(
            request,
            file_pointer,
            code,
            message,
            headers,
            new_url,
        )


class GitHubTransportError(RuntimeError):
    """A retryable network-level failure before GitHub returned a response."""


class GitHubApiError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int,
        retriable: bool,
        retry_after_seconds: int | None = None,
        rate_limit_remaining: int | None = None,
        rate_limit_limit: int | None = None,
        rate_limit_reset: int | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retriable = retriable
        self.retry_after_seconds = retry_after_seconds
        self.rate_limit_remaining = rate_limit_remaining
        self.rate_limit_limit = rate_limit_limit
        self.rate_limit_reset = rate_limit_reset


@dataclass(frozen=True, slots=True)
class ApiResult:
    status: int
    headers: Mapping[str, str]
    data: JsonObject | None

    @property
    def etag(self) -> str | None:
        return self.headers.get("etag")

    @property
    def rate_limit_remaining(self) -> int | None:
        return _optional_int(self.headers.get("x-ratelimit-remaining"))

    @property
    def rate_limit_limit(self) -> int | None:
        return _optional_int(self.headers.get("x-ratelimit-limit"))

    @property
    def rate_limit_reset(self) -> int | None:
        return _optional_int(self.headers.get("x-ratelimit-reset"))


class GitHubClient:
    def __init__(
        self,
        *,
        token: str | None = None,
        base_url: str = "https://api.github.com",
        api_version: str = "2026-03-10",
        user_agent: str = "StackGraph-repository-acquisition/1.0",
        timeout_seconds: float = 20.0,
        transport: HttpTransport | None = None,
        allow_insecure_localhost: bool = False,
    ) -> None:
        _validate_base_url(base_url, allow_insecure_localhost)
        if not api_version:
            raise ValueError("api_version must not be empty")
        if not user_agent:
            raise ValueError("user_agent must not be empty")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")

        self._token = token.strip() if token else None
        self._base_url = base_url.rstrip("/")
        self._api_version = api_version
        self._user_agent = user_agent
        self._timeout_seconds = timeout_seconds
        self._transport = transport or UrlLibTransport()

    @property
    def api_version(self) -> str:
        return self._api_version

    @property
    def base_url(self) -> str:
        return self._base_url

    def get_json(
        self,
        path: str,
        *,
        query: Mapping[str, str] | None = None,
        etag: str | None = None,
    ) -> ApiResult:
        if not path.startswith("/") or path.startswith("//"):
            raise ValueError("GitHub API path must be root-relative")

        url = f"{self._base_url}{path}"
        if query:
            url = f"{url}?{urlencode(query)}"

        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": self._user_agent,
            "X-GitHub-Api-Version": self._api_version,
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        if etag:
            headers["If-None-Match"] = etag

        response = self._transport.request(url, headers, self._timeout_seconds)
        normalized_headers = {key.lower(): value for key, value in response.headers.items()}
        if response.status == 304:
            return ApiResult(status=304, headers=normalized_headers, data=None)
        if response.status < 200 or response.status >= 300:
            raise _api_error(response.status, normalized_headers, response.body)

        try:
            decoded = json.loads(response.body)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise GitHubApiError(
                "GitHub returned an invalid JSON response",
                status_code=response.status,
                retriable=False,
            ) from error
        if not isinstance(decoded, dict):
            raise GitHubApiError(
                "GitHub returned an unexpected JSON document",
                status_code=response.status,
                retriable=False,
            )
        return ApiResult(status=response.status, headers=normalized_headers, data=decoded)


def _validate_base_url(base_url: str, allow_insecure_localhost: bool) -> None:
    parsed = urlsplit(base_url)
    if parsed.query or parsed.fragment or parsed.username or parsed.password:
        raise ValueError("base_url must not contain credentials, query, or fragment")
    is_local = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    if parsed.scheme != "https" and not (
        allow_insecure_localhost and is_local and parsed.scheme == "http"
    ):
        raise ValueError("base_url must use HTTPS")
    if not parsed.hostname:
        raise ValueError("base_url must include a host")


def _api_error(status: int, headers: Mapping[str, str], body: bytes) -> GitHubApiError:
    message = f"GitHub API request failed with status {status}"
    try:
        document = json.loads(body)
        if isinstance(document, dict) and isinstance(document.get("message"), str):
            message = f"{message}: {document['message']}"
    except (UnicodeDecodeError, json.JSONDecodeError):
        pass

    remaining = _optional_int(headers.get("x-ratelimit-remaining"))
    limit = _optional_int(headers.get("x-ratelimit-limit"))
    retry_after = _optional_int(headers.get("retry-after"))
    reset = _optional_int(headers.get("x-ratelimit-reset"))
    rate_limited = status == 429 or (
        status == 403
        and (
            remaining == 0
            or retry_after is not None
            or "secondary rate limit" in message.lower()
        )
    )
    return GitHubApiError(
        message,
        status_code=status,
        retriable=rate_limited or status >= 500,
        retry_after_seconds=retry_after,
        rate_limit_remaining=remaining,
        rate_limit_limit=limit,
        rate_limit_reset=reset,
    )


def _optional_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
