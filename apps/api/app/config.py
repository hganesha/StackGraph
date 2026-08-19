from functools import lru_cache
from pathlib import Path
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
    cors_allowed_origins: str = "http://localhost:3000,http://localhost:5173"
    auth_mode: Literal["development", "signed_session"] = "development"
    auth_session_secret: str | None = None
    development_actor_key: str = "local-user"
    contracts_dir: Path = Path("/contracts/v1")

    @model_validator(mode="after")
    def validate_auth(self) -> "Settings":
        if self.auth_mode == "signed_session" and (
            self.auth_session_secret is None or len(self.auth_session_secret) < 32
        ):
            raise ValueError("auth_session_secret must contain at least 32 characters in signed_session mode")
        return self

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
