import asyncio

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.config import Settings
from app.errors import APIError
from app.github_app import GitHubAppSetupClient


def _private_key() -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")


def _settings() -> Settings:
    return Settings(
        environment="test",
        github_app_setup_enabled=True,
        github_app_slug="stackgraph",
        github_app_id="12345",
        github_app_client_id="Iv1.client",
        github_app_client_secret="client-secret",
        github_app_private_key=_private_key(),
        github_app_setup_callback_uri=(
            "https://stackgraph.example/api/v1/admin/github/installations/setup/callback"
        ),
    )


def test_verifies_user_app_permissions_and_installation_token() -> None:
    requests: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append((request.method, request.url.path))
        if request.url.path == "/login/oauth/access_token":
            return httpx.Response(200, json={"access_token": "ghu_variable_length_token"})
        if request.url.path == "/user/installations/9876/repositories":
            assert request.headers["Authorization"] == "Bearer ghu_variable_length_token"
            return httpx.Response(200, json={"total_count": 1, "repositories": []})
        if request.url.path == "/app/installations/9876":
            return httpx.Response(200, json={
                "account": {"login": "acme", "id": 42},
                "target_type": "Organization",
                "permissions": {"contents": "read", "metadata": "read"},
            })
        if request.url.path == "/app/installations/9876/access_tokens":
            return httpx.Response(201, json={
                "token": "ghs_12345_stateless-token-shape",
                "expires_at": "2026-08-21T18:00:00Z",
            })
        return httpx.Response(404)

    client = GitHubAppSetupClient(_settings(), transport=httpx.MockTransport(handler))
    verified = asyncio.run(client.verify_installation(code="oauth-code", installation_id="9876"))
    assert verified.account_login == "acme"
    assert verified.permissions == ("contents:read", "metadata:read")
    assert requests == [
        ("POST", "/login/oauth/access_token"),
        ("GET", "/user/installations/9876/repositories"),
        ("GET", "/app/installations/9876"),
        ("POST", "/app/installations/9876/access_tokens"),
    ]


def test_rejects_spoofed_installation_not_visible_to_installing_user() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/login/oauth/access_token":
            return httpx.Response(200, json={"access_token": "user-token"})
        return httpx.Response(404, json={"message": "Not Found"})

    client = GitHubAppSetupClient(_settings(), transport=httpx.MockTransport(handler))
    with pytest.raises(APIError) as captured:
        asyncio.run(client.verify_installation(code="oauth-code", installation_id="9876"))
    assert captured.value.code == "GITHUB_INSTALLATION_NOT_AUTHORIZED"


def test_setup_url_carries_only_opaque_state() -> None:
    client = GitHubAppSetupClient(_settings())
    assert client.installation_url("opaque-state") == (
        "https://github.com/apps/stackgraph/installations/new?state=opaque-state"
    )
