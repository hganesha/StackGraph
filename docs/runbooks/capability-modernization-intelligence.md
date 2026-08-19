# Capability and modernization intelligence

This pipeline turns a complete repository dependency-usage snapshot into versioned capability inferences,
dependency and code-duplication candidates, eligibility-gated options, evidence-backed impact estimates, and
reviewable migration recommendations.

## Data flow

1. The repository scanner publishes a `COMPLETE` `repository-dependency-usage` snapshot.
2. The publication trigger inserts idempotent capability and `REPOSITORY_MODERNIZATION` jobs for the tenant,
   repository, source revision, and configuration fingerprint.
3. The intelligence worker synchronizes the active capability taxonomy and applies curated mappings. Unmapped active usage can optionally be sent through the configured AI capability-inference route.
4. Multiple active dependencies mapped to one capability become duplicate-capability candidates.
5. The scanner's persisted code-unit fingerprints generate internal or vendored duplication candidates within
   the tenant. Structural similarity is review evidence, not a behavioral-equivalence claim.
6. Native, compatible-upgrade, and approved-internal options are evaluated for capability, API, behavior,
   runtime, license, security, and policy fit.
7. Phase 3 analysis persists affected tests, uncovered call sites, dynamic signals, configuration/build/deploy
   touchpoints, versioned effort points, and migration/rollback plans.
8. The API records audited candidate/recommendation decisions and post-migration validation outcomes, then
   exposes aggregate quality and operations metrics.

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

Reanalyze an unchanged repository after an analyzer, catalog, taxonomy, or policy change:

```shell
make intelligence-requeue TENANT_ID=<tenant-uuid> REPOSITORY_ID=<repository-entity-uuid>
MAX_JOBS=10 make intelligence-work
```

The requeue command is idempotent for the computed configuration fingerprint.

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
- `POST /api/v1/modernization-candidates/{id}/review`
- `POST /api/v1/modernization-recommendations/{id}/review`
- `POST /api/v1/modernization-recommendations/{id}/validation-outcomes`
- `GET /api/v1/intelligence/phase-3/metrics`

Tenant identity comes from the authenticated session and is never accepted in a route, query, or body.

## Policy, eligibility, and limitations

The Phase 3 ranking policy is `modernization-ranking/v2`. An active row in `modernization_policy` supplies
deployed runtime versions, allowed licenses/security statuses, required tags, and explicitly denied option keys.
`modernization_internal_component` supplies tenant-approved internal options and their evidence-backed API and
behavior claims.

Every option persists seven eligibility dimensions. Any failure disqualifies it; missing evidence remains
`UNKNOWN`. The worker emits `REPLACE` only when all dimensions pass, otherwise it emits `INVESTIGATE` or keeps
an observed option. Test links are deterministic static evidence, not runtime coverage proof. Dynamic imports,
reflection, plugins, generated code, and behavior equivalence remain explicit gaps until direct evidence exists.
Effort is an explainable versioned point model mapped to an ordinal band, not a time estimate.

## Feedback and metrics

Candidate reviews record `CONFIRM` or `REJECT`. Recommendation reviews record `ACCEPT` or `DISMISS`; only an
accepted recommendation can receive a validation outcome. Actual call sites, files, effort band, successful
checks, failed checks, and notes feed the Phase 3 metrics endpoint.

Use the endpoint to monitor candidate precision, acceptance, validation success, scope error, effort accuracy,
evidence completeness, queue lag/latency, retry and dead-letter counts, stale results, and available model
latency/cost. Production rollout should attach dashboards and alerts to these fields.

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

The CI workflow additionally creates a fresh PostgreSQL/AGE database, verifies that bootstrap migration
checksums match migrations 001–008, seeds and projects the foundation catalog, and runs API tests with the
application role so RLS is exercised.
