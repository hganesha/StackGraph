# StackGraph production push — review, remaining work, and recommendations

**Reviewed:** 2026-08-20
**Baseline:** `main` at `37c85dd` (merge of PR #38, pilot readiness gates)
**Scope:** merged PR history, planning documents, and independent verification of the repository state.
**Companion documents:** [milestone 0–4 balance](balance-plan.md) · [implementation plan](stackgraph-implementation-plan.md) · [lane A/B/D audit](lanes-a-b-d-audit-and-roadmap.md) · [pilot readiness runbook](runbooks/pilot-readiness.md)

---

## Verdict

The product is built and the repository gates are real. Thirty-eight pull requests are merged, none are open,
and the quality bar the planning documents claim is genuinely enforced in CI rather than asserted in prose.

What is missing is not product. It is nearly everything between a green CI run and a service a person can
sign in to. There is no authentication entry point, no container image for the web application, no deployment
topology as code, no delivery pipeline, and no runtime observability surface. The planning documents do not
name these gaps, because each document scoped itself to a lane and no document owns the deployment boundary.

That is the whole of the production push: six blockers, none of which are research problems, and all of which
sit outside the lanes that have been executed so far.

---

## What I verified myself

Two gates were executed against this baseline. Everything else in this document comes from reading the
repository, not from re-running the full suite.

| Check | Command | Result |
| --- | --- | --- |
| Contract and fixture validation | `npm --prefix stackgraph-foundation run validate` | **Pass** — 20 fixtures and registries valid, exit 0 |
| Repository typecheck | `pnpm typecheck` | **Pass** — 4 workspaces, no errors |

Not re-run here (each needs Docker and material wall-clock time): `pnpm build`, `pnpm e2e`, `pnpm perf:budget`,
`make fresh-integration`, `make pilot-100`, `make recovery-drill`, and the Python integration suites. CI runs
all of the first group on every pull request; the last three are **not** in CI, which is a finding in its own
right — see recommendation R12.

### What CI actually enforces

`.github/workflows/api-lane.yml` is the only workflow. It runs four jobs on every pull request and every push
to `main`, and it is stronger than a single-workflow repository usually implies:

- **contracts-and-types** — foundation validation, generated-type drift check against a committed artifact,
  typecheck, production build, CSS lint, and a bundle performance budget.
- **browser-journey** — Playwright against a real production build with a live database, seed, and projection,
  across Chromium, Firefox, and WebKit.
- **python-unit** — byte-for-byte comparison of FastAPI's generated OpenAPI against the canonical contract,
  plus API, seed, intelligence, and enterprise-discovery unit suites.
- **postgres-integration** — the same suites against a migrated PostgreSQL/AGE database, with the API suite
  running under the restricted `stackgraph_app` role so row-level security is exercised, not bypassed.

The OpenAPI drift check and the RLS-role integration run are the two gates most projects skip. Both are here.

---

## What shipped

| Milestone | Status | What backs it |
| --- | --- | --- |
| **0 — Contract hardening** | Complete | 33 route path patterns, generated wire types with a drift gate, 20 contract fixtures, migrations 001–012 in the consolidated schema |
| **1 — Ingestion substrate** | Complete in code | Continuous GitHub, deps.dev, OSV, projection, and intelligence workers; leases, retries, dead letters; persisted per-tenant provider quota state |
| **2 — Vertical estate slice** | Complete in code | GitHub App JWT/token broker, signed and deduplicated webhooks, Docker/Compose/Kubernetes/Terraform *as scanned canonical facts*, content-addressed local and S3 evidence stores |
| **3 — V0 product experience** | Complete | Five primary surfaces plus reviews, health, admin, evidence, graph lenses, and Business Map; WCAG 2.2 axe gate; cross-browser journey |
| **4 — Pilot readiness** | Automated gates complete; deployment pilot pending | Recovery drill, synthetic 100-repository report, `make pilot-live` collector, SLO table with named owners |

Shape of the codebase at this baseline: 35,296 lines of Python, 8,533 lines of TypeScript across 68 files,
32 CSS modules, 22 Compose services, 12 migrations, 38 Python test files, and one end-to-end spec.

One clarification worth making explicitly, because the phrasing in `balance-plan.md` invites the opposite
reading: Milestone 2's "Docker/Compose/Kubernetes/Terraform canonical deployment facts" means StackGraph can
*scan and model* those artifacts in a customer's repositories. It does not mean StackGraph has any of them for
its own deployment. It does not.

**Branch hygiene:** three remote branches report as unmerged to `main` — `claude/ui-architecture-design-plan-5934d4`,
`claude/ui-finding-system`, and `claude/ui-health-admin`. Their pull requests (#4, #13, #15) all merged; the tips
are simply not ancestors after squash. The content is in `main`. These are stale refs to delete, not lost work.

---

## Blockers the planning documents do not name

These are ordered by dependency. Each one independently prevents a person outside the team from using a
deployed StackGraph.

### B1 — There is no way to log in

`apps/api/app/auth.py` has two modes. `development` returns a hardcoded principal holding `admin` capability
with no credential at all. `signed_session` validates an HMAC-SHA256 bearer token — correctly, including
expiry, constant-time comparison, and least-privilege defaulting when the `capabilities` claim is absent.

Nothing issues that token. `create_session_token` exists as a library function with no caller outside tests.
Across all 33 route paths there is no `POST /session`, no `/auth/*`, no OIDC or SAML callback, and no identity
provider integration anywhere in the repository. `GET /session` reads the principal that a token already
established; it cannot create one.

The practical consequence: production runs either wide open in `development` mode, or locked shut in
`signed_session` mode with tokens minted by hand out of band. Neither is shippable. This is the single
largest gap in the repository and nothing in `balance-plan.md`, the pilot runbook, or the A/B/D audit
mentions it.

Related hardening the same work should pick up: the session token carries no `jti`, so it cannot be revoked
before expiry; there is no refresh path; the signing secret has no rotation mechanism or key id; and there is
no audience claim.

### B2 — The web application has no container image

`apps/api/Dockerfile` is well built: a shared base, a development stage, and a runtime stage that creates a
system user, chowns application files, and drops to non-root.

`apps/web` has no Dockerfile at all, and no `web` service appears in `compose.yaml`. The frontend can be built
(`pnpm build` runs in CI) but there is no artifact to deploy and no defined way to serve it. Whatever runs the
API in production has no counterpart for the UI.

### B3 — There is no deployment topology as code

`infrastructure/` contains database init scripts, twelve migrations, and smoke tests — and then three
directories that are nothing but `.gitkeep`:

```
infrastructure/observability/.gitkeep
infrastructure/local/.gitkeep
infrastructure/object-storage/.gitkeep
```

There is no Terraform, no Kubernetes manifest, no Helm chart, and no production Compose overlay anywhere in
the repository. The only orchestration is `compose.yaml`, which is a 22-service development topology with
plaintext default credentials and no TLS.

The pilot runbook instructs the operator to deploy "from the checked-in Compose topology or its production
equivalent." That equivalent does not exist, and the runbook's other prerequisites — HTTPS for the GitHub
webhook and setup callback, secret-broker delivery of the App private key — have nowhere to be configured.

### B4 — There is no delivery pipeline

CI validates pull requests. Nothing builds or publishes images, tags releases, runs migrations against a
deployed environment, promotes between environments, or deploys. Every production change would be a manual
sequence performed from someone's laptop, against infrastructure that does not yet exist (B3).

The migration runner is a Compose service invoked as `docker compose run --rm migrate`. Making that a
deploy-time step with ordering guarantees relative to the API rollout is unstarted work.

### B5 — Operational signals are defined but not delivered

`docs/operations-slo.md` is genuinely good: eleven signals, explicit alert thresholds, and a named owner and
response for each. The gap is the delivery mechanism.

The signals are produced by `python -m stackgraph_data.operations`, a CLI that prints a JSON snapshot. The
document says deployments "should scrape the JSON at least once per minute." There is nothing to scrape — no
`/metrics` endpoint, no exporter, no push gateway. Nor is there distributed tracing, structured JSON logging
(the API uses plain `logging`), or error tracking. The API's entire runtime dependency set is six packages;
none is an observability library.

What does exist and is correct: `/health/live` and `/health/ready`, with readiness checking connectivity, AGE
installation, and schema presence, returning 503 when not ready. Also a request-ID middleware that honors an
inbound `X-Request-ID` and echoes it on the response and in every error payload — the right foundation for
correlation once there is somewhere to correlate.

### B6 — The API has no abuse controls

No rate limiting, no per-tenant quota, no request body size limit, no concurrency cap. `POST /ask` reaches an
LLM provider and `STACKGRAPH_AI_ASK_MAX_EVIDENCE_CHARS` bounds the evidence sent per call, but nothing bounds
calls per actor per minute. For an authenticated internal pilot this is a low-severity risk; for anything
internet-facing it is not.

---

## Gaps the planning documents already name

These are correctly identified in `balance-plan.md` and the pilot runbook, and they are genuinely
environment-bound — they cannot be closed by writing code in this repository.

1. **Real GitHub lifecycle.** Provision the App, host the authenticated installation/setup callback with
   opaque state and installation-ownership verification, deploy TLS webhook ingress, bind an installation to a
   tenant, capture a push-to-live-UI trace. The runbook's warning is worth repeating: GitHub's setup-URL
   `installation_id` is not trustworthy on its own and must be bound to the authenticated tenant.
2. **Cloud durability.** Provision the bucket with versioning and Object Lock, KMS key policy, replication, and
   an authorized-deletion role; then run the account-specific object and key recovery exercise. The `S3EvidenceStore`
   adapter supports all of this; no account has been configured.
3. **Representative pilot.** `make pilot-live TENANT_KEY=<key>` against 100+ real repositories, archiving the
   JSON report alongside provider latency, UI latency, and reviewer-value observations.
4. **Human and security sign-off.** Keyboard and screen-reader sessions with target users, penetration and
   dependency review, privacy and retention approval, and alert routing and paging tests.
5. **Local migration ledger drift.** The long-lived developer database reports a migration 005 checksum
   mismatch from an earlier working copy. Fresh schema and CI are green. Back that volume up and recreate it;
   do not rewrite its ledger.

---

## Two things to correct in the documents

### The pilot bar is defined inconsistently

The A/B/D audit's pilot-ready gate requires that "each tenant has an active governed policy and internal
catalog, or recommendations remain explicitly investigative," and that "a reviewed calibration corpus has
documented thresholds and promotion behavior."

Neither exists. Searching the source for governed tenant policy, internal catalog, or calibration corpus
returns only the unrelated `/admin/scan-policy` route. `balance-plan.md` defers all three to Milestone 5 while
simultaneously calling Milestone 4 complete.

Both positions are defensible; holding both is not. Either implement them, or amend the audit's gate and take
the escape hatch it already offers — label recommendations explicitly investigative in the pilot UI. The
second option is cheap and honest, and it should be an explicit decision rather than an unnoticed conflict
between two documents.

### The 100-repository numbers do not mean what they look like

`artifacts/pilot/pilot-100-repositories.json` reports every target passing: 100 complete scans, 1,000 facts,
100% evidence coverage, zero failures. It also reports a p95 per-repository scan of 0.002 seconds and 0.16
seconds total for all 100 repositories.

Those timings prove the scanner's in-process path never touched a network, a database, or a provider. The
artifact says so plainly in its own `limitations` field, and that honesty is the right instinct. But the number
`time_to_first_five_findings_seconds: 0.007553` sits in the same file as the target
`first_five_findings_under_20_minutes: true`, and anyone reading quickly will carry away a latency claim the
drill cannot support.

Treat `pilot-100` as what it is — a correctness and throughput regression gate for the scanner. The
20-minute claim is established by `make pilot-live` against a real tenant, and only there.

---

## Recommendations

Four tracks. Tracks 1 and 2 are the production push proper and are strictly sequential in their internal
ordering; track 3 can run in parallel once track 1 lands; track 4 is opportunistic.

### Track 1 — Make it deployable and reachable

| | Recommendation | Done when |
| --- | --- | --- |
| **R1** | Build the authentication entry point. Prefer OIDC against the pilot organization's identity provider over a bespoke login; map IdP groups onto the existing `view / review / execute / admin` ladder, which is already correct and enforced server-side. | A user reaches a StackGraph URL, authenticates against the IdP, and receives a session without anyone minting a token by hand. |
| **R2** | Harden the session alongside R1: add `jti` and a revocation check, a refresh path, a key id on the signature for rotation, and an audience claim. Delete `development` auth mode from any image that can be built for production, or fail startup when `STACKGRAPH_AUTH_MODE=development` and `STACKGRAPH_ENVIRONMENT=production`. | A production image cannot start in a mode that grants `admin` without a credential. |
| **R3** | Add `apps/web/Dockerfile` using the Next.js standalone output, mirroring the API image's non-root runtime stage. Add a `web` service to Compose. | `docker compose up web` serves the built UI. |
| **R4** | Commit one production topology. Pick the smallest thing that fits the pilot: a Compose overlay with a TLS-terminating reverse proxy is legitimate for a single-tenant pilot and is days of work; a Helm chart is right only if the pilot lands on an existing cluster. Do not build both. Fill `infrastructure/observability` and `infrastructure/object-storage` while you are there. | The pilot environment is reproducible from the repository, and the runbook's "production equivalent" resolves to a real path. |
| **R5** | Add a delivery workflow: build and publish API and web images on tag, run migrations as an ordered deploy step, deploy, and verify `/health/ready` before completing. | A tagged commit reaches the pilot environment without manual steps. |

### Track 2 — Make it operable

| | Recommendation | Done when |
| --- | --- | --- |
| **R6** | Expose the operations snapshot as a scrapeable endpoint, or push it to whatever the deployment already runs. The metrics logic exists; only the transport is missing. | The eleven signals in `operations-slo.md` are queryable without running a CLI in a container. |
| **R7** | Add structured JSON logging keyed by the existing request ID, and error tracking. The correlation identifier is already threaded through middleware and every error payload — this is wiring, not design. | A production error can be traced from the user's request ID to a stack trace. |
| **R8** | Wire each SLO threshold to its named owner and test the paging path. The runbook already lists this under human acceptance; it depends on R6. | A deliberately tripped threshold pages the right person. |
| **R9** | Add rate limiting and a request body size limit, per-tenant, with `POST /ask` bounded separately given its provider cost. | A single actor cannot exhaust provider budget or database connections. |

### Track 3 — Close the external evidence gaps

R10. Execute the five environment-bound items listed above, in the runbook's order: GitHub App provisioning
and TLS ingress first, then the evidence bucket and its recovery exercise, then `make pilot-live` against the
real tenant, then the failure and recovery session, then human sign-off. The instrumentation for all of this
is already written; what remains is provisioning and running it.

R11. Decide the pilot bar conflict described above before the pilot starts, and record the decision in
`balance-plan.md` so the two documents agree.

### Track 4 — Tighten the gates and clean up

| | Recommendation | Why |
| --- | --- | --- |
| **R12** | Add `make fresh-integration` and `make recovery-drill` to CI on a nightly schedule, and `make pilot-100` per pull request. | Three of the strongest gates in the repository currently run only when someone remembers to run them. |
| **R13** | Add dependency vulnerability scanning and secret scanning to CI. | A platform whose product claim is estate vulnerability intelligence should scan itself. |
| **R14** | Delete the 134 Finder and iCloud conflict copies from the working tree. | They are correctly gitignored and excluded from test and migration discovery, but they still sit beside canonical sources — including `infrastructure/database/migrations/004_ai_prompt_catalog 2.sql`. The eventual failure is someone editing the wrong file. |
| **R15** | Split `apps/api/app/read_models.py` (4,242 lines, ~197 KB) along its read-model boundaries. | It is the widest file in the repository and every API change touches it. This is a review-velocity cost that compounds. |
| **R16** | Delete the three stale remote branches. | Their content is merged; the refs mislead. |

---

## Sequencing

R1 → R3 → R4 → R5 is the critical path, and R1 is the long pole. Nothing in track 3 produces a valid pilot
result before R1 lands, because "an authenticated StackGraph tenant bound to the GitHub installation" — the
runbook's own prerequisite — presumes authentication exists.

Track 2 can be built alongside track 1 and must land before the pilot takes real traffic. Track 4 is
independent of everything and can absorb spare capacity at any point.

The honest summary for a stakeholder: the product is done and the engineering discipline behind it is
unusually good for this stage. The remaining work is a platform-engineering push, not a product push, and it
is measured in weeks rather than months because none of it is unsolved.
