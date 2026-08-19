# StackGraph contract gate v1

The files under `contracts/v1` are the frozen boundary that lets ingestion, API, intelligence, and UI work proceed independently. Changes within v1 must be backward compatible. A breaking field, identity, predicate, or semantic change requires `contracts/v2` and a migration plan.

## Ownership and consumption

| Artifact | Producer | Consumers |
|---|---|---|
| `ontology.registry.json` | data-contract owner | scanners, normalization, SQL seeds, AGE projection, API |
| `schemas/fact.schema.json` | normalization | persistence, intelligence, evidence UI |
| `schemas/scanner-*.schema.json` | scanner platform | repository scanners and ingestion worker |
| `schemas/raw-observation.schema.json` | source adapters | replay and normalization workers |
| `openapi.json` + `schemas/read-models.schema.json` | API | fixture-first UI and API tests |
| `fixtures/*` | contract owner | every lane's contract tests and UI mocks |

The old files in `schemas/` are retained only as compatibility pointers. New code imports `contracts/v1` directly.

## Frozen semantic rules

- Public packages use purl without a version; public package versions use purl with a normalized version.
- Package source is a separate identity dimension. Every npm dependency records its normalized registry origin and resolution method. Private/custom-registry entities are tenant-scoped and use `registry:<registry-key>:<purl>` as their canonical key until an explicit identity assertion proves equivalence to a public package.
- GitHub repositories use `github:repo:<immutable-provider-id>`; mutable names and URLs are aliases.
- Global public entities have `tenant_id IS NULL`. Tenant observations and usage facts always carry a tenant.
- A fact contains exactly one of `object_entity` or `object_value` and at least one evidence item.
- `logical_key` excludes source revision and identifies the assertion across snapshots. For npm facts it includes normalized registry origin. `idempotency_key` additionally includes source revision and extractor version and identifies one immutable emitted assertion.
- `COMPLETE` publication closes prior current assertions for the same target and extractor. `PARTIAL` publication never closes earlier assertions.
- PostgreSQL is authoritative; `projection_outbox` is the only supported handoff to AGE.
- UI responses are read models, not raw tables. Graph responses render no more than 50 real nodes and carry truncation/aggregate metadata.
- Confidence labels are `HIGH >= 0.85`, `MEDIUM >= 0.60`, otherwise `LOW`; decimals remain present in the read model.
- Tenant identity comes from authentication/session context. It is never accepted as an API query or body field.
- Registry credentials are referenced only by `connector_account.credential_reference`. Scanner requests contain an origin allowlist and must set `redact_auth: true`; facts, evidence, raw metadata, and read models must never contain tokens, passwords, or credential-bearing URLs.

## npm registry resolution

For each npm-ecosystem dependency found by npm, Yarn, or pnpm, resolve and preserve the effective registry using lockfile data plus project/workspace configuration and explicitly supplied connector settings. Never inherit configuration from the scanner worker's host account. Record `LOCKFILE`, `NPMRC_SCOPE`, `NPMRC_DEFAULT`, `NPM_DEFAULT`, `EXPLICIT_TARBALL`, or `UNKNOWN` as the resolution source. Do not infer the public registry from the `npm` purl alone.

The default npm registry in a lockfile means the currently configured registry; an explicitly custom registry remains pinned. `publishConfig.registry` controls publishing and must not be treated as dependency-install resolution. `.npmrc` files are evidence artifacts, but authentication fields are redacted before hashing excerpts or emitting locators. Registry fetchers enforce the request allowlist, reject redirects outside it, and allow insecure HTTP only for an explicitly enabled localhost development endpoint.

## Transaction boundary for ingestion

1. Store the raw observation or source artifact.
2. Create a `source_snapshot` in `STAGED` state.
3. Resolve/upsert canonical entities, then insert immutable facts and evidence in one transaction.
4. Call `publish_source_snapshot(snapshot_id)` in that transaction.
5. Commit. AGE and intelligence consumers claim `projection_outbox` rows independently.

Facts without evidence fail at commit. Object kinds that disagree with the predicate registry fail before write. Replaying the same adapter output is suppressed by `idempotency_key`.

## Local verification

Run `npm install` once in `stackgraph-foundation`, then `npm run validate`. This validates the ontology and all golden ingestion/UI fixtures against JSON Schema Draft 2020-12.
