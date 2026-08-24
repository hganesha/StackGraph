# Graph enhancements — frontend work plan

**Updated:** 2026-08-24

**Lane:** Next.js app, shared client fixtures and hooks, design system, graph canvas, end-to-end tests

**Source:** [graph-enhancements.md](./graph-enhancements.md) — the review this plan executes. Task IDs cite the `U*` UI enhancements and the `A`–`E` milestones defined there.

**Paired lane:** [graph-enhancements-backend.md](./graph-enhancements-backend.md)

---

## 1. What this lane owns

| Owned | Not owned |
|---|---|
| `apps/web/app/` — every route and surface | `apps/api/` — models, routes, read models |
| `apps/web/components/`, `apps/web/lib/` — hooks, stores, query state | `services/intelligence/` — workers |
| `packages/design-system/` — components and glossary | `infrastructure/database/` — migrations |
| `packages/graph-ui/` — canvas, nodes, layout | `stackgraph-foundation/contracts/v1/openapi.json` and the generated types |
| Fixture implementations in `packages/shared/src/api/client.ts`, `tests/e2e/` | Live client methods in the same file, where they mirror a backend contract |

The generated contract types are read-only to this lane. Where a shape is wrong, that is a backend contract step, not a local type edit.

---

## 2. Working ahead of the backend

`playwright.config.ts` runs the suite with `NEXT_PUBLIC_DATA_SOURCE=fixtures`, and `stackGraphClient` resolves to `fixtureClient` in that mode. Every surface below can be built, styled, reviewed, and tested end to end before its endpoint exists.

The sequence per task:

1. Backend publishes the contract (generated types land in `packages/shared/src/contracts/`).
2. This lane adds a **fixture** in `packages/shared/src/api/client.ts` beside the existing `fixtureEmbeddingStatus` / `fixtureApplicationSimilarity` helpers, a hook in `apps/web/lib/queries.ts`, and the surface.
3. E2E covers it in fixture mode.
4. Live integration when the backend's implementation step lands.

**A fixture is not optional.** Any new client method without a fixture counterpart breaks fixture mode for the whole app, and fixture mode is what CI runs. Fixtures should represent the *interesting* state — a renormalized score, a limitation present, a cohort anomaly — not the happy path only, because the empty and degraded states are most of this work.

Three tasks need no backend at all and can start immediately: **FE-A1** (`POST /similarity-candidates/{id}/review` already exists), **FE-A2** (`listGraphIntelligenceCommunities` already exists in the client), and **FE-A6** (glossary, drawer, and accessibility repairs).

**Correction, found in implementation.** FE-A1 was listed as fully unblocked and is not. `ReviewQueueItem` carries a title, a confidence, and a review path — not the two application IDs and not the candidate's overlaps and differences. The *decision* is unblocked and is built; showing the evidence beside it in the queue needs a read for a single candidate by id (`GET /similarity-candidates/{id}`), which no backend task currently covers. Add it to BE-A1.

---

## 3. Task list

| ID | Task | Source | Milestone | Depends on |
|---|---|---|---|---|
| FE-A1 | Reviews decides similarity inline | U1 | A | Shipped — decision only; inline overlaps need a candidate-by-id read |
| FE-A2 | Communities become a surface | U4 | A | Shipped — entity half; the Estate filter needs BE-C1 |
| FE-A3 | Anomalies and circular dependencies become surfaces | U4 | A | Blocked on BE-A2 contract |
| FE-A4 | Semantic search gets an entry point | U6 | A | Shipped — matched terms and excerpt need BE-A3 |
| FE-A5 | Detail-page consistency | U8 | A | Shipped — repository half; the technology request drop needs BE-A4 |
| FE-A6 | Vocabulary, drawer reuse, and accessibility repairs | U8 | A | Shipped |
| FE-B1 | Architecture risk explains itself | U3 | B | Blocked on BE-B2, BE-B4 contracts |
| FE-C1 | Estate ranked lenses, server-sorted | U2 | C | Blocked on BE-C1 contract |
| FE-C2 | The graph lens shows what the graph knows | U5 | C | Blocked on BE-C2 contract |
| FE-D1 | Ask shows what it resolved | — | D | Blocked on BE-D1, BE-D2 contracts |
| FE-E1 | Admin operates the intelligence it configures | U7 | E | Blocked on BE-E1 contract |

---

## 4. Task detail

### FE-A1 — Reviews decides similarity inline

**Files:** `apps/web/app/reviews/page.tsx`, `reviews.module.css`, new `apps/web/components/reviews/SimilarityDecision.tsx`, `apps/web/lib/queries.ts`

The queue lists `APPLICATION_SIMILARITY` items correctly — right count, right title (`Billing API ↔ Ledger API`), right confidence chip — and then renders the string *"Open where this was found to review it"* with no link. `IDENTITY_ASSERTION` is the only type with an inline affordance (`UncertainBridge`). The only place a similarity decision can be made today is a drawer inside Application detail, which a reviewer working the queue never opens.

Build `SimilarityDecision` on the `UncertainBridge` pattern: the candidate's overlaps and differences inline, the four governed decisions, a **required reason** and an optional rationale, and links to both applications.

**The reason field is the point of this task.** `useReviewApplicationSimilarity` currently hardcodes `reason_code: "APPLICATION_DETAIL_REVIEW"` and never captures a rationale, so every consolidation decision in the estate is recorded without its reasoning while the API and the append-only feedback table both accept it. Capture both here and in the Application-detail drawer, which shares the hook.

While in this file: every queue type that is not `IDENTITY_ASSERTION` currently gets the same dead hint string. At minimum give each a working link to where it can be reviewed.

**Acceptance:** a reviewer completes a decision without leaving Reviews; no new feedback row carries a constant reason; the queue count and the candidate list both refresh on success (the hook already invalidates both keys).

### FE-A2 — Communities become a surface

**Files:** `apps/web/lib/queries.ts`, `apps/web/app/estate/`, `apps/web/components/graph-intelligence/GraphIntelligenceSummary.tsx`

`listGraphIntelligenceCommunities` has existed in `packages/shared/src/api/client.ts` since the merge with no hook and no caller. Add `useGraphIntelligenceCommunities`, a community filter on Estate, and a "peers in this community" line on the entity panel.

A community is a weakly-connected component, not a team or a domain — name it in the UI so it is not read as ownership. `algorithm_key` is on the response; surface it rather than implying the grouping is semantic.

**Acceptance:** communities are reachable from Estate and from an entity; the `NO_ACTIVE_POLICY_SNAPSHOT` limitation renders as a stated reason, not an empty list.

### FE-A3 — Anomalies and circular dependencies become surfaces

**Files:** `apps/web/lib/queries.ts`, `apps/web/app/ask/page.tsx`, `apps/web/components/graph-intelligence/`

Both finding classes are computed on every analysis run with their supporting fact IDs and have never had a reader.

- **Anomalies** as a line on the entity panel and a lens on Estate. Phrase them cohort-relative: the entity sits at or above the 95th percentile of a metric *within its own cohort*, with the cohort named and its size shown. The size matters — the worker requires a cohort of at least 5, and a finding drawn from 5 peers deserves less weight than one drawn from 200.
- **Circular dependencies** as an Architecture risk subsection on `/ask` and a badge on the entity panel, each opening the cycle in order with its evidence.

Both open the existing evidence drawer through `useEvidenceStore` — the fact IDs come with the rows.

**Acceptance:** each finding class is reachable and evidence-backed, or is stated as unavailable with a reason.

### FE-A4 — Semantic search gets an entry point

**Files:** `apps/web/lib/queries.ts`, the existing search affordance, `packages/shared/src/api/client.ts` (fixture)

`POST /search/semantic` has a live client method, no hook, and no UI. The estate's only semantic entry point is unreachable.

Wire it as a **governed second group**, never as the primary result: exact and lexical matches first, semantic candidates below under a label that says what they are, with score, matched terms, and evidence (from BE-A3).

**The unavailable state is the design problem, not the happy path.** The API returns `503 SEMANTIC_SPACE_UNAVAILABLE` when no evaluated space is active — which is correct and must not change — but a user must never see a broken search box. Render the semantic group as absent with its reason ("semantic candidates need an evaluated embedding space; none is active yet"), and keep lexical search fully functional. Treat the 503 as an expected state in the hook, not an error toast.

**Acceptance:** semantic candidates appear labeled and explained when a space is active; with no space, search still works and says why the second group is missing.

### FE-A5 — Detail-page consistency

**Files:** `apps/web/app/repositories/[id]/page.tsx`, `apps/web/app/technologies/[id]/page.tsx`

Repository detail has no graph-intelligence panel at all, though repositories rank in `graph_risks` and are the entity most likely to be an articulation point. Technology detail issues a separate `useEntityGraphMetrics` request for a panel that Application detail gets embedded in its detail response.

With BE-A4 landing `graph_intelligence` on both detail reads: add the panel to Repository detail, and drop the extra request on Technology detail.

**Acceptance:** all three entity types show the panel; the technology page makes one fewer request.

### FE-A6 — Vocabulary, drawer reuse, and accessibility repairs

**Files:** `packages/design-system/src/glossary/terms.ts`, `apps/web/components/graph-intelligence/GraphIntelligenceSummary.tsx`, `tests/e2e/graph-and-embeddings.spec.ts`

Three debts the graph work took on against conventions this repo had already established.

- **Vocabulary.** `GLOSSARY` defines twenty-odd terms and `Term` renders them inline; commit `fb34dc4` made defining the vocabulary in place the house rule. The graph panel then shipped `Bridge / SPOF`, `PageRank`, `Betweenness`, and `Upstream impact` as bare labels. Add glossary entries for blast radius, articulation point / SPOF, systemic risk, community, cohort anomaly, embedding space, and semantic similarity, and wrap the panel's labels in `Term`. These are the least self-explanatory words in the product and currently the only ones with no definition.
- **Drawer.** The design system exports `Drawer`. `GraphIntelligenceSummary` hand-rolls a backdrop, a dialog, focus management, and an Escape handler for two drawers — one of the few places in the app that reimplements a shared component. Move both onto `Drawer`.
- **Accessibility.** Every e2e spec runs an axe pass except `graph-and-embeddings.spec.ts`. Add one, and cover the two drawers specifically — hand-rolled modals are exactly where focus-trap and `aria-modal` defects live.

**Acceptance:** the graph panel's terms are defined in place; both drawers use the shared component; the graph spec has an axe pass at the level of its siblings.

### FE-B1 — Architecture risk explains itself

**Files:** `apps/web/app/ask/page.tsx`, `ask.module.css`

The Architecture risk section shows six cards with a score and one reason string. With BE-B2's `component_contributions`, show which families drove the score — structural percentile, reachable vulnerabilities, Tier-1 applications — and where families were renormalized, say so **on the card**, not only in the limitation footer under the section. A score composed from two of four families is a materially different claim from one composed from four, and today the card cannot tell them apart.

Once BE-B4 lands, the `systemic_dependency_risk` report card and this section are the same ranking. Remove the duplicate card, or relabel it explicitly as the same ranking viewed as a table.

**Acceptance:** a card states its family contributions and any renormalization; `/ask` presents one ranking of systemic risk, not two.

### FE-C1 — Estate ranked lenses, server-sorted

**Files:** `apps/web/lib/estateFilters.ts`, `apps/web/lib/useEstateQuery.ts`, `apps/web/app/estate/EstateView.tsx`, `apps/web/components/estate/DomainList.tsx`

This is the largest frontend task and the one with a trap in it.

Estate sorting is entirely client-side: `applyEstateQuery` sorts the pages already loaded by infinite scroll. That is *already* misleading for `priority` and `viability` — the "top" item is the top of what happens to be loaded — and it becomes actively wrong for systemic risk, where the whole point is finding the critical entity you have not scrolled to.

So FE-C1 is not "add three options to the sort control". It is:

1. Pass `sort` from `useEstateQuery` through to `/estate/summary` (BE-C1), making it part of the query key so a sort change refetches rather than reorders stale pages.
2. Reset pagination on sort change — BE-C1's cursor encodes its sort key and rejects a mismatched cursor, so a stale cursor is a visible error rather than an incoherent page.
3. Move `priority` and `viability` to the server too, or the list sorts two different ways depending on which key is chosen.
4. Add `Systemic risk`, `Upstream impact`, `Dependency depth`, preserving the ranked-table default.
5. Consider a graph lens in `LENSES` beside `cto` / `ea` / `risk` / `platform` — an "architecture risk" persona bundle.

**Disabled beats wrong.** With no active snapshot the graph fields are absent and BE-C1 rejects a graph sort with a typed `400`. Disable those options with the reason shown rather than letting the request fail or silently falling back to priority order.

**Acceptance:** every sort is server-authoritative; changing sort refetches from the first page; graph sorts are disabled with a stated reason when no snapshot is active.

### FE-C2 — The graph lens shows what the graph knows

**Files:** `packages/graph-ui/src/GraphCanvas.tsx`, `DomainNode.tsx`, `graph.module.css`, `apps/web/app/technologies/[id]/graph/GraphLens.tsx`

The canvas renders a bounded neighborhood with no structural encoding at all — every node looks equally important. With BE-C2's node and edge fields: size or tint by systemic risk, mark articulation points, and draw bridge edges distinctly, with "removing this disconnects N entities" in the inspector on selection.

Constraints:

- **Encoding must not be the only channel.** Color or size alone fails colorblind users and fails at small canvas zoom; pair every encoding with a shape, badge, or inspector line. The axe pass will not catch this — review it deliberately.
- **Aggregate nodes carry no structural claim.** BE-C2 returns nothing structural for them; render them plainly rather than inventing an average.
- **Watch the budget.** `scripts/check-bundle-budget.mjs` caps a route at 210 KB First Load JS. React Flow is already dynamically imported in `GraphLens`; keep new encoding logic inside `graph-ui` so it stays behind that boundary.

**Acceptance:** articulation points and bridge edges are visually distinct, explained on selection, and distinguishable without relying on color; `pnpm perf:budget` still passes.

### FE-D1 — Ask shows what it resolved

**Files:** `apps/web/app/ask/page.tsx`, `ask.module.css`

With BE-D1, Ask resolves entities semantically before answering. Resolution is a hypothesis, so the answer must name the entity it resolved and how confidently — otherwise a wrong resolution produces a confident answer about the wrong application and nothing on screen reveals it.

Show the resolved entity as a correctable chip near the answer, and mark structurally-answered responses with their snapshot provenance, distinguishing a snapshot-backed answer from the SQL fallback BE-D2 falls back to under projection lag.

**Acceptance:** a reader can see what Ask thought the question was about and that it might be wrong; snapshot-backed and fallback answers are distinguishable.

### FE-E1 — Admin operates the intelligence it configures

**Files:** `apps/web/components/admin/ServicesSection.tsx`, `IntelligenceSection.tsx`, `apps/web/app/admin/page.tsx`

Admin → Services & health shows `graph-intelligence` and `embeddings` as start/stop rows. With BE-E1: active and shadow spaces side by side with coverage and evaluation results, promote and roll back, request an analysis run, request a backfill, and the governed weight configuration from BE-B1.

Structural Node2Vec spaces stay visible as `SHADOW` with their stability numbers. The promotion gate is currently invisible — an operator cannot see that a candidate space exists, let alone why it has not been promoted. Making the gate legible is most of this task's value; the buttons are the smaller half.

Promotion is destructive to search behavior for a whole tenant. Confirm before promoting, name the space, and show what changes.

**Acceptance:** an operator promotes an evaluated space and configures weights without a shell; a space that fails its gates shows *which* gate; every promotion is confirmed.

---

## 5. Cross-cutting obligations

- **Fixture parity.** Every new client method needs a fixture. Fixtures cover the degraded states — no active snapshot, renormalized score, restricted document, empty candidate set — because those are most of what this work renders.
- **Empty and unavailable states are designed, not defaulted.** Every one of these surfaces has a real "not ready yet" state driven by snapshot freshness or embedding-space gates. A blank panel is a bug.
- **Limitations render.** Every response carries `limitations`; they belong next to the number they qualify, not collapsed at the bottom. The current panel says *"Coverage is limited; open the blast-radius detail for snapshot limitations"* — telling the user to go looking is not rendering a limitation.
- **Accessibility.** New surfaces get an axe pass in their spec and keyboard paths for every affordance, matching `glossary-terms.spec.ts`.
- **Budget.** `pnpm perf:budget` after canvas and Estate work.
- **No design drift.** Reuse `Drawer`, `StatTile`, `ConfidenceChip`, `CitationChip`, `Term`, `RankedTable` rather than growing new one-off patterns.

---

## 6. Sequencing

```text
Start now, no backend:     FE-A1   FE-A2   FE-A6
On contract publication:   FE-A3   FE-A4   FE-A5
Then:                      FE-B1 → FE-C1 → FE-C2
Independent:               FE-D1   FE-E1
```

FE-A6 is unblocked, small, and pays into every task after it — the glossary entries and the shared drawer are used by FE-A3, FE-B1, and FE-C2. Do it early rather than last.

FE-C1 is the biggest single change and the one most likely to surface a backend cursor problem; start it as soon as BE-C1's contract lands rather than batching it behind FE-B1.

## 7. Definition of done for this lane

- Every new surface has a fixture, a hook, an empty state, an unavailable state, and a limitation state.
- `pnpm typecheck`, `pnpm lint`, `pnpm lint:css`, `pnpm perf:budget`, and `pnpm e2e` pass.
- `tests/e2e/graph-and-embeddings.spec.ts` has an axe pass and covers: an inline similarity decision, an Estate graph sort, a marked bridge edge, and a semantic search with no active space.
- No graph term appears in the UI without a glossary definition.
- No surface presents a score without the coverage and limitations that qualify it.
