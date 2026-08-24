# Graph and embedding intelligence operations

PostgreSQL is authoritative for facts, evidence, queues, policies, metric snapshots, vectors, and reviews. Neo4j is a tenant-scoped disposable projection used for traversal and GDS. A Neo4j loss is recoverable from PostgreSQL; a PostgreSQL loss is not recoverable from Neo4j.

## Runtime topology

The `pipeline` profile runs three independent stages after discovery publishes facts:

1. `neo4j-projection-continuous` projects stable entity and fact UUIDs and advances a tenant watermark.
2. `graph-intelligence-continuous` runs versioned deterministic GDS policies only after projection catch-up and atomically activates complete PostgreSQL snapshots.
3. `embeddings-continuous` renders provenance-bearing entity documents, generates vectors in isolated spaces, and rebuilds explainable application-similarity candidates.

Each tenant has a `tenant_graph_deployment` registry entry. The standard security boundary is one Neo4j deployment per StackGraph tenant; multiple tracked organizations remain governed Organization nodes inside that tenant unless they require separate credentials, residency, retention, or administration.

Development uses `stackgraph-postgres:pg16-pgvector`, which layers pgvector onto the transitional AGE-compatible PostgreSQL 16 image so existing local volumes remain readable. Production defaults to `pgvector/pgvector:pg16`; AGE is not required. Neo4j/GDS is deployed separately.

## Health and alert interpretation

The API `/metrics` endpoint exports every signal as `stackgraph_operational_signal` and its threshold state as `stackgraph_operational_alert`. Prometheus routes the generic breach alert with the signal owner.

| Signal | Default gate | First checks |
|---|---:|---|
| `graph_projection_lag_events` | 1,000 events | Neo4j connectivity, deployment state, delivery retries |
| `graph_projection_queue_age_seconds` | 5 minutes | expired projection lease, oldest delivery error |
| `graph_analysis_queue_age_seconds` | 10 minutes | projection watermark, GDS capacity, tenant service state |
| `failed_graph_analysis_requests` | any unrecovered failure | run error, policy hash, GDS limitation or memory estimate |
| `graph_snapshot_age_seconds` | 30 minutes | active policy coverage, coalesced successor request |
| `embedding_queue_age_seconds` | 10 minutes | provider rate limit, worker heartbeat, policy state |
| `expired_embedding_leases` | any | worker termination and lease recovery |
| `dead_letter_embedding_jobs` | any | error class, sensitivity/provider policy, retry horizon |
| `embedding_coverage_gap_basis_points` | active coverage below 95% | missing documents, dead letters, active-space gate |
| `embedding_provider_failures_24h` | any | provider outage/5xx, circuit breaker, tenant credentials |

Provider request, cache-hit, token, latency, and rate-limit counters are exported as telemetry even when they do not breach an alert threshold. Use them to size provider quotas and distinguish a healthy content-hash cache from suppressed work.

Before projection, the worker counts the policy graph and calls `gds.graph.project.estimate` with the prospective node/relationship counts. It records `bytesMin`, `bytesMax`, required memory, and the configured `STACKGRAPH_GDS_MAX_PROJECTION_BYTES` budget in `resource_usage`; the default 5 GiB cap leaves the Small profile's 8 GiB heap guard intact. GDS also performs its automatic execution-time estimate for supported algorithms. A budget or automatic-memory rejection fails the run without replacing the active snapshot.

The Health page is tenant-scoped and shows projection lag, graph request state, active semantic coverage, candidate spaces, and queue failures. Admin → Services provides pause/resume controls and worker heartbeat context.

Useful database checks:

```sql
SELECT tenant_id,deployment_state,desired_outbox_id,projected_outbox_id,
       desired_outbox_id-projected_outbox_id AS lag,last_error
FROM tenant_graph_deployment ORDER BY lag DESC;

SELECT tenant_id,status,count(*),min(created_at) AS oldest
FROM graph_analysis_request GROUP BY tenant_id,status ORDER BY tenant_id,status;

SELECT tenant_id,status,count(*),min(created_at) AS oldest
FROM embedding_job GROUP BY tenant_id,status ORDER BY tenant_id,status;

SELECT space.tenant_id,space.space_key,space.lifecycle_state,space.coverage_ratio,
       space.evaluation,space.last_error
FROM embedding_space space ORDER BY space.tenant_id,space.created_at DESC;
```

## Recovery procedures

### Projection outage

1. Leave PostgreSQL ingestion running. Pending `graph_projection_delivery` rows are durable.
2. Restore Neo4j connectivity or credentials and set the deployment back to `ACTIVE` only after a connection test.
3. Start the projection worker. Idempotent MERGE operations safely replay processing leases.
4. Confirm the projected watermark catches the desired watermark and the queue drains.
5. Confirm one coalesced graph-analysis request is created after catch-up, then compare active snapshot counts and checksums.

Do not mark outbox or delivery rows processed manually. A terminal delivery must be replayed from its dead-letter metadata after the underlying error is fixed.

### Full Neo4j loss or upgrade

Provision an empty candidate database and run `make neo4j-rebuild TENANT_ID=... CANDIDATE_DATABASE=...`. The rebuild command leases projection, streams a repeatable PostgreSQL snapshot, validates node/edge counts and UUID checksums, catches up deliveries created after the snapshot watermark, and atomically switches the registry pointer. The old graph can be destroyed after its retention/parity window. PostgreSQL backup/restore is the only authoritative backup procedure; Neo4j backup is optional acceleration. See [the selected deployment profile](../architecture/graph-intelligence-deployment-profile.md).

### Graph-analysis failure

The last complete active snapshot remains readable. Fix the policy, capacity, GDS compatibility, or projection condition and enqueue a successor. Never edit an immutable run or activate a failed/partial run manually. `SUCCEEDED_WITH_LIMITATIONS` is valid only when every persisted metric is complete and omitted algorithms carry explicit limitations.

### Embedding-provider outage

Graph analysis continues independently. Retryable 429/5xx jobs honor provider delay and exponential backoff; terminal policy, dimension, or credential errors dead-letter. Restore the provider or change tenant policy, create a new shadow space if provider/model/template/dimensions changed, enqueue affected entities, evaluate, and activate only after at least 95% coverage and a passing evaluation. Never mix vectors from different spaces.

## Security and privacy

- The application never accepts a client-supplied tenant ID. RLS covers graph controls, snapshots, embedding spaces/documents/vectors/jobs, similarity, motifs, anomalies, proposals, and feedback.
- Neo4j credentials are tenant-bound encrypted secrets or runtime secret references. Endpoints may not contain credentials.
- External embedding processing is off by default. It requires tenant opt-in; confidential or restricted content requires a separate explicit opt-in.
- Documents retain source fact UUIDs, source revision, template version, content hash, and sensitivity. Provider keys and raw credentials never enter documents, logs, metrics, Neo4j properties, or API responses.
- Semantic spaces include tenant entities plus the governed global Technology, Runtime, Database, and Package catalog. Global changes fan out to eligible tenant spaces; a reusable visibility trigger accepts global references and rejects another tenant's private entity.
- Similarity feedback is append-only. A candidate is derived intelligence, not an authoritative relationship.

## Rollout and rollback

Deploy migrations before workers and API. Start with projection, then deterministic graph analysis, then local embeddings. Keep semantic spaces in `SHADOW` until coverage and evaluation gates pass. Activate one space kind atomically; the trigger retires the prior active space. API search always embeds a query with the exact active provider/model/template/dimensions.

Rollback application code without deleting new tables. Pause `graph-intelligence` or `embeddings` through tenant service controls if a worker is unhealthy. Retire a bad space by activating the last evaluated compatible space; do not rewrite vectors in place.

Exact tenant-filtered cosine search is the initial production path. Record p50/p95 latency, candidate count, and relevance evaluation by tenant size. Consider partitioned or tenant-specific HNSW only when exact p95 exceeds the agreed interactive budget; require a recall and isolation review before enabling approximate search.

## Verification commands

```shell
docker compose config -q
docker compose --profile pipeline up -d
docker compose run --rm --no-deps api pytest -q
make graph-intelligence-test
make graph-embeddings-benchmark TENANT_ID=... SYNTHETIC_VECTOR_COUNT=10000
```

For a fresh database, apply `stackgraph-foundation/schema.sql`, then run:

```shell
psql --set ON_ERROR_STOP=1 --file infrastructure/database/tests/neo4j-projection-smoke.sql
psql --set ON_ERROR_STOP=1 --file infrastructure/database/tests/graph-analysis-control-plane-smoke.sql
psql --set ON_ERROR_STOP=1 --file infrastructure/database/tests/embedding-control-plane-smoke.sql
```

The embedding smoke test rejects an unqualified active space, verifies atomic replacement, rejects a vector dimension mismatch, accepts tenant-visible global catalog vectors while rejecting cross-tenant private references, verifies global-catalog job fan-out, proves tenant RLS isolation through a non-owner role, and proves review feedback is immutable.
