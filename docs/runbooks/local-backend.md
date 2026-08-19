# Local backend environment

The local backend uses FastAPI for the API and the official Apache AGE image for PostgreSQL 16 plus AGE 1.6.0. PostgreSQL is authoritative; the `stackgraph` AGE graph is initialized as an asynchronous projection target.

## Start

Copy `.env.example` to `.env` only when you need to override the development defaults, then run:

```shell
make backend-up
```

The API is available at `http://localhost:8080`, interactive API documentation at `http://localhost:8080/docs`, and PostgreSQL at `localhost:5432` by default. The host API port is intentionally configurable through `STACKGRAPH_API_PORT`; the container always listens on port 8000.

## Verify

```shell
make backend-test
make backend-verify
curl --fail http://localhost:8080/health/live
curl --fail http://localhost:8080/health/ready
```

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
