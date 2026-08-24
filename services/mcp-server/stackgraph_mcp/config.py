"""Runtime settings for the StackGraph MCP server."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

def _default_openapi_path() -> Path:
    """The frozen contract in a repository checkout, or the image's copy elsewhere.

    Inside the Docker image the package lives at /code, too shallow for the
    repository-relative walk, and the contract ships at /contracts/v1 instead.
    """
    parents = Path(__file__).resolve().parents
    if len(parents) > 3:
        return parents[3] / "stackgraph-foundation" / "contracts" / "v1" / "openapi.json"
    return Path("/contracts/v1/openapi.json")


DEFAULT_OPENAPI_PATH = _default_openapi_path()


class Settings(BaseSettings):
    """Configuration read from ``STACKGRAPH_MCP_*`` environment variables."""

    model_config = SettingsConfigDict(
        env_prefix="STACKGRAPH_MCP_",
        case_sensitive=False,
        extra="ignore",
    )

    api_base_url: str = Field(
        default="http://localhost:8000",
        description="Origin of the StackGraph API. The contract's /api/v1 base path is appended when absent.",
    )
    api_token: str | None = Field(
        default=None,
        description="Bearer token sent as the Authorization header.",
    )
    session_cookie: str | None = Field(
        default=None,
        description="Value of the stackgraph_session cookie, as an alternative to a bearer token.",
    )
    openapi_path: Path = Field(
        default=DEFAULT_OPENAPI_PATH,
        description="Path to the frozen OpenAPI contract the tools are generated from.",
    )
    toolsets: str = Field(
        default="",
        description="Comma-separated contract tags to expose. Empty exposes every toolset except authentication.",
    )
    read_only: bool = Field(
        default=False,
        description="Expose only operations that cannot modify estate state.",
    )
    timeout_seconds: float = Field(
        default=30.0,
        ge=1.0,
        le=600.0,
        description="Per-request timeout when calling the StackGraph API.",
    )
    max_response_chars: int = Field(
        default=40_000,
        ge=1_000,
        le=1_000_000,
        description="Responses larger than this are truncated so a single call cannot flood the context.",
    )
    max_body_schema_chars: int = Field(
        default=4_000,
        ge=0,
        description=(
            "Request-body schemas larger than this are replaced in tools/list by a pointer to "
            "stackgraph_describe_operation. 0 always inlines the full schema."
        ),
    )
    verify_tls: bool = Field(
        default=True,
        description="Verify TLS certificates. Disable only against a local development server.",
    )
    database_url: str | None = Field(
        default=None,
        description=(
            "PostgreSQL URL used to record service heartbeats for Admin -> Services & health. "
            "Set only for the deployment-managed HTTP transport; leave unset for stdio clients."
        ),
    )
    heartbeat_seconds: float = Field(
        default=15.0,
        ge=5.0,
        le=300.0,
        description="Interval between service heartbeats when database_url is configured.",
    )

    @field_validator("api_base_url")
    @classmethod
    def _strip_trailing_slash(cls, value: str) -> str:
        return value.rstrip("/")

    @property
    def toolset_names(self) -> tuple[str, ...]:
        """The requested toolsets, empty when the caller did not restrict them."""
        return tuple(name.strip() for name in self.toolsets.split(",") if name.strip())

    def resolve_base_url(self, contract_base_path: str) -> str:
        """Join the configured origin with the contract's base path.

        Callers commonly set the origin only (``http://localhost:8000``), but the
        contract serves everything under ``/api/v1``. Appending it here means both
        ``http://localhost:8000`` and ``http://localhost:8000/api/v1`` work.

        Args:
            contract_base_path: ``servers[0].url`` from the contract (e.g. "/api/v1").

        Returns:
            str: The absolute base URL requests are made against, without a trailing slash.
        """
        base_path = contract_base_path.rstrip("/")
        if not base_path or self.api_base_url.endswith(base_path):
            return self.api_base_url
        return f"{self.api_base_url}{base_path}"
