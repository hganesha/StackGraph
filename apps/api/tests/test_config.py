from __future__ import annotations

from uuid import UUID

import pytest
from pydantic import ValidationError

from app.config import DEFAULT_TENANT_ID, Settings


PRODUCTION_TENANT_ID = UUID("00000000-0000-4000-8000-000000000101")


def test_production_rejects_development_auth_mode() -> None:
    with pytest.raises(ValidationError, match="development auth mode is not allowed in production"):
        Settings(
            environment="production",
            auth_mode="development",
            default_tenant_id=PRODUCTION_TENANT_ID,
            credential_encryption_key="a-production-credential-key-with-32-characters",
        )


def test_production_accepts_configured_signed_session_auth() -> None:
    settings = Settings(
        environment="production",
        auth_mode="signed_session",
        default_tenant_id=PRODUCTION_TENANT_ID,
        auth_session_secret="a-production-session-secret-with-32-characters",
        credential_encryption_key="a-production-credential-key-with-32-characters",
    )

    assert settings.auth_mode == "signed_session"
    assert settings.default_tenant_id == PRODUCTION_TENANT_ID


def test_production_requires_explicit_default_tenant_id() -> None:
    with pytest.raises(ValidationError, match="default_tenant_id must be explicitly configured"):
        Settings(
            environment="production",
            auth_mode="signed_session",
            auth_session_secret="a-production-session-secret-with-32-characters",
            credential_encryption_key="a-production-credential-key-with-32-characters",
        )


def test_development_auth_remains_available_outside_production() -> None:
    settings = Settings(environment="test", auth_mode="development")

    assert settings.auth_mode == "development"
    assert settings.default_tenant_id == DEFAULT_TENANT_ID


def test_oidc_requires_provider_configuration() -> None:
    with pytest.raises(ValidationError, match="oidc auth requires"):
        Settings(
            environment="test",
            auth_mode="oidc",
            auth_session_secret="a-production-session-secret-with-32-characters",
        )
