from __future__ import annotations

import asyncio
import base64
import hashlib
import secrets
import time
from typing import Any
from urllib.parse import urlencode
from uuid import UUID

import httpx
import jwt
from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse

from app.auth import (
    Authenticator,
    OIDC_STATE_COOKIE,
    REFRESH_COOKIE,
    SESSION_COOKIE,
    TokenClaims,
)
from app.config import Settings
from app.errors import APIError


router = APIRouter(prefix="/auth", tags=["authentication"])


def _safe_return_path(value: str | None, fallback: str) -> str:
    if value and value.startswith("/") and not value.startswith("//"):
        return value
    return fallback


def _cookie_options(settings: Settings) -> dict[str, Any]:
    return {
        "httponly": True,
        "secure": settings.auth_cookie_secure,
        "samesite": "lax",
        "path": "/",
    }


def _set_session_cookies(
    response: Response,
    *,
    settings: Settings,
    access_token: str,
    refresh_token: str,
) -> None:
    options = _cookie_options(settings)
    response.set_cookie(
        SESSION_COOKIE,
        access_token,
        max_age=settings.auth_access_ttl_seconds,
        **options,
    )
    response.set_cookie(
        REFRESH_COOKIE,
        refresh_token,
        max_age=settings.auth_refresh_ttl_seconds,
        **options,
    )
    response.headers["Cache-Control"] = "no-store"


def _clear_session_cookies(response: Response, settings: Settings) -> None:
    options = _cookie_options(settings)
    for name in (SESSION_COOKIE, REFRESH_COOKIE, OIDC_STATE_COOKIE):
        response.delete_cookie(name, **options)
    response.headers["Cache-Control"] = "no-store"


class OIDCClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._discovery: dict[str, Any] | None = None
        self._jwks_clients: dict[str, jwt.PyJWKClient] = {}

    async def discovery(self) -> dict[str, Any]:
        if self._discovery is not None:
            return self._discovery
        url = f"{self.settings.oidc_issuer.rstrip('/')}/.well-known/openid-configuration"
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(url, headers={"Accept": "application/json"})
            response.raise_for_status()
            document = response.json()
        required = ("issuer", "authorization_endpoint", "token_endpoint", "jwks_uri")
        if not isinstance(document, dict) or any(not document.get(field) for field in required):
            raise APIError(502, "OIDC_DISCOVERY_INVALID", "The identity provider discovery document is invalid.")
        if document["issuer"].rstrip("/") != self.settings.oidc_issuer.rstrip("/"):
            raise APIError(502, "OIDC_ISSUER_MISMATCH", "The identity provider issuer does not match configuration.")
        self._discovery = document
        return document

    async def exchange_code(self, *, code: str, verifier: str) -> dict[str, Any]:
        discovery = await self.discovery()
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                discovery["token_endpoint"],
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": self.settings.oidc_redirect_uri,
                    "client_id": self.settings.oidc_client_id,
                    "client_secret": self.settings.oidc_client_secret,
                    "code_verifier": verifier,
                },
                headers={"Accept": "application/json"},
            )
        if response.status_code >= 400:
            raise APIError(401, "OIDC_CODE_EXCHANGE_FAILED", "The identity provider rejected the login callback.")
        payload = response.json()
        if not isinstance(payload, dict) or not isinstance(payload.get("id_token"), str):
            raise APIError(401, "OIDC_ID_TOKEN_MISSING", "The identity provider did not return an ID token.")
        return payload

    async def validate_id_token(self, token: str, *, nonce: str) -> dict[str, Any]:
        discovery = await self.discovery()
        try:
            header = jwt.get_unverified_header(token)
            algorithm = header.get("alg")
            if algorithm not in {"RS256", "RS384", "RS512", "ES256", "ES384", "ES512"}:
                raise ValueError("unsupported ID token algorithm")
            jwks_uri = discovery["jwks_uri"]
            client = self._jwks_clients.setdefault(jwks_uri, jwt.PyJWKClient(jwks_uri, cache_jwk_set=True))
            signing_key = await asyncio.to_thread(client.get_signing_key_from_jwt, token)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=[algorithm],
                audience=self.settings.oidc_client_id,
                issuer=self.settings.oidc_issuer,
                leeway=30,
                options={"require": ["sub", "exp", "iat", "iss", "aud", "nonce"]},
            )
            if not secrets.compare_digest(str(claims["nonce"]), nonce):
                raise ValueError("nonce mismatch")
            return claims
        except (jwt.PyJWTError, KeyError, TypeError, ValueError) as error:
            raise APIError(401, "OIDC_ID_TOKEN_INVALID", "The identity provider ID token is invalid.") from error


def _identity_from_claims(settings: Settings, claims: dict[str, Any]) -> tuple[str, UUID, list[str]]:
    actor_key = claims.get("sub")
    if not isinstance(actor_key, str) or not actor_key:
        raise APIError(401, "OIDC_SUBJECT_MISSING", "The identity provider did not identify the user.")
    raw_tenant = claims.get(settings.oidc_tenant_claim)
    try:
        tenant_id = UUID(str(raw_tenant)) if raw_tenant else settings.default_tenant_id
    except ValueError as error:
        raise APIError(403, "OIDC_TENANT_INVALID", "The identity provider tenant claim is invalid.") from error
    if tenant_id is None:
        raise APIError(403, "OIDC_TENANT_REQUIRED", "The identity provider did not assign a StackGraph tenant.")

    groups = claims.get(settings.oidc_groups_claim, [])
    if isinstance(groups, str):
        groups = [groups]
    if not isinstance(groups, list):
        groups = []
    mapped = [
        settings.oidc_group_capabilities[group]
        for group in groups
        if isinstance(group, str) and group in settings.oidc_group_capabilities
    ]
    capabilities = [max(mapped, key=("view", "review", "execute", "admin").index)] if mapped else ["view"]
    return actor_key, tenant_id, capabilities


@router.get("/login", response_model=None)
async def login(request: Request, return_to: str | None = None) -> RedirectResponse:
    settings: Settings = request.app.state.settings
    if settings.auth_mode != "oidc":
        raise APIError(404, "OIDC_DISABLED", "OIDC login is not enabled.")
    oidc: OIDCClient = request.app.state.oidc_client
    discovery = await oidc.discovery()
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    authenticator: Authenticator = request.app.state.authenticator
    state_token, _ = authenticator.issue_token(
        actor_key="oidc-state",
        tenant_id=None,
        capabilities=[],
        token_type="oidc_state",
        ttl_seconds=600,
        additional_claims={
            "state": state,
            "nonce": nonce,
            "verifier": verifier,
            "return_to": _safe_return_path(return_to, settings.oidc_web_return_uri),
        },
    )
    query = urlencode({
        "response_type": "code",
        "client_id": settings.oidc_client_id,
        "redirect_uri": settings.oidc_redirect_uri,
        "scope": "openid profile email",
        "state": state,
        "nonce": nonce,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    })
    response = RedirectResponse(f"{discovery['authorization_endpoint']}?{query}", status_code=302)
    response.set_cookie(
        OIDC_STATE_COOKIE,
        state_token,
        max_age=600,
        **_cookie_options(settings),
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@router.get("/callback", response_model=None)
async def callback(request: Request, code: str, state: str) -> RedirectResponse:
    settings: Settings = request.app.state.settings
    state_cookie = request.cookies.get(OIDC_STATE_COOKIE)
    if not state_cookie:
        raise APIError(401, "OIDC_STATE_MISSING", "The login state cookie is missing.")
    authenticator: Authenticator = request.app.state.authenticator
    state_claims = authenticator.decode_token(state_cookie, expected_type="oidc_state")
    if not secrets.compare_digest(str(state_claims.raw.get("state", "")), state):
        raise APIError(401, "OIDC_STATE_INVALID", "The login state is invalid.")
    oidc: OIDCClient = request.app.state.oidc_client
    exchanged = await oidc.exchange_code(code=code, verifier=str(state_claims.raw["verifier"]))
    id_claims = await oidc.validate_id_token(
        exchanged["id_token"],
        nonce=str(state_claims.raw["nonce"]),
    )
    actor_key, tenant_id, capabilities = _identity_from_claims(settings, id_claims)
    access_token, _ = authenticator.issue_token(
        actor_key=actor_key,
        tenant_id=tenant_id,
        capabilities=capabilities,
        token_type="access",
        ttl_seconds=settings.auth_access_ttl_seconds,
    )
    refresh_token, _ = authenticator.issue_token(
        actor_key=actor_key,
        tenant_id=tenant_id,
        capabilities=capabilities,
        token_type="refresh",
        ttl_seconds=settings.auth_refresh_ttl_seconds,
    )
    response = RedirectResponse(
        _safe_return_path(str(state_claims.raw.get("return_to", "")), settings.oidc_web_return_uri),
        status_code=302,
    )
    response.delete_cookie(OIDC_STATE_COOKIE, **_cookie_options(settings))
    _set_session_cookies(
        response,
        settings=settings,
        access_token=access_token,
        refresh_token=refresh_token,
    )
    return response


@router.post("/refresh")
async def refresh(request: Request) -> JSONResponse:
    settings: Settings = request.app.state.settings
    authenticator: Authenticator = request.app.state.authenticator
    raw_refresh = request.cookies.get(REFRESH_COOKIE)
    if not raw_refresh:
        raise APIError(401, "REFRESH_REQUIRED", "A refresh session is required.")
    claims = authenticator.decode_token(raw_refresh, expected_type="refresh")
    if await authenticator.revocations.is_revoked(tenant_id=claims.tenant_id, jti=claims.jti):
        raise APIError(401, "SESSION_REVOKED", "The refresh session has been revoked.")
    rotated = await authenticator.revocations.revoke(
        tenant_id=claims.tenant_id,
        jti=claims.jti,
        actor_key=claims.actor_key,
        token_type="refresh",
        expires_at=claims.expires_at,
        reason="refresh-rotation",
    )
    if not rotated:
        raise APIError(401, "REFRESH_REPLAYED", "The refresh session has already been used.")
    capabilities = sorted(claims.capabilities)
    access_token, access = authenticator.issue_token(
        actor_key=claims.actor_key,
        tenant_id=claims.tenant_id,
        capabilities=capabilities,
        token_type="access",
        ttl_seconds=settings.auth_access_ttl_seconds,
    )
    refresh_token, _ = authenticator.issue_token(
        actor_key=claims.actor_key,
        tenant_id=claims.tenant_id,
        capabilities=capabilities,
        token_type="refresh",
        ttl_seconds=settings.auth_refresh_ttl_seconds,
    )
    response = JSONResponse({"status": "refreshed", "expires_at": access.expires_at})
    _set_session_cookies(
        response,
        settings=settings,
        access_token=access_token,
        refresh_token=refresh_token,
    )
    return response


async def _revoke_cookie(
    authenticator: Authenticator,
    token: str | None,
    *,
    token_type: str,
    reason: str,
) -> None:
    if not token:
        return
    try:
        claims: TokenClaims = authenticator.decode_token(token, expected_type=token_type)
    except APIError:
        return
    await authenticator.revocations.revoke(
        tenant_id=claims.tenant_id,
        jti=claims.jti,
        actor_key=claims.actor_key,
        token_type=token_type,
        expires_at=claims.expires_at,
        reason=reason,
    )


@router.post("/logout")
async def logout(request: Request) -> JSONResponse:
    settings: Settings = request.app.state.settings
    authenticator: Authenticator = request.app.state.authenticator
    await _revoke_cookie(
        authenticator,
        request.cookies.get(SESSION_COOKIE),
        token_type="access",
        reason="logout",
    )
    await _revoke_cookie(
        authenticator,
        request.cookies.get(REFRESH_COOKIE),
        token_type="refresh",
        reason="logout",
    )
    response = JSONResponse({"status": "signed_out"})
    _clear_session_cookies(response, settings)
    return response
