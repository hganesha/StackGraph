# Repository dependency analysis runbook

This runbook covers the Phase 0 deterministic dependency inventory and Phase 1
usage-evidence path. The pipeline is revision-aware and tenant-safe:

```text
GitHub default-branch SHA
  -> bounded immutable repository snapshot
  -> tenant-scoped content-addressed evidence archive
  -> scanner request v1
  -> dependency and usage facts
  -> transactional PostgreSQL publication
  -> AGE projection outbox
```

A `COMPLETE` scan closes facts from the prior revision for the same target and
extractor key. A `PARTIAL` scan publishes what it observed but never closes facts.
Changing the extractor version does not strand facts produced by the previous
version.

## 1. Apply the database migration

```shell
make database-migrate
```

Migration `005_dependency_usage_analysis.sql` adds checksum-keyed package API
surfaces and per-dependency usage summaries.

## 2. Acquire a revision snapshot

The Compose tools share `services/enterprise-discovery/repository-snapshots` as
`/snapshots`. The acquisition tool also writes a deterministic archive to the
`stackgraph_evidence_data` volume using a tenant-scoped, content-addressed path:

```shell
make repository-acquire REPOSITORY=acme/widgets TENANT_KEY=acme
```

For a private repository, set `GITHUB_TOKEN` and pass its GitHub App installation
ID as `INSTALLATION_ID`. The output reports the canonical repository key, exact
source revision, snapshot directory, archive URI, SHA-256 checksum, and byte size.
If `PREVIOUS_REVISION` matches, acquisition returns `UNCHANGED` without fetching
the tree or blobs.

## 3. Enqueue and build the scanner request

Create or reuse an ingest target/run:

```shell
make scanner-enqueue \
  TENANT_KEY=acme \
  REPOSITORY_KEY=github:repo:123 \
  SOURCE_REVISION=7f83b1657ff1fc53b92dc18148a1d65dfa135014
```

Copy `stackgraph-foundation/contracts/v1/fixtures/scanner-request.json` into the
snapshot volume and replace its run, tenant, target, revision, timestamp, and
checkout root fields. Inside Compose, `snapshot.checkout_root` must point to the
materialized `files` directory, for example:

```json
{
  "snapshot": {
    "source_revision": "7f83b1657ff1fc53b92dc18148a1d65dfa135014",
    "checkout_root": "/snapshots/github-repo-123/7f83b1657ff1fc53b92dc18148a1d65dfa135014/files",
    "requested_at": "2026-08-19T14:00:00Z",
    "blob_uri": "stackgraph-evidence://local/tenants/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/sha256/bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
    "content_hash": "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
    "content_size_bytes": 4096
  }
}
```

Use the exact `blob_uri`, `content_hash`, and `content_size_bytes` printed by the
acquisition result. These fields are optional only for backward compatibility;
when one is supplied, all three are required.

The complete document must remain valid against
`stackgraph-foundation/contracts/v1/schemas/scanner-request.schema.json`.

## 4. Scan and persist

Both paths below are container paths under `/snapshots`:

```shell
make repository-scan \
  SCANNER_REQUEST=/snapshots/request.json \
  SCANNER_RESULT=/snapshots/result.json

make scanner-persist \
  SCANNER_RESULT=/snapshots/result.json \
  RAW_OBSERVATION=/snapshots/github-repo-123/7f83b1657ff1fc53b92dc18148a1d65dfa135014/raw-observation.json \
  TARGET_ID=00000000-0000-4000-8000-000000000100 \
  RUN_ID=00000000-0000-4000-8000-000000000101
```

Persistence validates run/target/tenant/revision/extractor alignment, preserves
source-artifact immutability, stores the raw observation and archive descriptor,
writes exact archive-member evidence URIs, publishes the source snapshot, and
advances the ingest run in one transaction. Replaying a published result is
idempotent.

## 5. Extract a package API surface

Place an unpacked, checksum-verified package artifact beneath the snapshot volume.
The checksum must be `sha256:` followed by 64 hexadecimal characters, and the
purl must identify an exact version.

```shell
make api-surface-extract \
  ARTIFACT_ROOT=/snapshots/artifacts/example-1.2.3 \
  ECOSYSTEM=npm \
  PACKAGE_PURL=pkg:npm/example@1.2.3 \
  ARTIFACT_CHECKSUM=sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef \
  API_SURFACE_RESULT=/snapshots/artifacts/example-1.2.3-api.json

make api-surface-persist \
  API_SURFACE_RESULT=/snapshots/artifacts/example-1.2.3-api.json
```

Public package purls remain global identities. Pass `TENANT_ID` only when the
analysis record itself must be tenant-scoped, such as a private artifact.

## Verification

```shell
PYTHONPATH=services/enterprise-discovery \
python -m unittest discover -s services/enterprise-discovery/tests -v

docker compose run --rm --no-deps \
  -e STACKGRAPH_TEST_DATABASE_URL=postgresql://stackgraph_admin:stackgraph_admin@database:5432/stackgraph \
  --entrypoint python scanner-ingest -m unittest discover -s /code/tests -v
```

The scanner test suite validates results against the frozen scanner JSON Schema
when `jsonschema` is available. The database integration suite verifies
transactional persistence, replay, and complete-snapshot closure across analyzer
versions.
