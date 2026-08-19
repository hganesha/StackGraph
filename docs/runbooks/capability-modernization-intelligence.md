# Capability and modernization intelligence

This pipeline turns a complete repository dependency-usage snapshot into versioned capability inferences, duplicate-capability candidates, ranked consolidation options, deterministic impact estimates, and reviewable migration recommendations.

## Data flow

1. The repository scanner publishes a `COMPLETE` `repository-dependency-usage` snapshot.
2. Migration 007's publication trigger inserts one idempotent `REPOSITORY_MODERNIZATION` job for the tenant, repository, and source revision.
3. The intelligence worker synchronizes the active capability taxonomy and applies curated mappings. Unmapped active usage can optionally be sent through the configured AI capability-inference route.
4. Multiple active dependencies mapped to one capability become duplicate-capability candidates.
5. Phase 3 analysis calculates observed call-site and file impact, ranks observed and curated alternatives, records validation gaps, and persists a migration and rollback plan.
6. The API exposes the results and records optimistic, audited review decisions.

Only a `COMPLETE` snapshot schedules the pipeline. Partial snapshots never stale prior results. A later complete source revision stales earlier capability, duplication, candidate, and recommendation rows.

## Run locally

Start the database, apply migrations, and run one repository directly:

```shell
make backend-up
make database-migrate
make intelligence-run TENANT_ID=<tenant-uuid> REPOSITORY_ID=<repository-entity-uuid>
```

Process automatically queued jobs:

```shell
MAX_JOBS=10 make intelligence-work
```

To enable AI inference only for active dependency usage that has no curated mapping:

```shell
AI_UNMAPPED=1 AI_ROUTE=default MAX_JOBS=10 make intelligence-work
```

Provider credentials remain server-side. AI output must use a known taxonomy capability and only evidence references supplied in the invocation.

## API

- `GET /api/v1/capabilities/taxonomy`
- `GET /api/v1/repositories/{id}/capabilities`
- `POST /api/v1/capability-inferences/{id}/review`
- `POST /api/v1/duplicate-capability-candidates/{id}/review`
- `GET /api/v1/repositories/{id}/modernization-intelligence?limit=50`
- `POST /api/v1/modernization-recommendations/{id}/review`

Tenant identity comes from the authenticated session and is never accepted in a route, query, or body.

## Ranking and limitations

The initial Phase 3 policy is `modernization-ranking/v1`. It selects among dependencies already observed providing the same capability by capability confidence, observed usage share, and evidence completeness. Curated native or package options are exposed with `UNKNOWN` compatibility and cannot outrank an observed option until repository-specific compatibility evidence exists.

Affected call sites come from deterministic dependency-usage summaries. Source files come from evidence locators. Test coverage, dynamic imports, reflection, plugins, generated code, behavior equivalence, and unknown runtime use remain explicit validation gaps. Effort is an explainable ordinal band; it is not a time estimate.

## Retry and recovery

Workers claim jobs with `FOR UPDATE SKIP LOCKED` and a five-minute lease. Failures retry with bounded exponential delay. After the configured maximum attempts the job becomes `FAILED` and a record is written to `dead_letter` with repository replay metadata.

To replay a terminal job after correcting the cause:

```sql
UPDATE intelligence_job
SET status='PENDING', attempt=0, available_at=now(), leased_by=NULL,
    leased_until=NULL, completed_at=NULL, last_error=NULL, updated_at=now()
WHERE id='<job-uuid>' AND status='FAILED';
```

## Verification

```shell
make backend-test
make ai-test
pnpm --filter @stackgraph/shared typecheck
```

The CI workflow additionally creates a fresh PostgreSQL/AGE database, verifies that bootstrap migration checksums match migrations 001–007, seeds and projects the foundation catalog, and runs API tests with the application role so RLS is exercised.
