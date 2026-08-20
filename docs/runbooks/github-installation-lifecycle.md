# GitHub App installation lifecycle runbook

This runbook covers the tenant-scoped GitHub installation control plane: credential-reference registration,
authorized-repository reconciliation, webhook verification and deduplication, and safe installation removal.
Repository content acquisition and scanning continue in
[repository dependency analysis](repository-dependency-analysis.md).

## Security boundary

- StackGraph stores only `connector_account.credential_reference`; registration never accepts a token argument.
- The local runtime resolves `env://GITHUB_INSTALLATION_TOKEN`. Production deployments should provide a
  secret-manager resolver that returns a short-lived installation token on every reconciliation invocation.
- Required minimum permissions are `contents:read` and `metadata:read`.
- Webhook signatures are verified with `X-Hub-Signature-256` before JSON parsing or database writes.
- Signature headers and credential values are never persisted. Webhook bodies are checksum-addressed in the
  tenant evidence store, while `webhook_delivery` retains only safe operational headers and the blob URI.

## 1. Register the installation

The tenant must already exist and be active. For the local environment, expose a short-lived installation token
through the referenced variable:

```shell
export GITHUB_INSTALLATION_TOKEN=ghs_short_lived_value

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

For a production secret provider, invoke the CLI directly and use an approved URI such as
`vault://stackgraph/github/installations/12345678`. The checked-in local resolver supports only `env://`; a
deployment-specific resolver must handle Vault or cloud secret-manager references.

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

## Current deployment boundary

The repository now contains the persistence, reconciliation, HTTP verification, delivery dedupe, and event-routing
services. B-01/A-03 remain partial until a hosted GitHub App callback exchanges installation authorization for a
credential reference, a production secret broker mints/refreshes installation tokens, the scheduler continuously
claims due installation targets, and alerting covers failed/stale deliveries and reconciliation lag.
