# UI Phase 2 Alignment

**Status:** review document, verified against the shipped contract.
**Baseline:** `origin/main` at `a970bfb` ("backend improvements"), which added the Phase 2
API surface. Previous revision of this document was written against `f5eed18`, before
that commit existed; §2 lists what it got wrong.
**Assessed against:** [`phase-2-integrated-implementation-plan.md`](phase-2-integrated-implementation-plan.md),
[`phase-2-plan.md`](phase-2-plan.md), [`scanner-improvements.md`](scanner-improvements.md),
and `stackgraph-foundation/contracts/v1/openapi.json` as it now stands.
**Relationship to [`ui-recommendations.md`](../ui-recommendations.md):** Part II stays
normative for R1–R16. This document adds U1–U13, corrects R7′ and R11, and revises the
UI estimate.

---

## 0. Contract status

The Phase 2 API has landed. `openapi.json` went from **89 to 101 paths** and gained
**29 schemas**. Nothing was removed.

| New endpoint | Returns |
|---|---|
| `GET /action-types` | `ActionTypeList` |
| `GET /action-types/{predicate}/subjects` | `ActionSubjectList` |
| `GET /entities/{id}/valid-targets` | `ValidTargetList` |
| `GET /entities/{id}/scopes` | `ChangeScopeList` |
| `GET /entities/{id}/change-history` | `ObservedMutationList` |
| `POST /mutations/compile` | `MutationCompileResult` |
| `POST /mutations/validate` | `MutationCompileResult` |
| `POST /modernization-recommendations/{id}/compile` | `MutationCompileResult` |
| `POST /simulations` | `202` → `SimulationRunModel` |
| `GET /simulations/{id}` | `SimulationRunModel` |
| `DELETE /simulations/{id}` | `SimulationRunModel` (cancel) |
| `POST /observed-mutations` | `201` → `ObservedMutationModel` |
| `GET /repositories/{id}/fingerprints` | `RepositoryFingerprintList` |

This document is therefore no longer speculative about field names. Every schema quoted
below is read from the shipped contract.

---

## 1. What the contract confirms

Worth stating first, because it is the reassuring half and it decides how much of the UI
work is now unblocked.

**The gate and resolution vocabularies match the design system exactly.** PR #86 shipped
`GateVerdict` and `ResolutionState` ahead of any consumer, guessing at their members from
the plan's prose. The contract independently arrived at the same two enums:

```
ChangeGate.state        BLOCKED | ESCALATE | CONSTRAIN | CLEAR
EntityResolution.state  RESOLVED | INFERRED | UNRESOLVED
```

Both shapes also carry what the components need and Part II specified without knowing
they would exist:

- `GateReason { code, message, evidence_fact_ids }` — a gate can name its blocker and
  link to evidence, which is what makes it a gate rather than a caution tone;
- `EntityResolution { candidates[], confidence, method, method_version }` — candidates for
  the inline chooser, and **`confidence` as a field distinct from `state`**, which is the
  two-axis argument made in the schema rather than only in a document.

`GateNotice` and `ResolutionLabel` can be wired to real data without modification.

**Four more Part II positions are confirmed by enums rather than by argument:**

| Contract | Confirms |
|---|---|
| `SimulationFinding.classification` = `DIRECT \| TRANSITIVE \| CONTEXT \| STOP \| INFORMATIONAL` | R3′ — the correction from hop-distance banding to classification banding, `STOP` included |
| `MutationCompileResult.command_state` = `EMPTY \| RESOLVING \| TOKENISED \| COMPILED` | R11's four command states |
| `ActionTypeSummary.predicate` = `UPGRADE \| REPLACE \| REMOVE \| DEPRECATE \| MIGRATE \| MOVE` | C1's bounded verb set; no `CHANGE`, `IMPROVE`, or `TRANSFORM` |
| `SimulationInterpretation.cited_finding_ids` | R14 — interpretation cites findings by id, structurally |

**`SimulationRunModel` is the provenance stamp U11 asked for**, and then some:

```
status  QUEUED | RUNNING | SUCCEEDED | LIMITED | NOT_SIMULATABLE | FAILED | CANCELLED
estate_watermark   policy_version   provider_version   scanner_versions[]
result_hash        replayed         gate: ChangeGate   limitations: GateReason[]
```

Two fields there are more interesting than the rest. `result_hash` makes M1's
determinism gate checkable *by a reader on a screen* rather than only in a test.
`replayed: boolean` means a run can be a replay of an earlier one, which is a state the
UI has to say out loud — a user looking at a replayed result and believing it was
computed fresh is exactly the confusion the watermark exists to prevent.

---

## 2. What the contract corrects in the previous revision

Six items. Four are mine to fix; two were open questions the contract has now answered
against the option I had leaned toward.

**2.1 — The premise was wrong, and briefly.** The previous revision opened with "the
Phase 2 endpoints are not in the repository yet", verified at `f5eed18`. True then, false
now. §0 replaces it.

**2.2 — The run-lifecycle recommendation was wrong.** §8 previously proposed building the
async-run component against `POST /graph-intelligence/analysis-requests` "so M2 inherits a
proven pattern". The two state models are not the same:

```
GraphAnalysisRequestResult.status   PENDING | WAITING_FOR_PROJECTION
SimulationRunModel.status           QUEUED | RUNNING | SUCCEEDED | LIMITED
                                    NOT_SIMULATABLE | FAILED | CANCELLED
```

Building against the two-state endpoint would have produced a component that has to be
rewritten. Build the run lifecycle against `SimulationRunModel` directly. The
`analysis-requests` endpoint is still worth a client method (§3.2), just not as the model
for this.

**2.3 — Target freshness is per-target, not per-response.** U13 previously put provider
freshness "once, at the foot of the target picker". `ValidTarget` carries it per row, and
carries a second axis alongside it:

```
ValidTarget { version, entity_id, canonical_key, source, observed_at,
              freshness: FRESH | STALE | UNKNOWN,
              support:   SUPPORTED | UNKNOWN | UNSUPPORTED }
```

Freshness and support are independent — a target can be freshly observed and unsupported,
or stale and supported — so they need two readings, not one badge. A footer cannot
express either.

**2.4 — `NOT_SIMULATABLE` is a run status.** The previous §9 asked whether it was a run
status, a finding classification, or a refusal code, and said the three readings need
different components. It is the first: a terminal value of `SimulationRunModel.status`,
alongside `LIMITED`. So it renders in the run header, not in the findings list, and it
sits beside a `LIMITED` state the previous revision did not anticipate at all —
a run that succeeded with reduced coverage is a third outcome between success and
"cannot simulate".

**2.5 — Refusal codes are open strings.** `GateReason.code` and
`MutationValidationError.code` are both `string`, not enums. The previous §9 asked whether
the set was closed. It is not, so U10's unknown-code path is required rather than
defensive.

**2.6 — Component is already in the contract.** U1 was written as a consequence of S1
landing later. It is here now:

```
ChangeScope.kind = ESTATE | REPOSITORY | COMPONENT
ChangeScope.component_path: string | null
```

This makes U1 more urgent, not less, and it moves where Component first appears in the
UI. See §4.1.

---

## 3. Where the UI stands

Re-verified against `a970bfb`. All four findings from the previous revision hold, and the
second one is now much larger.

### 3.1 U0 is defined but still unproven — zero call sites

Unchanged from the previous revision, re-counted at this baseline. Outside
`packages/design-system/src`: `GateNotice` 0, `ResolutionLabel` 0, `CorroborationMark` 0,
`Sparkline` 0, `GATE_LABEL` 0, `RESOLUTION_LABEL` 0, `IconStrata` 0, `IconBlast` 0.

U0's exit gate — *"no component can make inferred identity appear resolved"* — still
cannot be tested, because nothing renders a resolution state. The difference now is that
**there is real data to wire them to**: every `MutationCompileResult` carries a
`ChangeGate`, and every `MutationIR.subject` is an `EntityResolution`. The blockers are
gone.

### 3.2 Twelve endpoints and twenty-nine schemas the UI cannot reach

`apps/web/` has no changes in `a970bfb`, which is the intended split. But the shared
package is only half wired:

| Layer | State |
|---|---|
| `stackgraph-foundation/contracts/v1/openapi.json` | 12 new paths, 29 new schemas |
| `packages/shared/src/contracts/openapi.generated.ts` | regenerated, carries all 29 |
| `packages/shared/src/contracts/read-models.ts` | **none of the 29** |
| `packages/shared/src/api/client.ts` | **no method for any of the 12** |

Verified by normalising every `req()` template path in the client against the spec: none
of the twelve match. `read-models.ts` is what `apps/web` imports through
`@stackgraph/shared`, so nothing in the UI can currently name a `MutationIR`, let alone
fetch one.

The four endpoints named in the previous revision are still unreachable too —
`/entities/{id}/critical-edges`, `/graph-intelligence/anomalies`,
`/graph-intelligence/motifs`, `POST /graph-intelligence/analysis-requests` have no client
method and no type. So the total is **sixteen endpoints the frontend cannot call**.

This is now the single largest blocker to every UI item in this document, and it is
frontend-lane work.

### 3.3 Run provenance still arrives unrendered

`GraphAnalysisSnapshot` is unchanged by `a970bfb` and still ships `policy_key`,
`policy_version`, `policy_hash`, `neo4j_projection_watermark` and
`requested_change_watermark` on every traversal result. A search across `apps/web` for
`policy_version`, `policy_hash` or `estate_watermark` in `.tsx` returns nothing.

The stakes rose: `SimulationRunModel` carries the same concepts under different names
(`estate_watermark`, `policy_version`, plus `result_hash` and `scanner_versions`). One
component built now against the snapshot serves both, and there is a real risk of two
divergent provenance renderers if the simulation surfaces are built first.

### 3.4 Read models still unconsumed

`getRepositoryCapabilities`, `getCapabilityTaxonomy`, `getPhase3IntelligenceMetrics`,
`getBusinessMapRevisions` — all still zero call sites in `apps/web`.
`listCapabilityFootprints` has one, from PR #86.

### 3.5 No fixtures for any of it

`packages/shared/src/fixtures` has no fixture for any of the twelve new endpoints or the
four older unreachable ones. `NEXT_PUBLIC_DATA_SOURCE=fixtures` is how the e2e suite runs
by default, so fixtures are a prerequisite for testing any of this, not an afterthought.

---

## 4. UI surfaces required by the scanner plan

`scanner-improvements.md` still has no UI assessment outside this document, and the
integrated plan's §14 traceability still maps its topics to backend packages only. What
follows is unchanged in substance from the previous revision except where the contract
has now confirmed or moved something; those points are marked.

### U1 — Component becomes the unit of impact *(confirmed by contract, and now urgent)*

**What changed.** `ChangeScope.kind` already includes `COMPONENT`, with a
`component_path` and its own `affected_count` and `version_distribution`. So the first
place a user meets a component is **the scope picker in the command bar** — not the estate
list, not the repository page. A user will be asked to choose "this component" as the
blast radius of a change before the product has anywhere to show them what a component is.

**What has not changed.** `RankedItem` is untouched: `domain` is still the six
namespaces, `kind` is still a free string, and there is no component field. There is no
`/components` route and no `/repositories` index route — only `/repositories/[id]`,
reachable by drilling from elsewhere.

**The three consequences stand.**

1. The estate's five domain bands are an entity-kind taxonomy and Component does not fit
   any of them. `RankedTable` already has the mechanism for the fix: `showDependencyTier`
   adds a column only when items carry that field. Entity level follows the same pattern.
   The fix is to make level explicit in the row, not to add a band.
2. Every count that says "repositories" becomes ambiguous. A repository count that hides
   an unaffected component overstates impact — the precise failure Component exists to
   fix. `ChangeScope.affected_count` is scope-kind-dependent, so the same number means
   three different things depending on `kind`, and the UI has to say which.
3. Drill-through gains a hop, and canvas occupants are placed by component.

**Recommendation.** Unchanged, and moved earlier: a `/components` route and detail
surface as peers of Applications; level rendered on every row where two levels can appear
together, by label and position, never a new hue; impact counts as `n components in m
repositories` wherever the scope is component-derived. Add: **the scope picker renders
`kind` explicitly**, because `ESTATE`, `REPOSITORY` and `COMPONENT` are three different
promises about what a change will touch.

**Effort.** ~4 days, and now on the C2 critical path rather than the S1 one.

### U2 — Repository classification is multi-label

Unchanged. Multi-valued architecture plus contained kinds plus frameworks plus deployment
profiles, at a confidence. The repository page renders a single `kind`. An empty
`contains` is "nothing classified yet", not "contains nothing" — the `CELL_STATE_LABEL`
distinction between "None found" and "Not observed", applied to a new object.

**Effort.** ~1 day.

### U3 — The repository fingerprint page *(endpoint now exists)*

**What changed.** `GET /repositories/{id}/fingerprints` ships, returning
`RepositoryFingerprintSnapshot[]`:

```
fingerprint  profile: object  confidence  fact_id
source_revision  observed_at  system_from  system_to
```

Three things follow. `fact_id` means every snapshot links to evidence, which is what the
scanner plan asked for. `system_from`/`system_to` make it **bitemporal**, so the page can
show a repository's fingerprint as it was at a point in time — the first surface in the
product that could, and the natural home for "what changed about this repo since last
quarter". And `profile` is an **untyped `object`**, so the UI cannot render it
type-safely; see §10.

**Effort.** ~3 days once U2/U4/U5/U7 exist as blocks, plus whatever `profile` typing
costs.

### U4 — Container composition, and the digest/tag resolution insight

Unchanged, and the connection it rests on is now stronger: `EntityResolution` is a real
contract type, so mapping a pinned digest to `RESOLVED`, an ambiguous tag to `INFERRED`,
and `latest` to `UNRESOLVED` reuses a shipped shape rather than an argument by analogy.
The integrated plan's risk table already says digests are canonical and tags are
"temporal observations with explicit unresolved state".

**Effort.** ~2.5 days.

### U5 — Deployment profile

Unchanged. Verb-plus-target rows, because "Deploys to Vercel · Runs jobs on Databricks"
says something "Vercel, Databricks" does not. No hue for provider: an open set would
exhaust the colour budget on day one. `canvas-ui`'s `icons.tsx` is the precedent worth
copying rather than extending — it maps semantic keys to glyphs and reports unknown keys
instead of silently degrading, which is what a provider registry needs on the day a
provider the UI has never seen arrives from a scan.

**Effort.** ~1.5 days.

### U6 — Architecture archetypes, with a data source already shipping

Unchanged. `GET /graph-intelligence/anomalies` returns `cohort_key`, `cohort_size`,
`percentile`, `reasons`; `GET /graph-intelligence/motifs` returns recurring patterns with
members and a minimum confidence. A cohort with a size is an archetype distribution; an
entity scoring high against its own cohort is "bespoke / anomalous". Both still need a
client method and a type (§3.2).

The trap stands: an anomalous cohort member is an observation that something differs from
its peers, not a fault. Same class of statement as `UNEVALUABLE`, same quiet treatment.

**Effort.** ~2 days, plus ~0.5 to re-point at deployment profiles when S2 lands.

### U7 — Activity and velocity *(partly available now)*

**What changed.** `GET /entities/{id}/change-history` ships, returning
`ObservedMutationList`. That is not the full `RepositoryActivityProfile` — no velocity,
hotspots, or ownership concentration yet — but it is a per-entity change series with
outcomes, which is the harder half and the part R5's sparklines were built for.

`ObservedMutationModel` carries `observed_at`, `success`, `rolled_back`,
`intervention_required`, `predicted_simulation_run_id`, `graph_watermark_before`,
`observed_impact` and `unexpected_impact`.

**Effort.** ~2 days for the drift strip against change history; the remaining activity
profile waits on T1.

### U8 — Change actors

Unchanged, and still the item with the strongest constraints. `ObservedMutationModel` has
`source_kind` and `confidence`, which is where an actor taxonomy would attach, but the
`ChangeActor` enum from the scanner plan is not in the contract yet.

Both constraints stand and both are UI requirements, not backend policy:

- an authoritative actor signal is a scanned fact and renders mono; an inferred one is
  StackGraph's reading and renders sans — the same mechanism as U4's digest/tag split;
- **the actor surface shows classes, never individuals.** No per-contributor view, no
  leaderboard, no per-person drill-through, and aggregates below a documented minimum
  cohort size suppressed rather than published wide. `ownership_concentration` is a
  repository property and must never resolve to a named person.

**Effort.** ~2 days, and it needs a written privacy review before it ships.

---

## 5. Behaviour the plans require and neither UI document specified

Now written against the shipped schemas rather than against the plan's prose.

### U9 — The simulation run lifecycle

`POST /simulations` returns **202** with a `SimulationRunModel`, takes an
`idempotency_key` in the request body, and `DELETE /simulations/{id}` cancels. R11 ends at
`[ Simulate ]` and R14 begins with a finished result; everything between is still
unspecified, and it now has an exact seven-state shape:

```
QUEUED → RUNNING → SUCCEEDED | LIMITED | NOT_SIMULATABLE | FAILED | CANCELLED
```

Required, and each of these is a distinct thing to draw:

- **Non-terminal runs never render a partial finding as a finished one.** `QUEUED` and
  `RUNNING` show the run, not its findings.
- **`LIMITED` is not `SUCCEEDED`.** A run that completed with reduced coverage carries
  `limitations: GateReason[]`, and those belong beside the numbers they qualify, which is
  the placement rule the `Limitations` component already follows.
- **`NOT_SIMULATABLE` is a terminal answer, not an error.** It has reasons and it is the
  product being honest; it should not look like `FAILED`.
- **Idempotency has to be visible.** The UI owns the `idempotency_key`, so resubmitting
  shows the *existing* run. Without a line saying so, a user will believe nothing
  happened and press it again.
- **`replayed: true` is stated on screen.** A replayed result is not a fresh computation.
- **Cancellation returns the run**, so a cancelled run still has a page.

**Effort.** ~2.5 days, and it precedes R14 rather than following it.

### U10 — Refusal as a rendered object

`ChangeGate { state, reasons: GateReason[] }` arrives on **every** `MutationCompileResult`
— compile, validate, and recommendation-compile alike. `GateReason` is
`{ code, message, evidence_fact_ids }` and `MutationValidationError` adds `field`.

Two refinements to the previous revision:

- **`code` is an open string**, so an unknown-code fallback that shows the code rather
  than swallowing it is required, not defensive (§2.5);
- **`field` scopes an error to a token.** A validation error is not a page-level banner;
  it points at the subject chip, the target chip, or the scope chip, and the command bar
  has to be able to highlight the one it names.

The six refusal classes and their next actions stand: no matching entity, ambiguous
subject, contradicted fact, stale beyond policy, unsupported predicate, and scope or
policy violation. Two map onto `GateNotice` states that already exist, which is where U0
earns its keep.

**Effort.** ~1.5 days.

### U11 — The run provenance stamp

Build one `RunProvenance` component now against `GraphAnalysisSnapshot`, and have
`SimulationRunModel` reuse it. The field names differ between the two — `as_of` versus
`created_at`/`completed_at`, `neo4j_projection_watermark` versus `estate_watermark` — so
the component takes a normalised shape and each caller maps into it. Building it twice is
the failure mode to avoid.

Renders: as-of, policy key and version, watermark and its age, coverage, status, and —
for simulations — `result_hash`, `scanner_versions` and `replayed`. Under the §4 language
rule the machine strings stay on `title`.

**Effort.** ~1 day, buildable today.

### U12 — The AI-off state *(confirmed, and named by the contract)*

The previous revision argued the UI must distinguish three cases: interpretation
collapsed by the user, absent because AI is off, and absent because its claims could not
be cited. The contract names exactly that third axis:

```
SimulationInterpretation.status = AVAILABLE | UNAVAILABLE | QUARANTINED
```

`QUARANTINED` is the uncited-claim case, given a name. R14's rule extends to it directly:
a quarantined interpretation renders as quarantined and says so, rather than being
suppressed, because an interpretation that produced nothing citable is a result about the
AI and hiding it is the same error as hiding the claim.

The guarantee is unchanged in all three states: **the findings panel is identical**. It
does not move, collapse, or change when interpretation is absent.

`SimulationInterpretation` also carries `limitation`, `risk`, `rollout[]`,
`verification[]` and `cited_finding_ids[]`, which is R14's structure field for field.

**Effort.** ~0.5 day if specified into R14 before it is built.

### U13 — Target and scope pickers carry two axes, per row

Corrected per §2.3. `ValidTarget` carries `freshness` (`FRESH | STALE | UNKNOWN`) and
`support` (`SUPPORTED | UNKNOWN | UNSUPPORTED`) **per target**, plus `source` and
`observed_at`. They are independent, so a row can be freshly observed and unsupported.

Two readings per row, then — not one badge, and not a footer. `support` is the one that
changes a decision, so it leads; `freshness` qualifies the claim and takes the quieter
treatment. An `UNSUPPORTED` target is not blocked, because choosing to move onto an
unsupported version is a decision a user is allowed to make with their eyes open, but it
is the row that carries the strongest reading on the picker.

**Effort.** ~1 day.

---

## 6. Revisions to Part II

**R7′ — confirmed exactly, by two schemas.** The previous revision corrected R7′ to carry
two series. The contract puts them in two places: `ChangeScope.version_distribution` is
`{ version, count }[]` — the current estate distribution — and `ValidTargetList` is the
suggested targets. So the comb reads the scope for its teeth and the target list for its
markers. `latest` remains `UNRESOLVED` by construction, so choosing it raises the
resolution state rather than hiding it.

**R11 — the command state machine is server-driven.** `MutationCompileResult.command_state`
returns `EMPTY | RESOLVING | TOKENISED | COMPILED`. The command bar renders the state the
server reports rather than deriving it from what the user has typed. That is a better
design than the one R11 assumed, and it removes the risk of client and server disagreeing
about whether a mutation is compiled.

**R3′ — confirmed.** `SimulationFinding.classification` is the exact five-value set, and
`SimulationFinding.path: EntitySummary[]` means the ring can render named hops without the
neighbourhood lookup the current blast-radius drawer needs.

**R15 — the endpoint exists.** `POST /modernization-recommendations/{id}/compile` takes
only an `idempotency_key` and returns a full `MutationCompileResult`. "Simulate
recommendation" is one call from any recommendation row, which is what R15 asked for and
cheaper than it estimated.

**R1′, R8′ — no change.**

---

## 7. The visual channel budget

Re-derived over every axis now known, including those the contract added.

| Axis | Channel |
|---|---|
| Domain | hue — the four existing ramps |
| Confidence | segments — `ConfidenceChip` |
| Resolution (`EntityResolution.state`) | typography + glyph |
| Impact classification (`SimulationFinding.classification`) | position — ring band |
| Gate verdict (`ChangeGate.state`) | the one filled surface |
| Spread / entropy | the one sequential ramp, legended surfaces only |
| Before / after | fill pattern — solid vs hatched |
| Corroboration depth | stacked hairlines |
| Entity level / `ChangeScope.kind` | label + position |
| Repository classification | label set |
| Deployment provider | icon + label |
| Workload kind | label |
| Archetype / cohort | label + count, ranked |
| Change actor class | label + typography |
| Lifecycle (`ActionTypeSummary.lifecycle`, `MutationIR.lifecycle`) | label |
| Run status (`SimulationRunModel.status`) | label + position in the run header |
| Target support / freshness (`ValidTarget`) | label pair, per row |
| Interpretation status | label, in the partition header |

Net new hues: **zero**. Net new ramps: **one**. Eleven axes beyond Part II's seven, all
absorbed by label, position, typography and pattern.

The rule that makes it hold: **an axis whose value set is open or large cannot have a
hue.** Providers, workloads, classifications, cohorts and refusal codes are all open.
Domain has a hue because it has exactly six members and always will.

---

## 8. Non-negotiables added by this assessment

Continuing Part II's list of thirteen.

14. **A repository count is not a component count.** `ChangeScope.affected_count` means
    three different things depending on `kind`, and every figure describing impact says
    which.
15. **An unresolved container tag blocks simulation exactly as an unresolved subject
    does.** `latest` is not an identity.
16. **Actor data is aggregate and class-level.** No individual scoring, no per-person
    view, no leaderboard, and aggregates below the documented minimum cohort size are
    suppressed rather than published wide.
17. **A rate without its sample size is not shown.**
18. **A non-terminal run never renders as a finished one**, and `LIMITED`,
    `NOT_SIMULATABLE` and `FAILED` never render alike.
19. **A refusal names its class and its next action**, and an unknown `code` is displayed
    rather than swallowed.
20. **Provenance travels with every derived number** — policy version, watermark, and for
    simulations `result_hash` and `replayed`.

---

## 9. What can start now

Everything here is buildable against the contract as it stands. Ordered by what unblocks
the most.

| # | Work | Depends on | Effort |
|---|---|---|---|
| 1 | Client methods + `read-models.ts` types for the 12 Phase 2 endpoints (§3.2) | nothing — schemas are already generated | 2 d |
| 2 | Client methods + types for the 4 older unreachable endpoints (§3.2) | nothing | 1 d |
| 3 | Fixtures for all 16, so the e2e suite can run in its default mode (§3.5) | items 1–2 | 1.5 d |
| 4 | `RunProvenance` against `GraphAnalysisSnapshot`, shaped for `SimulationRunModel` (§U11) | nothing | 1 d |
| 5 | `GateNotice` + `ResolutionLabel` first call sites on `MutationCompileResult` (§3.1) | items 1, 3 | 1.5 d |
| 6 | Run-lifecycle component against `SimulationRunModel` (§U9) | items 1, 3 | 2.5 d |
| 7 | Refusal renderer keyed by `GateReason.code` with `field` scoping (§U10) | items 1, 3 | 1.5 d |
| 8 | Archetype surface on cohorts and motifs (§U6) | items 2, 3 | 2 d |
| 9 | Corroboration depth on `critical-edges` — first `CorroborationMark` call site | items 2, 3 | 1 d |
| 10 | `/repositories` index + classification block (§U2) | nothing | 1.5 d |

**≈15.5 days**, none of it blocked on the backend. Item 1 is the gate on almost
everything else and should start first. Items 5, 6, 7 and 9 each give a U0 primitive its
first call site, which is what turns §3.1 from an intention into something a test can
hold.

---

## 10. Open questions for the backend lane

Most of the previous revision's questions were answered by the contract. What remains:

1. **`RepositoryFingerprintSnapshot.profile` is an untyped `object`.** The fingerprint
   page (U3) cannot render it type-safely, and a UI that reaches into an untyped payload
   is the thing `read-models.ts` exists to prevent. Is a typed schema planned, or should
   the UI treat `profile` as a versioned extension payload and render only a known
   subset?
2. **`ActionSubject.resolution` is a plain `string`, while `EntityResolution.state` is an
   enum.** If they mean the same thing, the UI should render them the same way, and the
   looser type will let them drift.
3. **Is component identity path-based or authoritative?** `ChangeScope.component_path`
   suggests path-based. Routing, saved views and deep links all depend on this, and a
   path-based id breaks every saved link when a monorepo is reorganised.
4. **What is the minimum cohort size for actor aggregates?** Non-negotiable 16 needs a
   number, and it belongs in policy rather than a component's default prop.
5. **Does `ChangeActor` land on `ObservedMutationModel.source_kind`, or as its own field?**
   U8's typographic rule depends on being able to tell an authoritative signal from an
   inferred one, which needs the confidence and the source together.
6. **Will `RankedItem` gain a component level, or do components get their own list
   endpoint?** U1's estate work differs depending on which.

---

## 11. Sequencing

Slotted into the integrated plan's own work packages. Effort is UI only.

| Package | UI work | Effort |
|---|---|---|
| **B0 / now** | §9 items 1–10 | 15.5 d |
| **U0 (completion)** | Test that an inferred subject cannot render as resolved; the remaining gate states | 1 d |
| **C2 → 2A** | R11 command bar on `MutationCompileResult`; R7′ comb from `ChangeScope` + `ValidTargetList`; U13 per-row support and freshness; **U1 scope picker with `kind`** | 6 d |
| **S1 → 2A** | U1 estate IA — `/components`, level on rows, count semantics | 4 d |
| **S2/S3 → 2A** | U4 container composition; U5 deployment profile | 4 d |
| **M2 → 2B** | R14 partition **and** U12 interpretation status; R3′ ring from `SimulationFinding.path`; R1′ simulated heat grid; R2 funnel; Change Brief | 7 d |
| **R1 → 2C** | R15 on `/modernization-recommendations/{id}/compile`; Simulate as a standard row action | 3 d |
| **T1/H1 → 2D** | U7 drift strip on change history; U8 actor mix; calibration plot from `predicted_simulation_run_id` | 6 d |
| **E1/S4 → 2E** | U3 fingerprint page; R13 contradiction ledger; six-band stratum bar; Business Map revisions; Estate Brief | 8 d |
| **A1 → 2F** | R16 capability envelope and flight recorder | 5 d |

**≈59.5 UI days**, against the ~41 carried in §12 of the integrated plan. The delta is
§4 — the scanner plan's surfaces — plus §5, the run behaviour. Three items came *down*
because the contract does more than assumed: R15, R3′'s named paths, and R11's
server-driven state.

§12 of the integrated plan should either carry the revised figure or cite this document
as the reason it differs. That is the plan owner's call, not mine.

---

## 12. Revision history

**This revision (`a970bfb`):** verified every claim against the shipped contract.
Corrected six items (§2). Confirmed the gate and resolution vocabularies, R3′, R11's
states, R7′'s two series, U12's third case, and R15's endpoint. The reachability finding
grew from four endpoints to sixteen. §9 grew from 9 days to 15.5 and is now the critical
path for everything else.

**Previous revision (`f5eed18`):** written before the Phase 2 API existed. Its §0 caveat
about specified-versus-read field names no longer applies; every schema quoted here is
read from the contract.

**Note on how this reached `main`.** PR #87 merged at `06215ac`, the previous revision,
minutes before the verified rewrite was pushed to the same branch. `main` therefore
carried the pre-contract version — including the claim that the Phase 2 endpoints did not
exist — until this change replaced it. Nothing was lost; the correction simply arrived in
a second PR.

**Still to check:** the six questions in §10, and `ChangeActor` when it lands.
