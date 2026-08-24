"""Runtime settings for the StackGraph MCP server."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_OPENAPI_PATH = (
    Path(__file__).resolve().parents[3] / "stackgraph-foundation" / "contracts" / "v1" / "openapi.json"
)


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
