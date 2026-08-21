# ADR 004: Manual GitHub installation binding is a bounded pilot fallback

- Status: Accepted for pilot only
- Date: 2026-08-21
- Owners: Platform and Security

## Decision

Manual entry of a GitHub App installation ID is acceptable for the pilot only when all of the
following controls are enforced:

1. Only a tenant administrator can bind an installation.
2. StackGraph mints installation tokens from the operator-owned GitHub App private key; the UI
   never accepts a PAT, installation token, private key, or other raw credential.
3. The installation ID is globally unique across tenants, is verified by an installation-token
   request before production use, and is reconciled against repositories visible to that token.
4. The bind, disable, and removal operations are tenant-scoped and written to `admin_audit_log`.
5. A failed or revoked installation is disabled and surfaced as needing reauthorization.
6. The hosted GitHub App setup callback is the required production onboarding path. Manual
   binding must be feature-flagged off after that callback is deployed and verified.

The existing `POST /api/v1/admin/github/installations` path satisfies the identity, tenancy,
reference-only credential, uniqueness, scheduling, and audit boundaries. It does not prove that
the acting administrator initiated the provider-side installation flow. That residual social
binding risk is accepted for a named, closely supported pilot cohort and is not accepted for
self-service or general availability.

## Consequences

- Pilot onboarding can proceed without blocking on the hosted setup callback deployment.
- Pilot operators must independently verify the installation owner and tenant before binding.
- General availability is blocked until the signed setup/OAuth callback binds provider state to
  the authenticated tenant without manual transcription.
- The manual endpoint remains useful as an operator recovery tool, but should be unavailable to
  ordinary tenant administrators once hosted onboarding is live.

## Exit gate

Deploy the GitHub App setup callback implemented by
`POST /api/v1/admin/github/installations/setup` and its callback route, enable GitHub user
authorization during installation, capture an end-to-end installation trace, test cross-tenant
and replay rejection, then set `STACKGRAPH_GITHUB_MANUAL_BINDING_ENABLED=false`.
