# StackGraph milestone 0–4 balance

**Revisited:** 2026-08-20
**Branch baseline:** `codex/pilot-readiness` from `origin/main` at `4fbdda8`, including this branch's pilot commit
**Source plan:** [StackGraph implementation plan](docs/stackgraph-implementation-plan.md)

This balance supersedes the 2026-08-19 A/B/D audit for milestone status; that document remains a historical
record of the earlier baseline.

## Outcome

Milestones 0–3 are complete at the repository/code-verification boundary, and Milestone 4 now has an automated
repository gate plus a live representative-tenant measurement gate. The implementation has a
reproducible contract and type baseline, a continuous GitHub → scan → enrichment → projection → intelligence
pipeline, production credential and evidence-storage adapters, persisted provider quota state, all V0 product
surfaces, cross-browser failure/theme gates, operational SLOs, recovery automation, measured 100-repository
synthetic evidence, and a machine-readable live-pilot report.

Production acceptance is not inferred from local evidence. A real GitHub installation, TLS ingress, cloud
object-store/KMS policy, and representative 100+ repository tenant still have to be exercised in the target
deployment. Those environment gates are listed explicitly below.

| Milestone | Repository status | Evidence |
| --- | --- | --- |
| **0 — Contract hardening** | **Complete** | FastAPI-generated canonical OpenAPI covers 35 path patterns/40 operations; generated TypeScript wire types; byte-for-byte drift check; green root typecheck/build; 20 contract fixtures; corrected fresh-schema PL/pgSQL; migration 010 included in consolidated schema; atomic production seed cohort with per-row provenance. |
| **1 — Running ingestion substrate** | **Complete in code and fresh-stack integration** | Continuous GitHub, deps.dev, OSV, projection, and intelligence workers; database health checks; leases/retries/dead letters; dual deps.dev/OSV fan-out; persisted tenant-scoped GitHub quota/reset/backoff state; fresh database integration passes without skips; restart/expired-lease behavior is tested. |
| **2 — First vertical estate slice** | **Complete in code** | Short-lived GitHub App JWT/token broker and cache; signed/deduplicated webhooks; repository lifecycle; Docker/Compose/Kubernetes/Terraform canonical deployment facts; `.tf` acquisition; attested runtime-observation contract/import adapter; content-addressed local and S3 evidence stores. The hosted installation callback remains a deployment task. |
| **3 — V0 product experience** | **Complete** | All five primary surfaces plus reviews, health, admin, evidence, graph lenses, and Business Map; generated API boundary; production browser journey across Chromium, Firefox, WebKit, and mobile; WCAG 2.2 serious/critical axe gate, keyboard skip/navigation, reduced-motion, explicit dark/light, responsive, and injected source-failure checks. |
| **4 — Pilot readiness** | **Automated repository/live gates complete; deployment pilot pending** | Explicit Pass A/Pass B timing; operational SLO snapshot and named owners; backup/restore plus AGE rebuild drill; failure matrix; deterministic 100-repository report; and `make pilot-live` for database, quota, RLS, evidence, projection, source, API-latency, and bounded-graph measurements. A representative external tenant and human sign-off are still required. |

## What was built in this pass

### Trustworthy baseline

- CSS-module and Node environment declarations make root TypeScript checks deterministic.
- Finder/iCloud conflict copies are excluded from builds, tests, migration discovery, and Git.
- API tests have strict pytest configuration and a valid default tenant.
- `scripts/export_openapi.py` makes the API implementation the OpenAPI source; CI compares its output with
  `stackgraph-foundation/contracts/v1/openapi.json` byte for byte.
- `scripts/generate_contract_types.mjs` generates `packages/shared/src/contracts/openapi.generated.ts`; curated
  UI read models remain an intentional application facade.
- The authoritative schema now succeeds from an empty PostgreSQL database and includes every table through
  migration 012. The new `make fresh-integration` gate deletes its uniquely named verification database.
- `stackgraph-foundation/seed/PROVENANCE.md` and `production-cohort.json` establish durable provenance and an
  atomic first cohort while retaining original compound groups only as curation provenance.

### Continuous discovery and production boundaries

- Scanner publication creates both deps.dev and OSV targets for newly observed public package versions.
- OSV has a continuous lease/poll worker and is part of `pipeline-up`, `pipeline-down`, and health/log commands.
- The GitHub App broker creates RS256 JWTs, mints one-hour installation tokens, refreshes them before expiry,
  validates installation binding, and never persists or logs the token. `env://` remains a development fallback.
- Repository acquisition and scanning now model Dockerfiles, Compose services, Kubernetes workloads/images/
  environments, and Terraform resources as evidence-backed canonical facts with exact file locators.
- Runtime imports require verified attestation and explicitly preserve absence as `UNKNOWN`.
- `S3EvidenceStore` supports S3-compatible storage, SHA-256 verification, SSE-KMS/SSE-S3, governance retention,
  legal hold, tenant isolation, and deletion authorization. Local storage remains the development adapter.

### Product and pilot verification

- Playwright builds the production Next.js artifact and validates the five primary surfaces on isolated port
  3100 across Chromium, Firefox, WebKit, and mobile. It explicitly audits settled light/dark themes and injects a
  live-client 503 to verify that the failure is announced without losing the application shell.
- Axe checks WCAG 2 A/AA, 2.1 A/AA, and 2.2 AA serious/critical violations on every primary surface.
- `python -m stackgraph_data.operations` emits queue age, expired lease, dead-letter, projection, webhook,
  freshness, intelligence, provider quota, AI cost, and AI latency metrics with thresholds and owners.
- `make recovery-drill` restores a PostgreSQL custom-format backup, verifies authoritative counts, destroys and
  rebuilds AGE from outbox state, writes a JSON artifact, and removes only its ephemeral databases.
- `make pilot-100` scans a deterministic polyglot/deployment workload and writes
  `artifacts/pilot/pilot-100-repositories.json` with Pass A inventory and Pass B refinement timings, explicit
  pass/fail targets, and limitations.
- `make pilot-live TENANT_KEY=<key>` writes a timestamped representative-tenant report covering live repository
  completion, evidence, fifth-finding time, scan latency, projection/source health, GitHub quota state, RLS and
  credential/webhook posture, API p95, and the bounded graph contract. It exits nonzero if any automated target
  fails and never promotes automated success to human production acceptance.

## Verification record

| Gate | Result |
| --- | --- |
| Contract validation | **20 fixtures/registries valid** |
| OpenAPI implementation drift | **Byte-for-byte identical** |
| Root typecheck | **Passed — 4 workspaces** |
| Production web build/CSS/bundle | **Passed — 103 kB shared, 154 kB heaviest route** |
| Empty-database API integration | **67 passed, no skips** |
| Empty-database data integration | **46 passed, no skips** |
| Empty-database enterprise integration | **58 passed, no skips** |
| Production browser fixture matrix | **12 passed across Chromium, Firefox, WebKit, and mobile; 4 live-only checks skipped by design** |
| Injected live-client source failure | **4 passed across Chromium, Firefox, WebKit, and mobile** |
| Backup/restore + AGE rebuild | **Passed; JSON recovery artifact written** |
| Synthetic 100-repository pilot | **Passed; 100 complete scans, 1,000 facts, 200 findings, 100% evidence coverage, 0 failures; Pass A/Pass B p95 each 0.001 s** |
| Live-pilot collector schema check | **Passed against a freshly migrated database** |

Durable outputs: [100-repository pilot](artifacts/pilot/pilot-100-repositories.json) and
[database/AGE recovery drill](artifacts/recovery/recovery-20260820133853.json).

## What is left before production acceptance

The repository now contains the automation needed to measure these gates. The following evidence can only be
created in the target deployment or with representative customer data:

1. **Real GitHub lifecycle:** provision the GitHub App, host an authenticated installation/setup callback with
   opaque state and installation-ownership verification, deploy TLS webhook ingress, bind a real installation
   to a tenant, and capture a push-to-live-UI trace with provider timestamps.
2. **Cloud durability:** provision the S3-compatible bucket with versioning/Object Lock, KMS key policy,
   replication, authorized deletion role, and run the account-specific object/key recovery exercise.
3. **Representative pilot:** run `make pilot-live TENANT_KEY=<key>` after reconciling 100+ real repositories;
   archive the JSON report and record provider latency, UI latency, and reviewer value alongside it.
4. **Human/security sign-off:** complete keyboard and screen-reader sessions with target users, penetration and
   dependency review, privacy/retention approval, and alert routing/paging tests in the deployment.
5. **Local historical volume:** the current long-lived developer database correctly reports migration 005
   checksum drift from an earlier working copy. The fresh schema and CI are green; preserve/backup that volume,
   then recreate it rather than rewriting its migration ledger.

OpenSSF Scorecard and broad public-GitHub polling are explicitly outside the V0 source set. They should be
admitted only after a pilot owner defines target selection, quota budgets, freshness, evidence semantics, and
ranking effects. Milestone 5 calibration, tenant policy, internal-catalog governance, and business/portfolio
intelligence remain the next product milestone rather than being smuggled into the 0–4 completion claim.

## Reproducible commands

```bash
npm --prefix stackgraph-foundation run validate
pnpm typecheck
pnpm build
pnpm lint:css
pnpm perf:budget
pnpm e2e
make fresh-integration
make pilot-100
STACKGRAPH_PILOT_BEARER_TOKEN='<short-lived-session>' make pilot-live TENANT_KEY='<tenant-key>'
make recovery-drill
make operations-snapshot
```
