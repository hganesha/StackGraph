# GitHub App installation lifecycle runbook

This runbook covers the tenant-scoped GitHub installation control plane: credential-reference registration,
authorized-repository reconciliation, webhook verification and deduplication, and safe installation removal.
Repository content acquisition and scanning continue in
[repository dependency analysis](repository-dependency-analysis.md).

## Security boundary

- StackGraph stores only `connector_account.credential_reference`; registration never accepts a token argument.
- The normal `github-app://installation/<id>` runtime creates a short-lived RS256 App JWT, mints an installation
  token, and refreshes the in-memory cache before expiry. The App private key must come from the deployment secret
  broker through `GITHUB_APP_PRIVATE_KEY` or a broker-mounted `GITHUB_APP_PRIVATE_KEY_FILE`.
- `env://GITHUB_INSTALLATION_TOKEN` remains a local-development fallback for an already short-lived token.
- Required minimum permissions are `contents:read` and `metadata:read`.
- Webhook signatures are verified with `X-Hub-Signature-256` before JSON parsing or database writes.
- Signature headers and credential values are never persisted. Webhook bodies are checksum-addressed in the
  tenant evidence store, while `webhook_delivery` retains only safe operational headers and the blob URI.

## 1. Register the installation

The tenant must already exist and be active. Configure the App identity and private key through the local
environment or a secret-broker mount:

```shell
export GITHUB_APP_ID=123456
export GITHUB_APP_PRIVATE_KEY_FILE=/run/secrets/stackgraph-github-app.pem

make github-installation-register \
  TENANT_KEY=acme \
  INSTALLATION_ID=12345678
```

Registration creates or reactivates:

- one tenant-scoped `source_system` with key `github-app`;
- one `connector_account` keyed by `github:installation:<installation-id>`;
- one due `GITHUB_INSTALLATION` target that represents periodic repository-set reconciliation.

GitHub installation IDs are treated as globally assigned. Registering the same installation to another tenant is
rejected. Replaying registration for the same tenant updates the credential reference and permission set without
creating another connector.

The default credential reference is `github-app://installation/<installation-id>`. A deployment secret broker
must inject or mount the App private key; the database never stores the key, App JWT, or installation token.

## 2. Reconcile authorized repositories

```shell
make github-installation-reconcile \
  TENANT_KEY=acme \
  INSTALLATION_ID=12345678
```

Reconciliation requests `/installation/repositories` in bounded 100-item pages and fails the attempt if pagination
is incomplete, duplicated, changes total count mid-read, or exceeds the configured page budget. A successful
complete snapshot:

- creates or refreshes installation-qualified repository targets;
- schedules enabled targets for revision acquisition;
- disables repositories missing from the complete authorized set;
- cancels pending runs for removed repositories without deleting historical snapshots or facts;
- stores the repository-set fingerprint and page/ETag metadata on the installation reconciliation cursor.

Run reconciliation periodically even when webhooks are healthy. Webhooks are low-latency triggers, not the
authoritative repository membership source.

## 3. Receive GitHub webhooks

Set the same webhook secret configured on the GitHub App, then start the receiver:

```shell
export GITHUB_WEBHOOK_SECRET=replace-with-runtime-secret
make github-webhook-up
```

The local endpoint is `http://127.0.0.1:8090/webhooks/github`; expose it through the deployment ingress with TLS.
Configure GitHub to send `push`, `installation_repositories`, `repository`, and `installation` events.

Routing behavior:

- default-branch `push` updates the target's desired immutable revision, cancels superseded pending work, and
  creates one idempotent `WEBHOOK` ingest run;
- non-default-branch pushes are recorded as `IGNORED`;
- repository additions/removals update target availability and make the installation reconciliation target due;
- repository deletion/transfer disables the target and preserves history;
- installation suspension disables the connector/targets and cancels pending runs; unsuspension reactivates only
  the installation reconciliation target so the authorized repository set is re-established before scanning;
- installation deletion revokes the connector, disables its targets, and cancels pending runs;
- signed GitHub `ping` checks are acknowledged without requiring tenant routing;
- unsupported event types/actions are retained as `IGNORED` rather than silently discarded.

A duplicate delivery with the same body replays harmlessly. Reusing a delivery ID for different content is
rejected. The receiver performs only checksum storage and bounded database routing before responding; provider
acquisition remains asynchronous.

Stop the local receiver with:

```shell
make github-webhook-down
```

## 4. Revoke an installation manually

```shell
make github-installation-revoke \
  TENANT_KEY=acme \
  INSTALLATION_ID=12345678
```

Revocation marks the connector `REVOKED`, disables its installation and repository targets, and cancels pending
runs. Running or already-published work is not destructively deleted; its evidence remains available for audit and
tenant lifecycle policy.

## Continuous processing and deployment boundary

The checked-in [`pipeline` profile](continuous-discovery-pipeline.md) continuously claims due installation and
repository targets, recovers expired leases, and connects changed revisions to durable evidence, scanning,
publication, projection, intelligence, and freshness. The remaining deployment boundary is a hosted GitHub App
setup/OAuth callback that binds opaque state to the authenticated tenant and verifies installation ownership,
secret-broker delivery of the App private key, TLS ingress, and routed alerting for failed/stale deliveries and
reconciliation lag.
