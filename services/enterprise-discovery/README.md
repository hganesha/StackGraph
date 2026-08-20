# GitHub repository acquisition

This service implements the deterministic repository acquisition and analysis slices from the dependency plan. It detects a GitHub repository's current default-branch revision and retrieves the bounded manifest, lockfile, JS/TS source, and Python source set needed by the Phase 0 inventory and Phase 1 usage scanners.

It supports public repositories without authentication and private/customer repositories through a token supplied at runtime. Tokens are sent only in the `Authorization` header and are never written into snapshot metadata, file content metadata, paths, or logs.

## Behavior

- Resolves the repository's immutable GitHub ID and current default branch.
- Resolves the default branch to an exact commit and tree SHA.
- Stops before tree or blob retrieval when `--previous-revision` matches.
- Lists the Git tree, selects known JavaScript/TypeScript and Python dependency and source files, and downloads blobs serially.
- Enforces per-file, total-byte, and file-count limits.
- Marks snapshots `PARTIAL` when GitHub truncates the tree or a configured limit skips a target file.
- Writes an immutable, revision-addressed directory containing retrieved files, `snapshot.json`, and a contract-v1 `raw-observation.json` envelope.
- When an evidence-store root is configured, creates a deterministic tar archive, verifies its SHA-256 checksum, and atomically stores it beneath a hashed tenant prefix. The raw observation then contains a durable `blob_uri` instead of an inline payload.

## Run locally

From this directory:

```shell
python -m stackgraph_discovery.github_snapshot owner/repository \
  --output-dir /tmp/stackgraph-snapshots \
  --tenant-key example-tenant \
  --evidence-store-root /var/lib/stackgraph/evidence
```

For a private repository, expose a short-lived GitHub App installation token or another read-only token through an environment variable:

```shell
GITHUB_TOKEN=... python -m stackgraph_discovery.github_snapshot owner/private-repository \
  --output-dir /tmp/stackgraph-snapshots \
  --installation-id 12345678 \
  --tenant-key example-tenant
```

The token needs read access to repository contents. The default token variable can be changed with `--token-env`; the token itself is never accepted as a command-line argument. `--installation-id` qualifies a customer repository identity by its GitHub App installation. Omit it for a globally shared public OSS repository target.

The local evidence backend uses `stackgraph-evidence://local/...` descriptors so
database records never expose host paths or tenant keys. Content is addressed by
checksum and replays verify the existing object before reuse. Tenant deletion is
available only as an explicit lifecycle operation; the acquisition command never
removes evidence.

Reconciliation can skip unchanged content:

```shell
python -m stackgraph_discovery.github_snapshot owner/repository \
  --output-dir /tmp/stackgraph-snapshots \
  --previous-revision 0123456789abcdef0123456789abcdef01234567
```

The command prints a small JSON result suitable for a scheduler. `UNCHANGED` means only repository metadata and the branch commit were requested; no tree, blobs, or snapshot directory were produced.

Retryable transport, provider, and rate-limit failures exit with status `75` and include `retriable`, HTTP status, retry delay, and rate-limit reset fields when GitHub supplies them. The scheduler owns delayed retry and backoff; this acquisition command does not sleep or run an untracked retry loop.

## Test

```shell
python -m unittest discover -s tests -v
```

Tests use an in-memory HTTP transport and never call GitHub.

## Repository dependency and usage scanner

`stackgraph_discovery.repository_scanner` consumes the frozen scanner request v1
contract. It emits purl-based dependency facts from npm and Python manifests and
locks, then independently records declared, resolved, referenced, statically
reachable, and optionally runtime-observed use. Unused and narrow-use candidates
are emitted only for complete source scans and always include limitations.
When the request contains the snapshot `blob_uri`, checksum, and size descriptor,
every file evidence reference points to its exact archive member.

```shell
python -m stackgraph_discovery.repository_scanner request.json --output result.json
```

`stackgraph_discovery.api_surface` extracts public JS/TS or Python symbols from an
unpacked package artifact. Results are keyed by the exact package purl, artifact
SHA-256 checksum, and analyzer version so a mutable registry response cannot be
confused with a previously analyzed artifact.

```shell
python -m stackgraph_discovery.api_surface /tmp/unpacked-package \
  --ecosystem npm \
  --package-purl pkg:npm/example@1.2.3 \
  --artifact-checksum sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef \
  --output api-surface.json
```

See [the dependency analysis runbook](../../docs/runbooks/repository-dependency-analysis.md)
for the complete acquire, scan, persist, and API-surface workflow.

## GitHub App installation lifecycle

`stackgraph_discovery.github_installation_cli` registers a tenant connector using
only a secret-provider credential reference, paginates the installation's complete
authorized repository set, creates connector-bound repository targets, and safely
disables removed targets. `stackgraph_discovery.github_webhook_server` verifies
GitHub HMAC signatures, archives delivery bodies in the tenant evidence store,
deduplicates delivery IDs, and routes default-branch pushes and lifecycle changes
into the ingestion control plane.

See [the GitHub installation lifecycle runbook](../../docs/runbooks/github-installation-lifecycle.md)
for registration, reconciliation, webhook, and revocation commands.

## npm registry resolution

`stackgraph_discovery.npm_resolution` converts repository-owned `.npmrc` and
lockfile evidence into the registry-qualified dependency contract consumed by
registry acquisition. It records public-default portability, custom-registry
pinning, scoped registry selection, artifact integrity, and visibility without
retaining credential values or reading worker-host npm configuration.

See [the npm registry ingestion runbook](../../docs/runbooks/npm-registry-ingestion.md)
for the acquisition boundary and local commands.
