# StackGraph Foundation

This package defines the initial data foundation for an enterprise software + OSS intelligence platform.

## Core thesis

StackGraph connects six layers:

1. Business value chain, function, process and capability.
2. Applications, services, components and repositories.
3. Languages, frameworks, runtimes, packages and dependencies.
4. Deployment footprint across cloud, on-prem, compute, environment and infrastructure.
5. Public OSS reference intelligence: projects, packages, releases, dependencies, adoption, migrations, alternatives and viability.
6. Evidence-backed assessments and modernization recommendations.

The Git repository is a primary sensor; it is not the product.

## Design invariants

- PostgreSQL is the authoritative store.
- Neo4j is a tenant-scoped, disposable graph projection over canonical PostgreSQL entities and relationships.
- Every material conclusion is traceable to evidence.
- Scanners emit facts; analytics emit assessments; reasoning emits explanations; recommendation engines propose actions.
- Security is one viability dimension, not the product boundary.
- Alternatives are compared by capability/function first, then compatibility, ecosystem evidence and organizational fit.
- Curated claims and measured observations are stored separately.
- Time is first-class: first_seen, last_seen, scan/run and source versions.

## Files

- `schema.sql` — authoritative PostgreSQL 15+ foundation, including ingestion state, temporal facts, identity, outbox, and RLS.
- `CONTRACTS.md` — contract ownership, compatibility, identity, and snapshot rules.
- `contracts/v1/ontology.registry.json` — canonical entity and predicate vocabulary.
- `contracts/v1/schemas/` — normalized fact, scanner, raw observation, and UI read-model schemas.
- `contracts/v1/schemas/npm-resolution.schema.json` — registry origin, npmrc/lockfile resolution, visibility, artifact, and integrity contract for npm/Yarn/pnpm dependencies.
- `contracts/v1/openapi.json` — fixture-first UI/API boundary.
- `contracts/v1/fixtures/` — golden complete/partial ingestion and UI response examples.
- `schemas/` — pre-v1 compatibility artifacts; new implementations must use `contracts/v1`.
- `seed/domains.json` — core product domains.
- `seed/categories.json` — technology/business/deployment taxonomy.
- `seed/capabilities.json` — foundational capability ontology.
- `seed/technologies.json` — hydrated curated technology nodes from the reference landscape.
- `seed/oss-core.json` — curated package definitions, aliases, package-family patterns, and classification overlays for OSS dependencies.
- `seed/relationships.json` — initial semantic/capability relationships.
- `seed/assessments.json` — initial curated lifecycle/trajectory hypotheses.
- `seed/source-rows.json` — normalized raw reference rows retained for provenance.
- `seed/seed-manifest.json` — seed version and provenance.
- `AGE-PROJECTION.md` — legacy AGE projection notes retained for migration context.
- `../docs/graph-and-embeddings-features.md` — selected Neo4j/GDS architecture and delivery plan.
- `ONTOLOGY.md` — canonical entity and relationship semantics.

## Initial hydration

The source landscape is organized by job rather than by generic “framework” type. The hydration keeps that distinction and seeds technologies into categories such as server state, client state, API gateway, service mesh, messaging, identity, workflow, observability and backend ecosystem.

The source should be treated as curated knowledge, not immutable truth. Subsequent GitHub, package-registry, OSV, deps.dev and OpenSSF observations should be appended as external measured facts and may confirm or contradict curated assessments.

## Validate the contract gate

From this directory, run `npm install` and `npm run validate`.
