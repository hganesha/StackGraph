# Estate fidelity contract handoff

This addendum records the S1–S3 and safe E1 read surfaces added after
`ui-phase-2-alignment.md`. The OpenAPI document is authoritative for field-level detail.

## UI-ready resources

| UI need | Operation | Contract |
|---|---|---|
| Component index | `GET /components` | `EstateComponentList` |
| Component detail | `GET /components/{id}` | `EstateComponentDetail` |
| Container composition | `GET /repositories/{id}/container-compositions` | `ContainerCompositionList` |
| Deployment profiles | `GET /repositories/{id}/deployment-profiles` | `DeploymentProfileList` |
| Six-layer strata | `GET /estate/strata` | `EstateStrata` |
| Observed contradiction ledger | `GET /contradictions` | `ContradictionLedger` |

All six operations are available through `StackGraphClient`, fixture and live transports,
and React Query hooks in `apps/web/lib/estateFidelityQueries.ts`.

## Honesty and identity rules

- A component's entity UUID is its durable identity. `component_path` is nullable and is
  only a repository locator; moving a directory does not change the route identity.
- `AVAILABLE` component profiles require both a path and current evidence. Missing values
  produce `PARTIAL` with a stable limitation code.
- A container is `RESOLVED` only when an immutable `sha256` digest is present. A mutable
  tag is `INFERRED`; `latest` is `UNRESOLVED`. An available composition requires a resolved
  digest and at least one layer or package.
- Deployment profiles use verb-and-target action rows. Provider and workload values remain
  open strings so new platforms do not require a contract revision.
- The strata response always contains Business, Enterprise, Technology, OSS, Deployment,
  and AI in that order. AI is customer AI supply-chain coverage; StackGraph Intelligence is
  never substituted for it. Until E1 collection lands, AI is explicitly `NOT_COLLECTED`.
- The contradiction ledger shows distinct current claims by source, confidence, recency,
  evidence, and affected-entity count. It deliberately does not declare a winning claim.

## Still gated

The observed contradiction endpoint does not replace E1's governed assumption registry or
resolution history; it returns `ASSUMPTION_REGISTRY_NOT_AVAILABLE` until that persistence
exists. R16 capability envelopes and cross-system flight events remain A1 work and must not
be represented by the existing business-capability taxonomy. Agent execution authority is
still blocked on the security and governance gates in the integrated Phase 2 plan.
