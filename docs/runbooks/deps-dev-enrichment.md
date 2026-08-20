# deps.dev OSS enrichment

The Lane A deps.dev worker enriches explicitly observed or curated npm and PyPI package versions. It does not crawl arbitrary packages or use the v3alpha API.

Repository scanner publication automatically creates a global deps.dev target and an initial reconciliation run for each newly observed exact package-version purl with evidence that it resolved from a public registry. Replayed scans and already-known targets do not reset the target's freshness schedule. Private, custom-registry, or registry-unknown packages are not enqueued. npm scans currently provide this registry provenance; PyPI remains available through explicit targets until Python index provenance is captured by the scanner.

For each exact package-version purl, the worker retrieves stable deps.dev v3 version metadata and its resolved dependency graph, stores the combined response as an immutable raw observation, and publishes evidence-backed facts for:

- package-to-version membership;
- package-version metadata, including licenses, deprecation, advisories, registry links, and related projects; and
- resolved package-version dependency edges.

Package and package-version identities are global public purls backed by the public npm or PyPI registry identity. A custom/private registry package must not be sent to this worker.

## Run one target

```shell
make depsdev-run PURL='pkg:npm/react@18.2.0'
make database-project
make depsdev-verify
make database-project-verify
```

PyPI example:

```shell
make depsdev-run PURL='pkg:pypi/fastapi@0.116.1'
```

`run` enqueues the target and processes one leased job. Separate scheduler/worker operation is also available:

```shell
make depsdev-enqueue PURL='pkg:npm/react@18.2.0'
docker compose run --rm depsdev schedule
make depsdev-work
```

The `depsdev-continuous` pipeline service runs `serve`, which drains available work and polls for due targets. The bounded `schedule` and `work` commands remain available for operators and tests; PostgreSQL provides `FOR UPDATE SKIP LOCKED` leasing and retry availability.

## Safety and replay

- Only versioned npm and PyPI purls without qualifiers or subpaths are accepted.
- Graph node and edge counts are bounded per target.
- Provider graph errors, bundled dependencies, unsupported nodes, and exceeded budgets produce a `PARTIAL` snapshot. Partial snapshots never close facts from the prior complete snapshot.
- Content hashes are the provider source revision. Replaying unchanged content reuses the published snapshot and emits no duplicate facts.
- Retryable provider and transport failures return exit code `75` and reschedule with bounded exponential delay. Terminal schema/provider failures enter `dead_letter`.
- Freshness, limitations, next-due time, and content-hash cursors remain queryable in PostgreSQL.

## Tests

```shell
make database-seed-test
npm --prefix stackgraph-foundation run validate
```

The deterministic deps.dev fixtures exercise URL encoding, purl normalization, graph limits, retry classification, and fact generation without network access.
