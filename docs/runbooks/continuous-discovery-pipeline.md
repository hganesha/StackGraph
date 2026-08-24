# Continuous discovery pipeline runbook

This runbook operates the durable Lane A/B/D path from GitHub target scheduling through repository evidence,
fact publication, tenant Neo4j projection, and repository intelligence. It complements the
[GitHub installation lifecycle](github-installation-lifecycle.md) and
[repository dependency analysis](repository-dependency-analysis.md) runbooks.

## Processing topology

The `pipeline` Compose profile runs six restartable services:

1. `github-webhook` verifies and records provider deliveries, then creates or advances durable targets/runs.
2. `github-control-loop` schedules due installation and repository targets and leases one run at a time.
3. `neo4j-projection-continuous` drains per-tenant fact close/upsert deliveries into the tenant's registered Neo4j graph.
4. `intelligence-continuous` drains complete repository snapshots into capability and modernization analysis,
   resolving the encrypted provider/model independently for each job's tenant.
5. `graph-intelligence-continuous` claims coalesced tenant analysis requests after Neo4j reaches their authoritative watermark, runs deterministic GDS policies, and atomically activates complete PostgreSQL snapshots.
6. `embeddings-continuous` drains the separate entity/content queue, evaluates shadow spaces, and persists tenant-scoped pgvector embeddings and explainable application-similarity candidates.

The database is the queue of record. Provider work is never inferred from an in-memory timer alone. A worker
restart either leaves a pending run claimable or lets a running lease expire and become claimable again. A lease
that expires at the maximum attempt count is failed and copied to `dead_letter`.

## Start and stop

Apply migrations, sync the governed capability/policy catalogs for the environment, and register at least one
GitHub installation before starting the services. The local profile resolves `env://GITHUB_INSTALLATION_TOKEN`.

```shell
export GITHUB_INSTALLATION_TOKEN=ghs_short_lived_value
export GITHUB_WEBHOOK_SECRET=replace-with-runtime-secret
export STACKGRAPH_CREDENTIAL_ENCRYPTION_KEY=replace-with-at-least-32-random-characters
make pipeline-up
make pipeline-logs
```

Stop workers without deleting durable queues, evidence, snapshots, or database state:

```shell
make pipeline-down
```

For a bounded diagnostic pass, run:

```shell
make github-pipeline-work
```

## Repository run lifecycle

For each active connector, the control loop:

- creates one reconciliation run for a due installation target, without duplicating existing pending/running work;
- reconciles the complete paginated authorized repository set and advances its cadence;
- prioritizes webhook/manual/replay repository runs ahead of scheduled runs;
- fetches repository and default-branch revision metadata;
- completes an unchanged revision without fetching blobs or invoking the scanner;
- stores a changed snapshot in the tenant-scoped checksum store before scanning;
- scans only the materialized immutable snapshot and publishes through `persist_scanner_result_connection`;
- updates freshness and schedules the target's next cadence;
- relies on snapshot publication to enqueue projection and complete-snapshot intelligence work.

The default lease is 30 minutes. A provider/network failure retries with a bounded provider hint or exponential
delay. Validation, credential, identity, and non-retriable provider failures terminate immediately. Terminal runs
create a dead letter containing identifiers and error metadata, never a credential value.

## Verification queries

Queue state and oldest available work:

```sql
SELECT status,count(*),min(available_at) oldest_available
FROM ingest_run
GROUP BY status ORDER BY status;
```

Freshness and terminal failures:

```sql
SELECT target.target_kind,target.target_key,fresh.status,fresh.expected_by,
       fresh.last_source_revision
FROM ingest_target target
LEFT JOIN freshness_state fresh ON fresh.ingest_target_id=target.id
WHERE target.enabled
ORDER BY fresh.expected_by NULLS FIRST;

SELECT source_kind,error_class,count(*),max(failed_at) latest
FROM dead_letter WHERE replayed_at IS NULL
GROUP BY source_kind,error_class ORDER BY latest DESC;
```

Projection and intelligence lag:

```sql
SELECT count(*) pending,min(created_at) oldest
FROM projection_outbox WHERE processed_at IS NULL;

SELECT status,count(*),min(created_at) oldest
FROM intelligence_job GROUP BY status ORDER BY status;

SELECT status,count(*),min(created_at) oldest
FROM graph_analysis_request GROUP BY status ORDER BY status;

SELECT status,count(*),min(created_at) oldest
FROM embedding_job GROUP BY status ORDER BY status;
```

## Recovery drill

1. Stop `github-control-loop` while it owns a run.
2. Confirm the run remains `RUNNING` with `lease_expires_at` populated.
3. Start the worker after lease expiry and confirm the same run is reclaimed with a higher attempt.
4. Confirm changed content produces one published source snapshot; replay must not duplicate facts.
5. Stop and restart projection, graph-analysis, embedding, and repository-intelligence consumers and confirm their independent durable queues drain.
6. Inspect freshness and unresolved dead letters before declaring recovery complete.

## Production boundary

This profile is a deployable reference topology, not proof of production operations. A production deployment still
needs a secret-manager resolver that mints short-lived installation tokens, TLS ingress, managed object storage,
resource limits/autoscaling, graceful termination sized to the lease, exported queue/quota metrics, alert routes,
and a completed backup/restore/replay drill. Multiple installation credentials must be exposed through their
referenced runtime variables or a deployment-specific secret broker.
