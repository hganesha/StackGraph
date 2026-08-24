"""Assemble the MCP server: catalog tools, contract tools, and dispatch."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import httpx
import mcp_types as types
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError
from mcp.server.context import ServerRequestContext
from mcp.server.lowlevel import Server

from . import __version__
from .client import StackGraphClient
from .config import Settings
from .descriptions import DEFAULT_EXCLUDED_TOOLSETS, SERVER_INSTRUCTIONS
from .errors import ConfigurationError, ToolInputError, UnknownToolError, format_http_error
from .formatting import render_json, render_response
from .spec import Contract, iter_tags, load_contract
from .tools import (
    DESCRIBE_OPERATION_TOOL,
    ToolDefinition,
    build_input_schema,
    build_tools,
    select_tools,
    toolset_overview,
    unknown_toolsets,
)

logger = logging.getLogger("stackgraph_mcp")

SERVER_NAME = "stackgraph_mcp"
LIST_OPERATIONS_TOOL = "stackgraph_list_operations"

LIST_OPERATIONS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "toolset": {
            "type": "string",
            "description": "Restrict to one toolset (contract tag), e.g. 'graph-intelligence'.",
        },
        "query": {
            "type": "string",
            "description": "Case-insensitive substring matched against tool name, summary, and HTTP path.",
        },
        "limit": {
            "type": "integer",
            "minimum": 1,
            "maximum": 200,
            "default": 50,
            "description": "Maximum operations to return.",
        },
    },
    "additionalProperties": False,
}

DESCRIBE_OPERATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "tool": {
            "type": "string",
            "minLength": 1,
            "description": "Tool name ('stackgraph_get_graph_neighborhood') or contract operationId ('getGraphNeighborhood').",
        },
    },
    "required": ["tool"],
    "additionalProperties": False,
}


def _validation_message(tool: str, errors: list[ValidationError]) -> str:
    """Turn schema violations into one line an agent can act on."""
    details = []
    for error in errors[:5]:
        location = ".".join(str(part) for part in error.absolute_path) or "<root>"
        details.append(f"{location}: {error.message}")
    suffix = f" (+{len(errors) - 5} more)" if len(errors) > 5 else ""
    return (
        f"Error: invalid arguments for {tool}. "
        + "; ".join(details)
        + suffix
        + f". Call {DESCRIBE_OPERATION_TOOL} with tool='{tool}' for the full argument schema."
    )


class StackGraphMCP:
    """Serves one MCP tool per StackGraph API operation, plus two catalog tools."""

    def __init__(
        self,
        settings: Settings,
        contract: Contract,
        definitions: tuple[ToolDefinition, ...],
        *,
        client: StackGraphClient | None = None,
    ) -> None:
        self._settings = settings
        self._contract = contract
        self._definitions = definitions
        self._by_name = {definition.name: definition for definition in definitions}
        self._by_operation_id = {definition.operation.operation_id: definition for definition in definitions}
        self._validators: dict[str, Draft202012Validator] = {}
        self._client = client
        self._owns_client = client is None

    @property
    def definitions(self) -> tuple[ToolDefinition, ...]:
        return self._definitions

    @property
    def client(self) -> StackGraphClient:
        if self._client is None:
            raise RuntimeError("The StackGraph client is not open. Use the server lifespan or pass a client.")
        return self._client

    async def aopen(self) -> None:
        """Open the HTTP client if this server owns one."""
        if self._client is None:
            self._client = StackGraphClient(
                self._settings,
                base_url=self._settings.resolve_base_url(self._contract.base_path),
            )

    async def aclose(self) -> None:
        """Close the HTTP client if this server owns it."""
        if self._client is not None and self._owns_client:
            await self._client.aclose()
            self._client = None

    # -- tool listing ------------------------------------------------------

    def _catalog_tools(self) -> list[types.Tool]:
        return [
            types.Tool(
                name=LIST_OPERATIONS_TOOL,
                title="List StackGraph Operations",
                description=(
                    "List the StackGraph API operations this server exposes, optionally filtered by "
                    "toolset or keyword. Use it to find the right tool before calling it.\n\n"
                    "Returns the exposed toolsets and matching operations with their HTTP signatures."
                ),
                input_schema=LIST_OPERATIONS_SCHEMA,
                annotations=types.ToolAnnotations(
                    title="List StackGraph Operations",
                    read_only_hint=True,
                    destructive_hint=False,
                    idempotent_hint=True,
                    open_world_hint=False,
                ),
            ),
            types.Tool(
                name=DESCRIBE_OPERATION_TOOL,
                title="Describe StackGraph Operation",
                description=(
                    "Return the complete request and response JSON Schema for one operation, including "
                    "every referenced component. Call this before sending a request body you are unsure "
                    "about, or to learn the shape of a response before requesting it."
                ),
                input_schema=DESCRIBE_OPERATION_SCHEMA,
                annotations=types.ToolAnnotations(
                    title="Describe StackGraph Operation",
                    read_only_hint=True,
                    destructive_hint=False,
                    idempotent_hint=True,
                    open_world_hint=False,
                ),
            ),
        ]

    def _operation_tool(self, definition: ToolDefinition) -> types.Tool:
        return types.Tool(
            name=definition.name,
            title=definition.title,
            description=definition.description,
            input_schema=definition.input_schema,
            annotations=types.ToolAnnotations(
                title=definition.title,
                read_only_hint=definition.read_only,
                destructive_hint=definition.destructive,
                idempotent_hint=definition.idempotent,
                open_world_hint=True,
            ),
            meta={"stackgraph": {"toolset": definition.toolset, "operationId": definition.operation.operation_id}},
        )

    def list_tools(self) -> list[types.Tool]:
        """Every tool this server exposes: the two catalog tools, then the operations."""
        return self._catalog_tools() + [self._operation_tool(d) for d in self._definitions]

    async def handle_list_tools(
        self,
        ctx: ServerRequestContext[None],
        params: types.PaginatedRequestParams | None,
    ) -> types.ListToolsResult:
        """MCP ``tools/list`` handler."""
        return types.ListToolsResult(tools=self.list_tools())

    # -- catalog tools -----------------------------------------------------

    def _resolve(self, reference: str) -> ToolDefinition:
        """Look up a definition by tool name or by contract operation id."""
        definition = self._by_name.get(reference) or self._by_operation_id.get(reference)
        if definition is None:
            raise UnknownToolError(
                f"Error: no exposed operation named {reference!r}. "
                f"Call {LIST_OPERATIONS_TOOL} to see what this server exposes."
            )
        return definition

    def list_operations(self, arguments: dict[str, Any]) -> str:
        """Render the filtered operation catalog."""
        toolset = arguments.get("toolset")
        query = (arguments.get("query") or "").strip().lower()
        limit = int(arguments.get("limit", 50))

        matches = []
        for definition in self._definitions:
            if toolset and definition.toolset != toolset:
                continue
            if query and query not in f"{definition.name} {definition.title} {definition.operation.path}".lower():
                continue
            matches.append(
                {
                    "tool": definition.name,
                    "toolset": definition.toolset,
                    "method": definition.operation.method,
                    "path": definition.operation.path,
                    "summary": definition.title,
                    "read_only": definition.read_only,
                }
            )

        payload = {
            "toolsets": toolset_overview(self._definitions),
            "matched": len(matches),
            "returned": min(len(matches), limit),
            "operations": matches[:limit],
        }
        if toolset and not any(entry["toolset"] == toolset for entry in payload["toolsets"]):
            payload["hint"] = (
                f"Toolset {toolset!r} is not exposed. Available: "
                f"{', '.join(entry['toolset'] for entry in payload['toolsets'])}."
            )
        return render_json(payload, max_chars=self._settings.max_response_chars)

    def describe_operation(self, arguments: dict[str, Any]) -> str:
        """Render the full request and response schema for one operation.

        The input schema is rebuilt without the ``tools/list`` size cap, so this is where
        an agent gets the body schema that was elided from the tool listing.
        """
        definition = self._resolve(str(arguments["tool"]))
        operation = definition.operation
        input_schema = build_input_schema(self._contract, operation, tool=definition.name)

        response_schema = operation.response_schema
        if response_schema is not None:
            defs = self._contract.defs_for(response_schema)
            if defs:
                response_schema = {**response_schema, "$defs": defs}

        payload = {
            "tool": definition.name,
            "operation_id": operation.operation_id,
            "toolset": definition.toolset,
            "http": operation.signature,
            "description": definition.description,
            "read_only": definition.read_only,
            "destructive": definition.destructive,
            "input_schema": input_schema,
            "response_schema": response_schema,
        }
        return render_json(payload, max_chars=self._settings.max_response_chars)

    # -- dispatch ----------------------------------------------------------

    def _validator(self, definition: ToolDefinition) -> Draft202012Validator:
        validator = self._validators.get(definition.name)
        if validator is None:
            validator = Draft202012Validator(definition.input_schema)
            self._validators[definition.name] = validator
        return validator

    def validate(self, definition: ToolDefinition, arguments: dict[str, Any]) -> None:
        """Validate tool arguments against the operation's schema.

        Args:
            definition: The tool being called.
            arguments: Raw arguments supplied by the client.

        Raises:
            ToolInputError: If the arguments violate the schema.
        """
        errors = sorted(self._validator(definition).iter_errors(arguments), key=lambda error: list(error.absolute_path))
        if errors:
            raise ToolInputError(_validation_message(definition.name, errors))

    async def call(self, name: str, arguments: dict[str, Any]) -> str:
        """Run one tool and return its text output.

        Args:
            name: The tool name requested by the client.
            arguments: Raw arguments supplied by the client.

        Returns:
            str: Rendered tool output.

        Raises:
            UnknownToolError: If ``name`` is not exposed.
            ToolInputError: If ``arguments`` fail schema validation.
        """
        if name == LIST_OPERATIONS_TOOL:
            self._validate_against(LIST_OPERATIONS_TOOL, LIST_OPERATIONS_SCHEMA, arguments)
            return self.list_operations(arguments)
        if name == DESCRIBE_OPERATION_TOOL:
            self._validate_against(DESCRIBE_OPERATION_TOOL, DESCRIBE_OPERATION_SCHEMA, arguments)
            return self.describe_operation(arguments)

        definition = self._resolve(name)
        self.validate(definition, arguments)

        try:
            _, response = await self.client.call(definition.operation, arguments)
        except httpx.HTTPStatusError as exc:
            return format_http_error(exc, method=definition.operation.method, path=str(exc.request.url.path))
        except httpx.HTTPError as exc:
            path = self.client.build_path(definition.operation, arguments)
            return format_http_error(exc, method=definition.operation.method, path=path)

        return render_response(response, max_chars=self._settings.max_response_chars)

    def _validate_against(self, tool: str, schema: dict[str, Any], arguments: dict[str, Any]) -> None:
        errors = sorted(
            Draft202012Validator(schema).iter_errors(arguments),
            key=lambda error: list(error.absolute_path),
        )
        if errors:
            raise ToolInputError(_validation_message(tool, errors))

    async def handle_call_tool(
        self,
        ctx: ServerRequestContext[None],
        params: types.CallToolRequestParams,
    ) -> types.CallToolResult:
        """MCP ``tools/call`` handler.

        Tool-level failures are returned as ``isError`` results rather than protocol
        errors so the calling model can read the message and correct itself.
        """
        arguments = dict(params.arguments or {})
        try:
            text = await self.call(params.name, arguments)
        except (UnknownToolError, ToolInputError) as exc:
            return types.CallToolResult(content=[types.TextContent(type="text", text=str(exc))], is_error=True)
        except Exception as exc:  # noqa: BLE001 - surface any failure to the model, not the transport
            logger.exception("Tool %s failed", params.name)
            return types.CallToolResult(
                content=[types.TextContent(type="text", text=f"Error: {params.name} failed: {type(exc).__name__}: {exc}")],
                is_error=True,
            )

        is_error = text.startswith("Error: ")
        return types.CallToolResult(content=[types.TextContent(type="text", text=text)], is_error=is_error)


def build_app(settings: Settings, *, client: StackGraphClient | None = None) -> StackGraphMCP:
    """Load the contract and build the tool surface for ``settings``.

    Args:
        settings: Runtime settings.
        client: Optional pre-built client, used by tests to inject a transport.

    Returns:
        StackGraphMCP: The configured tool surface.

    Raises:
        ConfigurationError: If the contract is unusable, an unknown toolset was
            requested, or the filters leave no tools to expose.
    """
    contract = load_contract(settings.openapi_path)
    definitions = build_tools(contract, max_body_schema_chars=settings.max_body_schema_chars)

    unknown = unknown_toolsets(settings.toolset_names, iter_tags(contract.operations))
    if unknown:
        available = ", ".join(iter_tags(contract.operations))
        raise ConfigurationError(
            f"STACKGRAPH_MCP_TOOLSETS names unknown toolsets: {', '.join(unknown)}. Available: {available}."
        )

    selected = select_tools(
        definitions,
        toolsets=settings.toolset_names,
        excluded_toolsets=DEFAULT_EXCLUDED_TOOLSETS,
        read_only=settings.read_only,
    )
    if not selected:
        raise ConfigurationError(
            "The configured filters expose no tools. Relax STACKGRAPH_MCP_TOOLSETS or "
            "STACKGRAPH_MCP_READ_ONLY."
        )
    return StackGraphMCP(settings, contract, selected, client=client)


def create_server(app: StackGraphMCP) -> Server[None]:
    """Wrap a :class:`StackGraphMCP` in an MCP low-level server with a managed client.

    Args:
        app: The tool surface to serve.

    Returns:
        Server[None]: A server whose lifespan owns the HTTP client.
    """

    @asynccontextmanager
    async def lifespan(_: Server[None]) -> AsyncIterator[None]:
        await app.aopen()
        try:
            yield None
        finally:
            await app.aclose()

    exposed = ", ".join(sorted({definition.toolset for definition in app.definitions}))
    instructions = f"{SERVER_INSTRUCTIONS}\nExposed toolsets: {exposed}."

    return Server(
        SERVER_NAME,
        version=__version__,
        title="StackGraph",
        instructions=instructions,
        lifespan=lifespan,
        on_list_tools=app.handle_list_tools,
        on_call_tool=app.handle_call_tool,
    )


__all__ = [
    "DESCRIBE_OPERATION_TOOL",
    "LIST_OPERATIONS_TOOL",
    "SERVER_NAME",
    "StackGraphMCP",
    "build_app",
    "create_server",
]
