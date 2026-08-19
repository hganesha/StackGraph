# StackGraph V0 dependency ingestion plan

## Goal

Answer four questions:

1. Which repositories depend on which packages?
2. Which exact versions are declared or locked?
3. Which dependencies are direct, transitive, development, optional, or runtime?
4. What externally measured health/security/release information exists for those observed packages?

Nothing else belongs in the first ingestion pipeline.

## Minimal flow

```text
Customer repository changes
  -> inspect manifest and lock files
  -> resolve effective package registry from lockfile + npm configuration
  -> normalize package/version identities as purls qualified by registry provenance
  -> store repository dependency facts and evidence
  -> enrich only newly observed/stale packages through deps.dev, registries, and OSV
  -> optionally fetch metadata for the package's official project repository
```

## What gets pulled

### From customer GitHub repositories

Pull only when the default-branch revision changes:

- `package.json`, npm/yarn/pnpm lockfiles, workspace configuration, and project-level `.npmrc` resolution settings;
- `pyproject.toml`, requirements files, Poetry/uv/Pipenv locks;
- Dockerfiles and selected deployment manifests when runtime/deployment identification is enabled;
- repository metadata needed to identify the revision and evidence source.

Authentication values in `.npmrc` are never emitted or stored as fact properties. The scanner records only the normalized registry origin, applicable scope, config locator, and resolution method. Credential material remains behind a connector-owned secret reference.

Start with targeted file retrieval. Use a shallow checkout/archive only when monorepo discovery or file layout makes targeted retrieval impractical.

### From external services

For packages actually observed in customer repositories or the curated seed, and from the registry through which each package was resolved:

- deps.dev: versions, resolved dependency graph, package/project association, licenses;
- OSV: vulnerabilities for observed package versions;
- package registry: current/deprecation/release metadata when deps.dev lacks a required field, using registry-scoped authentication for private sources;
- GitHub: official linked project's metadata, archive status, releases, and timestamps—not source code by default.

## What does not get pulled

- the GH Archive firehose;
- arbitrary public GitHub repositories;
- public repository source code;
- every npm/PyPI package;
- full Git history;
- repeated repository snapshots when the commit SHA has not changed.

## Continuous behavior

### Customer repositories

- GitHub push/default-branch webhook enqueues the changed repository.
- Deduplicate work by repository ID + commit SHA + scanner version.
- A reconciliation job checks current default-branch SHAs periodically; it does not fetch code when the SHA is unchanged.
- A complete scan closes dependencies no longer present. A partial/failed scan never removes prior facts.

### Observed packages

- A newly observed registry-qualified purl creates an enrichment job.
- Public package/project data is shared globally across tenants. Private/custom-registry metadata and package identities remain tenant-scoped unless an evidence-backed identity assertion links them to a public package.
- Refresh active/important packages on a configurable schedule; unchanged responses only advance freshness.
- A new observed version triggers deps.dev/OSV enrichment for that version.
- Do not recursively expand beyond the dependency depth/edge budget required by the current customer query.

## Initial scale assumptions

These are ceilings for capacity tests, not ingestion targets:

| Pilot estate | Expected order of magnitude |
|---|---:|
| Customer repositories | 100 |
| Manifest/lock artifacts | 100–500 |
| Repository-to-package observations | 10,000–100,000 |
| Unique package versions after deduplication | 10,000–50,000 |
| Dependency edges after bounded resolution | 100,000–1,000,000 |

This should fit comfortably in a small PostgreSQL deployment. Raw manifests/lockfiles and external responses should remain well below a few gigabytes for the first pilot unless repositories contain unusually large generated locks.

Measure the first 100-repository scan and revise these assumptions before sizing further.

## Implementation order

1. Correct the fact contract and define registry-qualified, purl-based package identities.
2. Implement GitHub revision detection and targeted manifest retrieval.
3. Implement npm lockfile/workspace parsing.
4. Implement Python manifest/lock parsing.
5. Persist idempotent dependency facts with exact file/line/JSON-pointer evidence.
6. Add deps.dev enrichment for newly observed package versions.
7. Add OSV batch queries.
8. Add official project/repository metadata resolution.
9. Add complete-snapshot removal semantics and reconciliation.
10. Expose repository and technology dependency views.

## npm registry resolution rules

1. Treat `registry.npmjs.org` as a configured default, not an assumption derived from an npm purl.
2. Resolve scoped registry mappings and default registry settings from applicable `.npmrc` and workspace configuration, with the lockfile as evidence of the concrete resolution.
3. Preserve whether a lockfile entry follows the configured default, is pinned to a custom registry, or uses an explicit tarball URL.
4. Keep package identity and registry origin separate. Public npm uses its normal purl identity; a private/custom package initially uses `registry:<registry-key>:<purl>` to avoid collisions with an identically named public package.
5. Record requested spec, resolved version, artifact URL, integrity, dependency scope, and direct/transitive status without retaining authentication material.
6. `publishConfig.registry` is publishing metadata and does not determine dependency installation.
7. Registry clients enforce normalized-origin allowlists, redirect checks, per-registry credentials, conditional requests, rate limits, and freshness independently.
8. Do not use the public CouchDB mirror as a V0 firehose. Enrich only packages observed in a customer repository or approved curated seed.

These behaviors follow npm's documented registry selection, registry-scoped authentication, and default-versus-custom lockfile semantics: [npm registry documentation](https://docs.npmjs.com/cli/v10/using-npm/registry).

## Optional second pass

Source imports can later distinguish a declared dependency from one actually referenced and support unused-dependency or capability-level recommendations. Run that pass only when a repository revision changes or when a user requests deeper analysis. It is not a daily public-code ingestion job.
