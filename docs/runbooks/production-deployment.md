# Production pilot deployment

This is the repository-owned deployment boundary for a single-tenant pilot. It combines
`compose.yaml` with `compose.production.yaml`; Caddy terminates public TLS, while PostgreSQL,
MinIO, Prometheus, Alertmanager, and Grafana remain on the internal Compose network.

## Provision

1. Copy `.env.production.example` to `.env.production` on the deployment host and replace every
   placeholder through the host secret broker. Never commit the resulting file.
2. Point `STACKGRAPH_DOMAIN` at the host and allow inbound TCP 80/443. Register the exact OIDC
   callback `https://<domain>/api/v1/auth/callback`.
3. Configure the IdP tenant claim as a StackGraph tenant UUID and map groups using
   `STACKGRAPH_OIDC_GROUP_CAPABILITIES_JSON`.
4. Configure the GitHub App webhook as `https://<domain>/webhooks/github`.
5. Run `make production-config`, then `make production-up`.
6. For automated releases, pre-authorize the deployment host to pull the private GHCR images and
   configure `STACKGRAPH_DEPLOY_SSH_KEY`, `STACKGRAPH_DEPLOY_KNOWN_HOSTS`, `STACKGRAPH_DEPLOY_HOST`,
   and `STACKGRAPH_DEPLOY_USER` in the protected `pilot` GitHub environment. The known-hosts value
   must be pinned from an independently verified host key; the workflow does not trust `ssh-keyscan`.

`production-up` initializes the object-lock bucket, runs migrations before application rollout,
and health-gates the API and web service. Tagged releases publish immutable API, web, data,
discovery, control-loop, and intelligence images with provenance, check out the exact tag on the
deployment host, and execute the same ordered path through `scripts/deploy_production.sh`.

## Session key rotation

Add a new key to `STACKGRAPH_AUTH_SESSION_KEYS_JSON`, set it as
`STACKGRAPH_AUTH_SESSION_ACTIVE_KID`, and deploy. Retain the previous key for at least the refresh
TTL, then remove it in a later deployment. Every token carries `kid`, `aud`, `jti`, and token type;
logout and refresh rotation persist revocations in PostgreSQL.

## Operations and paging

Prometheus scrapes `/metrics` using the Compose secret. Alertmanager groups alerts by the owner in
`docs/operations-slo.md` and sends them to `STACKGRAPH_ALERT_WEBHOOK_URL`. Run
`make production-alert-test` and verify receipt by `platform-on-call` before pilot traffic.
Structured API logs include request ID, actor, tenant, status, and latency. Configure
`STACKGRAPH_SENTRY_DSN` for correlated stack traces.

## Evidence recovery

The local pilot bucket uses versioning, object lock, and default governance retention. Exercise
recovery with a disposable object: record its version ID, delete the current version, restore the
recorded version, and verify its SHA-256 through `S3EvidenceStore`. A cloud deployment must repeat
this with the account KMS key, replication target, and authorized deletion role; local MinIO does
not constitute cloud KMS or cross-account recovery evidence.

## Acceptance boundary

Repository automation cannot provision the organization's IdP/GitHub accounts, select a
representative 100-repository tenant, perform penetration/privacy review, or attest human
screen-reader and paging results. Archive those outputs with `make pilot-live` before marking
production acceptance complete.
