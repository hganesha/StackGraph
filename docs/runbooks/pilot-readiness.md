# Pilot readiness and representative-tenant acceptance

This runbook turns Milestone 4 into two separate, auditable decisions:

1. **Repository readiness** uses deterministic fixtures, fresh databases, browser automation, recovery drills,
   and the synthetic 100-repository scanner workload.
2. **Deployment acceptance** uses a real tenant, a real GitHub App installation, production ingress and object
   storage, at least 100 representative repositories, and named human reviewers.

Passing the first decision never substitutes for the second.

## Prerequisites

- Deploy the API, PostgreSQL/AGE, discovery workers, deps.dev/OSV workers, projection worker, and intelligence
  worker from the checked-in Compose topology or its production equivalent.
- Configure HTTPS for the GitHub webhook and App setup/callback endpoints.
- Configure `GITHUB_APP_ID` and the App private key through the deployment secret broker. Do not create a PAT.
- Configure the evidence bucket with versioning, Object Lock/retention, encryption, and the deployment's recovery
  and authorized-deletion roles.
- Bind an authenticated StackGraph tenant to the GitHub installation and select at least 100 repositories that
  represent the languages, deployment models, sizes, and criticality tiers expected in the pilot.
- Route the operational signals in `docs/operations-slo.md` to their named owners.

GitHub carries an opaque `state` value through its installation URL, but its setup URL's `installation_id` is
not trustworthy by itself. The hosted flow must bind state to the authenticated tenant and verify installation
ownership before registration. StackGraph stores `github-app://installation/<id>`, never the minted token.

## Repository gate

Run the deterministic and failure/recovery gates before touching a pilot tenant:

```shell
npm --prefix stackgraph-foundation run validate
pnpm typecheck
pnpm build
pnpm e2e
make fresh-integration
make pilot-100
make recovery-drill
```

The synthetic report must show both scanner phases, 100 complete scans, five findings within 20 minutes, at
least 99% fact/evidence coverage, and zero failures. The browser run covers Chromium, Firefox, WebKit, mobile,
keyboard navigation, reduced motion, explicit light/dark themes, accessibility, and an injected API failure.

## Start and observe the representative pilot

Start the continuous pipeline with deployment-injected credentials:

```shell
make pipeline-up
```

Confirm the GitHub installation target is active, repository reconciliation has created at least 100 repository
targets, and webhook deliveries are signature verified. Keep the deeper intelligence worker running; Milestone
4 measures time to early evidence while deeper work continues asynchronously.

Run the live gate from a host that can reach both the database and API. With Compose, the API defaults to
`http://api:8000` from the measurement container:

```shell
STACKGRAPH_PILOT_BEARER_TOKEN='<short-lived signed session>' \
make pilot-live TENANT_KEY='<tenant-key>'
```

For a non-Compose API, set `STACKGRAPH_PILOT_API_BASE_URL`. The bearer token must be scoped to the measured
tenant and supplied only through the environment.

The JSON artifact under `artifacts/pilot/` records:

- reconciled repository targets and latest complete scans;
- evidence-backed material findings and time to the fifth finding;
- scan median/p95/max duration and failed runs;
- fact/evidence coverage, projection backlog, source freshness, and asynchronous intelligence backlog;
- persisted GitHub quota/reset/backoff observations;
- API p50/p95/max latency and the 50-real-node bounded graph invariant;
- RLS coverage, credential-reference hygiene, and webhook-signature posture.

The command exits `0` only when every automated target passes. Exit `2` means the artifact is valid but one or
more pilot gates failed.

## Failure and recovery session

During the pilot window, record one controlled exercise for each case:

1. Stop one worker after it acquires a lease; verify retry or dead-letter ownership and no duplicate semantic facts.
2. Inject a provider 429/403; verify `connector_quota`, reset/backoff, Admin status, and operational alerting.
3. Replay a signed webhook delivery; verify deduplication. Submit an invalid signature and verify rejection.
4. Make deps.dev or OSV unavailable; verify source freshness becomes limited/error without erasing prior facts.
5. Run `make recovery-drill`; separately exercise the production bucket/key recovery process.
6. Stop AGE or create projection lag; verify bounded SQL fallback and successful outbox replay.

Do not manufacture provider failures against shared production accounts. Use a controlled proxy, staging tenant,
or provider-approved test mechanism.

## Human acceptance

Automated success leaves `production_acceptance` pending. Named owners must attach:

- keyboard and screen-reader results from target users;
- security, dependency, privacy, retention, and deletion approval;
- reviewer assessment of finding usefulness and false-positive burden;
- alert delivery/paging evidence and recovery timing;
- the exact repository cohort definition and exclusions.

After sign-off, archive the live JSON report, reviewer record, deployment version, runbook deviations, and links
to recovery evidence together. That bundle is the Milestone 4 production acceptance record.
