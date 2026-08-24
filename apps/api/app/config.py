from functools import lru_cache
from pathlib import Path
import json
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="STACKGRAPH_",
        case_sensitive=False,
        extra="ignore",
    )

    service_name: str = "stackgraph-api"
    environment: str = "development"
    database_url: str = "postgresql://stackgraph_app:stackgraph_app@localhost:5432/stackgraph"
    db_pool_min_size: int = Field(default=1, ge=1)
    db_pool_max_size: int = Field(default=5, ge=1)
    default_tenant_id: UUID | None = None
    cors_allowed_origins: str = "http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173"
    auth_mode: Literal["development", "signed_session", "oidc"] = "development"
    auth_session_secret: str | None = None
    auth_session_keys_json: str = ""
    auth_session_active_kid: str = "primary"
    auth_session_audience: str = "stackgraph-api"
    auth_access_ttl_seconds: int = Field(default=300, ge=60, le=3600)
    auth_refresh_ttl_seconds: int = Field(default=28_800, ge=300, le=2_592_000)
    auth_cookie_secure: bool = True
    oidc_issuer: str = ""
    oidc_client_id: str = ""
    oidc_client_secret: str = ""
    oidc_redirect_uri: str = ""
    oidc_web_return_uri: str = "/"
    oidc_tenant_claim: str = "stackgraph_tenant_id"
    oidc_groups_claim: str = "groups"
    oidc_group_capabilities_json: str = '{"stackgraph-view":"view","stackgraph-review":"review","stackgraph-execute":"execute","stackgraph-admin":"admin"}'
    github_app_setup_enabled: bool = False
    github_app_slug: str = ""
    github_app_id: str = ""
    github_app_client_id: str = ""
    github_app_client_secret: str = ""
    github_app_private_key: str = ""
    github_app_private_key_file: Path | None = None
    github_app_setup_callback_uri: str = ""
    github_app_web_return_uri: str = "/admin"
    github_api_url: str = "https://api.github.com"
    github_web_url: str = "https://github.com"
    github_allow_insecure_localhost: bool = False
    github_manual_binding_enabled: bool = True
    development_actor_key: str = "local-user"
    contracts_dir: Path = Path("/contracts/v1")
    graph_read_mode: Literal["auto", "neo4j", "age", "sql"] = "auto"
    graph_discovery_limit: int = Field(default=5000, ge=50, le=50000)
    graph_age_timeout_seconds: float = Field(default=3.0, ge=0.1, le=30.0)
    ai_ask_enabled: bool = False
    ai_ask_route: str = "default"
    ai_ask_fallback_enabled: bool = True
    ai_ask_max_evidence_chars: int = Field(default=50_000, ge=1_024, le=200_000)
    credential_encryption_key: str = Field(
        default="stackgraph-local-development-credential-key",
        min_length=32,
    )
    request_body_max_bytes: int = Field(default=1_048_576, ge=1_024, le=10_485_760)
    rate_limit_requests_per_minute: int = Field(default=300, ge=1, le=100_000)
    rate_limit_ask_per_minute: int = Field(default=20, ge=1, le=10_000)
    metrics_bearer_token: str = ""
    sentry_dsn: str = ""
    log_level: str = "INFO"

    @model_validator(mode="after")
    def validate_auth(self) -> "Settings":
        normalized_environment = self.environment.strip().lower()
        if normalized_environment in {"production", "prod"} and self.auth_mode == "development":
            raise ValueError("development auth mode is not allowed in production")
        keys = self.session_keys
        if self.auth_mode in {"signed_session", "oidc"} and not keys:
            raise ValueError("signed_session and oidc auth require at least one session signing key")
        if keys and self.auth_session_active_kid not in keys:
            raise ValueError("auth_session_active_kid must identify a configured session signing key")
        if any(len(secret) < 32 for secret in keys.values()):
            raise ValueError("every session signing key must contain at least 32 characters")
        if self.auth_mode == "oidc" and not all((
            self.oidc_issuer, self.oidc_client_id, self.oidc_client_secret, self.oidc_redirect_uri,
        )):
            raise ValueError("oidc auth requires issuer, client ID, client secret, and redirect URI")
        if self.github_app_setup_enabled and not all((
            self.github_app_slug,
            self.github_app_id,
            self.github_app_client_id,
            self.github_app_client_secret,
            self.github_app_setup_callback_uri,
        )):
            raise ValueError(
                "hosted GitHub setup requires the App slug, App ID, client ID, client secret, and callback URI"
            )
        private_key_file_configured = (
            self.github_app_private_key_file is not None
            and str(self.github_app_private_key_file).strip() not in {"", "."}
        )
        if self.github_app_setup_enabled and not (
            self.github_app_private_key.strip() or private_key_file_configured
        ):
            raise ValueError("hosted GitHub setup requires a GitHub App private key or private-key file")
        if self.github_app_slug and (
            len(self.github_app_slug) > 100
            or any(character not in "abcdefghijklmnopqrstuvwxyz0123456789-" for character in self.github_app_slug)
        ):
            raise ValueError("github_app_slug must be GitHub's lowercase App slug")
        if (
            self.github_app_setup_enabled
            and not self.github_app_setup_callback_uri.startswith("https://")
            and not self.github_allow_insecure_localhost
        ):
            raise ValueError("the hosted GitHub setup callback URI must use HTTPS")
        if not self.github_app_web_return_uri.startswith("/") or self.github_app_web_return_uri.startswith("//"):
            raise ValueError("github_app_web_return_uri must be a safe absolute path")
        try:
            group_mapping = json.loads(self.oidc_group_capabilities_json)
        except json.JSONDecodeError as error:
            raise ValueError("oidc_group_capabilities_json must be valid JSON") from error
        if not isinstance(group_mapping, dict) or any(
            not isinstance(group, str) or capability not in {"view", "review", "execute", "admin"}
            for group, capability in group_mapping.items()
        ):
            raise ValueError("OIDC group mappings must map group names to StackGraph capabilities")
        if (
            normalized_environment not in {"development", "dev", "test"}
            and self.credential_encryption_key == "stackgraph-local-development-credential-key"
        ):
            raise ValueError("credential_encryption_key must be overridden outside development and test")
        return self

    @property
    def session_keys(self) -> dict[str, str]:
        if self.auth_session_keys_json.strip():
            try:
                value = json.loads(self.auth_session_keys_json)
            except json.JSONDecodeError as error:
                raise ValueError("auth_session_keys_json must be valid JSON") from error
            if not isinstance(value, dict) or any(
                not isinstance(key, str) or not isinstance(secret, str)
                for key, secret in value.items()
            ):
                raise ValueError("auth_session_keys_json must be a string-to-string object")
            return value
        if self.auth_session_secret:
            return {self.auth_session_active_kid: self.auth_session_secret}
        return {}

    @property
    def oidc_group_capabilities(self) -> dict[str, str]:
        return json.loads(self.oidc_group_capabilities_json)

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
