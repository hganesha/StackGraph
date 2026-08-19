# API lane implementation status

**Updated:** 2026-08-19

See [API lane status and gap plan](./api-lane-status-and-gap-plan.md) for the detailed completion evidence,
remaining Phase 3 gaps, delivery sequence, and definition of done.

## Outcome

The API lane is implemented through the first evidence-backed Phase 3 vertical slice.

- Phase 0: exact package identity, ingestion, evidence, enrichment, refresh, and projection are complete for npm/PyPI.
- Phase 1: deterministic import, symbol, reachability, runtime, unused/narrow-use, and package API-surface analysis are complete.
- Phase 2: versioned capability taxonomy, curated mappings, constrained AI inference, duplicate-capability detection, human review, automatic scheduling, and API contracts are complete.
- Phase 3: dependency-consolidation candidates, bounded alternatives, deterministic call-site/file impact, effort bands, counter-signals, migration/rollback plans, audited review, replay, staleness, and API/shared-client contracts are implemented.
- AI-backed Ask: allowlisted deterministic query selection, tenant-scoped execution, validated citations, provider-neutral explanation, and safe fallback are implemented.
- Phase 4 remains deliberately deferred.

Phase 3 currently covers the safest initial slice: multiple observed dependencies serving the same capability. Internal-code semantic duplication, copied/vendored similarity, calibrated test-coverage mapping, ecosystem trajectory, and automatically verified package/runtime compatibility remain future expansion areas. Curated but unobserved alternatives stay `UNKNOWN` and cannot outrank an observed dependency.

## Delivery gates closed

- Phase 2 work is committed on `codex/api-phase-3-plan` and rebased onto current `origin/main`.
- Fresh database bootstrap records migration checksums for migrations 001–007; the migration runner reports all seven as applied/skipped consistently.
- Complete repository snapshots enqueue idempotent leased intelligence jobs.
- Retry, terminal failure, and dead-letter behavior are implemented.
- New API read and review models run under the application role with RLS.
- Capability, modernization, and shared TypeScript contracts have fixtures.
- CI covers contract validation, fresh-database integration, service tests, and TypeScript checks.

## Remaining expansion plan

1. Add internal-wrapper and repeated-internal-implementation candidate generators.
2. Persist test-to-call-site coverage and dynamic behavior evidence.
3. Add runtime/framework version constraints and license/policy gates to alternative filtering.
4. Calibrate effort bands and recommendation precision against reviewed migrations.
5. Add NuGet and bounded reference cohorts only after Phase 3 quality targets are met.
