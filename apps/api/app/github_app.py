from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlsplit

import httpx
import jwt

from app.config import Settings
from app.errors import APIError


@dataclass(frozen=True, slots=True)
class VerifiedGitHubInstallation:
    installation_id: str
    account_login: str
    account_id: int
    target_type: str
    permissions: tuple[str, ...]


class GitHubAppSetupClient:
    """Verify a hosted installation without persisting OAuth or installation tokens."""

    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.settings = settings
        self._transport = transport
        self._validate_base_url(settings.github_api_url, "GitHub API")
        self._validate_base_url(settings.github_web_url, "GitHub web")

    @property
    def enabled(self) -> bool:
        return self.settings.github_app_setup_enabled

    def installation_url(self, state: str) -> str:
        if not self.enabled:
            raise APIError(404, "GITHUB_APP_SETUP_DISABLED", "Hosted GitHub App setup is not enabled.")
        query = urlencode({"state": state})
        return (
            f"{self.settings.github_web_url.rstrip('/')}/apps/"
            f"{self.settings.github_app_slug}/installations/new?{query}"
        )

    async def verify_installation(
        self,
        *,
        code: str,
        installation_id: str,
    ) -> VerifiedGitHubInstallation:
        if not self.enabled:
            raise APIError(404, "GITHUB_APP_SETUP_DISABLED", "Hosted GitHub App setup is not enabled.")
        if not installation_id.isascii() or not installation_id.isdigit() or installation_id.startswith("0"):
            raise APIError(422, "GITHUB_INSTALLATION_INVALID", "GitHub returned an invalid installation ID.")
        if len(installation_id) > 20:
            raise APIError(422, "GITHUB_INSTALLATION_INVALID", "GitHub returned an invalid installation ID.")

        timeout = httpx.Timeout(15.0)
        try:
            async with httpx.AsyncClient(
                timeout=timeout,
                follow_redirects=False,
                transport=self._transport,
            ) as client:
                user_token = await self._exchange_user_code(client, code)
                await self._verify_user_installation(client, user_token, installation_id)
                app_jwt = self._app_jwt()
                installation = await self._load_app_installation(client, app_jwt, installation_id)
                await self._verify_installation_token(client, app_jwt, installation_id)
        except APIError:
            raise
        except httpx.HTTPError as error:
            raise APIError(
                502,
                "GITHUB_APP_UNAVAILABLE",
                "GitHub could not be reached while verifying the installation.",
            ) from error

        account = installation.get("account")
        permissions = installation.get("permissions")
        if not isinstance(account, dict) or not isinstance(permissions, dict):
            raise APIError(502, "GITHUB_INSTALLATION_INVALID", "GitHub returned invalid installation metadata.")
        account_login = account.get("login")
        account_id = account.get("id")
        target_type = installation.get("target_type")
        if (
            not isinstance(account_login, str)
            or not account_login
            or not isinstance(account_id, int)
            or not isinstance(target_type, str)
        ):
            raise APIError(502, "GITHUB_INSTALLATION_INVALID", "GitHub returned invalid installation metadata.")
        normalized_permissions = tuple(
            sorted(
                f"{name}:{level}"
                for name, level in permissions.items()
                if isinstance(name, str) and isinstance(level, str)
            )
        )
        if "contents:read" not in normalized_permissions or not any(
            permission.startswith("metadata:") for permission in normalized_permissions
        ):
            raise APIError(
                403,
                "GITHUB_APP_PERMISSIONS_INSUFFICIENT",
                "The GitHub App installation must grant contents and metadata read access.",
            )
        return VerifiedGitHubInstallation(
            installation_id=installation_id,
            account_login=account_login,
            account_id=account_id,
            target_type=target_type,
            permissions=normalized_permissions,
        )

    async def _exchange_user_code(self, client: httpx.AsyncClient, code: str) -> str:
        response = await client.post(
            f"{self.settings.github_web_url.rstrip('/')}/login/oauth/access_token",
            json={
                "client_id": self.settings.github_app_client_id,
                "client_secret": self.settings.github_app_client_secret,
                "code": code,
                "redirect_uri": self.settings.github_app_setup_callback_uri,
            },
            headers={"Accept": "application/json", "User-Agent": "StackGraph/1.0"},
        )
        if response.status_code >= 400:
            raise APIError(401, "GITHUB_OAUTH_REJECTED", "GitHub rejected the installation authorization.")
        payload = self._json_object(response, "GitHub returned an invalid OAuth response.")
        token = payload.get("access_token")
        if not isinstance(token, str) or not token:
            raise APIError(401, "GITHUB_OAUTH_REJECTED", "GitHub rejected the installation authorization.")
        return token

    async def _verify_user_installation(
        self,
        client: httpx.AsyncClient,
        user_token: str,
        installation_id: str,
    ) -> None:
        response = await client.get(
            f"{self.settings.github_api_url.rstrip('/')}/user/installations/{installation_id}/repositories",
            params={"per_page": 1},
            headers=self._api_headers(user_token),
        )
        if response.status_code in {401, 403, 404}:
            raise APIError(
                403,
                "GITHUB_INSTALLATION_NOT_AUTHORIZED",
                "The authenticated GitHub user is not authorized for this installation.",
            )
        if response.status_code >= 400:
            raise APIError(502, "GITHUB_APP_UNAVAILABLE", "GitHub could not verify installation ownership.")
        self._json_object(response, "GitHub returned invalid installation authorization metadata.")

    async def _load_app_installation(
        self,
        client: httpx.AsyncClient,
        app_jwt: str,
        installation_id: str,
    ) -> dict[str, Any]:
        response = await client.get(
            f"{self.settings.github_api_url.rstrip('/')}/app/installations/{installation_id}",
            headers=self._api_headers(app_jwt),
        )
        if response.status_code in {401, 403, 404}:
            raise APIError(
                403,
                "GITHUB_INSTALLATION_NOT_OWNED_BY_APP",
                "The installation does not belong to the configured GitHub App.",
            )
        if response.status_code >= 400:
            raise APIError(502, "GITHUB_APP_UNAVAILABLE", "GitHub could not load the installation.")
        return self._json_object(response, "GitHub returned invalid installation metadata.")

    async def _verify_installation_token(
        self,
        client: httpx.AsyncClient,
        app_jwt: str,
        installation_id: str,
    ) -> None:
        response = await client.post(
            f"{self.settings.github_api_url.rstrip('/')}/app/installations/{installation_id}/access_tokens",
            json={},
            headers=self._api_headers(app_jwt),
        )
        if response.status_code in {401, 403, 404}:
            raise APIError(
                403,
                "GITHUB_INSTALLATION_TOKEN_REJECTED",
                "GitHub did not authorize an installation token for this App installation.",
            )
        if response.status_code >= 400:
            raise APIError(502, "GITHUB_APP_UNAVAILABLE", "GitHub could not verify the installation token.")
        payload = self._json_object(response, "GitHub returned an invalid installation-token response.")
        if not isinstance(payload.get("token"), str) or not payload["token"]:
            raise APIError(502, "GITHUB_INSTALLATION_TOKEN_INVALID", "GitHub returned an invalid installation token.")

    def _app_jwt(self) -> str:
        now = int(time.time())
        try:
            return jwt.encode(
                {"iat": now - 60, "exp": now + 540, "iss": self.settings.github_app_id},
                self._private_key(),
                algorithm="RS256",
            )
        except (TypeError, ValueError, jwt.PyJWTError) as error:
            raise APIError(503, "GITHUB_APP_KEY_INVALID", "The GitHub App signing key is invalid.") from error

    def _private_key(self) -> str:
        value = self.settings.github_app_private_key.replace("\\n", "\n").strip()
        if value:
            return value
        path = self.settings.github_app_private_key_file
        if path is None:
            raise APIError(503, "GITHUB_APP_KEY_MISSING", "The GitHub App signing key is unavailable.")
        try:
            return Path(path).read_text(encoding="utf-8").strip()
        except OSError as error:
            raise APIError(503, "GITHUB_APP_KEY_MISSING", "The GitHub App signing key is unavailable.") from error

    @staticmethod
    def _api_headers(token: str) -> dict[str, str]:
        return {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "StackGraph/1.0",
            "X-GitHub-Api-Version": "2026-03-10",
        }

    @staticmethod
    def _json_object(response: httpx.Response, message: str) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError as error:
            raise APIError(502, "GITHUB_RESPONSE_INVALID", message) from error
        if not isinstance(payload, dict):
            raise APIError(502, "GITHUB_RESPONSE_INVALID", message)
        return payload

    def _validate_base_url(self, value: str, label: str) -> None:
        parsed = urlsplit(value)
        local = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
        if (
            not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or (
                parsed.scheme != "https"
                and not (self.settings.github_allow_insecure_localhost and local and parsed.scheme == "http")
            )
        ):
            raise ValueError(f"{label} URL must be an HTTPS origin without credentials, query, or fragment")
