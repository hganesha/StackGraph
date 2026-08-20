StackGraph is an enterprise software estate intelligence and
modernization platform designed for a world in which software creation
is accelerating dramatically through coding agents, AI-assisted
development, and "vibe coding."

The underlying enterprise problem is not simply that organizations have
vulnerabilities. It is that they increasingly cannot answer basic
questions about their software estate:

-   What applications, services, components, and repositories exist?
-   What business functions, processes, capabilities, and value-chain
    stages do they support?
-   What languages, runtimes, frameworks, packages, databases, UI
    systems, infrastructure components, and deployment patterns do they
    use?
-   What are the direct and transitive dependencies?
-   Where is each workload intended to run: cloud, on-premises,
    Kubernetes, containers, VMs, serverless, managed services?
-   Which technologies are healthy and strategically viable versus
    merely free of known CVEs?
-   Which packages/frameworks are unsupported, abandoned, declining,
    unnecessarily complex, or superseded by native/runtime capabilities?
-   Which technologies have better alternatives for the **actual
    function being performed**?
-   Where has the organization independently implemented the same
    capability multiple times?
-   Which applications should be retained, upgraded, consolidated,
    refactored, rebuilt, replatformed, retired, or investigated?
-   Where should modernization investment be directed based on business
    importance, technical viability, opportunity, confidence, and
    effort?
-   What new technology and architecture patterns are coding agents
    introducing into the estate?

StackGraph addresses this by turning source repositories and related
evidence into a continuously updated, evidence-backed model of:

**Business → Applications → Code → Technology → Dependencies →
Deployment → Infrastructure → OSS ecosystem → Viability → Modernization
actions**

Git repositories are a primary sensor, not the final product.

## Importing the public npm OSS catalog

The data platform can import the currently 5,232-row
[DeepKlarity top npm packages dataset](https://huggingface.co/datasets/deepklarity/top-npm-packages)
as global, evidence-backed OSS metadata:

```sh
make backend-up
make oss-catalog-import
```

The importer keeps every dataset column under `entity.properties.catalog_metadata`,
creates package, latest-version, OSS-project, and repository entities, and publishes
idempotent `EXTERNAL_MEASURED` facts. It pins the CSV revision and records its
November 5, 2024 effective date so the metrics are not presented as current.
Re-running unchanged content is a no-op. To load a reviewed local copy instead:

```sh
docker compose run --rm \
  -v "$PWD/npm_packages.csv:/input/npm_packages.csv:ro" \
  oss-catalog --csv-file /input/npm_packages.csv \
  --effective-at 2024-11-05T09:18:44Z
```
