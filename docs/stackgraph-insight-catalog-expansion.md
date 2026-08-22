# StackGraph insight catalog expansion

Status: proposal · Date: 2026-08-22 · Author: estate-intelligence review

## 1. Scope and method

StackGraph today ships two insight surfaces:

- **Deterministic insight rules** — nine rules in `RULE_CATALOG`
  ([deterministic_insights.py:24](../apps/api/app/deterministic_insights.py:24)), evaluated per
  tenant, governed by `deterministic_insight_rule_policy`, rendered by
  [DeterministicInsightsPanel.tsx](../apps/web/components/insights/DeterministicInsightsPanel.tsx).
- **Enterprise insight reports** — ten canned executive questions in
  `_ENTERPRISE_INSIGHT_REPORTS` ([read_models.py:148](../apps/api/app/read_models.py:148)), answered
  through the Ask pipeline with citations.

This document inventories what those surfaces already answer, identifies the parts of the schema
that carry decision-grade signal but feed no insight, and proposes a catalog of additional
insights. Every proposal below states the exact columns it reads, why it is not a restatement of an
existing rule or report, and what it is blocked on. Nothing here assumes data the platform does not
already have unless it is explicitly labelled as such.

The organising claim: the current catalog is a **point-in-time, positive-space, dependency-centric**
view. It answers "what bad things exist in the packages we resolved, right now." Three whole
dimensions of the schema are unread — time, provenance, and negative space — and they contain the
questions enterprises actually escalate to a steering committee.

---

## 2. Baseline — what the estate already answers

### 2.1 Deterministic rules

| Rule key | Reads | Readiness today |
| --- | --- | --- |
| `dependency.vulnerable-direct` | `AFFECTED_BY` on resolved direct versions | ACTIVE |
| `dependency.vulnerable-transitive` | `AFFECTED_BY` through the resolved graph | ACTIVE |
| `dependency.deprecated` | registry deprecation metadata | ACTIVE |
| `dependency.unused-direct` | `dependency_usage_summary.referenced` | ACTIVE |
| `dependency.version-fragmentation` | multiple resolved versions per package | ACTIVE |
| `capability.technology-diversity` | curated technologies per code capability | ACTIVE |
| `deployment.external-exposure` | IaC production/public entry points | ACTIVE |
| `business.critical-impact` | Business Map criticality ≥ threshold | ACTIVE |
| `architecture.drift` | golden-stack baselines | NEEDS_DATA |

### 2.2 Enterprise reports

Systemic dependency risk · reachable Tier-1 vulnerabilities · package business blast radius ·
duplicated capabilities · unnecessary technology diversity · modernization blockers · internal
platform replacements · enterprise library standards · retirement & consolidation · standardization
payoff.

### 2.3 Supporting surfaces

`capability_footprint` (technology entropy and reuse signal per capability), the modernization
scenario planner (`ModernizationScenarioResult`, knapsack against an effort budget), and
`Phase3IntelligenceMetrics` (pipeline precision, acceptance rate, effort MAE, queue latency, model
cost).

### 2.4 The shape of the gap

1. **No time dimension.** `fact_assertion` is bitemporal (`system_from`/`system_to`,
   `effective_from`/`effective_to`, `observed_at`) and `entity` carries
   `first_seen_at`/`last_seen_at`. Not one insight reads them. Every finding is a snapshot; nothing
   answers "what changed," "how fast," or "did the decision we made last quarter land."
2. **No provenance dimension.** `dependency_resolution` records registry origin, integrity hashes,
   resolution source, and lockfile behaviour for every npm dependency. Nothing reads it. The
   platform can say a package is vulnerable but not whether the artifact the build pulled is the
   artifact the registry published.
3. **No negative space.** Every rule enumerates things that exist. Nothing enumerates what is
   *missing* — unmapped applications, unmodelled capabilities, ecosystems the scanners cannot parse,
   repositories that failed to refresh. An empty result currently reads as "healthy" when it often
   means "unobserved."

---

## 3. Unexploited data assets

| Schema object | Carries | Read by today | Unlocks |
| --- | --- | --- | --- |
| `dependency_resolution` | `resolution_source`, `custom_registry`, `integrity`, `resolved_artifact_uri`, `visibility`, `npm_scope`, `lockfile_behavior` | nothing | Theme A |
| `package_registry`, `package_registry_scope`, `package_registry_identity` | registry inventory, scope routing, public/private visibility | resolution only | Theme A |
| deps.dev `HAS_PROPERTY` fact (`deps_dev_version_metadata`) | `licenses`, `published_at`, `project_status`, `registries` | `is_deprecated` only | Theme B |
| npm registry bundle | `time` (release history), `repository`, `dist-tags` | version resolution | Theme B |
| pypi registry bundle | `license`, `author`, `yanked`, `yanked_reason` | version resolution | Theme B |
| `entity.first_seen_at` / `last_seen_at` | when each technology entered and was last observed | nothing | Theme C |
| `fact_assertion.system_to` | when an assertion was retracted | currency filter only | Theme C |
| `code_implementation_summary` | `structural_fingerprint`, `covering_tests`, `dynamic_signals`, `vendored`, `touchpoints` | per-repo modernization candidates | Theme D |
| `package_api_surface` + `dependency_usage_summary.referenced_symbols` | exported symbol count vs symbols actually referenced | binary used/unused | Theme E |
| `Deployment`/`Environment`/`ContainerImage` entities, `RUNS_ON`, `LOCATED_IN` | deployment topology from IaC | exposure flag only | Theme F |
| `business_map_capability.owner`/`.criticality`/`.kpis`, `business_map_placement.maturity`, `business_map_shared_group` | governed business intent | criticality threshold only | Theme G |
| `assertion_class`, `confidence`, `evidence`, `capability_inference.model_invocation_id` | how each claim was derived | per-fact display | Theme H |
| `freshness_state`, `dead_letter`, `connector_quota`, `ecosystem_admission`, `identity_assertion` | model coverage and integrity | admin screens | Theme H |
| `repository_code_policy_evaluation` | `MISALIGNED`/`UNASSESSED`, `violation_count`, `unclassified_count` | admin screens | Theme H |
| `modernization_recommendation.review_state` + `modernization_validation_outcome` | decisions taken vs decisions landed | pipeline metrics | Theme C |

Readiness vocabulary used below:

- **ACTIVE** — every column is populated today; this is a query and a contract, nothing else.
- **NEEDS_EXTRACTOR** — the schema and the upstream connector both exist; the extractor does not
  emit the fact yet.
- **NEEDS_DATA** — requires a source the platform does not currently pull.

---

## 4. Proposed insight catalog

### Theme A — Supply-chain integrity and provenance

The estate can name its vulnerable packages but cannot yet vouch for the artifacts it installs.
This theme is entirely additive: no existing rule reads `dependency_resolution`.

Caveat applying to all of Theme A: npm resolution is fully populated
([npm_resolution.py](../services/enterprise-discovery/stackgraph_discovery/npm_resolution.py));
PyPI resolution is not. Findings must be scoped to npm and the coverage stated, or the theme reads
as a clean bill of health for Python repositories that were never checked.

**A1 · `supplychain.dependency-confusion` — Dependency confusion exposure** · CRITICAL · ACTIVE

- *Question:* which internal package names could a public registry answer for?
- *Signal:* a `@scope` in `dependency_resolution.npm_scope` resolved from a private or custom
  registry, where the same `package_name` also exists in `package_registry_identity` with
  `visibility='PUBLIC'`; or a private-scope dependency with `resolution_source='NPM_DEFAULT'`,
  meaning no `.npmrc` scope rule routed it.
- *Not a duplicate of:* nothing. No existing rule or report considers registry routing.
- *Drives:* an `.npmrc` scope pin, or a defensive public placeholder publication.

**A2 · `supplychain.unverifiable-artifact` — Unverifiable artifact provenance** · HIGH · ACTIVE

- *Signal:* `integrity IS NULL`, or `lockfile_behavior='EXPLICIT_TARBALL'`, or
  `resolved_artifact_uri` pointing outside the resolving registry's origin.
- *Not a duplicate of:* the vulnerability rules, which assume the resolved version is what was
  installed. This insight tests that assumption.
- *Drives:* lockfile hygiene enforcement; it also bounds how much the vulnerability findings can be
  trusted for the affected repositories.

**A3 · `supplychain.registry-sprawl` — Unapproved and shadow registries** · MEDIUM · ACTIVE

- *Signal:* distinct `package_registry` rows with `custom_registry=true` reached across the estate,
  grouped by `config_path`; registries appearing in one or two repositories only.
- *Not a duplicate of:* `capability.technology-diversity`, which is about too many libraries doing
  one job. This is about too many places the build trusts.
- *Drives:* registry consolidation and proxy enforcement.

**A4 · `supplychain.non-deterministic-build` — Floating dependency specs** · MEDIUM · ACTIVE

- *Signal:* `resolved_version IS NULL` with a range in `requested_spec`, or
  `lockfile_behavior='UNKNOWN'` — a build whose output is not reproducible from its inputs.
- *Not a duplicate of:* `dependency.version-fragmentation`, which is about the estate holding many
  pinned versions of one package. This is about a single repository having no pin at all.
- *Drives:* lockfile adoption, and it explains version fragmentation where the two co-occur.

### Theme B — OSS sustainability and legal exposure

The current model treats an OSS package as healthy if it has no CVE and is not flagged deprecated.
Enterprises lose more time to unmaintained and mislicensed dependencies than to exploited ones.

**B1 · `oss.license-obligation` — License obligation and compatibility exposure** · HIGH · ACTIVE

- *Signal:* the `licenses` array in the deps.dev `deps_dev_version_metadata` property fact
  ([depsdev.py:432](../services/data-platform/stackgraph_data/depsdev.py:432)), joined to
  applications reached by `deployment.external-exposure`, with `modernization_policy.allowed_licenses`
  as the tenant's allow-list. Ranked by copyleft class and by whether the consuming application is
  externally distributed.
- *Not a duplicate of:* `modernization_policy.allowed_licenses`, which gates *proposed replacement
  options*. Nothing today evaluates the licences already in the estate.
- *Drives:* legal review, replacement, or a licence exception record. This is usually the fastest
  path to an executive-visible win because it produces a finite, closable list.

**B2 · `oss.release-decay` — Abandonware and release-cadence decay** · MEDIUM · ACTIVE

- *Signal:* deps.dev `published_at` on the resolved version, plus the npm registry `time` map for
  the package's newest release. Two distinct findings: *the estate is far behind* (many releases
  since the pinned one) versus *the package is dead* (no release in N months). Weight by
  `dependency_usage_summary.static_reachability`.
- *Not a duplicate of:* `dependency.deprecated`, which requires the maintainer to have explicitly
  flagged the package. Most abandonware is never flagged.
- *Drives:* replacement before the abandonment becomes an unpatchable CVE.

**B3 · `oss.yanked-release` — Withdrawn releases in use** · HIGH · ACTIVE (PyPI)

- *Signal:* `yanked` / `yanked_reason` from the PyPI connector
  ([pypi_registry.py:274](../services/data-platform/stackgraph_data/pypi_registry.py:274)).
- *Not a duplicate of:* `dependency.deprecated` — yanking withdraws a specific release, usually for
  a defect the maintainer considers serious enough to unpublish. This is the narrowest, highest
  signal-to-noise finding in the catalog.
- *Note:* small enough that it may be best delivered as a second condition on the deprecation rule
  rather than a rule of its own. Recommend a separate `rule_key` regardless, so tenants can set its
  severity independently.

**B4 · `oss.maintainer-concentration` — Bus factor** · MEDIUM · NEEDS_EXTRACTOR

- *Signal:* `MAINTAINED_BY` edges to `OSS/Maintainer` entities; single-maintainer packages on the
  critical path. The ontology declares both the entity type and the predicate; no extractor emits
  them. npm returns `maintainers` and PyPI returns `author` in bundles already fetched.
- *Effort:* small — extend the two registry connectors to emit `MAINTAINED_BY`.

**B5 · `oss.project-health` — Composite OSS viability** · MEDIUM · NEEDS_DATA

- *Signal:* OpenSSF Scorecard. `source_system.kind` already admits `'OPENSSF'`; no connector exists.
- *Note:* the README frames "healthy and strategically viable versus merely free of known CVEs" as
  a core product question. B2 and B4 approximate it from data on hand; Scorecard answers it
  properly. Sequence this after B1–B4 prove the surface.

### Theme C — Estate change dynamics

This is the largest gap and the one most specific to StackGraph's stated thesis. The README asks
"what new technology and architecture patterns are coding agents introducing into the estate?" —
and no insight can currently answer it, because nothing reads the time columns.

**C1 · `estate.technology-introduction` — What entered the estate, and who introduced it** · INFO/MEDIUM · ACTIVE

- *Signal:* `entity.first_seen_at` within a window for `TECHNOLOGY`/`OSS` entities, attributed to
  the introducing repository via the earliest `DEPENDS_ON`/`USES` fact by `observed_at`.
- *Not a duplicate of:* anything. Every current insight is a snapshot.
- *Drives:* the standing "what changed this quarter" review. This is the insight an architecture
  board opens first, and it is also the one that makes the acceleration thesis legible: adoption
  rate is a number, not an anecdote.

**C2 · `estate.unratified-adoption` — Single-repository novelty with no governance record** · MEDIUM · ACTIVE

- *Signal:* a technology first seen inside the window, adopted by exactly one repository, with no
  matching row in `tenant_code_policy.allowed_technology_ids` and no
  `modernization_internal_component`.
- *Not a duplicate of:* `capability.technology-diversity`, which fires when *many* technologies
  serve one function. C2 fires on a single unvetted choice before it proliferates — the cheap moment
  to intervene.
- *Drives:* a governance decision while the blast radius is one repository.

**C3 · `estate.decision-lag` — Decisions taken versus decisions landed** · HIGH · ACTIVE

- *Signal:* `modernization_recommendation` with `review_state='ACCEPTED'`, aged by
  `modernization_recommendation_review.reviewed_at`, with no `modernization_validation_outcome` and
  the underlying condition still asserted in `current_fact`.
- *Not a duplicate of:* `Phase3IntelligenceMetrics`, which measures whether the *pipeline* is
  accurate. C3 measures whether the *organisation* executed. Those diverge, and the divergence is
  the finding.
- *Drives:* portfolio governance. It is also the only proposed insight that grades the customer
  rather than the estate, which makes it the most valuable one in a renewal conversation.

**C4 · `estate.model-churn` — Assertion instability** · INFO · ACTIVE

- *Signal:* rate of `system_to` closures per repository per scan. High churn means the extracted
  model is unstable — a monorepo being partially scanned, a generated lockfile, a flapping
  extractor.
- *Not a duplicate of:* `freshness_state`, which tracks whether data arrived. C4 tracks whether the
  data that arrived is consistent with the last batch.
- *Drives:* extractor tuning, and it qualifies the confidence of every trend built on C1–C3.

### Theme D — Code-level structure

`code_implementation_summary` is richly populated by the scanner
([repository_scanner.py:1224](../services/enterprise-discovery/stackgraph_discovery/repository_scanner.py:1224))
and read only by the per-repository modernization worker. Its estate-wide potential is untouched.

**D1 · `code.cross-repository-clone` — The same code in many repositories** · HIGH · ACTIVE

- *Signal:* identical `structural_fingerprint` across distinct `repository_entity_id`, above the
  existing `MIN_STRUCTURAL_DUPLICATE_LINES` floor, grouped and ranked by repository count and by
  how many distinct business capabilities the clones sit under.
- *Not a duplicate of:* `duplicate_capability_candidate`, which is scoped to a single
  `repository_entity_id` and keyed on *dependencies* serving one capability. D1 finds copy-paste
  *between* teams — the classic "we wrote this six times" finding — and it is the direct evidence
  base for the existing `internal_library_standards` report, which currently has no deterministic
  input.
- *Drives:* extraction into a shared internal library; feeds `modernization_internal_component`.

**D2 · `code.vendored-third-party` — OSS copied into the tree** · HIGH · ACTIVE

- *Signal:* `code_implementation_summary.vendored=true`, aggregated by repository and correlated
  against the dependency graph to show that the vendored copy has no `DEPENDS_ON` edge.
- *Not a duplicate of:* every vulnerability rule, all of which traverse `DEPENDS_ON`. Vendored code
  is invisible to all of them by construction. This is a genuine hole in the security narrative and
  worth surfacing precisely because it explains what the scanner *cannot* see.
- *Drives:* re-externalising the dependency so it becomes patchable.

**D3 · `code.untested-change-surface` — Where the estate cannot be safely changed** · MEDIUM · ACTIVE

- *Signal:* `covering_tests = '{}'` on code units, weighted by `modernization_impact.affected_call_sites`
  and by Business Map criticality of the owning capability.
- *Not a duplicate of:* `modernization_impact.uncovered_call_sites`, which scopes coverage to one
  proposed change. D3 is the standing estate-level measure and is what determines whether *any*
  modernization programme is feasible.
- *Drives:* test investment sequencing ahead of a modernization wave.

**D4 · `code.dynamic-behavior` — Static-analysis blind spots** · INFO · ACTIVE

- *Signal:* `dynamic_signals` (reflection, `eval`, dynamic import) present in code units that also
  reference dependencies flagged by `dependency.unused-direct`.
- *Not a duplicate of:* it is the honest counterweight to the unused-dependency rule. A dependency
  invoked only through reflection reads as unused and is not.
- *Drives:* suppression of false positives, and it should feed
  `DeterministicInsight.missing_inputs` on affected findings rather than standing alone.

### Theme E — Dependency right-sizing

**E1 · `dependency.symbol-utilization` — Over-weight dependencies** · MEDIUM · ACTIVE

- *Signal:* `dependency_usage_summary.referenced_symbols` cardinality against
  `package_api_surface.public_symbol_count` for the same `package_version_entity_id`. Flag ratios
  below a policy threshold where the referenced symbols have a native or internal equivalent.
- *Not a duplicate of:* `dependency.unused-direct`, which is binary. E1 covers the far more common
  case — a large dependency pulled in for one function.
- *Drives:* `NATIVE_REPLACEMENT` modernization candidates, which the schema already models but which
  currently have no deterministic trigger. Both `package_api_surface.completeness` and
  `dependency_usage_summary.limitations` must be surfaced with the finding; a `PARTIAL` analysis
  will otherwise manufacture false "unused surface."

### Theme F — Deployment topology and resilience

The IaC scanner emits `Deployment`, `Environment`, and `ContainerImage` entities with `DEPLOYED_AS`,
`RUNS_ON`, and `LOCATED_IN` edges. Only the external-exposure rule reads any of it.

**F1 · `deployment.image-provenance` — Mutable and stale base images** · HIGH · ACTIVE

- *Signal:* `RUNS_ON` targets resolved to a `ContainerImage` pinned by mutable tag (`:latest`, a
  bare major) rather than digest; distinct base images across the estate.
- *Not a duplicate of:* Theme A, which covers package artifacts. Container base images are a
  parallel and usually larger unpatched surface.
- *Drives:* digest pinning and base-image consolidation.

**F2 · `deployment.environment-parity` — Environments that have drifted apart** · MEDIUM · ACTIVE

- *Signal:* one repository's `DEPLOYED_AS` deployments across distinct `Environment` entities
  declaring different images or different `USES` technology sets.
- *Not a duplicate of:* anything. It also materially qualifies `business.critical-impact`: a finding
  present in staging but not production is a different priority.

**F3 · `deployment.concentration` — Portability and single-point exposure** · MEDIUM · NEEDS_EXTRACTOR

- *Signal:* estate share bound to one `CloudProvider`, `Region`, or `ComputeTarget`.
- *Blocked on:* the ontology declares `CloudProvider`, `Region`, and `ComputeTarget`; the scanner
  emits none of them. Terraform and Kubernetes manifests already parsed carry provider and region
  attributes, so this is an extractor extension, not a new source.

### Theme G — Business alignment and negative space

The Business Map is governed, versioned, and rich — `criticality`, `maturity`, `owner`, `kpis`,
`shared_group` — and exactly one field (`criticality`) reaches an insight. The map's real analytic
power is in what it shows to be *missing*.

**G1 · `business.dark-capability` — Business capabilities with no software behind them** · HIGH · ACTIVE

- *Signal:* `business_map_capability` with `criticality >= 4` and zero rows in
  `business_map_application_assignment`.
- *Not a duplicate of:* `package_business_blast_radius`, which is explicitly gated on
  `requires_mapped_rows`. Every existing business insight reasons from what *is* mapped; G1 reasons
  from what is not. Two readings, both actionable: either the capability is served by a system
  StackGraph cannot see (shadow IT, SaaS, mainframe), or the map is wrong.
- *Drives:* onboarding the missing system, or correcting the map. It is also the honest disclosure
  that bounds every other business-mapped finding.

**G2 · `business.unmapped-application` — The shadow portfolio** · MEDIUM · ACTIVE

- *Signal:* `ENTERPRISE/Application` entities with no `business_map_application_assignment` row.
- *Not a duplicate of:* the inverse of G1. Spend and risk with no business owner.
- *Drives:* either map it or challenge its existence — which feeds the existing
  `application_retirement_consolidation` report with a deterministic input it currently lacks.

**G3 · `business.ownership-gap` — Unowned critical capabilities** · MEDIUM · ACTIVE

- *Signal:* `business_map_capability.owner IS NULL OR owner=''` at `criticality >= 4`, cross-referenced
  with open findings on the applications assigned to it.
- *Drives:* routing. Findings on an unowned capability have nowhere to go, which is why they age.

**G4 · `business.investment-mismatch` — Investment not tracking criticality** · HIGH · ACTIVE

- *Signal:* join `business_map_capability.criticality` and `business_map_placement.maturity` against
  the count and effort of open `modernization_recommendation` rows for the assigned applications.
  Two findings: high criticality + low maturity + no open recommendations (**under-served**), and
  low criticality absorbing disproportionate recommended effort (**over-served**).
- *Not a duplicate of:* `standardization_initiatives`, which ranks candidate initiatives by payoff.
  G4 audits the *allocation across the portfolio*, including the absence of candidates where they
  should exist. Absence is the finding.
- *Drives:* the annual planning conversation. Pairs naturally with the existing scenario planner.

**G5 · `business.shared-capability-divergence` — Declared-shared, implemented apart** · MEDIUM · ACTIVE

- *Signal:* members of a `business_map_shared_group` whose `capability_footprint.technology_counts`
  show disjoint technology sets.
- *Not a duplicate of:* `capability.technology-diversity` measures entropy within one capability.
  G5 fires only where the business has *explicitly declared* capabilities should be shared and the
  estate contradicts it — a governance breach, not a style difference.

### Theme H — Model assurance

Every finding above is only as good as the model beneath it. These insights are about StackGraph's
own epistemics. They are unglamorous and they are what earns the platform the right to be believed
in a room where someone will push back.

**H1 · `assurance.coverage` — What share of the estate can we speak to?** · HIGH · ACTIVE

- *Signal:* composite of `freshness_state` (`STALE`/`ERROR`), `dead_letter` backlog,
  `connector_quota` at `THROTTLED`/`EXHAUSTED`, repositories with no `source_snapshot`, and —
  critically — **ecosystems present in the estate but not analysable**. The scanners parse npm and
  PyPI only; a Java, .NET, Go, or Rust repository currently contributes nothing to any finding while
  appearing in `EstateCounts.repositories`. `ecosystem_admission` models the admission decision but
  is not surfaced as coverage.
- *Not a duplicate of:* `EstateCoverage`, which reports scanned-repository count and evidence ratio.
  H1 converts that into the analytic statement: *these findings cover 61% of the estate; here is the
  other 39% and why*.
- *Drives:* connector investment. It also prevents the single most damaging failure mode — a clean
  dashboard for an estate that was never read.

**H2 · `assurance.inference-reliance` — How much of this is inferred?** · MEDIUM · ACTIVE

- *Signal:* distribution of `fact_assertion.assertion_class` and `confidence` across the facts
  supporting current findings; share of `capability_inference` rows carrying a
  `model_invocation_id` (LLM-derived) and still `UNREVIEWED`.
- *Not a duplicate of:* `Phase3IntelligenceMetrics.evidence_completeness_rate`, which is a pipeline
  health metric. H2 attaches the provenance mix to the *findings a customer is about to act on*.
- *Drives:* review prioritisation, and it is the correct answer to "how do you know?"

**H3 · `assurance.resolution-debt` — Duplicate identities distorting every count** · MEDIUM · ACTIVE

- *Signal:* `identity_assertion` at `review_state='POSSIBLE'` with high confidence, weighted by how
  many findings the affected entities appear in.
- *Drives:* the identity review queue. Unresolved duplicates inflate technology diversity, deflate
  blast radius, and split version fragmentation — they corrupt several existing rules silently.

**H4 · `assurance.rule-precision` — Which rules are producing noise?** · MEDIUM · ACTIVE

- *Signal:* rejection and dismissal rates from `modernization_recommendation_review`,
  `capability_inference_review`, and `duplicate_capability_candidate_review`, attributed to the
  originating rule or analyzer, with backlog aging.
- *Not a duplicate of:* `Phase3IntelligenceMetrics` reports aggregate precision and acceptance.
  H4 attributes them **per rule**, which is what makes them actionable through the existing
  `deterministic_insight_rule_policy` controls (severity, `minimum_repositories`, enable/disable).
- *Drives:* self-tuning. A rule rejected 80% of the time should be down-weighted, and the tenant
  already has the control surface to do it.

**H5 · `assurance.policy-posture` — Code policy compliance over time** · MEDIUM · ACTIVE

- *Signal:* `repository_code_policy_evaluation` status mix, `violation_count` trend, and
  `unclassified_count` as an explicit coverage caveat.
- *Not a duplicate of:* the planned `architecture.drift`, which infers deviation from golden-stack
  *peers*. H5 evaluates the tenant's *explicit* allow/prohibit lists in `tenant_code_policy`, and
  that data is already computed and stored. This is the cheapest way to give `architecture.drift`
  a shipping predecessor while golden stacks remain NEEDS_DATA.

---

## 5. Prioritisation

Ranked by (enterprise decision value) × (readiness) ÷ (implementation cost).

**Tier 1 — build first.** Each is ACTIVE, reads data already populated, and answers a question no
existing surface touches.

| # | Insight | Why first |
| --- | --- | --- |
| 1 | `assurance.coverage` (H1) | Bounds the credibility of everything else; prevents a false all-clear |
| 2 | `oss.license-obligation` (B1) | Finite, closable, legally material, executive-visible |
| 3 | `estate.technology-introduction` (C1) | Answers the README's own unanswered question; opens the time dimension |
| 4 | `code.vendored-third-party` (D2) | Closes a real hole in the vulnerability story |
| 5 | `supplychain.dependency-confusion` (A1) | Critical severity, no coverage, cheap query |
| 6 | `business.dark-capability` (G1) | Turns the Business Map from a filter into an analytic asset |
| 7 | `code.cross-repository-clone` (D1) | Gives `internal_library_standards` a deterministic input |
| 8 | `estate.decision-lag` (C3) | Measures whether the platform is producing outcomes |

**Tier 2 — high value, follows Tier 1 patterns.** A2, A4, B2, B3, C2, D3, E1, F1, G2, G4, H2, H4, H5.

**Tier 3 — later.** Blocked on an extractor or a new source: B4, B5, F3, and A3 (needs a tenant
approved-registry list). Ready but narrower in value, or dependent on a Tier 1/2 insight shipping
first: C4, D4, F2, G3, G5, H3.

## 6. Where each lands in the product surface

Three delivery shapes, matching what already exists:

1. **`RULE_CATALOG` entries** — per-entity, policy-governed, severity-scored findings that fit
   `DeterministicInsight`: A1, A2, A4, B1, B2, B3, C2, D1, D2, D3, E1, F1, F2, G1, G2, G3, G5.
   These need a `rule_key`, a SQL query in the `queries` tuple, an `InsightKind` contract addition,
   and a `deterministic_insight_rule_policy` default row. The existing `InsightImpactStages` funnel
   (present → referenced → statically reachable → runtime observed → deployed → production →
   externally exposed → business critical) applies to all of them unchanged, which is a strong
   argument for this shape wherever it fits.
2. **`_ENTERPRISE_INSIGHT_REPORTS` entries** — estate-wide aggregate questions with a headline
   metric: C1, C3, G4, A3, H1. These need a question, a metric field, and an Ask-pipeline query.
3. **New read models** — cross-cutting posture surfaces that are neither per-entity findings nor
   single questions: H1 belongs in the estate summary as a coverage statement, H2 as a provenance
   band on every finding, H4 and H5 as admin/governance panels, C4 and H3 as data-quality panels
   beside them, and D4 as a `missing_inputs` contribution to other findings rather than a standalone
   item.

The four blocked proposals (B4, B5, F3, A3) take shape 1 or 2 once their extractor or source lands;
none of them needs a delivery mechanism the platform does not already have.

Contract impact: `InsightKind` is a closed union in
[read-models.ts:337](../packages/shared/src/contracts/read-models.ts:337) and will need extending
per rule. `DeterministicInsight` itself needs no new fields — `missing_inputs`, `evidence_coverage`,
and `scope_entity_ids` already carry what the new rules need to be honest about their limits.

## 7. Caveats

- **Ecosystem coverage is the binding constraint.** npm and PyPI only. Themes A, B, and E are npm/PyPI
  findings presented against an estate that may be mostly neither. H1 must ship before or alongside
  them, or the catalog overstates its reach.
- **Theme A is npm-only even within scanned ecosystems**, because `dependency_resolution` is
  populated by the npm resolver alone.
- **Rule count is not the goal.** Thirty-one proposals is a menu, not a roadmap. Each rule added to
  `RULE_CATALOG` costs query time on every insight list call (the 30-second cache in
  `_INSIGHT_CACHE` mitigates but does not remove this) and adds a row to a UI that is already dense.
  Tier 1 is eight insights, and eight is a release.
- **Several proposals are load-bearing for existing reports.** D1 feeds `internal_library_standards`,
  G2 feeds `application_retirement_consolidation`, E1 feeds `NATIVE_REPLACEMENT` candidates. Those
  reports currently answer from thin or absent deterministic input; building the proposals improves
  what already ships rather than only adding surface.
