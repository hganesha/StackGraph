"""Turn contract operations into MCP tool definitions."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

from .descriptions import (
    OPERATION_DESCRIPTIONS,
    READ_ONLY_POST_OPERATIONS,
    TOOLSET_SUMMARIES,
)
from .spec import Contract, JsonSchema, Operation

TOOL_PREFIX = "stackgraph_"
BODY_PROPERTY = "body"
FALLBACK_BODY_PROPERTY = "request_body"
DESCRIBE_OPERATION_TOOL = f"{TOOL_PREFIX}describe_operation"

_CAMEL_BOUNDARY = re.compile(r"(.)([A-Z][a-z]+)")
_LOWER_UPPER_BOUNDARY = re.compile(r"([a-z0-9])([A-Z])")

# Compound words the camel-case splitter would otherwise tear apart ("git_hub").
_COMPOUND_WORDS: dict[str, str] = {"GitHub": "Github"}

# FastAPI synthesises operation ids like "ready_health_ready_get" for routes that do not
# set one. Name those tools by hand rather than propagating the generated stutter.
_TOOL_NAME_OVERRIDES: dict[str, str] = {
    "callback_auth_callback_get": "stackgraph_auth_callback",
    "live_health_live_get": "stackgraph_health_live",
    "login_auth_login_get": "stackgraph_auth_login",
    "logout_auth_logout_post": "stackgraph_auth_logout",
    "ready_health_ready_get": "stackgraph_health_ready",
    "refresh_auth_refresh_post": "stackgraph_auth_refresh",
}


def tool_name(operation_id: str) -> str:
    """Derive a stable snake_case MCP tool name from an operation id.

    Args:
        operation_id: The contract's ``operationId`` (e.g. "getGraphNeighborhood").

    Returns:
        str: The prefixed tool name (e.g. "stackgraph_get_graph_neighborhood").
    """
    override = _TOOL_NAME_OVERRIDES.get(operation_id)
    if override is not None:
        return override

    normalized = operation_id
    for compound, replacement in _COMPOUND_WORDS.items():
        normalized = normalized.replace(compound, replacement)

    snake = _CAMEL_BOUNDARY.sub(r"\1_\2", normalized)
    snake = _LOWER_UPPER_BOUNDARY.sub(r"\1_\2", snake)
    snake = re.sub(r"[^0-9a-zA-Z]+", "_", snake).strip("_").lower()
    return f"{TOOL_PREFIX}{snake}"


def _schema_label(schema: JsonSchema | None) -> str | None:
    """Name the response payload when it is a reference to a named component."""
    if not schema:
        return None
    ref = schema.get("$ref")
    if isinstance(ref, str):
        return ref.rsplit("/", 1)[-1]
    if schema.get("type") == "array":
        item = _schema_label(schema.get("items"))
        return f"{item}[]" if item else None
    return None


def build_description(operation: Operation) -> str:
    """Compose the agent-facing description for one operation.

    Uses the curated text when there is one, otherwise the contract summary, and always
    appends the HTTP signature and the response payload name so an agent can correlate
    the tool with the API documentation.

    Args:
        operation: The parsed contract operation.

    Returns:
        str: A short multi-line description.
    """
    lead = OPERATION_DESCRIPTIONS.get(operation.operation_id) or operation.summary
    lines = [lead.rstrip("."), "", operation.signature]
    label = _schema_label(operation.response_schema)
    if label:
        lines[-1] += f" -> {label}"
    return "\n".join(lines)


def _root_type(contract: Contract, schema: JsonSchema) -> str | None:
    """The declared ``type`` of a schema, following a single component reference."""
    ref = schema.get("$ref")
    if isinstance(ref, str):
        component = contract.components.get(ref.rsplit("/", 1)[-1])
        return component.get("type") if isinstance(component, dict) else None
    declared = schema.get("type")
    return declared if isinstance(declared, str) else None


def _elided_body(tool: str, root_type: str | None) -> JsonSchema:
    """A placeholder for a request body whose full schema would dominate tools/list.

    Keeps whatever the contract declares about the body's outermost type so local
    validation still rejects an obviously wrong shape, and points at the tool that
    returns the rest.
    """
    placeholder: JsonSchema = {
        "description": (
            "JSON request body. Its schema is too large to inline here - call "
            f"{DESCRIBE_OPERATION_TOOL} with tool='{tool}' to get it before building the body."
        ),
    }
    if root_type is not None:
        placeholder["type"] = root_type
    return placeholder


def build_input_schema(
    contract: Contract,
    operation: Operation,
    *,
    tool: str,
    max_body_schema_chars: int = 0,
) -> JsonSchema:
    """Build the JSON Schema an MCP client validates tool arguments against.

    Path and query parameters become top-level properties under their contract names.
    A JSON request body becomes a single ``body`` object property (``request_body`` in
    the impossible case that a parameter already occupies that name), so query and body
    fields can never collide.

    Args:
        contract: The parsed contract, used to resolve the ``$defs`` closure.
        operation: The operation to describe.
        tool: The tool name, quoted in the placeholder when a body is elided.
        max_body_schema_chars: Elide the inline body schema once it and its ``$defs``
            exceed this many serialized characters. ``0`` always inlines it. Every
            ``tools/list`` response carries these schemas, so a handful of deeply nested
            admin payloads would otherwise cost more context than the rest combined.

    Returns:
        JsonSchema: A self-contained draft 2020-12 object schema.
    """
    properties: dict[str, JsonSchema] = {}
    required: list[str] = []

    for parameter in operation.parameters:
        properties[parameter.name] = parameter.schema
        if parameter.required:
            required.append(parameter.name)

    defs = contract.defs_for(*(parameter.schema for parameter in operation.parameters))

    if operation.body_schema is not None:
        key = BODY_PROPERTY if BODY_PROPERTY not in properties else FALLBACK_BODY_PROPERTY
        body = {**operation.body_schema, "description": "JSON request body."}
        body_defs = contract.defs_for(operation.body_schema)

        if max_body_schema_chars and len(json.dumps([body, body_defs])) > max_body_schema_chars:
            body = _elided_body(tool, _root_type(contract, operation.body_schema))
            body_defs = {}

        properties[key] = body
        defs.update(body_defs)
        if operation.body_required:
            required.append(key)

    schema: JsonSchema = {
        "type": "object",
        "properties": properties,
        "additionalProperties": False,
    }
    if required:
        schema["required"] = required
    if defs:
        schema["$defs"] = defs
    return schema


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    """An MCP tool backed by exactly one contract operation."""

    name: str
    title: str
    description: str
    input_schema: JsonSchema
    operation: Operation

    @property
    def toolset(self) -> str:
        return self.operation.tag

    @property
    def read_only(self) -> bool:
        return self.operation.method == "GET" or self.operation.operation_id in READ_ONLY_POST_OPERATIONS

    @property
    def destructive(self) -> bool:
        return self.operation.method == "DELETE"

    @property
    def idempotent(self) -> bool:
        return self.operation.method in ("GET", "PUT", "DELETE")


def build_tools(contract: Contract, *, max_body_schema_chars: int = 0) -> tuple[ToolDefinition, ...]:
    """Build one tool definition per contract operation.

    Args:
        contract: The parsed contract.
        max_body_schema_chars: Forwarded to :func:`build_input_schema`.

    Returns:
        tuple[ToolDefinition, ...]: Definitions ordered by tool name.

    Raises:
        ValueError: If two operations derive the same tool name, which would make the
            server's dispatch ambiguous.
    """
    definitions: list[ToolDefinition] = []
    seen: dict[str, str] = {}
    for operation in contract.operations:
        name = tool_name(operation.operation_id)
        if name in seen:
            raise ValueError(
                f"Operations {seen[name]!r} and {operation.operation_id!r} both map to tool {name!r}. "
                "Rename one operationId in the API before regenerating the contract."
            )
        seen[name] = operation.operation_id
        definitions.append(
            ToolDefinition(
                name=name,
                title=operation.summary,
                description=build_description(operation),
                input_schema=build_input_schema(
                    contract,
                    operation,
                    tool=name,
                    max_body_schema_chars=max_body_schema_chars,
                ),
                operation=operation,
            )
        )
    definitions.sort(key=lambda definition: definition.name)
    return tuple(definitions)


def select_tools(
    definitions: Iterable[ToolDefinition],
    *,
    toolsets: Sequence[str] | None,
    excluded_toolsets: Iterable[str] = (),
    read_only: bool = False,
) -> tuple[ToolDefinition, ...]:
    """Filter tool definitions down to what this server instance should expose.

    Args:
        definitions: All available definitions.
        toolsets: Explicit allow-list of contract tags. ``None`` or empty means "every
            toolset except ``excluded_toolsets``".
        excluded_toolsets: Tags dropped when ``toolsets`` is not given.
        read_only: When true, drop every tool that can modify estate state.

    Returns:
        tuple[ToolDefinition, ...]: The surviving definitions, order preserved.
    """
    allowed = {toolset.strip() for toolset in toolsets or () if toolset.strip()}
    excluded = set(excluded_toolsets)
    selected = []
    for definition in definitions:
        if allowed:
            if definition.toolset not in allowed:
                continue
        elif definition.toolset in excluded:
            continue
        if read_only and not definition.read_only:
            continue
        selected.append(definition)
    return tuple(selected)


def unknown_toolsets(toolsets: Sequence[str] | None, available: Iterable[str]) -> tuple[str, ...]:
    """Return requested toolset names that do not exist in the contract."""
    known = set(available)
    return tuple(sorted({name.strip() for name in toolsets or () if name.strip()} - known))


def toolset_overview(definitions: Iterable[ToolDefinition]) -> list[dict[str, Any]]:
    """Summarise the exposed toolsets for the catalog tool.

    Args:
        definitions: The definitions this server exposes.

    Returns:
        list[dict[str, Any]]: One entry per toolset with its name, tool count, and
        summary, sorted by name.
    """
    counts: dict[str, int] = {}
    for definition in definitions:
        counts[definition.toolset] = counts.get(definition.toolset, 0) + 1
    return [
        {
            "toolset": toolset,
            "tools": count,
            "summary": TOOLSET_SUMMARIES.get(toolset, ""),
        }
        for toolset, count in sorted(counts.items())
    ]
