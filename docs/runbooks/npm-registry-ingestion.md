# npm registry acquisition

This slice resolves npm package source separately from purl identity and acquires exact-version metadata only for observed package versions. It supports the public npm registry and compatible private registries without mirroring a registry or retaining credentials in emitted observations.

## Repository-side resolution

`stackgraph_discovery.npm_resolution` parses non-secret registry settings from project/workspace `.npmrc` content and combines them with lockfile artifact URLs. It emits:

- normalized registry origin and deterministic registry key;
- `LOCKFILE`, `NPMRC_SCOPE`, `NPMRC_DEFAULT`, `NPM_DEFAULT`, or `EXPLICIT_TARBALL` resolution source;
- configured-default, custom-pinned, or explicit-tarball lockfile behavior;
- requested spec, resolved version, integrity, dependency scope, and directness;
- public/private/unknown visibility and a tenant-qualified canonical key where required.

Authentication keys are detected by name but values are discarded. Worker-host npm configuration is never inherited.

## Registry acquisition

Fetch public metadata:

```bash
make npm-registry-fetch PURL=pkg:npm/react@19.1.0
```

Fetch private metadata with registry-scoped credentials:

```bash
export STACKGRAPH_NPM_REGISTRY_TOKEN=...
make npm-registry-fetch \
  PURL=pkg:npm/%40acme/billing-sdk@2.4.1 \
  NPM_REGISTRY_ARGS='--registry-key acme-npm --registry-origin https://npm.acme.example/repository/npm/ --visibility PRIVATE --tenant-key acme'
```

The token is used only in the request header. It is absent from normalized metadata and the raw-observation envelope.

## Safety and refresh behavior

- Registry origins and tarball URLs must be credential-free HTTPS.
- Cross-origin packument redirects are rejected.
- ETags are accepted through `--etag`; a `304` produces `UNCHANGED` without re-normalization.
- `429` and `5xx` responses are classified as retriable and retain `Retry-After` where present.
- Responses are bounded to 16 MiB by default.
- No CouchDB mirror or registry-wide change feed is consumed.

## Verification

```bash
python -m unittest tests.test_npm_resolution
docker compose run --rm --no-deps --entrypoint python depsdev -m unittest tests.test_npm_registry
```
