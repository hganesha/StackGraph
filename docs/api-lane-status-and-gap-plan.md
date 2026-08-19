# API lane status and gap plan

**Reviewed and implemented:** 2026-08-19  
**Branch:** `codex/api-phase-3-plan`  
**Scope:** Backend read API, dependency/capability intelligence, modernization intelligence, and AI-backed Ask.

## Executive assessment

The API lane is implemented through an evidence-backed first Phase 3 vertical slice on this branch.
Phases 0 and 1 were already complete. This branch closes the Phase 2 shipment gaps, adds the Phase 3
dependency-consolidation pipeline, and ports provider-backed Ask onto the current architecture.

Phase 3 is not complete in its broadest product sense. The delivered slice detects multiple observed
dependencies serving the same capability, ranks bounded observed/curated alternatives, calculates exact
known impact, and persists reviewable migration recommendations. Internal-code duplication, copied or
vendored similarity, runtime and policy compatibility proof, test-coverage mapping, calibration, and
production telemetry remain open.

The branch is ready for review, but it has not been pushed, opened as a pull request, or merged.

## Status by phase

| Phase | Status | Delivered outcome | Remaining boundary |
| --- | --- | --- | --- |
| API foundation | Complete | Versioned `/api/v1` read models, auth-derived tenancy, CORS, structured errors, bounded graph reads, evidence, and audited review | Product UI adoption remains outside this backend lane |
| Phase 0 | Complete for npm/PyPI | Exact package identity, scanner ingestion, evidence, enrichment, refresh/replay, and AGE projection | New ecosystems are Phase 4 work |
| Phase 1 | Complete | Deterministic imports, symbols, reachability, runtime signals, unused/narrow-use findings, and package API surfaces | No dedicated unused/narrow-use product endpoint |
| Phase 2 | Complete on branch | Versioned capability taxonomy, curated mappings, constrained inference, duplicate-capability candidates, audited review, automatic jobs, replay, RLS, contracts, and runbook | Taxonomy breadth and editorial governance should expand with measured demand |
| Phase 3 | First vertical slice complete | Dependency-consolidation candidates, bounded alternatives, impact/effort, migration and rollback plans, audited review, stale/replay behavior, API and shared client | Broader semantic duplication, compatibility proof, calibration, and telemetry remain |
| AI-backed Ask | Complete on branch | Allowlisted deterministic tool selection, tenant-scoped execution, validated citations, structured explanation, provider routing, and safe deterministic fallback | Production route credentials, cost/latency telemetry, and operational rollout |
| Phase 4 | Deferred | None intentionally | Broader ecosystems, cohorts, trajectory, and public migration intelligence |

## What this branch completes

### Phase 2 closure

- Commits the previously uncommitted capability-intelligence work and rebases it onto current main.
- Adds golden capability fixtures and validates them in JSON Schema, OpenAPI, Python, and TypeScript.
- Adds optimistic, audited duplicate-candidate review.
- Schedules idempotent intelligence jobs after complete repository usage snapshots.
- Implements leasing, retry, terminal failure, dead-letter, and replay behavior.
- Verifies API queries with the application database role and explicit cross-tenant RLS denial.
- Adds a capability/modernization operations runbook and CI for contracts, types, services, migrations, and RLS.

### Phase 3A: dependency consolidation

- Converts Phase 2 duplicate-capability results into versioned modernization candidates.
- Builds a bounded alternative universe containing observed packages plus curated native/package options.
- Prevents unobserved alternatives with unknown compatibility from outranking observed dependencies.
- Derives affected references and files from persisted source evidence.
- Emits ordinal effort, explicit validation gaps, counter-signals, migration steps, and rollback steps.
- Persists deterministic input and analysis fingerprints for idempotent replay.
- Stales superseded results only after complete newer snapshots.
- Exposes bounded repository modernization reads and optimistic recommendation review with audit history.

### Provider-backed Ask

- The model selects only an allowlisted deterministic estate query; it cannot provide SQL or entity IDs.
- The API executes the query under the authenticated tenant before any explanation is generated.
- Explanations may cite only fact IDs returned by the deterministic tool result.
- Provider, prompt, database-audit, context-limit, or validation failures safely fall back to deterministic Ask by default.

## Remaining gap register

| Priority | Gap | Why it matters | Exit condition |
| --- | --- | --- | --- |
| P0 | Branch is not yet reviewed or merged | The implementation is not a shared release until normal review and CI complete | Push branch, open PR, obtain review, run CI from a fresh checkout, and merge |
| P0 | Internal semantic-duplication generators | Dependency consolidation finds only one important class of duplication | Detect internal wrapper/dependency overlap and repeated internal implementations with evidence and tenant isolation |
| P0 | Compatibility and policy filtering | Curated alternatives remain `UNKNOWN`; ranking cannot claim safe replacement | Evaluate runtime/framework version, required behavior, license, security, and tenant policy; expose disqualifiers and unknowns |
| P1 | Test and dynamic-behavior impact evidence | Static call sites alone cannot prove migration safety | Map tests to affected behavior and persist reflection, plugin, generated-code, and runtime-observation gaps |
| P1 | Effort/quality calibration | Ordinal effort and ranking are explainable but not yet measured | Build a reviewed migration corpus and publish precision, acceptance, affected-scope error, and effort-band error |
| P1 | Production observability | Jobs are durable, but operating quality is not visible enough | Add queue lag, retry/dead-letter, stale-result, latency, model-cost, acceptance, and dismissal metrics with alerts |
| P1 | Phase 1 findings product surface | Unused/narrow-use evidence is available mainly as downstream input | Add a bounded findings endpoint/review flow or explicitly document recommendations as the only supported surface |
| P1 | Taxonomy governance | The starter catalog proves the mechanism but does not provide broad coverage | Define ownership, coverage targets, aliases/hierarchy rules, version upgrade, deprecation, and retirement workflow |
| P2 | Broader alternative sources | Tenant-approved internal components and compatible upgrades are not yet populated | Add governed internal/native mappings and upgrade discovery after compatibility gates exist |
| P2 | Phase 4 reference intelligence | Broader signals would improve ranking but can create unbounded crawling and weak evidence | Add NuGet and bounded cohorts only after Phase 3 quality gates are met |

## Gap execution plan

### Work package 1 — ship the branch

1. Push `codex/api-phase-3-plan` and open a focused pull request containing commits `1ddc246`, `a8f00ab`, and `fab7928` plus this status document.
2. Require the API-lane workflow on a fresh hosted runner.
3. Review migration `007`, RLS policies, queue trigger semantics, and the AI Ask trust boundary.
4. Merge without mixing unrelated UI changes.

**Gate:** current main can bootstrap a fresh database and pass contracts, types, API, data, intelligence, and RLS checks.

### Work package 2 — broaden duplication candidates

Implement candidates in increasing-risk order:

1. internal wrapper versus dependency API usage;
2. repeated internal implementations within a tenant;
3. copied, forked, or vendored code;
4. native runtime functionality that supersedes a dependency.

Deterministic structure, symbols, checksums, call sites, and tests remain authoritative. Models or embeddings
may propose similarity, but cannot assert behavioral equivalence.

**Gate:** replay is idempotent, no comparison crosses tenants, limitations are persisted, and a reviewed fixture set establishes precision.

### Work package 3 — prove alternative eligibility

Add runtime/framework constraints, required API and behavior fit, compatible upgrades, license/policy rules,
vulnerability posture, maintenance health, release trajectory, and approved internal-component sources. Missing
evidence remains `UNKNOWN` and cannot become a favorable score.

**Gate:** every included/excluded option exposes its source, disqualifiers, unknowns, and score components.

### Work package 4 — improve impact and migration confidence

Persist exact affected imports, symbols, wrappers, tests, uncovered behavior, dynamic loading, configuration,
build, and deployment touch points. Calibrate ordinal effort against accepted migrations before considering
time estimates.

**Gate:** every count resolves to evidence and prediction error is measurable against reviewed outcomes.

### Work package 5 — operate and measure

Add selective reevaluation and metrics for repository revision, analyzer/taxonomy/policy version, queue lag,
retry/dead-letter, latency, stale results, model cost, review outcomes, and evidence completeness.

**Gate:** the Phase 3 pipeline can be replayed, monitored, explained, and rolled back without losing reviewed history.

## Verification evidence

The implementation was verified against an isolated fresh PostgreSQL/Apache AGE database and rebuilt service images.

| Check | Result |
| --- | ---: |
| API unit, contract, auth, RLS, and PostgreSQL integration | 38 passed |
| Data platform unit and PostgreSQL integration | 31 passed |
| Intelligence unit and PostgreSQL integration | 19 passed |
| Contract fixture validation | 18 fixtures valid |
| Shared TypeScript typecheck | Passed |
| Web TypeScript typecheck | Passed |
| Python compilation and `git diff --check` | Passed |

## Definition of done through full Phase 3

The lane is fully complete through Phase 3 when the branch is merged and a repository snapshot automatically
produces tenant-isolated, versioned, stale-aware, bounded, explainable, and reviewable usage, capability,
duplication, alternative, impact, and recommendation results; compatibility and policy gates are evidence-backed;
AI Ask uses deterministic tenant-scoped tools and validated citations; and precision, impact error, effort error,
latency, and review outcomes are measured in production.
