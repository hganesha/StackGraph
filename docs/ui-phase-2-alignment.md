# UI Phase 2 Alignment

**Status:** review document. No implementation proposed here has started.
**Baseline:** `origin/main` at `f5eed18`, which is `7a595f5` (the three Phase 2 plans)
plus `6e2ba98` (the merged Pre-2A UI work, PR #86).
**Assessed against:** [`phase-2-integrated-implementation-plan.md`](phase-2-integrated-implementation-plan.md),
[`phase-2-plan.md`](phase-2-plan.md), and [`scanner-improvements.md`](scanner-improvements.md).
**Supersedes nothing.** [`ui-recommendations.md`](../ui-recommendations.md) Part II stays
normative for R1–R16. This document records what Part II got wrong, what it never saw,
and what the integrated plan requires of the UI that neither document states.

---

## 0. Contract status, stated plainly

The Phase 2 endpoints are **not in the repository yet**. Verified against
`stackgraph-foundation/contracts/v1/openapi.json` at this baseline: 89 paths, none of
which are `/action-types`, `/mutations/*`, or `/simulations`. A repository-wide code
search for `/simulations` under the contracts directory returns nothing, and nothing
under `stackgraph-foundation/contracts/` or `packages/shared/src/contracts/` has changed
since `5a04057`.

So every field name in this document that belongs to a Phase 2 endpoint is taken from
the plan's own specification — §15 of `phase-2-plan.md` and work package C2 of the
integrated plan — and is a **statement of what the UI needs**, not a reading of a
shipped schema. When the real OpenAPI lands, §9 below is the list to re-check first.

What *is* verifiable today is more useful than it sounds, and §1 is entirely built from
it.

---

## 1. Where the UI actually stands

Four findings, each checked against the tree at this baseline rather than inferred.

### 1.1 U0 is defined but unproven — four primitives have zero call sites

PR #86 delivered the U0 vocabulary: `GateVerdict`, `GateNotice`, `ResolutionState`,
`ResolutionLabel`, `CorroborationMark`, `Sparkline`, and five signal glyphs. That was
the right order of work — the integrated plan makes U0 block C2 precisely so the
blocking vocabulary exists before anything needs it.

But a count of call sites outside `packages/design-system/src` gives:

| Primitive | Call sites |
|---|---|
| `GateNotice` | 0 |
| `ResolutionLabel` | 0 |
| `CorroborationMark` | 0 |
| `Sparkline` | 0 |
| `GATE_LABEL` / `RESOLUTION_LABEL` | 0 |
| `IconStrata`, `IconBlast` | 0 |
| `IconAttenuation`, `IconSpread`, `IconDrift` | 2 each |

U0's exit gate reads: *"no component can make inferred identity appear resolved, no
blocking reason exists only in a tooltip/color, and automated axe plus keyboard
journeys pass."* The third clause passes. **The first two cannot be tested at all**,
because nothing renders a resolution state or a gate. A primitive with no call site is
a design intention, not a guarantee.

This is not an argument for building C2 surfaces early to exercise them. It is an
argument that U0 is not finished, and §8 names three places in the shipped product
where a gate and a resolution state genuinely belong today.

### 1.2 Four shipped endpoints the UI cannot reach at all

Not "unused" in the §7-defect-10 sense — these have **no client method and no contract
type**, so no UI code could consume them without contract work first:

| Endpoint | Returns | Why it matters to Phase 2 |
|---|---|---|
| `GET /entities/{id}/critical-edges` | `CriticalGraphEdge[]` with `metric_key`, `score`, `source`, `target`, `supporting_fact_ids`, `components` | The per-edge scoring that R9′ corroboration depth needs somewhere to live, and the closest existing thing to M1's classified paths |
| `GET /graph-intelligence/anomalies` | `GraphAnomaly[]` with `cohort_key`, `cohort_size`, `percentile`, `reasons`, `observed_components` | **Architecture archetypes, already shipping.** See §3.6 |
| `GET /graph-intelligence/motifs` | `GraphMotif[]` with `motif_key`, `members`, `minimum_confidence`, `components` | Recurring structural patterns; the second half of the archetype picture |
| `POST /graph-intelligence/analysis-requests` | `{ id, status, policy_key, requested_change_watermark, created_at }` | **A shipped async-run contract with a watermark.** See §4.1 |

Adding four client methods and four types is contract-adjacent frontend work that
unblocks two of the most differentiating surfaces in this document.

### 1.3 Run provenance is already flowing to the UI, and is almost entirely unrendered

`GraphAnalysisSnapshot` ships on blast radius, risks, communities, and entity metrics.
It carries:

```
analysis_run_id   policy_key         policy_version      policy_hash
as_of             status             coverage            limitations
node_count        edge_count
neo4j_projection_watermark            requested_change_watermark
```

That is, field for field, the provenance stamp M1 and M2 require of a `SimulationRun`:
pinned watermark, policy version, run status, coverage limitation. The UI renders
`as_of` as a relative time, renders `limitations` (correctly, and beside the numbers
they qualify), and renders **nothing else**. `policy_version` and `policy_hash` appear
on no surface. Both watermarks appear once, on Scan health, as an operator line.

M1's exit gate is that *"repeated traversal over the same snapshot/policy is
byte-for-byte deterministic … and evidence-reconstructable."* A reader cannot check
reconstructability against a screen that does not say which policy version produced it.

### 1.4 The unconsumed read-model list, updated

Defect §7.10 named four. After PR #86, `listCapabilityFootprints` has a call site and
the rest do not:

| Client method | Web call sites |
|---|---|
| `listCapabilityFootprints` | 1 (heat grid, stratum bar) |
| `getRepositoryCapabilities` | 0 |
| `getCapabilityTaxonomy` | 0 |
| `getPhase3IntelligenceMetrics` | 0 |
| `getBusinessMapRevisions` | 0 |

`getBusinessMapRevisions` is scheduled into 2E by the integrated plan, which is the
right place. The other three are the joins E1 hardens; surfacing them early is how the
capability layer stops being the thinnest band on the stratum bar.

---

## 2. The finding that matters most

`scanner-improvements.md` has **no UI assessment anywhere**. Part II assessed
`phase-2-plan.md` and nothing else. The integrated plan's traceability table (§14) maps
every scanner topic to a backend work package — S1, S2, S3, S4, T1 — and maps not one
of them to a UI surface, because no UI document has ever read that plan.

This is a larger gap than anything in Part II, for a structural reason:

> The scanner plan changes **what an entity is**. Part II changed what the UI *draws*.

Six new first-class concepts arrive — Component, multi-label repository classification,
ContainerImage, DeploymentProfile, RepositoryActivityProfile with ChangeActor, and
RepositoryFingerprint — plus one derived one, architecture archetypes. Every one of them
lands in a UI that currently has no route, no card, no vocabulary, and in one case no
level of abstraction to put them at.

§3 works through them in the scanner plan's own priority order.

---

## 3. New UI surfaces required by the scanner plan

### U1 — Component becomes the unit of impact *(the information-architecture consequence)*

**What the plan says.** `scanner-improvements.md` §2: insert `Component` between
repository and application/service, because "a monorepo may contain 30 independently
deployable components", and so that blast radius can say *"`apps/payment-api` is
affected; `apps/customer-ui` in the same monorepo is not."*

**What that does to this UI.** The rail's Understand group is Estate, Business Map,
Applications, Technologies, Architecture. Repositories are not in it — there is no
`/repositories` index route at all, only `/repositories/[id]`, reachable by drilling
from somewhere else. A component has no route, no list, no detail, and no place in the
domain model the estate is grouped by.

Three consequences, in descending order of how hard they are to reverse later:

1. **The estate's five domain bands are an entity-kind taxonomy, and Component does not
   fit any of them.** `Namespace` is `BUSINESS | ENTERPRISE | TECHNOLOGY | OSS |
   DEPLOYMENT | INTELLIGENCE`. A component is an Enterprise-domain entity sitting
   between Repository and Application, so the ranked list will silently start mixing
   two levels of abstraction inside one band unless the row states which it is. The
   `RankedItem.kind` field already carries the entity type, and `RankedTable` already
   has the mechanism: `showDependencyTier` adds a column only when the items carry that
   field. Entity level follows the same pattern. The fix is to make level explicit in the
   row, not to add a band.
2. **Every count that says "repositories" becomes ambiguous.** `affected_repository_count`
   on a deterministic insight, `382 direct repositories` in the §44 demo output, the
   stratum bar's Enterprise band, Scan health's coverage — all of them mean "repository"
   today and will mean "repository, of which some components are affected and some are
   not" after S1. A repository count that hides an unaffected component overstates
   impact, which is the specific failure the plan's blast-radius precision argument
   exists to fix.
3. **Drill-through has one more hop.** Estate → Application → Repository becomes Estate
   → Application → Component → Repository, and the canvas's occupant chips are placed by
   component rather than by repository.

**Recommendation.** Treat this as a Phase 2A UI work item landing with S1, not as a
consequence to absorb later. Specifically:

- add a `/components` route and a component detail surface, peers of Applications;
- render level on every row where two levels can appear together — the existing
  `DomainBadge` pattern extends to it, and the same argument `vocabulary.ts` makes for
  domains applies: distinguish by label and position, never by a new hue;
- change impact counts to the pair `n components in m repositories` wherever the scope
  is component-derived, and keep the bare repository count only where the fact genuinely
  is repository-level;
- state the monorepo case explicitly in the copy, because it is the case that makes the
  distinction worth the extra hop.

**Effort.** ~4 days, and cheaper now than after six surfaces have hard-coded the
repository as the unit.

### U2 — Repository classification is multi-label

**What the plan says.** §1: a repository has `architecture` (one of MONOREPO,
DATA_PLATFORM_REPO, …), `contains` (several of FRONTEND_APP, API_SERVICE,
SHARED_LIBRARY, DATABRICKS_JOBS, …), `frameworks`, `data_workloads`,
`deployment_profiles`, and a confidence. Not one `repo_type`.

**What the UI does today.** The repository page renders a single `kind`. The technology
hierarchy renders `node.technology.kind` as a chip. Neither has a shape for "this is one
architecture and four contained kinds, at 0.98 confidence".

**Recommendation.** A classification block, not a chip row: architecture as the
headline, contained kinds as a labelled set, and the confidence on the existing
`ConfidenceChip` rather than as a fifth number. The one thing to get right is that an
empty `contains` is "nothing classified here yet" and not "this repository contains
nothing" — the `CELL_STATE_LABEL` distinction between "None found" and "Not observed",
applied to a new object.

**Effort.** ~1 day.

### U3 — The repository fingerprint page

**What the plan says.** §"I'd introduce a `RepositoryFingerprint`" gives a full worked
example — identity, structure, components, language shares, frameworks, data,
containers, deployment profiles, architecture, activity, change actors, lifecycle,
confidence — and then says, in the document's own words: *"And every line should link
back to evidence. That's an extremely compelling 'repo page' too."*

That is a UI deliverable stated as an aside in a backend document, and it is the single
highest-density screen in either plan. It is also the natural home for U2, U4, U5, U7
and U8 at once.

**Recommendation.** Build `/repositories/[id]` into the fingerprint, and give
`/repositories` the index route it never had. Every line carries a `CitationChip`; the
whole page carries one as-of stamp and one confidence. Language shares are the one place
a stacked proportion bar earns its place, and it needs no new hue — the same
solid/hatched pattern the channel budget already allocates covers observed versus
inferred shares.

This is the Estate Brief's sibling: the Estate Brief is the quarterly board artifact,
the fingerprint is what an architect opens when someone says "tell me about this repo".

**Effort.** ~3 days, once U2/U4/U5/U7 exist as blocks to compose.

### U4 — Container composition, and the digest/tag resolution insight

**What the plan says.** §3: containers become real entities with digest, registry,
architecture, OS, base layers, packages, runtimes, ports, entrypoint, user; the chain
`Service → DEPLOYED_AS → ContainerImage → BASED_ON → BaseImage → CONTAINS → OSPackage`
answers "which production workloads contain Log4j even though the application manifests
don't declare it?". And: **"image digest should be the canonical identity wherever
possible. Tags such as `latest` aren't identities."**

**The non-obvious part.** That last sentence is not a container fact. It is a *resolution
state*, and the vocabulary for it shipped in PR #86:

| Container reference | Resolution state | UI behaviour |
|---|---|---|
| pinned digest | `RESOLVED` | mono, canonical id on hover, proceeds silently |
| tag resolving to several observed digests | `INFERRED` | sans, `n candidates`, inline chooser |
| `latest`, unresolved at scan time | `UNRESOLVED` | struck, reason, raises `BLOCKED` on anything that would simulate against it |

The integrated plan's risk table already says *"Digest is canonical; tags are temporal
observations with explicit unresolved state"*, and §8 clause 4 requires that
*"'latest' is resolved to an immutable value before simulation/execution"*. So the first
real call site for `ResolutionLabel` and `GateNotice` is a container tag, and it exists
in the scanner lane rather than the command lane. That is worth knowing, because it
means U0 can be proven during S3 rather than waiting for C2.

**Recommendation.** A composition surface for the image chain — base image, OS packages,
runtimes — with the digest in mono as the identity and the tag beside it as an
observation. The "affected even though the manifest doesn't declare it" case is the one
to write the copy around, since it is the claim no manifest scanner can make.

**Effort.** ~2.5 days.

### U5 — Deployment profile

**What the plan says.** §4: model detected deployment *capabilities* — provider,
workload, resources, evidence, confidence — not `hosted_on`. An application may have
several: `DEPLOYS_TO → Vercel`, `USES → Supabase`, `STORES_DATA_IN → Azure`,
`RUNS_JOBS_ON → Databricks`.

**Recommendation.** The relationship verb is the information, so the profile renders as
verb-plus-target rows rather than a provider chip row: "Deploys to Vercel · Runs jobs on
Databricks" says something "Vercel, Databricks" does not. Provider gets no hue —
providers are a large open set and would blow the colour budget on day one; label and
icon carry them. `canvas-ui`'s `icons.tsx` is the precedent worth copying rather than
extending — it maps semantic keys to glyphs and reports unknown keys instead of silently
degrading, which is the behaviour a provider registry needs on the day a provider the UI
has never seen arrives from a scan.

**Effort.** ~1.5 days.

### U6 — Architecture archetypes *(and this one has a data source today)*

**What the plan says.** §5: once deployment profiles exist, the estate exposes
archetypes, and the plan gives the shape as a distribution:

```
Serverless SaaS stack       84 apps
Azure enterprise stack     312 apps
Databricks data stack       67 repos
Legacy Java middleware     119 apps
Bespoke / anomalous         28 apps
```

with the recommendation that follows from it: *"These 14 applications appear
functionally identical to your standard Vercel/Supabase architecture but use a bespoke
deployment pattern."*

**Why this is available before S2 lands.** `GET /graph-intelligence/anomalies` already
returns `cohort_key`, `cohort_size`, `percentile` and `reasons` per entity, and
`GET /graph-intelligence/motifs` already returns recurring structural patterns with
members and a minimum confidence. A cohort with a size *is* an archetype distribution,
and an entity scoring high against its own cohort *is* "bespoke / anomalous". The
deployment-profile version of this will be better, but the picture does not have to wait
for it — it has to wait for a client method and a type (§1.2).

**Recommendation.** An archetype surface built on cohorts now, re-pointed at deployment
profiles when S2 lands. The distribution reads as a ranked list rather than a chart —
five bars with counts is a list wearing a costume — and the differentiating row is the
last one. "Bespoke / anomalous, 28 apps" is the row a reader clicks, so it is the row
that gets the drill-through and the `reasons` array rendered in full.

The one trap: an anomalous cohort member must not render as a fault. It is an
observation that something differs from its peers, which is the same class of statement
as `UNEVALUABLE`, and it takes the quiet treatment for the same reason.

**Effort.** ~2 days on cohorts, plus ~0.5 to re-point later.

### U7 — Activity and velocity, which is where R5's missing data arrives

**What the plan says.** The temporal section specifies `RepositoryActivityProfile`: age,
commits/PRs/contributors over 90 days, change velocity, deployment frequency, dependency
change rate, major refactors, ownership concentration, hotspots, stability. And the
argument for it: two services with identical dependency graphs, one with 47 changes a
week and 14 maintainers, one untouched for 18 months with a single maintainer, *"should
not get the same risk score."*

**Why this closes a gap Part I left open.** R5 (drift timeline) was specified with a
caveat: *"If a historical series is not yet exposed, ship the strip with current value +
the report's own delta, and add sparkline points as snapshots accumulate."* That caveat
is why `Sparkline` shipped in PR #86 with zero call sites. T1 is the series. The
component is already built and the layout was designed not to change when the points
arrive.

**Recommendation.** Land the drift strip against T1 rather than shipping the degraded
version first. Add hotspots and ownership concentration as their own reading, because
they answer a different question from velocity — velocity says how fast, concentration
says how many people would have to be found before it could change safely, and that is
the number that makes an upgrade recommendation land or not.

**Effort.** ~2 days, most of it already paid for.

### U8 — Change actors: the founding premise, finally measurable

**What the plan says.** The `ChangeActor` taxonomy — HUMAN, BOT, DEPENDENCY_BOT,
CI_AUTOMATION, AI_AGENT, AI_ASSISTED_HUMAN, UNKNOWN — correlated with outcome, so the
estate can answer *"do AI-authored changes behave differently?"* with rollback rates and
review times per actor class.

`README.md` opens by framing StackGraph as a response to software creation accelerating
through coding agents. Part I noted the product had no time-based view at all. This is
the data that makes the founding claim checkable rather than asserted, and no competitor
holds it.

**Two constraints the UI must carry, and they are not decoration.**

First, the plan is emphatic about evidence class: `AI_ASSISTED` from Copilot metadata at
HIGH confidence is a different claim from `POSSIBLY_AI_ASSISTED` from commit style at LOW
confidence, and *"code-style detection by itself should never be considered
authoritative."* The Strata typographic rule already encodes exactly this: an
authoritative actor signal is a scanned fact and renders mono; an inferred one is
StackGraph's reading and renders sans. This is the same mechanism as U4's digest/tag
split, and it should not be re-invented per surface.

Second, the integrated plan's risk table names the failure mode directly: *"Actor data
becomes employee surveillance — purpose limitation, aggregation, retention, RBAC, audit,
no individual scoring by default."* That is a UI requirement, not only a backend policy.
Concretely: **the actor surface shows classes, never individuals**, aggregates below a
documented minimum cohort size are suppressed rather than shown with wide error bars,
and there is no per-contributor view, no leaderboard, and no per-person drill-through.
`ownership_concentration` from U7 is a repository property and stays one; it must never
resolve to a named person in the UI.

**Recommendation.** An actor-mix reading on the drift strip — share by class over 90
days — and an outcome comparison (rollback rate, review time) with sample size printed
beside every rate. Rates without their denominator are the specific way this surface
would mislead, and H1's own gate requires publishing sample size, confidence, and
coverage limitations.

**Effort.** ~2 days, and it needs a written privacy review before it ships, which the
plan's §9.4 already anticipates.

---

## 4. What the integrated plan requires that neither UI document specifies

Part II specified what the simulation surfaces should *show*. The integrated plan adds
requirements about how they *behave*, and those are unspecified.

### U9 — Simulation is asynchronous and idempotent, and has no UI state model

M2: *"make submission asynchronous and idempotent; expose `POST /simulations` and
`GET /simulations/{id}` with cancellation/retry rules and stable terminal results."*

Part II's R11 command bar ends at `COMPILED — Mutation ready · [ Simulate ]`, and R14
begins with a finished result. **Everything between those two states is unspecified**,
and it is the part a user will spend real time looking at. Required:

- a run lifecycle with named states, and a rule that a non-terminal run never renders a
  partial finding as a finished one;
- what a duplicate submission does — idempotency means resubmitting shows the *existing*
  run rather than starting a second one, and the UI has to say so or the user will
  believe nothing happened;
- cancellation, and what a cancelled run leaves on screen;
- what happens when the user navigates away and returns, which is the common case for
  anything that takes more than a few seconds.

**There is a shipped precedent to build against.** `POST /graph-intelligence/analysis-requests`
returns `{ id, status, policy_key, requested_change_watermark }` — an async run with a
watermark and a status, in the contract today, with no client method and no UI (§1.2).
Building the run-lifecycle component against that endpoint during 2A means M2 inherits a
proven pattern instead of inventing one, and it gives Scan health a genuine control it
currently lacks.

**Effort.** ~2 days, and it should precede R14 rather than follow it.

### U10 — Refusal is a rendered object, not an error state

C2 requires *"machine-readable refusal reasons"*; §8 clause 3 requires that invalid,
ambiguous, contradicted, stale-beyond-policy or unsupported input be *"refused with a
stable code, human reason, and evidence link."*

Part II specified one refusal, in prose: *"No estate entity matches 'tree'."* That is one
of at least six distinct refusal classes, each of which needs a different next action:

| Refusal | What the user must be offered |
|---|---|
| No matching entity | what StackGraph can change, and how to search it |
| Ambiguous subject | the inline chooser — `INFERRED`, never a dead end |
| Contradicted fact | the contradiction, and its sources (R13) |
| Stale beyond policy | the watermark, its age, and the policy threshold it missed |
| Unsupported predicate/subject | the ontology's actual coverage, and that it is versioned |
| Scope or policy violation | which policy, which version, and who can clear it — `ESCALATE`, with an approver named |

**Recommendation.** One `RefusalNotice` keyed by stable code, rendering reason plus
evidence plus a class-appropriate next action, with an explicit unknown-code fallback
that shows the code rather than swallowing it. Two of the six rows map to `GateNotice`
states that already exist, which is where U0 earns its keep.

**Effort.** ~1.5 days. It is the difference between a demo where refusal is the
differentiator and one where refusal looks like a bug.

### U11 — The run provenance stamp

From §1.3: the fields exist and are already arriving. M1's determinism gate and §8
clause 8 both require that a result be reconstructable, and the plan's architecture rules
require every decision to record *"tenant, input fingerprint, estate/projection
watermark, policy versions, scanner/extractor versions, evidence IDs, actor, and
timestamps."*

**Recommendation.** One `RunProvenance` component — as-of, policy key and version,
watermark and its age, coverage, status — rendered on every snapshot-derived surface, and
inherited unchanged by `SimulationRun` and the Change Brief when they arrive. Under the
§4 language rule the machine strings stay on `title` and the surface reads *"Standard:
runtime-dependency v3 · checked 5 Sep 14:02 · graph current to 14:01"*, which is the
same treatment `CanvasControls` provenance already received in PR #86.

The stale case is the one that matters: when the projection watermark trails the
authoritative watermark past the policy threshold, this component is where
`NOT_SIMULATABLE` gets stated, with the age, before anyone reads a number that was
computed from a stale graph.

**Effort.** ~1 day, and it is buildable today against `GraphAnalysisSnapshot`.

### U12 — The AI-off state is a first-class layout, not a fallback

M2: *"allow deterministic results to succeed when AI is unavailable"*; §8 clause 9
requires AI-off and AI-timeout to preserve deterministic truth; §10 of the definition of
done says the UI *"never interleaves findings and interpretation"*.

R14 specified the partition and made the interpretation panel collapsible. It did not
specify the case where interpretation is **absent** — AI disabled, timed out, or
unavailable. The distinction matters because three different things must not look alike:
interpretation collapsed by the user, interpretation absent because AI is off, and
interpretation absent because every claim it produced failed to cite a finding.

**Recommendation.** The findings panel is unchanged in all three cases — that is the
guarantee. Where interpretation would sit, an absent state names which of the three
applies. R14's rule that an uncited claim renders as *"Not derived from the findings
above"* rather than being suppressed extends here: an interpretation that produced
nothing citable is a result about the AI, and hiding it silently is the same error as
hiding the claim.

**Effort.** ~0.5 day if specified before R14 is built; considerably more if retrofitted.

### U13 — Context API responses carry freshness and pagination

C2 requires the Context API endpoints to expose *"pagination, freshness, policy
version"*, and C1 requires provider freshness among the target-state inputs.

R11 specified the command bar's dropdown as counted, estate-backed candidates. It did not
specify what a paginated candidate list does — `Library 2,847 detected` cannot be a
scrollable list of 2,847 — or where provider freshness renders. A target-version
suggestion drawn from a registry snapshot three weeks old is a materially weaker claim
than one drawn from this morning's, and §12's non-negotiable is that the command surface
never invents a candidate; a stale candidate is a quieter version of the same failure.

**Recommendation.** Counts stay as counts and are never a promise of a full list;
refinement is the affordance, not scrolling. Provider freshness renders once, at the foot
of the target picker, beside the line that already says suggestions come from the estate.

**Effort.** ~0.5 day, specified into R11 rather than added after.

---

## 5. Revisions to Part II

Four, in light of what the plans actually say.

**R3′ is confirmed, with one addition.** M1 specifies exactly the classification set
Part II corrected to — `DIRECT`, `TRANSITIVE`, `CONTEXT`, `STOP`, `INFORMATIONAL` — and
requires recording *"deliberately stopped branches and reasons"*. Add: the ring's policy
line must name `policy_key`, `policy_version` and the pinned watermark, not a prose
summary, because M1's determinism gate is what the line exists to let a reader check.

**R7′ is larger than "a target picker".** §6 shows the comb carrying the *current estate
distribution* — `10.x 21 repos · 11.x 47 repos · 12.x 143 repos · 13.x 171 repos` —
alongside suggested targets labelled `Consolidate estate`, `Candidate upgrade`, and
`Latest — resolve at execution time`. So the comb has two data series, not one, and the
third suggested target is an `UNRESOLVED` value by construction: §8 clause 4 requires
`latest` to resolve to an immutable value before simulation. Choosing it must therefore
raise the resolution state, not hide it — which makes the comb the second natural call
site for `ResolutionLabel`, after container tags.

**R1′ gains a fifth colour-by, and it is free.** With U6, `cohort_key` becomes a way to
read the capability heat grid: which capabilities are implemented in the house archetype
and which are bespoke. It needs no new encoding — the existing segmented control and the
one sequential ramp cover it.

**R8′ ordering is confirmed by the plan's own sequence.** Part II argued the Change Brief
ships before the Estate Brief because it is used weekly rather than quarterly. The
integrated plan puts the Change Brief in M2/2B and the Estate Brief in E1/2E, which is
the same conclusion reached independently. No change.

---

## 6. The visual channel budget, re-derived

Part II §11.3 allocated seven channels for the axes Phase 2 introduced and concluded:
net new hues zero, net new ramps one. The scanner plan adds axes that assessment never
saw. Re-derived over everything now known:

| Axis | Channel | Note |
|---|---|---|
| Domain | hue — the four existing ramps | unchanged |
| Confidence | segments — `ConfidenceChip` | unchanged |
| Resolution | typography + glyph | now covers container tags and `latest` targets too |
| Impact classification | position — ring band | unchanged |
| Gate verdict | the one filled surface | unchanged |
| Spread / entropy | the one sequential ramp | legended surfaces only |
| Before / after | fill pattern — solid vs hatched | now also covers observed vs inferred language shares |
| **Corroboration depth** | **stacked hairlines** | 1–4, mandatory on simulation edges |
| **Entity level** (repo / component / app) | **label + position** | never a hue — U1 |
| **Repository classification** | **label set** | multi-valued; a hue cannot express a set |
| **Deployment provider** | **icon + label** | open set; hue would exhaust the budget immediately |
| **Workload kind** | **label** | — |
| **Archetype / cohort** | **label + count, ranked** | anomalous members quiet, never danger |
| **Change actor class** | **label + typography** | mono for authoritative, sans for inferred |
| **Lifecycle** (active / dormant / retiring) | **label** | — |

Net new hues: still **zero**. Net new ramps: still **one**. Seven new axes, all absorbed
by label, position, typography and pattern.

The rule that makes this hold is worth stating once: **an axis whose value set is open or
large cannot have a hue.** Providers, workloads, classifications and cohorts are all open
sets. Domain has a hue because it has exactly six members and always will.

---

## 7. Non-negotiables added by this assessment

Part II ended at thirteen. These continue the list.

14. **A repository count is not a component count.** After S1, any figure describing
    impact says which it is. Reporting affected repositories when some of their
    components are unaffected overstates impact, and precision is the reason Component
    exists.

15. **An unresolved container tag blocks simulation exactly as an unresolved subject
    does.** `latest` is not an identity. This is the digest rule and the resolution rule
    being the same rule.

16. **Actor data is aggregate and class-level.** No individual scoring, no per-person
    view, no leaderboard, no drill-through to a named contributor, and aggregates below
    the documented minimum cohort size are suppressed rather than published wide.

17. **A rate without its sample size is not shown.** Rollback rates, review times, and
    every predicted-versus-actual figure carry their denominator on the same line.

18. **A non-terminal run never renders as a finished one.** Partial findings from a
    running simulation are not findings yet.

19. **A refusal names its class and its next action.** A stable code with no offered move
    is an error message, and the product's claim is that refusal is the differentiator.

20. **Provenance travels with every derived number.** Policy version and watermark are
    part of the result, not operator telemetry, wherever the result is a traversal
    output.

---

## 8. What can start now, with no backend dependency

Ordered by ratio of value to blocking risk. Everything here is buildable against the
contract as it stands at this baseline.

| # | Work | Depends on | Effort |
|---|---|---|---|
| 1 | `RunProvenance` on snapshot-derived surfaces (§U11) | nothing — `GraphAnalysisSnapshot` already arrives | 1 d |
| 2 | Client methods + types for the four unreachable endpoints (§1.2) | contract-adjacent only; no server change | 1 d |
| 3 | Archetype surface on cohorts and motifs (§U6) | item 2 | 2 d |
| 4 | Corroboration depth on critical edges — the first real `CorroborationMark` call site | item 2 | 1 d |
| 5 | Run-lifecycle component against `analysis-requests` (§U9) | item 2 | 2 d |
| 6 | `/repositories` index + classification block (§U2) | nothing | 1.5 d |
| 7 | Fixtures for anomalies, motifs, critical edges, analysis requests | items 2–5 | 0.5 d |

Items 1, 4 and 5 each give one of the U0 primitives its first call site, which is what
turns §1.1 from an intention into something a test can hold. `packages/shared/src/fixtures`
has no fixture for any of the four endpoints, so item 7 is a prerequisite for testing
items 3–5 in fixture mode.

---

## 9. Open questions for the backend lane

Not requests. Each of these changes what the UI must render, and each is cheaper to
answer before the contract lands than after.

1. **Does a refusal carry a stable code enum in the contract, and is it closed?** U10's
   component is keyed by it. An open string set means the UI needs an unknown-code path,
   which is fine, but it should be a decision rather than a discovery.
2. **Does `SimulationRun.status` share a vocabulary with
   `GraphAnalysisRequestResult.status`?** If yes, U9's component serves both and the
   pattern is proven before M2. If no, the UI carries two run-state models.
3. **Where does `NOT_SIMULATABLE` live** — a run status, a finding classification, or a
   refusal code? It appears in M1, M2 and non-negotiable 13, and the three readings need
   different components.
4. **What is the cohort/archetype identity after S2?** If `cohort_key` from
   `/graph-intelligence/anomalies` is superseded by a deployment-profile archetype key,
   U6 should be built to re-point cleanly rather than to migrate.
5. **Is component identity path-based or authoritative?** The risk table says
   *"path-independent authoritative IDs where possible"*. The UI's routing, saved views
   and deep links all depend on which, and a path-based id that changes when a monorepo
   is reorganised breaks every saved link to it.
6. **What is the minimum cohort size for actor aggregates?** Non-negotiable 16 needs a
   number, and it belongs in policy rather than in a component's default prop.
7. **Do target suggestions carry provider freshness per suggestion or per response?**
   U13 renders it once per response today; per-suggestion would be a different control.

---

## 10. Sequencing, keyed to the plan's work packages

This slots UI work into the integrated plan's own lanes rather than proposing a parallel
schedule. Effort is UI only.

| Package | UI work | Effort |
|---|---|---|
| **B0 / Wave 0** | Items 1–7 of §8. `RunProvenance`, the four client methods and fixtures, the archetype surface, corroboration on critical edges, run lifecycle, repositories index | 9 d |
| **U0 (completion)** | First call sites for `GateNotice` and `ResolutionLabel`; a test that an inferred subject cannot render as resolved; refusal component (§U10) | 2.5 d |
| **S1 → 2A** | **U1 Component IA** — routes, level on rows, count semantics | 4 d |
| **S2/S3 → 2A** | U4 container composition and digest/tag resolution; U5 deployment profile | 4 d |
| **C2 → 2A** | R11 command states 1–3, R7′ comb with both series, U13 freshness and pagination | 6 d |
| **M1/M2 → 2B** | R14 partition **and** U12 AI-off state; R3′ ring with policy line; R1′ simulated heat grid; R2 funnel on findings; Change Brief | 8 d |
| **R1 → 2C** | R15 suggested changes; Simulate as a standard row action | 4 d |
| **T1/H1 → 2D** | U7 activity and hotspots; U8 actor mix and outcomes; drift strip; calibration plot | 6 d |
| **E1/S4 → 2E** | U3 repository fingerprint; R13 contradiction ledger; six-band stratum bar; Business Map revisions; Estate Brief | 8 d |
| **A1 → 2F** | R16 capability envelope and flight recorder | 5 d |

**≈56 UI days**, against the ~41 the integrated plan §12 currently carries. The delta is
almost entirely §3 — the scanner plan's surfaces, which no UI estimate has included
because no UI document had read it. §12 of the integrated plan should be updated to
carry the revised figure, or this document should be cited as the reason it differs.

Two notes on the shape. **B0 grew and is now the largest single block that is not
blocked on anything** — nine days of work that needs no backend change and that proves
three U0 primitives on the way. And **U1 is the one item whose cost rises the longer it
waits**: every surface built between now and S1 that treats the repository as the unit of
impact is a surface that has to be revisited.

---

## 11. What this document got from re-reading, and what to check next

**Corrected here:**

- Part II assessed one of the three plans. `scanner-improvements.md` was never read, and
  it carries six new entity concepts, one of which (Component) changes the level of
  abstraction the whole UI is built at.
- Part II's estimate of ~41 UI days omitted all of §3.
- R7′ was specified as a target picker carrying one series. §6 of the plan shows two.

**Confirmed, no change:** R3′'s classification bands, R8′'s Change-Brief-before-Estate-Brief
ordering, the colour budget's conclusion, and the judgement that ⌘K should not have been
built as the Part I palette.

**To check when the contract lands:** everything in §9, and every Phase 2 field name used
above. §0 is the caveat that governs them.
