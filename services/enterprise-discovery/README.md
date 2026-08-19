# GitHub repository acquisition

This service implements the first repository-ingestion slice from the V0 dependency plan: detect a GitHub repository's current default-branch revision and retrieve only dependency manifests and lockfiles needed by downstream scanners.

It supports public repositories without authentication and private/customer repositories through a token supplied at runtime. Tokens are sent only in the `Authorization` header and are never written into snapshot metadata, file content metadata, paths, or logs.

## Behavior

- Resolves the repository's immutable GitHub ID and current default branch.
- Resolves the default branch to an exact commit and tree SHA.
- Stops before tree or blob retrieval when `--previous-revision` matches.
- Lists the Git tree, selects known JavaScript/TypeScript and Python dependency files, and downloads blobs serially.
- Enforces per-file, total-byte, and file-count limits.
- Marks snapshots `PARTIAL` when GitHub truncates the tree or a configured limit skips a target file.
- Writes an immutable, revision-addressed directory containing retrieved files, `snapshot.json`, and a contract-v1 `raw-observation.json` envelope.

## Run locally

From this directory:

```shell
python -m stackgraph_discovery.github_snapshot owner/repository \
  --output-dir /tmp/stackgraph-snapshots \
  --tenant-key example-tenant
```

For a private repository, expose a short-lived GitHub App installation token or another read-only token through an environment variable:

```shell
GITHUB_TOKEN=... python -m stackgraph_discovery.github_snapshot owner/private-repository \
  --output-dir /tmp/stackgraph-snapshots \
  --installation-id 12345678 \
  --tenant-key example-tenant
```

The token needs read access to repository contents. The default token variable can be changed with `--token-env`; the token itself is never accepted as a command-line argument. `--installation-id` qualifies a customer repository identity by its GitHub App installation. Omit it for a globally shared public OSS repository target.

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
