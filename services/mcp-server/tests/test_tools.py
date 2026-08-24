"""Tool names, schemas, annotations, and toolset filtering."""

from __future__ import annotations

import json

import pytest
from jsonschema import Draft202012Validator

from stackgraph_mcp.descriptions import DEFAULT_EXCLUDED_TOOLSETS, TOOLSET_SUMMARIES
from stackgraph_mcp.spec import Contract, iter_tags
from stackgraph_mcp.tools import build_tools, select_tools, tool_name, unknown_toolsets


@pytest.mark.parametrize(
    ("operation_id", "expected"),
    [
        ("getGraphNeighborhood", "stackgraph_get_graph_neighborhood"),
        ("getAIProviderConfiguration", "stackgraph_get_ai_provider_configuration"),
        ("listAvailableGitHubRepositories", "stackgraph_list_available_github_repositories"),
        ("getPhase3IntelligenceMetrics", "stackgraph_get_phase3_intelligence_metrics"),
        ("ready_health_ready_get", "stackgraph_health_ready"),
    ],
)
def test_tool_names_are_readable_snake_case(operation_id: str, expected: str) -> None:
    assert tool_name(operation_id) == expected


def test_tool_names_are_unique_and_within_the_mcp_length_limit(contract: Contract) -> None:
    names = [definition.name for definition in build_tools(contract)]

    assert len(set(names)) == len(names)
    assert max(len(name) for name in names) <= 64


def test_every_input_schema_is_a_valid_2020_12_schema(contract: Contract) -> None:
    for definition in build_tools(contract):
        Draft202012Validator.check_schema(definition.input_schema)


def test_query_and_path_parameters_become_top_level_properties(contract: Contract) -> None:
    definition = next(d for d in build_tools(contract) if d.name == "stackgraph_list_similar_applications")
    schema = definition.input_schema

    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    assert "id" in schema["properties"]
    assert schema["required"] == ["id"]


def test_request_bodies_become_a_single_body_property(contract: Contract) -> None:
    definition = next(d for d in build_tools(contract) if d.name == "stackgraph_semantic_search")
    schema = definition.input_schema

    assert schema["properties"]["body"]["$ref"] == "#/$defs/SemanticSearchRequest"
    assert schema["required"] == ["body"]
    assert "SemanticSearchRequest" in schema["$defs"]


def test_oversized_request_bodies_are_elided_with_a_pointer(contract: Contract) -> None:
    definition = next(
        d
        for d in build_tools(contract, max_body_schema_chars=4_000)
        if d.name == "stackgraph_save_business_map"
    )
    body = definition.input_schema["properties"]["body"]

    assert body["type"] == "object", "the outermost type is still enforced locally"
    assert "stackgraph_describe_operation" in body["description"]
    assert len(json.dumps(definition.input_schema)) < 4_000


def test_small_request_bodies_are_still_inlined_in_full(contract: Contract) -> None:
    definition = next(
        d
        for d in build_tools(contract, max_body_schema_chars=4_000)
        if d.name == "stackgraph_semantic_search"
    )

    assert definition.input_schema["properties"]["body"]["$ref"] == "#/$defs/SemanticSearchRequest"


def test_descriptions_carry_the_http_signature_and_payload_name(contract: Contract) -> None:
    definition = next(d for d in build_tools(contract) if d.name == "stackgraph_get_estate_summary")

    assert "GET /estate/summary -> EstateSummary" in definition.description
    assert definition.description.startswith("Top-level counts and posture")


def test_annotations_classify_side_effects(contract: Contract) -> None:
    by_name = {definition.name: definition for definition in build_tools(contract)}

    assert by_name["stackgraph_get_estate_summary"].read_only is True
    assert by_name["stackgraph_semantic_search"].read_only is True, "a POST that only queries is read-only"
    assert by_name["stackgraph_invite_member"].read_only is False
    assert by_name["stackgraph_remove_member"].destructive is True
    assert by_name["stackgraph_update_scan_policy"].idempotent is True


def test_every_toolset_has_a_written_summary(contract: Contract) -> None:
    assert set(iter_tags(contract.operations)) <= set(TOOLSET_SUMMARIES)


def test_authentication_is_excluded_by_default(contract: Contract) -> None:
    definitions = build_tools(contract)

    selected = select_tools(definitions, toolsets=None, excluded_toolsets=DEFAULT_EXCLUDED_TOOLSETS)

    assert "authentication" not in {definition.toolset for definition in selected}
    assert len(selected) == len(definitions) - 4


def test_an_explicit_toolset_overrides_the_default_exclusions(contract: Contract) -> None:
    definitions = build_tools(contract)

    selected = select_tools(
        definitions,
        toolsets=["authentication"],
        excluded_toolsets=DEFAULT_EXCLUDED_TOOLSETS,
    )

    assert {definition.toolset for definition in selected} == {"authentication"}


def test_read_only_mode_drops_every_mutating_operation(contract: Contract) -> None:
    selected = select_tools(build_tools(contract), toolsets=None, read_only=True)

    assert selected
    assert all(definition.read_only for definition in selected)
    assert all(definition.operation.method in ("GET", "POST") for definition in selected)


def test_unknown_toolsets_are_reported(contract: Contract) -> None:
    assert unknown_toolsets(["graph", "nope"], iter_tags(contract.operations)) == ("nope",)
