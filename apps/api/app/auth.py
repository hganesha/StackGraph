from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from app.config import Settings
from app.errors import APIError


# Graded capability ladder: each tier implies the ones before it
# (view → review → execute → admin). Mirrors the web session model in apps/web/lib/session.ts.
CAPABILITY_LADDER: tuple[str, ...] = ("view", "review", "execute", "admin")


def _normalize_capabilities(raw: Any) -> frozenset[str]:
    if not isinstance(raw, (list, tuple, set, frozenset)):
        return frozenset()
    return frozenset(item for item in raw if isinstance(item, str) and item in CAPABILITY_LADDER)


@dataclass(frozen=True, slots=True)
class Principal:
    actor_key: str
    tenant_id: UUID | None
    capabilities: frozenset[str] = frozenset()

    def has_capability(self, required: str) -> bool:
        """True when the principal holds `required` or any higher tier on the ladder."""
        if required not in CAPABILITY_LADDER:
            return False
        held = [CAPABILITY_LADDER.index(c) for c in self.capabilities if c in CAPABILITY_LADDER]
        return bool(held) and max(held) >= CAPABILITY_LADDER.index(required)


def _base64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def _base64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def create_session_token(
    secret: str,
    *,
    actor_key: str,
    tenant_id: UUID | None,
    expires_at: int,
    capabilities: list[str] | None = None,
) -> str:
    payload: dict[str, Any] = {
        "sub": actor_key,
        "tenant_id": str(tenant_id) if tenant_id else None,
        "exp": expires_at,
    }
    if capabilities is not None:
        payload["capabilities"] = list(capabilities)
    encoded_payload = _base64url_encode(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    )
    signature = hmac.new(
        secret.encode(), encoded_payload.encode(), hashlib.sha256,
    ).digest()
    return f"{encoded_payload}.{_base64url_encode(signature)}"


class Authenticator:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def authenticate(self, authorization: str | None) -> Principal:
        if self.settings.auth_mode == "development":
            # Local/fixtures development runs with full capability, matching the mock web session.
            return Principal(
                actor_key=self.settings.development_actor_key,
                tenant_id=self.settings.default_tenant_id,
                capabilities=frozenset({"admin"}),
            )

        if authorization is None or not authorization.startswith("Bearer "):
            raise APIError(401, "AUTH_REQUIRED", "A valid bearer session is required.")
        token = authorization.removeprefix("Bearer ").strip()
        try:
            encoded_payload, encoded_signature = token.split(".", 1)
            secret = self.settings.auth_session_secret
            assert secret is not None
            expected = hmac.new(
                secret.encode(), encoded_payload.encode(), hashlib.sha256,
            ).digest()
            if not hmac.compare_digest(expected, _base64url_decode(encoded_signature)):
                raise ValueError("signature mismatch")
            payload: dict[str, Any] = json.loads(_base64url_decode(encoded_payload))
            actor_key = payload["sub"]
            if not isinstance(actor_key, str) or not actor_key:
                raise ValueError("invalid subject")
            expires_at = int(payload["exp"])
            if expires_at <= int(time.time()):
                raise APIError(401, "SESSION_EXPIRED", "The bearer session has expired.")
            raw_tenant_id = payload.get("tenant_id")
            tenant_id = UUID(raw_tenant_id) if raw_tenant_id else None
            # Absent capabilities default to least privilege (read-only).
            capabilities = (
                _normalize_capabilities(payload["capabilities"])
                if "capabilities" in payload
                else frozenset({"view"})
            )
        except APIError:
            raise
        except (AssertionError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise APIError(401, "INVALID_SESSION", "The bearer session is invalid.") from error
        return Principal(actor_key=actor_key, tenant_id=tenant_id, capabilities=capabilities)
