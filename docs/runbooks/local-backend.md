# Local backend environment

The local backend uses FastAPI for the API and the official Apache AGE image for PostgreSQL 16 plus AGE 1.6.0. PostgreSQL is authoritative; the `stackgraph` AGE graph is initialized as an asynchronous projection target.

## Start

Copy `.env.example` to `.env` only when you need to override the development defaults, then run:

```shell
make backend-up
```

The API is available at `http://localhost:8080`, interactive API documentation at `http://localhost:8080/docs`, and PostgreSQL at `localhost:5432` by default. The host API port is intentionally configurable through `STACKGRAPH_API_PORT`; the container always listens on port 8000.

The V0 API read models are available both at their contract paths and under the versioned `/api/v1` prefix:

- `GET /estate/summary`
- `GET /applications/{id}`
- `GET /technologies/{id}`
- `GET /modernization`
- `POST /ask`
- `GET /graph/neighborhood`
- `GET /facts/{id}/evidence`
- `POST /identity-assertions/{id}/review`

In `development` auth mode, the API derives the principal from `STACKGRAPH_DEFAULT_TENANT_ID` and `STACKGRAPH_DEVELOPMENT_ACTOR_KEY`. Client-supplied tenant or actor headers are ignored. For a deployed environment, set `STACKGRAPH_AUTH_MODE=signed_session` and configure a random `STACKGRAPH_AUTH_SESSION_SECRET` of at least 32 characters; the API then requires a signed bearer session containing the tenant and actor claims.

Graph neighborhoods accept repeatable `predicate` and `namespace` filters, `min_confidence`, and an optional `highlight_to` entity ID in addition to the frozen v1 center, depth, and limit parameters. Traversal and response nodes remain bounded to depth 2 and 50 nodes.

## Verify

```shell
make backend-test
make backend-integration-test
make backend-verify
curl --fail http://localhost:8080/health/live
curl --fail http://localhost:8080/health/ready
```

The integration suite queries the running database, exercises the HTTP read models, verifies an optimistic audited identity review, and installs a temporary evidence-backed Billing estate that covers every public read endpoint plus deterministic Ask templates. Temporary tenant data is removed after each test.

## Seed the curated framework catalog

The checked-in foundation catalog is loaded as global curated knowledge. The loader is versioned and idempotent, writes evidence-backed facts into PostgreSQL, and queues AGE projection through `projection_outbox`.

```shell
make database-seed-test
make database-seed
make database-seed-verify
```

`database-seed` applies pending tracked migrations before loading. Migrations can also be run independently with `make database-migrate`. Re-running the same seed version is a no-op and reports `"replayed": true`. A later seed version creates a new complete snapshot and closes the earlier current facts through the normal snapshot publication path.

## Populate the AGE projection

Project pending fact events after seeding:

```shell
make database-project
make database-project-verify
```

The worker uses leased `projection_outbox` batches, idempotently upserts generic `Entity` vertices and `Relationship` edges, and acknowledges each batch in the same PostgreSQL transaction as its AGE writes. Re-running with an empty outbox reports zero processed events.

## Operate

```shell
make backend-logs
make backend-down
```

The database bootstrap scripts run only when Docker creates a fresh `stackgraph_postgres_data` volume. Removing that volume deletes all local StackGraph database data and is intentionally not wrapped in a Make target.
