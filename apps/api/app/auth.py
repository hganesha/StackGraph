from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID, uuid4

import jwt

from app.config import Settings
from app.errors import APIError


CAPABILITY_LADDER: tuple[str, ...] = ("view", "review", "execute", "admin")
SESSION_COOKIE = "stackgraph_session"
REFRESH_COOKIE = "stackgraph_refresh"
OIDC_STATE_COOKIE = "stackgraph_oidc_state"


def _normalize_capabilities(raw: Any) -> frozenset[str]:
    if not isinstance(raw, (list, tuple, set, frozenset)):
        return frozenset()
    return frozenset(item for item in raw if isinstance(item, str) and item in CAPABILITY_LADDER)


@dataclass(frozen=True, slots=True)
class Principal:
    actor_key: str
    tenant_id: UUID | None
    capabilities: frozenset[str] = frozenset()
    jti: UUID | None = None
    expires_at: int | None = None

    def has_capability(self, required: str) -> bool:
        if required not in CAPABILITY_LADDER:
            return False
        held = [CAPABILITY_LADDER.index(c) for c in self.capabilities if c in CAPABILITY_LADDER]
        return bool(held) and max(held) >= CAPABILITY_LADDER.index(required)


@dataclass(frozen=True, slots=True)
class TokenClaims:
    actor_key: str
    tenant_id: UUID | None
    capabilities: frozenset[str]
    jti: UUID
    expires_at: int
    token_type: str
    raw: dict[str, Any]


class TokenRevocationStore(Protocol):
    async def is_revoked(self, *, tenant_id: UUID | None, jti: UUID) -> bool: ...

    async def revoke(
        self,
        *,
        tenant_id: UUID | None,
        jti: UUID,
        actor_key: str,
        token_type: str,
        expires_at: int,
        reason: str,
    ) -> bool: ...


class NullTokenRevocationStore:
    async def is_revoked(self, *, tenant_id: UUID | None, jti: UUID) -> bool:
        return False

    async def revoke(
        self,
        *,
        tenant_id: UUID | None,
        jti: UUID,
        actor_key: str,
        token_type: str,
        expires_at: int,
        reason: str,
    ) -> bool:
        return True


class DatabaseTokenRevocationStore:
    def __init__(self, database: Any) -> None:
        self.database = database

    async def is_revoked(self, *, tenant_id: UUID | None, jti: UUID) -> bool:
        row = await self.database.fetch_one(
            "SELECT 1 AS revoked FROM auth_token_revocation WHERE jti = %s AND expires_at > now()",
            (jti,),
            tenant_id=tenant_id,
        )
        return row is not None

    async def revoke(
        self,
        *,
        tenant_id: UUID | None,
        jti: UUID,
        actor_key: str,
        token_type: str,
        expires_at: int,
        reason: str,
    ) -> bool:
        if tenant_id is None:
            return False
        row = await self.database.fetch_one(
            """
            INSERT INTO auth_token_revocation(
              tenant_id,jti,actor_key,token_type,expires_at,reason
            ) VALUES (%s,%s,%s,%s,to_timestamp(%s),%s)
            ON CONFLICT (tenant_id,jti) DO NOTHING
            RETURNING jti
            """,
            (tenant_id, jti, actor_key, token_type, expires_at, reason),
            tenant_id=tenant_id,
        )
        return row is not None


def create_session_token(
    secret: str,
    *,
    actor_key: str,
    tenant_id: UUID | None,
    expires_at: int,
    capabilities: list[str] | None = None,
    audience: str = "stackgraph-api",
    kid: str = "primary",
    jti: UUID | None = None,
    token_type: str = "access",
    additional_claims: dict[str, Any] | None = None,
) -> str:
    now = int(time.time())
    payload: dict[str, Any] = dict(additional_claims or {})
    # Protocol claims always win over caller-provided state. This keeps internal
    # extension claims from silently changing the token subject or lifetime.
    payload.update({
        "sub": actor_key,
        "tenant_id": str(tenant_id) if tenant_id else None,
        "iat": now,
        "exp": expires_at,
        "aud": audience,
        "jti": str(jti or uuid4()),
        "token_type": token_type,
    })
    if capabilities is not None:
        payload["capabilities"] = list(capabilities)
    return jwt.encode(payload, secret, algorithm="HS256", headers={"kid": kid, "typ": "JWT"})


class Authenticator:
    def __init__(
        self,
        settings: Settings,
        revocations: TokenRevocationStore | None = None,
    ) -> None:
        self.settings = settings
        self.revocations = revocations or NullTokenRevocationStore()

    def issue_token(
        self,
        *,
        actor_key: str,
        tenant_id: UUID | None,
        capabilities: list[str],
        token_type: str,
        ttl_seconds: int,
        additional_claims: dict[str, Any] | None = None,
    ) -> tuple[str, TokenClaims]:
        expires_at = int(time.time()) + ttl_seconds
        jti = uuid4()
        secret = self.settings.session_keys[self.settings.auth_session_active_kid]
        token = create_session_token(
            secret,
            actor_key=actor_key,
            tenant_id=tenant_id,
            expires_at=expires_at,
            capabilities=capabilities,
            audience=self.settings.auth_session_audience,
            kid=self.settings.auth_session_active_kid,
            jti=jti,
            token_type=token_type,
            additional_claims=additional_claims,
        )
        return token, TokenClaims(
            actor_key=actor_key,
            tenant_id=tenant_id,
            capabilities=frozenset(capabilities),
            jti=jti,
            expires_at=expires_at,
            token_type=token_type,
            raw=additional_claims or {},
        )

    def decode_token(self, token: str, *, expected_type: str = "access") -> TokenClaims:
        try:
            header = jwt.get_unverified_header(token)
            kid = header.get("kid")
            if not isinstance(kid, str) or kid not in self.settings.session_keys:
                raise ValueError("unknown signing key")
            payload = jwt.decode(
                token,
                self.settings.session_keys[kid],
                algorithms=["HS256"],
                audience=self.settings.auth_session_audience,
                options={"require": ["sub", "exp", "iat", "aud", "jti", "token_type"]},
            )
            actor_key = payload["sub"]
            if not isinstance(actor_key, str) or not actor_key:
                raise ValueError("invalid subject")
            token_type = payload["token_type"]
            if token_type != expected_type:
                raise ValueError("unexpected token type")
            raw_tenant_id = payload.get("tenant_id")
            tenant_id = UUID(raw_tenant_id) if raw_tenant_id else None
            capabilities = (
                _normalize_capabilities(payload["capabilities"])
                if "capabilities" in payload
                else frozenset({"view"})
            )
            return TokenClaims(
                actor_key=actor_key,
                tenant_id=tenant_id,
                capabilities=capabilities,
                jti=UUID(payload["jti"]),
                expires_at=int(payload["exp"]),
                token_type=token_type,
                raw=payload,
            )
        except jwt.ExpiredSignatureError as error:
            raise APIError(401, "SESSION_EXPIRED", "The session has expired.") from error
        except (jwt.PyJWTError, KeyError, TypeError, ValueError) as error:
            raise APIError(401, "INVALID_SESSION", "The session is invalid.") from error

    async def authenticate(
        self,
        authorization: str | None,
        session_cookie: str | None = None,
    ) -> Principal:
        if self.settings.auth_mode == "development":
            return Principal(
                actor_key=self.settings.development_actor_key,
                tenant_id=self.settings.default_tenant_id,
                capabilities=frozenset({"admin"}),
            )

        token = session_cookie
        if authorization is not None and authorization.startswith("Bearer "):
            token = authorization.removeprefix("Bearer ").strip()
        if not token:
            raise APIError(401, "AUTH_REQUIRED", "A valid session is required.")

        claims = self.decode_token(token)
        if await self.revocations.is_revoked(tenant_id=claims.tenant_id, jti=claims.jti):
            raise APIError(401, "SESSION_REVOKED", "The session has been revoked.")
        return Principal(
            actor_key=claims.actor_key,
            tenant_id=claims.tenant_id,
            capabilities=claims.capabilities,
            jti=claims.jti,
            expires_at=claims.expires_at,
        )
