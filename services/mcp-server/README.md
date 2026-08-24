# StackGraph MCP server

An [MCP](https://modelcontextprotocol.io) server that exposes the StackGraph API to
coding agents and MCP-capable clients.

Tools are generated at startup from the frozen contract at
`stackgraph-foundation/contracts/v1/openapi.json` — one tool per operation, plus two
catalog tools. Nothing is hand-transcribed, so the tool surface cannot drift from the
API: regenerating the contract (`python scripts/export_openapi.py <path>` in `apps/api`)
is all it takes to pick up new operations.

The contract is OpenAPI 3.1, whose schema objects are already JSON Schema 2020-12, so
each operation's parameters and request body are handed to the client verbatim as the
tool's `inputSchema` (component references are relocated into a self-contained `$defs`
block). Arguments are validated against that same schema before any HTTP request is made.

## Install

```bash
python -m venv .venv && .venv/bin/pip install -r services/mcp-server/requirements.txt
```

## Configure

All settings are read from `STACKGRAPH_MCP_*` environment variables.

| Variable | Default | Purpose |
| --- | --- | --- |
| `STACKGRAPH_MCP_API_BASE_URL` | `http://localhost:8000` | Origin of the API. The contract's `/api/v1` base path is appended when absent. |
| `STACKGRAPH_MCP_API_TOKEN` | — | Bearer token sent as `Authorization`. |
| `STACKGRAPH_MCP_SESSION_COOKIE` | — | `stackgraph_session` cookie value, as an alternative to a bearer token. |
| `STACKGRAPH_MCP_OPENAPI_PATH` | the repo contract | Path to `openapi.json`. |
| `STACKGRAPH_MCP_TOOLSETS` | all but `authentication` | Comma-separated contract tags to expose. |
| `STACKGRAPH_MCP_READ_ONLY` | `false` | Expose only operations that cannot modify estate state. |
| `STACKGRAPH_MCP_TIMEOUT_SECONDS` | `30` | Per-request timeout. |
| `STACKGRAPH_MCP_MAX_RESPONSE_CHARS` | `40000` | Truncation budget for a single tool result. |
| `STACKGRAPH_MCP_MAX_BODY_SCHEMA_CHARS` | `4000` | Request-body schemas above this size are replaced in `tools/list` by a pointer to `stackgraph_describe_operation`. `0` always inlines them. |
| `STACKGRAPH_MCP_VERIFY_TLS` | `true` | Verify TLS certificates. |
| `STACKGRAPH_MCP_DATABASE_URL` | — | PostgreSQL URL used to record service heartbeats for Admin → Services & health. Set only for the deployment-managed HTTP transport (the Docker Compose service sets it); leave unset for stdio clients. |
| `STACKGRAPH_MCP_HEARTBEAT_SECONDS` | `15` | Interval between service heartbeats when a database URL is configured. |

The API accepts a bearer token or a session cookie. When neither is set, calls fail with
a 401 whose message says which variable to set — except against an API running in
development auth mode, which admits every request as a tenant admin.

## Run

Local client over stdio (the usual case):

```bash
python -m stackgraph_mcp
```

Remote, over streamable HTTP:

```bash
python -m stackgraph_mcp --transport http --host 0.0.0.0 --port 8080
```

Print the tool surface without serving:

```bash
python -m stackgraph_mcp --list-tools
```

### As a deployment service

Docker Compose runs the HTTP transport as the `mcp-server` service (published on
`127.0.0.1:8085` by default, `STACKGRAPH_MCP_PORT` to change it). It records
heartbeats so Admin → Services & health shows the endpoint's liveness, and the
page's Stop/Start control gates MCP traffic per workspace: while stopped, the
API answers MCP-originated requests with `503 SERVICE_STOPPED` and durable
state is untouched.

### Claude Code / Claude Desktop

```json
{
  "mcpServers": {
    "stackgraph": {
      "command": "/path/to/.venv/bin/python",
      "args": ["-m", "stackgraph_mcp"],
      "cwd": "/path/to/StackGraph/services/mcp-server",
      "env": {
        "STACKGRAPH_MCP_API_BASE_URL": "https://stackgraph.example.com",
        "STACKGRAPH_MCP_API_TOKEN": "…"
      }
    }
  }
}
```

## Tools

Every operation becomes `stackgraph_<operation_id in snake_case>` —
`getGraphNeighborhood` → `stackgraph_get_graph_neighborhood`. Path and query parameters
are top-level arguments under their contract names; a JSON request body is a single
`body` argument, so query and body fields can never collide.

Two tools describe the rest:

- **`stackgraph_list_operations`** — filter the catalog by toolset or keyword.
- **`stackgraph_describe_operation`** — the full request *and* response JSON Schema for
  one operation, including every referenced component. This is also where an agent
  recovers a request-body schema that was too large to inline in `tools/list`.

Toolsets are the contract's own tags: `admin`, `applications`, `architecture-canvas`,
`authentication`, `business-map`, `embeddings`, `estate`, `evidence`, `graph`,
`graph-intelligence`, `identity`, `intelligence`, `operations`, `repositories`,
`reviews`, `session`, `technologies`.

### Keeping the tool surface small

The full surface is 99 tools and roughly 85 KB of `tools/list` payload. For most agents
that is more than they need in context. Narrow it:

```bash
# read-only estate analysis
STACKGRAPH_MCP_READ_ONLY=true \
STACKGRAPH_MCP_TOOLSETS=estate,intelligence,graph,graph-intelligence,technologies,repositories,evidence \
  python -m stackgraph_mcp
```

`authentication` is excluded by default: its OIDC login and callback endpoints are
browser redirects that an agent cannot complete.

### Safety annotations

`readOnlyHint` is set from the HTTP verb, corrected for the four POST operations that
only compute (`askEstate`, `semanticSearch`, `compareCanvasProjections`,
`optimizeModernizationScenario`). `destructiveHint` is set for `DELETE`, and
`idempotentHint` for `GET`/`PUT`/`DELETE`. Clients that gate on annotations therefore
prompt on writes but not on reads.

### Errors

Tool failures come back as `isError` results rather than protocol errors, so the model
can read them and correct itself. Each names the remedy — which environment variable to
set for a 401, the capability ladder for a 403, which parameter was out of range for a
schema violation.

## Layout

| File | Role |
| --- | --- |
| `stackgraph_mcp/spec.py` | Parses the contract into operations and resolves the `$defs` closure. |
| `stackgraph_mcp/tools.py` | Turns operations into tool names, descriptions, schemas, and annotations. |
| `stackgraph_mcp/descriptions.py` | The hand-written layer: server instructions, toolset summaries, curated descriptions. |
| `stackgraph_mcp/client.py` | Async HTTP client that maps arguments onto requests. |
| `stackgraph_mcp/server.py` | Tool listing, argument validation, and dispatch. |
| `stackgraph_mcp/formatting.py` | Response rendering and truncation. |
| `stackgraph_mcp/errors.py` | Actionable error messages. |

The contract carries no operation descriptions and its summaries are title-cased
operation ids, so `descriptions.py` supplies the prose that tells an agent *when* to
reach for a tool. Operations without a curated description fall back to the contract
summary plus their HTTP signature and response payload name.

## Tests

```bash
pip install -r services/mcp-server/requirements-dev.txt
cd services/mcp-server && python -m pytest
```

The suite runs against the real contract with a mocked HTTP transport; it needs no
running API. It is not yet wired into `compose.yaml` or the CI lanes.
