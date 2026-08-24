"""Shared fixtures. Living at the rootdir also puts the package on sys.path for pytest."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import httpx
import pytest

from stackgraph_mcp.client import StackGraphClient
from stackgraph_mcp.config import Settings
from stackgraph_mcp.server import StackGraphMCP, build_app
from stackgraph_mcp.spec import Contract, load_contract

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = REPO_ROOT / "stackgraph-foundation" / "contracts" / "v1" / "openapi.json"

Handler = Callable[[httpx.Request], httpx.Response]


@pytest.fixture(scope="session")
def contract() -> Contract:
    return load_contract(CONTRACT_PATH)


@pytest.fixture
def settings() -> Settings:
    return Settings(
        api_base_url="https://stackgraph.test",
        api_token="test-token",
        openapi_path=CONTRACT_PATH,
    )


@pytest.fixture
def build_server(settings: Settings) -> Callable[..., StackGraphMCP]:
    """Build a server whose HTTP calls are answered by a caller-supplied handler."""

    def _build(handler: Handler, **overrides: object) -> StackGraphMCP:
        configured = settings.model_copy(update=overrides) if overrides else settings
        client = StackGraphClient(
            configured,
            base_url=configured.resolve_base_url("/api/v1"),
            transport=httpx.MockTransport(handler),
        )
        return build_app(configured, client=client)

    return _build
