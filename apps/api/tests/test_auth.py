from __future__ import annotations

import asyncio
import time
from uuid import UUID

import pytest

from app.auth import Authenticator, create_session_token
from app.auth_routes import _identity_from_claims, _safe_return_path
from app.config import Settings
from app.errors import APIError


SECRET = "a-test-session-secret-with-at-least-32-characters"
TENANT = UUID("00000000-0000-4000-8000-000000000123")


class Revocations:
    def __init__(self) -> None:
        self.revoked: set[UUID] = set()

    async def is_revoked(self, *, tenant_id, jti) -> bool:
        return jti in self.revoked

    async def revoke(self, *, tenant_id, jti, actor_key, token_type, expires_at, reason) -> bool:
        if jti in self.revoked:
            return False
        self.revoked.add(jti)
        return True


def test_session_enforces_audience_kid_jti_and_revocation() -> None:
    revocations = Revocations()
    settings = Settings(
        environment="test",
        auth_mode="signed_session",
        auth_session_keys_json='{"old":"' + SECRET + '","current":"' + SECRET + '-current"}',
        auth_session_active_kid="current",
    )
    authenticator = Authenticator(settings, revocations)
    token, claims = authenticator.issue_token(
        actor_key="reviewer",
        tenant_id=TENANT,
        capabilities=["review"],
        token_type="access",
        ttl_seconds=60,
    )

    principal = asyncio.run(authenticator.authenticate(f"Bearer {token}"))
    assert principal.jti == claims.jti
    assert principal.has_capability("view")
    assert principal.has_capability("review")

    revocations.revoked.add(claims.jti)
    with pytest.raises(APIError) as caught:
        asyncio.run(authenticator.authenticate(f"Bearer {token}"))
    assert caught.value.code == "SESSION_REVOKED"


def test_session_rejects_wrong_audience_and_token_type() -> None:
    authenticator = Authenticator(Settings(
        environment="test",
        auth_mode="signed_session",
        auth_session_secret=SECRET,
    ))
    wrong_audience = create_session_token(
        SECRET,
        actor_key="viewer",
        tenant_id=TENANT,
        expires_at=int(time.time()) + 60,
        audience="another-api",
    )
    refresh = create_session_token(
        SECRET,
        actor_key="viewer",
        tenant_id=TENANT,
        expires_at=int(time.time()) + 60,
        token_type="refresh",
    )

    for token in (wrong_audience, refresh):
        with pytest.raises(APIError) as caught:
            authenticator.decode_token(token)
        assert caught.value.code == "INVALID_SESSION"


def test_additional_claims_cannot_override_session_protocol_claims() -> None:
    token = create_session_token(
        SECRET,
        actor_key="expected-actor",
        tenant_id=TENANT,
        expires_at=int(time.time()) + 60,
        additional_claims={"sub": "attacker", "token_type": "refresh", "custom": "preserved"},
    )
    claims = Authenticator(Settings(
        environment="test",
        auth_mode="signed_session",
        auth_session_secret=SECRET,
    )).decode_token(token)

    assert claims.actor_key == "expected-actor"
    assert claims.token_type == "access"
    assert claims.raw["custom"] == "preserved"


def test_oidc_claim_mapping_is_least_privilege_and_tenant_scoped() -> None:
    settings = Settings(environment="test", default_tenant_id=TENANT)
    actor, tenant, capabilities = _identity_from_claims(settings, {
        "sub": "oidc-user",
        "groups": ["stackgraph-review", "unrelated"],
    })
    assert (actor, tenant, capabilities) == ("oidc-user", TENANT, ["review"])

    _, _, least_privilege = _identity_from_claims(settings, {"sub": "viewer"})
    assert least_privilege == ["view"]


def test_oidc_return_path_rejects_open_redirects() -> None:
    assert _safe_return_path("/estate?domain=OSS", "/") == "/estate?domain=OSS"
    assert _safe_return_path("//attacker.example", "/") == "/"
    assert _safe_return_path("https://attacker.example", "/") == "/"
