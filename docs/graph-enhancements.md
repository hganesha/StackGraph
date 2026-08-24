# Graph intelligence and embeddings — enhancement review and actions

**Updated:** 2026-08-24

**Status:** review of merged work; no behavior changed by this document

**Reviewed:** `d22b301` (Neo4j graph intelligence and embeddings), `821fef2` (merge), `68b13fd` (graph finding routing and documentation)

**Work plans:** [graph-enhancements-backend.md](./graph-enhancements-backend.md) · [graph-enhancements-frontend.md](./graph-enhancements-frontend.md) — this document is the *why*; the lane plans are the *how*, and each owns its own task detail.

**Companion documents:** [graph-and-embeddings-features.md](./graph-and-embeddings-features.md) (the implemented plan), [runbooks/graph-and-embeddings-operations.md](./runbooks/graph-and-embeddings-operations.md) (operations)

**Scope:** what the merged graph and embedding work can now become, in three lanes — (1) more intelligent API services, (2) UI implementation, (3) sequenced actions. Everything below is an increment on merged behavior; nothing here proposes reversing a delivered decision.

---

## 1. Executive assessment

The merged work is a substrate, not a product surface. It is a strong substrate: PostgreSQL stays authoritative, Neo4j is disposable, embeddings retrieve rather than assert, promotion is gated, and every read carries `as_of`, coverage, and limitations. Those properties are the expensive part and they are done.

The gap is that the substrate computes materially more than it exposes, and exposes materially more than the product uses. Three separate leaks, in order of lost value:

1. **Computed and stored, never read.** Cohort anomalies, circular-dependency motifs, and bridge edge metrics are written to PostgreSQL on every analysis run and have no read path in the API at all. These are the "hidden criticality" findings the product promises; today they are write-only rows.
2. **Exposed, never consumed.** `GET /graph-intelligence/communities` and `POST /search/semantic` exist in the API and in the shared TypeScript client, and no UI calls either. There is no query hook for either.
3. **Consumed, but not reconciled.** Two independent systemic-risk rankings render on the same `/ask` screen from two unrelated methods that share no weights, no inputs, and no version. An architect reading that page sees two different answers to one question.

The single highest-value enhancement is not a new algorithm. It is joining the structural signal the graph worker now produces to the business and vulnerability signal the estate already had, under one governed, versioned composite — and then giving that composite a ranked surface, an explanation, and a decision.

### What the merged work already gets right, and this plan preserves

| Property | Where it holds | Why it must not be relaxed |
|---|---|---|
| PostgreSQL is authoritative | `graph_analysis_run`, `graph_entity_metric`, `entity_embedding` | Neo4j and every vector space stay rebuildable and disposable |
| Fail-closed retrieval | `semantic_search` requires an `ACTIVE` space at coverage ≥ 0.95 with `evaluation.passed` | A degraded space must never quietly answer |
| Evidence-backed paths | `GraphImpactPath.supporting_fact_ids`, `graph_motif.supporting_fact_ids` | Every structural claim stays reconstructable |
| Explainable similarity | `overlaps` / `differences` / `coverage` on every candidate | A percentage alone is never a consolidation decision |
| Gated promotion | Structural spaces held in `SHADOW`; activation is deliberate | A model cannot self-promote |

Every recommendation below inherits these properties. Where a recommendation would weaken one, it is marked and bounded.

---

## 2. Gap inventory

Verified against the merged tree. "Reader" means an API read model or endpoint that returns the data to a client.

| Artifact | Writer | Reader | Consequence |
|---|---|---|---|
| `graph_anomaly` (cohort percentile outliers) | `worker.py` | none | Cohort-relative criticality is invisible |
| `graph_motif` (circular dependency SCCs, with fact IDs) | `worker.py` | none | Dependency cycles are detected and discarded |
| `graph_edge_metric` (`spof.bridge`) | `worker.py` | none | The canvas cannot mark the edge whose removal partitions the graph |
| `structural_embedding_run` | `worker.py` | none | Node2Vec stability/evaluation results are unreviewable in product |
| `graph_community_alignment` | none | none | Table shipped with neither side implemented |
| `application_description_proposal` | none | none | Governed proposal schema shipped ahead of its feature (documented as deliberate) |
| `GET /graph-intelligence/communities` | — | client method only | No hook, no surface |
| `POST /search/semantic` | — | client method only | No hook, no surface; the estate's only semantic entry point is unused |
| `graph_entity_metric` | `worker.py` | per-entity + risk list | No collection-level read; Estate cannot rank by it |

Two further defects are behavioral rather than structural:

- **Divergent risk methods.** `graph_risks` composes four structural percentiles with weights hardcoded in Python (`reachability.upstream_impact` 0.4, `betweenness` 0.3, `spof.articulation` 0.2, `pagerank` 0.1) and states in its own `RENORMALIZED_COMPOSITE` limitation that business criticality and vulnerability overlays are unavailable. `_ask_systemic_dependency_risk` composes vulnerability count, repository breadth, static reachability, runtime observation, deployability, Tier-1 criticality, and deprecation with a different set of hardcoded point weights in SQL — and no centrality at all. Both render on `/ask`: the first as the "Architecture risk" section, the second as the "Systemic dependency risk" card under Enterprise risk.
- **Discarded review rationale.** `application_similarity_feedback` stores `reason_code` and `rationale`, and the API accepts both. The UI sends the constant `"APPLICATION_DETAIL_REVIEW"` and never captures a rationale, so every consolidation decision in the estate is recorded without its reasoning. The review is also one-way: `ApplicationSimilarityReviewRequest.decision` excludes `UNREVIEWED`, so a mistaken decision cannot be reopened through the API.

---

## 3. More intelligent API services

Ten enhancements, ordered by value per unit of risk. Each keeps the existing response contract shape: `contract_version`, `as_of`, snapshot provenance, score components, coverage, limitations, and supporting fact IDs.

### S1 — One governed composite risk method (`graph-systemic-risk/v2`)

**Problem.** Two rankings, two weight sets, neither versioned, both wrong in complementary ways: the structural one cannot see that a package is vulnerable, the business one cannot see that a package is an articulation point.

**Change.** Compose one score from four signal families, renormalizing over whichever families the tenant actually has:

| Family | Source | Present today |
|---|---|---|
| Structural | `graph_entity_metric` percentiles from the active runtime-dependency snapshot | yes |
| Business | `current_capability_application_relationship.criticality`, application tier | yes, unused by `graph_risks` |
| Exposure | `AFFECTED_BY` vulnerability facts, static reachability, runtime observation, deployability | yes, unused by `graph_risks` |
| Lifecycle | deprecation, support state, catalog viability | yes, partially used |

**Governance.** Move the weights out of Python and SQL literals into `graph_analysis_policy.configuration`, which is already versioned and content-hashed per tenant. The response then carries `policy_version` and `policy_hash` that actually explain the number. A tenant that disagrees with the weighting changes a governed policy rather than requiring a release.

**Contract.** Extend `GraphRiskItem` with `component_contributions` (family → normalized contribution and the metric or fact IDs behind it) and `renormalized_families`, so the UI can state *why* an entity ranks where it does. Retire the `_ask_systemic_dependency_risk` SQL heuristic and route the `systemic_dependency_risk` report at `read_models.py:212` to the same composite, so the report card and the Architecture risk section cannot disagree.

**Guardrail.** Where a family is absent, renormalize and emit a limitation — never impute. This is the behavior `graph_risks` already has; it must survive the merge of the two methods.

### S2 — Rank in SQL, filter and paginate

**Problem.** `graph_risks` fetches every metric row for the run (four metric keys × every node in the policy graph — 22,385 nodes in the recorded benchmark), groups and sorts in Python, and then slices to `limit`. The wire response is small; the work is not. There are no filters and no cursor.

**Change.** Materialize the composite at run completion into a `graph_entity_risk` table keyed by `(run_id, entity_id)`, written by the worker in the same transaction as the metrics it derives from. Then serve the endpoint as an indexed ranked read with:

```text
GET /graph-intelligence/risks
  ?entity_type=Package&namespace=TECHNOLOGY
  &community_key=…&min_score=0.6
  &cursor=…&limit=50
```

This also gives Estate a ranked lens (S3) for free, and makes the ranking reproducible from a snapshot rather than recomputed per request.

### S3 — Collection-level graph metrics for Estate

**Problem.** `/entities/{id}/graph-metrics` is per-entity. `RankedItem` carries `priority`, `viability`, and freshness — no structural fields. `/estate/summary` accepts `cursor`, `limit`, and `domain`, and has no `sort`. The Estate ranked lens described in the plan's §8 cannot be built without one request per row.

**Change.** Add optional graph fields to `RankedItem` (`systemic_risk`, `upstream_impact`, `dependency_depth`, `community_key`, `structural_status`), populated from the active snapshot with a single join, and add `sort` to `/estate/summary` accepting `priority` (default), `systemic_risk`, `upstream_impact`, and `dependency_depth`. Absent snapshot ⇒ fields omitted and the sort rejected with a typed error, not silently reordered.

### S4 — Read paths for anomalies, motifs, and bridges

**Problem.** Three classes of finding are computed and stored with their supporting fact IDs, and no client can read any of them.

**Change.** Three small read models in the established shape:

```text
GET /graph-intelligence/anomalies?cohort_key=&limit=      → entity, metric, cohort, percentile, cohort size, reasons
GET /graph-intelligence/motifs?motif_key=&limit=          → cycle members, supporting fact IDs, minimum confidence
GET /entities/{id}/critical-edges                         → spof.bridge edges incident to the entity, with fact IDs
```

Every row already has its evidence — `graph_motif.supporting_fact_ids` and `graph_anomaly.observed_components` are populated on write — so each finding opens the existing evidence drawer with no new plumbing.

**Why it is more intelligent, not just more data.** A cohort anomaly answers a question raw centrality cannot: this service sits at or above the 95th percentile of upstream impact *for its own cohort*, which is what makes it unexpected rather than merely large. A circular motif is the one structural finding an architect can act on immediately without business context.

### S5 — Semantic entity resolution in Ask (the plan's missing stage 1)

**Problem.** The plan's §9 specifies three stages: semantic retrieval resolves entities, deterministic queries answer, an LLM summarizes only what was returned. Stages 2 and 3 are implemented. Stage 1 is not. `AIAskOrchestrator` selects one of twenty fixed `query_kind` values, and entity identity reaches the deterministic layer only through caller-supplied `context_entity_ids`. Deterministic `ask()` routes on substring matching. A question that names an application or package cannot resolve it.

**Change.** Add a second allowlisted tool alongside `query_estate`:

```text
resolve_entities(text_span, entity_types[]) → tenant-scoped candidate entity IDs
```

Back it with the existing `semantic_search` read model, tenant-scoped, restricted to the active evaluated space, capped at a small `k`, and returning IDs only. Feed resolved IDs into `context_entity_ids` on the deterministic call. The model still selects and never computes; retrieval narrows the deterministic query rather than answering it.

**Guardrail.** Resolution is a *hypothesis*. Where an answer depends on a resolved entity, the response names the entity it resolved and the score, so a wrong resolution is visible rather than silent. If no space is active, resolution is skipped and Ask behaves exactly as it does today.

### S6 — Graph-backed query kinds in Ask

**Problem.** Structural questions currently reach SQL heuristics. "If package X disappeared tomorrow, what breaks?" is answered by `_ask_package_business_blast_radius` walking `current_relationship`, while a complete, snapshot-backed, evidence-carrying answer already exists in `graph_blast_radius`.

**Change.** Add `blast_radius`, `structural_criticality`, `community_membership`, and `circular_dependencies` to `QUERY_KINDS`, routing to the snapshot read models when a complete snapshot covers the entity, and falling back to the existing SQL path — with a stated limitation — when it does not. This is the plan's "deterministic Neo4j queries answer structural questions, with SQL fallback during projection lag."

### S7 — Explainable semantic search

**Problem.** `SemanticSearchHit` returns entity, score, `input_hash`, and sensitivity. No excerpt, no overlap, no path back to the facts. `embedding_document.source_fact_ids` is populated on every document and never returned, so the explanation exists and is withheld.

**Change.** Return `matched_terms` (overlap between the query and the rendered document), a bounded excerpt of `rendered_content` respecting the document's sensitivity, and `source_fact_ids` for the evidence drawer. Add `min_score` and `namespace` to the request. Optionally re-rank the top-k by the active snapshot's structural percentile so a semantically-plausible but structurally-irrelevant match sinks — with the blend published in the response, never hidden.

**Guardrail.** An excerpt inherits the most restrictive sensitivity of its inputs, as the plan requires. Where sensitivity forbids the excerpt, return the score and the fact IDs without the text.

### S8 — Similarity beyond applications

**Problem.** `similar_applications` covers `Application` only. The `technology_diversity`, `internal_library_standards`, and `custom_to_internal_platform` reports all ask a similarity question about technologies and capabilities and answer it with unrelated heuristics.

**Change.** Generalize the endpoint to `/entities/{id}/similar` across `Application`, `Technology`, and `Capability`, with per-kind feature sets and per-kind method versions. Keep the explainability contract unchanged — `overlaps`, `differences`, `coverage`, `limitations` on every candidate.

Also: add `review_state` filtering and cursor pagination to the candidate list, capture `reason_code` and `rationale` from the caller rather than a constant, and add a governed reopen path so a decision can be corrected. The append-only feedback table already records every transition; only the API refuses the reverse direction.

### S9 — Operator API for runs and promotion

**Problem.** There is no endpoint to request a graph analysis run or an embedding backfill, and shadow-space promotion is a CLI subcommand (`embedding_worker.py`, `activate`) that writes `active_embedding_space` directly. An operator with the Admin UI open cannot see an evaluated candidate space, compare it to the active one, or promote it. The repository rescan path shows the right pattern.

**Change.** Three audited, capability-gated endpoints:

```text
POST /graph-intelligence/analysis-requests   → coalesced request (mirrors the existing unique-index coalescing)
POST /embeddings/backfill                     → bounded re-render/re-embed for a space
POST /embedding-spaces/{id}/promotion         → promote or roll back, gated on coverage + evaluation.passed
```

Promotion writes an `admin_audit_log` row in the same transaction as the pointer swap and refuses a space that does not pass its gates. This exposes the existing gate; it does not lower it.

### S10 — Intelligence on graph nodes

`GraphNode` carries `namespace`, `type`, `key`, `label`, `aggregate`, `member_count`, `confidence` — nothing structural. Add optional `structural_status`, `systemic_risk`, and `community_key` to nodes and `is_bridge` to edges, populated from the active snapshot. This is the prerequisite for U5 and costs one join on a bounded neighborhood.

---

## 4. UI implementation

The plan's §8 rule stands: no new top-level page, contextual delivery over an intelligence destination. Every item below lands in an existing surface. §8.2's bar for a dedicated workspace is not met and this plan does not try to meet it.

### U1 — Reviews acts on similarity (highest value, smallest change)

Today the Reviews queue lists `APPLICATION_SIMILARITY` items — the API routes them correctly, the count is right, the title reads `Billing API ↔ Ledger API` — and then renders the string *"Open where this was found to review it"* with no link. `IDENTITY_ASSERTION` is the only type with an inline decision affordance. The only place a similarity decision can be made is a drawer inside Application detail, which a reviewer working the queue never opens.

Give the row the same treatment `UncertainBridge` gives identity: inline overlaps and differences, the four governed decisions, a required reason and an optional rationale, and a link to both applications. Every other queue type at minimum gets a working link to its review location.

### U2 — Estate ranked lenses

With S3, add `Systemic risk`, `Upstream impact`, and `Dependency depth` to the Estate sort control, server-sorted, preserving the ranked-table default. The plan asked for this in §8 and it is the single change that makes graph intelligence reachable without first knowing which entity to open. When no snapshot is active, the lenses are disabled with the reason stated, not hidden.

### U3 — Architecture risk becomes explainable and complete

The `/ask` Architecture risk section shows six cards with a score and one reason. With S1 it should show the composite's family contributions ("structural 78th percentile · 3 reachable vulnerabilities · 2 Tier-1 applications") and, where families were renormalized, say so on the card rather than only in the limitation footer. Remove the duplicate `Systemic dependency risk` report card once S1 unifies the method, or relabel it explicitly as the same ranking viewed as a table.

### U4 — Findings that currently have no surface

- **Anomalies** as a lens on Estate and a line in the entity's graph-intelligence panel, naming the cohort, the percentile, and the cohort size that made the finding admissible.
- **Circular dependencies** as an Architecture risk subsection and a badge on the entity panel, each opening its cycle with supporting evidence.
- **Communities** as a filter on Estate and a "peers in this community" line on entity detail. `listGraphIntelligenceCommunities` already exists in the client and needs a hook and a surface.

### U5 — The graph lens shows what the graph knows

`GraphCanvas` renders a bounded neighborhood with no structural encoding. With S10: size or tint nodes by systemic risk, mark articulation points, and draw bridge edges distinctly with the "removing this disconnects N entities" explanation on selection. This is where the bounded-canvas rule pays off — the canvas stops being a picture of adjacency and starts showing where the estate is brittle.

### U6 — Semantic search has an entry point

`POST /search/semantic` has a client method, no hook, and no UI. Wire it into the existing search affordance as a governed fallback: exact and lexical matches first, semantic candidates in a clearly-labeled second group with score, matched terms, and evidence (S7). When no evaluated space is active, the semantic group is absent with the reason stated — the current fail-closed 503 is correct for the API and must not surface as a broken search box.

### U7 — Admin operates the intelligence it configures

Admin → Services & health shows `graph-intelligence` and `embeddings` as start/stop rows. Add, backed by S9: active vs. shadow spaces with coverage and evaluation results side by side, promote and roll back, request an analysis run, request a backfill, and the governed weight configuration from E1. Structural Node2Vec spaces stay visible as `SHADOW` with their stability numbers — the promotion gate becomes legible instead of invisible.

### U8 — Consistency repairs

- Repository detail has no graph-intelligence panel at all, though repositories are ranked in `graph_risks` and are the entity most likely to be a bridge.
- Application detail receives `graph_intelligence` embedded in `ApplicationDetail`; Technology detail issues a separate `useEntityGraphMetrics` request for the same panel. Pick one — embedding it costs one join on a detail read already doing several.
- The panel's "Coverage is limited; open the blast-radius detail for snapshot limitations" tells the user to go looking. State the limitation where it applies.

---

## 5. Actions

Sequenced so each phase is independently shippable and each unblocks the next. Effort is relative, not calendar. "Exit" is the observable condition, in the style the feature plan uses.

This section is the **cross-lane milestone view** — the only place the two lanes are sequenced against each other. Per-task detail (files, acceptance, tests) lives in the lane plans: backend tasks are `BE-*` in [graph-enhancements-backend.md](./graph-enhancements-backend.md), frontend tasks are `FE-*` in [graph-enhancements-frontend.md](./graph-enhancements-frontend.md). The "Lane" column below says which plan owns each row; rows marked *Web + API* split across both and are handed off at the contract.

The two lanes run in parallel rather than in series. `playwright.config.ts` runs end-to-end tests against the fixture client, so the frontend builds and tests a surface as soon as its **contract** is published — not when its implementation lands. The backend lane therefore ships each wire shape in two steps, contract first; the protocol is in its plan.

### Phase A — Reconcile and surface what already exists

No new computation. Highest value per unit of risk.

| # | Action | Lane tasks | Depends on | Exit |
|---|---|---|---|---|
| A1 | Inline similarity decisions in Reviews, with required reason and optional rationale (U1, part of S8) | FE-A1 · BE-A1 | — | A reviewer completes a consolidation decision without leaving Reviews; `application_similarity_feedback` carries a non-constant reason on every new row |
| A2 | Read models for anomalies, motifs, and bridge edges (S4) | BE-A2 | — | Each endpoint returns snapshot-backed rows with supporting fact IDs that open the evidence drawer |
| A3 | Surface anomalies, motifs, communities (U4) | FE-A2 · FE-A3 | A2 | Each finding class is reachable from Estate or an entity, or is stated as unavailable with a reason |
| A4 | Hook and surface semantic search (U6, S7 request fields) | FE-A4 · BE-A3 | — | Semantic candidates appear as a labeled group with matched terms and evidence; absent space degrades visibly, never breaks |
| A5 | Consistency repairs (U8) | FE-A5 · FE-A6 · BE-A4 | — | Repository detail carries the panel; both detail pages load intelligence the same way |

### Phase B — One risk method, one ranking

The flagship change. Its backend half (`BE-B1`) has no dependency and can run alongside Phase A; its frontend half should not, because `FE-A2`/`FE-A3` establish the finding-surface pattern `FE-B1` reuses. This is the clearest case for the lanes moving at different speeds.

| # | Action | Lane tasks | Depends on | Exit |
|---|---|---|---|---|
| B1 | Move composite weights into `graph_analysis_policy.configuration`; publish `policy_version` and `policy_hash` on every risk response (S1) | BE-B1 | — | Changing a tenant's weighting requires no release; the response explains the number it returned |
| B2 | Compose structural + business + exposure + lifecycle families with renormalization and per-family contributions (S1) | BE-B2 | B1 | Scores are reproducible from a snapshot plus a policy hash; every absent family emits a limitation |
| B3 | Materialize `graph_entity_risk` at run completion; serve ranked, filtered, cursor-paginated risks (S2) | BE-B3 | B2 | The endpoint no longer loads the full metric set per request; filters and cursor are covered by tests |
| B4 | Route the `systemic_dependency_risk` report to the composite and retire the divergent SQL heuristic (S1) | BE-B4 | B2 | `/ask` cannot show two different rankings of one question |
| B5 | Explainable Architecture risk cards (U3) | FE-B1 | B2 | Each card states its family contributions and any renormalization |

### Phase C — Ranked lenses and the graph that shows what it knows

| # | Action | Lane tasks | Depends on | Exit |
|---|---|---|---|---|
| C1 | Graph fields on `RankedItem`; `sort` on `/estate/summary` (S3) | BE-C1 | B3 | Estate ranks by structural signal in one request; an unavailable sort is a typed error |
| C2 | Estate ranked lenses (U2) | FE-C1 | C1 | An architect reaches the most structurally critical entity without knowing its name |
| C3 | Intelligence on graph nodes and edges (S10) | BE-C2 | B3 | Bounded neighborhoods carry status, risk, community, and bridge flags |
| C4 | Structural encoding in the graph lens (U5) | FE-C2 | C3 | Articulation points and bridge edges are visually distinct and explained on selection |

### Phase D — Ask becomes retrieval-grounded

| # | Action | Lane tasks | Depends on | Exit |
|---|---|---|---|---|
| D1 | `resolve_entities` tool backed by tenant-scoped semantic search (S5) | BE-D1 | A4 | A question naming an entity resolves it; the response names what it resolved and its score |
| D2 | Graph-backed query kinds with stated SQL fallback (S6) | BE-D2 | B2 | Structural questions answer from snapshots when covered, from SQL with a limitation when not |
| D3 | Resolution and structural provenance in the Ask answer presentation | FE-D1 | D1, D2 | A wrong resolution is visible to the reader, not silent |

### Phase E — Operate it

| # | Action | Lane tasks | Depends on | Exit |
|---|---|---|---|---|
| E1 | Analysis-request, backfill, and promotion endpoints, audited and gate-enforcing (S9) | BE-E1 | — | Promotion refuses a space failing coverage or evaluation; every promotion writes an audit row in the same transaction |
| E2 | Admin space comparison, promotion, rollback, and weight configuration (U7) | FE-E1 | E1, B1 | An operator promotes an evaluated space and configures weights without a shell |
| E3 | Generalized similarity across Technology and Capability (S8) | BE-E2 | A1 | Per-kind method versions with unchanged explainability contract |

### Deferred, deliberately

- **`graph_community_alignment`** — implement or drop. A table with neither a writer nor a reader is a maintenance liability; decide which before adding anything that depends on it.
- **`application_description_proposal`** — the feature plan already documents generation as separately authorized. Leave the schema; do not build the generator on this plan's authority.
- **ANN indexes** — the plan's gate stands: exact search must miss a measured SLO first. Nothing in this plan changes that; S7's re-ranking operates on an already-bounded top-k.
- **A dedicated graph-intelligence workspace** — §8.2's bar is not met. Revisit only if Phase C usage shows architects entering the product to investigate rather than starting from Insights, Estate, or an entity.

---

## 6. Verification to add with the work

The merged work's test posture is good and these additions follow it rather than replacing it.

| Area | Test |
|---|---|
| Composite risk | Golden fixture proving the same snapshot plus the same policy hash yields the same ranking; a fixture with each family absent in turn proving renormalization and a stated limitation, never imputation |
| Ranked reads | Cursor stability across a page boundary under concurrent run completion; filter combinations covered |
| Anomalies and motifs | Every returned row's supporting fact IDs resolve through the evidence endpoint |
| Entity resolution | A question naming an entity resolves it; with no active space, Ask behaves byte-identically to today |
| Sensitivity | A `RESTRICTED` document never returns an excerpt through semantic search, at any score |
| Promotion | A space below coverage or with `evaluation.passed` false is refused; the refusal and every accepted promotion are audited |
| E2E | Reviews completes a similarity decision inline; Estate sorts by systemic risk; the graph lens marks a bridge edge |

---

## 7. Guardrails this plan does not relax

Stated explicitly so a later reader can tell what was decided from what was overlooked.

- Embeddings retrieve and rank candidates. They never assert a dependency, an impact, or a consolidation.
- Fail-closed stays fail-closed. A degraded or unevaluated space answers nothing; the *UI* degrades visibly, the *API* does not soften.
- The natural-language layer selects and summarizes. It never computes reachability, never invents causation, and never cites evidence outside the tool result.
- Absent signal is renormalized and declared, never imputed.
- Every structural claim keeps a reconstructable path and its supporting fact IDs.
- No model or algorithm promotes itself.
- No full-estate graph canvas.
