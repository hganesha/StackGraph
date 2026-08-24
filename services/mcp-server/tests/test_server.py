"""End-to-end tool dispatch against a mocked StackGraph API."""

from __future__ import annotations

import json
from typing import Any, Callable

import httpx
import pytest

from stackgraph_mcp.config import Settings
from stackgraph_mcp.errors import ConfigurationError
from stackgraph_mcp.server import DESCRIBE_OPERATION_TOOL, LIST_OPERATIONS_TOOL, StackGraphMCP, build_app

Build = Callable[..., StackGraphMCP]


def json_ok(payload: Any, status: int = 200) -> Callable[[httpx.Request], httpx.Response]:
    return lambda request: httpx.Response(status, json=payload)


def record(payload: Any, seen: list[httpx.Request]) -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=payload)

    return handler


async def test_catalog_tools_are_listed_first(build_server: Build) -> None:
    app = build_server(json_ok({}))

    tools = app.list_tools()

    assert [tool.name for tool in tools[:2]] == [LIST_OPERATIONS_TOOL, DESCRIBE_OPERATION_TOOL]
    assert len(tools) == len(app.definitions) + 2
    assert all(tool.input_schema["type"] == "object" for tool in tools)


async def test_a_get_sends_path_and_query_parameters(build_server: Build) -> None:
    seen: list[httpx.Request] = []
    app = build_server(record({"nodes": []}, seen))

    output = await app.call(
        "stackgraph_get_graph_neighborhood",
        {"center_id": "3f1c9a2e-0000-4000-8000-000000000001", "depth": 2, "namespace": ["TECHNOLOGY", "OSS"]},
    )

    request = seen[0]
    assert request.method == "GET"
    assert request.url.path == "/api/v1/graph/neighborhood"
    assert request.url.params.get("depth") == "2"
    assert request.url.params.get_list("namespace") == ["TECHNOLOGY", "OSS"]
    assert request.headers["Authorization"] == "Bearer test-token"
    assert json.loads(output) == {"nodes": []}


async def test_path_parameters_are_substituted_and_escaped(build_server: Build) -> None:
    seen: list[httpx.Request] = []
    app = build_server(record({"key": "cloud-native"}, seen))

    await app.call("stackgraph_get_architecture_reference_model", {"key": "cloud native/v2"})

    assert seen[0].url.raw_path == b"/api/v1/canvas/reference-models/cloud%20native%2Fv2"


async def test_a_post_sends_the_body_property_as_json(build_server: Build) -> None:
    seen: list[httpx.Request] = []
    app = build_server(record({"matches": []}, seen))

    await app.call("stackgraph_semantic_search", {"body": {"query": "payment processing", "limit": 5}})

    request = seen[0]
    assert request.method == "POST"
    assert request.url.path == "/api/v1/search/semantic"
    assert json.loads(request.content) == {"query": "payment processing", "limit": 5}


async def test_invalid_arguments_are_rejected_before_any_request(build_server: Build) -> None:
    seen: list[httpx.Request] = []
    app = build_server(record({}, seen))

    result = await app.handle_call_tool(None, _params("stackgraph_get_graph_neighborhood", {"depth": 9}))

    assert result.is_error is True
    text = result.content[0].text
    assert "center_id" in text, "the missing required parameter is named"
    assert "9 is greater than the maximum of 2" in text, "the out-of-range value is explained"
    assert DESCRIBE_OPERATION_TOOL in text
    assert seen == [], "validation happens before the request is sent"


async def test_unknown_arguments_are_rejected(build_server: Build) -> None:
    app = build_server(json_ok({}))

    result = await app.handle_call_tool(None, _params("stackgraph_get_estate_summary", {"tenant": "acme"}))

    assert result.is_error is True
    assert "Additional properties are not allowed" in result.content[0].text


async def test_unknown_tool_points_at_the_catalog(build_server: Build) -> None:
    app = build_server(json_ok({}))

    result = await app.handle_call_tool(None, _params("stackgraph_not_a_tool", {}))

    assert result.is_error is True
    assert LIST_OPERATIONS_TOOL in result.content[0].text


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (401, "STACKGRAPH_MCP_API_TOKEN"),
        (403, "capability"),
        (404, "List the parent collection"),
        (429, "Rate limit exceeded"),
        (503, "stackgraph_health_ready"),
    ],
)
async def test_http_failures_explain_the_remedy(build_server: Build, status: int, expected: str) -> None:
    app = build_server(lambda request: httpx.Response(status, json={"error": {"code": "X", "message": "nope"}}))

    result = await app.handle_call_tool(None, _params("stackgraph_get_estate_summary", {}))

    assert result.is_error is True
    assert expected in result.content[0].text


async def test_connection_failures_name_the_base_url_setting(build_server: Build) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    app = build_server(handler)

    result = await app.handle_call_tool(None, _params("stackgraph_get_estate_summary", {}))

    assert result.is_error is True
    assert "STACKGRAPH_MCP_API_BASE_URL" in result.content[0].text


async def test_empty_responses_report_the_status(build_server: Build) -> None:
    app = build_server(lambda request: httpx.Response(204))

    output = await app.call("stackgraph_remove_member", {"id": "3f1c9a2e-0000-4000-8000-000000000001"})

    assert output == "OK (204). The operation returned no content."


async def test_large_responses_are_truncated_with_guidance(build_server: Build) -> None:
    app = build_server(json_ok({"items": ["x" * 200] * 200}), max_response_chars=1000)

    output = await app.call("stackgraph_get_estate_summary", {})

    assert len(output) < 1500
    assert "truncated after 1000" in output


async def test_list_operations_filters_by_toolset_and_keyword(build_server: Build) -> None:
    app = build_server(json_ok({}))

    payload = json.loads(await app.call(LIST_OPERATIONS_TOOL, {"toolset": "graph-intelligence", "query": "anomal"}))

    assert payload["matched"] == 1
    assert payload["operations"][0]["tool"] == "stackgraph_list_graph_intelligence_anomalies"
    assert any(entry["toolset"] == "graph-intelligence" for entry in payload["toolsets"])


async def test_list_operations_flags_a_toolset_that_is_not_exposed(build_server: Build) -> None:
    app = build_server(json_ok({}))

    payload = json.loads(await app.call(LIST_OPERATIONS_TOOL, {"toolset": "authentication"}))

    assert payload["matched"] == 0
    assert "not exposed" in payload["hint"]


async def test_describe_operation_returns_both_schemas(build_server: Build) -> None:
    app = build_server(json_ok({}))

    payload = json.loads(await app.call(DESCRIBE_OPERATION_TOOL, {"tool": "semanticSearch"}))

    assert payload["tool"] == "stackgraph_semantic_search"
    assert payload["http"] == "POST /search/semantic"
    assert payload["input_schema"]["properties"]["body"]["$ref"] == "#/$defs/SemanticSearchRequest"
    assert payload["response_schema"]["$ref"] == "#/$defs/SemanticSearchResponse"
    assert "SemanticSearchResponse" in payload["response_schema"]["$defs"]


async def test_describe_operation_recovers_a_body_schema_elided_from_the_listing(build_server: Build) -> None:
    app = build_server(json_ok({}), max_body_schema_chars=4_000)
    listed = next(t for t in app.list_tools() if t.name == "stackgraph_save_business_map")
    assert "too large to inline" in listed.input_schema["properties"]["body"]["description"]

    payload = json.loads(await app.call(DESCRIBE_OPERATION_TOOL, {"tool": "stackgraph_save_business_map"}))

    body = payload["input_schema"]["properties"]["body"]
    assert "$ref" in body
    assert payload["input_schema"]["$defs"]


async def test_read_only_mode_hides_mutating_tools(build_server: Build) -> None:
    app = build_server(json_ok({}), read_only=True)

    names = {definition.name for definition in app.definitions}

    assert "stackgraph_get_estate_summary" in names
    assert "stackgraph_remove_member" not in names


def test_an_unknown_toolset_fails_startup_with_the_available_list(settings: Settings) -> None:
    with pytest.raises(ConfigurationError, match="graph-intelligence"):
        build_app(settings.model_copy(update={"toolsets": "graph-intelligence,nonsense"}))


def test_filters_that_expose_nothing_fail_startup(settings: Settings) -> None:
    with pytest.raises(ConfigurationError, match="expose no tools"):
        build_app(settings.model_copy(update={"toolsets": "identity", "read_only": True}))


def _params(name: str, arguments: dict[str, Any]):
    import mcp_types as types

    return types.CallToolRequestParams(name=name, arguments=arguments)


def test_cli_lists_tools_without_serving(capsys, monkeypatch) -> None:
    from stackgraph_mcp.__main__ import main

    monkeypatch.setenv("STACKGRAPH_MCP_TOOLSETS", "estate,session")

    assert main(["--list-tools"]) == 0

    printed = capsys.readouterr().out
    assert "stackgraph_get_estate_summary" in printed
    assert "stackgraph_remove_member" not in printed


def test_cli_reports_a_bad_environment_instead_of_crashing(capsys, monkeypatch) -> None:
    from stackgraph_mcp.__main__ import main

    monkeypatch.setenv("STACKGRAPH_MCP_TIMEOUT_SECONDS", "-4")

    assert main(["--list-tools"]) == 2
    assert "Configuration error" in capsys.readouterr().err
