from __future__ import annotations

import base64
import json
import os
import socket
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import UUID

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from .github_client import GitHubApiError, GitHubTransportError, HttpResponse
from .github_installation import validate_installation_id


API_VERSION = "2026-03-10"
DEFAULT_APP_ID_VARIABLE = "GITHUB_APP_ID"
DEFAULT_PRIVATE_KEY_VARIABLE = "GITHUB_APP_PRIVATE_KEY"
DEFAULT_PRIVATE_KEY_FILE_VARIABLE = "GITHUB_APP_PRIVATE_KEY_FILE"


class GitHubAppTransport(Protocol):
    def post(
        self,
        url: str,
        headers: Mapping[str, str],
        body: bytes,
        timeout_seconds: float,
    ) -> HttpResponse: ...


class UrlLibGitHubAppTransport:
    def __init__(self) -> None:
        self._opener = build_opener(_NoRedirectHandler())

    def post(
        self,
        url: str,
        headers: Mapping[str, str],
        body: bytes,
        timeout_seconds: float,
    ) -> HttpResponse:
        request = Request(url, headers=dict(headers), data=body, method="POST")
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
            raise GitHubTransportError(
                f"GitHub App token request failed: {reason}"
            ) from error


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, *_: Any, **__: Any) -> None:
        return None


@dataclass(frozen=True, slots=True)
class CachedInstallationToken:
    token: str
    expires_at: datetime


class GitHubAppTokenBroker:
    """Mint and cache short-lived GitHub App installation access tokens."""

    def __init__(
        self,
        *,
        base_url: str = "https://api.github.com",
        api_version: str = API_VERSION,
        timeout_seconds: float = 20.0,
        refresh_margin_seconds: int = 300,
        transport: GitHubAppTransport | None = None,
        clock: Callable[[], float] = time.time,
        allow_insecure_localhost: bool = False,
    ) -> None:
        _validate_base_url(base_url, allow_insecure_localhost)
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if refresh_margin_seconds < 0:
            raise ValueError("refresh_margin_seconds must not be negative")
        self._base_url = base_url.rstrip("/")
        self._api_version = api_version
        self._timeout_seconds = timeout_seconds
        self._refresh_margin_seconds = refresh_margin_seconds
        self._transport = transport or UrlLibGitHubAppTransport()
        self._clock = clock
        self._cache: dict[tuple[str, str], CachedInstallationToken] = {}

    def token(
        self,
        installation_id: str,
        *,
        app_id: str,
        private_key_pem: str,
    ) -> str:
        validate_installation_id(installation_id)
        normalized_app_id = _validate_app_id(app_id)
        now = self._clock()
        cache_key = (normalized_app_id, installation_id)
        cached = self._cache.get(cache_key)
        if cached is not None and cached.expires_at.timestamp() - now > self._refresh_margin_seconds:
            return cached.token

        app_jwt = create_app_jwt(
            normalized_app_id,
            private_key_pem,
            issued_at=int(now) - 60,
            expires_at=int(now) + 540,
        )
        url = f"{self._base_url}/app/installations/{installation_id}/access_tokens"
        response = self._transport.post(
            url,
            {
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {app_jwt}",
                "Content-Type": "application/json",
                "User-Agent": "StackGraph-github-app-token-broker/1.0",
                "X-GitHub-Api-Version": self._api_version,
            },
            b"{}",
            self._timeout_seconds,
        )
        normalized_headers = {key.lower(): value for key, value in response.headers.items()}
        if response.status < 200 or response.status >= 300:
            raise GitHubApiError(
                "GitHub rejected the installation token request",
                status_code=response.status,
                retriable=response.status == 429 or response.status >= 500,
                retry_after_seconds=_optional_int(normalized_headers.get("retry-after")),
                rate_limit_reset=_optional_int(normalized_headers.get("x-ratelimit-reset")),
            )
        try:
            document = json.loads(response.body)
            token = document["token"]
            expires_at = datetime.fromisoformat(document["expires_at"].replace("Z", "+00:00"))
        except (KeyError, TypeError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
            raise GitHubApiError(
                "GitHub returned an invalid installation token response",
                status_code=response.status,
                retriable=False,
            ) from error
        if not isinstance(token, str) or not token.strip() or expires_at.tzinfo is None:
            raise GitHubApiError(
                "GitHub returned an invalid installation token response",
                status_code=response.status,
                retriable=False,
            )
        cached = CachedInstallationToken(token=token.strip(), expires_at=expires_at.astimezone(UTC))
        self._cache[cache_key] = cached
        return cached.token


def create_app_jwt(
    app_id: str,
    private_key_pem: str,
    *,
    issued_at: int,
    expires_at: int,
) -> str:
    normalized_app_id = _validate_app_id(app_id)
    if expires_at <= issued_at or expires_at - issued_at > 600:
        raise ValueError("GitHub App JWT lifetime must be between 1 and 600 seconds")
    try:
        key = serialization.load_pem_private_key(private_key_pem.encode("utf-8"), password=None)
    except (TypeError, ValueError) as error:
        raise ValueError("GITHUB_APP_PRIVATE_KEY is not a valid unencrypted PEM key") from error
    if not isinstance(key, rsa.RSAPrivateKey):
        raise ValueError("GITHUB_APP_PRIVATE_KEY must contain an RSA private key")
    header = _base64url_json({"alg": "RS256", "typ": "JWT"})
    payload = _base64url_json({"iat": issued_at, "exp": expires_at, "iss": normalized_app_id})
    signing_input = f"{header}.{payload}".encode("ascii")
    signature = key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
    return f"{header}.{payload}.{_base64url(signature)}"


def resolve_runtime_credential(
    credential_reference: str,
    *,
    installation_id: str | None = None,
    environment: Mapping[str, str] | None = None,
    broker: GitHubAppTokenBroker | None = None,
    database_url: str | None = None,
    tenant_id: UUID | None = None,
    credential_encryption_key: str | None = None,
) -> str:
    from .github_installation_store import (
        resolve_environment_credential,
        resolve_tenant_secret_credential,
        validate_credential_reference,
    )

    validate_credential_reference(credential_reference)
    parsed = urlsplit(credential_reference)
    if parsed.scheme == "env":
        return resolve_environment_credential(credential_reference, environment)
    if parsed.scheme == "tenant-secret":
        if database_url is None or tenant_id is None or credential_encryption_key is None:
            raise ValueError("database URL, tenant ID, and encryption key are required for tenant secrets")
        return resolve_tenant_secret_credential(
            credential_reference,
            database_url=database_url,
            tenant_id=tenant_id,
            encryption_key=credential_encryption_key,
        )
    if parsed.scheme != "github-app":
        raise ValueError("this runtime can resolve only env:// or github-app:// references")
    if installation_id is None:
        raise ValueError("a GitHub installation ID is required for github-app:// credentials")
    validate_installation_id(installation_id)
    if parsed.netloc != "installation" or parsed.path.strip("/") not in {"", installation_id}:
        raise ValueError("github-app credential reference does not match the installation")
    source = environment if environment is not None else os.environ
    app_id = source.get(DEFAULT_APP_ID_VARIABLE, "").strip()
    private_key = source.get(DEFAULT_PRIVATE_KEY_VARIABLE, "")
    private_key_file = source.get(DEFAULT_PRIVATE_KEY_FILE_VARIABLE, "").strip()
    if not private_key and private_key_file:
        private_key = Path(private_key_file).read_text(encoding="utf-8")
    private_key = private_key.replace("\\n", "\n").strip()
    if not app_id:
        raise ValueError(f"{DEFAULT_APP_ID_VARIABLE} is required for github-app:// credentials")
    if not private_key:
        raise ValueError(
            f"{DEFAULT_PRIVATE_KEY_VARIABLE} or {DEFAULT_PRIVATE_KEY_FILE_VARIABLE} is required "
            "for github-app:// credentials"
        )
    active_broker = broker or _default_broker()
    return active_broker.token(
        installation_id,
        app_id=app_id,
        private_key_pem=private_key,
    )


_BROKERS: dict[tuple[str, bool], GitHubAppTokenBroker] = {}


def _default_broker() -> GitHubAppTokenBroker:
    base_url = os.getenv("STACKGRAPH_GITHUB_API_URL", "https://api.github.com")
    allow_local = os.getenv("STACKGRAPH_GITHUB_ALLOW_INSECURE_LOCALHOST") == "true"
    return _BROKERS.setdefault(
        (base_url, allow_local),
        GitHubAppTokenBroker(base_url=base_url, allow_insecure_localhost=allow_local),
    )


def _validate_app_id(app_id: str) -> str:
    normalized = app_id.strip()
    if not normalized or len(normalized) > 255 or any(character.isspace() for character in normalized):
        raise ValueError("GITHUB_APP_ID is invalid")
    return normalized


def _validate_base_url(base_url: str, allow_insecure_localhost: bool) -> None:
    parsed = urlsplit(base_url)
    if parsed.query or parsed.fragment or parsed.username or parsed.password or not parsed.hostname:
        raise ValueError("base_url must not contain credentials, query, or fragment")
    local = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    if parsed.scheme != "https" and not (allow_insecure_localhost and local and parsed.scheme == "http"):
        raise ValueError("base_url must use HTTPS")


def _base64url_json(value: Mapping[str, object]) -> str:
    return _base64url(json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8"))


def _base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _optional_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None
