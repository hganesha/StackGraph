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

Tenant-scoped requests use `X-StackGraph-Tenant-ID`. Identity reviews also accept `X-StackGraph-Actor` for the audit record. These headers are the local-development boundary; production authentication must supply trusted tenant and actor claims rather than forwarding arbitrary client headers.

## Verify

```shell
make backend-test
make backend-integration-test
make backend-verify
curl --fail http://localhost:8080/health/live
curl --fail http://localhost:8080/health/ready
```

The integration suite queries the running database, exercises the HTTP read models, and verifies an optimistic, audited identity review. Its temporary tenant data is removed after the test.

## Seed the curated framework catalog

The checked-in foundation catalog is loaded as global curated knowledge. The loader is versioned and idempotent, writes evidence-backed facts into PostgreSQL, and queues AGE projection through `projection_outbox`.

```shell
make database-seed-test
make database-seed
make database-seed-verify
```

Re-running the same seed version is a no-op and reports `"replayed": true`. A later seed version creates a new complete snapshot and closes the earlier current facts through the normal snapshot publication path.

## Operate

```shell
make backend-logs
make backend-down
```

The database bootstrap scripts run only when Docker creates a fresh `stackgraph_postgres_data` volume. Removing that volume deletes all local StackGraph database data and is intentionally not wrapped in a Make target.
