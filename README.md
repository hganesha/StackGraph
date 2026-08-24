# StackGraph

StackGraph is an enterprise software estate intelligence and
modernization platform designed for a world in which software creation
is accelerating dramatically through coding agents, AI-assisted
development, and "vibe coding."

The underlying enterprise problem is not simply that organizations have
vulnerabilities. It is that they increasingly cannot answer basic
questions about their software estate:

-   What applications, services, components, and repositories exist?
-   What business functions, processes, capabilities, and value-chain
    stages do they support?
-   What languages, runtimes, frameworks, packages, databases, UI
    systems, infrastructure components, and deployment patterns do they
    use?
-   What are the direct and transitive dependencies?
-   Where is each workload intended to run: cloud, on-premises,
    Kubernetes, containers, VMs, serverless, managed services?
-   Which technologies are healthy and strategically viable versus
    merely free of known CVEs?
-   Which packages/frameworks are unsupported, abandoned, declining,
    unnecessarily complex, or superseded by native/runtime capabilities?
-   Which technologies have better alternatives for the **actual
    function being performed**?
-   Where has the organization independently implemented the same
    capability multiple times?
-   Which applications should be retained, upgraded, consolidated,
    refactored, rebuilt, replatformed, retired, or investigated?
-   Where should modernization investment be directed based on business
    importance, technical viability, opportunity, confidence, and
    effort?
-   What new technology and architecture patterns are coding agents
    introducing into the estate?

StackGraph addresses this by turning source repositories and related
evidence into a continuously updated, evidence-backed model of:

**Business → Applications → Code → Technology → Dependencies →
Deployment → Infrastructure → OSS ecosystem → Viability → Modernization
actions**

Git repositories are a primary sensor, not the final product.

## What is implemented

StackGraph currently provides:

- continuous GitHub repository acquisition, scanning, ingestion, webhook processing, retries, leases, and dead-letter recovery;
- a bitemporal, evidence-backed enterprise model in PostgreSQL with tenant isolation and governed global catalog visibility;
- application, repository, technology, business-capability, dependency, deployment, risk, and modernization read models;
- deps.dev, OSV, npm registry, and reviewed public OSS-catalog enrichment;
- tenant-scoped Neo4j projections for interactive graph traversal and Neo4j Graph Data Science analysis;
- deterministic graph intelligence including degree, PageRank, sampled betweenness, reach/depth, articulation points, bridges, impact paths, connected communities, cohort anomalies, and circular motifs;
- explainable application similarity with stored candidates, important differences, review decisions, and append-only feedback;
- semantic application and technology embeddings stored in PostgreSQL with pgvector, versioned spaces, content-hash caching, provider quotas, retries, relevance evaluation, and atomic shadow/active promotion;
- structural Node2Vec embeddings held in isolated `SHADOW` spaces until stability and relevance gates are approved;
- evidence-grounded Ask routing that can retrieve semantically, answer structural questions deterministically, and summarize only returned facts, paths, metrics, and limitations;
- contextual graph intelligence in Application Overview and Technology detail, similarity review in Reviews, and graph/embedding operations in Scan Health and Admin Services;
- production Compose services for authentication, object storage, observability, alerting, worker health, and recovery workflows.

There is intentionally no separate top-level “graph intelligence” page. Intelligence is presented where an application, technology, review, question, or operational decision is already being made.

## Architecture

PostgreSQL is the only authoritative store. Neo4j, GDS projections, graph metrics, and embeddings are derived and rebuildable.

```text
GitHub / scanners / ecosystem sources
                 |
                 v
     PostgreSQL + pgvector
 entities, bitemporal facts, evidence,
 reviews, jobs, snapshots, embeddings
        |                    |
        | projection outbox  | embedding jobs
        v                    v
 tenant Neo4j + GDS     embedding worker
        |                    |
        +---------+----------+
                  v
        graph-intelligence worker
                  |
                  v
       FastAPI read models / Ask
                  |
                  v
          Next.js contextual UI
```

Important boundaries:

- A StackGraph tenant is the hard isolation boundary. One tenant may contain multiple organizations when cross-organization analysis is allowed; use separate tenant IDs when credentials, residency, retention, administration, billing, or access must differ.
- The PostgreSQL deployment registry selects a tenant's Neo4j endpoint and credential reference. Application code does not construct endpoints from tenant IDs.
- Projected nodes and relationships retain PostgreSQL UUIDs. No API, review, or snapshot depends on Neo4j internal IDs.
- `auto` graph reads use Neo4j only when its tenant deployment is healthy and caught up. Lag, outage, parity failure, or a bounded-discovery limit falls back to the relational SQL reader.
- Apache AGE remains available only as an explicit legacy read mode; it is not required by the target production architecture.
- Vector similarity retrieves and ranks candidates. It is never proof of dependency, reachability, causality, or consolidation suitability.

The graph and embedding control plane is implemented by database migrations `026` through `040`. See [the completed feature plan](docs/graph-and-embeddings-features.md) for contracts, decisions, measurements, and exit evidence.

## Local Docker quick start

Prerequisites are Docker Desktop (or another running Docker Engine) and Docker Compose v2.

Start the complete local application:

```sh
make app-up
```

The equivalent script is:

```sh
./scripts/start_docker.sh
```

It builds the images, starts PostgreSQL/pgvector and Neo4j/GDS, applies migrations, synchronizes prompts, loads the reference cohort, registers the local tenant graph, projects pending facts, and starts the API, Next.js UI, and continuous workers. It waits for every long-running service to become healthy before returning.

| Service | Local address |
|---|---|
| StackGraph UI | [http://localhost:3000](http://localhost:3000) |
| API readiness | [http://localhost:8080/health/ready](http://localhost:8080/health/ready) |
| Neo4j Browser | [http://localhost:7474/browser/](http://localhost:7474/browser/) |
| Neo4j Bolt | `neo4j://localhost:7687` |
| PostgreSQL | `localhost:5432` |
| GitHub webhook | `http://localhost:8090` |

Local Neo4j Browser credentials are:

```text
username: neo4j
password: stackgraph_neo4j
```

These defaults are for local development only. Set `STACKGRAPH_NEO4J_PASSWORD` and the other secrets through the production environment contract outside local development.

Common lifecycle commands:

```sh
make app-logs
make operations-snapshot
make app-down
```

Named PostgreSQL and Neo4j volumes survive `make app-down`. Preserve current database contents and skip the reference seed on the next start with:

```sh
./scripts/start_docker.sh --no-seed
```

Use `./scripts/start_docker.sh --help` for an explicit environment file, image reuse, seed control, startup timeout, and log-following options.

## Graph intelligence and embeddings locally

The quick start launches these services continuously:

| Service | Responsibility |
|---|---|
| `neo4j-projection-continuous` | Replays tenant projection deliveries, advances watermarks, reconciles logical relationships, and retries/dead-letters bounded failures. |
| `graph-intelligence-continuous` | Fairly schedules versioned GDS policies, enforces memory/time budgets, computes deterministic metrics, persists immutable snapshots, and optionally writes structural embeddings. |
| `embeddings-continuous` | Renders governed semantic documents, applies cache/quota/provider policy, persists pgvector values, and maintains space coverage. |

Useful graph commands:

```sh
# Register the default local tenant and project pending facts.
make neo4j-project

# Verify PostgreSQL projection state and live Neo4j counts.
make neo4j-verify

# Exercise graph-analysis and embedding control-plane invariants.
make database-graph-intelligence-verify

# Run projector and graph-intelligence unit suites in containers.
make graph-intelligence-test

# Measure extraction, Neo4j, GDS, and exact pgvector timings separately.
make graph-embeddings-benchmark \
  TENANT_ID=00000000-0000-0000-0000-000000000001 \
  SYNTHETIC_VECTOR_COUNT=10000
```

Neo4j is a disposable read/analysis projection. Do not edit it as a source of truth in Neo4j Browser; authoritative changes must enter through PostgreSQL-backed ingestion and review paths.

Local Neo4j Community supports normal projection, traversal, GDS analysis, and the contextual product experience. A real in-instance two-database blue/green switch requires Neo4j Enterprise staging. The implemented rebuild command is:

```sh
make neo4j-rebuild \
  TENANT_ID=<tenant-uuid> \
  CANDIDATE_DATABASE=<empty-candidate-database>
```

The rebuild streams a repeatable PostgreSQL snapshot, catches up concurrent deliveries, verifies node/relationship counts and SHA-256 checksums, and switches the deployment pointer only after parity succeeds.

## Product surfaces

- **Application Overview** shows criticality, dependency depth, centrality, structural risks, impact paths, similar applications, freshness, and limitations in context.
- **Technology detail** shows usage relationships and relevant graph intelligence for the selected technology.
- **Ask** can use semantic retrieval to identify likely entities before deterministic SQL/Neo4j answers and evidence-grounded summarization.
- **Reviews** presents explainable application-similarity candidates and controlled reviewer feedback.
- **Scan Health** exposes projection lag, graph snapshot age, embedding coverage, queue health, retries, provider performance, and failures.
- **Admin → Services** shows API, UI, PostgreSQL/pgvector, GitHub, enrichment, Neo4j projection, graph analysis, semantic embedding, and modernization-intelligence services with their heartbeat and control state.
- **Admin → Connections** binds already-authorized GitHub App installations without exposing private keys or short-lived installation tokens to the browser.

## GitHub continuous discovery

Configure `GITHUB_APP_ID` and either `GITHUB_APP_PRIVATE_KEY` or `GITHUB_APP_PRIVATE_KEY_FILE` in the Docker environment. Private keys and short-lived installation tokens remain server-side.

Direct repository connections using `GITHUB_TOKEN` remain available for development. The Admin UI lists only repositories visible to that credential that are not already active in the StackGraph estate.

The continuous pipeline performs repository acquisition, scanning, normalized ingestion, dependency and API-surface extraction, ecosystem enrichment, graph projection, graph analysis, and modernization intelligence without making interactive API latency depend on worker execution.

See [the continuous-discovery runbook](docs/runbooks/continuous-discovery-pipeline.md) and [GitHub installation lifecycle](docs/runbooks/github-installation-lifecycle.md) for configuration and recovery.

## Importing the public npm OSS catalog

The data platform can import the currently 5,232-row [DeepKlarity top npm packages dataset](https://huggingface.co/datasets/deepklarity/top-npm-packages) as global, evidence-backed OSS metadata:

```sh
make backend-up
make oss-catalog-import
```

The importer keeps every dataset column under `entity.properties.catalog_metadata`, creates package, latest-version, OSS-project, and repository entities, and publishes idempotent `EXTERNAL_MEASURED` facts. It pins the CSV revision and records its November 5, 2024 effective date so the metrics are not presented as current. Re-running unchanged content is a no-op.

To load a reviewed local copy instead:

```sh
docker compose run --rm \
  -v "$PWD/npm_packages.csv:/input/npm_packages.csv:ro" \
  oss-catalog --csv-file /input/npm_packages.csv \
  --effective-at 2024-11-05T09:18:44Z
```

Global catalog entities such as technologies, runtimes, databases, and packages are visible to eligible tenant embedding spaces. Their updates fan out to active/shadow spaces without allowing one tenant's private entities into another tenant's vectors.

## Verification

Run the focused checks:

```sh
make backend-test
make backend-integration-test
make graph-intelligence-test
CI=true PNPM_CONFIG_OFFLINE=true pnpm typecheck
CI=true PNPM_CONFIG_OFFLINE=true pnpm lint:css
CI=true PNPM_CONFIG_OFFLINE=true pnpm exec playwright test --project=chromium
```

Run the disposable fresh-install and upgrade matrix with:

```sh
make fresh-integration
```

The matrix validates the canonical schema, ordered migrations, tenant RLS, global-catalog visibility, projection and embedding control-plane invariants, API integration, data-platform behavior, and enterprise discovery without modifying the normal local database.

## Production deployment

Production keeps one Neo4j security deployment per StackGraph tenant by default and may track multiple organizations inside it. The selected profile is self-managed Neo4j Enterprise plus GDS Enterprise on private networking with certificate-validated `neo4j+s://` endpoints. PostgreSQL backup/restore remains authoritative; Neo4j backups are optional recovery acceleration.

Render and launch the production profile with an explicit `.env.production` contract:

```sh
make production-config
make production-up
```

Production promotion deliberately requires:

- Neo4j/GDS licensing, procurement, security, capacity, residency, backup, and unit-cost approval;
- an Enterprise staging drill of concurrent-write blue/green rebuild and atomic pointer activation;
- per-tenant GDS memory estimates within the configured heap guard;
- exact pgvector relevance and latency evidence before considering tenant-isolated ANN;
- reviewed evidence that structural embeddings outperform the deterministic baseline before leaving `SHADOW`;
- explicit authorization for any generated application-description workflow—curated descriptions are never automatically overwritten.

See the [deployment profile](docs/architecture/graph-intelligence-deployment-profile.md), [production runbook](docs/runbooks/production-deployment.md), and [graph/embedding operations runbook](docs/runbooks/graph-and-embeddings-operations.md).

## Repository map

| Path | Purpose |
|---|---|
| `apps/api` | FastAPI service, normalized SQL/Neo4j readers, authorization, operations, and read models. |
| `apps/web` | Next.js product UI and contextual graph/embedding experiences. |
| `services/data-platform` | Migrations/seeding tools, ecosystem ingestion, Neo4j projector/rebuild, and benchmarks. |
| `services/intelligence/graph-intelligence` | GDS analysis, deterministic graph algorithms, embeddings, evaluation, and worker orchestration. |
| `infrastructure/database` | PostgreSQL/pgvector image, ordered migrations, grants, and SQL smoke tests. |
| `stackgraph-foundation` | Canonical schema and versioned API/read-model contracts. |
| `packages/shared` | Generated and hand-authored TypeScript API/read-model clients. |
| `docs/runbooks` | Local, production, ingestion, graph, embedding, and recovery procedures. |

## Key documentation

- [Graph intelligence and embeddings implementation](docs/graph-and-embeddings-features.md)
- [Graph and embedding operations](docs/runbooks/graph-and-embeddings-operations.md)
- [Graph-intelligence deployment profile](docs/architecture/graph-intelligence-deployment-profile.md)
- [Local backend](docs/runbooks/local-backend.md)
- [Continuous discovery pipeline](docs/runbooks/continuous-discovery-pipeline.md)
- [Production deployment](docs/runbooks/production-deployment.md)
- [Failure and recovery drills](docs/failure-and-recovery-drills.md)
- [Operations SLOs](docs/operations-slo.md)
