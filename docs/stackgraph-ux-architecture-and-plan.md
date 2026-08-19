# StackGraph — UX Architecture & Delivery Plan

**Status:** Proposed (v1) — the UI-lane blueprint for the `apps/web` surface
**Scope:** UI/UX only. The backend, ingestion, intelligence, and contracts are treated as fixed inputs.
**Grounded in:** `docs/stackgraph-ui-spec-v2.md` (Evidence-First Triad), `docs/strata-design-language.md` + `strata-design-tokens.json` (Strata), `stackgraph-foundation/ONTOLOGY.md`, `stackgraph-foundation/contracts/v1/*` (frozen read models + OpenAPI), and Lane C of `docs/stackgraph-implementation-plan.md`.
**Companion deliverables (proposed next):** low-fidelity screen wireframe map, component inventory in Figma bound to Strata variables, and a scaffolded `apps/web` shell.

---

## 0. How to read this document

This plan is organized so each layer builds on the one above it:

1. **North Star & principles** — the felt experience we are held to.
2. **Users → jobs → surfaces** — who we serve and what each screen is _for_.
3. **Information architecture** — the ontology-driven map that makes a 10k-node estate navigable.
4. **The needle-in-haystack system** — search, rank, filter, and progressive disclosure as one coherent finding-engine.
5. **Screen-by-screen UX architecture** — every surface, its states, and its interactions.
6. **Design system (Strata) & component architecture** — how it's built and kept consistent.
7. **Data & state architecture** — how read models become pixels without component rewrites.
8. **Cross-cutting quality** — accessibility, localization, security, performance/portability, maintenance.
9. **Delivery plan** — phased roadmap, milestones tied to the 20-minute test, and quality gates.
10. **Open decisions** — the few things that need a human call.

Every recommendation here is traceable to a frozen contract or an existing design decision. Where I extend beyond what's written, it's flagged **[NEW]** so the boundary is explicit.

---

## 1. North Star & design principles

### 1.1 The one-sentence experience

> A leader connects a GitHub org and, within 20 minutes, _scans_ their software estate like a sorted table, _trusts_ every number because the evidence is one click beneath it, and _follows_ their curiosity down into a single bounded neighborhood — never fighting a hairball, never guessing what a color means, never losing where they were.

This is a **calm command-center**, not a dashboard template and not a graph toy. The success test (spec §49) is behavioral, not visual: five material facts leadership didn't know, in ~20 minutes. The UI's entire job is to compress time-to-insight.

### 1.2 Seven principles (the design constitution)

| # | Principle | What it forces in the UI | Anti-pattern it rules out |
|---|---|---|---|
| P1 | **Scan before explore** | The home surface is a ranked, sortable, filterable table — never a canvas. Graph is an opt-in _lens_ reached from a node. | A force-directed hairball as the front door. |
| P2 | **Evidence is a layer, not a footnote** | Every score, badge, and recommendation exposes DECLARED→OBSERVED→INFERRED evidence within one interaction. No conclusion is undismissable-without-provenance. | "Trust us, viability is 44." |
| P3 | **Honesty about uncertainty** | Confidence is categorical (HIGH/MEDIUM/LOW) at a glance, decimal on inspection. Sub-0.85 joins render as _dashed "possible match"_ with Confirm/Reject — never as settled fact. | A speculative join drawn as a solid line. |
| P4 | **Ontology is the map** | Navigation, breadcrumbs, filters, and node types mirror the canonical ontology (Business / Enterprise / Deployment / OSS / Intelligence). The user learns one mental model and it holds everywhere. | Ad-hoc IA that doesn't match the graph the data actually forms. |
| P5 | **Typography carries meaning** | Mono = raw fact (from a scan); Sans = StackGraph's reasoning. The trust boundary is legible before a word is read. | Uniform type that hides the fact/inference distinction. |
| P6 | **Restraint is the aesthetic** | Five hues total, two elevations, motion only for the active bridge selection. Density with breathing room. | Decorative gradients, five shadow tiers, ambient animation. |
| P7 | **Calm under pressure** | Predictable layout, no layout shift, reduced-motion honored, keyboard-first. The tool must be usable by a CISO cross-checking a CVE at 2am and a CTO screen-sharing in daylight. | Surprise, motion sickness, hunt-and-peck. |

### 1.3 What "calm" means operationally

Calm is not "minimal." It's the absence of _unnecessary decisions_ and _unexplained change_:

- **No unexplained motion.** The single 1.8s bridge pulse is the only ambient animation, scoped to the active selection, disabled under `prefers-reduced-motion`.
- **No layout shift.** Skeletons reserve exact final dimensions; content fades in, never reflows.
- **One primary action per view.** Everything else is progressive disclosure.
- **Stable spatial memory.** The three-region shell (rail / workspace / evidence) never rearranges; only content within regions changes.
- **Quiet defaults, loud exceptions.** Neutral ink everywhere; red appears exactly once in the whole system (LOW confidence + genuine errors). When the user sees red, it _means something_.

---

## 2. Users → jobs → surfaces

Five personas (spec §4), each with a dominant job and a "first screen." The IA must let each land where their job lives in <2 clicks, while sharing one substrate.

| Persona | Dominant job-to-be-done | Primary surface | Signature interaction |
|---|---|---|---|
| **CTO / CIO** | "Where is debt concentrated and where should modernization capital go?" | Software Estate + Viability Dashboard | Sort by Priority; read the Technology Entropy number from across the room. |
| **Enterprise Architect** | "What do we have, where does it duplicate, what's the standard?" | Technology Explorer + Estate filters | Capability clustering; standardization opportunities. |
| **Engineering leadership** | "What should this repo do, and why?" | Application Explorer + recommendations | Evidence Drawer read line-by-line; migration complexity. |
| **Platform Engineering** | "Runtime/framework versions, deployment drift, replatform candidates." | Application Explorer (deployment lens) + Estate distributions | Declared-vs-observed deployment diff. |
| **CISO / AppSec** | "Vulnerable, unsupported, reachable — and what business it touches." | Estate filtered to risk + Ask Your Estate | Transitive vulnerability path in Graph Explore; business-impact propagation. |

**Design consequence:** no persona gets a bespoke app. They get the _same five surfaces_ with **saved views / lenses** (§4.4) that pre-configure filters, sort, and columns for their job. This is cheaper to build, easier to maintain, and lets a CTO and their EA hand each other a URL that reproduces the exact view.

---

## 3. Information Architecture — the ontology _is_ the map

The estate is 10k+ nodes across five namespaces (`BUSINESS`, `ENTERPRISE`, `TECHNOLOGY`, `OSS`, `DEPLOYMENT`, `INTELLIGENCE` — per `common.schema.json`). The IA's job is to make that legible without ever asking the user to hold the whole graph in their head.

### 3.1 The three-region application shell **[NEW, consolidates spec intent]**

Every authenticated screen lives in one stable shell so spatial memory never breaks:

```
┌──────────────────────────────────────────────────────────────────────┐
│  TOP BAR:  StackGraph ·  [ Ask your estate ⌘K ............. ]  · tenant │  ← global, always present (spec §3.1)
├────────────┬─────────────────────────────────────────┬─────────────────┤
│            │                                          │                 │
│  LEFT RAIL │            WORKSPACE                      │  EVIDENCE /      │
│  (nav +    │   (the active surface: table, explorer,  │  INSPECTOR       │
│   lenses)  │    dashboard, or graph lens)             │  (contextual,    │
│            │                                          │   collapsible)   │
│            │                                          │                 │
├────────────┴─────────────────────────────────────────┴─────────────────┤
│  STATUS STRIP:  coverage · freshness · as-of · contract version         │  ← trust telemetry, always visible
└──────────────────────────────────────────────────────────────────────┘
```

- **Top bar** carries the one global input — **Ask your estate** (`⌘K`/`Ctrl-K`) — available from _every_ screen (spec §3.1), plus tenant identity (from session, never editable — a security requirement, §7).
- **Left rail** is navigation _and_ lenses. Navigation mirrors the surfaces; lenses are saved views. Collapsible to icon-only for wide-table focus.
- **Workspace** is the only region that swaps wholesale between surfaces.
- **Evidence/Inspector** is a persistent right region that fills contextually — the Evidence Drawer, the graph node inspector, or the recommendation detail. It is a _layer over the current surface_, not a separate page (P2).
- **Status strip** makes trust telemetry ambient: `repositories_scanned / total`, `facts_with_evidence_ratio`, `as_of`, freshness status, and `contract_version` — straight from `estateSummary.coverage` and `.as_of`. This is how a coverage gap becomes visible before it becomes a wrong conclusion.

### 3.2 Navigation model

Primary nav (left rail), matching spec §46 V0 order exactly:

1. **Software Estate** (home) — the ranked portfolio.
2. **Applications** — enter the Application Explorer (list → detail).
3. **Technologies** — enter the Technology Explorer (list → detail).
4. **Modernization** — the Viability & Modernization Dashboard.
5. **Ask** — full-surface conversational view (the top-bar input is the quick entry; this is the expanded home for a working session).

Below a divider: **Lenses** (saved views), then **Reviews** (the uncertain-bridge / identity-assertion queue — the human-in-the-loop backlog).

Pinned to the rail footer (role-gated, always reachable but visually quiet): **Estate Health** (ingestion/enrichment status), **Settings** (personal-scope), and **Admin** (workspace-scope, shown only to admins). The **onboarding / connect-your-org** flow is the first-run entry into Admin › Connections. Full detail in §11.

### 3.3 Breadcrumb & context model

Because everything is one connected graph, the user must _never_ feel lost when they drill in. Breadcrumbs are **ontology paths**, not URL segments:

```
Estate › Application: Billing API › Repository: billing-svc › Package: axios ⟨Graph lens⟩
```

Each crumb is a real entity with a namespace badge. The final `⟨Graph lens⟩` chip signals "you are in the bounded exploration mode; press Esc to return." Graph Explore is explicitly a _lens on the current entity_, not a destination — exiting returns you exactly where you entered (spec §3.2).

### 3.4 URL & deep-linking architecture **[NEW]**

Every meaningful state is a URL — this is what makes the tool _shareable_ (a CTO pastes a link to their EA) and _portable_ (deep-link from Slack/ticket):

| State | URL shape |
|---|---|
| Estate with a lens | `/estate?lens=ciso-risk&sort=priority` |
| Application detail | `/applications/{id}` |
| Evidence open on a fact | `/applications/{id}?evidence={fact_id}` |
| Graph lens on a node | `/applications/{id}/graph?center={node_id}&depth=1` |
| Ask with a result | `/ask?q=...` (question echoed; results re-fetched, never cached in URL) |

Filters, sort, lens, and open-drawer state are query params (shareable, back-button-safe). **Never** put tenant, credentials, or PII in the URL (§7). Ask questions are re-run server-side on load, not restored from a stale cached answer.

---

## 4. The Needle-in-Haystack System

This is the product's core UX challenge: an EA needs _one_ unsupported runtime out of thousands of facts. Finding is not one feature — it's a coordinated system of **rank → filter → search → cluster → disclose**.

### 4.1 Rank first, always (the anti-hairball stance)

The default answer to "what matters?" is a **priority-sorted list**, not exploration. Priority is a first-class score in the contract (`rankedItem.priority` = business importance × viability gap × opportunity × confidence ÷ effort, spec §31). The estate and modernization surfaces open pre-sorted by it. **Scanning a sorted table is fast; exploring a 10k-node canvas is not** — this is the whole thesis of the 20-minute test.

### 4.2 Faceted filtering, driven by the ontology

Filters are generated from ontology dimensions and the assessment dimensions in `ONTOLOGY.md`, so they stay in sync with the data model:

- **Domain / namespace** (Business, Enterprise, Technology, OSS, Deployment, Intelligence).
- **Assessment dimension** (supportability, security, ecosystem health, runtime compatibility, … — the 13 dimensions).
- **Confidence band** (HIGH / MEDIUM / LOW).
- **Freshness** (FRESH / STALE / UNKNOWN — from `freshness.status`).
- **Recommendation action** (RETAIN, REPLACE, CONSOLIDATE, … — the 10 actions).
- **Effort** (LOW / MEDIUM / HIGH / UNKNOWN).

Filters compose, are reflected in the URL, and show an active-filter summary chip-row that's one click to clear. Each filter shows a live count so the user never lands on an empty result by surprise.

### 4.3 Search & the command palette (`⌘K`)

Two complementary finders:

- **Ask your estate** (natural language) — for questions: "Which Tier-1 apps use unsupported runtimes?" Returns typed `askResponse` (`ANSWER` / `TABLE` / `GRAPH` / `UNSUPPORTED`), text-first with citations, graph only for traversal-shaped questions (§5.6).
- **Command palette** (structured jump) — for known-item finding: type an app, package, repo, or capability name → jump straight to its explorer. Fuzzy, keyboard-driven, entity-typed results with namespace badges.

The `⌘K` palette also exposes _actions_ (switch lens, toggle theme, go to Reviews) so power users never touch the mouse.

### 4.4 Lenses (saved views) **[NEW, operationalizes §2 personas]**

A **lens** = a named bundle of `{filters, sort, visible columns, default surface}`. Ships with persona presets (CTO Overview, EA Standardization, CISO Risk, Platform Drift) and supports user-defined lenses. Lenses are URL-encoded and shareable. This is how one product serves five personas without five apps — and how a saved investigation survives a page reload.

### 4.5 Progressive disclosure & clustering

The finding system is layered so the user pulls detail toward themselves rather than being buried:

- **List row** → name, domain badge, one-line status, confidence chip, priority. (Scan.)
- **Row expand / detail** → assessments, recommendations, evidence summaries. (Read.)
- **Evidence Drawer** → DECLARED/OBSERVED/INFERRED lines with source paths. (Verify.)
- **Graph lens** → bounded one-hop neighborhood; anything past one hop **clusters into a labeled aggregate** ("+212 repositories using this package") rather than rendering (spec §3.2, contract caps at 50 real nodes + `truncated`/`truncation_reason`). (Explore.)

Each layer is one interaction from the last, and each is reversible without losing place.

---

## 5. Screen-by-screen UX architecture

Each surface below specifies: **purpose · layout · states · key interactions · contract binding**. All bind to `contracts/v1` read models — the UI is built fixture-first and switches to live APIs with no component rewrite (Lane C exit criterion).

### 5.1 Software Estate (Home) — `getEstateSummary`

**Purpose:** the 20-minute first impression. Scored, filterable portfolio (spec §3.1).

**Layout:**
- **Top strip:** estate counts (applications, repositories, services, technologies) + distributions (runtime/deployment split) from `counts` + `distributions`. Rendered as compact stat tiles, not charts-for-charts'-sake.
- **Center:** ranked table/card grid of `ranked_items`. Columns: domain badge · mono name · sans one-line summary · confidence chip · right-aligned priority score. Default sort: Priority desc.
- **No graph by default.** Filter/sort/search are the primary interactions.
- **Status strip:** `coverage` + `as_of` (see §3.1).

**States:**
- _First-run / ingesting:_ coverage shows `repositories_scanned < total`; a non-blocking banner: "Scanning 43 of 118 repositories — results sharpen as coverage grows." The table populates progressively; already-scanned facts are actionable immediately (time-to-first-evidence, not time-to-complete — impl plan §6).
- _Empty (no org connected):_ a focused connect-your-org empty state (§8).
- _Loaded:_ ranked rows; each row → Application or Technology Explorer.
- _Stale:_ rows with `freshness.status = STALE` carry a subtle freshness marker; not an error, just honesty.

**Key interactions:** sort, filter, search, lens-switch, row → detail. Click a bridge-eligible field (package/capability) inside a detail → the _only_ path into Graph Explore.

### 5.2 Application Explorer — `getApplication`

**Purpose:** everything about one application, evidence-first (spec §3.3).

**Layout (workspace + evidence region):**
- **Header:** application name (mono), business-criticality context, freshness.
- **Business context strip:** `business_context` entities (Value Chain → Function → Process → Capability) as an ontology path — this is where an engineer sees _why_ their repo matters.
- **Viability radar / assessment panel:** `assessments[]` by dimension, each with categorical-or-score value, confidence chip, and citations. Radar is optional-decorative; the honest primary is a labeled dimension list.
- **Repositories / technologies / deployments:** `repositories`, `technologies`, `deployments` as entity chips; a package or technology chip is bridge-eligible → Graph lens.
- **Recommendations:** `recommendations[]` as recommendation cards (§6.5) — action, why (sans prose), migration stats (mono), counter-signals, confidence.
- **Evidence Drawer (right region):** opens on any score/badge → `getFactEvidence` → DECLARED/OBSERVED/INFERRED/CURATED/EXTERNAL_MEASURED lines.

**Signature interaction — the uncertain bridge:** next to a package, a badge like `[OSS bridge: request → HTTP Client — possible match · 0.71] [Confirm] [Reject]`, dashed border, no glow (0.71 < 0.85). Confirm/Reject → `POST /identity-assertions/{id}/review` with `expected_version` (optimistic concurrency; 409 handled, §7) — an audited mutation, not graph editing.

**Deployment lens (Platform Eng):** a toggle surfaces declared-vs-observed deployment as a side-by-side diff — the ontology explicitly keeps these distinguishable (`ONTOLOGY.md` deployment graph).

### 5.3 Technology Explorer — `getTechnology`

**Purpose:** internal usage × OSS intelligence × recommendation (spec §3.4).

**Layout:**
- **Internal Estate pane:** `internal_usage` (repository_count, application_count, repo list) — "how much of us depends on this."
- **OSS Intelligence pane:** `projects`, `packages`, ecosystem health, `alternatives`, `migration_patterns`. This is the first-class OSS graph, not enrichment (spec core thesis).
- **Registry sources:** `registry_sources[]` with visibility (PUBLIC/PRIVATE/UNKNOWN) and `tenant_scoped` — the private-registry honesty required by the contract. Never render a credential-bearing origin.
- **Recommendation Engine card:** follows the ontology recommendation rule — _capability actually used → candidate implementations → viability → org fit → migration evidence → recommendation_ (`ONTOLOGY.md`). Confidence categorical-first: `HIGH (0.94)`.

### 5.4 Viability & Modernization Dashboard — `listModernizationOpportunities`

**Purpose:** "what should we do, in what order?" (spec §3.5). The template for how the whole product should _feel_.

**Layout:**
- **Hero metric:** Technology Entropy score in `display` type (32px) — one of only two oversized numbers in the system (design language §type scale). A CTO reads it from across the room.
- **Ranked opportunities table:** `opportunities[]` (ranked items) with score components, confidence, effort, counter-signals, and citations. Sortable, filterable, lens-aware.
- **Grouping:** collapsible by action (CONSOLIDATE, REPLACE, …) or by value chain, so capital allocation maps to business structure.

### 5.5 Graph Explore mode (lens) — `getGraphNeighborhood`

**Purpose:** the bounded "magic," scoped (spec §3.2). Entered only from a bridge node.

**Rules (contract-enforced):**
- Renders a **server-bounded** response: `nodes` (≤50), `edges`, optional `highlighted_path`, plus `truncated`/`truncation_reason`. The client never fetches the full estate.
- Beyond one hop → aggregate cluster nodes (`aggregate: true`, `member_count`), labeled "+N …".
- **Domain-colored, badge-labeled panels;** confirmed bridge (`review_state: CONFIRMED`, confidence ≥ 0.85) = solid 2px stroke + amber pulse _only while selected_; unconfirmed (`POSSIBLE`) = 1.5px dashed neutral, no motion, "possible match."
- **Read-only:** no connect/delete/drag-persist. The only mutations are Confirm/Reject on a bridge (audited API call).
- **Linked selection (Zustand):** selecting a node in the canvas highlights it in the evidence inspector and vice-versa — coordinated multiple views, not isolated tabs (spec §2 rendering model).
- **Exit (Esc) returns to entry point.** A lens, not a page.

**Built on:** `packages/graph-ui` — the Ladder-derived React Flow + Dagre kernel, stripped to read-only, re-themed to Strata, with Apache NOTICE preserved (impl plan §7).

### 5.6 Ask Your Estate — `askEstate`

**Purpose:** natural-language finding and explanation (spec §3.6). Text-first, always cited.

**Response routing by `result_kind`:**

| `result_kind` | Render |
|---|---|
| `ANSWER` | Prose answer + citation chips (each → Evidence Drawer). No graph. |
| `TABLE` | Answer + `rows[]` as a sortable table; links into the relevant explorer. |
| `GRAPH` | Answer + inline `graph_highlight` (a bounded `graphNeighborhood`) with the traversed path highlighted. |
| `UNSUPPORTED` | Honest "I can't answer that from the estate" + suggested rephrasings. Never fabricates. |

**Citations are non-negotiable:** the agent explains reasoning in text with citations (spec §36); a graph highlight is an _addition_ for traversal questions, never a replacement. The NL layer selects deterministic queries and explains results — it never invents estate facts (impl plan §8).

**Conversation model:** a running thread with `context_entity_ids` carried from the current surface (e.g. asking from Billing API pre-scopes to it). Streamed responses (SSE) for perceived speed.

### 5.7 Reviews (identity-assertion queue) **[NEW, operationalizes the review contract]**

**Purpose:** a dedicated home for the human-in-the-loop backlog — every `POSSIBLE` bridge awaiting Confirm/Reject. Turns a scattered set of uncertain joins into a workable queue (sorted by how much each join affects downstream scores). Each item shows the two entities, the confidence, the evidence, and Confirm/Reject with a required rationale (contract requires `rationale`). This is the "outcome feedback loop" (spec §50.6) given a real surface.

---

## 6. Design System (Strata) & component architecture

### 6.1 Token pipeline (source of truth → code)

`strata-design-tokens.json` (DTCG format) is the single source. The pipeline:

```
strata-design-tokens.json  ──(Style Dictionary)──►  CSS custom properties (:root + [data-theme=dark])
        │                                       └──►  TS typed token exports (packages/design-system)
        └──(Tokens Studio)──► Figma variables (design ↔ code parity)
```

**Action item flagged by impl plan P2:** the `confidence` block and `text.primary` alias are mode-ambiguous and not in the same token schema as the rest. **Normalize these before wiring Style Dictionary** — resolve `text.primary` per-mode and express confidence thresholds as data, not color tokens (confidence is _not_ a color, design language §color). This is a prerequisite, not a nice-to-have.

### 6.2 Package boundaries (matches existing repo scaffold)

| Package | Owns | Depends on |
|---|---|---|
| `packages/design-system` | Strata tokens (generated), primitives (Badge, Chip, Button, Table, Drawer, Card, Input), theme provider, icon set (Tabler outline), type styles. Storybook lives here. | nothing app-specific |
| `packages/graph-ui` | Read-only bounded-graph kernel (React Flow + Dagre), StackGraph node/edge types, domain theming, uncertain-bridge rendering, linked-selection store. | design-system tokens only — **no LGIR/YAML/compiler types** (impl plan §7) |
| `packages/shared` | Contract-generated TS types (from `read-models.schema.json`), API client, view-model mappers, fixture loaders, i18n message catalog utilities. | contracts/v1 |
| `apps/web` | Next.js shell, routing, surface composition, data fetching, auth/session boundary. | all three packages |

This mirrors the folders that already exist (`packages/design-system`, `packages/graph-ui`, `packages/shared`, `apps/web`) — the plan fills them, it doesn't restructure.

### 6.3 The Strata component inventory (V0)

Grouped by the design-language component principles:

**Trust primitives (the distinctive layer):**
- **DomainBadge** — pill, mono two-letter code (`ENT`/`OSS`/`BIZ`/`INT`/`DEP`), 100-tint fill + 800-tint text. Text label always present, never color-only (accessibility + B/W print).
- **ConfidenceChip** — 3-segment bar (▮▮▮/▮▮▯/▮▯▯) + label; neutral ink except LOW (red). Decimal on hover/inspect.
- **BridgeConnector** — solid + selected-pulse (confirmed) vs dashed static (unconfirmed). The system's one novel interaction.
- **EvidenceRow** — mono assertion-class tag + mono source path + one line of sans description.
- **FreshnessMarker** — FRESH/STALE/UNKNOWN, subtle.

**Layout & data:**
- **RankedTable** (the default reading surface), **StatTile**, **RecommendationCard** (raised, 4px domain-colored left border, confidence top-right), **EvidenceDrawer**, **NodeInspector**, **FilterBar**, **CommandPalette**, **AskThread**, **LensSwitcher**, **Breadcrumb (ontology path)**, **StatusStrip**.

**States every component must implement (§8):** default, hover, focus-visible, loading (skeleton), empty, error, disabled, stale, reduced-motion.

### 6.4 Typography as semantics (design language §"one idea")

Enforced at the component level, not left to authoring discipline:
- **IBM Plex Mono** — raw facts: file paths, package names, node/graph labels, confidence decimals, scan IDs, evidence source lines. (Any value that "came from a scan.")
- **IBM Plex Sans** — reasoning/narrative: headings, recommendation "why," INFERRED assessments, UI chrome.

Components take a `semantic` prop (`fact | narrative`) so the font choice is structural, not a per-use decision. Fonts self-hosted (portability + privacy — no Google Fonts call from an enterprise tool; §7, §8.5).

### 6.5 Visual restraint budget (hard limits, enforced in review)

- **5 hues total** (4 domain + 1 danger). A sixth hue requires a design-council decision.
- **2 elevations** (flat + raised).
- **1 ambient motion** (bridge pulse, selection-scoped, reduced-motion-aware).
- **14px body** default (density); 32px `display` reserved for exactly two numbers (entropy, viability delta).
- **8px grid** (4/8/12/16/24/32/48/64).

These are lint-able (§9.6) so drift is caught in CI, not code review.

---

## 7. Data & state architecture

### 7.1 Fixture-first, contract-bound (Lane C's whole premise)

The UI is built against `contracts/v1/fixtures/*` from day one and switches to live read APIs **without component rewrites** (impl plan Lane C exit gate). Mechanism:

```
read-models.schema.json ──(json-schema-to-ts)──► generated TS types (packages/shared)
contracts/v1/fixtures/*  ──► MSW handlers (dev/test) ◄──► same API client ──► live /api/v1/* (prod)
```

- **Generated types** — the schema is the source of truth for TS types; regenerated in CI so a contract change breaks the build, not production.
- **MSW (Mock Service Worker)** serves fixtures in dev/test using the exact `openapi.json` routes. Flip one env flag to point at the live API. Components never know the difference.
- **Contract tests** — every fixture validates against the schema in CI (the foundation already does this via `npm run validate`; the UI extends it to view-model mappers).

### 7.2 View models — never bind components to raw read models directly

A thin mapper layer (`packages/shared`) converts read models → view models. This is the seam that absorbs contract evolution and computes presentation-only derivations (e.g., relative "3 days ago" from `observed_at`, domain→color lookup, confidence→segment count). Components consume view models; contract changes touch mappers, not 40 components.

### 7.3 State management

| State kind | Tool | Notes |
|---|---|---|
| Server cache (read models) | TanStack Query | dedup, background refetch, stale-while-revalidate — matches `freshness` semantics. |
| Linked selection (graph ↔ evidence ↔ inspector) | Zustand | the coordinated-multiple-views store, reused from Ladder pattern (impl plan §7). |
| URL state (filters/sort/lens/drawer) | Next.js router + search params | shareable, back-button-safe (§3.4). |
| Ephemeral UI (open menus, focus) | local component state | never global. |

Deliberately **no global app store as a dumping ground** — server state lives in the query cache, shareable state lives in the URL, cross-panel selection lives in one small Zustand store. This keeps state debuggable and calm.

### 7.4 Real-time & freshness

- **SSE** for Ask streaming and for ingestion-progress on first-run (coverage climbing).
- **TanStack Query background refetch** keyed to `freshness` — a STALE read model triggers a quiet refetch, not a spinner.
- **Optimistic concurrency** on the only mutation (`reviewIdentityAssertion`): send `expected_version`; on `409` show a "this was reviewed by someone else — reload" reconciliation, never a silent overwrite (contract defines 409).

### 7.5 Rendering strategy (Next.js)

- **App Router**, server components for the shell/static chrome, **client boundary** for interactive surfaces (graph, tables, drawers) — the graph package is explicitly client-only (impl plan §7).
- **Streaming SSR** for the estate table so the first ranked rows paint fast (20-minute test = time-to-first-evidence).
- **No SSR for the graph lens** — it's an opt-in client island.

---

## 8. Cross-cutting quality

### 8.1 Accessibility — WCAG 2.2 AA as a build gate, not an audit afterthought

The design language already bakes in the hardest wins; this makes them systematic:

- **Never color-only.** Every domain encoded by badge _text_ + color; confidence by _bar + label_ + color. Survives colorblindness and B/W print (design language §color). This is already a design rule — we enforce it in the linter (§9.6).
- **Contrast:** neutrals and ramps chosen for AA; the "no black text on colored fill" rule is enforced (800/900 stops for text-on-fill). Verify every token pair with automated contrast checks in CI.
- **Keyboard-first:** the tool is used under pressure — full keyboard operability. `⌘K` palette, focus-visible rings (Strata `control` radius), roving tabindex in tables, Esc closes drawer/lens, arrow-key graph traversal. No keyboard trap in the graph canvas (a known React Flow risk — provide a list-mode fallback for the neighborhood).
- **Screen readers:** the graph has a **text-equivalent** — the neighborhood is also a described list ("axios 1.7.9, TECHNOLOGY, depends-on billing-svc, confidence HIGH"). Tables use proper semantics; live regions announce Ask streaming and filter-result counts.
- **Motion:** `prefers-reduced-motion` disables the bridge pulse and migration animation (design language §motion) — wired at the token/provider level so no component can opt out.
- **Targets & density:** 14px body is dense _but_ interactive targets meet 24×24 CSS px minimum (WCAG 2.2 §2.5.8); dense tables use full-row hit areas.
- **Reduced-cognitive-load:** consistent layout, no surprise motion, honest empty/error states = calm is an accessibility feature.

A dedicated `/accessibility-review` pass (the `design:accessibility-review` skill) runs before each surface's handoff.

### 8.2 Localization & internationalization

Built in from the first component, because retrofitting i18n is the classic enterprise-tool failure:

- **Externalized copy:** all narrative strings in a message catalog (`packages/shared`), keyed, with ICU MessageFormat for plurals/gender/number. Zero hardcoded UI strings — enforced by lint.
- **What stays untranslated (deliberately):** raw facts. Package names, file paths, node keys, purls, evidence source lines are mono _data_, not prose — they are never localized (this is another payoff of the mono/sans split: the translation boundary equals the typography boundary).
- **Locale-aware formatting:** numbers, dates (`observed_at`/`as_of`), relative times, and confidence decimals via `Intl` — a CTO in Frankfurt sees `19.08.2026` and `0,94`.
- **RTL readiness:** logical CSS properties (`margin-inline`, `padding-block`), no hardcoded left/right; the three-region shell mirrors cleanly. The graph lens handles RTL via canvas transform, tested early.
- **Expansion tolerance:** layouts tested at +40% string length (German/Finnish) — no truncation of meaning, tables reflow gracefully.
- **Pseudo-localization** in CI to catch un-externalized strings and clipping before translators are involved.

### 8.3 Security — the UI is a strict, minimal-trust client

The contracts encode hard security rules; the UI must honor every one:

- **Tenant is never client-supplied.** It comes from the authenticated session, is displayed read-only in the top bar, and is **never** a query param, body field, or URL segment (contract: "Tenant identity comes from authentication/session context. It is never accepted as an API query or body field"). The client cannot switch tenants by editing a URL.
- **No credentials ever reach the UI.** Read models are guaranteed free of tokens/passwords/credential-bearing URLs (contract §31). The UI additionally **never renders a raw `origin` that could carry auth** for private registries — it shows `registry_key` + visibility, and treats `origin` as display-sanitized. Defense in depth: the client assumes a read model _could_ leak and refuses to echo credential-shaped strings.
- **Mutations are audited & authorized:** the only writes are `reviewIdentityAssertion` and (future) recommendation status changes. Each requires rationale, carries `expected_version`, and is subject to the backend's approve/execute permissions (spec §38). The UI must gate Confirm/Reject behind the user's role — surface it disabled with a reason if the user lacks permission, never as a dead button.
- **RBAC in the UI [NEW, anticipating spec §38]:** a capability map derived from the session drives which actions render. The tiers are **view → review → execute → admin**, least-privilege by default; the UI degrades gracefully for lower roles (an unavailable action renders disabled with a reason, never as a dead control). **Admin is an expanded-capability tier, not just "more buttons":** admins get surfaces and controls other roles never see — the full Admin area (§11.2), provider/AI configuration, member/role management, connection lifecycle, and deeper observability (raw scan diagnostics, audit export). The same three-region shell hosts it, so an admin's expanded experience is a superset of the standard one, not a separate app.
- **AuthN:** SSO/OIDC (enterprise expectation) handled at the Next.js edge/middleware; session tokens httpOnly, never in JS-readable storage. CSRF protection on the mutation routes.
- **CSP & supply chain:** strict Content-Security-Policy, self-hosted fonts (no third-party font/CDN calls — an enterprise privacy expectation), Subresource Integrity, dependency pinning. The tool that _maps_ supply-chain risk must not _be_ one.
- **PII discipline:** no PII in URLs, logs, or client analytics. Ask questions may contain sensitive intent — they're sent over the session, never cached in shareable URLs (§3.4).

### 8.4 Performance & portability

- **Budget:** first ranked rows visible < 1.5s on the estate surface (time-to-first-evidence); interaction-to-paint < 100ms for sort/filter (client-side on already-loaded page); graph lens < 500ms to first render (it's ≤50 nodes by contract).
- **Virtualized tables** for the estate/modernization lists (thousands of rows) — render only what's visible.
- **Bounded graph is a performance _feature_:** the ≤50-node contract cap means the canvas is never the bottleneck. No full-estate layout, ever (impl plan §7: "do not reuse full-estate layout").
- **Code-splitting:** the graph package and Ask thread are lazy islands; the estate table is the only thing on the critical path.
- **Portability:** the UI is a standard Next.js app — deployable to any Node host or container (matches `infrastructure/`), no proprietary platform lock-in. Design-system and graph-ui packages are framework-portable (they could power a future embed/widget). Tokens are DTCG-standard, so the visual language survives a framework change.
- **Offline-tolerant** where honest: cached read models render with a clear "as-of" and STALE marker rather than a blank screen; mutations require connectivity and say so.

### 8.5 Maintainability

- **Contract-generated types** mean the compiler enforces contract conformance — a schema change surfaces as red squiggles, not a runtime surprise.
- **Fixture-first + MSW** means the entire UI is developable and testable with zero backend running — critical for parallel lanes (Lane C independent of A/B/D).
- **Storybook** for every Strata component with all states (§6.3) — the visual contract, and the surface for the `design:design-system` audit skill.
- **Token linting** (§9.6): no hardcoded colors/spacing/fonts; every value traces to a token. This is what keeps "restraint" from eroding over 18 months.
- **One mental model to onboard:** the ontology drives IA, filters, node types, and breadcrumbs — a new engineer learns the domain model once and the UI is legible.
- **ADRs:** each significant UI decision (state tooling, graph kernel reuse, i18n approach) recorded via the `engineering:architecture` skill so future maintainers know _why_.

---

## 9. Delivery plan

### 9.1 Phasing overview

Four phases. Each is independently demoable and maps to the Lane C integration gate ("switches fixtures to live read APIs without component rewrites").

| Phase | Theme | Exit criterion |
|---|---|---|
| **P0 — Foundation** | Tokens, shell, contract types, fixture harness | Strata renders in light+dark; `⌘K` shell navigates; all fixtures type-check and load via MSW. |
| **P1 — Scan** | Estate, Modernization, Application/Technology explorers (read-only), Evidence Drawer | The 20-minute test passes on fixtures: a user finds ≥5 material facts by scanning + reading evidence, **no graph required**. |
| **P2 — Explore & Ask** | Graph lens, uncertain bridges + Reviews queue, Ask thread | Traversal question → bounded graph highlight; Confirm/Reject round-trips through the review contract. |
| **P3 — Live & harden** | Flip to live APIs, a11y/i18n/security gates, performance budgets | Live estate loads within budget; WCAG AA, pseudo-loc, and security checks green in CI. |

### 9.2 P0 — Foundation (the enabling layer)

1. **Normalize tokens** (impl plan P2 fix): resolve `text.primary` per-mode, express confidence as data. Wire Style Dictionary → CSS vars + TS.
2. **Scaffold the monorepo** into existing folders: `apps/web` (Next.js App Router), `packages/design-system`, `packages/graph-ui`, `packages/shared`. Turborepo/pnpm workspace (match foundation's Node/ESM setup).
3. **Generate contract types** from `read-models.schema.json`; set up MSW with `contracts/v1/fixtures/*` on `openapi.json` routes.
4. **Build the shell:** three-region layout, top-bar `⌘K`, left rail, status strip, theme provider (light/dark, reduced-motion), i18n provider, self-hosted IBM Plex.
5. **Storybook** with the trust primitives (DomainBadge, ConfidenceChip, BridgeConnector, EvidenceRow) — the distinctive layer first, because it's the identity.

### 9.3 P1 — Scan (deliver the 20-minute test)

Build, in order of test-value: **Software Estate → Evidence Drawer → Application Explorer → Technology Explorer → Modernization Dashboard.** Read-only. All bound to fixtures. Faceted filters, lenses (persona presets), virtualized tables, RankedTable + RecommendationCard. **Gate: run the 20-minute test on fixtures — if the user needs the graph to get their first "I didn't know that," we've failed §49 and must fix the scan surfaces, not add graph.**

### 9.4 P2 — Explore & Ask

1. **`packages/graph-ui`:** port the Ladder React Flow + Dagre kernel, strip to read-only, re-theme to Strata, add domain badges / dashed uncertain bridges / selection-only pulse / clustering / truncation UI / linked-selection store / list-mode a11y fallback. Preserve Apache NOTICE.
2. **Graph Explore lens** wired to `getGraphNeighborhood`, entered only from bridge nodes, Esc-to-return.
3. **Uncertain-bridge flow + Reviews queue** → `reviewIdentityAssertion` with optimistic concurrency and 409 handling.
4. **Ask thread** → `askEstate` with `result_kind` routing, SSE streaming, citation chips, `UNSUPPORTED` honesty.

### 9.5 P3 — Live & harden

1. Flip MSW → live `/api/v1/*` (one flag). Verify no component rewrite needed (the Lane C promise).
2. First-run ingestion UX: progressive coverage, SSE progress, "results sharpen" banner.
3. **Quality gates green:** WCAG 2.2 AA (automated + manual SR pass), pseudo-localization, RTL smoke, security review (`/security-review`), performance budgets, token linting.
4. Responsive decision below 1440px (spec open question §7) — see §10.

### 9.6 Quality gates (CI, every PR)

- **Types:** contract types regenerated; build fails on drift.
- **Contract tests:** fixtures validate; view-model mappers round-trip.
- **Token lint:** no hardcoded color/space/font/radius; 5-hue / 2-elevation / 1-motion budget enforced.
- **a11y:** axe on every Storybook story + key flows; contrast check on token pairs; keyboard-nav smoke test.
- **i18n:** pseudo-loc build passes (no clipped/un-externalized strings).
- **Visual regression:** Storybook snapshots (light + dark).
- **Security:** CSP present, no credential-shaped strings rendered, no tenant/PII in URLs (lint rule).
- **Perf:** bundle-size budget on the estate critical path; graph package stays lazy.

### 9.7 Testing strategy

- **Unit:** view-model mappers, confidence/domain derivations, i18n formatting.
- **Component:** Storybook interaction tests across all states.
- **Contract:** fixtures ↔ schema ↔ generated types (extends foundation `npm run validate`).
- **E2E (Playwright):** the 20-minute test as an automated flow on fixtures; the uncertain-bridge round-trip; Ask routing; keyboard-only traversal of a surface.
- **Manual:** screen-reader pass per surface; screen-share-in-daylight legibility check (light mode contrast under projector).

---

## 10. Open decisions (need a human call)

These are genuinely product/leadership decisions, not things I should default silently:

1. **Responsive floor — RESOLVED (2026-08-19):** full mobile responsiveness **is** in scope. Implemented via a single `768px` breakpoint: above it, the persistent three-region shell; at/below it, the left rail becomes an **off-canvas drawer** (hamburger toggle + dimmed backdrop, Esc/route-change closes it), the top bar condenses (brand mark only, compact Ask, no ⌘K hint), and the **RankedTable reflows to stacked cards** (CSS Grid on the row — no horizontal table scroll). Verified at 375/768/1280 with zero document-level horizontal overflow. The bounded **graph lens** (Phase 2) will still offer a list-mode fallback on mobile rather than a pannable canvas (matches the a11y list-equivalent in §8.1).
2. **Confirm/Reject permissioning (spec §7 open Q):** does reviewing an uncertain bridge require an elevated role (touching spec §38 approve/execute)? Recommendation: **yes — gate it behind a "reviewer" capability**, view-only users see it disabled with a reason. Confirms the RBAC model in §8.3.
3. **Clustering threshold for the one-hop boundary (spec §7 open Q):** by degree, by domain count, or user-configurable? Recommendation: **server-decided, returned as aggregate nodes** (already in the contract) — the UI shouldn't own this heuristic. Confirm the backend owns clustering, not the client.
4. **Ask conversation persistence:** are Ask threads saved per-user (history, revisit) or ephemeral? Affects storage, privacy (§8.3), and whether threads are a fourth kind of shareable state. Recommendation: **ephemeral in V0, opt-in saved history later.**
5. **First-run without full coverage:** confirm the product _wants_ the estate to render partial (time-to-first-evidence) vs. wait for `COMPLETE`. The impl plan implies partial; this plan assumes it. Worth an explicit yes.
6. **AI model configurability — RESOLVED (2026-08-19):** model/provider is **admin-configurable across OpenRouter, OpenAI, and Claude (Anthropic)**, with write-only reference-only key handling and per-provider data-residency posture surfaced (§11.2C). Remaining sub-question for the backend owner: what does the model-list endpoint return per provider (so the UI populates the model field dynamically rather than hardcoding)?
8. **Reviews needs two contract additions (discovered during build):** (a) the graph `graphEdge` read model carries no `identity_assertion_id`, so reviewing a `POSSIBLE` bridge from the graph can't address the right assertion — the UI currently uses the edge `id` as a stand-in; and (b) there is no list endpoint for pending uncertain bridges, so the Reviews queue can't be populated in live mode. Recommendation: **add `identity_assertion_id` (+ `assertion_version`) to `graphEdge`, and a `GET /identity-assertions?review_state=POSSIBLE` list read model.** Until then Reviews works in fixture mode only.
7. **Settings vs. env boundary:** some of what belongs in "Settings" (model endpoint, secrets, allowlists) is really **deployment/env config** owned by the operator, not tenant admins. Direction confirmed: **the UI configures tenant-scoped policy (schedules, roles, connections, provider/model + keys, residency posture); pure infrastructure config stays in `infrastructure/` env, surfaced read-only in Admin for transparency.** Open sub-question: for a self-hosted deployment, is the provider key a _tenant_ secret (entered in the UI) or an _operator_ secret (env-only, UI shows read-only status)? Recommendation: **support both — UI-entered by default for SaaS; env-provided keys render as read-only "configured by operator" for self-hosted.**

---

## 11. Admin, Settings, Onboarding & Observability **[NEW — added in response to the settings/env question]**

The five read surfaces answer "what's in my estate." This section covers the surfaces that get data _in_, keep it _fresh_, and make the system _tunable and transparent_. The governing idea: **split "settings" into three concerns that are often wrongly merged** — tenant policy (UI-configurable), deployment/env config (operator-owned, read-only in UI), and system observability (a status surface, not settings).

### 11.1 The three-concern split (get this right or it rots)

| Concern | Who owns it | Where it lives | Example |
|---|---|---|---|
| **Tenant policy** | Workspace admin | Admin area (writable, RBAC + audited) | scan cadence, roles, which orgs are connected, data-residency posture |
| **Deployment/env config** | Operator / infra | `infrastructure/` env; **read-only** mirror in Admin | model endpoint, secrets, origin allowlists, DB/AGE connection |
| **Observability** | Everyone (role-scoped) | Estate Health + Activity surfaces (read-only) | coverage, enrichment progress, scan run history, audit log |

The UI **writes** tenant policy, **displays** env config (so a buyer can verify posture without SSH), and **reports** observability. Secrets are never entered or shown.

### 11.2 Admin area (workspace-scoped, role-gated, audited)

Entered from the rail footer; every mutation here is an audited action behind an `admin` capability (§8.3). Sections:

**A. Connections (the onboarding home)**
- **GitHub App install / OAuth** — the connect-your-org flow. The UI orchestrates the provider flow and stores only a `connector_account.credential_reference` (contract §31). **The UI never accepts, displays, or transmits a raw token, PAT, or password** — this is a hard security rule, not a preference (see §7 and the platform safety boundary on credentials). Read-only scopes per spec §425; broad PATs discouraged (spec §427).
- **Registry connectors** (npm/PyPI/private) — same reference-only credential model; shows `registry_key`, visibility (PUBLIC/PRIVATE/UNKNOWN), origin allowlist, and `redact_auth: true` posture. Never renders a credential-bearing origin.
- **Connection health** — connected/expired/failed, last successful sync, webhook delivery status (ties to `webhook_delivery`). A broken connection is the #1 cause of stale data, so it's surfaced loudly here and quietly in the Status Strip.
- **State handling:** disconnect is a destructive, confirmed action; re-auth is a guided flow; a connection in error shows the _reason_ and the fix, never a dead end.

**B. Scan & Refresh**
- Per-connector **cadence** (the target scheduler from impl plan §194: "the scheduler creates work; workers never invent their own untracked loops"), **manual rescan** trigger, and **reconciliation** ("re-check after missed webhook", impl plan §394).
- Per-provider **quota / freshness state** and backoff visibility, so an admin understands _why_ a refresh is throttled rather than assuming failure.

**C. Intelligence / AI** (admin-only, expanded-capability — decision §10.6 resolved: configurable)
- **Provider & model — configurable across OpenRouter, OpenAI, and Claude (Anthropic).** The UI presents: (1) a **provider** selector, (2) a **model** field for that provider that is **populated from a backend-supplied list, never hardcoded** (model catalogs change constantly — a hardcoded dropdown is stale within weeks and is a maintenance trap), and (3) provider-scoped options only where they're safe to expose. Selecting a provider changes the residency and key-handling context below.
- **API-key handling — write-only, reference-only.** A provider key (OpenAI / OpenRouter / Anthropic) is a secret. The admin enters it into a **masked, write-only field**; it is stored server-side and referenced only by `credential_reference` (same model as the GitHub/registry connectors), **never read back to the client**. After entry the UI shows status only — `configured` + a fingerprint/last-4, plus "rotate" and "remove" actions — and **never re-displays the raw key**. This keeps the "UI never displays a raw secret" rule intact even though the UI is now where the key is _collected_.
- **Data-residency / privacy posture — surfaced per provider, because it differs sharply.** This is the control a CISO cares about most: choosing a provider changes where estate data goes. The UI must state the egress implication of each choice plainly — in particular that **OpenRouter is a broker that forwards prompts to upstream third-party providers**, giving it the widest data-egress surface of the three, versus a direct OpenAI or Anthropic connection. Show the active posture as a first-class, verifiable statement (not buried fine print), and gate a residency-widening change behind an explicit confirm. This preserves the trust thesis: the AI selects deterministic queries over facts and **never generates estate facts from model memory** (impl plan §296) — so this screen governs _privacy and reproducibility_, not "creativity" knobs.
- **Method-version pinning** — assessments/recommendations carry `method_version`; an admin can see and pin which version is live, so scores are reproducible and a provider/model change is a visible, audited event (§11.5), never silent drift.
- **Optional guardrails to expose** (as the backend supports them): per-tenant token/cost budget and a "test connection" check that verifies the key + model without sending estate data.

**D. Members, Roles & SSO**
- The capability map (view / review / execute) that gates Confirm/Reject and future execute actions (§8.3, spec §38). SSO/OIDC configuration. Least-privilege defaults.

### 11.3 Personal Settings (user-scoped, no special role)
- Theme (light/dark/system), locale, **reduced-motion override** (in addition to OS preference), density, default lens.
- **Saved lenses** management; **Ask history** (only if persistence is enabled — open decision §10.4).
- Notification preferences (e.g., "tell me when a Tier-1 app gains a new HIGH-confidence recommendation").

### 11.4 Estate Health (observability surface — NOT settings)
Promotes the Status Strip (§3.1) into a full read-only surface, because "why is this number stale/partial?" deserves a real answer:
- **Coverage** — `repositories_scanned / total`, `facts_with_evidence_ratio` (from `estateSummary.coverage`), trended over time.
- **Enrichment status** — deps.dev/OSV/registry adapter progress and per-source **freshness** (`freshness.status`), including which packages are enriched vs. only observed (impl plan §190: enrichment limited to observed/curated).
- **Scan runs** — history of `COMPLETE`/`PARTIAL` snapshots, file/fact counts, skipped limits, structured diagnostics (impl plan §249). A `PARTIAL` run is explained, not hidden.
- This is where a CTO learns to trust (or distrust) a number _before_ acting on it — a first-class part of the evidence-first promise.

### 11.5 Activity & Audit (observability — compliance-facing)
- Chronological log of state-changing actions: bridge Confirm/Reject (with rationale + actor + `version`), recommendation status transitions, connection changes, role changes, scan triggers.
- Filterable by actor, entity, action; exportable for compliance (CISO value).
- Distinct from the **Time Slider** (§4 / spec §"time is structural"), which is a _viewing lens_ over the bitemporal data ("show me the estate as of last quarter"), not an audit of who-did-what. Keep the two conceptually and visually separate.

### 11.6 What this adds to the delivery plan
These surfaces slot into the existing phases without disrupting the 20-minute test:
- **P0:** Connections onboarding stub + the empty-state "connect your org" flow (the estate is empty until this exists — so a minimal Connections is actually a P0 dependency, not a late add).
- **P1:** Estate Health surface (extends the Status Strip already in P0/P1).
- **P2:** Scan & Refresh controls, Activity/Audit (pairs with the Reviews queue and bridge mutations landing in P2).
- **P3:** Members/Roles/SSO, Intelligence/AI posture, env read-only mirror — these harden alongside the security gate.

**Net:** yes, build it — but as a small, role-gated **Admin area + two observability surfaces + personal Settings**, not a single catch-all screen, and with a hard line that the UI configures _policy_ and never handles _secrets_.

---

## Appendix A — Contract → surface binding (quick reference)

| Surface | Endpoint(s) | Primary read model |
|---|---|---|
| Software Estate | `GET /estate/summary` | `estateSummary` |
| Application Explorer | `GET /applications/{id}`, `GET /facts/{id}/evidence` | `applicationDetail`, `evidenceDetail` |
| Technology Explorer | `GET /technologies/{id}` | `technologyDetail` |
| Modernization | `GET /modernization` | `modernizationList` |
| Graph Explore lens | `GET /graph/neighborhood` | `graphNeighborhood` |
| Ask | `POST /ask` | `askResponse` |
| Reviews / uncertain bridge | `POST /identity-assertions/{id}/review` | `identityReviewResult` |

## Appendix B — Traceability

Every section maps to a source: principles → design-language + spec §2; IA → ontology + spec §46; screens → spec §3; components → design-language §component principles + tokens; data/state → contracts/v1 + impl plan Lane C/§7/§8; graph kernel → impl plan §7; security → CONTRACTS.md frozen rules + spec §38; success gate → spec §49. Extensions beyond source are marked **[NEW]**.
