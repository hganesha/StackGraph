"""Parse the frozen StackGraph OpenAPI contract into MCP-ready operation descriptors.

The contract at ``stackgraph-foundation/contracts/v1/openapi.json`` is OpenAPI 3.1,
whose schema objects are JSON Schema 2020-12 documents. They can therefore be handed
to MCP clients as tool input schemas without translation -- the only rewriting needed
is moving ``#/components/schemas/*`` references into a self-contained ``$defs`` block.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from .errors import ConfigurationError

HTTP_METHODS: tuple[str, ...] = ("get", "post", "put", "patch", "delete")
COMPONENT_PREFIX = "#/components/schemas/"
DEFS_PREFIX = "#/$defs/"

JsonSchema = dict[str, Any]


def _rewrite_refs(value: Any) -> Any:
    """Return a copy of ``value`` with component references pointing at ``$defs``."""
    if isinstance(value, dict):
        rewritten: dict[str, Any] = {}
        for key, item in value.items():
            if key == "$ref" and isinstance(item, str) and item.startswith(COMPONENT_PREFIX):
                rewritten[key] = DEFS_PREFIX + item[len(COMPONENT_PREFIX) :]
            else:
                rewritten[key] = _rewrite_refs(item)
        return rewritten
    if isinstance(value, list):
        return [_rewrite_refs(item) for item in value]
    return value


def _referenced_components(value: Any, found: set[str]) -> None:
    """Accumulate component schema names referenced anywhere inside ``value``.

    Both spellings are recognised: the raw ``#/components/schemas/*`` of the contract
    and the ``#/$defs/*`` that :func:`_rewrite_refs` produces, so the closure can be
    computed from already-rewritten operation schemas.
    """
    if isinstance(value, dict):
        ref = value.get("$ref")
        if isinstance(ref, str):
            for prefix in (COMPONENT_PREFIX, DEFS_PREFIX):
                if ref.startswith(prefix):
                    found.add(ref[len(prefix) :])
                    break
        for item in value.values():
            _referenced_components(item, found)
    elif isinstance(value, list):
        for item in value:
            _referenced_components(item, found)


def _strip_keys(value: Any, keys: frozenset[str]) -> Any:
    """Drop noisy generated keys (FastAPI ``title``s) from an inline schema."""
    if isinstance(value, dict):
        return {key: _strip_keys(item, keys) for key, item in value.items() if key not in keys}
    if isinstance(value, list):
        return [_strip_keys(item, keys) for item in value]
    return value


@dataclass(frozen=True, slots=True)
class Parameter:
    """A single path or query parameter of an operation."""

    name: str
    location: str
    required: bool
    schema: JsonSchema


@dataclass(frozen=True, slots=True)
class Operation:
    """One HTTP operation from the contract, plus everything needed to invoke it."""

    operation_id: str
    method: str
    path: str
    summary: str
    tag: str
    parameters: tuple[Parameter, ...]
    body_schema: JsonSchema | None
    body_required: bool
    response_schema: JsonSchema | None

    @property
    def path_parameters(self) -> tuple[Parameter, ...]:
        return tuple(parameter for parameter in self.parameters if parameter.location == "path")

    @property
    def query_parameters(self) -> tuple[Parameter, ...]:
        return tuple(parameter for parameter in self.parameters if parameter.location == "query")

    @property
    def signature(self) -> str:
        """A one-line ``METHOD /path`` rendering used in tool descriptions."""
        return f"{self.method} {self.path}"


@dataclass(frozen=True, slots=True)
class Contract:
    """The parsed contract: its operations and the component schemas they reference."""

    title: str
    version: str
    base_path: str
    operations: tuple[Operation, ...]
    components: Mapping[str, JsonSchema]

    def defs_for(self, *schemas: JsonSchema | None) -> dict[str, JsonSchema]:
        """Return the transitive ``$defs`` closure required by ``schemas``.

        Args:
            *schemas: Schemas that may reference ``#/components/schemas/*``. ``None``
                entries are ignored so callers can pass optional bodies directly.

        Returns:
            dict[str, JsonSchema]: Component name -> schema, with every nested
            reference rewritten to ``#/$defs/*`` and every transitively referenced
            component included. Empty when nothing is referenced.
        """
        pending: set[str] = set()
        for schema in schemas:
            if schema is not None:
                _referenced_components(schema, pending)

        resolved: dict[str, JsonSchema] = {}
        while pending:
            name = pending.pop()
            if name in resolved:
                continue
            component = self.components.get(name)
            if component is None:
                continue
            resolved[name] = _rewrite_refs(component)
            _referenced_components(component, pending)
            pending -= resolved.keys()
        return resolved


def _response_schema(operation: Mapping[str, Any]) -> JsonSchema | None:
    """Extract the JSON schema of the operation's success response, if it declares one."""
    for status in ("200", "201", "202", "204"):
        response = operation.get("responses", {}).get(status)
        if not isinstance(response, dict):
            continue
        content = response.get("content", {}).get("application/json")
        if isinstance(content, dict) and isinstance(content.get("schema"), dict):
            return _rewrite_refs(content["schema"])
    return None


def _body_schema(operation: Mapping[str, Any]) -> tuple[JsonSchema | None, bool]:
    """Extract the JSON request body schema and whether it is required."""
    request_body = operation.get("requestBody")
    if not isinstance(request_body, dict):
        return None, False
    content = request_body.get("content", {}).get("application/json")
    if not isinstance(content, dict) or not isinstance(content.get("schema"), dict):
        return None, False
    return _rewrite_refs(content["schema"]), bool(request_body.get("required", False))


def _parameters(operation: Mapping[str, Any]) -> tuple[Parameter, ...]:
    """Extract path and query parameters, dropping generated titles from their schemas."""
    parsed: list[Parameter] = []
    for raw in operation.get("parameters", []):
        if not isinstance(raw, dict) or raw.get("in") not in ("path", "query"):
            continue
        schema = _rewrite_refs(_strip_keys(raw.get("schema", {}), frozenset({"title"})))
        description = raw.get("description")
        if description and "description" not in schema:
            schema = {**schema, "description": description}
        parsed.append(
            Parameter(
                name=raw["name"],
                location=raw["in"],
                required=bool(raw.get("required", raw.get("in") == "path")),
                schema=schema,
            )
        )
    return tuple(parsed)


def parse_contract(document: Mapping[str, Any]) -> Contract:
    """Parse a loaded OpenAPI document into a :class:`Contract`.

    Args:
        document: A decoded OpenAPI 3.1 document with ``paths`` and ``info``.

    Returns:
        Contract: Operations sorted by operation id, plus the component schema map.

    Raises:
        ConfigurationError: If the document declares no invocable operations.
    """
    info = document.get("info", {})
    servers = document.get("servers") or [{"url": ""}]
    base_path = str(servers[0].get("url", "")).rstrip("/")
    components: dict[str, JsonSchema] = dict(document.get("components", {}).get("schemas", {}))

    operations: list[Operation] = []
    for path, item in document.get("paths", {}).items():
        if not isinstance(item, dict):
            continue
        for method, raw in item.items():
            if method not in HTTP_METHODS or not isinstance(raw, dict):
                continue
            operation_id = raw.get("operationId")
            if not operation_id:
                continue
            body_schema, body_required = _body_schema(raw)
            tags = raw.get("tags") or []
            operations.append(
                Operation(
                    operation_id=operation_id,
                    method=method.upper(),
                    path=path,
                    summary=str(raw.get("summary") or operation_id),
                    tag=str(tags[0]) if tags else "other",
                    parameters=_parameters(raw),
                    body_schema=body_schema,
                    body_required=body_required,
                    response_schema=_response_schema(raw),
                )
            )

    if not operations:
        raise ConfigurationError(
            "The OpenAPI document declares no operations with an operationId. "
            "Regenerate it with 'python scripts/export_openapi.py <path>' from apps/api."
        )

    operations.sort(key=lambda operation: operation.operation_id)
    return Contract(
        title=str(info.get("title", "StackGraph API")),
        version=str(info.get("version", "unknown")),
        base_path=base_path,
        operations=tuple(operations),
        components=components,
    )


def load_contract(path: Path) -> Contract:
    """Read and parse the OpenAPI contract from disk.

    Args:
        path: Filesystem path to ``openapi.json``.

    Returns:
        Contract: The parsed contract.

    Raises:
        ConfigurationError: If the file is missing or is not valid JSON.
    """
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigurationError(
            f"OpenAPI contract not found at {path}. Point STACKGRAPH_MCP_OPENAPI_PATH at "
            "stackgraph-foundation/contracts/v1/openapi.json."
        ) from exc
    except json.JSONDecodeError as exc:
        raise ConfigurationError(f"OpenAPI contract at {path} is not valid JSON: {exc}") from exc

    if not isinstance(document, dict):
        raise ConfigurationError(f"OpenAPI contract at {path} must be a JSON object.")
    return parse_contract(document)


def iter_tags(operations: Iterable[Operation]) -> tuple[str, ...]:
    """Return the sorted set of tags across ``operations``."""
    return tuple(sorted({operation.tag for operation in operations}))
