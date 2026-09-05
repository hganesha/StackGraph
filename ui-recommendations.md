# StackGraph — UI Control Surface Review and Recommendations

> **Revised for Phase 2.** Part I below is the original review of the shipped
> control surface. **[Part II](#part-ii--impact-of-the-phase-2-plan)** assesses the
> Phase 2 backend plan (Enterprise Change Compiler, simulation, change memory, agent
> control plane) against it and states the required UI changes. Where the two differ,
> **Part II wins** — it revises R1, R3, R4, R5, R7, R8, R9 and R10, adds R11–R16, and
> replaces the sequencing table in §9. Read Part I for the diagnosis, Part II for the
> plan.

**Scope:** the UI control surface only — `apps/web`, `packages/design-system`,
`packages/canvas-ui`, `packages/graph-ui`. No backend, contract, or data-model
changes are proposed. Every recommendation below is buildable against read models
that already exist and are already reachable from `packages/shared/src/api/client.ts`.

**Constraint accepted throughout:** nothing currently in the product is removed,
renamed out of existence, or made harder to reach. Each recommendation either
*adds* a visual layer over data already rendered as text, or *reorganises* an
existing surface without dropping a control.

---

## 0. What was reviewed

| Surface | File | Lines |
|---|---|---|
| Shell, rail, top bar, status strip | `components/shell/*`, `design-system/StatusStrip.tsx` | ~450 |
| Estate (ranked + canvas) | `app/estate/EstateView.tsx`, `components/estate/FilterBar.tsx` | ~540 |
| Applications, Technologies, Repositories | `app/applications/**`, `app/technologies/**`, `app/repositories/**` | ~2,000 |
| Architecture canvas | `features/architecture/*`, `packages/canvas-ui/*` | ~2,300 |
| Business Map | `features/business-map/*` | ~4,700 |
| Ask / insight reports | `app/ask/page.tsx` | ~535 |
| Modernization | `app/modernization/page.tsx` | ~210 |
| Reviews, Scan health, Admin | `app/reviews`, `app/health`, `components/admin/*` | ~2,400 |
| Design system + tokens + glossary | `packages/design-system/*` | ~1,400 |

Read alongside `docs/strata-design-language.md`, `docs/stackgraph-ui-spec-v2.md`,
`docs/ux-copy-review.md` and `design-qa.md`.

---

## 1. Verdict

**The control surface is already better-reasoned than most enterprise software.**
Three things in it are genuinely rare and should be protected at all costs:

1. **Typography assigned by evidence class, not hierarchy.** Mono means "a scanner
   read this"; sans means "StackGraph concluded this." (`docs/strata-design-language.md`.)
   No other tool in this category encodes epistemic status in the typeface.
2. **A disciplined refusal to let colour carry meaning alone.** Every tone in
   `packages/canvas-ui/src/vocabulary.ts` ships with a text label, and confidence is
   deliberately a three-segment bar rather than a fifth hue.
3. **Vocabulary defined once, in code.** `packages/design-system/src/glossary/terms.ts`
   plus the `<Term>` component is a mechanism most design systems never build.

**And yet: there is not one picture in the entire product.**

A `grep` for `<svg`, `recharts`, `d3`, `sparkline`, `chart` across `apps/web` and
`packages` returns exactly one hit — the brand mark in `TopBar.tsx`. Outside the
React Flow node-link canvas, StackGraph renders **zero** data marks. Every quantity
in a system explicitly built to answer "where is the risk concentrated" is delivered
as a numeral in a table cell, a `<dl>` pair, or a chip:

- `technology_entropy` — computed per business capability, exposed at
  `/capabilities/footprints`, wired into `stackGraphClient` — and **rendered nowhere
  in the UI at all**. Zero call sites.
- The eight-stage reachability attenuation in `DeterministicInsightsPanel.tsx` — the
  single most differentiating idea in the product — is eight `<span>`/`<strong>` pairs
  in a row.
- Blast radius, a genuine traversal result, prints as
  `impact.entity_ids.join(" → ")` — a chain of raw UUIDs.
- The `display` type token (32px), reserved in the design language for "the two
  numbers meant to be read from across a room", is used once, on Scan health, for a
  repository count.

The product's own metaphor is **strata** — layers of business over applications over
code over packages over infrastructure, with evidence stacked underneath and time
stacked behind. The UI currently expresses that metaphor as a vertical list of
collapsible tables.

**The opportunity is not to add charts. It is to make the estate legible as a
shape.** Every recommendation below is a shape the competition structurally cannot
draw, because they do not hold the graph StackGraph holds.

---

## 2. The differentiating thesis

Snyk, Semgrep, SonarQube, Dependabot, Backstage, LeanIX and the rest all converge on
the same two screens: a list of findings, and a dependency tree. They converge
because they all hold the same object — *a repository*.

StackGraph holds a different object: **a business estate with evidence and time under
it.** Five pictures follow from that, and only from that. No competitor can draw any
of them.

| # | The picture | Why only StackGraph can draw it |
|---|---|---|
| 1 | **Capability heat grid** — business capabilities coloured by technology entropy, sized by footprint | Requires business-capability inference joined to package facts. Code scanners have no business layer; EA tools (LeanIX) have the business layer but no package-level truth. |
| 2 | **The attenuation funnel** — 1,240 present → 380 referenced → 91 reachable → 22 runtime → 12 deployed → 3 business-critical | Requires eight independent evidence classes on one finding. Scanners stop at "present in a lockfile". |
| 3 | **Blast radius ring** — concentric hops from a package outward to the business capability it eventually touches | Requires cross-domain traversal with per-hop confidence. Dependency trees stop at the repo boundary. |
| 4 | **Agent drift timeline** — what coding agents introduced into the estate this quarter, and whether entropy rose | Requires bitemporal facts. This is the founding premise in `README.md` and it is invisible in the UI. |
| 5 | **Estate stratum bar** — one always-visible strip showing all five domains, their coverage, and where evidence thins out | Requires a single unified model across Business/Enterprise/Technology/OSS/Deployment. |

If a CTO can screenshot exactly one of these five and put it in a board deck,
StackGraph has a category position nothing else in this market can copy.

---

## 3. Recommendations

### R1 — Capability Risk Heat Grid *(the flagship)*

**What.** A new peer view on Estate — `/estate?view=heat` — sitting beside "Ranked
list" and "Architecture canvas" in the existing `styles.viewSwitch` nav. A dense grid
where **each cell is one business capability**, its **fill** is technology entropy,
its **area** is application count, and a small numeral sits in every cell.

Toggle the fill between four measures, reusing the exact `CanvasControls` "Colour by"
segmented-radio pattern already built in `features/architecture/CanvasControls.tsx`:

| Colour by | Source field | Reads as |
|---|---|---|
| Spread | `technology_entropy` | "How many different ways do we do this one thing?" |
| Reuse | `reuse_signal` | "How much of this is shared versus rebuilt?" |
| Exposure | joined `systemic_risk` from `/graph-intelligence/risks` | "If this broke, how far does it go?" |
| Coverage | `evidence_coverage` from deterministic insights | "How much of this can we actually see?" |

**Why it differentiates.** This is the screen a CTO screenshots. "Order Fulfilment is
doing payments five different ways across nine applications" is a sentence no code
review tool on the market can produce, because none of them know what order
fulfilment is.

**Data already available — zero backend work.**
`GET /capabilities/footprints` → `CapabilityFootprintList` in
`packages/shared/src/contracts/read-models.ts:702` returns, per capability:
`application_count`, `repository_count`, `technology_count`, `technology_counts`,
`technology_entropy` (0–1), `reuse_signal`. The client method
`listCapabilityFootprints()` exists at `client.ts:931`/`2022`. **It has zero call
sites in `apps/web`.** The read model is already built and shipping, unused.

**Visual spec.**
- Squarified treemap, capability name inside the cell in sans, entropy as a two-digit
  numeral in mono bottom-right. Below ~64px, drop the numeral and keep the name; below
  ~32px, drop both and rely on hover/focus.
- Cell border stays the hairline `--sg-surface-border`. No shadows. No gradients.
- Click a cell → the existing capability detail path; hover/focus → the same content
  the ranked table row shows today, so no new information architecture.
- **Always render the legend**, inline and left of the grid, not in a popover.

**On the colour budget — this is the one place the system must extend, carefully.**
Strata deliberately allows five hues and states that colour never carries meaning
alone. A heat map is by definition a sequential encoding, so:
- Introduce **exactly one sequential ramp**, derived from the existing
  `--sg-color-domain-intelligence-*` violet ramp (100 → 700), because entropy is an
  *inference*, not a domain and not an error. **Do not use the danger red ramp** — red
  in Strata means LOW confidence or a genuine error, and high entropy is neither.
- The ramp is licensed **only** on surfaces where a legend is permanently visible
  (this grid, and R6's drift ribbon). It is banned in tables, chips, badges and cells
  elsewhere.
- Every cell carries the numeral, so the encoding is redundant and survives
  greyscale printing (the design language explicitly notes CTOs still print).
- Add a **"No colour"** option to the segmented control, exactly as
  `CanvasControls` already offers `{ value: "none", label: "Off", hint: "No colour —
  read the labels only." }`. The pattern is established; reuse it verbatim.

**Copy.** Title: *"Where the estate is most scattered."* Not "Technology entropy
heat map." The word "entropy" appears once, in the legend, with a `<Term>` gloss.

**Effort.** ~2 days. One new route, one treemap layout function (squarified treemap
is ~60 lines, no library needed), one legend component, one ramp added to
`tokens.css`. No API work.

---

### R2 — The Attenuation Funnel

**What.** Replace the eight-cell row in `components/insights/DeterministicInsightsPanel.tsx`
(the `styles.funnel` block, currently `<span>label</span><strong>value</strong>` × 8)
with a horizontal attenuation bar: one continuous track, eight segments, each segment's
width proportional to the count that survives to that stage, with the **drop** between
stages drawn as the negative space.

```
Present        ████████████████████████████████████████  1,240
Referenced     ████████████████████                        380
Reachable      █████                                        91
Runtime seen   ██                                           22
Deployed       █                                            12
In production  █                                             8
Internet-facing▌                                             3
Business-criticaI▌                                            3   ← act on these
```

**Why it differentiates.** This is the whole argument against every scanner on the
market, made in one glance. Snyk tells you about 1,240 things. StackGraph tells you
that three of them matter and shows you exactly where the other 1,237 fell away.
**The dropout is the product.** Right now the product's strongest claim is rendered
as a row of unstyled numbers where the eye cannot see the collapse at all.

**Data already available.** `DeterministicInsight["stages"]` — the eight keys are
already enumerated in the `STAGES` const at the top of the file. `null` already means
"unknown" and is already rendered distinctly (`styles.stageUnknown`).

**Visual spec.**
- Stages with `null` render as a **hatched** segment, never a zero-width one — an
  unknown stage must not read as "nothing survived here". Label: "Not checked".
- The last **non-null** stage gets a subtle end-cap and the eyebrow *"Act on these"*.
- The whole track keeps its existing `role="region"` and `tabIndex={0}`; add an
  `aria-label` that reads the attenuation as a sentence:
  *"1,240 present, narrowing to 3 business-critical across 6 checked stages;
  2 stages not checked."*
- Under 480px the track rotates to vertical rather than compressing.

**Copy.** Rename the stage labels once, everywhere (see §4): "Statically reachable"
→ "Reachable in code", "Deploy config" → "Deployed", "Public config" →
"Internet-facing", "Biz critical" → "Business-critical".

**Effort.** ~1 day, single component, pure CSS widths. Highest ratio of
differentiation to effort in this document.

---

### R3 — Blast Radius Ring (and a defect fix)

**What.** The blast radius drawer in
`components/graph-intelligence/GraphIntelligenceSummary.tsx` currently renders each
impact path as:

```tsx
<p className="sg-mono">{impact.entity_ids.join(" → ")}</p>
```

That is a chain of raw UUIDs shown to an executive. **This is a defect, not a style
preference** — it is unreadable to every persona in the spec.

Replace with a **concentric impact ring**: the subject at the centre, one ring per
hop distance, impacted entities placed on their ring, ring opacity carrying
`minimum_confidence`, and the arc to the outermost business capability drawn solid.
Beside it, the same paths as **named** breadcrumbs with the domain badge on each hop.

**Why it differentiates.** "This package, three hops out, touches Claims Settlement,
and here is the evidence for every hop" is the answer StackGraph exists to give. It
is currently one string-join away from being invisible.

**Data already available.** `getEntityBlastRadius` returns `impacts[]` with `target`,
`distance`, `minimum_confidence`, `entity_ids` and `supporting_fact_ids`. Names for
the intermediate hops can be resolved from the neighbourhood already fetched by
`useGraphNeighborhood`, or fall back to the truncated id as today.

**Visual spec.**
- Max 4 rings; anything deeper collapses to "+n further hops" with a count.
- Hop confidence uses the **existing** three-segment `ConfidenceChip`, not opacity
  alone, so the confidence encoding stays consistent with the rest of the product.
- Keep the existing per-hop `CitationChip` evidence buttons exactly as they are —
  they are the best thing in the drawer.
- `prefers-reduced-motion`: no ring draw-in animation.

**Effort.** ~1.5 days. Inline SVG, ~120 lines. The UUID fix alone is 20 minutes and
should ship immediately regardless of the ring.

---

### R4 — The Strata Bar (make the metaphor visible)

**What.** `StatusStrip` (`packages/design-system/src/components/StatusStrip.tsx`) is
always on screen and currently reads:

> Scanned 41 of 52 repos · 79% | With evidence 64% | As of 5 Sep 2026, 14:02 | contract 1.0.0

Promote it into a **five-layer stratum bar** — the product's own metaphor, drawn.
Five stacked hairline bands, top to bottom: Business, Enterprise, Technology, OSS,
Deployment. Each band's **fill length** is how much of that layer is populated and
evidenced. Where a layer thins, the band visibly thins.

**Why it differentiates.** Every tool has a coverage percentage. Nobody shows *which
layer of the stack the knowledge runs out at*. A band that is full at Technology and
empty at Business says, at a glance, "we know what you run, we don't yet know what it
is for" — which is precisely the onboarding state most customers are in, and precisely
the thing they need to be told without reading a paragraph.

**Data already available.** `EstateSummary.counts`, `EstateSummary.coverage`,
`EstateSummary.distributions` — all already fetched on every page by `useEstateSummary()`
inside `AppShell`.

**Visual spec.**
- Collapsed (default): 28px tall, five 3px bands side by side horizontally, with the
  existing text facts to their right. No taller than today.
- Expanded on click/focus: 5 stacked rows with counts, evidence ratio, and "as of"
  per layer. This is the natural home for the drill-down the Scan health page does today.
- **Delete `contract 1.0.0` from the user-facing strip.** A contract version is
  operator telemetry; move it to Scan health and to a `title` attribute.
- The strip is already `role="status"` with a good `aria-label` — keep both and
  extend the label to name the thinnest layer:
  *"Weakest layer: Business — 12 of 61 applications mapped to a capability."*

**Effort.** ~1 day.

---

### R5 — Agent Drift Timeline *(the founding premise, currently invisible)*

**What.** `README.md` opens by framing StackGraph as a response to a world where
"software creation is accelerating dramatically through coding agents, AI-assisted
development, and vibe coding." The estate is changing *faster* than anyone can read.

**There is not a single time-based view anywhere in the UI.** No trend, no delta, no
"since last week", no sparkline. The system is bitemporal underneath and the control
surface is entirely a snapshot.

Add a **drift strip** to the top of Estate: a compact 90-day band with three
sparklines and three deltas.

```
Last 90 days                                        ▁▂▂▃▅▅▆  ↑
New technologies introduced        34   ▁▂▂▃▅▅▆      +12 vs prior 90d
Estate spread (entropy)          0.62   ▂▃▃▄▄▅▅      +0.06
Evidence coverage                  64%  ▅▅▄▄▄▃▃      −4 pts
```

And one sentence under it, generated from the same numbers:

> *"34 technologies entered the estate in the last 90 days. 12 of them are the only
> instance of their kind. Spread is rising and evidence coverage is falling."*

**Why it differentiates.** No code review tool has a point of view on the *rate* of
change of an estate. This is the one screen that is unmistakably 2026 rather than
2016 — and it is the direct visual expression of the thesis the README already
commits to. It also creates the natural hook for the highest-value question in the
product: *"what did the agents add this week, and did it make things worse?"*

**Data already available.** The `technology_introduction` insight report is already
enumerated in `PHASE2_ACTIONS` in `app/ask/page.tsx` ("Which technologies were
introduced into the estate in the last 90 days?" is literally suggestion #12).
Entropy and coverage are in the estate summary and capability footprints. If a
historical series is not yet exposed, ship the strip with **current value + the
report's own delta**, and add sparkline points as snapshots accumulate — the layout
does not change.

**Visual spec.** Sparklines are 64×18px inline SVG polylines, 1.5px stroke,
`currentColor`. No axes, no gridlines, no tooltips — the numeral beside them carries
the value. Deltas use the existing arrow icons from Tabler, with the word ("up",
"down") in the accessible name.

**Effort.** ~1.5 days for the strip; the sparkline primitive (~40 lines) is then
reusable across R7 and every stat tile in the product.

---

### R6 — Drift Ribbon on the Architecture Canvas

**What.** The Architecture Canvas already has the strongest conceptual model in the
product: `actual | target | drift | compare` views crossed with `posture |
conformance | coverage | none` emphasis (`features/architecture/CanvasControls.tsx`).
That is a genuinely sophisticated control surface — and its output is a grid of cells
that all look structurally identical whichever mode you are in.

Add one thing: in **drift** and **compare** views, a **ribbon** above the grid
summarising the whole comparison as a single 100%-width stacked band —
Aligned / Allowed / Discouraged / Prohibited / Required-but-missing / Can't judge —
using the tones already defined in `COMPARISON_TONE`.

**Why it differentiates.** "You are 71% aligned to your own standard, 6% in breach,
and 12% unjudgeable" is a board-level number nobody else can produce, because nobody
else holds a governed target model *and* the observed estate in one object. Today
that number exists implicitly across 40 cells and is never stated.

**Data already available.** `CanvasComparisonCellStatus` per cell, already projected,
already labelled and toned in `packages/canvas-ui/src/vocabulary.ts`.

**Visual spec.** Segments carry their count as a numeral; segments under 4% collapse
into a "+n other" segment that expands on click. `UNEVALUABLE` stays visually
**quiet**, never red — the vocabulary file's comment is explicit that an incomplete
observation must not read as non-conformance, and the ribbon must honour that.

**Effort.** ~1 day.

---

### R7 — Version Spread Comb

**What.** `OccupantChip` already solves the right problem correctly — it groups
`react@18.3.1`, `react@18.2.0`, `react@16.14.0` into one package chip reading
"3 versions", with the file comment explaining exactly why flat listing misleads.
That is excellent reasoning.

Give it a picture: a **comb** — a 40px inline strip of ticks, one per resolved
version, positioned by recency, most-severe policy status carried by the leading
tick. Three ticks bunched right = healthy. Three ticks spread across the strip =
a decade of drift in one package.

**Why it differentiates.** Every SCA tool lists versions. None show *version spread as
a shape*, which is the thing that predicts migration cost.

**Data available.** `group.versions`, `group.members[].policy_status` — already in
the component's props.

**Effort.** ~0.5 day.

---

### R8 — Estate Brief (the boardroom one-pager)

**What.** A single route, `/brief`, that renders one screen-shareable, printable page:
the R4 stratum bar, the R1 heat grid, the R5 drift strip, the top five risks from
`/graph-intelligence/risks`, and the R2 funnel for the highest-priority finding —
with the as-of timestamp and evidence coverage stamped at the foot.

**Why it differentiates.** `docs/strata-design-language.md` names the primary user as
"CTOs skimming for five minutes". Nothing in the product is built for a five-minute
skim: Estate opens onto four count tiles and five collapsible tables. Meanwhile the
artifact that actually travels inside an enterprise — the slide a CTO puts in front of
a board — is produced by hand, outside the tool, every single quarter, by every single
customer. **Owning that artifact is a moat.** No code review tool has ever tried to
own it.

**Visual spec.** Fixed A4/16:9 aspect. `@media print` stylesheet with the light
palette forced and the rail suppressed. No interactivity except drill-through links.
Every number carries its as-of date, because a brief that outlives its data is worse
than no brief.

**Copy.** Every heading is a finding, never a category: *"Payments is implemented five
different ways"*, not *"Capability entropy"*.

**Effort.** ~2 days once R1/R2/R4/R5 exist. Almost entirely composition.

---

### R9 — Evidence Temperature

**What.** `CitationChip` is used well but inconsistently: some numbers link to
evidence, most do not, and there is no way to tell which is which before clicking.
Introduce a **uniform evidence affordance**: any figure derived from evidence carries
a 4px mono superscript degree mark; hovering or focusing it reveals the count and
opens the existing evidence drawer.

**Why it differentiates.** The product's central claim (spec §33) is "no material
conclusion without evidence." Today that claim is enforced in the *backend* and
surfaced *sporadically*. Making it a uniform, sub-visual property of every number —
present everywhere, loud nowhere — turns a policy into a felt experience.

**Visual spec.** Never a colour. Never a badge. A single mono glyph at 0.6em,
`--sg-text-muted`. Absent = the number is a direct count, not an inference; that
absence is itself information and should be stated once in the glossary.

**Effort.** ~1 day (one wrapper component + a sweep of call sites).

---

### R10 — Command surface upgrades

Four small changes to the navigational chrome, none of which remove anything:

**a) Rail counts.** `LeftRail.tsx` renders 11 flat items with no state. Reviews should
carry the queue depth, Scan health should carry a dot when a service is degraded.
`useServiceStatus` already polls every 15s and `useReviewQueue` is already fetched
by the Reviews page; hoisting both into the shell is a query-key reuse, not a new
request path. A reviewer should never have to open Reviews to discover it is empty.

**b) Rail grouping with visible labels.** The rail already groups `PRIMARY /
SECONDARY / ADMIN` with bare `<div className={styles.divider}/>` separators — the
grouping exists structurally but is invisible. Label the groups: **Explore**
(Estate, Business Map, Applications, Technologies, Architecture), **Decide**
(Modernization, Ask, Reviews), **Operate** (Scan health, Admin, About). Three verbs
tell a new user what the product is for before they click anything.

**c) ⌘K should be a command palette, not a redirect.** Today `AppShell.tsx` binds
⌘K to `router.push("/ask?view=ask")` — it navigates away, losing the user's place.
Make it an overlay palette that searches entities *and* offers actions ("Ask…",
"Jump to application…", "Open review queue"), with Ask as the fallthrough when
nothing matches. The `semanticSearch` endpoint already backs the entity half via
`SemanticMatches`.

**d) Saved views.** `useEstateQuery` already serialises the full filter state to the
URL and `LENSES` already defines named presets. Adding "Save this view" is a
`localStorage` write and a rail section. Analysts who live in the tool for hours
(persona #2 in the design language) rebuild the same filter stack every morning.

**Effort.** ~2 days total.

---

## 4. Language pass

The copy is already unusually careful — `presentRecommendationTitle` exists purely to
turn "Review duplicated implementation implementations" into English, and
`CELL_STATE_DESCRIPTION` explains the difference between "none found" and "not
observed" in one sentence each. That instinct is right. It just has not been applied
uniformly, and machine vocabulary still leaks through in a dozen places.

**Rule to adopt: no identifier, version string, or `SCREAMING_SNAKE` enum ever
reaches a user-facing surface.** They belong in `title` attributes, Scan health, and
Admin.

| Where | Today | Proposed |
|---|---|---|
| `StatusStrip` | `contract 1.0.0` | *(remove; move to Scan health)* |
| `CanvasControls` provenance | `model stackgraph-reference-v1@3 · template porter@2 · v1.4.0-method` | "Standard: Reference v3 · Checked 5 Sep, 14:02" — full string on hover |
| `DeterministicInsightsPanel` | `rule_key` shown raw: `dependency.unsupported-runtime` | "Unsupported runtime" — the key moves to the `title` |
| Ask report cards | `WAITING_FOR_DATA` | "Needs more data" |
| Ask report cards | `report.status.replaceAll("_", " ")` → `WAITING FOR DATA` in caps | sentence case, always |
| Graph intelligence | `STRUCTURALLY_CRITICAL` → "Structurally critical" | "Single point of failure" |
| Graph intelligence | "PageRank", "Betweenness" as metric labels | "How central" / "How often on the path between others" — the algorithm name moves to the `<Term>` gloss |
| Estate domain header | "3 of 50 match" beside "50 loaded" | "50 loaded · 3 match your filters" |
| Estate | "Ranked items" | "Everything found" |
| Modernization | "Portfolio value 214" | "Combined value 214 pts" with a `<Term>` on what a point is |
| Modernization | "Effort budget · 21 points" | "How much work you can take on this quarter" |
| Modernization | "Governed scoring active" / "Pilot guidance" | "Ranked using your approved policy" / "Draft ranking — not yet approved" |
| Canvas | "Colour by: Health / Your standard / Gaps / Off" | *already excellent — use this as the model for every other control in the product* |
| Insight stages | "Statically reachable" / "Deploy config" / "Public config" / "Biz critical" | "Reachable in code" / "Deployed" / "Internet-facing" / "Business-critical" |
| Technologies | "Declared" / "Observed" | keep — but add the one-line `<Term>` gloss the canvas states already have |
| Reviews | "Decisions remain optimistic and audited by the originating workflow." | "Your decision applies immediately and is recorded in the audit trail." |
| Blast radius | `a3f8…-91b2 → 7c11…-40de → …` | "payments-sdk → billing-api → Claims Settlement" |
| Ask | "Evaluated 3 minutes ago" | keep — this is right |

**Three headline rewrites:**

- Estate H1: "Software Estate" → **"Your estate"**, subtitle *"Everything StackGraph
  found across your repositories — and what it means."*
- Modernization H1: "Modernization" → **"What to fix first"**.
- Ask H1: "Ask your estate" → keep. It is the best label in the product.

---

## 5. Layout and information architecture

**5.1 Estate does not answer a question above the fold.**
Today: title → view switch → four count tiles (Applications / Repositories / Services
/ Technologies) → filter bar → semantic matches → five collapsible domain tables.
Four counts are inventory, not intelligence. Nobody's first question is "how many
repositories do I have."

Proposed above-the-fold order:
1. **Stratum bar** (R4) — what we know, and where the knowledge thins.
2. **Drift strip** (R5) — what changed, and whether it got worse.
3. **Three findings, not four counts** — the top three from
   `/graph-intelligence/risks`, each one sentence with a drill-through.
4. Then the existing view switch, filter bar and tables, entirely unchanged.

Counts move into the stratum bar's expanded state. Nothing is lost; the fold now
carries meaning instead of arithmetic.

**5.2 The Estate view switch should hold four peers, not two.**
`Ranked list · Architecture canvas` becomes
**`Ranked list · Heat grid · Canvas · Brief`** — four ways to read the same estate,
switched in place. This is the right pattern and it is already built; it just needs
its other two members.

**5.3 Application detail buries the intelligence.**
`app/applications/[id]/page.tsx` puts `GraphIntelligenceSummary` first in the
Overview tab, then five `<dl>` sections of counts. Correct instinct. But the
Recommendations tab — where "what should I do" lives — is fourth of four. Reorder to
**Overview · Findings · Technology · Assessments**, and surface the finding count on
the tab itself.

**5.4 Modernization's budget slider is the best interaction in the product and is
under-sold.** A raw `<input type="range">` labelled "Effort budget" with `21 points`
in an `<output>` drives a live knapsack optimisation against the whole portfolio.
That is a genuinely delightful control. Give it the room it deserves: pin the four
plan stats (`Open opportunities / Recommended now / Effort used / Portfolio value`)
directly beneath the slider so they visibly recount as it moves, and add
**effort-vs-value scatter** beside the ranked list so the reader can see the cheap
high-value cluster the optimiser is picking from.

**5.5 There is no first-run state.** Every page assumes a populated estate.
`EstateView` renders four zero-tiles and five empty tables before the first scan
completes. Add a single onboarding path — Connect a source → first scan running →
first findings — reusing the existing `Placeholder` component. This is the state
every evaluator sees first and the only state nobody has designed.

---

## 6. Iconography and the visual system

Tabler at 1.5px stroke is the right call and `packages/canvas-ui/src/icons.tsx`'s
semantic key registry (reference models ship keys, never component names or colours)
is a genuinely good piece of architecture. Two additions:

**6.1 A signal glyph set — five custom marks, drawn once.** Tabler has no icon for
any of the concepts that make StackGraph distinct. Draw five, in the same 1.5px
stroke, 24px grid, outline-only language:

| Mark | Meaning | Where |
|---|---|---|
| **Attenuation** — a wedge narrowing left to right | The funnel, reachability | Insight cards, Ask reports |
| **Blast** — concentric arcs from a point | Impact radius | Graph intelligence, risk cards |
| **Spread** — scattered ticks on a baseline | Entropy, version drift | Heat grid, occupant chips |
| **Strata** — five stacked bands, one broken | Estate layers, coverage gap | Stratum bar, Scan health |
| **Drift** — two diverging lines | Actual vs target | Canvas drift view, ribbon |

These become the product's visual signature. A customer should recognise a StackGraph
screenshot from across a room by these five marks the way they recognise a Figma file
by its cursor.

**6.2 Use the `display` token.** The design language reserves 32px display type for
"the two numbers meant to be read from across a room" — entropy and viability delta.
It is currently used once, for a repo count on Scan health. Give it to the heat grid's
estate-wide spread figure and to the drift strip's headline delta. A type scale that
never reaches its top step is a scale with a wasted step.

**6.3 Domain colour stays for domains.** Resist every temptation to tint the heat grid
by domain as well as by entropy. One encoding per surface. The existing note in
`vocabulary.ts` — *"there is deliberately no per-domain hue: domains are distinguished
by label, icon, and position, which keeps the colour budget for signal"* — is the best
sentence in the codebase and should be quoted in the design review of every new
surface.

---

## 7. Defects found in the current control surface

Independent of any redesign, these are wrong today:

| # | Issue | Where |
|---|---|---|
| 1 | Raw UUID chains shown as an impact path | `GraphIntelligenceSummary.tsx` — `impact.entity_ids.join(" → ")` |
| 2 | `contract 1.0.0` in the persistent user-facing status strip | `StatusStrip.tsx` |
| 3 | Machine identifiers rendered as labels (`rule_key`, `method_version`, `reference_model_key@version`) | `DeterministicInsightsPanel.tsx`, `CanvasControls.tsx` |
| 4 | `SCREAMING_SNAKE` enums reaching the user in caps | `app/ask/page.tsx` report status |
| 5 | Domain count reads "3 of 50 match" *and* "50 loaded" in the same line — two denominators, one row | `EstateView.tsx` |
| 6 | ⌘K navigates away rather than opening a palette, losing the user's place | `AppShell.tsx` |
| 7 | Rail gives no state: review queue depth and service degradation are invisible until you navigate | `LeftRail.tsx` |
| 8 | Theme control is an icon-only 3-state cycle with no visible current-state text | `TopBar.tsx` |
| 9 | `listCapabilityFootprints` — a shipped, tested read model with zero UI call sites | `client.ts:931` |
| 10 | `getRepositoryCapabilities`, `getCapabilityTaxonomy`, `getPhase3IntelligenceMetrics`, `getBusinessMapRevisions` — also zero call sites | `client.ts` |
| 11 | No first-run / empty-estate path | all list surfaces |
| 12 | ~~Business Map persistence is browser-local~~ — **corrected:** `useBusinessMap.ts` does persist server-side via `listBusinessMaps`/`saveBusinessMap`, with `localStorage` as a cache and offline fallback. The P3 in `design-qa.md` is stale. The real remaining gap is that `getBusinessMapRevisions` is fetched by nothing, so the saved revision history is invisible | `useBusinessMap.ts` |

Items 1–5 and 8 are under a day of work in total and should not wait for anything
else in this document.

---

## 8. Non-negotiables — do not "improve" these away

Any redesign is at risk of flattening the three things that already make this product
distinctive. Explicitly:

1. **Mono = fact, sans = inference.** This must survive every new component. A number
   in the heat grid is a computed inference and takes sans-adjacent treatment; a
   package name in a chip is mono. Do not homogenise.
2. **Colour never carries meaning alone.** Every new tone ships with a label in
   `vocabulary.ts` and a numeral in the cell. The heat grid ships with a "No colour"
   mode from day one.
3. **`EMPTY` is not `DANGER`.** The comment in `vocabulary.ts` — *"An empty optional
   concern is a correct result; severity comes from policy, not from emptiness"* — is
   a product decision, not a styling one. A heat map makes it very easy to accidentally
   paint "we found nothing" bright red. Do not.
4. **`UNEVALUABLE` stays quiet.** An incomplete observation must never read as
   non-conformance. This is the single most likely regression when adding ramps.
5. **Limitations stay beside the number they qualify**, never behind a link. The
   `Limitations` component's placement is deliberate and correct.
6. **Two elevation levels only.** No card-within-card. No third shadow tier.
7. **Motion stays restrained** — 150ms hover, 200ms panel, one 1.8s pulse reserved for
   the selected bridge, all `prefers-reduced-motion`-aware. No ambient animation on any
   new visualisation.

---

## 9. Sequencing

| Phase | Contents | Effort | Outcome |
|---|---|---|---|
| **0 — Repairs** | Defects 1–5, 8 from §7; the §4 language pass | 2 days | Nothing machine-facing reaches a user |
| **1 — The picture** | R2 Attenuation funnel, R1 Heat grid, R4 Stratum bar | 4 days | Three screenshots the competition cannot produce |
| **2 — The shape of change** | R5 Drift timeline, R3 Blast ring, R7 Version comb | 3.5 days | Time and impact become visible |
| **3 — The artifact** | R8 Estate Brief, R6 Drift ribbon | 3 days | StackGraph owns the quarterly board slide |
| **4 — The daily surface** | R9 Evidence temperature, R10 Command upgrades, §5 layout | 4 days | The tool an EA lives in for hours |

**≈16.5 engineering days** to a control surface with no analogue in this market. Phase
1 alone changes the demo.

---

## 10. What not to do

- **Do not add a charting library.** Every visualisation above is under 150 lines of
  inline SVG or CSS. `recharts` or `d3` would import a visual language that fights
  Strata's hairline-and-flat discipline, and the CSP/self-hosting posture in
  `layout.tsx` (no third-party runtime font call, nonce'd scripts) is deliberate.
- **Do not make the node-link graph the home screen.** `docs/stackgraph-ui-spec-v2.md`
  already concluded that scored, ranked tables outperform graph canvases for "what
  should we do", and it is right. The graph is a drill-down, not a dashboard.
- **Do not animate the estate.** No physics, no force-directed drift, no ambient
  pulsing. An instrument panel read under pressure by a CISO cross-checking a
  vulnerability list must be still.
- **Do not add a sixth hue.** One sequential ramp, on two legended surfaces, derived
  from an existing domain ramp. That is the entire budget.
- **Do not hide anything behind a hover.** Everything above is redundantly encoded:
  shape *and* numeral *and* label. Hover adds detail; it never carries meaning.
- **Do not ship a heat map without a legend on screen.** Not in a popover, not in a
  tooltip — inline, permanent, beside the grid.

---
---

# Part II — Impact of the Phase 2 plan

**Assessed against:** *StackGraph Phase 2 Improvements* (Enterprise Change Compiler,
Action Grammar, Mutation IR, impact simulation, change memory, AI dependency graph,
agent control plane).

**Verdict in one line:** Phase 2 does not invalidate Part I — it **raises the stakes
on every recommendation in it and moves one of them to the centre of the product.**

Part I diagnosed a control surface that renders no pictures. Phase 2 introduces
something more consequential: **for the first time, the UI has to stop people.**
Everything in the shipped surface is advisory — tones, labels, limitations placed
beside the number they qualify, an explicit product rule that `EMPTY` is not `DANGER`
and `UNEVALUABLE` stays quiet. That restraint is correct for a system that *describes*
an estate. It is insufficient for a system that **gates changes to one.**

That single shift drives most of what follows.

---

## 11. What Phase 2 changes about the UI plan

### 11.1 The five structural consequences

| # | Phase 2 clause | Consequence for the UI |
|---|---|---|
| 1 | §5 "Do not make an unconstrained chatbot the primary simulator interface. The preferred UX is a contextual command surface." | **R10c stops being a navigation improvement and becomes the product's primary interaction surface.** Promoted to R11 and re-specced. |
| 2 | §5 Resolution states; §10 "Low-confidence matches must never silently enter deterministic simulation"; §18 "No unresolved entity should silently become a Mutation subject" | The design system needs a **blocking state class** it does not have, and a **resolution axis** distinct from confidence. |
| 3 | §12 "Blast radius must not mean generic N-hop graph traversal" — DIRECT / TRANSITIVE / CONTEXT / STOP / INFORMATIONAL | **R3 as drawn in Part I is wrong.** Rings must band by impact classification, not hop distance. |
| 4 | §13 `diff(G, G')` hypothetical estate overlay | Every visualisation in Part I gains a **second, simulated state**. The heat grid becomes before/after. This makes R1 substantially stronger. |
| 5 | §14 "AI must not manufacture the underlying impact graph" | The Strata mono/sans rule stops being a nice epistemic touch and becomes a **safety boundary rendered in type.** |

### 11.2 The design-system gap Phase 2 opens

Today's tonal vocabulary in `packages/canvas-ui/src/vocabulary.ts` has four tones —
`neutral | positive | caution | danger | quiet` — and every one of them is *advisory*.
The file's own comments make the philosophy explicit and correct:

> *"An empty optional concern is a correct result; severity comes from policy, not
> from emptiness."*
> *"`UNEVALUABLE` is quiet, never danger: an incomplete observation must not read as
> non-conformance."*

Phase 2 introduces states that are **not advisory**:

- an **Unresolved** subject that *blocks* compilation;
- a **material ambiguity** that *blocks* simulation;
- a **DENY** or **ESCALATE** verdict from the capability compiler;
- a **contradiction** between two authoritative sources that invalidates a plan.

None of these are "danger tone, more so". A `danger` chip on a table row and a wall
that stops you submitting a change are different classes of object, and conflating
them will either make blocking states too quiet to work or make advisory states too
loud to live with.

**Required addition to the design system: a `gate` class**, distinct from the four
tones, with exactly four members and its own component:

| Gate state | Meaning | Visual treatment |
|---|---|---|
| `BLOCKED` | Cannot proceed. A required input is unresolved or contradicted. | Full-width barrier bar above the action; the action control is `disabled` **and** the reason is stated inline, never only in a tooltip |
| `ESCALATE` | Can proceed only with a named approval. | Barrier bar with the approver role named and the request action inline |
| `CONSTRAIN` | Can proceed, narrower than requested. | Inline notice on the scope control showing what was removed and why |
| `CLEAR` | Nothing is in the way. | No component rendered — absence is the signal |

Rules: a gate always names the *specific* blocking entity or contradiction and links
to its evidence; a gate is never dismissible; a gate never uses the domain ramps.
`BLOCKED` and `ESCALATE` are the **only** places in the product allowed a filled
(rather than hairline) surface — because they are the only places where the reader
must not be able to skim past.

### 11.3 The colour budget is now over-subscribed — resolve it deliberately

Part I asked for one new sequential ramp. Phase 2 arrives with **five new semantic
axes** at once: resolution state (3 values), impact classification (5), gate verdict
(4), contradiction status, and before/after diff polarity. A five-hue budget cannot
absorb that, and trying will destroy the discipline that makes the current UI good.

**Assign each axis a channel, and hold the line:**

| Axis | Channel | Rationale |
|---|---|---|
| Domain (Business/Enterprise/…) | **Hue** — the four existing ramps | Already learned; do not touch |
| Confidence | **Segments** — existing `ConfidenceChip` | Already correct; do not touch |
| Resolution (Resolved/Inferred/Unresolved) | **Typography + glyph** — see R12 | It is an *identity* claim, and Strata already encodes epistemic status in type |
| Impact classification (Direct/Transitive/Context) | **Position** — ring band, see R3′ | Distance from centre already means this; colour would be redundant |
| Gate verdict | **The one filled surface in the system** | Deliberately the loudest thing in the product, used nowhere else |
| Entropy / spread | **The one sequential ramp** from R1 | Legended surfaces only |
| Before/after diff | **Fill pattern** — solid = now, hatched = simulated | Survives greyscale and colour-blindness; carries no new hue |

Net new hues: **zero.** Net new ramps: **one** (unchanged from Part I).

---

## 12. Revisions to existing recommendations

### R1′ — Heat Grid becomes the *simulated* heat grid  *(strengthened)*

Phase 2 §13 gives the heat grid a second state. The flagship screen is no longer
"where the estate is scattered" — it is **"where the estate is scattered, and what
this change would do to it."**

- Add a fourth mode to the existing view switch: **Now · Simulated · Difference.**
- In *Difference*, each capability cell shows only the delta, hatched for simulated
  values, with the numeral signed (`−0.14`, `+0.03`).
- The headline becomes a sentence a board understands:
  *"This change reduces payment-capability spread from 0.71 to 0.44 and touches
  8 capabilities, one of them Tier-0."*
- Cells whose delta cannot be computed render **"Not simulatable"** with the reason —
  never a zero delta. A missing simulation must not read as "no effect".

Still zero backend work for the *Now* state (`/capabilities/footprints` remains
unused). The *Simulated* state consumes `POST /simulations`.

**This is now the strongest single screen in the roadmap** and should stay the
flagship.

### R3′ — Blast Radius Ring: bands by classification, not by hop  *(corrected)*

Phase 2 §12 is explicit: *"Blast radius must not mean generic N-hop graph
traversal."* The ring I specified in Part I bands by `impact.distance`, which is
exactly the generic traversal Phase 2 rejects. **Revised:**

- **Bands are impact classifications**, in this fixed order outward:
  `DIRECT` → `TRANSITIVE` → `CONTEXT`. Hop distance becomes a numeral on each
  plotted entity, not the ring itself.
- **`STOP` boundaries are drawn**, as a hairline arc terminating a branch, labelled
  with why traversal stopped ("Owner — not an impact path"). Showing where the engine
  *deliberately stopped looking* is what separates this from a dependency tree, and
  it is the thing that makes the result auditable.
- **`INFORMATIONAL` sits outside the outermost band**, visually detached, so it can
  never be read as impact.
- The **business capability terminus is the visual destination** — per §22, "a blast
  radius of 73 repositories is much less meaningful than: Payment Authorization, a
  Tier-0 business capability, is affected." Draw the arc that reaches a capability
  solid and terminate it in a labelled node; everything else is subordinate.
- Per-hop `ConfidenceChip` and per-hop evidence chips stay exactly as specified.
- The traversal policy that produced the ring is named beneath it
  (*"Policy: package-upgrade impact, 4 edge types, max depth 6"*), because §12 makes
  the policy the reason the picture is trustworthy.

The UUID defect fix from Part I is unchanged and still ships immediately.

### R4′ — Stratum Bar gains a sixth band and a provenance reading  *(extended)*

Phase 2 §31 adds an AI supply-chain layer (Agent → Harness → Model → Prompt →
Context Source → Tool → Dataset). The `Namespace` union in
`packages/shared/src/contracts/read-models.ts:10` currently has six members —
`BUSINESS | ENTERPRISE | TECHNOLOGY | OSS | DEPLOYMENT | INTELLIGENCE` — where
`INTELLIGENCE` means *StackGraph's own assessments*, not *the customer's AI estate*.
Those are different things and must not share a band.

- The bar becomes **six bands**: Business · Enterprise · Technology · OSS ·
  Deployment · **AI**.
- **Do not give AI a sixth hue.** It renders in the existing intelligence violet at a
  distinct 300-stop with the `strata` glyph, and is separated by label and position —
  exactly the argument `vocabulary.ts` already makes for domains.
- Add a **second reading** to the expanded state, required by §19: not just *how much*
  of each layer is known, but **how well-evidenced it is** — the share of that layer's
  simulation-relevant edges carrying corroborating provenance. A layer that is 90%
  populated and 20% corroborated is the single most dangerous state in a simulation
  product, and today nothing surfaces it.

### R5′ — Drift Timeline absorbs predicted-vs-actual  *(strengthened)*

Phase 2 §30 is the best thing in the plan and it lands directly on R5. Extend the
drift strip with a fourth row, and give it its own surface:

```
Change memory                  142 similar changes on record
                               119 succeeded · 18 needed intervention · 5 rolled back

Strongest failure predictors   Runtime mismatch      7.8×  ████████
                               High schema fan-out   4.1×  ████
                               Tier-0 dependency     3.7×  ████
                               Low test coverage     2.9×  ███
```

And — the honest chart nobody ships — a **calibration plot**: predicted impact on one
axis, observed impact on the other, one dot per executed change, the diagonal drawn.
Dots above the line are under-prediction; dots below are over-prediction. **Publishing
your own miss rate is a trust move no competitor will copy**, and it is the natural
home for the "Learn" stage of the lifecycle.

Place the failure-predictor bars **inside the simulation result**, not only on a
dashboard: a predictor that matches the current change is the most decision-relevant
thing on the screen.

### R7′ — Version Spread Comb is promoted to the target picker  *(promoted)*

Phase 2 §6 specifies contextual target autofill with exactly the data the comb draws:

```
10.x    21 repos      11.x    47 repos
12.x   143 repos      13.x   171 repos
```

The comb is no longer a decoration on `OccupantChip`. It is **the control you choose
a target version with** — click a tooth to set the target, and the estate mass sitting
to the left of your choice is the migration you just proposed, shown as you choose it.
Suggested targets (`Consolidate estate` / `Candidate upgrade` / `Latest — resolved at
execution`) render as labelled markers above the comb.

Promoted from Phase 2 to **Phase 1** of the delivery sequence; it is now on the
critical path for the first vertical slice (`UPGRADE Package`).

### R8′ — the Change Brief joins the Estate Brief  *(split)*

The Estate Brief in Part I is the quarterly board artifact. Phase 2 creates a second,
higher-frequency artifact that matters more operationally: **the plan document that
goes to a change board.** Terraform's `plan` output is the reference, and its power is
that it is *readable by someone who did not write it*.

`/simulations/{id}` renders as a **Change Brief**: the mutation in grammar tokens, the
gate verdict, deterministic findings in mono, AI interpretation in sans and visually
partitioned, the impact ring, the prior-outcomes strip, and the verification plan —
one page, printable, with the as-of stamp and the policy version.

Both briefs share a layout system; build the Change Brief **first**, because it is
used weekly rather than quarterly.

### R9′ — Evidence Temperature becomes corroboration depth  *(escalated)*

Phase 2 §19 makes relationship provenance safety-critical and gives it a shape:

```
PaymentService DEPENDS_ON CustomerService
✓ generated OpenAPI client   ✓ endpoint reference in source
✓ runtime traffic            ✓ architecture documentation
```

Four independent corroborations is a materially different claim from one, and the
Part I proposal (a single degree mark) cannot express it. **Revised:** the mark
becomes **1–4 stacked hairlines** — corroboration depth, not mere presence. On any
edge that participates in a simulation, the mark is **mandatory, not decorative**, and
a single-source edge in a `DIRECT` impact band must be visibly weaker than a
four-source one.

Escalated from "consistency polish" to **Phase 1, blocking** — §19's own framing is
"prefer fewer trustworthy edges over a huge noisy graph", and the UI is where that
preference either becomes visible or is lost.

### R10′ — command-surface items re-scoped

- **(a) Rail counts** — unchanged, still worth doing.
- **(b) Rail grouping** — **revised.** The three verbs in Part I (Explore / Decide /
  Operate) predate the Phase 2 lifecycle. Use the lifecycle's own spine instead:
  **Understand** (Estate, Business Map, Applications, Technologies, Architecture) ·
  **Change** (Simulate, Recommendations, Reviews, Change memory) · **Operate**
  (Scan health, Admin, About). "Change" is a new rail group and the product's centre
  of gravity.
- **(c) ⌘K palette** — **superseded by R11.** Do not build the Part I version; it
  would have to be rebuilt six months later.
- **(d) Saved views** — unchanged, and now extends naturally to saved ChangeSets.

---

## 13. New recommendations required by Phase 2

### R11 — The Command Bar *(new flagship — supersedes R10c)*

**What.** A grammar-constrained command surface, opened with ⌘K from anywhere, that
compiles keystrokes into a Mutation. It is the primary interface of Phase 2 and the
plan is explicit (§5) that it must **not** be a chat box.

Four states, each with a distinct visual register:

```
1  EMPTY        upgrade|
                ── estate-backed candidates, counted, never generated ──
                Library    2,847      Runtime   17
                Framework      8      Database   6      Platform  9

2  RESOLVING    upgrade newt|
                Newtonsoft.Json          pkg:nuget/Newtonsoft.Json   171 repos  ✓ Resolved
                Newtonsoft.Json.Schema   pkg:nuget/…Schema            14 repos  ✓ Resolved
                Newtonsoft.Json.Bson     pkg:nuget/…Bson               3 repos  ✓ Resolved

3  TOKENISED    [ Upgrade ] [ Newtonsoft.Json ] [ → 14.x ] [ estate ]
                ── the comb (R7′) sits directly beneath, targets marked ──

4  COMPILED     Mutation ready · 382 repos in scope · 3 unresolved   [ Simulate ]
                                                       ↑ blocks
```

**Design requirements that are not negotiable:**
- **Every candidate comes from the estate.** `GET /action-types`,
  `/action-types/{predicate}/subjects`, `/entities/{id}/valid-targets`,
  `/entities/{id}/scopes`. Nothing in the dropdown is LLM-generated, and the surface
  should say so once, quietly, at the foot: *"Suggestions come from your estate."*
- **Tokens, not text.** Once resolved, the input is chips carrying canonical IDs. The
  displayed label is for humans; the token holds `pkg:nuget/Newtonsoft.Json`. Show the
  canonical ID in mono on hover — it is a scanned fact and belongs in mono under the
  Strata rule.
- **Free text is a compiler, not the interface.** Natural language is one of the seven
  entry points in §7, and it must visibly *produce tokens* rather than bypass them.
  When NL is used, animate the compilation: the sentence resolves into chips, so the
  user learns the grammar by watching it happen. This is the single best onboarding
  mechanism available and costs one transition.
- **Ungrounded input fails visibly and specifically.** "Plant a tree in my garden"
  must return *"No estate entity matches 'tree'. StackGraph can only change things it
  has found in your repositories."* — not an empty dropdown, and not an LLM apology.
- **The three resolution states are always visible** (R12), and material unresolved
  components render the `BLOCKED` gate on the Simulate control with the count and the
  list.

**Why it differentiates.** Every AI tool in this market is converging on a chat box.
Shipping a *constrained, estate-backed, tokenising* command surface is a visible bet
in the opposite direction, and it is legible in a five-second demo: type a sentence,
watch it become a plan, watch an invalid one get refused. **No competitor can offer
the refusal**, because refusing requires knowing what actually exists.

**Effort.** ~5 days for states 1–3 against the Context API; ~2 more for NL
compilation and the token animation. This is the largest single UI investment in
Phase 2 and it is correctly placed.

### R12 — Resolution State as a first-class visual  *(new, blocking)*

Phase 2 §5 and §10 define three states that carry safety weight and have no
representation in the current design system. They are **not** confidence — an entity
can be resolved with certainty and still be a low-confidence fact, or ambiguous
between two entities each of which is well-evidenced. Two axes, two components.

| State | Treatment | Behaviour |
|---|---|---|
| **Resolved** | Mono label, canonical ID on hover, no adornment | Proceeds silently |
| **Inferred** | Sans label + `n candidates` counter, always expandable inline | Renders a chooser; cannot be dismissed by ignoring it |
| **Unresolved** | Struck label + reason | Raises the `BLOCKED` gate on any control that would consume it |

Add `RESOLUTION_LABEL`, `RESOLUTION_TONE` and `RESOLUTION_DESCRIPTION` maps to the
vocabulary module alongside the existing `POLICY_*`, `POSTURE_*` and `COMPARISON_*`
maps, so the new axis inherits the "every visual signal has a text equivalent"
guarantee for free. Add all three to the glossary in
`packages/design-system/src/glossary/terms.ts`.

**The 100% ambiguity-surfacing goal in §10 is a UI commitment, not a backend one.**
The backend can detect ambiguity perfectly and still fail the goal if the UI renders
an inferred match as though it were resolved. Treat that as a test.

### R13 — The Contradiction Ledger *(new — most under-rated idea in the plan)*

Phase 2 §33 describes the Contradiction Engine and gives it a natural picture:

```
Node runtime — 4 sources disagree
  Source code       Node 18   ●───────────── 47 repos    observed 2d ago
  Dockerfiles       Node 20   ────●───────── 41 repos    observed 2d ago
  Documentation     Node 16   ●───────────── —           updated 14mo ago
  Policy            Node 22   ──────────●───  standard    set 3mo ago

  Nobody is on the standard. Docs are 14 months stale.
  8 applications · 2 business capabilities affected
```

A **disagreement comb**: one row per source, positioned on a shared axis, with
observation recency and scale on each row. The engine "does not need to immediately
determine truth" (§33) — which is precisely why this must be a *picture of a
disagreement* rather than a finding with a severity. A severity implies a verdict.

**Why it differentiates.** Every enterprise has this problem and no tool has a screen
for it. It is also the most immediately *recognisable* screen in the entire roadmap —
every architect who sees it will recognise their own estate in it within five seconds.
Extends directly to §32's assumption drift ("AI context says OrdersDB is
authoritative; the estate migrated to LedgerDB") which is the same comb with a
different axis.

**Where it lives.** A new surface under the **Change** rail group, plus an inline
contradiction badge anywhere a contradicted entity appears in a mutation — a change
built on a contradicted assumption is the failure mode §32 exists to prevent, and the
warning has to reach the person compiling the change, not just a dashboard.

**Effort.** ~2 days. Highest recognition-per-day ratio in Part II.

### R14 — The Simulation Result: a hard visual partition *(new, architectural)*

Phase 2 §14 requires deterministic findings and AI interpretation to be separable.
The Strata typographic rule already encodes exactly this distinction — **mono = a
scanner read it, sans = StackGraph reasoned it** — which means StackGraph already owns
the right primitive and simply has to make it structural rather than incidental.

**Requirement: findings and interpretation never interleave.** Not alternating cards,
not a summary paragraph above a table with prose in the cells. A ruled partition, in
this order:

```
┌ FOUND ─────────────────────────────── deterministic, evidence-backed ┐
│  382  direct repositories          ▏▏▏▎ 4 sources                    │
│   71  applications                 ▏▏   2 sources                    │
│    8  business capabilities        ▏▏▏  3 sources    ← 1 is Tier-0   │
│   23  dependency constraint conflicts                                │
│   17  call sites with no linked test                                 │
└──────────────────────────────────────────────────────────────────────┘
┌ INTERPRETED ──────────────────────── AI reading of the findings above ┐
│  Risk · Rollout · Verification, in sans, each citing the rows above   │
└───────────────────────────────────────────────────────────────────────┘
```

- The interpretation panel is **collapsible; the findings panel is not.** Whether the
  AI commentary is present must never change what the deterministic result says.
- Every interpretation claim **cites a finding row by name**. An interpretation that
  cannot cite one is a hallucination and should render as *"Not derived from the
  findings above"* rather than being suppressed — surfacing the ungrounded claim is
  more useful than hiding it.
- Corroboration depth (R9′) renders on every finding row.

This is one component, but it is the component that makes the "AI must not manufacture
the impact graph" guarantee *visible*, which is the whole positioning claim in §2.

### R15 — Suggested Changes replace the estate fold *(new — revises §5.1)*

Phase 2 §8 ("avoid the blank-page problem") supersedes the third element of the
above-the-fold proposal in Part I. "Three findings" becomes **three simulatable
changes**, each carrying its own Simulate action:

```
HIGH   Internal API /customer/v1 is scheduled for retirement       [ Simulate ]
       31 known consumers · 4 business capabilities

MED    143 repositories are on React 18; React 19 is available     [ Simulate ]
       Estimated spread reduction 0.31 → 0.12

MED    PostgreSQL is fragmented across four major versions         [ Simulate ]
       37 databases · 2 unsupported
```

Every one of these is already producible from shipped read models (deterministic
insights, modernization opportunities, capability footprints) — the only new thing is
that the row **carries a proposed ChangeSet** (§16) instead of ending in a link to a
repository. The revised fold is therefore: **stratum bar (R4′) → drift + change
memory (R5′) → three simulatable changes (R15)** — know / trend / act, in that order.

Per §16, `Simulate recommendation` becomes a **standard row action everywhere a
recommendation appears** — Modernization, insight cards, application Findings tab,
review queue. One component, six call sites.

### R16 — Agent Control Plane surfaces *(new, later phase — 2F)*

For §34–35, two surfaces, both of which should be designed now and built last so the
vocabulary is consistent from the start:

- **Capability envelope card.** `READ / EXECUTE / CONDITIONAL / PROHIBITED / ESCALATE`
  rendered as five fixed bands, always all five shown even when empty — an empty
  `PROHIBITED` band is a statement, and the same logic that made `PostureMeter` render
  "Not scored" rather than a blank applies here.
- **Flight recorder.** A single horizontal trace: objective → context retrieved →
  tools available → calls → actions → assets affected → verification → outcome. The
  differentiator in §35 is *cross-system reconstruction*, so the trace must visibly
  span systems — the lane changes where the action crosses from StackGraph to GitHub
  to the deployment platform, and the seams are the point.

Both consume the gate vocabulary from §11.2, which is why that must be defined in
Phase 1 rather than invented here.

---

## 14. Additional non-negotiables introduced by Phase 2

Add these to the seven in §8, and treat them as review gates on every new surface:

8. **Deterministic findings and AI interpretation never interleave.** A ruled
   partition, findings first, interpretation collapsible. If a reader cannot tell in
   under a second which half they are reading, the component has failed.
9. **No inferred or unresolved entity enters a simulation silently.** 100% ambiguity
   surfacing (§10) is a UI commitment. A resolved-looking chip over an ambiguous match
   is the most dangerous single bug this product can ship.
10. **A gate is never a tone.** Blocking states get the one filled surface in the
    system; advisory states keep hairlines. Never promote a `caution` tone to do a
    gate's job, and never demote a gate to a chip to keep a screen calm.
11. **Every simulation-relevant edge shows its corroboration depth.** §19's
    "prefer fewer trustworthy edges" is only real if the UI makes a one-source edge
    look weaker than a four-source one.
12. **The command surface never invents a candidate.** If it is in the dropdown, it is
    in the estate. This is the product's core claim rendered as an interaction, and
    one convenience-driven exception destroys it.
13. **A missing simulation is never a zero.** "Not simulatable" with a reason, always
    — the same discipline `CELL_STATE_LABEL` already applies to "None found" versus
    "Not observed", which is the best distinction in the existing product.

---

## 15. Revised sequencing

**This replaces the table in §9.** Aligned to the Phase 2A–2F delivery sequence, so
UI and backend land together rather than the UI arriving after the API it needs.

| Backend phase | UI work | Effort | Success criterion |
|---|---|---|---|
| **Pre-2A — repairs** | §7 defects 1–5, 8; the §4 language pass; **the gate + resolution vocabulary defined in the design system** | 3 d | No machine-facing text reaches a user; the blocking vocabulary exists before anything needs it |
| **2A — deterministic foundation** | **R11** command bar states 1–3 · **R12** resolution states · **R9′** corroboration depth · **R7′** comb as target picker | 8 d | A user can compile `UPGRADE Package` into a validated Mutation, or watch it be refused, without seeing a UUID or an enum |
| **2B — change simulator** | **R14** findings/interpretation partition · **R3′** classification ring · **R1′** simulated heat grid · **R2** attenuation funnel | 7 d | One vertical slice — package upgrade — is compiled, simulated and read end-to-end with every impact traceable to evidence |
| **2C — recommendation→action** | **R15** suggested changes fold · Simulate-recommendation row action · **R8′** Change Brief | 5 d | A user goes from an estate finding to an evidence-backed simulation without retyping anything |
| **2D — change memory** | **R5′** drift + prior outcomes + calibration plot · failure predictors inside the simulation result | 4 d | A simulation cites the organisation's own history, and the product publishes its own miss rate |
| **2E — estate fidelity** | **R4′** six-band stratum bar · **R13** contradiction ledger · Business Map revision history · **R8** Estate Brief | 6 d | Coverage *and* corroboration are legible per layer; source disagreement has a screen |
| **2F — AI control plane** | **R16** capability envelope · flight recorder | 5 d | An agent's permitted envelope and its actual execution history are both readable by a human |
| **Continuous** | **R10′** rail counts, lifecycle grouping, saved views · **R6** drift ribbon | 3 d | — |

**≈41 engineering days**, up from ≈16.5, and now spread across the backend's own
sequence rather than front-loaded. Two things are worth noting about the shape:

- **Pre-2A grew and must not be skipped.** Defining the gate and resolution
  vocabularies *before* 2A is three days that prevents every subsequent surface from
  inventing its own blocking treatment. This is the highest-leverage item in the table.
- **R2 (attenuation funnel) survives untouched from Part I** and is still the cheapest
  differentiation in either half of this document. It fits naturally in 2B because a
  simulation finding attenuates exactly the way an insight does.

---

## 16. What Part I got wrong, and one thing worth re-checking

**Corrected in this revision:**

- **R3's rings were the wrong axis.** Banding by hop distance is the generic traversal
  Phase 2 §12 explicitly rejects. Corrected to classification bands with drawn `STOP`
  boundaries.
- **R10c would have been built twice.** The Part I palette (entity search with Ask as
  fallthrough) inverts Phase 2's priority, which puts grammar first and NL last.
  Superseded rather than extended.
- **Defect 12 was wrong.** `useBusinessMap.ts` does persist server-side via
  `listBusinessMaps`/`saveBusinessMap`; `localStorage` is a cache and offline
  fallback. The P3 in `design-qa.md` is stale. The real gap is that
  `getBusinessMapRevisions` is fetched by nothing, so saved history is invisible —
  which matters more now that §22 raises capability mapping to Very High Priority and
  a business map becomes an input to governance decisions.

**Worth re-checking as Phase 2 lands:** Part I recommended the `display` type token
(32px) go to the heat grid's estate-wide spread figure. Under Phase 2 there is a
better claimant — **the simulated delta**. The design language reserves that size for
"the two numbers meant to be read from across a room", and "spread 0.71 → 0.44"
is now the number a room is actually looking at.
