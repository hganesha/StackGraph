# Local backend environment

The local backend uses FastAPI, authoritative PostgreSQL, and a local Neo4j Community deployment with the Graph Data Science plugin. Neo4j is a tenant-scoped, disposable projection; the API retains its bounded SQL graph reader as the correctness and outage fallback.

## Start

Copy `.env.example` to `.env` only when you need to override the development defaults. For the
complete application—including the standalone UI Docker image—run:

```shell
./scripts/start_docker.sh
```

This builds the database tools, API, and UI images; waits for PostgreSQL and Neo4j; applies migrations;
loads the reference cohort; projects graph changes; and health-gates the API and UI. For backend-only
work, run:

```shell
make backend-up
```

The UI is available at `http://localhost:3000`, the API at `http://localhost:8080`, interactive API
documentation at `http://localhost:8080/docs`, PostgreSQL at `localhost:5432`, Neo4j Browser at
`http://localhost:7474`, and Bolt at `localhost:7687` by default. Host
ports are configurable through `STACKGRAPH_WEB_PORT`, `STACKGRAPH_API_PORT`, and
`STACKGRAPH_DB_PORT`; container ports remain fixed.

The V0 API read models are available both at their contract paths and under the versioned `/api/v1` prefix:

- `GET /estate/summary`
- `GET /applications/{id}`
- `GET /technologies/{id}`
- `GET /modernization`
- `POST /ask`
- `GET /graph/neighborhood`
- `GET /graph-intelligence/status`
- `GET /entities/{id}/graph-metrics`
- `GET /entities/{id}/blast-radius`
- `POST /search/semantic`
- `GET /embeddings/status`
- `GET /entities/{id}/similar`
- `POST /similarity-candidates/{id}/review`
- `GET /facts/{id}/evidence`
- `POST /identity-assertions/{id}/review`
- `GET /capabilities/taxonomy`
- `GET /repositories/{id}/capabilities`
- `POST /capability-inferences/{id}/review`
- `POST /duplicate-capability-candidates/{id}/review`
- `GET /repositories/{id}/modernization-intelligence`
- `POST /modernization-candidates/{id}/review`
- `POST /modernization-recommendations/{id}/review`
- `POST /modernization-recommendations/{id}/validation-outcomes`
- `GET /intelligence/phase-3/metrics`

In `development` auth mode, the API derives the principal from `STACKGRAPH_DEFAULT_TENANT_ID` and `STACKGRAPH_DEVELOPMENT_ACTOR_KEY`. Client-supplied tenant or actor headers are ignored. Production uses provider-agnostic OIDC and a rotating `STACKGRAPH_AUTH_SESSION_KEYS_JSON` keyring; see `docs/runbooks/production-deployment.md`. `signed_session` remains available for controlled automation bearer tokens.

Graph neighborhoods accept repeatable `predicate` and `namespace` filters, `min_confidence`, and an optional `highlight_to` entity ID in addition to the frozen v1 center, depth, and limit parameters. Traversal and response nodes remain bounded to depth 2 and 50 nodes.

Neo4j projects tenant graphs for asynchronous deterministic analysis while the bounded SQL reader remains the outage and correctness fallback. Completed graph-intelligence snapshots, blast-radius paths, semantic search, and explainable application-similarity candidates are available through contextual application/technology views and Scan Health. PostgreSQL remains authoritative; see [graph and embedding intelligence operations](graph-and-embeddings-operations.md).

`STACKGRAPH_GRAPH_READ_MODE=auto` is the default: a caught-up, parity-valid tenant Neo4j deployment serves bounded neighborhoods and the API falls back to SQL on lag, outage, timeout, or discovery-cap overflow. `neo4j` keeps the same fail-closed fallback behavior, `sql` bypasses Neo4j, and `age` exists only for explicit legacy comparison. The backward-compatible `STACKGRAPH_GRAPH_AGE_TIMEOUT_SECONDS` variable currently sets the generic projected-reader timeout.

### Enable AI-backed Ask

`POST /ask` remains deterministic by default. To enable model-assisted query selection and explanation, first apply migrations and sync the versioned prompt catalog:

```shell
make ai-prompts-sync
```

Then configure a logical model route, the matching provider credential, and a tenant for local invocation auditing:

```shell
STACKGRAPH_DEFAULT_TENANT_ID=00000000-0000-4000-8000-000000000001
STACKGRAPH_AI_ASK_ENABLED=true
STACKGRAPH_AI_ROUTES_JSON={"default":{"provider":"openrouter","model":"your/model-id"}}
OPENROUTER_API_KEY=replace-me
```

The model never receives SQL access and cannot supply entity IDs. It selects one allowlisted deterministic query, the API executes that query under the authenticated tenant, and the model may explain only the returned rows and fact citations. Returned citation IDs are checked against the deterministic tool result. Provider, prompt-catalog, database-audit, context-limit, or output-validation failures use the deterministic Ask response when `STACKGRAPH_AI_ASK_FALLBACK_ENABLED=true`; disabling fallback returns `503 AI_ASK_UNAVAILABLE` instead.

## Verify

```shell
make backend-test
make backend-integration-test
make backend-verify
curl --fail http://localhost:8080/health/live
curl --fail http://localhost:8080/health/ready
```

Benchmark a representative bounded neighborhood after seeding and projection:

```shell
GRAPH_CENTER_ID=<entity-uuid> GRAPH_REQUESTS=50 \
  GRAPH_BENCHMARK_ARGS="--max-p95-ms 1000" make backend-graph-benchmark
```

The benchmark reports min/mean/p50/p95/max latency and fails if the response exceeds the 50-node contract or the optional p95 gate.

The integration suite queries the running database, exercises the HTTP read models, verifies an optimistic audited identity review, and installs a temporary evidence-backed Billing estate that covers every public read endpoint plus deterministic Ask templates. Temporary tenant data is removed after each test.

Complete repository dependency-usage snapshots automatically enqueue capability and modernization intelligence. See `docs/runbooks/capability-modernization-intelligence.md` for direct execution, queued workers, review APIs, retry behavior, and limitations.

## Seed the curated framework catalog

The checked-in foundation catalog is loaded as global curated knowledge. The loader is versioned and idempotent, writes evidence-backed facts into PostgreSQL, and fans projection deliveries out to every active tenant Neo4j deployment.

The migrator recognizes the one documented pre-canonical checksum for migration 005 only after verifying
its installed schema. Migration 014 then replaces the legacy global package-analysis uniqueness rule with
the tenant-scoped canonical rule. The historical ledger entry is preserved; every other checksum mismatch
continues to fail closed.

```shell
make database-seed-test
make database-seed
make database-seed-verify
```

`database-seed` applies pending tracked migrations before loading. Migrations can also be run independently with `make database-migrate`. Re-running the same seed version is a no-op and reports `"replayed": true`. A later seed version creates a new complete snapshot and closes the earlier current facts through the normal snapshot publication path.

## Populate the Neo4j projection

Project pending fact events after seeding:

```shell
make database-project
make database-project-verify
```

`make database-project` starts the local Neo4j deployment, registers it for the development tenant, and drains its per-tenant deliveries. The worker batches parameterized Cypher, writes stable PostgreSQL entity/fact IDs in one Neo4j transaction, and only then advances the PostgreSQL watermark. A crash between those commits safely replays the idempotent batch. Global catalog events receive one delivery per active tenant rather than sharing a single acknowledgement.

## Operate

```shell
make backend-logs
make backend-down
```

The database bootstrap scripts run only when Docker creates a fresh `stackgraph_postgres_data` volume. Removing that volume deletes all local StackGraph database data and is intentionally not wrapped in a Make target.
