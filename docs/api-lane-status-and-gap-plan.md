# API lane status and gap plan

**Updated:** 2026-08-19

**Implementation branch:** `phase-3-gap`

**Scope:** Backend read API, dependency/capability intelligence, modernization intelligence, and AI-backed Ask.

## Executive assessment

The backend API lane is now implemented through Phase 3. The original dependency-consolidation slice has
been extended with persisted code-unit evidence, internal and vendored duplication detection, native and
approved-internal alternatives, compatible-upgrade discovery, explicit eligibility gates, richer impact
evidence, validation outcomes, quality metrics, and configuration-aware reanalysis.

This does not make Phase 3 operationally finished in production. The branch still needs review and merge;
each tenant needs governed policy and internal-component data; and precision, scope error, effort error, and
acceptance targets need to be calibrated on real reviewed migrations. Phase 4 remains deliberately deferred.

## Status by phase

| Phase | Status | Delivered outcome | Remaining boundary |
| --- | --- | --- | --- |
| API foundation | Complete | Versioned `/api/v1` models, auth-derived tenancy, RLS, structured errors, bounded reads, evidence, and audited review | Product UI adoption is outside this backend lane |
| Phase 0 | Complete for npm/PyPI | Exact package identity, ingestion, evidence, enrichment, refresh/replay, and AGE projection | Additional ecosystems are Phase 4 |
| Phase 1 | Complete | Imports, symbols, reachability, runtime signals, unused/narrow-use findings, and package API surfaces | A dedicated findings product surface remains optional |
| Phase 2 | Complete | Versioned taxonomy, curated/constrained inference, duplicate-capability candidates, review, durable jobs, replay, RLS, and contracts | Taxonomy breadth and editorial governance grow with measured demand |
| Phase 3 backend | Complete on branch | Dependency and internal duplication, bounded alternatives, eligibility, impact, migration/rollback plans, review/outcomes, metrics, replay, and selective reanalysis | Production policy population, calibration, alerting, review, and merge |
| AI-backed Ask | Complete on branch | Allowlisted deterministic tools, tenant-scoped execution, validated citations, provider routing, and deterministic fallback | Production credentials, budgets, and rollout |
| Phase 4 | Deferred | None intentionally | More ecosystems, cohorts, trajectory, and public migration intelligence |

## Phase 3 completion inventory

### Evidence acquisition and persistence

- Python and JavaScript code units are extracted with stable structural fingerprints and semantic tokens.
- Code units retain repository, revision, symbol, line range, dependency keys, and source-fact identity.
- Deterministic local-import analysis links tests to code units without claiming runtime coverage.
- Dynamic imports, reflection, plugin loading, generated code, configuration, build, deployment, and vendored
  paths are persisted as evidence or explicit limitations.
- Complete scanner results persist code-unit facts and summaries under the same tenant and snapshot boundary.

### Candidate generation and alternatives

- Multiple dependencies serving one capability continue to produce consolidation candidates.
- Repeated internal implementations are detected within the tenant; vendored matches are labeled separately.
- A single observed dependency can produce a native, compatible-upgrade, or approved-internal replacement
  candidate when the bounded catalog contains an applicable option.
- Structural similarity proposes review; it never asserts behavioral equivalence.

### Eligibility and recommendation safety

- Every alternative records capability, API, behavior, runtime, license, security, and tenant-policy fit.
- A failed dimension disqualifies the option. Missing evidence remains `UNKNOWN` and cannot be converted into
  favorable compatibility.
- `REPLACE` is emitted only for a fully eligible alternative; otherwise the action remains `INVESTIGATE`.
- Tenant policy, approved internal components, catalog version, and analyzer version participate in replay
  fingerprints.

### Impact, feedback, and operations

- Impact records affected and uncovered call sites, affected files/tests, dynamic signals, config/build/deploy
  touchpoints, evidence locations, confidence, limitations, and versioned effort points.
- Candidate confirmation/rejection and recommendation acceptance/dismissal use optimistic concurrency and audit.
- Accepted recommendations can receive validation outcomes with actual scope, effort, checks, and notes.
- The Phase 3 metrics endpoint reports candidate precision, recommendation acceptance, validation success,
  affected-scope error, effort accuracy, evidence completeness, queue lag/latency, retries, dead letters,
  stale results, and available AI cost/latency data.
- `make intelligence-requeue` creates an idempotent job for the current analyzer, catalog, taxonomy, and policy
  configuration even when the repository revision is unchanged.

## Remaining gap register

| Priority | Gap | Why it matters | Exit condition |
| --- | --- | --- | --- |
| P0 | Review, push, CI, and merge | The implementation is not shared until normal delivery gates complete | Push `phase-3-gap`, open a focused PR, pass fresh hosted CI, review migration/RLS/worker semantics, and merge |
| P0 | Tenant policy and internal catalog rollout | Safe decisions depend on real runtime, license, security, and ownership rules | Each production tenant has a versioned active policy and governed approved-internal records |
| P1 | Calibration corpus and quality thresholds | The system exposes measurement but has no representative production baseline yet | Review a representative migration corpus and set precision, acceptance, scope-error, and effort-accuracy targets |
| P1 | Dashboards and alert routing | Metrics are queryable but not yet connected to operational ownership | Publish dashboards and alerts for queue lag, terminal failures, stale results, latency, cost, and quality regressions |
| P1 | Runtime behavior evidence | Static tests and dynamic-risk flags do not prove behavior equivalence | Attach bounded runtime/validation evidence where available and preserve `UNKNOWN` where it is not |
| P1 | Taxonomy and alternative stewardship | Catalog quality degrades without ownership and lifecycle rules | Assign owners and define review, versioning, deprecation, and security-refresh procedures |
| P2 | Scanner language breadth | Code-unit duplication currently targets Python and JavaScript/TypeScript syntax | Add languages only with deterministic extraction, fixtures, and the same tenant/evidence guarantees |
| P2 | Phase 4 reference intelligence | Broader signals may improve ranking but can create weak or unbounded evidence | Add ecosystems and bounded cohorts only after Phase 3 production quality gates hold |

## Gap execution plan

### Work package 1 — deliver the branch

1. Push `phase-3-gap` and open a focused pull request.
2. Require contract, type, service, fresh-schema, migration, API integration, and RLS checks.
3. Review migration `008`, policy defaults, reanalysis uniqueness, optimistic review, and metrics queries.
4. Merge without mixing unrelated UI work.

**Gate:** a fresh checkout bootstraps migrations 001–008 and passes the same isolated verification suite.

### Work package 2 — configure production safely

1. Publish a tenant policy with deployed runtime versions and approved license/security constraints.
2. Register only owned and supported internal components with evidence-backed API and behavior claims.
3. Requeue repositories under the new configuration fingerprint.
4. Sample `UNKNOWN`, disqualified, internal-duplication, and replacement results before wider exposure.

**Gate:** every recommendation explains its policy version, included/excluded options, evidence, unknowns, and
disqualifiers.

### Work package 3 — calibrate and operate

1. Record candidate decisions, recommendation decisions, and post-migration validation outcomes.
2. Establish baselines for precision, acceptance, validation success, scope error, and effort accuracy.
3. Set quality thresholds and alerts; investigate regressions by analyzer/catalog/policy version.
4. Promote catalog or scoring changes only after replaying the calibration set.

**Gate:** Phase 3 has owned dashboards, measurable quality targets, and an auditable promotion process.

### Work package 4 — expand cautiously

Add runtime evidence, languages, ecosystems, and reference cohorts one bounded source at a time. New sources
must preserve tenant isolation, deterministic provenance, replay, staleness, explicit unknowns, and review.

**Gate:** no expansion weakens the Phase 3 evidence or eligibility invariants.

## Verification evidence

The implementation was verified from rebuilt images against an isolated fresh PostgreSQL/Apache AGE database.

| Check | Result |
| --- | ---: |
| Fresh schema and migration checksum verification | Migrations 001–008 valid |
| API unit, contract, PostgreSQL/AGE integration, auth, and RLS | 39 passed |
| Data-platform unit and PostgreSQL integration | 31 passed |
| Intelligence unit and PostgreSQL integration | 22 passed |
| Repository scanner | 25 passed; frozen-schema test skipped because the production image omits `jsonschema` |
| Contract fixture validation | 19 fixtures valid |

## Definition of done

The Phase 3 backend implementation is complete when this branch is reviewed, green in hosted CI, and merged.
Phase 3 is production-complete when active tenant policies and approved internal catalogs are governed,
configuration changes are selectively replayed, reviewed outcomes establish quality thresholds, and queue,
latency, cost, staleness, precision, scope-error, and effort-error metrics have owned alerts.
