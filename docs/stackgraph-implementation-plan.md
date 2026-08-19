# StackGraph implementation plan

**Status:** proposed execution plan after review of the product specification, UI specification, Strata design language/tokens/style guide, relational and graph schemas, scanner/fact contracts, curated seed, AGE projection notes, and the local Ladder Graph implementation.

**Active V0 ingestion plan:** `stackgraph-dependency-ingestion-plan.md`  
**Deferred research:** `stackgraph-ingestion-sizing-and-pull-plan.md` sizes a possible future GH Archive program; it is not required for dependency discovery.

## 1. Executive decision

StackGraph should be built as four coordinated systems with separate failure and release boundaries:

1. **Acquisition** continuously captures source snapshots and raw observations from customer GitHub installations and selected public OSS sources.
2. **Normalization** resolves stable identities and emits evidence-backed facts through versioned contracts.
3. **Intelligence** derives current graph relationships, assessments, recommendations, and temporal changes from facts.
4. **Experience** serves evidence-first portfolio views, bounded graph neighborhoods, and deterministic estate queries.

The first production milestone is not a complete OSS graph. It is a running, replayable ingestion loop plus one end-to-end slice:

`repository -> package version -> OSS project -> external health signals -> evidence -> application/technology view`

The OSS ingester should start in the first implementation cycle, but only for packages and projects observed in customer repositories or the curated seed. It should not ingest the public GitHub firehose or fetch unrelated source code.

## 2. What is already strong

- The product thesis is differentiated and coherent: Git is a sensor, viability is broader than security, and capability/function precedes replacement choice.
- PostgreSQL as the system of record and Apache AGE as an asynchronous traversal projection is the right boundary.
- Scanner, evidence, assessment, recommendation, and execution responsibilities are explicitly separated.
- Declared, observed, inferred, curated, and externally measured assertions are meaningfully distinct.
- The UI v2 correctly avoids a full-estate graph canvas. The default is a ranked estate view; graph exploration is a bounded neighborhood.
- The Strata language reinforces provenance through typography and makes confidence inspectable without turning the interface into a color legend.
- The seed has useful job-first categories and capabilities and preserves its original raw rows.

These decisions should be treated as invariants, not reopened during initial implementation.

## 3. Contract and schema issues to resolve first

### P0: blocking correctness issues

1. **The normalized fact JSON Schema cannot reliably validate entity-valued objects.** `object` uses `oneOf`, but the scalar/value branch also permits any JSON object. An entity reference therefore matches both branches and fails `oneOf`. `object` is also not required, while the SQL fact table requires exactly one object representation.
2. **The UI, ontology, and graph vocabulary disagree.** The UI depends on `SAME_AS`, `PUBLISHED_BY`, `IMPLEMENTS`, `HOSTED_AT`, and `TREND`; these are absent from `graph-schema.json`. The ontology mentions `OnPrem`, technical `Capability`, `ArchitecturePattern`, storage, and queues that are also absent or only implicit.
3. **Idempotency is stated but not modeled.** Facts have no semantic identity or uniqueness constraint, scan targets have no source revision, and repeated ingestion can append duplicate facts/evidence.
4. **Snapshot removal is undefined.** `first_seen_at` and `last_seen_at` exist, but there is no complete-snapshot marker or rule for closing facts that disappear. A partial scan must never tombstone data.
5. **Graph edge requirements are not enforced in the relational model.** The graph contract requires confidence and assertion class, while `relationship` stores them only as optional JSON properties.
6. **Continuous ingestion state is absent.** There is no durable webhook inbox, provider cursor, scheduled target, lease/retry state, raw response store, dead-letter record, freshness policy, or projection outbox.
7. **The seed's provenance is incomplete in this repository.** The manifest points to `framework-landscape-2026.md`, but that source file is not checked in. Individual claims often retain a source line and prose statistic but not a durable source URL, measurement date, or external identity.

### P1: semantic issues

1. All 192 seed entries use `technology_or_group`; many rows combine independent products. Preserve each original group as curated provenance, but split it into atomic technology records before matching packages or repositories.
2. Canonical package identity needs an ecosystem-qualified key plus registry provenance. Use Package URL (purl) for public packages and versions; tenant-qualify custom/private packages by normalized registry origin until identity is proven. Use GitHub's immutable repository/node ID plus normalized host/owner/name aliases for repositories.
3. Decide whether a package is globally canonical or duplicated between enterprise and OSS namespaces. Recommended model: a globally canonical `Package`/`PackageVersion` identity, tenant-scoped usage facts, and explicit identity assertions only when a local alias cannot be deterministically resolved. Do not create two package nodes merely because observations came from different planes.
4. Facts, relationships, and assessments need bitemporal semantics: when the source said something was true and when StackGraph learned it.
5. Assessment records need a model/rule version, input fact set or query snapshot, supersession status, and an invariant requiring a score or categorical value.
6. Recommendation status and review actions need controlled vocabularies and actor/audit metadata, especially for uncertain bridge confirmation/rejection.
7. Multi-tenant isolation needs explicit RLS and global-public versus tenant-private ownership rules before customer data is loaded.

### P2: design-system cleanup

1. Token references under `confidence` are not expressed in the same token schema as the rest of the file and `text.primary` is mode-ambiguous. Normalize aliases before wiring Tokens Studio or code generation.
2. Ladder Graph uses Lucide; Strata specifies Tabler. Keep Strata's decision and swap only the icon adapter, or explicitly revise the design language. Do not ship two icon systems accidentally.
3. Define responsive behavior as desktop-first with a documented minimum supported viewport. The V0 product does not need a mobile graph canvas.

## 4. Target data architecture

### 4.1 Stable identities

| Entity | Canonical identity | Aliases retained |
|---|---|---|
| Public package | purl without version + public registry provenance | ecosystem-native name, renamed package, registry URL |
| Public package version | purl with normalized version + public registry provenance | source version string |
| Private/custom package | tenant + normalized registry origin + purl | scoped name and resolved artifact URL; bridge to public identity only through an explicit assertion |
| OSS repository | provider + immutable provider repository ID | current and historical full names/URLs |
| OSS project | StackGraph project ID | official site, repository set, registry projects |
| Release | repository/project + immutable release/tag identity | tag name |
| Vulnerability | OSV ID | CVE/GHSA aliases |
| License | SPDX expression/identifier where possible | source text/name |
| Technology | StackGraph stable slug | names, package/project identities, curated group membership |
| Customer repository | GitHub installation + immutable repository ID | full name, default branch |

Identity resolution must emit its own assertion with method, confidence, source, and review state. A UI `SAME_AS` bridge is a presentation of that assertion, not a hard-coded join.

### 4.2 Authoritative tables

Retain the current entity/fact/evidence/assessment/recommendation concepts, but add the following substrate:

- `connector_account`: GitHub App installation or external source account, encrypted credential reference, permissions, tenant/global scope.
- `package_registry` and `package_registry_scope`: normalized origin, public/private visibility, connector credential reference, and scope-to-registry mappings without secret material.
- `package_registry_identity` and `dependency_resolution`: registry-qualified package identity plus requested spec, resolved artifact/integrity, npmrc/lockfile/default resolution method, and pinning behavior for each dependency fact.
- `ingest_target`: provider target, priority tier, refresh policy, next due time, last success, desired source revision.
- `ingest_cursor`: provider-specific cursor/ETag/Last-Modified/page token and monotonic checkpoint.
- `webhook_delivery`: delivery ID, verified headers, event/action, body checksum, received/processed status. Unique by provider delivery ID.
- `ingest_run` and `ingest_item`: leased work, attempts, retry time, completeness, stats, error class, source revision.
- `raw_observation`: immutable provider response metadata, content hash, observed/effective time, schema version, and pointer to compressed raw body.
- `source_snapshot`: a complete or partial snapshot boundary for a target and revision.
- `entity_identity` and `entity_alias`: purl/provider/SPDX/OSV identities and resolution assertions.
- `fact_assertion`: immutable, semantically keyed fact with source/effective/system time and normalization version.
- `current_fact`/`relationship`: materialized current state derived from assertions, not the only historical record.
- `projection_outbox`: changed entity/edge IDs for idempotent AGE projection.
- `dead_letter`: terminally failed work with replay metadata.
- `freshness_state`: expected and actual freshness by source/target.

Large repository archives and raw API bodies should live in an object store keyed by content hash; PostgreSQL stores metadata and small payloads. Local development can use an S3-compatible container or filesystem adapter.

### 4.3 Fact contract v1

Replace the ambiguous `object` field with explicit alternatives:

```json
{
  "fact_contract_version": "1.0",
  "idempotency_key": "sha256:...",
  "subject": {"namespace": "ENTERPRISE", "type": "Repository", "key": "github:repo:123"},
  "predicate": "DEPENDS_ON",
  "object_entity": {"namespace": "TECHNOLOGY", "type": "PackageVersion", "key": "pkg:npm/axios@1.7.9"},
  "assertion_class": "DECLARED",
  "confidence": 1.0,
  "observed_at": "...",
  "effective_at": "...",
  "source_revision": "git-sha-or-provider-version",
  "extractor": {"key": "npm-lock", "version": "1.0.0"},
  "evidence": [{"source_artifact_key": "...", "type": "LOCKFILE", "locator": {"path": "package-lock.json"}}]
}
```

The schema must require exactly one of `object_entity` or `object_value`, disallow unknown top-level properties, require traceable evidence except for explicitly enumerated system facts, and validate source/target types against a versioned predicate registry.

Semantic idempotency key:

`scope + subject + predicate + object + assertion_class + source_artifact + source_revision + extractor_version`

### 4.4 Snapshot reconciliation

1. Acquire a target at a specific source revision.
2. Persist raw observations before normalization.
3. Normalize and validate a complete fact batch.
4. Upsert semantic assertions and evidence transactionally.
5. If and only if the snapshot is marked `COMPLETE`, close previously current assertions from the same target/extractor that were not observed in the new snapshot.
6. Write changed identities to the projection outbox in the same transaction.
7. Mark authoritative ingestion successful; AGE projection and assessments retry independently.

This makes retries safe and prevents a parser/network failure from erasing an estate.

## 5. Continuous GitHub and OSS ingestion

### 5.1 GH Archive is deferred for V0

GH Archive does not directly identify dependencies: it contains public activity events, not complete manifests, lockfiles, or resolved dependency graphs. Do not ingest it for the V0 dependency-discovery pipeline.

Reconsider it only when StackGraph is ready to build ecosystem adoption cohorts, historical project-health models, or migration-pattern mining. Those are separate V1/V2 workloads with their own sampling and storage decisions.

### 5.2 Two different GitHub modes

**Customer/installed repositories**

- Use a GitHub App with minimum read permissions.
- Receive installation, repository, push, release, and relevant metadata events.
- Verify webhook signatures, deduplicate by delivery ID, acknowledge quickly, then process asynchronously.
- Run periodic reconciliation because webhook delivery is a trigger, not the sole source of truth.
- On push, scan the new default-branch revision; ignore superseded queued revisions where safe.

GitHub recommends responding to webhooks within ten seconds, using the delivery ID for uniqueness, and redelivering missed deliveries. Its App permissions determine both API access and eligible webhook events: [webhook best practices](https://docs.github.com/en/webhooks/using-webhooks/best-practices-for-using-webhooks), [GitHub App permissions](https://docs.github.com/en/apps/creating-github-apps/registering-a-github-app/choosing-permissions-for-a-github-app).

**Arbitrary public OSS repositories**

- A GitHub App cannot receive push webhooks for repositories where it is not installed/administered.
- Maintain a selected target set and poll metadata, releases, tags/default-branch SHA, and relevant files with conditional requests and per-source budgets.
- Do not treat GitHub's public events endpoint as a reliable change stream; GitHub documents latency and a bounded recent window.
- Expand the target set from packages actually observed in customer estates, curated seeds, and explicitly selected reference/migration cohorts.
- Fetch source only when a source revision changed and a downstream extractor needs it. Avoid cloning all history.

GitHub installation request budgets scale with installation size, while unauthenticated public requests are far more constrained, so quota state and conditional fetching must be first-class: [REST API rate limits](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api), [public events limitations](https://docs.github.com/en/rest/activity/events).

### 5.3 OSS source roles

| Source | Use in StackGraph | Refresh trigger |
|---|---|---|
| Package registries | registry-qualified package/version/release metadata and ecosystem-native identity | new version, stale target, observed package at that registry |
| deps.dev v3 | resolved dependency graphs, package/project association, licenses/advisories and project metadata | new observed version, periodic refresh |
| OSV | version/commit vulnerability observations | new package version, advisory refresh |
| OpenSSF Scorecard | external supply-chain/security signals | weekly or source freshness policy |
| Public GitHub | repository state, releases, maintainers/contributors, targeted source evidence | changed SHA/release, stale target |
| Curated StackGraph seed | capability, category, lifecycle hypotheses, reference cohorts | versioned seed release |

Use stable deps.dev v3 for production contracts and isolate v3alpha batch/purl features behind an adapter. deps.dev permits caching and provides resolved graphs for npm, Cargo, Maven, and PyPI in its stable API: [deps.dev API](https://docs.deps.dev/api/v3/). OSV supports batched package-version/commit queries: [OSV API](https://google.github.io/osv.dev/api/). OpenSSF publishes pre-calculated Scorecard results, with documented omissions in weekly large-scale scans that must remain visible as source limitations: [OpenSSF Scorecard](https://github.com/ossf/scorecard/blob/main/README.md).

### 5.3.1 npm registry resolution

npm is a registry protocol/ecosystem, not a guarantee that a package came from the public npm registry. The npm scanner resolves the effective origin from the concrete lockfile plus applicable scope/default `.npmrc` settings and records the resolution method. A default-registry lockfile entry follows the currently configured registry; an explicitly custom registry remains pinned. `publishConfig.registry` is publishing policy and is not used as dependency-install resolution.

Public npm package metadata is global. Custom/private registry identities and observations are tenant-scoped and use `registry:<registry-key>:<purl>` until an evidence-backed identity assertion establishes equivalence. Registry adapters use connector-owned credential references, normalized-origin allowlists, redirect validation, conditional requests, and per-registry quota/freshness state. Tokens and credential-bearing URLs never enter raw observation metadata, facts, evidence, logs, or UI read models. The public CouchDB mirror is not a V0 ingestion target; enrichment remains limited to observed or curated packages.

### 5.4 Scheduler and priority policy

Use a PostgreSQL-backed queue initially with `FOR UPDATE SKIP LOCKED`, leases, exponential backoff with jitter, per-provider concurrency, and explicit retry classes. The scheduler creates work; workers never invent their own untracked loops.

Priority tiers:

- **Hot:** used by a customer, business-critical, newly changed, or backing an active recommendation.
- **Warm:** present in any customer estate or an approved curated/reference cohort.
- **Cold:** curated seed candidates not yet observed internally.
- **On demand:** dependency neighborhood, migration example, or reference implementation requested by a user/query.

Refresh intervals are source-specific configuration, not hard-coded product semantics. A changed release/branch SHA can pull work forward; unchanged conditional responses should update freshness without re-normalizing.

### 5.5 First continuously running slice

Start with npm and PyPI because they align with the V0 JavaScript/TypeScript and Python scanners.

1. Atomize and identity-map the relevant seed technologies.
2. Enqueue seed and observed purls at their resolved registries.
3. Fetch package/version/project/dependency information from stable deps.dev.
4. Query OSV in batches for observed versions.
5. Resolve the official project/repository for observed packages.
6. Conditionally refresh metadata and releases for those linked projects; do not fetch their source by default.
7. Store raw observations, normalize external facts, and project a bounded dependency/project neighborhood.
8. Display freshness, provenance, cohort, and source limitations in the Technology Explorer.

Do not calculate a global adoption trend from this customer-centered target set. Co-occurrence, adoption, and migration rates require an explicitly defined sampling cohort and denominator; label them as cohort observations until that exists.

## 6. Repository scanner plan

Build scanners as deterministic plugins over a common repository snapshot contract.

### Pass A: fast inventory

- Repository metadata, languages, ownership files, monorepo/build markers.
- Manifests and lockfiles.
- Dockerfiles, basic Kubernetes, basic Terraform, and CI/deployment descriptors.
- Direct/resolved dependencies, runtimes, frameworks, and declared deployment facts.

This pass is optimized to produce initial material findings across 100+ repositories quickly.

### Pass B: evidence refinement

- AST/import usage for JS/TS and Python.
- Selected function/capability usage for the first recommendation patterns.
- Entry points, framework config, SDK/API clients, test/build/UI systems.
- Declared-versus-observed package use and unused dependency candidates.

### Pass C: asynchronous depth

- Transitive neighborhoods not available from lockfiles/deps.dev.
- More precise capability inference.
- Internal reuse/semantic similarity candidates.
- Targeted repository history for migration patterns.

The 20-minute pilot objective is time to first useful evidence, not time to complete Pass C.

Each scanner output reports `COMPLETE`/`PARTIAL`, source revision, extractor versions, file/fact counts, skipped limits, and structured diagnostics. Large output is NDJSON or chunked batches, not one in-memory JSON array.

## 7. Ladder Graph reuse plan

Ladder Graph is Apache-2.0 and its graph implementation is a useful accelerator, but StackGraph should reuse a small visual kernel rather than fork the whole application.

### Reuse directly or with a thin adapter

- React Flow canvas setup: background, controls, minimap, selection, fit behavior, typed node/edge conversion.
- Deterministic Dagre left-to-right layout and its test patterns.
- Ontology canvas structure, which is closer to StackGraph's read-only labeled graph than the editable workflow canvas.
- PNG/SVG export sizing and viewport capture.
- Zustand linked-selection pattern for synchronizing graph, evidence, and inspector panes.
- Theme persistence pattern, renamed and mapped to Strata variables.
- Inspector/drawer interaction and keyboard/accessibility test approaches.

### Adapt for StackGraph

- Create a generic `packages/graph-ui` module with StackGraph node/edge types; do not import LGIR/YAML/compiler types.
- Default to read-only: no connect, delete, inline edit, or drag persistence. Confirm/reject bridge actions are explicit audited API mutations, not graph editing.
- Render only a server-bounded response: selected center, one-hop nodes, highlighted paths, aggregate cluster nodes, and truncation metadata. Hard cap rendered real nodes at approximately 50.
- Add domain badges, evidence counts, freshness, confidence, dashed uncertain bridges, selected-only pulse, and `prefers-reduced-motion` behavior.
- Use a client-only boundary when embedded in Next.js.
- Replace Ladder-specific colors, fonts, icons, copy, and CSS with generated Strata tokens.
- Preserve Apache attribution/NOTICE obligations for copied files.

### Do not reuse

- YAML canonical-source editing, compiler worker/WASM, LGIR types, macros, workflow groups, execution semantics, or MCP companion.
- IndexedDB/OPFS project persistence; StackGraph state is server-authoritative.
- The editable workflow palette/connect/delete behavior.
- Ladder's full application shell, catalog, onboarding, or Vite build as the StackGraph architecture.
- Full-estate layout. Ladder's canvas is designed for bounded authored graphs; StackGraph's own UI spec correctly requires a bounded exploration lens.

## 8. Product/API slices

Build read models, not raw graph endpoints, for the five V0 surfaces:

1. `GET /estate/summary` — counts, distributions, ranked applications/technologies, freshness and coverage.
2. `GET /applications/{id}` — business context, repositories, technology/deployment profile, assessments, recommendations, evidence summaries.
3. `GET /technologies/{id}` — internal usage plus OSS project/version/health/alternative/migration context.
4. `GET /modernization` — ranked opportunities with score components, confidence, effort, counter-signals, and evidence.
5. `POST /ask` — typed response `{text, citations, result_kind, rows?, graph_highlight?}`.
6. `GET /graph/neighborhood` — center, depth, filters, real-node limit, aggregate clusters, highlighted path, truncation reason.
7. `GET /facts/{id}/evidence` — source artifact, locator, source revision, parser version, assertion class, timestamps.
8. `POST /identity-assertions/{id}/review` — confirm/reject uncertain bridge with actor and rationale.

The natural-language layer selects deterministic SQL/AGE query tools and explains returned data. It never generates estate facts from model memory.

## 9. Parallel execution model

After a short shared contract gate, four lanes can progress independently.

| Lane | Starts with | Runs continuously | Integration gate |
|---|---|---|---|
| A — Data platform/OSS | ingestion substrate, raw observations, target scheduler, registry-qualified purl/repo identity, deps.dev/OSV adapters | public/private source refresh and replay | emits validated external facts for one registry-qualified purl/project slice |
| B — Enterprise discovery | repository snapshot contract, JS/TS/Python manifests, Docker/K8s/Terraform parsers | customer rescan/reconciliation | emits validated repository/package/deployment facts |
| C — API/UI | Next.js shell, Strata tokens, fixture read models, Ladder-derived bounded graph package | UI and query-contract tests | switches fixtures to live read APIs without component rewrites |
| D — Intelligence/quality | predicate registry, current-state materialization, baseline rules, evidence/assessment evaluation harness | recomputation on change outbox | produces explainable assessment/recommendation from shared facts |

### Shared contract gate before lanes diverge

Freeze only these items first:

- canonical identity formats, including npm registry origin and private-package tenant scope;
- predicate/entity vocabulary v1;
- fact/evidence contract v1;
- complete/partial snapshot semantics;
- raw observation envelope;
- bounded graph/read-model API shapes;
- one golden repository and one golden package/project fixture.

Everything else can evolve behind versioned adapters.

## 10. Milestones

### Milestone 0 — contract hardening

- Correct fact schema and formalize scanner/raw observation schemas.
- Reconcile ontology, UI, SQL, and graph vocabularies.
- Add migrations for ingestion state, identity, idempotency, temporal closure, outbox, and RLS.
- Atomize a representative subset of the seed and restore durable provenance.
- Create golden fixtures and contract tests.

**Exit:** the same fixtures validate in JSON Schema, database ingestion, graph projection, and TypeScript/Python generated types.

### Milestone 1 — running ingestion substrate

- Deploy Postgres/AGE, raw blob store, scheduler, workers, and observability.
- Run deps.dev and OSV adapters continuously for seed/observed npm and PyPI targets.
- Implement targeted public GitHub repo resolver/poller.
- Implement inbox, cursor, retry, replay, dead-letter, and freshness dashboards.

**Exit:** stop/restart/replay produces no duplicate semantic facts; unchanged sources do not cause re-normalization; source lag is visible.

### Milestone 2 — first vertical estate slice

- GitHub App installation and repository reconciliation.
- JS/TS and Python Pass A scanners plus Docker/basic K8s/Terraform.
- Canonical repository-to-registry-qualified-package-version-to-project bridge.
- AGE projection and bounded neighborhood query.
- Technology Explorer backed by live data and exact evidence.

**Exit:** a repository dependency can be traced to its manifest/lockfile, effective registry resolution, and external package/project/OSV observations without exposing registry credentials.

### Milestone 3 — V0 product experience

- Software Estate, Application Explorer, Technology Explorer, Viability Dashboard, and Ask Your Estate.
- Ladder-derived bounded graph explore mode with aggregation and uncertain bridge UI.
- Baseline deterministic assessments: unsupported runtime, archived/deprecated project, stale release, known vulnerability, unused declared dependency, and declared deployment pattern.
- Text-first query responses with citations.

**Exit:** all five screens operate on live read models; no UI conclusion lacks evidence and freshness.

### Milestone 4 — pilot readiness

- Two-pass scanning optimized for early findings.
- Tenant isolation/security review, provider quota behavior, backups, replay drills, and projection recovery.
- Performance/load tests for 100+ repositories and bounded graph queries.
- Accessibility, keyboard, reduced-motion, dark/light, browser, and source-failure testing.
- Pilot runbook and measurement instrumentation.

**Exit:** a 100+ repository pilot yields at least five material, evidence-backed findings within roughly 20 minutes, while deeper scans continue asynchronously.

### Milestone 5 — V1 intelligence

- Business capability mapping, entropy, internal reuse, alternative scoring, modernization portfolio ranking.
- Explicit sampling cohorts for OSS adoption/co-occurrence.
- Targeted history analysis and reusable migration-pattern objects.
- Recommendation review/outcome feedback and rescan verification.

## 11. Testing and operational gates

### Contract/data quality

- Every JSON artifact validates against a pinned schema version.
- Referential-integrity checks cover seed, identities, predicate endpoints, evidence, and projection parity.
- Golden snapshots prove idempotency, rename handling, removal closure, partial-scan safety, and parser-version replay.
- External facts retain raw source pointer, observed/effective time, provider version, and adapter version.

### Ingestion resilience

- Duplicate/out-of-order webhook delivery.
- Worker crash after raw write, after normalization, and before outbox acknowledgement.
- Rate-limit/secondary-limit response, stale ETag, pagination restart, provider schema drift, and corrupted blob.
- Reconciliation after missed webhook.
- Dead-letter replay after adapter upgrade.

### Product correctness

- SQL current state and AGE neighborhood return the same canonical IDs/edge assertions.
- Every score exposes components, method version, inputs, confidence, and counter-signals.
- Ask responses cite returned fact IDs and reject unsupported queries rather than inventing results.
- Low-confidence bridges are never rendered as confirmed.
- Cluster expansion never bypasses the bounded-node limit.

### Operational SLOs to track before setting targets

- time to first estate inventory and first material finding;
- customer repository scan lag;
- hot/warm OSS target freshness;
- queue depth/oldest work age;
- provider quota remaining and conditional-request hit rate;
- normalization failure and dead-letter rate;
- duplicate suppression rate;
- facts with complete evidence;
- AGE projection lag and parity errors;
- assessment/recommendation recomputation lag.

## 12. Recommended first backlog

1. Write architecture decision records for canonical identity, registry-qualified private packages, global versus tenant entities, temporal facts, and public-GitHub targeting.
2. Replace fact contract 0.x and make scanner contract a real JSON Schema.
3. Reconcile and generate one canonical ontology/predicate registry for SQL constraints, JSON Schema, API types, and AGE projection.
4. Add ingestion/raw observation/cursor/job/outbox migrations and RLS.
5. Restore the seed source artifact; atomize 20 representative seed groups with purl/repository identities and validation.
6. Stand up the observed-package scheduler, one deps.dev adapter, replay CLI, and freshness view.
7. Add the OSV batch adapter and project/repository metadata resolver.
8. Build JS/TS and Python manifest/lockfile scanners against the shared contract.
9. Extract the Ladder OntologyCanvas/layout/export kernel into a StackGraph read-only graph package with Apache attribution.
10. Build live Technology Explorer and evidence inspector for the golden vertical slice.
11. Add Software Estate read model and fixture-first UI while scanners widen.
12. Add deterministic baseline assessments and the first cited Ask query templates.

## 13. Decisions deliberately deferred

- A globally representative GitHub crawl or clone corpus.
- Full source/symbol graph.
- Migration mining across broad public history.
- Runtime/cloud/observability integrations.
- Autonomous code changes.
- Literal modernization priority formula and universal viability score.
- A separate distributed queue before PostgreSQL leasing becomes a measured bottleneck.
- Graph technology beyond AGE before real traversal/query evidence shows the need.

This ordering preserves the differentiating assets—evidence, capability semantics, temporal estate state, and OSS context—while allowing acquisition to compound from the beginning.
