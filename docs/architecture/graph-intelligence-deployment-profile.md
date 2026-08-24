# Graph intelligence deployment profile

**Decision:** production uses one self-managed Neo4j Enterprise deployment with Graph Data Science Enterprise per StackGraph security tenant. A tenant may contain multiple `BUSINESS.Organization` entities. Development uses the single-database Community/GDS image in Compose; it is not the production topology.

This profile is an engineering selection, not a grant of commercial rights. Procurement must approve the Neo4j and GDS terms and the deployment owner must record the contracted unit price before enabling a production tenant.

## Version and capability pin

The reference pin is Neo4j `2026.07.x` with GDS `2026.07`. Neo4j's current compatibility matrix pairs those release lines. Patch upgrades must pass the graph golden fixtures, projection parity, blue/green rebuild, and representative capacity benchmark before rollout.

| StackGraph module | Selected operation | GDS maturity / fallback |
|---|---|---|
| Degree in/out | `gds.degree.stream` | production GDS operation |
| PageRank | `gds.pageRank.stream` | production GDS operation |
| Betweenness | `gds.betweenness.stream` with recorded deterministic sampling | production GDS operation; exact mode remains size-gated |
| Components | `gds.wcc.stream` | production GDS operation |
| Communities | WCC now; Louvain/Leiden only through a new versioned policy | no silent algorithm substitution |
| Articulation points / bridges | `stackgraph.tarjan-v1` bounded adapter | current GDS exposes production articulation/bridge procedures; StackGraph retains its fact-ID-aware oracle until parity and result-mapping fixtures approve a switch |
| Structural embedding | `gds.node2vec.stream` with fixed seed | production GDS operation; results remain `SHADOW` until reviewed relevance and stability gates pass |
| Reachability / impact paths | `stackgraph.bfs-v1` over the normalized edge stream | deterministic evidence/fact path adapter; Neo4j is used for bounded interactive traversal |

At startup and before a policy run, operators can verify `gds.version()`, `gds.isLicensed()`, and the required entries in `gds.list()`. Missing or incompatible optional procedures produce explicit limitations; missing required deterministic procedures fail the run without replacing the active snapshot.

Official references: [database administration and edition database limits](https://neo4j.com/docs/operations-manual/current/database-administration/), [GDS/Neo4j compatibility](https://neo4j.com/docs/graph-data-science/current/installation/supported-neo4j-versions/), [GDS installation and license checks](https://neo4j.com/docs/graph-data-science/current/installation/), [algorithm operations and maturity](https://neo4j.com/docs/graph-data-science/current/operations-reference/algorithm-references/), and [memory estimation](https://neo4j.com/docs/graph-data-science/current/common-usage/memory-estimation/).

## Isolation and network

- One tenant deployment is one physical security, credential, residency, retention, and noisy-neighbor boundary.
- The PostgreSQL deployment registry selects the endpoint; application code never derives it from a tenant ID.
- Production endpoints use certificate-validated `neo4j+s://` and private networking. Security groups permit Bolt only from the projector, graph-intelligence worker, and API reader identities assigned to that tenant.
- Credentials are encrypted tenant secrets or injected `env://` references in local development. Endpoints cannot contain credentials. Credential rotation updates the reference, tests connectivity, and restarts the bounded client pools without changing graph identity.
- Neo4j UUID properties are PostgreSQL entity/fact IDs. Internal Neo4j IDs never appear in contracts, snapshots, or reviews.

## Blue/green rebuild and recovery

Enterprise multi-database support is required because the selected rebuild path streams a repeatable PostgreSQL snapshot into an empty candidate database, catches up outbox changes, validates node and relationship UUID counts/checksums, and atomically changes `tenant_graph_deployment.database_name`. The prior database name is retained for inspection. A rollback rebuilds that prior database from PostgreSQL and switches it through the same parity gate; it is not a blind stale-pointer swap.

Run:

```bash
docker compose run --rm neo4j-projection rebuild \
  --tenant-id "$TENANT_ID" \
  --candidate-database "$CANDIDATE_DATABASE"
```

The command leases projection, records candidate state/watermarks, emits separated extraction/write/validation timings, and releases the lease on success or failure. Ingestion continues throughout. Interactive reads fall back to relational SQL whenever Neo4j is behind or unavailable. PostgreSQL backup/restore is authoritative; Neo4j backups are optional recovery acceleration and never replace a rebuild drill.

Community Edition supports one standard database, so the local Compose instance cannot exercise an in-instance two-database switch. CI/staging must use the selected Enterprise profile or two isolated candidate instances for the destructive rebuild drill.

## Initial capacity classes

These are conservative starting envelopes for pilots, not vendor guarantees. Each tenant must run GDS `.estimate` procedures and the checked-in benchmark against its actual projection before class assignment. GDS operates on heap, and undirected projections may store relationships twice; estimates and a minimum 30% free-heap guard take precedence over this table.

| Class | Policy ceiling (nodes / relationships) | Starting compute | Starting memory split | Behavior above envelope |
|---|---:|---:|---|---|
| Small | 50k / 250k | 4 vCPU | 16 GiB total; 8 GiB heap, 2 GiB page cache | queue a resize; lightweight metrics may publish with limitations |
| Medium | 250k / 2m | 8 vCPU | 32 GiB total; 20 GiB heap, 4 GiB page cache | sampled betweenness; Node2Vec remains separately gated |
| Large | 1m / 10m | 16 vCPU | 64 GiB total; 44 GiB heap, 8 GiB page cache | dedicated benchmark/approval; split policies or skip heavy modules rather than truncate silently |

Default GDS concurrency is 2. Increase it only when concurrent projection and interactive traversal SLOs remain green. Before every large graph projection or algorithm, call the matching `.estimate` operation and reject work whose `bytesMax` would consume the free-heap guard.

## Cost and approval record

Record these per tenant in the deployment ticket and telemetry:

```text
monthly_unit_cost = compute + memory + persistent_storage + backup + network + license
cost_per_analysis = allocated_runtime_seconds * unit_runtime_rate
cost_per_projected_million_edges = monthly_unit_cost / projected_edge_millions
```

Required approval fields are contracted Neo4j/GDS edition and term, region, capacity class, monthly unit-cost ceiling, backup retention, RTO/RPO, data residency, and owner. No placeholder dollar value in this document authorizes production spend.

## Promotion gates

1. Fresh install, upgrade, PostgreSQL restore, and Neo4j loss/rebuild pass.
2. Cross-tenant credential/endpoint tests and same-tenant multi-organization paths pass.
3. Projection and normalized reader parity pass at the same watermark.
4. Blue/green catch-up and atomic switch pass under concurrent authoritative writes.
5. GDS estimates fit with the heap guard; p50/p95 extraction, Neo4j write, GDS projection, algorithm, and result-transfer measurements are attached.
6. Exact pgvector p50/p95/p99 and relevance gates pass. ANN remains disabled unless its separate recall/isolation review passes.
7. Engineering, security, operations, procurement, and the tenant owner approve the deployment record.
