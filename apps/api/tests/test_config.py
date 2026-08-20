from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config import Settings


def test_production_rejects_development_auth_mode() -> None:
    with pytest.raises(ValidationError, match="development auth mode is not allowed in production"):
        Settings(
            environment="production",
            auth_mode="development",
            credential_encryption_key="a-production-credential-key-with-32-characters",
        )


def test_production_accepts_configured_signed_session_auth() -> None:
    settings = Settings(
        environment="production",
        auth_mode="signed_session",
        auth_session_secret="a-production-session-secret-with-32-characters",
        credential_encryption_key="a-production-credential-key-with-32-characters",
    )

    assert settings.auth_mode == "signed_session"


def test_development_auth_remains_available_outside_production() -> None:
    settings = Settings(environment="test", auth_mode="development")

    assert settings.auth_mode == "development"


def test_oidc_requires_provider_configuration() -> None:
    with pytest.raises(ValidationError, match="oidc auth requires"):
        Settings(
            environment="test",
            auth_mode="oidc",
            auth_session_secret="a-production-session-secret-with-32-characters",
        )
