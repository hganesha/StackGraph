# Graph intelligence and embeddings feature plan

**Status:** implemented and verified through the contextual UI, with production-only promotion gates called out below

**Source reviewed:** [Enterprise graph embeddings.md](./Enterprise%20graph%20embeddings.md)

**Enhancement review:** [graph-enhancements.md](./graph-enhancements.md) — post-merge gap review and sequenced actions for API services and UI

**Decision summary:** build a separate `graph-intelligence` worker and use Neo4j as the tenant-scoped, asynchronous graph projection and GDS execution engine. Keep PostgreSQL as the only authoritative store for entities, facts, evidence, reviews, jobs, graph-analysis snapshots, and pgvector embeddings. A Neo4j graph is disposable and fully rebuildable from PostgreSQL. Compute explainable graph metrics before introducing graph embeddings. Use embeddings to retrieve and rank candidates; never treat vector similarity as proof or as an authoritative graph relationship.

## Implementation outcome

The plan is implemented end to end in migrations `026` through `040`, the Neo4j projection and graph-intelligence workers, the FastAPI read models, the shared TypeScript client, and the existing application, technology, Ask, Reviews, Admin, and Scan Health surfaces. PostgreSQL remains authoritative; `auto` graph reads use a caught-up tenant Neo4j deployment and fail closed to the bounded SQL reader on lag, outage, parity failure, or discovery-cap overflow. AGE is retained only as an explicit legacy read mode.

| Delivery area | Implemented outcome |
|---|---|
| Tenant graph | Tenant deployment registry, encrypted credential/reference boundary, delivery fan-out, idempotent logical-relationship projection, watermarks, leases, retry/dead-letter behavior, reconciliation, and PostgreSQL-snapshot blue/green rebuild orchestration. |
| Deterministic intelligence | Fair/coalesced analysis requests, immutable active snapshots, degree, PageRank, sampled betweenness, reach/depth, Tarjan articulation/bridges, impact paths, WCC communities, cohort anomalies, circular motifs, limitations, and resource telemetry. |
| Similarity and reviews | IDF-weighted deterministic application features, hard-negative-aware explanations, persisted candidates, controlled append-only feedback, review API, and contextual UI. |
| Semantic embeddings | Versioned spaces and renderers, tenant policy, provider/local adapters, content-hash cache, quota/retry/dead-letter handling, pgvector persistence, reviewed relevance evaluation, shadow/active swap, exact tenant-scoped search, and global technology catalog fan-out with private-tenant rejection. |
| Structural embeddings | GDS Node2Vec persisted into isolated SHADOW spaces, stability/evaluation metadata, and hybrid ranking that renormalizes only available signals. |
| Product/UI | No new top-level page. Application and technology detail show contextual graph intelligence; Ask can use semantic retrieval before deterministic answers; Reviews handles similarity decisions; Scan Health and Admin expose graph/embedding readiness and worker controls. |
| Operations | Compose services, health/status APIs, Prometheus signals, runbook, selected deployment profile, deterministic benchmark command, rebuild command, and fresh-install matrix. |

The representative performance snapshot contained 64,906 current facts and 55,049 relationships with the tenant projection caught up at watermark 164,601. Ten warm/cold Neo4j count samples measured p50 `0.586 ms`; a deterministic temporary 2,000-vector, 64-dimension exact pgvector corpus measured top-10 p50 `0.247 ms` and p95 `0.502 ms`. A later full live reconciliation streamed 82,951 current facts into 22,385 governed nodes and 55,049 contracted logical relationships; PostgreSQL and Neo4j node and relationship SHA-256 checksums matched exactly. The latest real GDS runs processed 5,917 and 12,998 policy nodes and recorded GDS projection, server execution/result-consumption, client/transfer overhead, and total wall time separately. These measurements are reproducible with `make graph-embeddings-benchmark`; they are evidence for this development corpus, not universal production SLOs.

The final disposable matrix passes 158 API tests (plus one intentional legacy-AGE skip), 61 data-platform tests, and 71 enterprise-discovery tests. Projection and graph-intelligence unit suites pass 10 and 19 tests respectively. Workspace type checks, CSS lint, production UI build, SQL control-plane smokes, live Neo4j/GDS analysis, the authenticated operations query, and production Compose rendering also pass.

The following are deliberate promotion gates rather than unfinished hidden behavior:

- Production uses self-managed Neo4j Enterprise plus GDS Enterprise per security tenant; license, procurement, actual unit price, and capacity approval belong to the deployment owner. The selected version/capacity/security profile is [graph-intelligence-deployment-profile.md](architecture/graph-intelligence-deployment-profile.md).
- Community Edition has one standard database, so the implemented atomic blue/green pointer switch must be drilled against two databases in Enterprise staging before production promotion. A failed build leaves the active pointer unchanged.
- ANN remains disabled until an exact-search corpus misses its SLO and a tenant-isolated ANN design passes declared recall-at-k and operational tests.
- Structural spaces remain SHADOW until reviewed relevance/stability results beat the deterministic baseline. A model or algorithm does not self-promote.
- Generated application descriptions have a governed proposal/provenance schema but are not auto-generated or allowed to overwrite curated text. Existing descriptions are embedded now; generation remains an optional, separately authorized downstream feature.

## 1. Executive recommendation

The proposal is strong and fits StackGraph's existing product direction. Much of its value does not require an LLM or even graph embeddings: blast radius, dependency depth, articulation points, centrality, community structure, and cross-team coupling are deterministic products of the graph plus governed business context. These should be the first deliverables.

The recommended architecture is:

```text
PostgreSQL authoritative entity/fact/evidence tables
                         |
                 projection outbox/watermark
                         v
             tenant-scoped Neo4j projection
                         |
                    Neo4j GDS
                         v
              graph-intelligence worker
                |                    |
                |                    +--> PostgreSQL metric/review snapshots
                +--> embedding jobs/adapters --> PostgreSQL pgvector
                                             |
                                             v
                                     API read models / Ask
```

The worker remains a good service boundary even with GDS because scheduling, fairness, graph revisions, policy, score composition, result activation, feedback, and governance remain StackGraph responsibilities. GDS supplies graph algorithms; it does not replace the control plane. A bad centrality run must not delay graph projection, repository scanning, or interactive requests.

The initial product slice should be **Enterprise Graph Intelligence**, not a generic vector-search project:

1. application/component criticality and hidden infrastructure;
2. transitive blast radius and dependency depth;
3. structural single points of failure;
4. application similarity and consolidation candidates;
5. semantic search over applications and other governed entities;
6. evidence-backed application descriptions as an optional downstream feature.

## 2. Findings from the current repository

The implementation can extend existing foundations rather than introduce a second data platform:

- PostgreSQL is already authoritative for `entity`, bitemporal `fact_assertion`, evidence, review state, jobs, and read models.
- Apache AGE was the original asynchronous projection named `stackgraph`. Neo4j is now the production interactive/analysis projection; AGE is an explicit legacy mode and SQL remains the correctness/outage fallback.
- The projection outbox and PostgreSQL leased-work pattern already establish replay, `FOR UPDATE SKIP LOCKED`, retries, dead letters, and service heartbeat conventions.
- The current intelligence worker is repository-scoped and its `intelligence_job` contract only admits `REPOSITORY_MODERNIZATION`. Graph-wide jobs have different inputs and should not be forced into that table or process.
- Several useful product questions already exist as deterministic SQL reports: systemic dependency risk, reachable vulnerabilities, governed package blast radius, duplicate capabilities, technology diversity, and retirement/consolidation. New graph features should improve and generalize these reports, not create competing answers.
- Application summaries are currently read from entity properties such as `purpose`, `definition`, and catalog metadata. This gives semantic embeddings an immediate use case, but also means description coverage and provenance must be measured before similarity scores are presented as complete.
- The development database image currently bundles AGE. The Neo4j decision removes AGE from the target PostgreSQL requirement; PostgreSQL only needs the existing relational extensions plus pgvector for semantic embeddings.
- The authoritative graph already exists relationally in `entity` plus current entity-valued `fact_assertion` rows. That representation is the projection and full-rebuild source for every tenant Neo4j graph.

## 3. Product and data principles

### 3.1 Deterministic structure first

Use explicit traversal and graph algorithms for questions that have structural answers. Embeddings are inappropriate for proving reachability, blast radius, shortest paths, articulation points, or dependency depth.

Every surfaced score must retain:

- the graph revision and analysis run;
- algorithm and configuration version;
- included predicates, namespaces, confidence floor, and scope;
- component metrics rather than only a composite number;
- freshness and coverage limitations;
- supporting fact IDs or a reproducible path query.

### 3.2 Embeddings retrieve candidates; governed evidence supports conclusions

An embedding may suggest that two applications are similar. A consolidation recommendation must still explain the overlap using capabilities, dependencies, business ownership, deployment context, source evidence, and important differences.

Do not immediately project `SIMILAR_TO` edges into Neo4j. Persist unreviewed similarity candidates as derived intelligence in PostgreSQL. Only a governed decision or evidence-backed inference should become an authoritative fact and then a projected edge.

### 3.3 Separate embedding spaces

The following vectors are not interchangeable and must never be compared across spaces:

- **semantic entity embedding:** text describing an application, service, technology, capability, or recommendation;
- **structural graph embedding:** graph neighborhood learned from topology, such as Node2Vec;
- **code embedding:** source/code-unit meaning, if added later;
- **query embedding:** transient vector generated in the same semantic space as the searched documents.

Every stored vector therefore needs an embedding-space identity, dimensions, provider/model or algorithm, normalization, source-template version, and content/input hash.

### 3.4 Derived intelligence is versioned and disposable

Graph metrics and vectors can be regenerated from authoritative inputs. They should be snapshotted for reproducibility and audit, but they are not the source of truth. A failed or incomplete run must never overwrite the last complete run.

### 3.5 Tenant isolation precedes ANN performance

All jobs, input queries, result tables, and vector searches must be tenant-scoped and covered by RLS. Exact nearest-neighbor search is acceptable for the first estate sizes. Approximate indexes should be introduced only after a measured latency threshold and an isolation/recall design review.

pgvector documents that approximate search applies filters after scanning and that a shared multi-tenant ANN index can affect recall and speed across tenants. It recommends partitioning or separate tables where stronger isolation is needed. Start with exact search plus a tenant B-tree filter, benchmark it, and then choose tenant partitions or iterative HNSW scans deliberately. See the [pgvector project documentation](https://github.com/pgvector/pgvector#readme).

### 3.6 Neo4j is a disposable derived projection

No authoritative table, public API contract, analysis-run identity, review, or evidence record may depend on a Neo4j internal node/relationship identifier. Project PostgreSQL entity UUIDs and fact UUIDs as stable Neo4j properties with uniqueness constraints. PostgreSQL remains sufficient to rebuild the entire graph and reproduce the facts supporting any result.

Maintain two readers behind one normalized graph contract:

- `RelationalGraphReader`: required correctness/fallback implementation; streams tenant-visible entities and current fact edges from PostgreSQL.
- `Neo4jGraphReader`: selected production traversal/GDS implementation; must pass parity tests against the relational reader for the same change watermark and policy.

Neo4j projection lag or unavailability must degrade interactive traversal to existing SQL behavior and leave the last complete graph-intelligence snapshot readable. It must never block ingestion or authoritative PostgreSQL writes.

### 3.7 Tenant and organization boundaries

The default deployment unit is one Neo4j database or managed instance per StackGraph tenant. This makes the tenant security boundary physical and avoids depending on property filters for cross-customer isolation.

A customer tenant may contain multiple tracked organizations, subsidiaries, portfolios, or GitHub organizations. Model those as `BUSINESS.Organization` entities and explicit membership/ownership relationships inside the same tenant graph. Keep their rows under the same PostgreSQL `tenant_id` when users are allowed to analyze relationships across them.

Create separate StackGraph tenant IDs—and therefore separate Neo4j deployments—only when hard isolation, credentials, residency, retention, administration, or billing must differ. Splitting ordinary organizations into tenant IDs prevents direct cross-organization paths and would require an explicit federation product later.

## 4. Analysis graph contract

Before implementing algorithms, define a versioned graph view. Without this contract, two valid-looking metrics can have incompatible meanings.

### 4.1 Required policy

`graph_analysis_policy` should define:

- included namespaces and entity types;
- included predicates and their semantic direction;
- whether a predicate participates in operational, ownership, business, security, or technology views;
- minimum confidence and allowed assertion classes;
- treatment of confirmed, possible, and rejected identity assertions;
- current-fact and snapshot completeness rules;
- maximum traversal depth and node/edge safety limits;
- edge weights and business criticality normalization;
- whether global catalog nodes may participate in a tenant run.

Start with multiple named projections rather than one overloaded graph:

| Projection | Primary nodes/edges | Used for |
|---|---|---|
| `runtime-dependency-v1` | Application, Repository, Service, Component, API, Package, Database, Deployment; dependency/runtime edges | blast radius, depth, centrality, SPOFs |
| `business-alignment-v1` | Applications, capabilities, processes, business maps, owners | business-weighted risk and coverage |
| `ownership-v1` | components, repositories, applications, teams/owners | team crossings and Conway coupling |
| `technology-portfolio-v1` | applications/repositories, packages, technologies, capabilities | similarity, diversity, consolidation |

The current ontology does not yet include a Team entity or incident/change entities. Ownership and change-propagation features therefore require ontology and ingestion work and should not be claimed in the first release.

### 4.2 Direction and scope

Normalize edges into a consistent impact direction for each analysis. For example, if `A DEPENDS_ON B`, failure impact travels from `B` to `A`, while dependency exposure travels from `A` to `B`. Store both metric names explicitly rather than using an ambiguous `reach` field.

Use confirmed `SAME_AS` identities to collapse duplicates for analysis. Exclude rejected identities. Treat possible identities as separate nodes and expose them as a coverage limitation unless a particular policy explicitly permits them.

### 4.3 Data readiness gate

An application-level insight should be `WAITING_FOR_DATA` or coverage-qualified when the tenant lacks enough of the following:

- repository-to-application mapping;
- complete dependency snapshots;
- application criticality/business capability mapping;
- current ownership data;
- deployment/environment observations;
- source and projection freshness.

Do not silently rank repository/package topology and label it application criticality.

## 5. Worker and scheduling design

Create `services/intelligence/graph-intelligence/` as an independently deployable Python service with its own Docker image and Compose service, `graph-intelligence-continuous`.

### 5.1 Responsibilities

The worker should:

1. claim a tenant-scoped analysis request;
2. resolve the tenant's Neo4j deployment and verify that its projected watermark has reached the requested authoritative change watermark;
3. create or refresh the versioned GDS in-memory projection for the selected analysis policy;
4. invoke deterministic GDS metric modules and capture their job/resource metadata;
5. optionally invoke GDS structural embedding modules;
6. reconcile semantic embedding jobs through configured adapters;
7. write immutable run results and atomically activate a complete snapshot;
8. emit freshness, performance, coverage, and failure telemetry.

The API must only read completed, active snapshots. It must not compute graph-wide algorithms synchronously. Each run records the Neo4j projection watermark, GDS graph name/configuration, algorithm versions, and PostgreSQL fact input fingerprint.

### 5.2 Scheduling

Do not let the new worker compete for rows in `projection_outbox`. The projection worker owns those leases and marks its rows processed.

The Neo4j projector consumes graph-affecting outbox rows, applies idempotent node/relationship upserts or closures, advances the tenant's projection watermark, and then upserts a coalescing request keyed by tenant and analysis policy:

```text
graph_analysis_request(
  tenant_id,
  policy_key,
  requested_change_watermark,
  reason,
  available_at
)
```

Frequent changes should collapse into one pending request. If a newer watermark arrives during a run, allow the current run to finish and enqueue one successor. Also run a periodic reconciliation so missed notifications cannot leave intelligence permanently stale.

The projector and analysis worker use separate queues and credentials. Projection lag must not cause repeated analysis failures: a request remains `WAITING_FOR_PROJECTION` until its tenant watermark is available. A periodic full relational-to-Neo4j checksum/reconciliation detects missed or divergent projection events.

Embedding work is entity/content-scoped and should have a separate queue:

```text
embedding_job(
  tenant_id,
  embedding_space_id,
  subject_kind,
  subject_id,
  input_hash,
  status,
  lease/attempt/retry fields
)
```

This separation allows graph analysis to succeed while an external embedding provider is unavailable.

### 5.3 Fair scheduling and resource isolation

Whole-tenant graph jobs must not create head-of-line blocking for smaller tenants. Apply these controls from Phase 1:

- at most one active whole-graph run per tenant and policy;
- fair tenant scheduling rather than a queue ordered only by creation time;
- separate lightweight and heavyweight algorithm stages so degree/reach summaries are not queued behind betweenness;
- configured projection, wall-clock, GDS concurrency, and memory budgets per stage;
- lease heartbeats plus Neo4j/GDS job identifiers, cancellation, and query timeouts;
- chunked/batched PostgreSQL-to-Neo4j projection and bounded result transfer;
- graph-size gates that select exact, approximate, sampled, or skipped implementations;
- per-tenant concurrency and resource classes that can be governed without code changes.

Do not naively split PageRank, communities, or articulation calculations into disconnected chunks; that changes their mathematical meaning. Chunk projection transport, not the logical tenant graph. Use GDS concurrency and approximate modes deliberately; approximate betweenness must disclose its sampling parameters.

A resource-constrained run may finish as `SUCCEEDED_WITH_LIMITATIONS` and atomically activate the metrics that were computed completely, such as degree and bounded reach. Omitted heavy metrics must be absent and accompanied by a `RESOURCE_EXCEEDED` limitation. Never label a sampled or truncated value as an exact complete metric.

### 5.4 Computation engine

Neo4j Graph Data Science is the selected production algorithm engine:

- use named, versioned GDS graph projections derived from `graph_analysis_policy`;
- prefer GDS estimate procedures where available before running memory-intensive algorithms;
- record algorithm mode, concurrency, sampling, seed, and library/server version;
- use mutate/write modes only in disposable GDS/Neo4j derived state; authoritative metric snapshots are written to PostgreSQL;
- drop or replace stale GDS projections after the run/retention window;
- retain NetworkX only as a small-fixture correctness oracle and emergency development fallback, not the production scale path.

Not every required StackGraph metric should be assumed to exist as a native procedure in every selected GDS version. Phase 0 must produce a capability matrix. Use native, version-pinned GDS procedures where they satisfy the metric contract; implement any missing metric, such as a required articulation/bridge variant, behind the same bounded StackGraph adapter or defer it explicitly. Do not silently substitute a mathematically different algorithm.

The StackGraph algorithm adapter still returns typed metric rows so Neo4j/GDS procedures, result shapes, or future engine changes do not alter the PostgreSQL schema or public API contract.

## 6. Neo4j deployment and PostgreSQL/pgvector persistence

### 6.1 Per-tenant Neo4j deployment model

Default to one Neo4j database or managed instance per StackGraph tenant. PostgreSQL stores the deployment registry and credential reference; application code never derives an endpoint from `tenant_id`.

```text
tenant_graph_deployment
  tenant_id, backend_kind, endpoint, database_name, credential_secret_id,
  deployment_state, schema_version, desired_change_watermark,
  projected_change_watermark, last_reconciled_at, last_error
```

Required lifecycle operations are provision, test connection, initialize constraints/indexes, full rebuild, incremental project, reconcile, rotate credentials, suspend, resume, and destroy. Destruction of a Neo4j deployment never deletes PostgreSQL authoritative data.

Within a tenant graph:

- every node has stable `entity_id`, `tenant_id`, namespace, type, and canonical key properties;
- every relationship has stable `fact_id`, `tenant_id`, predicate, confidence, assertion class, source revision, and evidence references;
- PostgreSQL UUIDs, not Neo4j internal IDs, are used for idempotency and API linkage;
- global catalog entities used by the tenant are copied into that tenant's disposable projection with explicit `scope='GLOBAL'` metadata;
- organizations are ordinary governed graph entities, not Neo4j databases, unless they are separate StackGraph security tenants.

Per-tenant deployment substantially reduces cross-customer graph leakage and whale interference at the database layer, but the shared StackGraph projection/analysis control plane must still enforce fair scheduling and credential isolation.

The selected production profile is self-managed Neo4j Enterprise plus GDS Enterprise per security tenant; development uses Community/GDS with one database. The design does not depend on multiple databases during steady-state serving, while Enterprise multi-database capability provides the blue/green rebuild switch. Network, TLS, version compatibility, memory estimates, capacity classes, backup/rebuild behavior, and the unit-cost formula are documented in [graph-intelligence-deployment-profile.md](architecture/graph-intelligence-deployment-profile.md). Actual license terms and unit prices require deployment-owner and procurement approval. See the official [Neo4j database administration](https://neo4j.com/docs/operations-manual/current/database-administration/), [GDS installation](https://neo4j.com/docs/graph-data-science/current/installation/), and [GDS algorithm catalog](https://neo4j.com/docs/graph-data-science/current/algorithms/) documentation.

The implemented credential contract permits `NEO4J_PASSWORD` tenant secrets and explicit `env://` external references. Deployment rows store references only; passwords, client certificates, and tokens are not stored inline in `tenant_graph_deployment`.

### 6.2 Projection and rebuild contract

Adapt or replace the existing AGE projector with a Neo4j projector that preserves the current outbox semantics:

1. claim PostgreSQL `projection_outbox` rows using existing leases;
2. group by tenant and resolve the tenant graph deployment;
3. idempotently merge nodes by `entity_id` and relationships by governed `logical_key`, retaining `fact_id` as evidence identity;
4. apply closures/deletes without inventing facts;
5. commit the Neo4j transaction;
6. advance `projected_change_watermark` in PostgreSQL and mark outbox rows processed;
7. coalesce the corresponding graph-analysis request.

If Neo4j is unavailable, leave rows retryable with backoff; ingestion remains successful because PostgreSQL committed first. Terminal projection failures enter the existing dead-letter/replay path.

Full rebuild must stream a repeatable PostgreSQL snapshot into an empty versioned Neo4j database/projection, validate counts and checksums, catch up outbox events created after the snapshot watermark, then atomically switch the tenant deployment pointer. This blue/green rebuild is also the upgrade and disaster-recovery path.

Phase 0 must benchmark projection throughput, catch-up time, result transfer, full rebuild duration, and PostgreSQL/Neo4j checksum reconciliation independently from GDS algorithm time.

### 6.3 Proposed tables

Use names and exact columns as a migration-design starting point, not as a frozen schema:

```text
tenant_graph_deployment
  tenant_id, backend_kind, endpoint, database_name, credential_secret_id,
  deployment_state, schema_version, desired_change_watermark,
  projected_change_watermark, last_reconciled_at, last_error

graph_analysis_policy
  id, tenant_id/null-global, policy_key, version, configuration, content_hash, status

graph_analysis_run
  id, tenant_id, policy_id, change_watermark, graph_source,
  neo4j_projection_watermark, gds_graph_name, input_fingerprint, algorithm_versions,
  status, node_count, edge_count, coverage, resource_usage, limitations,
  started_at, completed_at, error_detail

graph_entity_metric
  run_id, tenant_id, entity_id, metric_key, numeric_value,
  percentile, rank, components, limitations

graph_edge_metric
  run_id, tenant_id, fact_assertion_id/source_id/target_id,
  metric_key, numeric_value, components

graph_community_membership
  run_id, tenant_id, entity_id, community_key, membership_score

graph_similarity_candidate
  id, tenant_id, run_id, left_entity_id, right_entity_id,
  candidate_kind, score, score_components, explanation,
  supporting_fact_ids, input_fingerprint, review_state, stale_at

graph_similarity_feedback
  id, tenant_id, candidate_id, decision, feedback_type, rationale,
  reviewer_actor_key, score_version, created_at

embedding_space
  id, tenant_id/null-global, space_key, kind, provider, model_or_algorithm,
  dimensions, distance_metric, normalization, template_version,
  configuration_fingerprint, lifecycle_state, target_coverage,
  covered_subjects, eligible_subjects, activated_at, retired_at

active_embedding_space
  tenant_id/null-global, kind, embedding_space_id, prior_embedding_space_id,
  activated_by, activated_at

embedding_document
  id, tenant_id, subject_kind, subject_id, template_version,
  content, content_hash, source_fact_ids, provenance, sensitivity

entity_embedding
  id, tenant_id, embedding_space_id, subject_kind, subject_id,
  document_id/null, input_hash, embedding vector, created_at, stale_at
```

Key constraints:

- one active graph deployment per tenant, with credentials stored through an extended `tenant_secret` graph-backend kind or a tenant-scoped external secret-manager reference rather than inline;
- projected watermarks never advance before the matching Neo4j transaction commits;
- one active result per `(tenant, policy, metric key, entity)` through an active-run pointer or view;
- immutable completed runs;
- only `SUCCEEDED` or `SUCCEEDED_WITH_LIMITATIONS` runs can become active, and each metric records its own completeness;
- unique embedding per `(space, subject, input_hash)`;
- `vector_dims(embedding)` must equal the embedding-space dimensions;
- no raw secrets, inaccessible source code, or unredacted sensitive fields in `embedding_document`;
- RLS on every tenant table;
- delete or tombstone semantics that prevent stale embeddings from being returned;
- append-only similarity feedback with controlled rejection reasons such as `COMMON_FOUNDATION_ONLY`, `BUSINESS_DOMAIN_MISMATCH`, `FUNCTIONAL_DIFFERENCE`, `OWNERSHIP_BOUNDARY`, `DEPLOYMENT_CONTEXT`, and `DATA_QUALITY`.

pgvector indexes require a known dimension. If multiple model dimensions share a generic `vector` column, create a partial expression index for each active production space with an explicit cast such as `embedding::vector(N)`, or provision dimension-specific partitions. Do not mix models in one ANN index.

### 6.4 Embedding storage and migration

Keep semantic and persisted structural embeddings in PostgreSQL/pgvector for the first production release. This preserves RLS, model-space lifecycle, exact-search evaluation, review joins, and deletion semantics in the authoritative control plane. Neo4j vector indexes may be benchmarked later for graph-plus-vector retrieval, but do not duplicate every embedding into Neo4j without a measured serving requirement.

GDS may calculate structural node embeddings inside the disposable tenant graph. Export the selected vectors and their algorithm/input fingerprints into PostgreSQL `entity_embedding` before activating a StackGraph embedding space.

Embedding model changes must use shadow backfill rather than in-place mutation:

1. create a new `SHADOW` embedding space with its own model, dimensions, template, and configuration fingerprint;
2. backfill eligible subjects asynchronously while the current `ACTIVE` space continues serving reads;
3. expose coverage, failure, cost, and relevance/parity metrics for the shadow space;
4. require the configured coverage threshold plus evaluation gates before activation;
5. atomically swap `active_embedding_space` to the new space;
6. retain the prior space as `RETIRING` for a rollback window, then mark it `RETIRED` and remove it according to retention policy.

Query vectors and entity vectors must always come from the same active space. API requests never wait for a model-wide backfill and never combine results from active and shadow spaces. Rollback is a pointer swap, not another re-embedding job.

### 6.5 Index strategy

1. Start with exact cosine search, a B-tree on `(tenant_id, embedding_space_id)`, and a small `LIMIT`.
2. Capture `EXPLAIN (ANALYZE, BUFFERS)` and p50/p95 latency at realistic tenant sizes.
3. Introduce HNSW only when the exact-search SLO is missed. HNSW generally offers a better speed/recall tradeoff than IVFFlat but uses more memory and builds more slowly.
4. Test ANN recall against exact search on every representative corpus and tenant size.
5. If tenant filtering reduces recall, use iterative scans and/or tenant partitioning rather than increasing parameters blindly.
6. Build production indexes concurrently and include index size, build time, vacuum, and reindex behavior in capacity planning.

## 7. Feature plan

### 7.1 Release A: structural foundation

Deliver per-entity metrics for:

- inbound and outbound degree;
- upstream impact count and downstream dependency count;
- weighted transitive business impact;
- maximum and percentile dependency depth;
- PageRank or eigenvector centrality;
- approximate betweenness for graphs above a configured size;
- articulation-point membership and bridge edges;
- cross-domain edge count and ratio;
- component/team count where ownership data exists.

Do not collapse them into a single opaque score. The first UI should show the component metrics, coverage, and why the item ranked.

Composite scores may be added after normalization. Avoid raw multiplication, which can make one missing/zero input erase every other signal. Use capped, percentile-normalized components plus explicit missing-data policy. Example:

```text
systemic_risk =
  0.30 * business_criticality_percentile +
  0.25 * upstream_impact_percentile +
  0.20 * betweenness_percentile +
  0.15 * spof_percentile +
  0.10 * incident_or_vulnerability_overlay_percentile
```

The overlay is omitted and weights are renormalized when its governed inputs are unavailable. The response must say so.

### 7.2 Release B: similarity without model dependency

Create explainable application similarity candidates using deterministic features first:

- weighted Jaccard overlap of direct dependencies;
- overlap of transitive dependency neighborhoods;
- shared governed capabilities;
- runtime/framework/database overlap;
- business-domain alignment;
- ownership and deployment differences as penalties or warnings.

Weight dependency overlap by inverse estate frequency so ubiquitous foundations such as React, Node.js, common logging libraries, or shared cloud primitives contribute less than distinctive dependencies. This baseline is cheap, stable, and easy to validate. It also provides labels and hard negatives for evaluating embeddings later.

Reviewer decisions are an explicit learning loop, not merely workflow state. Store the controlled feedback type, rationale, candidate score/version, and actor in append-only feedback. Use aggregated feedback to evaluate proposed score-weight changes offline. Promote a new version only through the governed calibration process; do not silently learn online from individual decisions or leak one tenant's preferences into another tenant's scoring policy.

### 7.3 Release C: semantic entity embeddings

Build a canonical document renderer per entity type. An application document might contain only governed, accessible fields:

```text
name
curated purpose/description
business capabilities and processes
repository purposes
services/APIs
major technologies and data stores
owners and lifecycle state, when allowed
```

Immediate features:

- semantic application and technology search;
- "applications like this" candidate retrieval;
- better retrieval for Ask before deterministic SQL/graph reasoning;
- capability/entity matching suggestions;
- near-duplicate or missing-description review queues.

The content renderer and its source fields are part of the model contract. A field change changes `template_version` or the input hash and triggers re-embedding.

Provider rules:

- configure embedding provider/model per tenant where required;
- honor tenant AI service controls, data residency, and provider policy;
- record model, dimensions, token/cost usage, latency, retry class, and input hash;
- cache by content hash;
- allow a local embedding adapter for tenants that cannot send metadata externally;
- never fall back to a different embedding model within the same space;
- treat `429` and other provider quota responses as retryable, honor `Retry-After`, and use exponential backoff with jitter;
- apply per-provider and per-tenant concurrency/rate budgets plus a circuit breaker so one throttled provider cannot fail or starve an entire tenant graph run;
- dead-letter only after the configured retry horizon, preserving replay metadata and the input hash.

### 7.4 Release D: structural graph embeddings and hybrid ranking

Add Node2Vec or another unsupervised structural embedding only after the deterministic baseline and evaluation corpus exist.

Structural embeddings can retrieve applications with similar topology even when their technology names differ. Evaluate them against:

- known duplicate platforms;
- architect-reviewed similar/dissimilar application pairs;
- deterministic neighborhood similarity;
- random and same-domain hard negatives;
- stability across small graph revisions.

Hybrid application similarity should expose its components:

```text
candidate_score =
  semantic_similarity +
  structural_embedding_similarity +
  dependency_jaccard +
  capability_overlap -
  governed_difference_penalties
```

Weights must be versioned and calibrated from reviewer outcomes. The API should return both the composite and the contributing evidence, not only a cosine score.

### 7.5 Release E: communities, anomalies, and motifs

Add after the graph contract and basic metrics are trustworthy:

- Leiden/Louvain community membership and mismatch with governed domains;
- unusual degree/depth/team-crossing outliers relative to comparable cohorts;
- circular dependency and shared-database motifs;
- direct database access bypassing governed APIs;
- repeated legacy middleware chains;
- cross-domain bridge and distributed-monolith candidates.

Anomaly comparisons require an explicit cohort such as entity type, business domain, size, lifecycle stage, and observation coverage. "Unusual" must never mean merely "different from the whole mixed estate."

### 7.6 Application descriptions

Treat two related features separately:

1. **Embed existing descriptions** to enable semantic search and similarity. This is low risk and belongs in Release C.
2. **Generate missing or improved descriptions** from cited facts. This is an AI inference feature, not an embedding feature.

Generated descriptions should be persisted as proposals with:

- source fact IDs and source revisions;
- prompt/model/configuration fingerprints;
- confidence and limitations;
- review state and reviewer audit;
- a clear distinction from curated text.

Persist claim- or sentence-level provenance, not only one citation list for the entire paragraph. The UI should let a user select a generated sentence and see the exact facts, APIs, repositories, capabilities, and source revisions that support it.

Generated text inherits the most restrictive sensitivity and audience policy of its inputs. Re-check authorization when reading the proposal and its citations; generation must not turn private repository metadata into broadly visible application text. Embedding documents and vectors are governed with the same sensitivity classification as their source content.

Never overwrite a curated application description automatically. Approved text can be promoted through the normal governed entity-update path. Unapproved text can be displayed as an "AI-proposed summary" and used for search only if tenant policy permits.

## 8. UI impact and navigation

Do not add a new top-level page for the first releases. The existing navigation already represents the user jobs this intelligence supports, and another primary destination would fragment the experience before graph intelligence has enough depth to sustain its own workspace.

Place graph and embedding features in the current surfaces:

| Existing surface | Graph-intelligence impact |
|---|---|
| **Insights** | Primary portfolio entry point for hidden critical infrastructure, largest blast radius, structural SPOFs, coupling, similarity, and consolidation reports. Add an `Architecture risk` report group or place the first reports under the existing Enterprise risk category. |
| **Estate** | Add ranked lenses and sort options for systemic risk, blast radius, dependency depth, hidden criticality, and similarity coverage. Preserve the ranked-table default rather than replacing it with a graph canvas. |
| **Application detail** | Add a compact graph-intelligence summary to Overview: criticality, upstream impact, dependency depth, community, SPOF status, and similar applications. Open metric explanations, paths, and limitations in a drawer. Keep dependency hierarchy in the existing Technology tab. |
| **Technology detail** | Extend Technology findings and the existing `Explore neighborhood` action with centrality, affected applications/capabilities, bridge status, and reconstructable impact paths. |
| **Architecture** | Add community/domain mismatch, coupling, and conformance as canvas emphasis or comparison modes. Do not create a second architecture canvas. |
| **Insights Ask** | Use semantic retrieval to resolve entities and select candidate reports, then answer structural questions with deterministic Neo4j/SQL results. Show citations, metric components, and paths in the existing answer presentation. |
| **Reviews** | Route application-similarity, consolidation, community-mismatch, and generated-description proposals into the existing governed review queue. |
| **Estate Health** | Show graph-analysis freshness, authoritative and Neo4j projection watermarks, projection/reconciliation lag, queue lag, failed runs, embedding coverage, and provider health. |
| **Admin** | Configure graph-analysis policies, service state, embedding provider/model, sensitivity policy, and permitted description generation. |

Contextual delivery is more important than making users visit an intelligence destination. When StackGraph adds pull-request, commit/change, or deployment-review surfaces, place a precomputed impact summary directly in those workflows: likely blast radius, critical applications/capabilities, bridge/SPOF warnings, freshness, and a link to the evidence-backed path. These future views require reliable change-to-entity mapping and are not a Phase 1 dependency. Architecture review surfaces can receive SPOF and domain-mismatch flags as soon as the first metric snapshots exist.

Interactive UI reads must remain synchronous and fast by reading active snapshots. A pull-request, deployment, application, or Architecture screen must never wait for a whole-graph analysis run.

The primary investigation flow should be:

```text
Insight report or Estate lens
          -> ranked entities/candidates
          -> metric and path explanation
          -> bounded graph neighborhood or entity detail
          -> governed review/action when applicable
```

Continue the existing product rule against a full-estate graph canvas. Large graphs are useful as a computation model but usually poor as a default navigation or prioritization interface. Keep graph visualization bounded around a selected entity, risk, path, or community.

### 8.1 Application-detail presentation

Do not add a fifth application tab for the first metric release. Add a concise `Graph intelligence` section to Overview with:

- one primary status such as `Structurally critical`, `Typical`, or `Waiting for data`;
- four to six component metrics with estate percentile and freshness;
- the top two reasons for the classification;
- links to `View blast radius`, `Explore dependencies`, and `See similar applications`;
- a visible coverage/limitations state.

The detailed blast-radius result should open as a drawer or focused drill-down containing impacted applications/capabilities, path length, confidence, and supporting facts. Similar applications should show shared characteristics and important differences; never present only a similarity percentage.

### 8.2 When a dedicated page becomes justified

A dedicated workspace is warranted only after the product supports a sustained estate-wide investigation job with several of the following together:

- saved graph-intelligence views and filters;
- community exploration and domain mismatch;
- motif/anomaly investigation;
- side-by-side entity or community comparison;
- time/revision comparison;
- triage ownership and review state;
- export or portfolio planning actions.

At that point, prefer an **Insights -> Graph intelligence** subview or nested route over another primary left-rail item. Promote it to primary navigation only if usage shows that architects repeatedly enter the product specifically to perform graph investigation rather than starting from Insights, Estate, or an entity.

## 9. API and experience changes

Prefer small read-model endpoints over exposing raw vector operations:

```text
GET /graph-intelligence/status
GET /entities/{id}/graph-metrics
GET /entities/{id}/blast-radius
GET /entities/{id}/similar
GET /graph-intelligence/risks
GET /graph-intelligence/communities
POST /search/semantic
POST /similarity-candidates/{id}/review
```

Every graph-intelligence response should include:

- `analysis_run_id` and `as_of`;
- authoritative change/source freshness and Neo4j projection freshness;
- policy/algorithm version;
- score components;
- coverage/limitations;
- supporting fact IDs and, for path claims, reconstructable paths;
- review state for inferred candidates.

Integrate with existing Ask routing as a three-stage process:

1. semantic retrieval identifies likely entities or candidate reports;
2. deterministic Neo4j queries answer structural questions, with SQL fallback during projection lag or outage;
3. an LLM may summarize only the returned facts, paths, metrics, and limitations.

The natural-language layer should not calculate reachability or invent causal explanations from embeddings.

## 10. Delivery phases and exit criteria

### Phase 0 — contracts, tenant projection, and GDS spike — implemented

Deliver:

- versioned analysis-graph policy and direction semantics;
- per-tenant Neo4j deployment registry, credential model, lifecycle, and organization-boundary rules;
- Neo4j node/relationship projection schema, uniqueness constraints, and stable PostgreSQL UUID mapping;
- incremental outbox projector, projection watermark, retry/dead-letter handling, and reconciliation;
- blue/green full rebuild and catch-up path from a repeatable PostgreSQL snapshot;
- relational reference reader plus Neo4j reader with parity fixtures;
- selected self-managed Neo4j/GDS and/or Aura deployment target with documented licensing and capacity assumptions;
- migration/schema proposal and RLS review;
- representative graph-size benchmark dataset;
- exact pgvector search benchmark independent of Neo4j;
- end-to-end projection/GDS benchmark separating PostgreSQL extraction, transfer, Neo4j writes, GDS projection, algorithm execution, and result transfer.

Exit criteria:

- fresh install and upgrade/restore tests pass;
- tenant A's control-plane credentials cannot connect to tenant B's Neo4j deployment, and API requests cannot select another deployment;
- multiple Organization nodes inside one tenant participate in cross-organization paths without weakening tenant isolation;
- PostgreSQL migrations and application readiness no longer require AGE;
- relational and Neo4j readers produce identical normalized fixtures at the same watermark;
- a blue/green rebuild catches up and switches without losing or duplicating projected facts;
- analysis inputs are reproducible from an authoritative change watermark;
- projection, GDS projection, algorithm, and result-transfer p50/p95 are measured separately;
- GDS/Aura licensing, per-tenant capacity, backup/rebuild, and estimated unit cost are approved;
- memory and time budgets are recorded for representative small, medium, and large pilot graphs.

### Phase 1 — worker substrate and deterministic metrics — implemented

Deliver:

- graph analysis queue, leases, retries, dead letters, heartbeat, and coalescing;
- fair tenant scheduling, staged algorithms, hard resource budgets, and `SUCCEEDED_WITH_LIMITATIONS` semantics;
- Neo4j projection status/reconciliation and GDS job cancellation/timeout controls;
- immutable analysis runs and active-snapshot views;
- degree, reachability, depth, PageRank, approximate betweenness, and SPOF metrics;
- status and per-entity metrics APIs;
- integration into the existing systemic-risk and blast-radius reports.

Exit criteria:

- golden graph fixtures prove direction and exact expected metrics;
- an incomplete/failed run never replaces the active snapshot;
- an authoritative graph change projects to Neo4j, makes results stale, and produces exactly one successor run after the watermark advances;
- a whale tenant cannot prevent a queued small-tenant job from starting within the declared scheduling SLO;
- a resource-exceeded run activates only complete lightweight metrics and clearly omits/limits heavy metrics;
- API latency does not depend on running graph algorithms synchronously.

### Phase 2 — explainable application similarity — implemented

Deliver:

- deterministic application-pair feature builder;
- similarity-candidate persistence and review workflow;
- "similar applications" and consolidation-candidate UI/API;
- coverage gate for repository-to-application and business-capability mappings.

Exit criteria:

- reviewers can see both overlaps and important differences;
- negative tests prove that applications sharing large ubiquitous foundations such as React, Node.js, or AWS primitives are not automatically high-similarity/consolidation candidates;
- controlled rejection reasons and rationales are retained with the candidate score/version;
- reviewer outcomes are retained as an evaluation corpus.

### Phase 3 — semantic embeddings and search — implemented with governed activation

Deliver:

- embedding spaces, canonical document renderers, jobs, adapters, caching, and pgvector queries;
- shadow backfill, atomic active-space swap, and rollback lifecycle;
- application/technology semantic search;
- semantic candidate retrieval feeding the Phase 2 explainer;
- provider governance, cost, failure, and data-sensitivity controls.

Exit criteria:

- model changes cannot mix vectors in one space;
- a shadow space can reach its coverage/evaluation gate and replace the active space without blocking reads;
- source changes deterministically stale/rebuild the correct embeddings;
- exact-search relevance meets a reviewed offline threshold;
- simulated `429`/`Retry-After`, provider outage, and quota exhaustion back off without failing the tenant's graph-analysis run;
- cross-tenant leakage, deleted-entity retrieval, and provider-failure tests pass.

### Phase 4 — structural embeddings and advanced graph intelligence — implemented in SHADOW/evaluation mode

Deliver:

- structural embeddings and hybrid ranking;
- communities, domain mismatch, motifs, and cohort-based anomalies;
- calibrated composite risk/modernization scores;
- natural-language summaries grounded in stored metrics and paths.

Exit criteria:

- embeddings materially outperform the deterministic retrieval baseline on labeled data;
- ANN, if enabled, meets a declared recall@k threshold against exact search;
- small graph changes do not create unacceptable ranking instability;
- every surfaced recommendation remains evidence-backed and reviewable.

## 11. Test and evaluation plan

### 11.1 Graph correctness

Maintain tiny directed golden graphs for:

- chain, star, diamond, cycle, disconnected components, and multi-edge cases;
- impact versus dependency direction;
- articulation points and bridges;
- confirmed/rejected/possible identity handling;
- confidence and assertion-class filters;
- tenant/global catalog visibility;
- stale/unavailable Neo4j projection and incomplete snapshot handling;
- relational/Neo4j projection parity, idempotent replay, closure/delete, and blue/green rebuild behavior;
- multiple organizations within one tenant and hard separation between tenant deployments;
- fair scheduling and resource-exceeded activation semantics.

Cross-check algorithm outputs with independently calculated expected values. Add property tests for monotonic reachability and path validity.

### 11.2 Embedding relevance and safety

Measure:

- precision@k, recall@k, nDCG, and reviewer acceptance;
- deterministic baseline versus semantic, structural, and hybrid ranking;
- exact versus ANN recall;
- common-technology false positives;
- controlled reviewer-feedback coverage and score-version traceability;
- model/template drift;
- shadow-space backfill, activation, rollback, and partial-failure behavior;
- multilingual or sparse-description behavior if present;
- tenant isolation, deletion, opt-out, and sensitive-field exclusion.

Cosine thresholds are not universal constants. Calibrate them per embedding space and feature using reviewed data.

### 11.3 Performance and operations

Benchmark by tenant node/edge/vector counts and record:

- PostgreSQL extraction, network transfer, Neo4j write throughput, projected graph size, and reconciliation time;
- GDS graph-projection time/memory, algorithm time/memory, concurrency, and result-transfer time as separate components;
- per-algorithm time and degradation behavior;
- analysis queue lag, per-tenant wait time, starvation SLO, and coalescing effectiveness;
- vector generation throughput, provider latency, tokens/cost, and cache hit rate;
- exact/ANN query p50/p95/p99;
- HNSW index size, build/rebuild time, vacuum behavior, and recall;
- concurrent Neo4j traversal/GDS impact on the tenant graph plus projection/API/ingestion impact on PostgreSQL.

Configure hard node/edge/time/memory limits. On limit, fail the run or activate it as `SUCCEEDED_WITH_LIMITATIONS` only when individual lightweight metrics are complete. Do not silently publish skipped, sampled, or truncated metrics as exact complete results.

## 12. Observability and governance

Add the service key `graph-intelligence` to tenant service controls rather than reusing `intelligence`. This lets an operator pause expensive graph work without disabling repository modernization or AI enrichment.

Required telemetry:

- latest requested/completed/active authoritative and Neo4j projection watermarks per tenant, reconciliation status, and deployment health;
- analysis and embedding queue depth/oldest age;
- per-tenant wait time, active resource class, timeout/resource-exceeded count, and starvation-SLO breaches;
- run duration, node/edge count, memory high-water mark, and per-module duration;
- failed/retried/dead-letter counts;
- active metric and embedding age;
- active/shadow/retiring embedding-space coverage and migration failures;
- vector provider requests, tokens/cost, cache hits, rate limits, and failures;
- exact/ANN latency and sampled ANN recall;
- database CPU, memory, locks, I/O, and vector-index size.
- per-tenant Neo4j storage/memory, GDS memory estimates/usage, query latency, projection throughput, connection pool, and unit cost.

Audited configuration includes graph policy, algorithm versions, score weights, embedding provider/model, document template, sensitivity policy, and reviewer actions.

## 13. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Graph metrics appear authoritative despite missing application mappings | coverage gates, readiness statuses, and explicit denominators |
| Expensive graph-wide analysis harms API or tenant graph latency | separate GDS orchestration, coalesced jobs, estimates, timeouts, and per-tenant resource limits |
| PostgreSQL and Neo4j diverge | PostgreSQL authority, stable IDs, watermarks, checksums, reconciliation, idempotent replay, and full rebuild |
| Neo4j is unavailable | ingestion continues in PostgreSQL, projection retries, SQL bounded-read fallback, and last complete metric snapshot remains active |
| Per-tenant Neo4j deployments create cost/operations sprawl | automated lifecycle, capacity classes, idle/suspend policy where supported, and unit-cost telemetry |
| Neo4j/GDS commercial tier or Aura constraints surprise deployment | approve licensing, security, backup, network, and GDS capability matrix in Phase 0 |
| Organizations are incorrectly modeled as tenants | tenant is the hard security/deployment boundary; organizations are graph entities unless isolation requirements differ |
| Neo4j credentials cross tenant boundaries | credential references scoped by tenant, endpoint allowlists, connection tests, and deployment-selection authorization |
| A whale tenant starves smaller tenants | fair scheduling, per-tenant concurrency, staged algorithms, resource classes, and starvation SLO |
| ANN tenant filter reduces recall or creates cross-tenant performance coupling | exact search first; benchmark; partition or separate indexes before ANN |
| Different models/dimensions are compared | immutable embedding-space identity and dimension checks |
| Embedding-model deprecation forces a disruptive backfill | shadow space, asynchronous coverage gate, atomic activation, and rollback window |
| Generic infrastructure makes unrelated apps look similar | down-weight ubiquitous nodes, IDF-style features, and hard-negative evaluation |
| Topology changes make graph embeddings unstable | deterministic baselines, fixed seeds where possible, revision stability tests |
| Similarity is mistaken for consolidation proof | candidate/review workflow with differences and supporting facts |
| Similarity rejections do not improve evaluation | controlled append-only feedback and governed offline calibration |
| Generated descriptions overwrite or leak governed metadata | proposals only; sentence-level provenance, inherited sensitivity, authorization checks, and explicit review/promotion |
| Raw multiplication creates misleading zero or extreme scores | normalized components, caps, missing-data policy, versioned calibration |
| Graph/embedding results become stale | watermarks, content hashes, active-run swap, reconciliation loop, freshness in API |

## 14. Explicit non-goals for the first release

- real-time graph-wide recomputation after every fact;
- global full-estate graph rendering;
- embedding-based proof of dependency or impact;
- automatic application consolidation or retirement decisions;
- automatic overwrite of application descriptions;
- change/incident propagation claims before change and incident data are ingested;
- a new standalone vector database;
- storing semantic embeddings in Neo4j before graph-plus-vector serving demonstrates a measured benefit;
- ANN indexes before exact-search measurements justify them;
- replacing existing deterministic risk and governance reports.

## 15. Backlog outcome

Items 1–12 from the approved implementation backlog are complete: policies and direction contracts; deployment/credential control plane; incremental projection and reconciliation; blue/green orchestration; selected deployment profile and benchmark; RLS-protected run/metric schemas; the independently deployable worker; the versioned GDS capability adapter; contextual report/UI integration; deterministic similarity and review; semantic embedding lifecycle; and semantic search/candidate retrieval.

Item 13 is implemented in its required safe state. GDS structural embeddings are generated into SHADOW spaces and can contribute to hybrid ranking only after an evaluated space is active. Production promotion remains conditional on reviewed baseline improvement and revision stability, so the system cannot mistake implementation availability for evidence of product value.

The important sequencing decision is: **graph metrics -> explainable structural similarity -> semantic embeddings -> structural embeddings -> advanced anomaly/community features**. This realizes the proposal's business value early while preserving StackGraph's evidence-first and tenant-safe architecture.
