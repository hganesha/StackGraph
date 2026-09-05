# Phase 2 backend implementation

This document records the implemented backend slice of the integrated Phase 2 plan. UI work is intentionally out of scope here.

## Implemented

- additive scanner `1.11.0`: evidence-backed Component entities, component dependencies, multi-label repository classification, declared deployment profiles, digest-first container identity, build/base-image edges, and repository fingerprints;
- richer activity: releases, deployments, actor taxonomy, raw bounded events, and recomputable 7/30/90-day aggregates;
- canonical action discovery for `UPGRADE Package`, exact subjects/targets/scopes, a bounded command parser, immutable Mutation IR and ChangeSets, semantic idempotency, explicit gates, and no-effect refusal;
- durable asynchronous SimulationRuns with queue leases/retries/cancellation, estate and policy pinning, predicate-aware direct/context/STOP findings, hypothetical overlays, immutable deterministic hashes, and a separate AI interpretation partition;
- recommendation-to-ChangeSet compilation without manual re-entry, with proposal provenance and persisted not-simulatable reasons;
- deployment-wide kill switches plus tenant-specific feature overrides, RLS, audit events, normalized tenant-safe evidence references, service control/heartbeat, Prometheus operational signals, Compose worker wiring, OpenAPI generation, and backend contract/integration tests;
- a read-only 10,000-request Phase 2 API latency gate and recovery-drill coverage for durable ChangeSets, SimulationRuns, findings, and deterministic result hashes.

## Deliberate boundaries

- Only `UPGRADE Package` is active. Other ontology actions and subject types remain disabled until deterministic semantic providers and policies exist.
- Mutable container tags remain unresolved observations. Registry/layer enrichment is asynchronous future work and must not block local scanning.
- Repository archetypes are emitted only when direct features meet a rule threshold. Activity and actor mix are marked unavailable in local scanner fingerprints until connector evidence is joined.
- AI interpretation remains disabled by default. No execution surface is enabled.

## Verification commands

```sh
docker compose run --rm migrate
pnpm --dir stackgraph-foundation validate
PYTHONPATH=services/enterprise-discovery .venv/bin/pytest -q services/enterprise-discovery/tests
STACKGRAPH_TEST_DATABASE_URL=postgresql://stackgraph_admin:stackgraph_admin@localhost:5432/stackgraph \
  PYTHONPATH=services/data-platform:services/enterprise-discovery \
  .venv/bin/pytest -q services/data-platform/tests/test_scanner_ingest_integration.py
STACKGRAPH_CONTRACTS_DIR="$PWD/stackgraph-foundation/contracts/v1" \
  PYTHONPATH=apps/api:services/intelligence/ai-services:services/intelligence/graph-intelligence \
  .venv/bin/pytest -q apps/api/tests
PACKAGE_ID=<canonical-package-uuid> make phase2-api-benchmark
make recovery-drill
```
