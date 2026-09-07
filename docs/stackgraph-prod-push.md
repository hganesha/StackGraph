# StackGraph production push

**Reviewed and implemented:** 2026-08-20

**Implementation branch:** `codex/prod-push`

**Review baseline:** `main` at `37c85dd` (merge of PR #38, pilot readiness gates)

**Companion documents:** [milestone 0–4 balance](../balance-plan.md) · [production deployment](runbooks/production-deployment.md) · [pilot readiness](runbooks/pilot-readiness.md) · [operations SLOs](operations-slo.md)

## Outcome

The repository-owned production push is implemented. StackGraph now has an OIDC login and hardened
session lifecycle, immutable non-root API and web images, a TLS production topology, tagged delivery,
scrapeable operational signals, structured error correlation, per-tenant abuse controls, scheduled
recovery gates, security scanning, and an explicit pilot trust label.

Production acceptance is deliberately separate. It still requires the target organization's IdP and
GitHub App, a representative real tenant, cloud-account durability evidence, and human/security/paging
sign-off. Those are external executions of checked-in runbooks, not missing repository implementation.

## Recommendation ledger

| Recommendation | Repository status | Evidence |
| --- | --- | --- |
| **R1 — OIDC entry point** | **Complete in code** | Authorization Code flow with PKCE S256, signed state, nonce validation, discovery/JWKS verification, safe return paths, IdP group-to-capability and tenant-claim mapping, and a production login page. |
| **R2 — hardened sessions** | **Complete in code** | Short access and rotating refresh sessions carry `kid`, `aud`, `iat`, `exp`, `jti`, and token type. PostgreSQL-backed revocation survives replicas/restarts; production rejects development auth. |
| **R3 — web image** | **Complete** | Next.js standalone multi-stage image, non-root runtime, Compose health check, and same-origin live API/auth configuration. |
| **R4 — production topology** | **Complete for the single-host pilot** | `compose.production.yaml` adds Caddy TLS, internal-only PostgreSQL/MinIO/Prometheus/Alertmanager/Grafana, object versioning/lock/retention initialization, and production-only secrets. |
| **R5 — delivery** | **Complete in code** | Tag workflow publishes API, web, data, discovery, control-loop, and intelligence images with provenance; a protected SSH deployment checks out the exact tag, migrates before rollout, and verifies readiness. |
| **R6 — metrics transport** | **Complete** | Bearer-protected Prometheus `/metrics` exposes the operational snapshot and alert state without an operator shell. |
| **R7 — correlation/error tracking** | **Complete in code** | JSON logs include request ID, actor, tenant, status, and duration; optional Sentry captures production stack traces without default PII. |
| **R8 — alert delivery** | **Complete in code; receiver acceptance pending** | Prometheus rules route by named owner through Alertmanager; `make production-alert-test` injects the acceptance page. Receipt must be confirmed in the target alert system. |
| **R9 — abuse controls** | **Complete** | Bounded request bodies and shared per-tenant/per-actor fixed-window limits, with a separate lower-cost ceiling for `/ask`. Unknown tenants retain normal authorization semantics. |
| **R10 — external evidence** | **Execution pending** | The automation and runbooks exist; IdP/GitHub provisioning, real-tenant pilot, cloud KMS recovery, and human acceptance require target accounts and people. |
| **R11 — pilot bar** | **Complete** | Modernization recommendations are explicitly labelled investigative during the pilot, including application and technology detail surfaces. |
| **R12 — strong scheduled gates** | **Complete** | Fresh-database integration and recovery drills run nightly; the synthetic 100-repository gate runs on pull requests. |
| **R13 — repository security** | **Scanning complete; publishing pending an admin decision** | Gitleaks and Trivy high/critical filesystem scanning run on pull requests, `main`, and weekly, and a finding fails the check. SARIF is *not* reaching the Security tab: code scanning is off for this private repository and needs GitHub Advanced Security. Findings are kept as the `trivy-sarif` workflow artifact meanwhile, and each run says which of the two happened. See [Enabling code scanning](#enabling-code-scanning). |
| **R14 — conflict copies** | **Complete** | All exact Finder/iCloud conflict copies were removed; 117 source copies are archived at `/private/tmp/stackgraph-conflict-copies-20260820.tgz`. Canonical files were verified separately. |
| **R15 — read-model split** | **Complete** | Review/admin persistence moved to `read_models_admin.py`; the core store fell from 4,242 to 3,093 lines while retaining its public class boundary. |
| **R16 — stale branches** | **Complete** | The three squash-merged `claude/ui-*` remote refs for PRs #4, #13, and #15 were verified and deleted. |

## Authentication and session boundary

Production uses a generic OpenID Connect provider. `/api/v1/auth/login` performs discovery and starts
Authorization Code + PKCE; the callback validates issuer, audience, signature, nonce, and state before
mapping the configured tenant and group claims. Access and refresh sessions use secure, HttpOnly,
SameSite=Lax cookies. API routes remain the authorization source of truth; the web middleware only
provides the login redirect experience.

Refresh tokens are single-use. Rotation first records the old `jti` under tenant RLS, so concurrent
replay loses atomically. Logout revokes both access and refresh tokens. Keyrings allow staged rotation:
issue with the active `kid`, retain prior keys through the refresh TTL, then remove them.

## Deployment and delivery boundary

The production overlay is intentionally scoped to a single-host pilot:

- Caddy owns ports 80/443, automatic TLS, public security headers, API/UI routing, and the bounded
  GitHub webhook ingress. Database, object storage, and observability services expose no host ports.
- The API production service resets all development source mounts and the reload command. Published
  runtime images are immutable and run without root.
- MinIO is initialized with versioning, Object Lock, and governance retention. It validates the
  application adapter locally; cloud KMS, replication, and cross-account recovery remain acceptance work.
- Tagged releases publish every continuous runtime image, attach GitHub provenance attestations, pin
  the deployment host using independently verified SSH known-hosts, migrate before application rollout,
  and fail unless `/health/ready` succeeds.

The reproducible operator path is documented in
[production-deployment.md](runbooks/production-deployment.md). `.env.production` is host-local and
ignored; `.env.production.example` is the required-variable contract.

## Operations and abuse boundary

Prometheus scrapes the eleven signals in [operations-slo.md](operations-slo.md). Each emitted alert
series carries its signal, threshold, and owner; alert rules route critical breaches and missing metrics
to Alertmanager. Grafana has a provisioned Prometheus datasource. The target receiver must still prove
delivery using `make production-alert-test`.

Every API response carries `X-Request-ID`. Completion logs are structured JSON with tenant and actor
context, while unexpected exceptions can be correlated in Sentry. Metrics require a dedicated bearer
secret and are excluded from the public OpenAPI contract.

Request bodies are rejected above the configured byte limit, including chunked bodies. General and
`/ask` limits are independently configurable and stored in tenant-RLS PostgreSQL counters so multiple API
replicas enforce the same window. Tests cover oversized requests, per-actor exhaustion, and the unknown-
tenant edge case found by the fresh-database matrix.

## Verification record

| Gate | Result on 2026-08-20 |
| --- | --- |
| Canonical contracts and fixtures | **Pass — 20 fixtures/registries valid** |
| Generated OpenAPI/type stability | **Pass — identical hashes before/after generation; 39 paths/49 operations** |
| Root TypeScript checks | **Pass — 4 workspaces** |
| Python compilation | **Pass** |
| API unit/auth/config suite | **Pass — 61 passed, 9 intentionally skipped without a database** |
| Fresh PostgreSQL/AGE integration matrix | **Pass — 70 API + 46 data + 58 discovery tests** |
| Production web build | **Pass — 103 kB shared, 155 kB heaviest route** |
| CSS and bundle budget | **Pass** |
| Browser/accessibility matrix | **Pass — 12 across Chromium, Firefox, WebKit, and mobile; 4 live-only checks skipped by design** |
| Production Compose resolution | **Pass with the `pipeline` profile and example environment** |
| Production release images | **Pass — all six definitions build; API/web declare non-root production users** |
| Object storage and deploy migration smoke | **Pass — versioning + 30-day governance lock; migrations 001–014 skipped as current** |
| Workflow YAML and deployment shell syntax | **Pass** |
| Backup/restore and AGE rebuild | **Pass — `artifacts/recovery/recovery-20260820155559.json`** |
| Synthetic 100-repository gate | **Pass — 100 complete, 1,000 facts, 200 findings, 100% evidence, zero failures** |

## Enabling code scanning

The security workflow produces SARIF and tries to publish it to the Security tab. That upload has
never succeeded: publishing requires code scanning to be enabled on the repository, and because
this repository is private that means GitHub Advanced Security, which is a paid add-on rather than
a switch. The upload returned `Code scanning is not enabled for this repository` and failed the
whole job, which is why `repository-scan` has been red on `main` independently of any finding.

The scans themselves never depended on it. Gitleaks and Trivy run locally in the job and a finding
fails the check, so the gate works today. What was lost was the *publishing* — and a security check
that goes red for a billing reason is one people learn to ignore, taking the next real finding with
it. So publishing is now attempted, allowed to fail, and reported either way; the findings are kept
as a workflow artifact regardless.

To publish to the Security tab, a repository admin enables it:

1. **Settings → Advanced Security** — enable GitHub Advanced Security for the repository. This is
   billed per active committer; it is a spending decision, not a configuration one.
2. **Settings → Code security → Code scanning** — leave default setup off. The workflow uploads its
   own SARIF, and default setup would run a second, redundant analysis.
3. Re-run the Security workflow. The job summary will then say the SARIF was published instead of
   naming the artifact.

Nothing else changes: the same findings gate the same check before and after. Making the repository
public would also enable code scanning at no cost, which is a different decision with different
consequences and is not recommended here.

## What is left for production acceptance

1. Provision the real OIDC client and claims, create the GitHub App, register the TLS callback/webhook,
   bind an installation to a tenant, and capture a push-to-live-UI trace.
2. Replace local MinIO evidence with the selected cloud account's versioned/Object-Locked bucket, KMS
   policy, replication target, and authorized-deletion role; run object and key recovery.
3. Run `make pilot-live TENANT_KEY=<key>` after reconciling at least 100 representative repositories and
   archive provider latency, UI latency, and reviewer-value evidence with the report.
4. Complete keyboard/screen-reader sessions, penetration and dependency review, privacy/retention approval,
   and confirm that `make production-alert-test` reaches the named human owner.

The former long-lived developer database migration-005 blocker is resolved: the known checksum is accepted
only after structural verification, and migration 014 repairs its legacy global package-analysis uniqueness
rule without rewriting the old ledger. Unknown checksum drift still fails closed.

None of these items can be honestly completed from a repository-only session. They are the remaining
deployment acceptance checklist; there is no unimplemented production-push recommendation hidden behind
them.
