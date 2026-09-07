# Phase 2 gap audit

**Reviewed:** `docs/phase-2-plan.md` and `docs/phase-2-integrated-implementation-plan.md` against the
code on `claude/phase-2-plan-review-gwjpnl` (merge of `origin/main` at `1b7e3fe`).

> **Status: remediated.** Every gap below has been closed on this branch. The findings are kept
> as written so the reasoning stays reviewable; [§10 Resolution](#10-resolution) records what
> changed for each, and the two corrections marked in the text are corrections to *this
> document*, not to the code.
**Method:** every plan clause was traced to a producer (scanner, worker, ingest), a persistence
path, an API surface, and a UI surface. A clause counts as delivered only when all four exist and
are reachable in a real tenant — a schema plus a read endpoint with no writer is recorded as partial.

The intent is not to relitigate the deliberate boundaries in
[`phase-2-backend-implementation.md`](phase-2-backend-implementation.md). Those are restated here
only where the plan's own exit gate is stricter than the boundary, or where a boundary is wider in
the code than the document claims.

## Summary

| Package | Plan sections | State |
| --- | --- | --- |
| B0 baselines and evaluation | §38, plan §9–§10 | **Partial** — ADRs, flags, latency gate and recovery drill exist; the golden corpus is empty and no scanner benchmark exists |
| S1 components and classification | §37, scanner plan | **Delivered in the scanner; not persisted** — typed profiles have no writer |
| S2 deployment profiles | §25 | **Partial** — schema and read API only |
| S3 container composition | §21, §25 | **Partial** — schema and read API only |
| T1 temporal and actors | §29 | **Partial** — 5 of 10 event types have no producer |
| S4 fingerprints and archetypes | §37 | **Delivered** |
| I1 identity and provenance | §10, §18, §19 | **Delivered for Package; unverified** — the >99% precision gate has no corpus to measure against |
| C1 action ontology and providers | §4, §6, §21 | **Partial** — one hardcoded capability; `ActionCapability` columns are never read |
| C2 Mutation IR, ChangeSet, Context API | §3, §5, §7, §9, §15 | **Partial** — single-mutation only; three of seven entry points |
| U0 safety vocabulary | UI plan | **Delivered** |
| M1 impact policies and traversal | §12 | **Partial** — the policy record is pinned but its configuration never drives traversal |
| M2 overlay, findings, explanation | §13, §14 | **Partial** — the overlay is nominal; the AI interpretation layer is absent |
| R1 recommendation to action | §8, §16 | **Partial** — modernization only |
| H1 change memory | §29, §30 | **Partial** — manual entry only; no predictors |
| E1 estate fidelity | §20–§28, §31–§33 | **Partial** — capability mapping is real; lineage, AI supply chain, assumptions and contradictions are read surfaces without producers |
| A1 AI control plane | §34, §35 | **Delivered** (§36 immune system deliberately deferred) |

---

## 1. Blocking gaps in the shipped vertical slice

These affect `UPGRADE Package`, which is the one path the plan declares active.

### 1.1 The impact policy does not drive traversal

`impact_policy` is read once, to pin `id`, `version` and `content_hash` onto the run
(`apps/api/app/phase2_changes.py:1042`, `:1074`). Its `configuration` — edge list, per-edge
direction, `max_depth`, `minimum_confidence`, `stop_conditions` — is never read. The traversal is
hardcoded SQL in `_execute_simulation` (`apps/api/app/phase2_changes.py:1279`, `:1360`) with the
0.80 confidence floor written as a Python literal (`:1306`, `:1407`).

Two consequences:

- M1's exit gate ("persist `ImpactPolicy` … use different policies for package upgrade, API
  deprecation, runtime change, database migration, service move") is structurally unmet. Adding a
  second predicate means writing new SQL, not seeding a policy row.
- Editing the policy row changes the pinned hash without changing behaviour, so two runs can carry
  different policy versions and identical results, or the reverse. That silently weakens the
  determinism claim in §9.1.

The seeded configuration also names predicates that do not exist in the ontology —
`SUPPORTS` and `BELONGS_TO` (`infrastructure/database/migrations/047_phase2_change_compiler.sql:262-263`
against `stackgraph-foundation/contracts/v1/ontology.registry.json:11-51`). Nothing catches this
today precisely because the configuration is inert.

### 1.2 No `TRANSITIVE` classification is ever produced

The findings vocabulary is `DIRECT`, `TRANSITIVE`, `CONTEXT`, `STOP`, `INFORMATIONAL`, and the
result ordering handles all five (`apps/api/app/phase2_changes.py:1123`). The engine emits only four:
`DIRECT` (`:1315`), `STOP` (`:1342`, `:1408`), `CONTEXT` (`:1408`) and `INFORMATIONAL` (`:1462`, `:1491`).

Traversal is two hops: package → repositories that declare it, then repository → one ring of
adjacent entities via `IMPLEMENTED_BY`, `CONTAINS`, `DEPLOYED_AS`, `USES` (`:1360-1375`). Plan §12
specifies `Repository <-BUILT_FROM- Application`, `Application <-DEPENDS_ON- Application`,
`Application -EXPOSES-> API`, `Application <-ENABLED_BY- BusinessCapability` as transitive impact.
Applications arrive as *context*, one hop; application-to-application dependency, exposed APIs and
business capabilities are not reached at all.

### 1.3 Business impact is missing from the simulator

Plan §22 and the §44 demo output both make business capability the headline — "Payment
Authorization, a Tier-0 business capability, is affected" rather than a repository count. The
simulator never joins to `BusinessCapability`, criticality or obligation; the string `capability`
does not appear in the traversal. Capability data exists (`/capabilities/footprints`,
`/capabilities/taxonomy`, the heat grid) but is not connected to a simulation run.

This is the single largest distance between the shipped slice and the plan's own demo script.

### 1.4 The hypothetical overlay is nominal

§13 asks for `diff(G, G')` reporting newly invalid dependencies, resolved and introduced policy
violations, compatibility failures, lifecycle changes, vulnerabilities removed or introduced, new
contradictions, and newly satisfied standards.

What exists is a literal marker on context findings — `{"changed_subject_id": …,
"target_version": …, "authoritative_facts_unchanged": true}` (`apps/api/app/phase2_changes.py:1419`) —
plus a version-spread finding (`:1487`). No condition is evaluated in `G'`, so nothing "resolved"
is ever reported, which is half of M2's exit gate. In particular the §14 finding types
(dependency constraint conflicts, missing tests, unsupported runtime combinations) are not produced,
and OSV data is ingested (`services/data-platform/stackgraph_data/osv.py`) but never consulted
during simulation.

### 1.5 The AI interpretation layer does not exist

`simulation_interpretation` supports `AVAILABLE` / `UNAVAILABLE` / `QUARANTINED` with `risk`,
`explanation`, `rollout`, `verification` and `cited_finding_ids`
(`infrastructure/database/migrations/047_phase2_change_compiler.sql:145-160`). The only write in
the codebase inserts `UNAVAILABLE` unconditionally (`apps/api/app/phase2_changes.py:1546`). There is
no provider call, no citation enforcement, and no quarantine path.

The UI is ready for it — `SimulationResult.tsx:194` already renders the uncited-claim warning — so
this is a missing backend step, not a missing surface. The `AI_INTERPRETATION` flag is seeded but
never read anywhere in the codebase, which is the tell.

Note the schema also omits `remediation`, which M2 lists alongside risk/explanation/rollout/verification.

### 1.6 ChangeSets are single-mutation in practice

The schema supports ordered, atomic, multi-mutation ChangeSets (`ordinal`, `atomic`,
`UNIQUE(change_set_id, ordinal)`). Compilation persists exactly one mutation and reads it back with
`ORDER BY ordinal LIMIT 1` (`apps/api/app/phase2_changes.py:821`); the simulator processes
`change_set.mutations[0]` and ignores the rest (`:1260`). The seeded `max_mutations: 20` validation
rule is unreachable.

So C2's ordering, atomicity and conflict-detection requirements are schema-only. This also blocks
the §7 PR-to-ChangeSet flow, which is inherently multi-mutation.

### 1.7 `ActionCapability` is metadata, not a driver

`action_capability` is read in exactly one place, to list action types
(`apps/api/app/phase2_changes.py:144`). `target_schema`, `validation_rules`, `scope_rules`,
`semantic_provider` and `provider_version` are never read. Validation is hardcoded
(`predicate != "UPGRADE"` at `:644`), as is the package-specific resolution path.

Because only one row is seeded, `GET /action-types` returns only `UPGRADE`. Plan §4 wants the whole
bounded grammar visible with the unavailable verbs shown as disabled — the descriptions for all six
predicates are already written at `:151-158` but are unreachable. Users cannot see what the product
will eventually do.

---

## 2. Delivered as a schema and a read API, with no producer

Each of these has migrations, models, endpoints, fixtures and UI. None has a write path outside the
API itself, so in a real tenant they return empty with a limitation code.

| Capability | Tables | Read surface | Writer |
| --- | --- | --- | --- |
| Component profiles (S1) | `estate_component_profile`, `estate_profile_evidence` | `GET /components`, `/components/{id}` | none |
| Deployment profiles (S2) | `estate_deployment_profile` | `GET /repositories/{id}/deployment-profiles` | none |
| Container composition (S3) | `estate_container_profile`, `_layer`, `_package` | `GET /repositories/{id}/container-compositions` | none |
| Data lineage (§23) | `estate_lineage_edge` | `GET /estate/lineage` | none |

`grep -rl estate_component_profile` returns two files: the migration and `apps/api/app/estate_fidelity.py`.

This one is worth separating from the others: the scanner *does* produce the underlying evidence.
`repository_scanner.py` at 1.11.0 emits Component entities (`:2401`), multi-label classifications
(`:2257`), deployment facts and container identity, and `_repository_fingerprint_facts` (`:508`)
consumes them. What is missing is the projection from those facts into the typed profile tables —
so `GET /components` lists Component entities but every profile reports `COMPONENT_EVIDENCE_PARTIAL`
(`apps/api/app/estate_fidelity.py:223`).

Correcting an earlier reading of this section: the deployment and container endpoints do **not**
return nothing. Both fall back to the repository's related entities
(`apps/api/app/estate_fidelity.py:480`, `:569`) and report `PARTIAL` or `NOT_COLLECTED` with a
per-image resolution limitation. The gap is narrower than first stated and entirely about the
typed profile: provider, workload kind, environment, confidence, and method version are absent,
so the surfaces degrade honestly but carry no S2 or S3 detail.

`estate_lineage_edge` is different in kind: nothing anywhere produces lineage, and the endpoint
returns `LINEAGE_NOT_COLLECTED` by design (`apps/api/app/estate_governance.py:344`). That is honest,
but E1 item 4 is not started.

### 2.1 The AI supply chain queries a vocabulary that cannot exist

`GET /estate/ai-supply-chain` filters on entity types `Agent`, `AgentHarness`, `AIModel`, `Prompt`,
`InstructionSet`, `ContextSource`, `Tool`, `Dataset` and predicates `ORCHESTRATES`, `INVOKES`,
`GROUNDED_BY`, `ACCESSES`, `FEEDS`, `TRIGGERS`, `PRODUCES`
(`apps/api/app/estate_governance.py:30-33`).

None of those sixteen names appears in `contracts/v1/ontology.registry.json`. Nothing in the scanner
or any connector emits them. The endpoint can only ever return empty, and the fixture
`phase2-ai-supply-chain.json` is the sole place the shape is exercised. §31 is not started; the
ontology extension it needs has not been made.

---

## 3. Change memory (H1 / §29–§30)

`observed_mutation` is immutable, evidence-required, correlation-keyed and links back to a
predicting run via `predicted_simulation_run_id` — the schema is right
(`infrastructure/database/migrations/053_phase2_change_memory.sql`). Simulation already cites
qualified history with an explicit sample floor of three and published bias limitations
(`apps/api/app/phase2_changes.py:1449-1486`), which is the honest version of §30.

The gaps are upstream and downstream of that:

**No automatic ingestion.** `source_kind` allows `PULL_REQUEST`, `COMMIT`, `DEPLOYMENT`, `TICKET`,
`INCIDENT`, `POSTMORTEM`, `MANUAL`, but the only writer is `POST /observed-mutations`. H1 requires
correlating PRs, commits, dependency changes, deployments, tickets, incidents, rollbacks and
postmortems. Today an operator types them in one at a time, so change memory stays empty in
practice and the three-outcome floor is never crossed.

**Five activity event types have no producer.** The collector emits `RELEASE` (`:196`),
`DEPLOYMENT` (`:222`), `COMMIT` (`:267`) and both PR types (`:313`, `:321`) in
`services/enterprise-discovery/stackgraph_discovery/github_activity.py`. The aggregate query counts
`DEPENDENCY_CHANGE`, `ARCHITECTURE_CHANGE`, `INCIDENT`, `INTERVENTION` and `ROLLBACK` (`:455-459`),
but nothing writes them, so those columns are structurally zero. Dependency-change events are the
ones most directly needed to auto-derive `ObservedMutation` for a package upgrade.

**No predictors and no real calibration.** §30's "strongest failure predictors" with multipliers is
absent. What is called calibration is a coverage ratio — how many recorded outcomes carry a
`predicted_simulation_run_id` (`apps/web/features/intelligence/ChangeHistory.tsx:83`, `:100`) —
not a comparison of predicted findings against observed impact. §9.1's published miss rate is
therefore not yet computable.

---

## 4. Entry points and the recommendation loop

### 4.1 Three of seven entry points

§7 lists natural language, autocomplete, recommendation, GitHub PR, change ticket, architecture
change, agent proposal and API. Implemented: autocomplete/command bar, natural language (a bounded
regex, `_INTENT` at `apps/api/app/phase2_changes.py:56`, applied at `:623` — correctly refusing anything outside
`Upgrade <package> to <version> [in <scope>]`), modernization recommendation
(`compile_modernization_recommendation:871`), and the API.

Not implemented: PR/change-set compilation, change tickets, architecture changes, agent proposals.
There is no `pull_request` reference anywhere in the compiler. §7's argument — that requiring users
to describe changes StackGraph can already observe is the wrong shape — is the strongest case for
closing this, and it depends on 1.6.

### 4.2 Suggested changes has one source

§8 lists recommendations, lifecycle events, deprecated APIs, version fragmentation, unsupported
runtimes, security findings, architecture policy violations and pending changes.
`SuggestedChanges.tsx:45` draws solely from `optimizeModernizationScenario`. The other seven sources
exist as data (deterministic insights, posture insights, OSV, architecture conformance) but do not
reach the fold.

### 4.3 `Simulate` is not on every actionable recommendation

R1 requires it on home suggested changes, modernization, insight cards, application findings and the
review queue. Present on modernization (`app/modernization/page.tsx:151`), reviews
(`app/reviews/page.tsx:125`) and suggested changes. Absent from `DeterministicInsightsPanel` and
from application findings.

Compilation itself is also modernization-only: `compile_modernization_recommendation` reads
`modernization_recommendation` and rejects anything that is not `UPGRADE` on a single canonical
`Package` subject (`:902-915`). Deterministic insights have no compile path at all.

---

## 5. Target intelligence (C1 / §6, §21)

`valid_targets` returns versions that already exist as entities in the tenant
(`apps/api/app/phase2_changes.py:517-533`), with `support="UNKNOWN"` hardcoded (`:533`).

- A version nobody in the estate runs cannot be a target. §6's "14.x — candidate upgrade" is
  unreachable unless some repository already uses it.
- `Latest — resolve at execution time` is not offered, and §6's target labels ("consolidate estate",
  "candidate upgrade") are not produced.
- Lifecycle, support status, compatibility metadata, organizational standards and migration paths —
  all named in §6 and §21 — are absent. `support_status` is read elsewhere in the product
  (`read_models.py:5319`) but not by the target provider.
- Semantic providers are not pluggable by ecosystem. `semantic_provider` is a string on a row that
  is never read; the npm and PyPI clients fetch one requested version rather than enumerating a
  packument (`npm_registry.py:259`).

---

## 6. Evaluation and gates (B0)

ADRs 0001–0005 cover contract evolution, Mutation IR, simulation persistence and overlay, policy
versioning, and history retention — complete against B0's list.

The corpus is not:

- `tests/fixtures/golden-package/` and `tests/fixtures/golden-repository/` contain only `.gitkeep`.
- `tests/integration/` contains only `.gitkeep`.
- No scanner benchmark target exists. `make` has `phase2-api-benchmark`, `backend-graph-benchmark`
  and `graph-embeddings-benchmark`; there is nothing for scanner p50/p95/p99, peak RSS, or the
  ≥60 repos/hour/worker throughput objective in §9.2.
- CI (`.github/workflows/api-lane.yml`) runs contract drift, typecheck, lint, bundle budget, unit,
  integration under RLS, and Playwright with axe. It does not run a precision/recall gate or any
  performance gate.

So the §9.1 correctness objectives — canonical entity precision >99%, no regression beyond 0.25
points — are stated but not measurable today, and I1's exit gate cannot be evidenced. This is the
gap with the widest blast radius, because every other quality claim in the plan is defined relative
to that corpus.

Two seeded feature flags are also dead: `SCANNER_PROFILES` and `AI_INTERPRETATION` appear only in
migration 047 and are read by no code. `CHANGE_COMPILER`, `CHANGE_SIMULATION` and `CHANGE_EXECUTION`
are enforced properly (`routes.py:616`, `:752`; `agent_control.py:293`).

---

## 7. Assumptions and contradictions (§32, §33)

The ledger, claims, evidence, dependents and resolution workflow all exist, and contradiction gating
is genuinely wired into compilation — an open contradiction on the subject or scope blocks the
mutation (`apps/api/app/phase2_changes.py:718`). That is the part that matters most and it is done.

What is missing is the front half of both sections. §32 asks for assumptions to be *extracted* from
code, architecture, documentation, configuration, data and agent instructions; §33 asks for
disagreement to be *detected* across sources. Both are manual: assumptions and their contradicting
claims arrive through `POST /assumptions` and `POST /assumptions/{id}/claims`
(`apps/api/app/estate_governance.py:46`, `:102`). There is no extractor and no detection engine, so
the §33 examples (code says Node 18, Docker says Node 20, docs say Node 16) will not surface on
their own. S2's requirement to "create contradiction facts when repository, runtime, documentation
and policy sources disagree" is the same gap seen from the scanner side.

---

## 8. What is fully delivered

Recorded so the gaps above are read in proportion.

- **Canonical identity and resolution for Package** — explicit `RESOLVED` / `INFERRED` /
  `UNRESOLVED`, ambiguity surfaced, `subject_resolution='RESOLVED'` enforced in the schema, no
  silent compilation of inferred subjects.
- **Mutation IR immutability** — content-hashed input fingerprints, uniqueness on
  `(tenant_id, input_fingerprint)`, idempotency keys, immutability triggers, lifecycle states.
- **Durable asynchronous simulation** — queue leases, retries, cancellation, estate watermark and
  policy pinning, deterministic result hashes, recovery-drill coverage.
- **Deterministic-first behaviour under AI absence** — findings are complete and unchanged with
  interpretation unavailable, which is M2's most important property even though the interpretation
  side is unbuilt.
- **U0 safety vocabulary** — `GateNotice`, `ResolutionLabel`, `ConfidenceChip`, `AttenuationBar`,
  `StratumBar`, `CitationChip`, `RunProvenance`, with axe and keyboard coverage across nine E2E specs.
- **M2 UI surfaces** — classification ring with STOP boundaries, attenuation funnel, Now/Simulated/
  Difference heat grid, findings/interpretation partition, printable Change Brief.
- **Command surface** — `EMPTY` / `RESOLVING` / `TOKENISED` / `COMPILED`, version-spread comb,
  named gate reasons.
- **T1 actor taxonomy and windowed aggregates** — full seven-value taxonomy, 7/30/90-day
  recomputable windows, retention classes, coverage statuses.
- **S4 fingerprints and archetypes** — versioned, threshold-gated, evidence-linked, with history.
- **A1 control plane** — capability envelope compilation, `ALLOW`/`CONSTRAIN`/`ESCALATE`/`DENY`,
  approvals, kill switch, flight recording with finalization, control drill. §36's immune system is
  deliberately deferred and should stay deferred.
- **Tenant integrity** — RLS with forced policies, audit events, evidence-reference normalization.

---

## 9. Suggested order

Ordered by how much each unblocks, not by size.

1. **Populate the golden corpus and add the scanner benchmark.** Every correctness claim in §9.1 is
   defined against a corpus that does not exist. Until it does, no other item can be shown to have
   improved anything.
2. **Make `ImpactPolicy.configuration` drive traversal, and fix `SUPPORTS` / `BELONGS_TO`.** This is
   the prerequisite for transitive impact, for a second predicate, and for the determinism claim
   being true rather than incidental.
3. **Extend traversal to transitive application, API and business capability, with criticality.**
   This is what makes the output match §44's demo and §22's differentiator.
4. **Project scanner facts into the component, deployment and container profile tables.** The
   evidence is already produced; only the projection is missing, and S2/S3 blast radius depends on it.
5. **Build the AI interpretation step behind `AI_INTERPRETATION`,** with citation enforcement and
   quarantine. The schema and the UI are both waiting for it.
6. **Emit `DEPENDENCY_CHANGE` events and auto-derive `ObservedMutation` from PRs and deployments.**
   Change memory is inert until outcomes arrive without manual entry.
7. **Multi-mutation ChangeSets, then PR-to-ChangeSet compilation.** In that order; the second needs
   the first.
8. **Widen the target provider** to registry-enumerated versions with lifecycle and support status.
9. **Broaden suggested changes and `Simulate` placement** to deterministic insights and application
   findings.
10. **Extend the ontology for the AI supply chain, or remove the endpoint** until there is a
    producer. A read surface that can only return empty is worse than an absent one.

---

## 10. Resolution

What changed on this branch, against the remediation order in §9. Each item names the behaviour
that is now different, not the files that moved.

### Closed

**1. Golden corpus and scanner benchmark.** Eleven labelled cases covering the repository shapes
B0 enumerates, an evaluation harness scoring precision and recall over the labelled set only, a
pytest gate holding both at 1.0, a report that fails on regression past the 0.25-point margin,
and a §9.2 benchmark for scan latency, peak RSS, and throughput. Both run in CI. Building the
corpus immediately found two real defects: analytics files were never admitted, so the DBT,
NOTEBOOKS, DATA_ANALYTICS and SQL_SCHEMA_MIGRATION rules were unreachable dead code; and
manifests inside vendored trees became Components of the repository with their transitive
dependencies recorded as its own DECLARED facts.

**2. The impact policy drives traversal.** Edge rules, directions, per-rule and global depth
bounds, the confidence floor, budgets, and stop conditions are now read from the persisted
policy. A policy that cannot be interpreted is refused rather than defaulted. A validation
trigger rejects any policy naming a non-projectable predicate, which is what `SUPPORTS` and
`BELONGS_TO` were.

**3. Transitive and business impact.** The walk reaches applications, services, and exposed APIs
transitively, then joins reached applications to the curated capability map with criticality.
Curated provenance is recorded separately from observed evidence, and every capability finding
says which it is.

**4. Typed estate profiles are projected.** Component and deployment records now reach
`estate_component_profile` and `estate_deployment_profile`, superseding older revisions rather
than accumulating. Container composition stays deferred: it is keyed by immutable digest, and
resolving one needs registry access the scanner deliberately does not perform.

**5. The interpretation layer exists.** Behind `AI_INTERPRETATION`, with grounding enforced in
code rather than trusted to the prompt. A claim citing a finding the run did not produce, or
citing nothing, is quarantined where it cannot touch risk or the gate and stays readable.
Provider outage, timeout, and unstructured output each leave deterministic findings unchanged.

**6. Change memory fills itself.** The collector detects manifest and lockfile moves on merged
pull requests; a derivation reads superseded dependency facts as observed mutations and
correlates them to the merge that carried them. Only increases become upgrades, success stays
NULL, and an unattributable change carries lower confidence. Writing the direction test found a
real ordering bug: a single lexical version key ranks `2.0.0-rc1` above `2.0.0`, so every
release-cutting change would have been dropped.

**7. Multi-mutation ChangeSets and the alternative entry points.** One draft step gates each
mutation and one set step runs every member through it before persisting anything. Conflict
detection covers what a per-mutation gate cannot see. `POST /change-sets/compile` carries an
entry point, so pull requests, tickets, architecture changes, and agent proposals reach the
engine through the same Mutation IR — none of them accepting prose.

**8. Target intelligence.** Targets carry estate spread, a labelled reason for being offered,
and support status read rather than assumed. Coverage states what the list was drawn from, so a
short list does not read as a short registry.

**9. Estate findings reach a simulation.** Deterministic insights compile, deriving their target
the way the command bar does. The Simulate action gained a source discriminator rather than a
sibling component, so one placement covers every surface R1 names. The fold fills from insights
when the optimiser has fewer than three proposals.

**10. Ontology contract synced.** The registry now carries the AI vocabulary the database has
registered since migration 055, and a contract test asserts that every type and predicate the
read model queries is declared. The endpoint's empty case now distinguishes uncollected from
absent.

**Also closed.** `/action-types` publishes the whole bounded grammar with per-subject lifecycle —
which exposed a defect, since the predicate-level flag was ANDed across subject types and would
have disabled `UPGRADE Package` the moment a planned subject was seeded. `SCANNER_PROFILES` gates
the typed profile projection instead of being dead. And §33's contradiction engine now detects
runtime disagreement across version pins, manifest engines, container base images, and
documentation, promoting it into the ledger the compiler already gates on.

### Closed since the audit

The four items this audit left open have been built. They are recorded here because the reasons
for deferring them were stated, and a reader who found those reasons persuasive is owed the
reason they no longer hold.

**Container composition profiles.** A registry client resolves an image reference to an immutable
digest, verifies the digest it computes against the one the registry returned, and writes the
digest-keyed profile the read surface was already shaped for. Tag history is kept rather than
overwritten, so a tag that has moved reads as a moved tag instead of silently replacing what
production ran. It runs after a scan, never during one, behind `REGISTRY_ENRICHMENT`, which
defaults off: reaching an external registry is an operator's decision. Layers are recorded;
`coverage.os_packages` still says `NOT_COLLECTED`, because nothing has read inside the layers.

**Registry-enumerated target versions.** npm and PyPI catalogues are enumerated into
`package_version_catalog`, with prereleases, yanks, deprecations, and support status separated
rather than collapsed. `package_catalog_collection` records what each enumeration achieved, so a
package the registry answered partially is distinguishable from a package with two releases.
`valid_targets` joins the catalogue and keeps reporting its coverage.

**AI supply-chain producers.** The scanner now emits the vocabulary migration 055 registered:
`ORCHESTRATES` for a declared harness, `ACCESSES` for SDKs and MCP servers, `GROUNDED_BY` for
vector stores, and `INVOKES` for models — `DECLARED` from configuration, `INFERRED` from source,
never the same confidence for both. The harness is resolved before anything is attached to it, so
the same repository does not produce two different graphs depending on how a package name sorted.
The endpoint still distinguishes an estate with no AI supply chain from one that was never
scanned for it.

**§36's immune system.** Eight generators derive adversarial scenarios from rows that exist —
stale facts, open contradictions, partial catalogue collections, quarantined interpretations,
datastores with consumers, harnesses grounded by retrieved content, subjects under competing
ChangeSets, and declared topologies with nothing observed beside them. A class that derived
nothing says why, so `NOT_DERIVABLE` never reads as immunity. Evaluation is `OFFLINE` by a column
that admits one value; a failure cannot be recorded without a diagnosis, `INCONCLUSIVE` is a
first-class outcome rather than a rounded pass, unanswered scenarios are named rather than
counted, and a finished evaluation is immutable.

**Container package inventory.** Closed. The enrichment step opens layer blobs and reads dpkg,
apk, Python `dist-info`, and `node_modules` package databases into `estate_container_package`,
honouring whiteouts so a package a later layer deleted is not reported as installed. It sits
behind its own `CONTAINER_PACKAGE_INVENTORY` flag rather than riding on `REGISTRY_ENRICHMENT`,
because agreeing to read a manifest is not agreeing to pull hundreds of megabytes of layer.

Four bounds keep it safe, and every one that trips is reported: an oversized layer is skipped
before it is requested, decompression is capped independently of the download because a gzip
bomb's whole point is that the two numbers are unrelated, only known package-database paths are
extracted, and the layer count is bounded. RPM databases are detected and deliberately not
parsed — Berkeley DB, ndb, or SQLite depending on the distribution, and a confident wrong answer
about what is installed is worse than a stated gap.

`coverage.os_packages` now distinguishes four states, and the read surface names each: an image
nobody opened, one read in part, one with no package database at all (distroless and scratch have
none), and one fully read. Before this an empty package list meant all four.

**Registries beyond npm and PyPI.** Closed. Building it exposed a defect in the enumerator that
shipped before it: `package_registry_identity` was written for npm alone, so the PyPI enumerator
could never see a package either, and every non-npm dependency reported no upgrade targets — a
sentence that reads as "no newer release exists" rather than "nothing asked". Identity is now
recorded for every ecosystem, against the public registry the build actually resolves against.

The scanner reads `pom.xml`, Gradle build files and version catalogues, `.csproj` and friends,
`Cargo.toml`, and `go.mod`; the enumerator speaks Maven Central's metadata XML, the NuGet flat
container, the crates.io API, and the Go module proxy. Each adapter states what its registry does
not publish rather than defaulting it: Maven has no yank or deprecation signal at all, the NuGet
flat container carries no release dates, and Go retractions live in a module's own `go.mod` where
the proxy's list cannot see them. Three places the parsers refuse to guess: an unresolvable Maven
property leaves the dependency versionless, a Cargo path or git dependency is not a crates.io
package, and a Go module a `replace` directive redirects keeps no resolved version.

**Champion/challenger promotion.** Closed. Migration 059 left it unrepresentable and said why:
A1 requires the loop to stay disabled "until offline evaluation, rollback, and governance are
proven". That is a condition, not a prohibition, and the honest way to open it was to make the
three proofs computable and require them — not to add a table and a flag and declare the
condition met.

Each precondition is now evidence the schema already holds. *Offline evaluation*: a completed
evaluation of the challenger with no failure, no inconclusive outcome and no unanswered scenario,
covering every class this estate has derived and every scenario the incumbent was tested against
— a challenger evaluated against less than the champion can score better while being tested less,
so that is refused by name. *Rollback*: a passed `ROLLBACK` drill recorded no earlier than the
evaluation it vouches for, plus a rollback path that restores the previous version, needs no
second person, and is always available. *Governance*: two people, enforced by a database CHECK
rather than only by the API, because a rule that lives in application code is one the next writer
can forget.

A proposal that fails the gate is written down with every reason, not just the first. A refusal
nobody can read is indistinguishable from a promotion nobody attempted, and a proposer who
discovers the blockers one round at a time learns the gate the slow way.

### Still open

These are the gaps the work above left behind. Each is reported by the surface that has it
rather than left to be inferred from a short list or an empty one.

**RPM package databases.** Detected inside an image and deliberately not parsed. They are
Berkeley DB, ndb, or SQLite depending on the distribution's age, and a confident wrong answer
about what is installed is worse than a stated gap. `coverage.os_packages` reports `PARTIAL` and
the limitation names the reason.

**Registries with no adapter.** Conan, Hex, RubyGems, Composer and the rest are recordable as
`OTHER` and not enumerable. `package_catalog_collection` has no row for them, so target coverage
says the catalogue was never collected rather than implying the registry is small.

**Signals the registries themselves do not publish.** Maven has no yank or deprecation at all;
the NuGet flat container carries no release dates or listing state; Go retractions live in a
module's own `go.mod`, out of the proxy list's reach. Each adapter reports its own blind spots as
limitations instead of defaulting the missing value.

**Gradle coordinates built at runtime.** Dependencies are read from string literals and version
catalogue aliases. A coordinate assembled from variables at configuration time is missed, and a
Maven property defined in a parent pom the scanner never fetched leaves its dependency
versionless rather than guessed.
