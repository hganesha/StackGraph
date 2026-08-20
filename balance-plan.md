# StackGraph milestone 0–4 balance

**Revisited:** 2026-08-20
**Branch baseline:** `codex/models-selection` at `25fe06f`, including the current working tree
**Source plan:** [StackGraph implementation plan](docs/stackgraph-implementation-plan.md)

This balance supersedes the 2026-08-19 A/B/D audit for milestone status; that document remains a historical
record of the earlier baseline.

## Outcome

Milestones 0–4 are now complete at the repository/code-verification boundary. The implementation has a
reproducible contract and type baseline, a continuous GitHub → scan → enrichment → projection → intelligence
pipeline, production credential and evidence-storage adapters, all V0 product surfaces, a live browser gate,
operational SLOs, recovery automation, and measured 100-repository synthetic evidence.

Production acceptance is not inferred from local evidence. A real GitHub installation, TLS ingress, cloud
object-store/KMS policy, and representative 100+ repository tenant still have to be exercised in the target
deployment. Those environment gates are listed explicitly below.

| Milestone | Repository status | Evidence |
| --- | --- | --- |
| **0 — Contract hardening** | **Complete** | FastAPI-generated canonical OpenAPI covers 35 path patterns/40 operations; generated TypeScript wire types; byte-for-byte drift check; green root typecheck/build; 20 contract fixtures; corrected fresh-schema PL/pgSQL; migration 010 included in consolidated schema; atomic production seed cohort with per-row provenance. |
| **1 — Running ingestion substrate** | **Complete in code and fresh-stack integration** | Continuous GitHub, deps.dev, OSV, projection, and intelligence workers; database health checks; leases/retries/dead letters; dual deps.dev/OSV fan-out; fresh database integration passes without skips; restart/expired-lease behavior is tested. |
| **2 — First vertical estate slice** | **Complete in code** | Short-lived GitHub App JWT/token broker and cache; signed/deduplicated webhooks; repository lifecycle; Docker/Compose/Kubernetes/Terraform canonical deployment facts; `.tf` acquisition; attested runtime-observation contract/import adapter; content-addressed local and S3 evidence stores. |
| **3 — V0 product experience** | **Complete** | All five primary surfaces plus reviews, health, admin, evidence, graph lenses, and Business Map; generated API boundary; production browser journey across Chromium, Firefox, WebKit, and mobile; WCAG 2.2 serious/critical axe gate, keyboard skip/navigation, reduced-motion, and responsive checks. |
| **4 — Pilot readiness** | **Repository gate complete; deployment pilot pending** | Operational SLO snapshot and named owners; backup/restore plus AGE rebuild drill; failure matrix; 100-repository deterministic pilot produced 1,000 facts, 200 findings, and 100% evidence coverage with zero failures. A representative external tenant is still required for production acceptance. |

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
  migration 011. The new `make fresh-integration` gate deletes its uniquely named verification database.
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
  3100 across Chromium, Firefox, WebKit, and mobile. CI runs the same journey against the live API/data stack.
- Axe checks WCAG 2 A/AA, 2.1 A/AA, and 2.2 AA serious/critical violations on every primary surface.
- `python -m stackgraph_data.operations` emits queue age, expired lease, dead-letter, projection, webhook,
  freshness, intelligence, AI cost, and AI latency metrics with thresholds and owners.
- `make recovery-drill` restores a PostgreSQL custom-format backup, verifies authoritative counts, destroys and
  rebuilds AGE from outbox state, writes a JSON artifact, and removes only its ephemeral databases.
- `make pilot-100` scans a deterministic polyglot/deployment workload and writes
  `artifacts/pilot/pilot-100-repositories.json` with explicit pass/fail targets and limitations.

## Verification record

| Gate | Result |
| --- | --- |
| Contract validation | **20 fixtures/registries valid** |
| OpenAPI implementation drift | **Byte-for-byte identical** |
| Root typecheck | **Passed — 4 workspaces** |
| Production web build/CSS/bundle | **Passed — 103 kB shared, 154 kB heaviest route** |
| API unit suite | **58 passed, 9 intentional integration skips** |
| Data-platform unit suite | **35 passed, 2 intentional integration skips** |
| Enterprise unit suite | **50 passed, 6 intentional database skips** (56 total) |
| Empty-database API integration | **67 passed, no skips** |
| Empty-database data integration | **35 passed, no skips** |
| Empty-database enterprise integration | **56 passed, no skips** |
| Production browser matrix | **8 passed across Chromium, Firefox, WebKit, and mobile** |
| Backup/restore + AGE rebuild | **Passed; JSON recovery artifact written** |
| Synthetic 100-repository pilot | **Passed; 100 complete scans, 1,000 facts, 200 findings, 100% evidence coverage, 0 failures** |

Durable outputs: [100-repository pilot](artifacts/pilot/pilot-100-repositories.json) and
[database/AGE recovery drill](artifacts/recovery/recovery-20260820133853.json).

## What is left before production acceptance

These are deployment or representative-data gates, not missing hidden implementation claims:

1. **Real GitHub lifecycle:** provision the GitHub App, host the installation/setup callback and TLS webhook
   ingress, bind a real installation to a tenant, and capture a push-to-live-UI trace with provider timestamps.
2. **Cloud durability:** provision the S3-compatible bucket with versioning/Object Lock, KMS key policy,
   replication, authorized deletion role, and run the account-specific object/key recovery exercise.
3. **Representative pilot:** run the same gates on 100+ real repositories and record GitHub/API quota,
   deps.dev/OSV latency, time to first five material findings, projection lag, API/UI latency, and reviewer value.
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
make recovery-drill
make operations-snapshot
```
