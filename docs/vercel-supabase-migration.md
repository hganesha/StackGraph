# Vercel + Supabase migration

Status: proposed

Last reviewed: 2026-08-21

Scope: deploy StackGraph with minimal application change, while keeping the existing Docker deployment supported and reversible.

## Decision summary

The lowest-risk production topology is hybrid:

- Vercel hosts the Next.js web application and the request-driven FastAPI application.
- Supabase hosts the authoritative PostgreSQL database.
- Evidence blobs use one selected backend: local durable storage, S3/S3-compatible storage, or Vercel Blob.
- The existing continuously polling workers remain Docker services for the first migration. They connect to the same Supabase database and selected blob store.
- Apache AGE is disabled in the Supabase topology. The API uses its existing SQL graph reader.
- The Docker topology remains supported. Selection is made with three provider variables; provider-specific URLs and credentials remain separate secrets.

This is intentionally a replatform, not a rewrite. No data model, API contract, authentication model, queue schema, or worker algorithm should be refactored as part of the first cut.

The target is:

```text
Browser
  |
  v
Vercel public project (Next.js)
  |-- /                         -> Next.js
  |-- /api/v1/* and /health/*  -> Vercel FastAPI project (rewrite/proxy)
                                      |
                                      v
                               Supabase Postgres
                                      ^
                                      |
Docker worker host ------------------+--------------------> selected blob store
(webhook/control loop/deps.dev/OSV/intelligence)           (local/S3/Vercel Blob)
```

Vercel Pro and Supabase Pro are appropriate, but upgrading the plans does not turn Vercel Functions into persistent containers. Function invocations still have finite durations (up to 800 seconds on Pro with Fluid Compute), and Vercel Cron invokes HTTP functions rather than running daemon processes. See [Vercel Function limits](https://vercel.com/docs/functions/limitations) and [Vercel Cron behavior](https://vercel.com/docs/cron-jobs/manage-cron-jobs).

## Why this is the minimal-change path

The repository already has the important seams:

- All application database access is driven by `STACKGRAPH_DATABASE_URL` and uses PostgreSQL through psycopg.
- The authoritative model is ordinary PostgreSQL 15+; Apache AGE is documented as an asynchronous projection.
- `STACKGRAPH_GRAPH_READ_MODE=sql` already bypasses AGE for graph reads.
- Evidence storage already has an `EvidenceStore` protocol with local and S3 implementations.
- Each polling worker already exposes a bounded one-shot command such as `work`, `run_once`, `run_batch`, or `work_jobs`. A later Vercel function can invoke those functions without changing the worker algorithms.

The main incompatibilities are narrow but important:

1. Hosted Supabase does not currently list Apache AGE among its supported extensions. StackGraph must use SQL graph reads and must not start the AGE projection worker. Supabase supports many packaged and pure-SQL extensions, but AGE is a compiled extension and is not in the hosted extension catalog. See the [Supabase extension catalog](https://supabase.com/docs/guides/database/extensions).
2. API readiness currently requires AGE even when SQL graph reads are selected. That check needs a small correction.
3. A serverless API should use a Supabase transaction pooler and must disable prepared statements. The current API pool has a minimum size of one and can automatically prepare repeated queries, so it needs small pool configuration changes. Supabase recommends transaction pooling for serverless functions and notes that it does not support prepared statements. See [Supabase database connections](https://supabase.com/docs/guides/database/connecting-to-postgres).
4. The current S3 store always sends checksum, server-side-encryption, Object Lock, and governance-retention headers. Supabase's S3 compatibility implements the common object operations but explicitly does not implement those headers. See [Supabase S3 compatibility](https://supabase.com/docs/guides/storage/s3/compatibility).
5. Vercel cannot run the Compose `serve` loops as-is. Those processes must initially stay on Docker or receive thin request/cron adapters.

## Provider switch contract

Add these three variables to the shared configuration contract:

```dotenv
# Deployment topology. This selects infrastructure wiring, not business logic.
STACKGRAPH_COMPUTE_PROVIDER=docker        # docker | vercel

# Authoritative PostgreSQL provider.
STACKGRAPH_DATABASE_PROVIDER=docker-postgres  # docker-postgres | supabase

# Evidence blob write provider.
STACKGRAPH_BLOB_PROVIDER=local            # local | s3 | vercel-blob
```

The selectors should be explicit, validated, case-insensitive, and have the Docker-compatible defaults shown above. They must not encode credentials or replace the existing connection variables.

The canonical runtime inputs remain:

```dotenv
STACKGRAPH_DATABASE_URL=postgresql://...
STACKGRAPH_DATABASE_MIGRATION_URL=postgresql://...
STACKGRAPH_EVIDENCE_STORE_ROOT=/evidence
STACKGRAPH_EVIDENCE_S3_BUCKET=
STACKGRAPH_EVIDENCE_S3_ENDPOINT=
BLOB_READ_WRITE_TOKEN=
```

`STACKGRAPH_DATABASE_MIGRATION_URL` is new. It separates long-lived/admin migration access from pooled application traffic. Application processes use `STACKGRAPH_DATABASE_URL`; schema installation, migrations, `pg_dump`, and `pg_restore` use `STACKGRAPH_DATABASE_MIGRATION_URL`.

Update `migrate`, `seed`, and other operator-only database entrypoints to prefer `STACKGRAPH_DATABASE_MIGRATION_URL` and fall back to `STACKGRAPH_DATABASE_URL` for backward compatibility. Normal API and worker entrypoints must continue to read only `STACKGRAPH_DATABASE_URL`.

Provider selectors are primarily used by configuration validation, deployment scripts, health reporting, and the evidence-store factory. The application should continue to depend on PostgreSQL and `EvidenceStore` interfaces, not on Supabase or Vercel SDKs throughout the codebase.

### Valid combinations

| Compute | Database | Blob | Supported | Notes |
| --- | --- | --- | --- | --- |
| Docker | Docker Postgres | local | Yes | Current development default. |
| Docker | Docker Postgres | S3 | Yes | Current production pattern. |
| Docker | Supabase | S3 | Yes, recommended first migration stage | Moves data before compute. |
| Docker | Supabase | Vercel Blob | Yes, after adding adapter | Vercel Blob has a Python SDK. |
| Vercel | Supabase | S3 | Yes, recommended target | Vercel web/API; Docker workers initially. |
| Vercel | Supabase | Vercel Blob | Yes, after adding adapter | Use a private Blob store for evidence. |
| Vercel | Supabase | local | No in production | Vercel's filesystem is not durable shared storage. |
| Vercel | Docker Postgres | any remote blob | Technically possible | Only if the Docker database is publicly and securely reachable; not recommended. |

`STACKGRAPH_COMPUTE_PROVIDER=vercel` describes the public web/API topology. It does not imply that every background process runs as a Vercel Function.

## Service placement

| Current service | Initial target | Code impact | Reason |
| --- | --- | --- | --- |
| `web` | Vercel Next.js project | None or deployment config only | Native Vercel workload. |
| `api` | Vercel Python/FastAPI project | Small entrypoint, pool, and readiness changes | Request-driven and supported by Vercel's Python runtime. |
| `database` | Supabase Postgres | Bootstrap/grant scripts only | Authoritative schema is portable PostgreSQL. |
| `migrate`, `seed` | CI or operator one-shot job | Environment/packaging only | Must not run on every function cold start. |
| `github-webhook` | Docker initially | None | Existing implementation owns a `ThreadingHTTPServer` and a heartbeat thread. A thin ASGI route is needed before moving it to Vercel. |
| `github-control-loop` | Docker initially | None | Persistent poll loop and repository work can exceed a single request. |
| `depsdev-continuous` | Docker initially | None | Persistent poll loop; one-shot function is already available for a later cron adapter. |
| `osv-continuous` | Docker initially | None | Same as deps.dev. |
| `intelligence-continuous` | Docker initially | None | External AI latency and batching make the existing daemon safer for the first cut. |
| `projection-continuous` | Disabled on Supabase | Small readiness/operations changes | Hosted Supabase has no AGE; SQL graph reads are already implemented. |
| tool-only scanners/importers | Developer machine, CI, or bounded jobs | Environment only | They are not public runtime services. |
| Caddy | Removed from Vercel topology | Routing config | Vercel provides TLS, domains, and rewrites. |
| MinIO | Replaced by selected remote blob provider | Adapter/config only | Vercel has no durable Compose volume. |
| Prometheus/Alertmanager/Grafana | Keep on Docker or replace with managed telemetry | Deployment change | These are persistent daemons, not Vercel Functions. Keep Sentry and add Vercel/Supabase log drains as needed. |

Vercel has a Services feature that can mount Next.js and FastAPI under one deployment, but as of the review date it is Private Beta and requires access. See [Vercel Services](https://vercel.com/docs/services). It is a useful later simplification, not a dependency for the first production migration.

## Required code changes

These changes are deliberately additive and localized.

### Change inventory

| File/area | Required change | Initial cut |
| --- | --- | --- |
| `apps/api/app/config.py` | Provider settings, pool minimum `0`, prepared-statement setting, projection mode validation | Required |
| `apps/api/app/database.py` | Pass serverless pool/connect options and disable psycopg prepared statements when configured | Required |
| `apps/api/app/main.py` | Treat AGE as optional in readiness when SQL graph mode is selected | Required |
| `services/data-platform/stackgraph_data/project.py` | Add bounded disabled-projection acknowledgement | Required for Supabase |
| `services/data-platform/stackgraph_data/migrate.py` and operator CLIs | Prefer the migration URL with backward-compatible fallback | Required |
| `services/enterprise-discovery/stackgraph_discovery/evidence_store.py` | Explicit provider selection, S3 compatibility profile, provider-routed reads | Required |
| `services/enterprise-discovery/requirements.txt` | Pin Vercel Python SDK only if Vercel Blob is enabled | Conditional |
| root `api/index.py`, root Python requirements, root `vercel.json` | Thin FastAPI deployment entrypoint and function inclusion | Required for Vercel API |
| `apps/web/vercel.json` | Same-origin API/health rewrites | Required for two-project Vercel layout |
| `.env.production.example` and `apps/web/.env.example` | Provider contract and target examples without secrets | Required |
| API/data/discovery tests | Provider matrix, SQL-only readiness, pool settings, outbox acknowledgement, blob contract | Required |
| worker HTTP/cron adapters | Call existing bounded worker functions | Later/optional |

No existing Dockerfile or Compose service needs to be removed. Docker configuration should consume the new defaults and continue to pass its current test/recovery suite.

### 1. Add and validate provider settings

Add the three provider fields to the API/shared operational configuration and document them in `.env.production.example`.

Behavior:

- Defaults preserve the existing Docker topology.
- Reject `compute=vercel` with `blob=local` outside development/test.
- Require a non-empty `STACKGRAPH_DATABASE_URL` for both database providers.
- Require `STACKGRAPH_DATABASE_MIGRATION_URL` only in migration/administrative commands, not in the API runtime.
- Require the relevant blob variables only for the selected blob provider.
- Continue to infer the old local/S3 selection only when `STACKGRAPH_BLOB_PROVIDER` is unset, for one deprecation cycle. Explicit configuration wins.

Do not branch read-model, authentication, or ingestion logic on these selectors.

### 2. Make the API database pool serverless-safe

In `apps/api/app/config.py` and `apps/api/app/database.py`:

- Allow `STACKGRAPH_DB_POOL_MIN_SIZE=0` (`ge=0`) and keep Docker's default at `1`.
- For Vercel/Supabase use `STACKGRAPH_DB_POOL_MIN_SIZE=0` and start with `STACKGRAPH_DB_POOL_MAX_SIZE=2`.
- Pass `prepare_threshold=None` to psycopg connections when using a Supabase transaction pooler.
- Keep `autocommit=True`; the existing `Database.session()` already wraps tenant-scoped work in an explicit transaction and calls `set_config(..., true)`, which is compatible with transaction pooling.
- Add a short connect timeout and retain the current per-checkout timeout.
- Do not create a new global pool per request. Create it in FastAPI lifespan as today and let the warm function instance reuse it.

Prefer an explicit setting rather than hostname inspection:

```dotenv
STACKGRAPH_DB_PREPARED_STATEMENTS=false
```

Docker remains `true` by default; Supabase deployment configuration sets it to `false`.

### 3. Correct readiness when AGE is intentionally disabled

The current `/health/ready` response is `503` unless `age_installed` is true. Change readiness to:

```text
database connected
AND StackGraph schema installed
AND (graph_read_mode == "sql" OR AGE installed)
```

Expose `graph_mode: sql|age` and `age_installed` separately in the payload so operators can distinguish an intended SQL topology from a degraded AGE topology.

For Supabase set:

```dotenv
STACKGRAPH_GRAPH_READ_MODE=sql
```

Do not use `auto` on Supabase. `auto` first probes projection state and then falls back, creating unnecessary AGE-related work and log noise.

### 4. Handle the projection outbox in SQL-only mode

Disabling the AGE worker alone leaves `projection_outbox` rows pending forever and makes Admin service/queue status misleading.

Add one explicit projection mode:

```dotenv
STACKGRAPH_GRAPH_PROJECTION_MODE=age   # age | disabled
```

Recommended minimal implementation:

- Keep writing the transactional outbox; it remains useful if AGE is restored later.
- Add a bounded `ack-disabled` operation to `stackgraph_data.project` that marks a batch as intentionally skipped with `processed_at` and payload/metadata indicating `projection_mode=disabled`.
- Invoke that operation from a small scheduled job or from the retained Docker data worker.
- Report the projection service as `DISABLED` rather than failed when this mode is selected.

This avoids rewriting the existing publication functions and prevents unbounded queue growth. Do not point the existing AGE `ProjectionWorker` at Supabase; it queries `ag_catalog` and calls `cypher()`.

### 5. Make blob selection explicit and preserve the interface

Update `evidence_store_from_environment()` to select by `STACKGRAPH_BLOB_PROVIDER`:

```text
local       -> LocalEvidenceStore
s3          -> S3EvidenceStore
vercel-blob -> VercelBlobEvidenceStore
```

Keep `EvidenceStore.put_bytes`, `read_bytes`, and `delete_tenant` unchanged.

Add a provider-neutral content key helper so all remote providers use the existing content-addressed layout:

```text
stackgraph-evidence/tenants/<tenant-segment>/sha256/<first-two>/<digest>
```

#### S3 compatibility profiles

Add:

```dotenv
STACKGRAPH_EVIDENCE_S3_PROFILE=aws   # aws | supabase | generic
```

`aws` preserves the current behavior. `supabase` must:

- use path-style addressing;
- omit `ChecksumSHA256`;
- omit `ServerSideEncryption` and KMS parameters;
- omit Object Lock mode, retention date, and legal-hold headers;
- omit `BypassGovernanceRetention` on delete;
- retain StackGraph's own SHA-256 metadata and verify content after reads.

Supabase S3 access keys are server-side credentials with access across buckets and bypass Storage RLS, so they must only be set on backend projects/workers. The S3 endpoint is `https://<project-ref>.storage.supabase.co/storage/v1/s3`; copy the exact endpoint and region from the project Storage settings. See [Supabase S3 authentication](https://supabase.com/docs/guides/storage/s3/authentication).

Supabase Storage does not provide S3 Object Lock/versioning semantics. If governance retention or legal hold is a hard requirement, use AWS S3 with Object Lock and keep `STACKGRAPH_EVIDENCE_S3_PROFILE=aws`. Setting `STACKGRAPH_EVIDENCE_ALLOW_DELETE=false` is an application control, not equivalent to immutable storage.

#### Vercel Blob adapter

Add `VercelBlobEvidenceStore` using the official Python `vercel` SDK (pin the package and lock it). Vercel documents Python Blob support and private stores; private Blob is generally available as of June 2026. See the [Blob SDK reference](https://vercel.com/docs/vercel-blob/using-blob-sdk) and [private Blob documentation](https://vercel.com/docs/vercel-blob/private-storage).

Requirements:

- Use a private Blob store.
- Use deterministic, content-addressed pathnames and do not overwrite content.
- Store `content-hash`, media type, tenant segment, and size as supported metadata or validate them from the descriptor/content.
- Use a distinct descriptor host such as `stackgraph-evidence://vercel/...` so reads can be routed correctly.
- Default tenant deletion to disabled, matching S3 behavior.
- Authenticate with `BLOB_READ_WRITE_TOKEN` initially. Vercel-hosted private Blob can later use Vercel OIDC, but that should be a separate hardening change.

### 6. Preserve reads across a blob-provider switch

Changing the active write provider must not make older descriptors unreadable.

Add a small `RoutingEvidenceStore`:

- writes go to the provider selected by `STACKGRAPH_BLOB_PROVIDER`;
- `stackgraph-evidence://local/...` reads use the configured local reader;
- `stackgraph-evidence://object/...` reads use the configured S3 reader;
- `stackgraph-evidence://vercel/...` reads use the Vercel Blob reader.

Because the current S3 URI does not identify a bucket/provider, switching between two S3 endpoints requires copying all objects with the same keys before changing the endpoint. Switching away from local storage also requires a bulk copy before Vercel cutover because Vercel cannot mount the old Docker volume.

The environment switch is simple for new writes; durable rollback still requires the old reader and data to remain available until the migration is accepted.

### 7. Add a thin Vercel FastAPI entrypoint

Use two Vercel projects for the stable initial deployment:

1. `stackgraph-web`, rooted at `apps/web`.
2. `stackgraph-api`, rooted at the repository root with a small `api/index.py` entrypoint.

The entrypoint should only:

- add `apps/api` and `services/intelligence/ai-services` to `sys.path`;
- set repo-relative defaults for contracts and prompt directories;
- import and export `app.main.app`.

Add a root Python requirements file that includes the pinned API requirements. Configure function file inclusion for:

- `apps/api/app/**`;
- `services/intelligence/ai-services/stackgraph_ai/**`;
- `services/intelligence/ai-services/prompts/**`;
- `stackgraph-foundation/contracts/v1/**`.

Do not start Uvicorn in Vercel. Export the ASGI application and let Vercel's Python runtime invoke it. Vercel supports existing FastAPI applications; see [FastAPI on Vercel](https://vercel.com/docs/frameworks/backend/fastapi).

### 8. Keep one public origin

The current authentication cookies are host-only and the Next.js middleware reads them on the web origin. Avoid changing cookie semantics by keeping browser traffic on one public origin.

In the web Vercel project, rewrite:

```json
{
  "rewrites": [
    {
      "source": "/api/v1/:path*",
      "destination": "https://<api-project>.vercel.app/api/v1/:path*"
    },
    {
      "source": "/health/:path*",
      "destination": "https://<api-project>.vercel.app/health/:path*"
    }
  ]
}
```

Then set `NEXT_PUBLIC_API_BASE_URL` to the canonical web origin, not the upstream API project URL. This preserves same-origin cookies, the current web middleware check, CSP, and browser fetch behavior.

Vercel documents the separate-project plus rewrite pattern for monorepos in its [Monorepo FAQ](https://vercel.com/docs/monorepos/monorepo-faq). Enable source files outside the root directory for the web project so workspace packages remain available.

### 9. Optional: move bounded worker calls to Vercel later

Do this only after the hybrid deployment is stable.

Add authenticated HTTP handlers that call the existing bounded functions:

- deps.dev: schedule plus `run_once`;
- OSV: schedule plus `run_batch`;
- GitHub control loop: `run_once`;
- intelligence: `work_jobs`;
- projection disabled mode: `ack-disabled`;
- webhook: adapt `verify_github_webhook()` and `process_github_webhook()` to an ASGI route.

Each handler must:

- require `Authorization: Bearer ${CRON_SECRET}`;
- impose an item/batch limit that completes comfortably inside `maxDuration`;
- rely on the existing database leases/idempotency instead of in-memory state;
- return non-2xx on failure and emit structured logs;
- be safe when two invocations overlap;
- avoid local repository/evidence paths unless all inputs are copied to remote blob storage;
- renew or conservatively size database job leases so function termination cannot strand work for long periods.

Vercel Cron does not retry failed invocations. Existing database retry/lease logic remains the source of truth; a later invocation must reclaim work. For high-frequency two-second polling, keep Docker. Cron is suited to coarser scheduling, not a drop-in replacement for the current loops.

## Required Supabase infrastructure changes

### Project and region

- Create a paid Supabase project in the same or closest available region to the Vercel Function region.
- Pin the Vercel API function to that region.
- Enable Point-in-Time Recovery for production if the recovery requirement calls for it.
- Create a separate Supabase branch/project for preview and migration rehearsal. Never give Vercel previews the production database URL.

Supabase is single-primary by region; region alignment matters more than placing the web UI near users because most API requests query PostgreSQL. See [Supabase regions](https://supabase.com/docs/guides/platform/regions).

### Database endpoints

Use two URLs:

```dotenv
# Vercel API and any short-lived Vercel worker functions:
STACKGRAPH_DATABASE_URL=postgresql://...@...pooler.supabase.com:6543/postgres?sslmode=require

# Schema install, migrations, dumps/restores (admin role, operator environment only):
STACKGRAPH_DATABASE_MIGRATION_URL=postgresql://postgres:...@db.<project-ref>.supabase.co:5432/postgres?sslmode=require

# Retained Docker worker environment (restricted app role, direct or session pooler):
STACKGRAPH_DATABASE_URL=postgresql://stackgraph_app:...@...:5432/postgres?sslmode=require
```

Use the exact strings from Supabase's Connect dialog. If the Docker worker host cannot reach the IPv6 direct endpoint, use the Supavisor session pooler on port 5432 or purchase/configure the appropriate IPv4 option. Do not reuse the migration/admin URL in the public API.

For Vercel runtime connections use transaction pooling and disable prepared statements. For persistent Docker workers prefer a direct or session-pooled restricted app-role URL. The two deployments may both call the variable `STACKGRAPH_DATABASE_URL` while assigning it different endpoint modes. If one URL must be shared temporarily, transaction pooling works only after all psycopg call sites that may auto-prepare statements are disabled; separate per-deployment values are safer.

### Schema and role bootstrap

Do not run Docker's database init directory against Supabase. Create a Supabase-specific bootstrap script that is idempotent and reviewable.

It must:

1. enable/verify `pgcrypto`;
2. install `stackgraph-foundation/schema.sql` into a fresh database;
3. apply `infrastructure/database/migrations` using the existing migration runner;
4. create or rotate a `stackgraph_app` login role;
5. grant `CONNECT`, public-schema usage, table DML, sequence usage, and required function execution;
6. omit `ag_catalog` and the AGE graph schema grants when projection mode is disabled;
7. set default privileges for future migrations;
8. revoke all StackGraph table privileges from `anon` and `authenticated` unless/until a reviewed Data API is intentionally introduced.

The API should continue using the restricted `stackgraph_app` role. Do not use Supabase's `postgres`, `service_role`, or a secret key from browser code.

StackGraph tables currently live in `public`. To avoid accidentally making the backend schema a public Data API, configure Supabase Data API settings so StackGraph tables are not exposed and explicitly retain the `REVOKE` statements above. Supabase's 2026 rollout stops automatically exposing new public tables, but explicit defense is still required. See the [Supabase breaking-change notice](https://supabase.com/changelog?types=breaking-change).

StackGraph's RLS policies use the transaction-local `app.tenant_id` setting established by the backend, not Supabase Auth JWT claims. Preserve that model for this migration. Adopting Supabase Auth/PostgREST would be a separate application redesign.

### AGE decision

Do not attempt to compile or install AGE into hosted Supabase as part of this migration.

- Set `STACKGRAPH_GRAPH_READ_MODE=sql`.
- Set `STACKGRAPH_GRAPH_PROJECTION_MODE=disabled`.
- Do not run `infrastructure/database/init/020-create-graph.sql`.
- Do not start `projection-continuous` against Supabase.
- Run the bounded disabled-projection acknowledger so the outbox remains controlled.

If AGE performance becomes necessary later, keep the authoritative Supabase relational database and add a separate supported graph read model, or move PostgreSQL back to an AGE-capable managed/container host. That is an architecture change and is outside this low-risk migration.

### Storage

If using Supabase Storage through S3:

1. Create a private `stackgraph-evidence` file bucket.
2. Enable S3 access and generate server-side access keys.
3. Record the direct storage endpoint and region.
4. Set the S3 profile to `supabase` so unsupported headers are omitted.
5. Keep access keys only in the Vercel API/worker projects and Docker worker secret store.
6. Test head, put, get, list-v2, and delete behavior with the exact boto3 version used by StackGraph.
7. Establish a separate object backup/export process.

Supabase database backups do not contain Storage objects; they contain only storage metadata. See [Supabase database backups](https://supabase.com/docs/guides/platform/backups). Database PITR and blob recovery therefore need separate runbooks.

## Required Vercel infrastructure changes

### Projects and routing

Create two projects from the same repository:

`stackgraph-web`:

- Root directory: `apps/web`.
- Framework: Next.js.
- Include source files outside root: enabled.
- Production domain: the canonical StackGraph domain.
- Rewrites: `/api/v1/*` and `/health/*` to the API project.

`stackgraph-api`:

- Root directory: repository root.
- Framework/runtime: Python/FastAPI function.
- Entrypoint: `api/index.py`.
- Function region: colocated with Supabase.
- Fluid Compute: enabled.
- Start `maxDuration` at 300 seconds; do not raise it without observing a real request need.

Keep deployments Git-driven. Use Vercel preview deployments with a preview Supabase branch/project, run the API and web tests, and promote the tested artifact. Pin any Vercel CLI version used by custom CI.

### Environment scope

- Production variables point only to production Supabase and production blob storage.
- Preview variables point only to preview/branch resources.
- Development variables point to Docker/local defaults unless a developer explicitly opts into a remote branch.
- Secrets live in Vercel project settings, not committed `.env` files.
- Only `NEXT_PUBLIC_*` values may be exposed to the browser; database URLs, S3 keys, Blob tokens, OIDC secrets, GitHub secrets, session keys, and encryption keys are server-only.

## Environment variable reference

### Core selectors

| Variable | Docker default | Vercel/Supabase target | Secret | Purpose |
| --- | --- | --- | --- | --- |
| `STACKGRAPH_COMPUTE_PROVIDER` | `docker` | `vercel` | No | Select deployment wiring and validation. |
| `STACKGRAPH_DATABASE_PROVIDER` | `docker-postgres` | `supabase` | No | Select database operational profile. |
| `STACKGRAPH_BLOB_PROVIDER` | `local` | `s3` or `vercel-blob` | No | Select evidence write provider. |
| `STACKGRAPH_DATABASE_URL` | Docker app URL | Supabase pooled app-role URL | Yes | Runtime application connection. |
| `STACKGRAPH_DATABASE_MIGRATION_URL` | Docker admin URL | Supabase direct admin URL | Yes | Migrations, dump, restore, bootstrap. |
| `STACKGRAPH_GRAPH_READ_MODE` | `auto` | `sql` | No | AGE versus relational graph reads. |
| `STACKGRAPH_GRAPH_PROJECTION_MODE` | `age` | `disabled` | No | AGE projection or intentional acknowledgement. |
| `STACKGRAPH_DB_PREPARED_STATEMENTS` | `true` | `false` | No | Required for Supabase transaction pooling. |
| `STACKGRAPH_DB_POOL_MIN_SIZE` | `1` | `0` | No | Avoid idle connection per cold instance. |
| `STACKGRAPH_DB_POOL_MAX_SIZE` | `5` | `2` initially | No | Bound database fan-out per warm instance. |

### Local evidence

```dotenv
STACKGRAPH_BLOB_PROVIDER=local
STACKGRAPH_EVIDENCE_STORE_ROOT=/evidence
```

Local is valid only where `/evidence` is a durable Docker volume. It is not valid on Vercel.

### AWS S3 or compatible S3

```dotenv
STACKGRAPH_BLOB_PROVIDER=s3
STACKGRAPH_EVIDENCE_S3_PROFILE=aws
STACKGRAPH_EVIDENCE_S3_BUCKET=stackgraph-evidence
STACKGRAPH_EVIDENCE_S3_PREFIX=stackgraph-evidence
STACKGRAPH_EVIDENCE_S3_ENDPOINT=
STACKGRAPH_EVIDENCE_S3_KMS_KEY_ID=<kms-key-id>
STACKGRAPH_EVIDENCE_RETENTION_DAYS=30
STACKGRAPH_EVIDENCE_LEGAL_HOLD=false
STACKGRAPH_EVIDENCE_ALLOW_DELETE=false
AWS_ACCESS_KEY_ID=<secret>
AWS_SECRET_ACCESS_KEY=<secret>
AWS_REGION=us-east-1
```

For generic S3-compatible providers set `STACKGRAPH_EVIDENCE_S3_PROFILE=generic`, provide the endpoint, and test the provider's checksum, encryption, retention, and path-style behavior explicitly.

### Supabase Storage through S3

```dotenv
STACKGRAPH_BLOB_PROVIDER=s3
STACKGRAPH_EVIDENCE_S3_PROFILE=supabase
STACKGRAPH_EVIDENCE_S3_BUCKET=stackgraph-evidence
STACKGRAPH_EVIDENCE_S3_PREFIX=stackgraph-evidence
STACKGRAPH_EVIDENCE_S3_ENDPOINT=https://<project-ref>.storage.supabase.co/storage/v1/s3
STACKGRAPH_EVIDENCE_RETENTION_DAYS=30
STACKGRAPH_EVIDENCE_LEGAL_HOLD=false
STACKGRAPH_EVIDENCE_ALLOW_DELETE=false
AWS_ACCESS_KEY_ID=<supabase-s3-access-key>
AWS_SECRET_ACCESS_KEY=<supabase-s3-secret-key>
AWS_REGION=<supabase-project-region>
```

Do not set a KMS key for the Supabase profile. `RETENTION_DAYS` is metadata/application policy only in this profile, not S3 Object Lock.

### Vercel Blob

```dotenv
STACKGRAPH_BLOB_PROVIDER=vercel-blob
STACKGRAPH_VERCEL_BLOB_ACCESS=private
STACKGRAPH_EVIDENCE_ALLOW_DELETE=false
BLOB_READ_WRITE_TOKEN=<secret>
```

### Vercel web

```dotenv
NEXT_PUBLIC_DATA_SOURCE=live
NEXT_PUBLIC_API_BASE_URL=https://stackgraph.example.com
NEXT_PUBLIC_AUTH_REQUIRED=true
STACKGRAPH_WEB_AUTH_REQUIRED=true
```

`NEXT_PUBLIC_API_BASE_URL` is the public web origin because `/api/v1` is rewritten there. It is not the private upstream project URL.

### Vercel API

Retain the current production auth, AI, GitHub, and observability variables from `.env.production.example`, plus:

```dotenv
STACKGRAPH_COMPUTE_PROVIDER=vercel
STACKGRAPH_DATABASE_PROVIDER=supabase
STACKGRAPH_DATABASE_URL=<supabase-pooled-stackgraph_app-url>
STACKGRAPH_DB_PREPARED_STATEMENTS=false
STACKGRAPH_DB_POOL_MIN_SIZE=0
STACKGRAPH_DB_POOL_MAX_SIZE=2
STACKGRAPH_GRAPH_READ_MODE=sql
STACKGRAPH_GRAPH_PROJECTION_MODE=disabled
STACKGRAPH_CORS_ALLOWED_ORIGINS=https://stackgraph.example.com
STACKGRAPH_OIDC_REDIRECT_URI=https://stackgraph.example.com/api/v1/auth/callback
STACKGRAPH_CONTRACTS_DIR=<set by entrypoint from repo-relative path>
STACKGRAPH_AI_PROMPTS_DIR=<set by entrypoint from repo-relative path>
```

Do not set `STACKGRAPH_DATABASE_MIGRATION_URL` on the public API project unless an operator-only function genuinely needs it. Prefer keeping it only in CI/operator secret storage.

### Optional Vercel cron handlers

```dotenv
CRON_SECRET=<random-secret>
STACKGRAPH_WORKER_BATCH_SIZE=10
```

Use the Vercel-generated/managed cron secret where available and compare it with constant-time logic. Never accept a worker name or arbitrary module/command from the request.

## Migration sequence

### Phase 0: compatibility patch on Docker

1. Add provider settings with Docker-compatible defaults.
2. Add serverless-safe pool configuration without changing Docker values.
3. Correct AGE-optional readiness.
4. Add projection disabled acknowledgement and blob provider profiles/adapters.
5. Add table-driven config tests and storage contract tests.
6. Run the entire existing test suite and Docker recovery drills.

No production infrastructure changes occur in this phase.

### Phase 1: move the database while compute remains Docker

1. Create a Supabase non-production project.
2. Apply the schema and migrations without AGE.
3. Create the restricted app role and harden Data API grants.
4. Copy representative production data.
5. Run Docker API/workers against Supabase using SQL graph mode.
6. Verify tenant RLS, migrations, queue leasing, AI jobs, GitHub discovery, Admin status, and graph results.
7. Load test connection counts and query latency.

This isolates database compatibility from Vercel runtime compatibility.

### Phase 2: move web and API to Vercel

1. Deploy the API project against the non-production Supabase project.
2. Verify `/health/live`, `/health/ready`, auth login/callback/refresh/logout, and all contract endpoints.
3. Deploy the web project with same-origin rewrites.
4. Run Playwright and production-like OIDC tests on the preview domain.
5. Keep all continuous workers on Docker, pointed at the same Supabase database and remote blob store.
6. Verify that no request depends on a local volume or long-lived in-memory state.

### Phase 3: production data cutover

For a small/current database, prefer a planned write pause over dual-write complexity:

1. Put the application and workers into maintenance/stopped mode.
2. Take a source database backup and record row counts/checksums.
3. Restore authoritative `public` schema data into Supabase using direct/admin connections. Exclude AGE schemas and AGE extension objects.
4. Copy evidence objects to the selected target, preserving deterministic keys.
5. Validate database and object manifests before changing production variables.
6. Run migrations and readiness checks.
7. Switch Docker workers to Supabase/remote blob.
8. Switch the public domain to the tested Vercel deployment.
9. Resume workers and writes.
10. Watch errors, connection counts, queue age, and auth failures through the acceptance window.

Use `pg_dump`/`pg_restore` with `--no-owner --no-acl` and direct connections. Rehearse the exact commands against a disposable Supabase project before production. Do not improvise schema cleanup on the production project.

### Phase 4: optionally serverlessize bounded workers

Move one worker at a time behind its thin authenticated handler. Disable its Docker daemon only after overlapping invocation, retry, lease-expiry, timeout, and rate-limit tests pass. Keep high-frequency or repository-heavy workers on Docker if that is operationally simpler.

## Verification gates

The migration is not complete until all of these pass.

### Database

- Fresh Supabase install applies schema and every migration without AGE.
- `stackgraph_app` can perform required application queries but cannot create roles/extensions or access Supabase internal schemas.
- `anon` and `authenticated` cannot read StackGraph tables through the Data API.
- Tenant isolation tests pass with transaction pooling and prepared statements disabled.
- Connection count remains bounded during concurrent/cold-start load.
- SQL graph neighborhood contract/golden tests match Docker/AGE-supported behavior where the contract requires equivalence.
- Projection disabled mode produces no growing pending outbox.

### Blob

- Contract tests pass for selected `put`, duplicate put, head/read, hash mismatch, list/delete policy, and tenant isolation behavior.
- A copied object can be read with its pre-migration descriptor.
- New objects use the expected descriptor host and deterministic key.
- A manifest comparison proves every referenced non-inline blob exists after copy.
- Recovery is tested independently from database recovery.

### Web/API

- Same-origin auth cookies are visible to Next.js middleware after OIDC callback.
- Browser requests use the public origin and rewrites, not the upstream API URL.
- CSP `connect-src` permits the selected origin and does not become wildcarded.
- Preview uses preview database/storage only.
- API readiness is green with `graph_read_mode=sql` and `age_installed=false`.
- Contract, type, lint, unit, integration, and Playwright suites pass.

### Workers

- Docker workers can reach Supabase and remote blob storage.
- Leases recover after forced process termination.
- Service heartbeats and Admin status distinguish Docker, Vercel, and disabled projection modes.
- Queue age, retry, and dead-letter behavior are unchanged.

## Rollback

Compute rollback is simple: point the public domain back to the Docker web/API deployment and set `STACKGRAPH_COMPUTE_PROVIDER=docker` there.

Database and blob rollback are not made lossless by an environment variable alone once new writes have occurred.

- During the initial acceptance window, retain the old Docker database and blob store without deleting them.
- If rollback occurs before accepting writes, switch URLs/providers back.
- If Supabase has accepted writes, pause writes and perform a tested reverse data export/import before returning to the old database, or accept a documented recovery point/data loss. Do not silently point the app at a stale database.
- If the blob provider has accepted new objects, keep the routing store configured and copy those objects back before removing the new provider.
- Rotate app-role passwords, S3 keys, Blob tokens, OIDC secrets, and webhook secrets if any rollback was caused by credential exposure.

The cutover runbook must define the recovery point objective and the person authorized to choose data loss versus extended downtime.

## Explicit non-goals

Do not combine this migration with:

- Supabase Auth adoption;
- direct browser access to Supabase tables;
- replacing psycopg with `supabase-py`;
- changing RLS from `app.tenant_id` to JWT claims;
- redesigning queue tables around Supabase Queues or Vercel Workflow;
- replacing the SQL graph implementation;
- splitting the FastAPI application into microservices;
- converting every polling loop to serverless in the first release;
- changing API contracts or frontend data-source behavior.

Those may be useful later, but each expands the failure surface and weakens the goal of moving the current system with minimal functional change.

## Recommended first production configuration

Use:

```dotenv
STACKGRAPH_COMPUTE_PROVIDER=vercel
STACKGRAPH_DATABASE_PROVIDER=supabase
STACKGRAPH_BLOB_PROVIDER=s3
STACKGRAPH_EVIDENCE_S3_PROFILE=supabase
STACKGRAPH_GRAPH_READ_MODE=sql
STACKGRAPH_GRAPH_PROJECTION_MODE=disabled
STACKGRAPH_DB_PREPARED_STATEMENTS=false
STACKGRAPH_DB_POOL_MIN_SIZE=0
STACKGRAPH_DB_POOL_MAX_SIZE=2
```

Run web/API on Vercel, PostgreSQL and evidence storage on Supabase, and retain the four continuous processing lanes on Docker. If evidence immutability/legal hold is mandatory, change only the blob profile/backend to AWS S3 with Object Lock. After this topology is stable, evaluate each bounded worker for a thin Vercel cron adapter based on observed duration and polling-frequency needs.
