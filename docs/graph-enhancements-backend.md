# Graph enhancements — backend work plan

**Updated:** 2026-08-24

**Lane:** API, graph-intelligence worker, embedding worker, migrations, contracts

**Source:** [graph-enhancements.md](./graph-enhancements.md) — the review this plan executes. Task IDs cite the `S*` service enhancements and the `A`–`E` milestones defined there.

**Paired lane:** [graph-enhancements-frontend.md](./graph-enhancements-frontend.md)

---

## 1. What this lane owns

| Owned | Not owned |
|---|---|
| `apps/api/app/` — models, routes, read models, Ask orchestration | `apps/web/` — every surface |
| `services/intelligence/graph-intelligence/` — analysis and embedding workers | `packages/design-system/`, `packages/graph-ui/` |
| `infrastructure/database/migrations/` and SQL smoke tests | Fixture implementations in `packages/shared/src/api/client.ts` |
| `stackgraph-foundation/contracts/v1/openapi.json` and the generated types it produces | Query hooks in `apps/web/lib/queries.ts` |
| `apps/api/tests/`, `services/*/tests/` | `tests/e2e/` |

The boundary is the contract. This lane's deliverable for any UI-visible task is not "the endpoint works" — it is **the contract is published and the generated types are committed**, because that is the moment the frontend lane can start.

---

## 2. The handshake

`tests/e2e/` runs against `NEXT_PUBLIC_DATA_SOURCE=fixtures` by default (`playwright.config.ts`). The frontend lane builds and tests every surface against the fixture client without a running API. That makes the two lanes genuinely parallel, on one condition: **the contract lands before the implementation.**

For every task that changes a wire shape, land it in two steps:

1. **Contract step** — Pydantic models in `apps/api/app/models.py`, route signature with `operation_id` and `tags`, then `pnpm contracts:generate` and commit `stackgraph-foundation/contracts/v1/openapi.json` plus `packages/shared/src/contracts/openapi.generated.ts`. The endpoint may return a stubbed but *contract-valid* payload at this point. Announce it; the frontend lane starts.
2. **Implementation step** — read model, SQL, worker changes, tests. No wire shape changes here. If implementation forces a shape change, that is a new contract step, announced again — not a silent edit, because the frontend has already built against the first one.

`pnpm contracts:check` fails CI when generated types drift from the source, which is the guard that keeps this honest.

---

## 3. Task list

Milestone letters match the review's phases. "Blocks FE-*" names the frontend task waiting on the contract.

| ID | Task | Source | Milestone | Blocks | Depends on |
|---|---|---|---|---|---|
| BE-A1 | Similarity list filtering, pagination, and a governed reopen path | S8 | A | FE-A1 | — |
| BE-A2 | Read models for anomalies, motifs, and bridge edges | S4 | A | FE-A3 | — |
| BE-A3 | Semantic search request filters and match explanation | S7 | A | FE-A4 | — |
| BE-A4 | Consistent graph-intelligence embedding on entity detail reads | U8 | A | FE-A5 | — |
| BE-B1 | Composite weights into governed policy configuration | S1 | B | — | — |
| BE-B2 | Composite risk `v2` with signal families and contributions | S1 | B | FE-B1 | BE-B1 |
| BE-B3 | Materialize `graph_entity_risk`; ranked, filtered, paginated risks | S2 | B | FE-B1 | BE-B2 |
| BE-B4 | Route the `systemic_dependency_risk` report to the composite | S1 | B | FE-B1 | BE-B2 |
| BE-C1 | Graph fields on `RankedItem`; `sort` on `/estate/summary` | S3 | C | FE-C1 | BE-B3 |
| BE-C2 | Structural fields on graph nodes and edges | S10 | C | FE-C2 | BE-B3 |
| BE-D1 | `resolve_entities` tool for Ask | S5 | D | FE-D1 | BE-A3 |
| BE-D2 | Graph-backed query kinds with stated SQL fallback | S6 | D | FE-D1 | BE-B2 |
| BE-E1 | Operator endpoints: analysis request, backfill, promotion | S9 | E | FE-E1 | — |
| BE-E2 | Similarity generalized to Technology and Capability | S8 | E | — | BE-A1 |

---

## 4. Task detail

### BE-A1 — Similarity list filtering, pagination, and a governed reopen path

**Files:** `apps/api/app/models.py`, `routes.py`, `read_models.py` (`similar_applications`, `review_application_similarity`)

`similar_applications` returns every candidate ordered by score with no filter and no cursor. `ApplicationSimilarityReviewRequest.decision` excludes `UNREVIEWED`, so a decision made in error cannot be undone through the API even though `application_similarity_feedback` is append-only and would record the reversal correctly.

- Add `review_state` filter and cursor pagination to `GET /entities/{id}/similar`, using the existing `_encode_cursor`/`_decode_cursor` helpers.
- Add `GET /similarity-candidates/{id}` returning one candidate with its `overlaps`, `differences`, `coverage`, and both applications. Found during frontend implementation: the review queue can now *decide* a candidate, but `ReviewQueueItem` carries only a title and a confidence, so the queue cannot show what the two applications share without this read. Until it lands, a reviewer decides from the title alone or opens the application.
- Add a `REOPENED` decision that resets `review_state` to `UNREVIEWED` and appends a feedback row like any other decision. It is a new decision, not a delete — the history stays complete.
- Keep `reason_code` required. The frontend currently sends a constant; that is FE-A1's fix, and this task must not paper over it by defaulting the field server-side.

**Acceptance:** a reviewer can page a large candidate set, filter to unreviewed, and reverse a decision; every transition including the reversal appears in `application_similarity_feedback` with its actor and the candidate's method version and score at decision time.

### BE-A2 — Read models for anomalies, motifs, and bridge edges

**Files:** `apps/api/app/models.py`, `routes.py`, `read_models.py`

`graph_anomaly`, `graph_motif`, and the `spof.bridge` rows in `graph_edge_metric` are written by `worker.py` on every run and read by nothing. All three already store their supporting fact IDs, so no worker change is needed — this is read models over data on disk.

```text
GET /graph-intelligence/anomalies?cohort_key=&limit=
GET /graph-intelligence/motifs?motif_key=&limit=
GET /entities/{id}/critical-edges
```

Follow the shape `graph_risks` and `graph_communities` already use: resolve the active snapshot via `_active_graph_snapshots`, return `snapshot`, `as_of`, and `limitations`, and return `NO_ACTIVE_POLICY_SNAPSHOT` rather than an empty list when no snapshot covers the policy. Anomalies carry `cohort_key`, `cohort_size`, `percentile`, and the reasons the worker already writes; motifs carry their member entities in cycle order with `supporting_fact_ids` and `minimum_confidence`.

**Acceptance:** every returned row's fact IDs resolve through `GET /facts/{id}/evidence` under the same tenant. A tenant with no snapshot gets a stated limitation, not an empty success.

### BE-A3 — Semantic search request filters and match explanation

**Files:** `apps/api/app/models.py`, `read_models.py` (`semantic_search`)

`SemanticSearchHit` returns entity, score, `input_hash`, and sensitivity. `embedding_document` stores `source_fact_ids` and `rendered_content` for every document, so the explanation exists and is withheld.

- Request: add `min_score` and `namespace`.
- Response: add `matched_terms` (overlap between the tokenized query and the rendered document — `TOKEN_PATTERN` in `embeddings.py` is already the tokenizer), a bounded `excerpt`, and `source_fact_ids`.
- **Sensitivity gate:** the excerpt inherits the document's classification. A `RESTRICTED` document returns score and fact IDs with no excerpt and a stated limitation. Test this explicitly — it is the one place this task can leak.

Keep the fail-closed behavior exactly as it is: no evaluated `ACTIVE` space at coverage ≥ 0.95 still means `503 SEMANTIC_SPACE_UNAVAILABLE`. Making search degrade gracefully is a frontend concern (FE-A4), not an API softening.

**Acceptance:** a hit explains itself; a restricted document never yields text at any score; the unavailable path is unchanged.

### BE-A4 — Consistent graph-intelligence embedding on entity detail reads

**Files:** `apps/api/app/models.py`, `read_models.py` (`repository_detail`, `technology_detail`)

`ApplicationDetail` carries `graph_intelligence` embedded. `TechnologyDetail` does not, so the technology page issues a second request for the same panel. `RepositoryDetail` carries nothing at all, though repositories rank in `graph_risks` and are the entity most likely to be an articulation point.

Add `graph_intelligence: EntityGraphIntelligence | None` to both, populated by the same helper `application_detail` uses. One join on a read already doing several.

**Acceptance:** all three detail reads carry the panel's data in one request; the technology page's separate metrics call becomes removable by FE-A5.

### BE-B1 — Composite weights into governed policy configuration

**Files:** `infrastructure/database/migrations/041_*.sql`, `apps/api/app/read_models.py`

The composite weights live as a Python dict in `graph_risks` (`reachability.upstream_impact` 0.4, `betweenness` 0.3, `spof.articulation` 0.2, `pagerank` 0.1). `graph_analysis_policy.configuration` is already a versioned, content-hashed, per-tenant JSONB column — the right home.

Migrate the defaults into the seeded `runtime-dependency` policy configuration under a `risk_weights` key, read them at request time, and publish `policy_version` and `policy_hash` on the risk response. Reject a configuration whose weights do not parse or do not sum to a positive total, at write time, with a typed error — a malformed policy must fail loudly rather than silently renormalize to nothing.

**Acceptance:** changing a tenant's weighting requires no release; the response's `policy_hash` reproduces the ranking it returned.

### BE-B2 — Composite risk `v2` with signal families and contributions

**Files:** `apps/api/app/models.py`, `read_models.py`

Compose four families, renormalizing over whichever are present:

| Family | Source |
|---|---|
| Structural | `graph_entity_metric` percentiles from the active snapshot |
| Business | `current_capability_application_relationship.criticality`, application tier |
| Exposure | `AFFECTED_BY` vulnerability facts, static reachability, runtime observation, deployability |
| Lifecycle | deprecation, support state, catalog viability |

The exposure and business SQL already exists inside `_ask_systemic_dependency_risk` — this task lifts it out of the Ask heuristic and into a reusable read model, which is also what makes BE-B4 a deletion rather than a rewrite.

Extend `GraphRiskItem` with `component_contributions` (family → normalized contribution plus the metric keys or fact IDs behind it) and `renormalized_families`. Set `method_version` to `graph-systemic-risk/v2`.

**Guardrail:** an absent family is renormalized and declared. Never imputed, never defaulted to a midpoint. `graph_risks` has this behavior today and it must survive the merge.

**Acceptance:** a golden fixture proves the same snapshot plus the same policy hash yields the same ranking; a fixture per absent family proves renormalization and a stated limitation.

### BE-B3 — Materialize `graph_entity_risk`; ranked, filtered, paginated risks

**Files:** `infrastructure/database/migrations/042_*.sql`, `services/.../worker.py`, `apps/api/app/read_models.py`, `routes.py`

`graph_risks` fetches every metric row for the run — four metric keys across every node in the policy graph, 22,385 nodes in the recorded benchmark — groups and sorts in Python, then slices to `limit`.

Write the composite into `graph_entity_risk(run_id, entity_id, systemic_risk, contributions, renormalized_families)` in the same worker transaction that writes the metrics it derives from, so the score is a property of the immutable snapshot rather than a per-request recomputation. Then serve:

```text
GET /graph-intelligence/risks?entity_type=&namespace=&community_key=&min_score=&cursor=&limit=
```

as an indexed ranked read. Index `(tenant_id, run_id, systemic_risk DESC, entity_id)` to make the cursor stable.

**Acceptance:** the endpoint no longer loads the full metric set per request; cursor paging is stable across a page boundary while a new run completes; filters are covered by tests.

### BE-B4 — Route the `systemic_dependency_risk` report to the composite

**Files:** `apps/api/app/read_models.py` (`_ENTERPRISE_INSIGHT_REPORTS`, `_ask_systemic_dependency_risk`)

The report at `_ENTERPRISE_INSIGHT_REPORTS[0]` and the Architecture risk section render on the same `/ask` screen from unrelated methods. Point the report at the composite and delete the divergent SQL scoring — its inputs now live in BE-B2's read model, so nothing is lost.

Keep the report's row shape stable where it can be (`risk_score` remains the `metric_field`) so the report card and its table do not need a frontend change beyond FE-B1's explanation work.

**Acceptance:** `/ask` cannot show two different rankings of one question; the report's readiness and metric extraction still work.

### BE-C1 — Graph fields on `RankedItem`; `sort` on `/estate/summary`

**Files:** `apps/api/app/models.py`, `routes.py`, `read_models.py` (`estate_summary`)

`/estate/summary` accepts `cursor`, `limit`, and `domain` — no `sort`. Add optional `systemic_risk`, `upstream_impact`, `dependency_depth`, `community_key`, and `structural_status` to `RankedItem`, joined from `graph_entity_risk` and the active snapshot, and add `sort` accepting `priority` (default), `systemic_risk`, `upstream_impact`, `dependency_depth`.

The cursor currently encodes `(score, name, id)`. A different sort needs a different cursor tuple; encode the sort key into the cursor and reject a cursor whose sort does not match the request, rather than paging incoherently.

**Guardrail:** with no active snapshot, the graph fields are omitted and a graph sort is a typed `400`, never a silent fallback to priority order. A ranked list that quietly ignores the requested ranking is worse than one that refuses.

**Acceptance:** Estate ranks by structural signal in one request; paging under each sort is stable; the no-snapshot path is a stated error.

### BE-C2 — Structural fields on graph nodes and edges

**Files:** `apps/api/app/models.py`, `read_models.py` (`graph_neighborhood` and its Neo4j/SQL readers)

`GraphNode` carries `namespace`, `type`, `key`, `label`, `aggregate`, `member_count`, `confidence` — nothing structural. Add optional `structural_status`, `systemic_risk`, `community_key` to nodes and `is_bridge` to edges, populated from the active snapshot for the bounded node set the neighborhood already returns.

Populate in **both** readers — the Neo4j path and the `_sql_graph_neighborhood` fallback — or the canvas will change appearance depending on projection lag. The existing parity fixtures are the place to prove they agree.

**Acceptance:** both readers produce identical normalized fixtures including the new fields; aggregate nodes carry no structural claim rather than a misleading average.

### BE-D1 — `resolve_entities` tool for Ask

**Files:** `apps/api/app/ai_ask.py`

The plan's three-stage Ask specifies semantic retrieval, then deterministic query, then summary. Stages 2 and 3 exist. Stage 1 does not: `AIAskOrchestrator` selects one of twenty `query_kind` values and entity identity reaches the deterministic layer only through caller-supplied `context_entity_ids`.

Add a second allowlisted `ToolDefinition` alongside `ESTATE_QUERY_TOOL`:

```text
resolve_entities(text_span: str, entity_types: string[]) → candidate entity IDs
```

backed by the existing `semantic_search` read model, tenant-scoped, restricted to the active evaluated space, capped at small `k`, **returning IDs only**. Feed the resolved IDs into `context_entity_ids` on the deterministic call.

**Guardrails:** the model still selects and never computes. Resolution is a hypothesis, so the response names what was resolved and with what score — a wrong resolution must be visible, not silent. With no active space, resolution is skipped and Ask behaves byte-identically to today; the existing `AIServiceError` fallback path covers the failure case unchanged.

**Acceptance:** a question naming an entity resolves it; a no-space tenant sees no behavior change; the tool cannot return anything but IDs from the caller's tenant.

### BE-D2 — Graph-backed query kinds with stated SQL fallback

**Files:** `apps/api/app/ai_ask.py` (`QUERY_KINDS`, `_tool_request`), `read_models.py` (`ask` routing)

Add `blast_radius`, `structural_criticality`, `community_membership`, and `circular_dependencies`, routing to the snapshot read models when a complete snapshot covers the entity and falling back to the existing SQL path with a stated limitation when it does not. `_ask_package_business_blast_radius` currently walks `current_relationship` for a question `graph_blast_radius` already answers from an immutable snapshot with evidence-backed paths.

`_tool_request` maps each kind to a phrase the deterministic substring router matches; extend that map in step with `QUERY_KINDS` — the two must stay in sync or the tool selects a kind the router drops.

**Acceptance:** structural questions answer from snapshots when covered and from SQL with a limitation when not; no existing question changes its route.

### BE-E1 — Operator endpoints: analysis request, backfill, promotion

**Files:** `apps/api/app/models.py`, `routes.py`, `read_models_admin.py`

Shadow-space promotion is a CLI subcommand in `embedding_worker.py` writing `active_embedding_space` directly. There is no way to request an analysis run or a backfill from the product at all.

```text
POST /graph-intelligence/analysis-requests    → coalesced request
POST /embeddings/backfill                     → bounded re-render/re-embed
POST /embedding-spaces/{id}/promotion         → promote or roll back
```

Model the analysis request on `request_rescan`: capability-gated, audited, `201` for a new request and `200` for an idempotent replay — the `uq_graph_analysis_request_coalescing` index already gives the coalescing semantics.

**Guardrail:** promotion enforces the existing gates — coverage ≥ 0.95 and `evaluation.passed` — and refuses otherwise. This exposes the gate; it does not lower it. The pointer swap and its `admin_audit_log` row commit in one transaction.

**Acceptance:** a space failing its gates is refused with a typed error naming which gate; every promotion and rollback is audited; the CLI path keeps working for operators without UI access.

### BE-E2 — Similarity generalized to Technology and Capability

**Files:** `services/.../similarity.py`, `embedding_worker.py`, `apps/api/app/read_models.py`, `routes.py`

`similar_applications` covers `Application` only, while the `technology_diversity`, `internal_library_standards`, and `custom_to_internal_platform` reports each ask a similarity question about technologies or capabilities and answer it with unrelated heuristics.

Generalize to `/entities/{id}/similar` across the three kinds with per-kind feature sets and per-kind method versions. The explainability contract does not change: `overlaps`, `differences`, `coverage`, `limitations` on every candidate, and a percentage alone is never a decision.

**Acceptance:** each kind produces explainable candidates under its own method version; application results are unchanged by the generalization.

---

## 5. Cross-cutting obligations

Every task above also owes:

- **Tenant isolation.** Each new read model takes `tenant_id` and passes it to `self.database`; each new table gets RLS in its migration alongside the existing graph tables. The control-plane smoke tests (`infrastructure/database/tests/*.sql`) get a case per new table.
- **Operational signals.** New queues or tables that can back up get a signal and threshold in `apps/api/app/operations.py` with a named owner, following the `graph-intelligence-on-call` entries already there.
- **Contracts.** `pnpm contracts:generate` after any model change; `pnpm contracts:check` must pass.
- **Limitations, not silence.** Every new response carries `as_of`, snapshot provenance, and `limitations`. Absent signal is declared.

---

## 6. Sequencing

```text
A: BE-A1  BE-A2  BE-A3  BE-A4        ← fully parallel, no interdependencies
B: BE-B1 → BE-B2 → BE-B3
                └→ BE-B4
C: BE-C1, BE-C2                      ← both need BE-B3
D: BE-D1 (needs BE-A3), BE-D2 (needs BE-B2)
E: BE-E1 (independent), BE-E2 (needs BE-A1)
```

BE-E1 has no dependency on anything and is small; pull it forward if the operator pain is more acute than the ranking pain.

## 7. Definition of done for this lane

- Every wire shape is published in `openapi.json` and the generated types, committed, and `contracts:check` passes.
- `make backend-test` and `make graph-intelligence-test` pass; new read models have tests at the level `test_read_models.py` sets.
- SQL control-plane smokes cover every new table's RLS and invariants.
- No new response can answer without stating its snapshot, its coverage, and its limitations.
- No guardrail in the review's §7 is weaker than it was before this lane started.
