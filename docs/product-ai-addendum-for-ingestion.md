# StackGraph product/AI addendum for ingestion

**Date:** 2026-08-19  
**Status:** Product direction and staged design; extends, but does not expand, the V0 ingestion commitment  
**Companions:** `stackgraph-dependency-ingestion-plan.md`, `stackgraph-implementation-plan.md`, `stackgraph-specs.md`

## 1. Purpose

This addendum describes how StackGraph can grow from deterministic dependency ingestion into a product that understands:

1. the global OSS/package ecosystem;
2. the packages and versions used by a customer repository;
3. how much of each dependency the repository actually uses;
4. duplicated internal or external capability;
5. safer or better-fit alternatives; and
6. the evidence, confidence, and effort behind each conclusion.

The design separates two connected graph planes:

```text
Registries, package artifacts, repositories, advisories, usage signals
                              |
                              v
                    OSS reference graph
                              |
                              v
Customer manifests, lockfiles, source, builds, and optional runtime evidence
                              |
                              v
                  Tenant repository graph
                              |
                              v
            Analysis and AI-supported inference
                              |
                              v
       Usage, risk, duplication, alternatives, and migration actions
```

The global reference graph is shared. Repository observations, source-derived facts, and organization-specific conclusions remain tenant-scoped. A canonical package or package-version node is not duplicated merely because multiple tenants use it.

## 2. Product principles

### 2.1 Function before package

StackGraph must first determine the job a dependency performs in the application before recommending a replacement.

For example, a repository may declare `lodash` but use only `debounce`, `groupBy`, and `get`. The decision space may include native JavaScript, a focused dependency, `lodash-es`, or retaining the existing package. A generic “similar package” match is insufficient.

### 2.2 Versions are first-class

Package health, APIs, dependencies, licenses, vulnerabilities, and runtime compatibility vary by version. Applications are evaluated against the declared or resolved version they use, not only against a package's latest state.

### 2.3 Facts and inference must remain distinguishable

Every conclusion is classified as:

- **Observed:** directly present in a manifest, lockfile, source file, registry response, artifact, advisory, repository, build, or runtime trace.
- **Derived:** produced deterministically from observed evidence, such as dependency resolution, reachability, or a score calculated by a versioned method.
- **Inferred:** produced probabilistically, including capability classification, semantic similarity, or an AI-supported recommendation.

AI does not replace deterministic package resolution, parsing, identity, or evidence capture.

### 2.4 No conclusion without provenance

Every fact, relationship, assessment, and recommendation must retain:

- source and source locator;
- observed-at and effective-at timestamps where applicable;
- repository revision or package artifact checksum;
- scanner, rule, model, and prompt/policy version as applicable;
- assertion class;
- confidence and confidence rationale;
- supporting and counter-evidence; and
- review state when human confirmation is possible.

## 3. OSS/package reference ingestion

### 3.1 Catalog scope

The long-term catalog may cover:

| Ecosystem | Initial source/identity plane |
|---|---|
| JavaScript / TypeScript | npm |
| Python | PyPI |
| .NET | NuGet |
| Java / Kotlin | Maven Central |
| Go | Go modules |
| Rust | crates.io |
| Ruby | RubyGems |
| PHP | Packagist |

V0 remains focused on packages observed in customer repositories or an approved curated seed, beginning with npm and PyPI. It does not require mirroring every registry. NuGet and other ecosystems should be added through the same contracts after identity, refresh, and analysis behavior is proven.

### 3.2 Defining “most used”

“Most used” must not be equated with raw downloads. Catalog ranking should be a versioned composite of available signals such as:

- direct and transitive dependents;
- downloads with bot, mirror, CI, and suspicious-traffic limitations documented;
- usage in an explicitly defined public-repository cohort;
- customer-estate prevalence, reported only in privacy-safe aggregate form;
- graph centrality;
- release recency and cadence;
- maintainer and contributor activity; and
- ecosystem-specific importance.

Every adoption or popularity statement must name its cohort, denominator, measurement window, and source limitations. Customer-centered discovery cannot be presented as a global adoption trend.

The catalog can be populated through three cohorts:

1. **Observed:** packages found in customer repositories.
2. **Curated:** approved technologies or strategically important packages.
3. **Ranked ecosystem:** a bounded, explicitly sampled set used for reference and alternative discovery.

### 3.3 Package resolution and enrichment

For each observed or curated package version, resolve as available:

- ecosystem, namespace, name, version, and canonical purl;
- published artifact location, integrity hash, signatures, and provenance;
- declared and resolved dependencies;
- runtime, development, optional, peer, build, and platform-specific dependency scope;
- license declarations and detected license evidence;
- repository/project identity and maintainers;
- publication, deprecation, yank, archive, and support state;
- releases and runtime/platform compatibility;
- vulnerabilities and malicious-package signals;
- downloads, dependents, contribution activity, and other cohort-qualified statistics;
- exported modules, classes, functions, types, and commands; and
- documented capabilities and migration/deprecation guidance.

Raw external responses should be retained long enough to audit normalization. Normalized facts are idempotent and reference the raw observation from which they were produced.

### 3.4 Reference graph model

Core node types include:

- Ecosystem
- Package
- Package Version
- Artifact
- OSS Project
- OSS Repository
- Release
- Symbol / API
- Runtime / Platform
- Capability
- Maintainer / Organization
- License
- Vulnerability
- Migration Pattern

Core relationships include:

```text
PackageVersion VERSION_OF Package
PackageVersion PUBLISHED_AS Artifact
PackageVersion DEPENDS_ON PackageVersion|PackageConstraint
PackageVersion EXPOSES Symbol
Package IMPLEMENTED_BY OSSProject
OSSProject HOSTED_IN OSSRepository
OSSProject MAINTAINED_BY Maintainer|Organization
PackageVersion AFFECTED_BY Vulnerability
Package|Symbol PROVIDES Capability
PackageVersion COMPATIBLE_WITH Runtime|Platform
Package|Capability ALTERNATIVE_TO Package|Capability
Package|PackageVersion MIGRATES_TO Package|PackageVersion
```

`ALTERNATIVE_TO`, `PROVIDES`, and `MIGRATES_TO` may be asserted, derived, or inferred. They must never appear as unqualified truth without evidence, context, and confidence.

## 4. Incremental reference refresh

The system should process changed information rather than repeatedly rebuilding the graph.

### 4.1 Change-driven pipeline

1. Maintain a cursor, watermark, ETag, last-modified value, or content fingerprint per source and object.
2. Poll source-specific change feeds or refresh only records whose freshness policy has expired.
3. Fetch metadata or artifacts only for new or changed package/project versions.
4. Compare artifact hashes and normalized observation fingerprints.
5. Re-run only invalidated normalization and analysis stages.
6. Update the changed node and its bounded affected neighborhood.
7. Recalculate expensive global metrics asynchronously and only when their inputs materially change.

Useful immutable work events include:

```text
PackageVersionPublished
PackageMetadataChanged
PackageVersionDeprecatedOrYanked
PackageArtifactChanged
ProjectRepositoryStateChanged
ReleasePublished
AdvisoryPublishedOrModified
PopularityWindowClosed
AnalyzerVersionChanged
```

### 4.2 Refresh classes

| Data | Trigger / indicative cadence |
|---|---|
| New package version | Registry event or short poll |
| Security advisory | Near real time or frequent batch |
| Deprecation/yank state | Registry event or scheduled refresh |
| Project/repository health | Daily to weekly, based on importance |
| Popularity/adoption window | Daily or weekly aggregate |
| API/symbol extraction | Artifact checksum or analyzer change |
| Centrality/ecosystem rank | Scheduled batch after meaningful graph change |

Refresh intervals are operational configuration, not fixed product truth. Active, customer-observed, vulnerable, or high-centrality packages can be kept warm; cold catalog entries can refresh less often or on demand.

### 4.3 Reuse and invalidation

Analysis artifacts should be content-addressed by inputs such as:

```text
package artifact checksum
+ analyzer name/version
+ configuration/policy version
+ relevant capability taxonomy version
= analysis fingerprint
```

If the fingerprint is unchanged, StackGraph reuses the prior result. A new analyzer or taxonomy version can selectively invalidate the affected stage without refetching the package artifact.

## 5. Tenant repository graph

### 5.1 Deterministic discovery

Repository ingestion begins with:

- manifests and lockfiles;
- workspace and monorepo configuration;
- imports, requires, includes, and language-specific dependency declarations;
- vendored or copied code indicators;
- build, test, container, CI, and deployment configuration;
- generated SBOMs where available; and
- optional build or runtime traces when explicitly enabled.

The tenant graph should connect:

```text
Organization
  -> Application / Service
  -> Repository / Repository Revision
  -> Component / Module
  -> Dependency Observation
  -> canonical Package Version
  -> imported or invoked Symbol
  -> Capability
```

Each dependency observation retains scope, resolution method, manifest/lock/source evidence, and the repository revision on which it was observed.

### 5.2 Scanner passes

The existing staged scanner model remains appropriate:

- **Pass A — inventory:** manifests, locks, versions, dependency scopes, runtimes, frameworks, and deployment facts.
- **Pass B — evidence refinement:** imports, symbol references, entry points, declared-versus-referenced usage, and initial capability detection.
- **Pass C — asynchronous depth:** reachability, semantic similarity, internal reuse, targeted history, runtime evidence, and alternative/migration analysis.

A repository revision change invalidates only affected files, components, and analyses where language/build-system semantics permit. A complete scan may close facts no longer observed; a partial or failed scan must not remove prior facts.

## 6. Analysis beyond dependency inventory

### 6.1 Usage depth

StackGraph should report several measurements rather than one ambiguous “percent used” value:

| Measure | Question answered | Evidence |
|---|---|---|
| Import coverage | Which package modules are imported? | AST/import graph |
| Public API coverage | Which exported symbols are referenced? | symbol resolution |
| Static reachability | Which implementation is reachable from application entry points? | call/reachability graph |
| Runtime execution coverage | Which symbols or paths execute in observed workloads? | optional instrumentation/traces |
| Artifact contribution | How much package code contributes to the shipped bundle/image? | build/bundle analysis |

Each percentage must state its denominator. For example, “8 of 120 public exports referenced” is different from “18% of implementation reachable” and from “4 functions observed at runtime.” Dynamic dispatch, reflection, generated code, native extensions, plugins, and framework conventions must reduce confidence or be explicitly marked as blind spots.

Useful product outputs include:

- installed but apparently unused dependency;
- used only in tests or tooling;
- narrow use of a broad dependency;
- substantial or framework-defining use;
- package contribution to bundle, image, or cold-start cost; and
- dependency removal or replacement blast radius.

### 6.2 Capability inference

Capability inference maps packages, symbols, and internal code to the jobs they perform. It may combine:

- curated package-to-capability mappings;
- package metadata and documentation;
- imported and invoked symbols;
- surrounding source and call sites;
- configuration and framework conventions;
- test names and behavior;
- runtime evidence; and
- AI/LLM classification.

The inference result should include the proposed capability, scope, evidence excerpts or locators, counter-signals, confidence, and taxonomy/model version.

### 6.3 Duplicated effort

Detect candidates such as:

- local functions that reproduce package functionality;
- multiple dependencies serving the same capability;
- copied, forked, or vendored OSS code;
- internal wrappers that reproduce most of a library;
- similar implementations across repositories; and
- custom code made unnecessary by a newer runtime or package version.

Candidate generation should combine structural fingerprints, dependency/symbol usage, embeddings, tests, and behavior where available. AI can describe semantic similarity and likely intent, but similarity alone must not be presented as proof of equivalence.

### 6.4 Alternative and migration analysis

An alternative is evaluated against the application's actual capability requirements and constraints, not against a package category label.

Score and expose:

- capability and API fit;
- behavior and semantic compatibility;
- runtime/platform/framework compatibility;
- migration surface and affected call sites;
- test coverage around the affected behavior;
- bundle/image size and performance implications;
- security and malicious-package history;
- maintenance health and release trajectory;
- license and policy compatibility;
- community and internal adoption;
- operational impact; and
- estimated effort, uncertainty, and rollback path.

A recommendation should read like:

> Package A provides 12 known capabilities; this repository appears to use 3. Package B covers those 3, reduces the browser bundle by an estimated 80 KB, and affects 14 call sites. Confidence: medium. Validate dynamic plugin behavior and the 5 call sites without test coverage before migration.

“Better” must always mean better for a stated objective and context. A recommendation must show tradeoffs and counter-signals rather than asserting a universal winner.

## 7. Role of AI models

### 7.1 Appropriate AI responsibilities

AI is useful for:

- inferring the purpose of local code and dependency usage;
- mapping code and packages to a capability taxonomy;
- explaining unfamiliar dependencies in application context;
- generating semantic-duplication candidates;
- comparing alternatives against repository-specific requirements;
- identifying likely static-analysis gaps;
- summarizing evidence and counter-evidence; and
- proposing migration steps and validation plans.

### 7.2 Responsibilities that remain deterministic

AI should not be the authority for:

- canonical package identity or purl construction;
- version and lockfile resolution;
- manifest, AST, or build parsing;
- vulnerability applicability when a deterministic advisory match exists;
- checksums, licenses, or artifact provenance;
- source locations and call-site counts; or
- whether a scan was complete.

### 7.3 Inference contract

An AI-produced assertion should carry at minimum:

```json
{
  "assertionClass": "INFERRED",
  "subject": "tenant-scoped or canonical entity reference",
  "predicate": "PROVIDES_CAPABILITY",
  "object": "capability reference",
  "confidence": 0.82,
  "confidenceBand": "MEDIUM",
  "evidenceRefs": [],
  "counterEvidenceRefs": [],
  "model": "model identifier",
  "modelVersion": "provider/model version",
  "policyVersion": "inference policy version",
  "inputFingerprint": "content-addressed input set",
  "createdAt": "timestamp",
  "reviewState": "UNREVIEWED"
}
```

Do not retain source content in model prompts, traces, or external systems beyond the tenant's configured data-handling policy. Derived embeddings and caches are tenant-isolated unless they originate solely from public canonical artifacts.

## 8. Product result contract

Every deep-analysis result should answer:

1. **What was found?**
2. **Where was it found?**
3. **Why does it matter?**
4. **How certain is StackGraph?**
5. **What evidence and counter-evidence support it?**
6. **What action is proposed?**
7. **What would the action affect?**
8. **How can a person validate or dismiss it?**

Recommended result types include:

- unused or weakly used dependency;
- narrow-capability dependency;
- obsolete or non-viable dependency;
- duplicate package capability;
- duplicate internal implementation;
- native runtime replacement opportunity;
- package consolidation opportunity;
- upgrade recommendation;
- alternative-package recommendation; and
- migration plan with affected components and call sites.

Findings and recommendations are versioned against repository revision, reference-graph freshness, analyzer version, and model/policy version. A change in any material input marks the result stale and schedules selective reevaluation.

## 9. Delivery sequence

### Phase 0 — V0 deterministic foundation

1. Establish purl-based identity and package-version nodes.
2. Ingest JS/TS and Python manifests and lockfiles.
3. Persist idempotent dependency facts with exact evidence.
4. Enrich observed versions through deps.dev, registries, and OSV.
5. Implement revision-aware repository refresh and source-aware package refresh.

### Phase 1 — usage evidence

1. Add JS/TS and Python import and symbol analysis.
2. Separate declared, resolved, referenced, reachable, and runtime-observed use.
3. Surface unused and narrow-use candidates with limitations.
4. Add package API/symbol extraction keyed by artifact checksum.

### Phase 2 — capability intelligence

1. Establish a versioned capability taxonomy.
2. Curate high-value package/symbol mappings.
3. Add AI-supported capability inference with evidence and review.
4. Detect multiple packages serving the same repository capability.

### Phase 3 — duplication and alternatives

1. Generate semantic-duplication candidates within tenant boundaries.
2. Rank native, internal, upgrade, and alternative-package options.
3. Estimate affected call sites, migration effort, and validation gaps.
4. Produce evidence-backed recommendations and migration plans.

### Phase 4 — broader reference intelligence

1. Add NuGet and subsequent ecosystems through the proven contracts.
2. Introduce bounded ranked ecosystem cohorts.
3. Add cohort-qualified adoption, co-occurrence, and trajectory signals.
4. Add targeted public migration/reference evidence where a product question justifies it.

## 10. Success metrics and guardrails

### 10.1 Product metrics

- percentage of dependency observations resolved to an exact canonical version;
- percentage with file- or JSON-pointer-level evidence;
- time from repository change to refreshed findings;
- package enrichment cache reuse and unchanged-fetch rate;
- percentage of declared packages classified as referenced, reachable, runtime-observed, or unknown;
- precision of unused-dependency and duplicate-capability findings after review;
- recommendation acceptance, dismissal, and successful-validation rates;
- median affected-call-site and migration-effort estimation error; and
- percentage of results with complete provenance, counter-signals, and freshness.

### 10.2 Guardrails

- Do not ingest all public source or every registry package to answer customer dependency questions.
- Do not expose tenant source, embeddings, package prevalence, or findings across tenants.
- Do not treat missing static evidence as proof of non-use.
- Do not collapse security, maintenance, adoption, compatibility, and viability into one opaque score.
- Do not recommend an alternative without capability fit, compatibility, effort, and counter-signal evidence.
- Do not present AI inference as an observed fact.
- Do not remove prior facts after a partial or failed scan.
- Do not publish global ecosystem conclusions from an undefined or customer-biased cohort.

## 11. Initial product wedge

The strongest initial product is not a complete mirror of the world's package ecosystem. It is an evidence-backed answer to:

> Exactly what does this repository use, why is it present, how deeply is it used, how risky or viable is it, and what would change if it were upgraded, removed, consolidated, or replaced?

The OSS reference graph should expand from packages encountered in real customer repositories and approved curated cohorts. Broader catalog ingestion is justified only when it improves an explicit customer decision such as alternative discovery, migration evidence, viability comparison, or ecosystem trajectory analysis.
