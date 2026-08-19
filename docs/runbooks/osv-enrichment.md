# OSV vulnerability enrichment

The Lane A OSV worker enriches exact public npm and PyPI package versions already observed by StackGraph. It sends package-version purls through OSV's stable batch query API, hydrates each distinct vulnerability record once per worker batch, and publishes evidence-backed `PackageVersion AFFECTED_BY Vulnerability` facts.

Vulnerability entities use the first observed OSV record ID as their canonical external identity. CVE and GHSA identifiers are recorded as additional identities when supplied by OSV. Alias-equivalent OSV records consolidate into one semantic edge while retaining every source record's evidence. A withdrawn advisory remains in raw history and entity metadata but does not emit a current `AFFECTED_BY` fact.

## Run one target

```shell
make osv-run PURL='pkg:npm/lodash@4.17.20'
make osv-run PURL='pkg:npm/lodash@4.17.20' # verifies unchanged-content replay
make database-project
make osv-verify
make database-project-verify
```

PyPI example:

```shell
make osv-run PURL='pkg:pypi/django@2.2.0'
```

## Discover existing package versions

The sync command creates OSV targets only for global public npm/PyPI `PackageVersion` identities already present in PostgreSQL. It never enumerates the public registries or OSV corpus.

```shell
make osv-sync
make osv-work
```

Separate scheduler operation is available with:

```shell
docker compose run --rm osv schedule
```

## Safety and replay

- Requests use versioned purls and never contain registry credentials.
- Query results retain input ordering and paginate per target; page and vulnerability budgets make an incomplete capture `PARTIAL`.
- Distinct vulnerability details are fetched once per worker batch and stored with the per-target query evidence.
- Every matched OSV record contributes two exact evidence hashes: the package-version match returned by `querybatch` and the hydrated vulnerability record. Alias-equivalent records attach all of those evidence pairs to one fact.
- Complete empty results close prior current OSV facts. Withdrawn records also stop emitting current edges.
- Content-addressed snapshots make unchanged responses replay-safe and prevent duplicate facts.
- Retryable provider and transport failures return exit code `75`; terminal failures enter `dead_letter` and respect the target refresh interval.

## Tests

```shell
make database-seed-test
npm --prefix stackgraph-foundation run validate
```

The deterministic OSV fixtures cover batching, per-target pagination, detail hydration, retry classification, evidence hashing, result budgets, and withdrawn advisories without network access.
