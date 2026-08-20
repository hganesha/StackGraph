# Lanes A, B, and D audit and roadmap

**Status:** Authoritative A/B/D implementation audit  
**Audit date:** 2026-08-19  
**Document baseline:** `main` at `3c9a31f`  
**Validated A/B/D baseline:** `442239c`; the intervening commits change only Lane C UI and bundle-budget files  
**Scope:** Lane A (data platform/OSS), Lane B (enterprise discovery), and Lane D (intelligence/quality)

## Executive assessment

StackGraph has a sound, tested foundation for all three audited lanes. The authoritative PostgreSQL model,
temporal publication rules, evidence requirements, tenant isolation, provider adapters, repository scanner,
capability inference, modernization analysis, and AGE projection all work together on a fresh database.

The main remaining risk is production operationalization, not the absence of core algorithms. A checked-in
continuous profile now connects GitHub installation/repository scheduling, acquisition, scanning, publication,
projection, intelligence, and freshness through durable leases and queues. It is a deployable reference topology,
not evidence of a production deployment. Production object-storage lifecycle controls, provider operations,
policy/catalog governance, calibration, and owned alerting are not complete.

| Area | Status | Evidence-backed conclusion | Primary remaining boundary |
| --- | --- | --- | --- |
| Lane A — Data platform/OSS | **Partial** | Schema, seed, temporal facts, evidence, deps.dev, OSV, npm metadata, queue primitives, replay, freshness, dead letters, AGE projection, local durable evidence, GitHub webhook routing, and a continuous reference topology are implemented and tested | Production deployment, webhook ingress/alerting, object-storage lifecycle controls, provider operations, PyPI metadata, and additional ecosystems |
| Lane B — Enterprise discovery | **Partial** | GitHub installation/reconciliation, webhook routing, leased acquisition-to-publication orchestration, npm/Python scanning, registry resolution, API-surface/code-unit evidence, persistence, and intelligence enqueueing are implemented and tested | Hosted GitHub App callback/token minting, production rollout, semantic deployment/IaC parsing, two-pass operation, runtime collection, and pilot-scale proof |
| Lane D — Intelligence/quality | **Partial** | Versioned taxonomy, evidence-constrained inference, duplicate detection, eligibility-gated modernization, impact, review/outcome capture, metrics, AI Ask, replay, and RLS are implemented and tested | Tenant policy/catalog rollout, calibration targets, dashboards/alerts, runtime validation, business-capability intelligence, and Phase 4 evidence |
| Cross-lane contract gate | **Verified** | The v1 ontology, fact, raw-observation, scanner, read-model, and OpenAPI fixtures validate together | Generated types and drift enforcement remain incomplete; TypeScript read-model types are still maintained manually |
| Pilot operations | **Missing** | No repository evidence demonstrates a complete 100+ repository production drill with owned SLOs, backups, replay, and alerts | Build and exercise the production control plane before claiming pilot readiness |
| Phase 4 expansion | **Deferred** | npm/PyPI are the intentionally bounded initial package ecosystems and Python/JS/TS are the scanner languages | Add sources only after Phase 3 quality and operational gates are measured |

Status means:

- **Verified** — implementation exists and a relevant automated check passed.
- **Partial** — meaningful implementation exists, but an integration, operational, or product boundary remains.
- **Missing** — the required production capability is not implemented in this repository.
- **Deferred** — intentionally outside the current bounded phase, not an accidental omission.

## Verification baseline

The audit used the repository contracts, tests, fresh-schema bootstrap, seed, and projection rather than treating
file presence as completion evidence.

| Verification | Result |
| --- | ---: |
| Frozen contract fixtures | 19 valid |
| Enterprise-discovery tests | 25 passed; 1 optional local `jsonschema` check skipped |
| Fresh PostgreSQL/AGE API and RLS suite | 39 passed |
| Fresh PostgreSQL/AGE data-platform suite | 31 passed |
| Fresh PostgreSQL/AGE intelligence suite | 22 passed |
| Foundation seed | 337 facts, 101 relationships, 192 technologies, 38 technical capabilities, 6 assessments |
| AGE projection | 337 events claimed and processed; 101 edge upserts; no pending audited events |

The fresh database bootstrapped the authoritative schema and verified migration checksums for migrations
001–008, then seeded and projected the complete foundation snapshot. The isolated audit database and volume were
removed after verification. These checks prove code and schema integration; they do not prove production provider
credentials, quotas, schedules, scale, backups, or operational ownership.

### Post-audit P0 implementation verification

The continuous control-loop implementation was verified on a separate fresh PostgreSQL/AGE Compose project and
does not replace the historical audit counts above:

| Verification | Result |
| --- | ---: |
| Enterprise discovery plus control loop | 43 passed; 1 optional local `jsonschema` check skipped |
| Data-platform regression | 31 passed |
| Intelligence regression | 22 passed |
| Changed/unchanged vertical integration | One changed revision published once and enqueued projection/intelligence; the next unchanged revision completed without a second snapshot |
| Continuous topology smoke | Discovery, projection, and intelligence stayed live; projection backlog reached 0 and generated intelligence jobs reached `SUCCEEDED` |

The isolated containers, network, database volume, snapshot volume, and evidence volume were removed after the
verification run. This proves the checked-in reference topology, not production provider or operations readiness.

Primary verification sources:

- [contract validator](../stackgraph-foundation/scripts/validate-contracts.mjs) and
  [v1 contracts](../stackgraph-foundation/contracts/v1/)
- [API/data/intelligence CI workflow](../.github/workflows/api-lane.yml)
- [database smoke tests](../infrastructure/database/tests/)
- [enterprise-discovery tests](../services/enterprise-discovery/tests/)
- [data-platform tests](../services/data-platform/tests/)
- [intelligence tests](../services/intelligence/ai-services/tests/)

## Milestone coverage

This table applies the milestones in the [implementation plan](stackgraph-implementation-plan.md) to the audited
lanes only. Lane C completion is intentionally not scored here.

| Milestone | Status | Delivered in A/B/D | Remaining A/B/D gate |
| --- | --- | --- | --- |
| 0 — Contract hardening | **Verified** | Canonical ontology and predicates, fact/evidence contract, raw observations, complete/partial snapshots, ingestion state, identity, RLS, outbox, golden fixtures, and migration checksums | Generate TypeScript/Python models from the frozen schemas and make generated drift a required gate |
| 1 — Running ingestion substrate | **Partial** | PostgreSQL/AGE, targets/runs, leases/recovery, retries, replay, dead letters, freshness, deps.dev, OSV, npm acquisition, local content-addressed evidence, continuous GitHub scheduling, and continuous projection are implemented | Deploy the topology with production object storage, webhook ingress, metrics/alerts, and provider observability |
| 2 — First vertical estate slice | **Partial** | GitHub reconciliation and revision detection automatically connect immutable acquisition, npm/Python scanning, publication, projection, intelligence, and bounded graph reads | Prove the topology against a real tenant slice with production credentials, quotas, and scale |
| 3 — V0 intelligence | **Partial** | Capability and modernization backends, deterministic evidence, AI-assisted constrained inference, Ask orchestration, reviews, outcomes, and metrics exist | Populate governed production policies/catalogs, calibrate results, attach alerts, and run continuously on live scans |
| 4 — Pilot readiness | **Missing** | Unit and fresh-database integration coverage are strong | Complete security/tenant review, quota behavior, backup/replay drills, 100+ repository load tests, and owned SLOs |
| 5 — V1 intelligence | **Partial** | Technical capability inference, dependency/internal duplication, alternatives, impact, and portfolio-ready recommendation records exist | Add business-capability mapping, entropy/reuse measures, business criticality, governed portfolio ranking, and outcome-driven recalibration |
| Phase 4 — Reference intelligence | **Deferred** | No unbounded reference intelligence is claimed | Add languages, ecosystems, cohorts, trajectory, history, and public migration evidence only after pilot gates hold |

## Lane A — Data platform and OSS ingestion

### Implemented and verified

| Capability | Status | Implementation evidence | Verification evidence |
| --- | --- | --- | --- |
| Authoritative relational model | **Verified** | [schema.sql](../stackgraph-foundation/schema.sql) defines tenants, source systems, connectors, registries, targets, runs, snapshots, entities, temporal facts, evidence, assessments, recommendations, outbox, dead letters, and freshness | Fresh-schema API, data, intelligence, seed, and database smoke suites |
| Tracked migrations | **Verified** | [migration runner](../services/data-platform/stackgraph_data/migrate.py) validates immutable SHA-256 checksums; [migrations 001–008](../infrastructure/database/migrations/) cover post-bootstrap evolution | Fresh bootstrap reported every tracked migration checksum as valid |
| Canonical seed and provenance | **Verified** | [catalog loader](../services/data-platform/stackgraph_data/catalog.py) and [seeder](../services/data-platform/stackgraph_data/seed.py) publish a versioned complete snapshot with entities, facts, evidence, assessments, and relationships | Seed tests plus fresh seed counts of 337 facts and 101 relationships |
| Temporal publication | **Verified** | `publish_source_snapshot` closes prior current facts only for complete publications and emits UPSERT/CLOSE outbox records in [schema.sql](../stackgraph-foundation/schema.sql) | Scanner persistence and projection integration tests |
| Evidence enforcement | **Verified** | Deferred database trigger requires evidence for every fact; fact object kind and tenant scope are checked in [schema.sql](../stackgraph-foundation/schema.sql) | Contract, database, and RLS integration suites |
| Registry-qualified npm identity | **Verified** | Registry/source tables plus [npm registry client](../services/data-platform/stackgraph_data/npm_registry.py) preserve origin, visibility, ETag, integrity, and safe authentication boundaries | npm normalization/client tests and repository registry-resolution tests |
| deps.dev enrichment | **Verified** | [adapter](../services/data-platform/stackgraph_data/depsdev.py) and [leased worker](../services/data-platform/stackgraph_data/depsdev_worker.py) support exact npm/PyPI purls, bounded dependency graphs, scheduling, retry, replay, freshness, and evidence | deps.dev unit tests; [runbook](runbooks/deps-dev-enrichment.md) |
| OSV enrichment | **Verified** | [adapter](../services/data-platform/stackgraph_data/osv.py) and [leased worker](../services/data-platform/stackgraph_data/osv_worker.py) batch exact npm/PyPI versions and publish evidence-backed vulnerability relationships | OSV unit tests; [runbook](runbooks/osv-enrichment.md) |
| Ingestion queue primitives | **Verified** | `ingest_target`, `ingest_run`, `ingest_item`, leases, due times, priorities, retries, and `FOR UPDATE SKIP LOCKED` claims are present in the schema and workers | Worker unit tests and database integration tests |
| Replay, failure, and freshness state | **Verified** | Idempotency keys, run fingerprints, `dead_letter`, and `freshness_state` are used by workers and persistence paths | deps.dev, OSV, scanner-ingest, and migration tests |
| AGE projection | **Verified** | [projector](../services/data-platform/stackgraph_data/project.py) claims outbox events, parameterizes Cypher, preserves evidence/confidence, and acknowledges in the database transaction | Projection unit/smoke tests and fresh projection of all 337 seed facts |
| Continuous GitHub control loop | **Verified** | [control loop](../services/enterprise-discovery/stackgraph_discovery/github_control_loop.py) schedules due targets, prioritizes durable triggers, recovers leases, retries provider failures, dead-letters terminal work, and feeds publication; [Compose](../compose.yaml) continuously runs discovery, projection, and intelligence | Control-loop unit/PostgreSQL tests and [continuous pipeline runbook](runbooks/continuous-discovery-pipeline.md) |
| SQL as authority | **Verified** | Projection is explicitly asynchronous; read paths can fall back to tenant-filtered SQL when AGE is unavailable, stale, or divergent | [local backend runbook](runbooks/local-backend.md) and graph aggregation tests |

### Implemented but not operationalized

- The [Compose `pipeline` profile](../compose.yaml) is a continuous reference topology for GitHub discovery,
  projection, and intelligence. It has not been deployed with production resource limits, autoscaling, graceful
  termination policy, SLOs, or operational ownership; deps.dev and OSV remain bounded tool workers.
- `source_artifact` and `raw_observation` retain `blob_uri` references, hashes, and metadata, but the local stack
  contains no S3-compatible object store, retention policy, lifecycle policy, or restore procedure.
- The GitHub webhook receiver verifies signatures, archives bodies, deduplicates deliveries, and routes lifecycle
  events into the continuous control loop. Production TLS ingress, secret rotation, delivery/reconciliation
  alerting, and a supervised deployment are not defined.
- Freshness and queue state are queryable in PostgreSQL, while production dashboards, alert routes, and named
  owners are not defined.
- npm registry acquisition is implemented as a bounded client/CLI, not a leased refresh worker equivalent to
  deps.dev and OSV.

### Lane A gap register

| ID | Priority | Gap | Required deliverable | Exit condition |
| --- | --- | --- | --- | --- |
| A-01 | P0 | Productionize continuous control loop | Deploy the checked-in durable scheduler/worker topology with graceful termination, resource/concurrency policy, queue metrics, and owned operations | Restarting any worker loses no work; due targets advance automatically; queue age and terminal failures are visible and alerted |
| A-02 | P0 | Durable raw-object storage | Tenant-scoped object-storage adapter for raw observations, source artifacts, and repository snapshots with checksums, retention, encryption, and deletion policy | Every persisted blob reference resolves; replay works after database/process restart; tenant deletion removes governed objects |
| A-03 | P0 | Webhook ingestion | Authenticated GitHub webhook receiver, signature verification, dedupe, event-to-target routing, and missed-event reconciliation | Duplicate/out-of-order deliveries are harmless and a missed delivery is repaired by reconciliation |
| A-04 | P0 | Production operations | Metrics export and owned alerts for queue age, retry/terminal failure, dead letters, provider quota, normalization failure, stale targets, projection lag, and parity | Dashboards have thresholds, routes, runbooks, and a named owner; injected failures alert and recover |
| A-05 | P1 | Public project metadata refresh | Bounded resolver/poller for public OSS project/repository, release, license, and maintainer metadata, driven only by observed/curated targets | One observed package is traceable to fresh project/release/license evidence without an ecosystem crawl |
| A-06 | P1 | PyPI index metadata | Exact-version PyPI metadata adapter with tenant-safe source identity, artifact hashes, conditional requests where supported, and replay | npm and PyPI both provide first-party package-index evidence for the golden package slice |
| A-07 | P1 | Backup and replay drills | Documented database/object backup, restore, outbox recovery, adapter replay, and projection rebuild drills | A clean environment is restored and reaches SQL/AGE parity within a measured recovery window |
| A-08 | P2 | Ecosystem expansion | One versioned adapter at a time for Maven, Cargo, and later ecosystems, retaining the same identity/evidence/replay rules | Each adapter has golden fixtures, schema validation, provider-failure tests, freshness, and bounded targeting |

## Lane B — Enterprise discovery

### Implemented and verified

| Capability | Status | Implementation evidence | Verification evidence |
| --- | --- | --- | --- |
| GitHub repository acquisition | **Verified** | [GitHub client](../services/enterprise-discovery/stackgraph_discovery/github_client.py) and [snapshot acquirer](../services/enterprise-discovery/stackgraph_discovery/github_snapshot.py) resolve immutable repository/commit identity, enforce bounds, reject unsafe paths/origins, and classify retryable failures | GitHub acquisition tests cover unchanged revisions, truncation, rate limits, unsafe paths, and private-installation identity |
| GitHub installation lifecycle | **Verified** | [installation discovery](../services/enterprise-discovery/stackgraph_discovery/github_installation.py), [persistence](../services/enterprise-discovery/stackgraph_discovery/github_installation_store.py), and the [lifecycle runbook](runbooks/github-installation-lifecycle.md) register credential references, paginate the complete authorized set, create connector-bound targets/cursors, disable removals, and revoke safely | Unit and PostgreSQL integration tests cover pagination, replay, tenant conflicts, removal, pending-run cancellation, and revocation |
| GitHub webhook routing | **Verified** | [webhook verifier](../services/enterprise-discovery/stackgraph_discovery/github_webhook.py), [delivery router](../services/enterprise-discovery/stackgraph_discovery/github_webhook_store.py), and [HTTP receiver](../services/enterprise-discovery/stackgraph_discovery/github_webhook_server.py) verify HMAC before parsing, archive bodies, dedupe delivery IDs, and schedule default-branch revisions/reconciliation | Signature and database integration tests cover safe headers, replay, push routing, repository removal, evidence URIs, and pending-run cancellation |
| Immutable snapshots and durable descriptors | **Verified** | Revision-addressed materializations contain selected files, `snapshot.json`, and a contract-v1 raw observation; a configured local evidence backend creates a deterministic checksum-addressed archive and scanner evidence retains archive-member URIs | Acquisition/evidence-store tests and [enterprise-discovery README](../services/enterprise-discovery/README.md) |
| npm manifests and locks | **Verified** | [repository scanner](../services/enterprise-discovery/stackgraph_discovery/repository_scanner.py) reads package manifests plus npm, Yarn, and pnpm locks, with workspace/component scope | Scanner tests cover resolved dependencies and line-level evidence |
| Python manifests and locks | **Verified** | Scanner supports `pyproject.toml`, Poetry, uv, Pipenv, and requirements files with exact-version resolution where available | Scanner tests cover Python lock, import, and reachability evidence |
| npm registry resolution | **Verified** | [resolver](../services/enterprise-discovery/stackgraph_discovery/npm_resolution.py) combines lockfiles and repository-owned `.npmrc`, redacts auth, preserves custom origins, and distinguishes public/private identity | Resolution tests cover scoped registries, custom origins, tarballs, credentials, and portability |
| Usage and reachability | **Verified** | JS/TS and Python references, symbols, deterministic entrypoint reachability, optional runtime observations, unused candidates, and narrow-use candidates are emitted separately with limitations | Scanner tests cover declared/resolved/referenced/reachable/runtime distinctions and partial-scan safety |
| API-surface extraction | **Verified** | [API surface analyzer](../services/enterprise-discovery/stackgraph_discovery/api_surface.py) extracts public Python and JS/TS symbols keyed by exact purl and artifact checksum | API-surface tests and scanner persistence integration tests |
| Code-unit evidence | **Verified** | Scanner persists Python and JS/TS function/class fingerprints, semantic tokens, dependency keys, test links, dynamic-risk signals, touchpoints, and vendored status | Code-unit scanner tests and migration 008 integration coverage |
| Scanner persistence | **Verified** | [scanner ingest](../services/data-platform/stackgraph_data/scanner_ingest.py) validates tenant/run/revision boundaries, publishes snapshots transactionally, persists usage summaries/code units, and supports replay | Scanner-ingest database integration tests |
| Automatic intelligence enqueue | **Verified** | A complete `repository-dependency-usage` publication triggers an idempotent `REPOSITORY_MODERNIZATION` job; the worker runs capability inference before modernization | Migration 007/008, modernization-worker tests, and fresh database intelligence tests |
| Acquisition-to-publication orchestration | **Verified** | [GitHub control loop](../services/enterprise-discovery/stackgraph_discovery/github_control_loop.py) leases installation/repository runs, short-circuits unchanged revisions, durably stores changed snapshots, scans, publishes, and updates freshness; projection and intelligence consume publication queues continuously | Control-loop tests, existing acquisition/scanner/persistence suites, and [pipeline runbook](runbooks/continuous-discovery-pipeline.md) |

### Implemented but not operationalized

- GitHub installation registration, authorized-repository pagination, removal/revocation, and webhook routing are
  implemented. A hosted authorization callback and production secret-broker adapter for minting/refreshing
  installation tokens are still absent; the checked-in local resolver supports `env://` references only.
- The checked-in control loop durably moves changed repositories through acquisition, scan, publication,
  projection, and intelligence, and avoids blob/scan work for unchanged revisions. Production deployment proof,
  concurrency/quota tuning, provider metrics, and a 100+ repository drill remain absent.
- `Dockerfile`, Compose files, and selected deployment/config YAML are acquired. The scanner records them as
  impact touchpoints; it does not parse Docker images, Kubernetes workloads, Terraform resources, environments,
  regions, or deployment relationships into canonical facts. `.tf` files are not currently selected.
- `stackgraph-runtime.json` can supply runtime observations to the scanner, but the repository contains no
  runtime collector, attestation format producer, or deployment integration that creates it.
- Snapshot evidence has a local durable backend, while production durability, retention, encryption, and restore
  still depend on completing Lane A's object-storage lifecycle gap.

### Lane B gap register

| ID | Priority | Gap | Required deliverable | Exit condition |
| --- | --- | --- | --- | --- |
| B-01 | P0 | GitHub App and organization lifecycle | Installation callback/service, credential reference, org/repository discovery, pagination, token refresh, removal handling, and reconciliation | Installing one tenant discovers the authorized repositories without accepting a raw token and removal stops/finalizes their targets safely |
| B-02 | P0 | Productionize repository orchestration | Deploy and exercise the implemented durable revision-to-intelligence workflow with bounded concurrency and provider quotas | A real changed default branch automatically produces current evidence and intelligence; an unchanged revision avoids blob/scan work under production operations |
| B-03 | P0 | Productionize webhook/reconciliation | Deploy the implemented delivery routing and periodic reconciliation with TLS ingress, delivery lag metrics, and alerts | Duplicate events do not duplicate facts, and an injected missed delivery is repaired and alerted by reconciliation |
| B-04 | P1 | Semantic deployment and IaC scan | Deterministic Docker, Compose, Kubernetes, and Terraform parsers using the shared fact/evidence contract | Golden repository emits declared image, workload, compute, environment, infrastructure, and locator-backed relationships |
| B-05 | P1 | Two-pass scanning | Fast inventory/early-finding pass followed by bounded deeper symbol, API, reachability, and code-unit analysis | Time to first inventory/finding is measured independently from deep-scan completion and partial results cannot close complete state |
| B-06 | P1 | Runtime evidence acquisition | Versioned runtime/deployment observation contract and bounded collectors or import adapters | Runtime claims link to source/revision/environment and can change `UNKNOWN` only with direct evidence |
| B-07 | P1 | Pilot-scale performance | Representative 100+ repository corpus, concurrency/quota policy, load harness, and failure injection | Pilot target reaches first inventory and material findings within measured goals while queues remain bounded |
| B-08 | P2 | Language breadth | Deterministic manifest, source-reference, API-surface, and code-unit support for additional languages | Each language matches existing completeness, evidence, limitation, replay, and tenant-isolation guarantees |

## Lane D — Intelligence and quality

### Implemented and verified

| Capability | Status | Implementation evidence | Verification evidence |
| --- | --- | --- | --- |
| Versioned capability taxonomy | **Verified** | [capability catalog](../services/intelligence/ai-services/stackgraph_ai/capabilities.py), [synchronizer](../services/intelligence/ai-services/stackgraph_ai/sync_capabilities.py), and migration 006 preserve versions, content hashes, mappings, aliases, and tenant/global visibility | Catalog, capability, persistence, API contract, and RLS tests |
| Evidence-constrained inference | **Verified** | Curated mappings use active dependency/symbol evidence; optional AI output must select a known capability and supplied fact IDs | Capability tests and [capability/modernization runbook](runbooks/capability-modernization-intelligence.md) |
| Duplicate-capability detection | **Verified** | Multiple distinct active dependencies serving one technical capability generate reviewable candidates only from complete snapshots | Capability unit/persistence tests |
| Internal and vendored duplication | **Verified** | Structural code-unit fingerprints generate separately labeled internal/vendored candidates; similarity remains evidence for review, not behavioral truth | Modernization unit and database integration tests |
| Bounded alternatives | **Verified** | [alternative catalog](../services/intelligence/ai-services/alternatives/default.json) plus compatible upgrades and governed internal components provide package/native/upgrade/internal options | Catalog and modernization tests |
| Seven-dimension eligibility | **Verified** | [modernization analyzer](../services/intelligence/ai-services/stackgraph_ai/modernization.py) evaluates capability, API, behavior, runtime, license, security, and tenant-policy fit; failure disqualifies and unknown stays unknown | Phase 3 modernization tests |
| Impact and effort | **Verified** | Affected/uncovered call sites, files/tests, dynamic signals, config/build/deploy touchpoints, evidence locations, confidence, and versioned effort points are persisted | Migration 008 and modernization integration tests |
| Durable intelligence jobs | **Verified** | [modernization worker](../services/intelligence/ai-services/stackgraph_ai/modernization_worker.py) claims leased jobs, runs capability inference then modernization, retries, dead-letters terminal failures, and stales superseded results | Worker/integration tests and runbook recovery procedure |
| Configuration-aware replay | **Verified** | Analyzer, taxonomy, alternative catalog, tenant policy, and internal-component state participate in configuration fingerprints; unchanged revisions can be requeued idempotently | Reanalysis tests and `make intelligence-requeue` flow |
| Human review and outcomes | **Verified** | Capability inference, duplicate candidate, modernization candidate, recommendation review, and validation outcomes use optimistic versions and audit records | API/RLS and modernization database tests |
| Quality/operations metrics | **Verified** | Phase 3 metrics expose precision, acceptance, validation success, scope/effort error, evidence completeness, queue latency, retries, dead letters, stale results, and available AI cost/latency | API contract and database integration tests |
| Provider-neutral AI and Ask | **Verified** | [AI service](../services/intelligence/ai-services/stackgraph_ai/service.py), versioned prompts, provider adapters, deterministic tool selection, citation validation, data-handling controls, and fallback are implemented | Provider, prompt, service, and API Ask tests |
| Tenant isolation | **Verified** | Taxonomy visibility and every tenant intelligence table are protected by RLS; tenant identity is auth-derived | Fresh API tests under the application role and dedicated RLS assertions |

### Implemented but not operationalized

- `modernization_policy` and `modernization_internal_component` are complete persistence inputs, but the
  repository contains no production tenant policy set, stewardship workflow, approval lifecycle, or population
  evidence. Default/unconfigured inputs deliberately prevent unsupported confident replacement.
- The metrics endpoint can calculate quality and operational measures, but no representative reviewed migration
  corpus establishes acceptable precision, scope-error, effort-error, or acceptance thresholds.
- Metrics are not attached to production dashboards, alerts, ownership, or promotion gates.
- Static test linkage, dynamic-risk flags, and optional runtime observations improve impact analysis, but they do
  not prove behavior equivalence. Runtime validation and post-change checks remain external evidence inputs.
- The implemented taxonomy is technical. Canonical business entities exist in the ontology, but intelligence
  does not yet resolve business capability importance, application support, entropy, reuse, or portfolio value.

### Lane D gap register

| ID | Priority | Gap | Required deliverable | Exit condition |
| --- | --- | --- | --- | --- |
| D-01 | P0 | Tenant policy rollout | Versioned active policies covering deployed runtimes, licenses, security posture, tags, denied options, ownership, and promotion | Every production recommendation explains the active policy version, exclusions, unknowns, and disqualifiers |
| D-02 | P0 | Approved internal catalog governance | Evidence-backed internal component registration, ownership, support status, API/behavior claims, deprecation, and security refresh | No internal option ranks without an active owner and supporting evidence; expired/deprecated options stop qualifying |
| D-03 | P0 | Calibration corpus and thresholds | Representative reviewed candidates, accepted/rejected recommendations, and post-change validation outcomes with versioned cohorts | Precision, acceptance, validation, scope-error, and effort-accuracy targets are set and reproducibly measured |
| D-04 | P0 | Operational and quality alerting | Dashboards, thresholds, promotion gates, and routes for quality regression, queue lag, terminal failure, staleness, latency, and AI cost | Analyzer/catalog/policy regressions alert by version and block promotion when a governed threshold fails |
| D-05 | P1 | Runtime and behavioral validation | Ingest bounded runtime, contract-test, performance, and post-migration validation evidence without converting absence into a pass | Eligible replacements distinguish direct proof from static inference and retain `UNKNOWN` wherever proof is absent |
| D-06 | P1 | Business-capability intelligence | Map canonical business capabilities/functions/value chains to applications/services/repositories with evidence, criticality, and ownership | A modernization opportunity can explain business impact through a cited business-to-technology path |
| D-07 | P1 | V1 portfolio measures | Versioned entropy, internal reuse, duplication, business criticality, confidence, effort, and portfolio ranking models | Each portfolio score exposes inputs, method version, confidence, counter-signals, and calibration performance |
| D-08 | P1 | Automated data-quality gates | Referential, evidence-completeness, SQL/AGE parity, stale-input, unsupported-confidence, and cohort-drift gates | Bad data or unsupported conclusions fail a machine-readable gate before promotion or display |
| D-09 | P2 | Reference intelligence | Bounded adoption/co-occurrence cohorts, release/project trajectory, targeted history, and reusable migration-pattern evidence | Every signal has a sampled denominator, observation window, provenance, freshness, and documented ranking influence |

## Dependency-ordered execution roadmap

The order below is intentionally cross-lane. Later work must not compensate for missing evidence or operations by
increasing model confidence.

Implementation progress on `codex/lane-a-b-d-p0`:

- Work package 1 / A-02 is **Partial**. Repository snapshots now have a tenant-scoped, content-addressed local
  evidence backend with atomic writes, checksum verification, deterministic archives, raw-observation database
  persistence, and archive-member URIs on persisted source artifacts.
- A-02 remains open until a production object-store backend, encryption/key policy, retention/legal-hold rules,
  authorized deletion workflow, restore/replay drill, and operational telemetry satisfy its exit condition.
- Work package 2 / B-01 + A-03 is **Partial**. Credential-reference installation registration, bounded complete
  repository reconciliation, safe removal/revocation, an HMAC-verifying HTTP receiver, durable webhook bodies,
  delivery dedupe, and default-branch push routing are implemented. It remains open for the hosted installation
  callback, production token broker/refresh, production scheduler ownership, TLS ingress, and delivery alerts.
- Work package 3 / A-01 + B-02 + B-03 is **Partial**. The checked-in control loop and Compose topology now cover
  due scheduling, trigger priority, lease recovery/renewal, provider-aware retry/dead letters, unchanged revision
  short-circuiting, durable acquisition, scan publication, freshness, projection, and intelligence. It remains
  open for production deployment, concurrency/quota policy, metrics/alerts, and pilot-scale recovery proof.

| Order | Work package | Owner | Prerequisites | Deliverable and exit condition |
| ---: | --- | --- | --- | --- |
| 1 | Durable evidence plane | A | Existing raw/source contracts | Complete A-02; raw artifacts and snapshots survive process/database replacement and remain replayable |
| 2 | GitHub tenant lifecycle | B with A | Credential references and durable evidence plane | Complete B-01 and A-03 for one tenant installation, including removal and missed-event reconciliation |
| 3 | Productionize repository/OSS control loop | A + B | Orders 1–2 | Deploy and operate the implemented A-01/B-02/B-03 topology; changed repositories reach published facts, projection, intelligence, and freshness under production credentials, quotas, metrics, and alerts |
| 4 | Production telemetry and recovery | A | Continuous control loop | Complete A-04 and A-07; failure injection proves alerts, lease recovery, restore, replay, and projection rebuild |
| 5 | Governed intelligence inputs | D | Stable tenant ingestion | Complete D-01 and D-02; requeue all repositories under explicit policy/catalog fingerprints |
| 6 | Calibration and promotion | D | Governed inputs and reviewed results | Complete D-03 and D-04; quality thresholds and version-aware promotion gates are owned |
| 7 | Richer deterministic estate evidence | B | Stable orchestration and storage | Complete B-04 and B-05; deployment/IaC facts and two-pass timing meet contract and partial-snapshot rules |
| 8 | Runtime validation | B + D | Richer estate evidence | Complete B-06 and D-05; runtime/validation evidence changes eligibility only when directly supported |
| 9 | Pilot-scale proof | A + B + D | Orders 1–8 | Complete B-07 and D-08; a 100+ repository drill meets measured SLOs without tenant, evidence, or parity violations |
| 10 | Business and portfolio intelligence | D; consumes Lane C contracts | Calibrated technical intelligence and canonical business data | Complete D-06 and D-07; cited business impact participates in governed portfolio ranking |
| 11 | Bounded expansion | A + B + D | Pilot gates remain green | Complete A-05/A-06 first, then A-08/B-08/D-09 one source at a time with replay and calibration |

## Lane C handoff — excluded from this branch

This audit does not modify `apps/web`, `apps/api`, shared UI/API contracts, or Lane C status documents. The
following findings are recorded only so A/B/D work does not assume that authored business data is already
durable:

- Business Map function, process, capability, stage, placement, organization-unit, assignment, maturity, and
  shared-group edits are saved only in browser `localStorage` by
  [useBusinessMap.ts](../apps/web/features/business-map/useBusinessMap.ts).
- `ValueChain`, `BusinessFunction`, `BusinessProcess`, and `BusinessCapability` are valid generic entity types in
  [schema.sql](../stackgraph-foundation/schema.sql), but no Business Map authoring tables, write service, revision
  model, or CRUD routes exist.
- `SharedCapabilityGroup` is a UI type, not a canonical ontology entity or database object. The recommended model
  is a map overlay that references canonical capabilities and a stage span; deleting the overlay must not delete
  its capabilities.
- Lane D business-capability work (D-06) depends on the canonical IDs, tenant scope, revision semantics, and read
  contract produced by the separate Lane C branch. Lane D must not ingest browser-local identifiers as durable
  business truth.

## Readiness gates

### Pilot-ready A/B/D

All of the following must be true before claiming pilot readiness:

- A tenant can install a GitHub App and automatically reconcile its repository set.
- A repository change flows through durable acquisition, scanning, publication, projection, intelligence, and
  freshness without manual Make targets.
- Raw inputs are replayable from durable storage; complete/partial semantics and tenant isolation remain intact.
- Queue, provider, projection, freshness, dead-letter, quality, latency, and AI-cost alerts have named owners.
- At least one database/object restore and projection rebuild drill has completed successfully.
- A 100+ repository test records time to inventory, first finding, queue age, provider quota, projection lag,
  evidence coverage, and intelligence latency.
- Each tenant has an active governed policy and internal catalog, or recommendations remain explicitly
  investigative.
- A reviewed calibration corpus has documented thresholds and promotion behavior.

### V1-ready A/B/D

In addition to pilot readiness:

- Business capability and application/technology links use canonical, tenant-scoped IDs and cited evidence.
- Portfolio ranking includes business importance, technical viability, opportunity, confidence, and effort with
  versioned methods.
- Runtime and post-change validation evidence can update outcomes without rewriting historical facts.
- Data-quality gates prevent unsupported confidence, stale inputs, parity divergence, or missing evidence from
  reaching governed recommendations.

### Phase 4 admission rule

Do not add an ecosystem, language, cohort, history source, or public migration source until it has:

1. a bounded target-selection rule;
2. canonical identity and tenant-scope semantics;
3. raw observation and evidence provenance;
4. complete/partial, freshness, retry, replay, and deletion behavior;
5. golden fixtures and provider-failure tests;
6. a documented effect on ranking and calibration; and
7. an owner for provider drift, quotas, and incident response.

## Assumptions and boundaries

- PostgreSQL remains authoritative; AGE is a recoverable asynchronous projection.
- Missing evidence remains `UNKNOWN`; it is never converted into favorable compatibility or behavioral proof.
- Operational readiness is not inferred from unit or integration success when deployment evidence is absent.
- The audit covers repository implementation only. It does not assert the state of external credentials,
  production tenants, dashboards, backups, or infrastructure that are not represented here.
- The user owns Lane C work on a separate branch. This branch is documentation-only and intentionally avoids
  Lane C code and status files.
