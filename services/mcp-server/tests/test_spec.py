"""The contract parses into operations that carry everything needed to call them."""

from __future__ import annotations

from typing import Any

import pytest

from stackgraph_mcp.errors import ConfigurationError
from stackgraph_mcp.spec import Contract, load_contract, parse_contract


def test_every_contract_operation_is_parsed(contract: Contract) -> None:
    assert contract.title == "StackGraph API"
    assert contract.base_path == "/api/v1"
    assert len(contract.operations) == 102
    assert len({operation.operation_id for operation in contract.operations}) == len(contract.operations)


def test_parameters_keep_constraints_and_drop_generated_titles(contract: Contract) -> None:
    operation = next(o for o in contract.operations if o.operation_id == "getGraphNeighborhood")

    depth = next(parameter for parameter in operation.query_parameters if parameter.name == "depth")
    assert depth.required is False
    assert depth.schema == {"type": "integer", "default": 1, "minimum": 1, "maximum": 2}

    center = next(parameter for parameter in operation.query_parameters if parameter.name == "center_id")
    assert center.required is True
    assert center.schema == {"type": "string", "format": "uuid"}


def test_path_parameters_are_separated_from_query_parameters(contract: Contract) -> None:
    operation = next(o for o in contract.operations if o.operation_id == "listSimilarApplications")

    assert [parameter.name for parameter in operation.path_parameters] == ["id"]
    assert "id" not in {parameter.name for parameter in operation.query_parameters}
    assert operation.signature == "GET /entities/{id}/similar"


def test_request_bodies_are_extracted(contract: Contract) -> None:
    operation = next(o for o in contract.operations if o.operation_id == "semanticSearch")

    assert operation.body_required is True
    assert operation.body_schema == {"$ref": "#/$defs/SemanticSearchRequest"}


def test_defs_closure_resolves_every_reference(contract: Contract) -> None:
    """No generated schema may point at a component that is not carried alongside it."""

    def refs(value: Any, found: set[str]) -> None:
        if isinstance(value, dict):
            ref = value.get("$ref")
            if isinstance(ref, str):
                found.add(ref)
            for item in value.values():
                refs(item, found)
        elif isinstance(value, list):
            for item in value:
                refs(item, found)

    for operation in contract.operations:
        schemas = [operation.body_schema, operation.response_schema]
        schemas.extend(parameter.schema for parameter in operation.parameters)
        defs = contract.defs_for(*schemas)

        found: set[str] = set()
        for schema in schemas:
            refs(schema, found)
        refs(defs, found)

        for reference in found:
            assert reference.startswith("#/$defs/"), f"{operation.operation_id} leaks {reference}"
            assert reference.removeprefix("#/$defs/") in defs, f"{operation.operation_id} misses {reference}"


def test_recursive_components_do_not_hang(contract: Contract) -> None:
    """defs_for walks references iteratively, so a self-referential schema terminates."""
    recursive = Contract(
        title="t",
        version="1",
        base_path="",
        operations=contract.operations,
        components={
            "Node": {
                "type": "object",
                "properties": {"children": {"items": {"$ref": "#/components/schemas/Node"}, "type": "array"}},
            }
        },
    )

    defs = recursive.defs_for({"$ref": "#/components/schemas/Node"})

    assert defs["Node"]["properties"]["children"]["items"] == {"$ref": "#/$defs/Node"}


def test_missing_contract_names_the_fix(tmp_path) -> None:
    with pytest.raises(ConfigurationError, match="STACKGRAPH_MCP_OPENAPI_PATH"):
        load_contract(tmp_path / "absent.json")


def test_document_without_operations_is_rejected() -> None:
    with pytest.raises(ConfigurationError, match="no operations"):
        parse_contract({"info": {"title": "empty"}, "paths": {}})
