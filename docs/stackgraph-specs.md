# StackGraph --- Product & Intelligence Specifications

**Status:** Foundational product specification\
**Date:** August 2026\
**Scope:** Product thesis, user experience, intelligence model,
discovery/enrichment behavior, OSS reference graph, viability and
modernization reasoning.\
**Schema note:** The physical PostgreSQL/Apache AGE schema is maintained
separately. This document intentionally focuses on product semantics,
behavior, requirements, reasoning, and experience.

------------------------------------------------------------------------

## 1. Executive summary

StackGraph is an **enterprise software estate intelligence and
modernization platform** designed for a world in which software creation
is accelerating dramatically through coding agents, AI-assisted
development, and "vibe coding."

The underlying enterprise problem is not simply that organizations have
vulnerabilities. It is that they increasingly cannot answer basic
questions about their software estate:

-   What applications, services, components, and repositories exist?
-   What business functions, processes, capabilities, and value-chain
    stages do they support?
-   What languages, runtimes, frameworks, packages, databases, UI
    systems, infrastructure components, and deployment patterns do they
    use?
-   What are the direct and transitive dependencies?
-   Where is each workload intended to run: cloud, on-premises,
    Kubernetes, containers, VMs, serverless, managed services?
-   Which technologies are healthy and strategically viable versus
    merely free of known CVEs?
-   Which packages/frameworks are unsupported, abandoned, declining,
    unnecessarily complex, or superseded by native/runtime capabilities?
-   Which technologies have better alternatives for the **actual
    function being performed**?
-   Where has the organization independently implemented the same
    capability multiple times?
-   Which applications should be retained, upgraded, consolidated,
    refactored, rebuilt, replatformed, retired, or investigated?
-   Where should modernization investment be directed based on business
    importance, technical viability, opportunity, confidence, and
    effort?
-   What new technology and architecture patterns are coding agents
    introducing into the estate?

StackGraph addresses this by turning source repositories and related
evidence into a continuously updated, evidence-backed model of:

**Business → Applications → Code → Technology → Dependencies →
Deployment → Infrastructure → OSS ecosystem → Viability → Modernization
actions**

Git repositories are a primary sensor, not the final product.

------------------------------------------------------------------------

## 2. Product thesis

### 2.1 Why now

AI coding agents materially increase the rate at which software can be
created and modified. That creates an organizational visibility problem.

Teams and agents can introduce:

-   new frameworks,
-   packages,
-   runtime versions,
-   duplicate internal components,
-   inconsistent authentication approaches,
-   different UI libraries,
-   different API patterns,
-   new cloud services,
-   new deployment models,
-   transitive dependencies,
-   unsupported or weakly maintained OSS,
-   architectural divergence.

The cost of producing software is falling faster than the cost of
understanding and governing the resulting estate.

StackGraph becomes the **intelligence/control plane for the software
estate**.

### 2.2 Product category

StackGraph sits across several existing categories but should not be
positioned as merely one of them:

-   software composition analysis,
-   application portfolio management,
-   enterprise architecture,
-   developer portals,
-   CMDB,
-   cloud inventory,
-   vulnerability management,
-   architecture governance,
-   modernization consulting,
-   dependency management.

The intended category is closer to:

> **Software Estate Intelligence / Technology Viability & Modernization
> Intelligence**

### 2.3 Core proposition

> Connect read-only to an organization's software repositories and
> continuously understand what the enterprise runs, why it exists, what
> it depends on, where it runs, how viable it is, what the external
> software ecosystem says about those choices, and what should change.

------------------------------------------------------------------------

## 3. The six questions StackGraph must answer

  -----------------------------------------------------------------------
  Question                            Capability
  ----------------------------------- -----------------------------------
  What do we have?                    Software Estate Discovery

  Why does it exist?                  Business / Value-Chain Mapping

  What is it built from?              Architecture & Dependency
                                      Intelligence

  Where and how does it run?          Deployment & Infrastructure
                                      Intelligence

  Is it viable?                       Technology / Application Viability
                                      Intelligence

  What should we do?                  Modernization & Optimization
                                      Intelligence
  -----------------------------------------------------------------------

A seventh question becomes increasingly important:

  -----------------------------------------------------------------------
  Question                            Capability
  ----------------------------------- -----------------------------------
  What is changing?                   Software Estate Observability /
                                      Temporal Intelligence

  -----------------------------------------------------------------------

------------------------------------------------------------------------

## 4. Primary users

### CTO / CIO

Needs portfolio-level answers:

-   Where is technology debt concentrated?
-   Which parts of the value chain rely on aging technology?
-   Where should modernization capital go?
-   How much architectural fragmentation exists?
-   What new technologies are appearing?
-   How much of the estate is cloud vs on-prem?
-   Which critical business functions have infrastructure concentration
    risk?

### Enterprise Architecture

Needs:

-   technology inventory,
-   architecture standards,
-   proliferation and entropy analysis,
-   approved/preferred technologies,
-   application dependency mapping,
-   capability duplication,
-   reference architecture comparison,
-   modernization candidates,
-   standardization opportunities.

### Engineering leadership

Needs:

-   repository/application-level recommendations,
-   evidence explaining recommendations,
-   migration complexity,
-   reusable internal implementations,
-   unsupported runtimes,
-   package/framework viability,
-   modernization sequencing.

### Platform Engineering

Needs:

-   runtime and framework versions,
-   deployment patterns,
-   cloud/on-prem footprint,
-   container/base-image usage,
-   internal platform adoption,
-   replatform candidates,
-   declared vs observed deployment drift.

### CISO / AppSec

Needs:

-   vulnerabilities,
-   transitive vulnerability paths,
-   vulnerable dependency reachability,
-   unsupported software,
-   supply-chain health,
-   business impact propagation.

Security is a major dimension, but **security is not the boundary of the
product**.

------------------------------------------------------------------------

## 5. Product architecture: interconnected intelligence domains

StackGraph should be understood as several interconnected logical
graphs.

### 5.1 Business graph

Represents:

-   Organization
-   Business Unit
-   Value Chain
-   Business Function
-   Business Process
-   Business Capability

Purpose:

Connect technology decisions back to enterprise value.

Example:

`Order-to-Cash → Billing → Invoice Customer → Invoice Generation → Billing Platform`

### 5.2 Enterprise technology graph

Represents the private software estate:

-   Application
-   Service
-   Component
-   API
-   Repository
-   Language
-   Runtime
-   Framework
-   Package
-   Database
-   Technology

### 5.3 Deployment / infrastructure graph

Represents declared and eventually observed runtime footprint:

-   Deployment
-   Environment
-   Compute Target
-   Container Image
-   Cloud Provider
-   Region
-   Infrastructure Resource
-   Database
-   Storage
-   Queue
-   Network-facing endpoint

### 5.4 OSS reference graph

This is **first-class**, not a side enrichment.

It represents what the outside software ecosystem knows about
technologies:

-   OSS Project
-   OSS Repository
-   Package
-   Package Version
-   Technology
-   Framework
-   Runtime
-   Capability
-   Release
-   License
-   Maintainer / Organization
-   Vulnerability
-   Reference Implementation
-   Migration Pattern
-   Ecosystem
-   adoption/co-occurrence signals
-   technology trajectory signals

### 5.5 Intelligence graph

Represents conclusions and actions:

-   Finding
-   Assessment
-   Recommendation
-   Modernization Opportunity
-   Standard

------------------------------------------------------------------------

## 6. Fundamental design principle: function before package

StackGraph must not ask:

> What package is similar to package X?

It must first ask:

> What function is package X actually providing in this application?

Example:

``` text
Repository imports lodash

Actual usage:
- debounce
- groupBy
- get
```

The recommendation space is therefore not simply another utility
library.

Possible conclusions:

1.  use native JavaScript for some functions,
2.  use a focused dependency for debounce,
3.  use `lodash-es` if broad utility behavior remains necessary,
4.  retain lodash if migration benefit is insufficient.

This principle applies throughout the product.

Examples:

-   TanStack Query and Zustand are both called "state management" but
    solve different jobs.
-   Kafka and RabbitMQ both involve messaging but are not universally
    interchangeable.
-   API gateways and service meshes solve different architectural
    concerns.
-   ORM and database are different layers.
-   runtime and web framework are different concepts.

The reference stack's **job-first classification** should remain
foundational.

------------------------------------------------------------------------

## 7. Technology purpose taxonomy

Technology should be modeled using several distinct concepts:

``` text
Technology
├── Domain
├── Category
├── Architecture Role
├── Capability
├── Use Case
└── Ecosystem
```

Example:

``` text
Kafka

Domain:
Middleware

Category:
Messaging / Streaming / Eventing

Architecture Role:
Durable Event Log

Capabilities:
- durable event streaming
- replay
- partitioned processing

Use Cases:
- event sourcing
- CDC
- streaming integration
```

RabbitMQ:

``` text
Architecture Role:
Message Broker

Capabilities:
- queues
- routing
- acknowledgements
- task distribution
```

This prevents incorrect "alternative" reasoning.

------------------------------------------------------------------------

## 8. Repository discovery

### 8.1 GitHub as initial sensor

The initial product should connect using a GitHub App with **minimal
read-only permissions**.

Avoid broad personal access tokens where possible.

The scanner should be able to process an organization with hundreds or
thousands of repositories without needing full semantic indexing of
every source line.

### 8.2 Repository-level discovery

Determine:

-   primary languages,
-   language proportions,
-   repository structure,
-   monorepo structure,
-   application/service boundaries,
-   build systems,
-   project metadata,
-   ownership metadata where available,
-   repository activity,
-   package manifests,
-   lock files,
-   infrastructure/deployment artifacts.

### 8.3 Source scanning

The product does **not** need a complete code graph initially.

It needs enough source understanding to identify:

-   imports,
-   libraries actually used,
-   frameworks,
-   selected functions/capabilities,
-   CSS/UI systems,
-   SDKs,
-   API clients,
-   framework configuration,
-   application entry points,
-   architecture clues.

File/function/class/symbol-level information can remain evidence rather
than first-class graph nodes in V1.

------------------------------------------------------------------------

## 9. Language/ecosystem scanners

### JavaScript / TypeScript

Parse and inspect:

-   `package.json`
-   package lock files
-   pnpm/yarn files
-   imports/requires
-   `tsconfig`
-   Next.js configuration
-   Vite configuration
-   Tailwind configuration
-   framework-specific files
-   CSS imports
-   test configuration
-   monorepo configuration

Infer:

-   Node/runtime expectations,
-   React/Vue/Angular/Svelte/etc.,
-   Next/Nuxt/etc.,
-   backend frameworks,
-   direct dependencies,
-   actual package usage,
-   UI/component systems,
-   test stack,
-   build stack.

### Python

Parse:

-   `pyproject.toml`
-   `requirements*.txt`
-   Poetry
-   uv
-   Pipenv
-   imports
-   framework configuration

Infer:

-   Python runtime,
-   FastAPI/Django/Flask/etc.,
-   direct packages,
-   actual imports,
-   data stack,
-   test stack,
-   background-job stack.

### Expansion

Later scanners should include:

-   Java/Kotlin
-   C#/.NET
-   Go
-   Rust
-   PHP
-   Ruby
-   infrastructure languages/configuration.

------------------------------------------------------------------------

## 10. Dependency intelligence

StackGraph should distinguish:

-   declared dependency,
-   observed/imported dependency,
-   direct dependency,
-   transitive dependency,
-   development dependency,
-   optional dependency,
-   peer dependency,
-   runtime dependency.

A package present in a manifest but never used is different from a
package imported in production code.

Likewise:

``` text
Enterprise App
  → directly depends on A
  → A depends on B
  → B depends on vulnerable C
```

must be explainable as a path.

The product should avoid unnecessarily expanding every possible
dependency globally. It can hydrate dependency neighborhoods **on demand
around technologies present in customer estates**.

------------------------------------------------------------------------

## 11. Deployment intelligence

Deployment manifests available in repositories are a major source of
estate intelligence.

Scan:

-   Dockerfiles
-   docker-compose
-   Kubernetes YAML
-   Helm
-   Terraform
-   CloudFormation
-   Pulumi
-   serverless configuration
-   GitHub Actions
-   Azure DevOps pipelines
-   provider-specific deployment descriptors

Normalize provider-specific details into common concepts.

### Compute types

Examples:

-   Kubernetes
-   managed container service
-   serverless function/service
-   VM
-   app platform
-   bare metal
-   on-prem Kubernetes
-   on-prem VM
-   unknown

Retain concrete implementation separately:

-   AWS ECS
-   AWS EKS
-   Lambda
-   Azure AKS
-   Azure App Service
-   Google Cloud Run
-   OpenShift
-   VMware
-   etc.

This enables both:

> How much of our estate runs on AWS?

and:

> How many applications are still VM-hosted?

### Environments

Distinguish:

-   dev
-   test
-   QA
-   staging
-   prod
-   DR

The same repository may have different deployment architectures by
environment.

### Declared vs observed deployment

This distinction is mandatory.

**Declared deployment** means repo/IaC evidence indicates an intended
state.

**Observed deployment** means a cloud/platform/runtime integration
confirms the running state.

V1 can rely primarily on declared deployment.

Future integrations can identify drift:

``` text
Repo declares: 2 replicas
Observed: 7 replicas

Repo expects: Node 20
Running image: Node 18

Repo declares: PostgreSQL
Observed: Aurora PostgreSQL
```

------------------------------------------------------------------------

## 12. Cloud vs on-prem footprint

StackGraph should provide estate-level views such as:

``` text
AWS                    43%
Azure                  28%
GCP                     7%
On-Prem Kubernetes     12%
On-Prem VM              8%
Unknown                 2%
```

It should support queries such as:

-   Which revenue-critical applications remain on-prem?
-   Which applications could move to the standard container platform?
-   Which business processes rely on a single cloud/region?
-   Which workloads use unsupported base images?
-   Which applications have no infrastructure-as-code?
-   Which stateless VM-hosted services are strong replatform candidates?

------------------------------------------------------------------------

## 13. OSS graph: purpose

The OSS graph answers:

> What does the outside software ecosystem tell us about this
> technology, its dependencies, its function, its health, its
> trajectory, its alternatives, and how other developers migrate away
> from or toward it?

Without the OSS graph, StackGraph can describe **what an enterprise
has**.

With it, StackGraph can reason about **whether those choices still make
sense and what better options exist**.

------------------------------------------------------------------------

## 14. OSS graph hydration strategy

Do **not** attempt to clone or continuously crawl all of GitHub.

Build an **on-demand external technology graph** centered on
technologies encountered in customer estates and curated technology
seeds.

Potential sources:

-   public GitHub repository metadata/source,
-   package registries,
-   OSV,
-   deps.dev,
-   OpenSSF,
-   official project/release/support information,
-   curated StackGraph seed datasets.

Store signals such as:

-   release recency,
-   release cadence,
-   maintainer activity,
-   contributor breadth,
-   issue/PR activity,
-   archive/deprecation status,
-   license,
-   runtime compatibility,
-   vulnerabilities,
-   dependency health,
-   ecosystem adoption,
-   adoption trend,
-   migration-out rate,
-   migration-in rate,
-   technology affinity,
-   co-occurrence,
-   reference implementations.

Raw observations and StackGraph assessments must remain separate.

Example:

``` text
FACT:
last release = 4.2 years ago

ASSESSMENT:
maintenance health = LOW
```

------------------------------------------------------------------------

## 15. Curated knowledge seed

The supplied application framework landscape should be treated as
**product data**, not just documentation.

It seeds:

-   technology domains,
-   technology categories,
-   capabilities,
-   purpose descriptions,
-   architecture roles,
-   ecosystem classifications,
-   known relationships,
-   lifecycle hypotheses,
-   use-case classifications,
-   initial alternative sets,
-   reference architecture building blocks.

Curated data must be versioned and explicitly distinguishable from
measured ecosystem data.

The seed should expand over time into:

-   databases,
-   cloud services,
-   observability,
-   AI/LLM libraries,
-   agent frameworks,
-   security,
-   IaC,
-   CI/CD,
-   data engineering,
-   ML,
-   identity,
-   API tooling,
-   integration,
-   storage,
-   queues,
-   vector databases.

------------------------------------------------------------------------

## 16. Capability classification

Packages/frameworks should be mapped to the functions they provide.

Example:

``` text
axios
node-fetch
undici
native fetch
       ↓
Capability: HTTP Client
```

Another:

``` text
jsonwebtoken
jose
passport-jwt
       ↓
Capability: JWT / Token Processing
```

A technology may provide multiple capabilities.

Example:

``` text
lodash
├── collection manipulation
├── object utilities
├── functional utilities
└── debounce/throttle
```

But an individual enterprise application may only use one of those
capabilities.

That distinction should drive recommendations.

Capability inference can combine:

-   package metadata,
-   curated capability catalog,
-   imported functions,
-   README/documentation,
-   code semantics,
-   LLM classification,
-   internal usage evidence.

------------------------------------------------------------------------

## 17. OSS project health

Packages should connect to the projects that maintain them.

Assess signals such as:

-   last release,
-   release frequency,
-   commits,
-   active maintainers,
-   contributor concentration,
-   issue responsiveness,
-   PR responsiveness,
-   security response,
-   deprecation/archive state,
-   runtime support,
-   release stability.

A package can be **secure today but strategically non-viable**.

Example:

``` text
Package foo

Last release           4.2 years
Active maintainers     0–1
Adoption trend         declining
New project adoption   very low
Runtime compatibility  questionable
Known vulnerabilities  none

Viability              LOW
```

This is why StackGraph must not collapse viability into vulnerability
management.

------------------------------------------------------------------------

## 18. OSS adoption graph

Public repositories provide evidence of how technologies are actually
combined.

Possible observations:

``` text
OSSRepository USES Package
OSSRepository USES Framework
OSSRepository USES Runtime
OSSRepository DEPLOYS_WITH Platform
```

At scale, aggregate low-value repository edges into useful statistical
relationships:

``` text
Next.js
  COMMONLY_USED_WITH
Tailwind

repository_count
co_occurrence_rate
sample_size
time_window
confidence
trend
```

This supports:

-   ecosystem architecture comparison,
-   common technology combinations,
-   unusual enterprise patterns,
-   emerging reference stacks.

------------------------------------------------------------------------

## 19. Migration graph

The migration graph may become one of StackGraph's strongest proprietary
assets.

Observe public repository evolution:

``` text
Commit/time A:
technology X present

Commit/time B:
X removed
Y introduced
similar application behavior remains
```

Infer:

``` text
X MIGRATED_TO Y
```

Aggregate across many examples:

-   number of observed migrations,
-   direction,
-   time window,
-   runtime context,
-   files changed,
-   approximate LOC changed,
-   common API mappings,
-   common breakages,
-   migration complexity,
-   target satisfaction/retention where measurable.

A `MigrationPattern` should become a reusable object.

Example:

``` text
axios → fetch

Common transformations:
axios.get() → fetch()
response.data → response.json()
interceptors → wrapper/middleware
```

This becomes excellent context for a coding agent performing an approved
migration.

------------------------------------------------------------------------

## 20. Reference implementation graph

Some public repositories should be elevated above generic adoption
evidence.

A reference implementation demonstrates:

-   a capability,
-   an architecture pattern,
-   a technology combination,
-   a deployment pattern.

Possible scoring:

-   project maturity,
-   maintainer quality,
-   activity,
-   architecture clarity,
-   tests,
-   documentation,
-   security posture,
-   adoption.

The product should eventually answer:

> Show three high-quality reference architectures for rebuilding this
> service.

------------------------------------------------------------------------

## 21. Ecosystem trajectory

Technology lifecycle should include categories such as:

-   Emerging
-   Growing
-   Stable
-   Declining
-   Legacy
-   Abandoned
-   Experimental
-   Specialized

Do not rely solely on installed-base size.

Useful trajectory signals include:

-   new repositories selecting technology,
-   growth rate,
-   version upgrade velocity,
-   migration-in rate,
-   migration-out rate,
-   release activity,
-   satisfaction signals,
-   maintainer health.

An old technology may have enormous installed base while very few new
systems choose it.

------------------------------------------------------------------------

## 22. Internal estate + OSS comparison

Recommendations should combine three major evidence planes:

``` text
INTERNAL ESTATE
What does this company use?
What has already succeeded internally?
What are company standards?

+

OSS REFERENCE GRAPH
What is happening externally?
What alternatives are viable?
What migration evidence exists?

+

LOCAL CODE
What capability does this application actually need?
How deeply is the technology used?

=

DECISION
```

Example:

Internal estate:

``` text
HTTP client usage
axios          91 repos
request        24 repos
node-fetch     16 repos
native fetch    9 repos
custom HTTP     7 repos
```

OSS trajectory:

``` text
native fetch   strongly growing
undici         growing
axios          stable
node-fetch     declining
request        legacy
```

Enterprise standard:

``` text
Preferred: native fetch
```

Now the recommendation has internal, external, and local-code evidence.

------------------------------------------------------------------------

## 23. Viability intelligence

The primary conceptual metric is **software viability**.

A technology can be free from known vulnerabilities and still be a poor
strategic dependency.

### Technology viability dimensions

-   Supportability
-   Security
-   Maintenance health
-   Ecosystem health
-   Runtime compatibility
-   Functional fitness
-   Architecture fitness
-   Organizational alignment
-   Performance opportunity
-   Dependency complexity
-   Operational cost implications
-   Standardization opportunity
-   Modernization opportunity
-   Replaceability

Example:

``` text
Package: request

Security               82
Supportability          18
Ecosystem health        24
Performance             47
Org alignment           31
Replaceability          91

Overall viability       38

Recommendation:
REPLACE
```

------------------------------------------------------------------------

## 24. Application viability

Technology-level findings should roll upward into an application
profile.

Example dimensions:

-   overall viability,
-   security,
-   supportability,
-   dependency health,
-   runtime health,
-   architecture fitness,
-   deployment fitness,
-   cloud/platform fitness,
-   performance opportunity,
-   technology entropy,
-   business criticality,
-   modernization potential.

Example:

``` text
Billing Platform

Overall viability          58
Business criticality       Tier 1
Security                   81
Supportability             44
Architecture fitness       63
Deployment fitness         52
Dependency viability       67

Modernization priority     HIGH
```

------------------------------------------------------------------------

## 25. Recommendation taxonomy

Recommendations must use a controlled action vocabulary:

-   RETAIN
-   UPGRADE
-   REMOVE
-   REPLACE
-   CONSOLIDATE
-   REFACTOR
-   REBUILD
-   REPLATFORM
-   RETIRE
-   INVESTIGATE

Examples:

``` text
Unsupported runtime
→ UPGRADE

Unused dependency
→ REMOVE

Abandoned HTTP library
→ REPLACE

Five auth implementations
→ CONSOLIDATE

Legacy transformation service
→ REBUILD

VM-hosted stateless service
→ REPLATFORM
```

The best replacement for a dependency may be **no dependency**.

------------------------------------------------------------------------

## 26. Alternative recommendation engine

### Step 1 --- Determine capability actually used

Do not use package labels alone.

### Step 2 --- Generate candidates

Candidate sources:

-   organizational standards,
-   existing internal implementations,
-   public OSS graph,
-   package ecosystem,
-   native runtime/platform capabilities,
-   reference architectures.

### Step 3 --- Score candidate fitness

Dimensions may include:

-   functional fit,
-   runtime compatibility,
-   internal adoption,
-   ecosystem adoption,
-   maintenance health,
-   security,
-   performance potential,
-   architecture alignment,
-   migration ease,
-   dependency complexity,
-   migration risk.

### Step 4 --- Explain

Never return only:

> Use Y.

Return something like:

``` text
Recommended: Y
Confidence: HIGH

Why
- equivalent required capability
- supported on target runtime
- actively maintained
- already used in 73 internal repositories
- company standard
- lower dependency complexity

Migration
- 17 call sites
- 8 files
- estimated LOW complexity

Counter-signals
- retry semantics differ
- integration tests required
```

Counter-signals are important. Recommendations should not pretend
uncertainty does not exist.

------------------------------------------------------------------------

## 27. Performance and optimization intelligence

StackGraph should identify **potential** performance opportunities from
architecture/code patterns without claiming measured performance
improvements unless runtime evidence exists.

Example:

``` text
pricing-api
  → old Node runtime
  → multiple transformation packages
  → large serialization pipeline
```

Possible conclusion:

> High potential for performance optimization; benchmark recommended.

Later, observability integrations can validate:

-   latency,
-   CPU,
-   memory,
-   throughput,
-   error rate,
-   utilization,
-   cloud cost.

This creates:

``` text
CODE GRAPH
what is implemented

+
RUNTIME GRAPH
what actually executes

+
BUSINESS GRAPH
what matters

+
OSS REFERENCE GRAPH
what alternatives exist

=
MODERNIZATION INTELLIGENCE
```

------------------------------------------------------------------------

## 28. Internal reuse and consolidation

StackGraph should detect multiple implementations of the same
capability.

Example:

``` text
Capability: PDF Generation

Implementations:
- invoice-pdf
- claims-doc
- contract-renderer
- shared-document-service
```

Signals:

-   semantic similarity,
-   API similarity,
-   dependency similarity,
-   code similarity,
-   business usage,
-   internal adoption.

Possible recommendation:

> Consolidate three implementations onto the shared document service.

This is more valuable than package-level cleanup because it addresses
organizational architecture.

------------------------------------------------------------------------

## 29. Technology entropy

Define a measure of unnecessary technological variation.

Possible domain views:

``` text
Authentication       HIGH
Logging              HIGH
UI frameworks        MEDIUM
HTTP clients         HIGH
Observability        LOW
Python frameworks    MEDIUM
```

Track it over time.

Questions:

-   Is technology entropy increasing?
-   Which teams/apps are introducing new technology?
-   Are coding agents introducing one-off dependencies?
-   Which capabilities have the most duplicate implementations?
-   Where could standardization reduce support cost?

Entropy should not automatically mean "bad." Variation may be justified.
The product must expose evidence and context.

------------------------------------------------------------------------

## 30. Business impact propagation

This is a major differentiator from conventional developer tooling.

Example path:

``` text
Vulnerability
↑
Package
↑
Repository
↑
Application
↑
Business Capability
↑
Business Process
↑
Business Function
↑
Value Chain
```

Thus:

> Critical CVE in package X

can become:

> Potential exposure in the customer payment process supporting a Tier-1
> capability.

The same propagation applies to:

-   unsupported runtime,
-   abandoned package,
-   single-region deployment,
-   on-prem dependency,
-   obsolete framework,
-   unmaintained base image,
-   architecture concentration.

------------------------------------------------------------------------

## 31. Modernization prioritization

Modernization should be treated as a portfolio optimization problem.

Conceptually:

``` text
Priority
≈
Business Importance
× Viability Gap
× Modernization Opportunity
× Confidence
÷ Migration Effort
```

This is not necessarily the literal production formula.

Example:

``` text
1. Billing API
   Business impact    HIGH
   Viability          41
   Effort             MEDIUM
   Opportunity        HIGH

2. Customer Profile
   Business impact    HIGH
   Viability          58
   Effort             LOW
   Opportunity        HIGH

3. Legacy Reporting
   Business impact    LOW
   Viability          22
   Recommendation     RETIRE
```

Long-term executive question:

> Where should we spend the next \$10M of modernization investment?

------------------------------------------------------------------------

## 32. Business / value-chain mapping

Applications should map back to:

``` text
Value Chain
  → Business Function
    → Business Process
      → Business Capability
        → Application
```

Mappings may come from:

-   manual curation,
-   imported architecture data,
-   service catalog,
-   CMDB,
-   repository metadata,
-   naming conventions,
-   documentation,
-   inferred semantics,
-   LLM-assisted classification.

Inference must retain confidence and evidence.

The product should support estate views such as:

``` text
VALUE CHAIN                 VIABILITY

Acquire Customer              82
Quote                         76
Order                         71
Fulfill                       63
Invoice                       58
Collect Payment               79
Customer Support              67
```

------------------------------------------------------------------------

## 33. Evidence and explainability

A foundational requirement:

> **No material conclusion without evidence.**

Every important finding should be traceable.

Evidence classes:

### DECLARED

Explicitly present in configuration or manifest.

Examples:

-   package manifest,
-   Terraform,
-   Kubernetes YAML,
-   Dockerfile.

### OBSERVED

Actually referenced/used.

Examples:

-   AST import,
-   function call,
-   code reference,
-   runtime observation.

### INFERRED

Derived from multiple signals.

Examples:

-   likely application boundary,
-   business capability mapping,
-   modernization suitability.

### CURATED

Human-curated StackGraph knowledge seed.

### EXTERNAL_MEASURED

Measured from OSS/public ecosystem data.

Users must be able to ask:

> Why does StackGraph think this?

and receive the exact evidence path.

------------------------------------------------------------------------

## 34. Confidence

Confidence should exist at the fact, relationship, assessment, and
recommendation levels.

Example:

``` text
Deployment:
AWS ECS

Evidence:
infra/prod/main.tf

Assertion:
DECLARED

Confidence:
1.0
```

versus:

``` text
Business Capability:
Customer Profile Management

Evidence:
README + route names + service name

Assertion:
INFERRED

Confidence:
0.78
```

Recommendations should not conceal uncertainty.

------------------------------------------------------------------------

## 35. Temporal intelligence

Time must be first-class.

Track:

-   first seen,
-   last seen,
-   scan,
-   source version,
-   assessment validity,
-   recommendation state.

Questions:

-   What changed this week?
-   What new technologies appeared?
-   Which dependencies disappeared?
-   Did entropy increase?
-   Which applications improved viability?
-   Which new deployment patterns appeared?
-   What did coding agents introduce?
-   Which modernization recommendations were resolved?

This evolves StackGraph from a static catalog into a **software estate
observability platform**.

------------------------------------------------------------------------

## 36. Natural-language experience

The core interaction can be framed as:

> **Ask your software estate**

Example questions:

-   Which Tier-1 applications run unsupported Node versions?
-   What business processes depend on on-prem infrastructure?
-   Where are we duplicating authentication capabilities?
-   Which packages should we replace?
-   What are our largest modernization opportunities?
-   What new technologies appeared this month?
-   Why is Billing's viability score low?
-   What should we standardize?
-   Show applications indirectly dependent on package X.
-   What would prevent us standardizing on the current Node standard?
-   Which revenue-critical applications are single-region?
-   Which internal components could be reused rather than rebuilt?

Natural language should invoke deterministic graph/SQL tools wherever
evidence exists. The model should explain and reason over results, not
invent estate facts from pretrained knowledge.

------------------------------------------------------------------------

## 37. Core product experiences

### 37.1 Software Estate

Portfolio overview:

-   applications,
-   services,
-   repositories,
-   languages,
-   runtimes,
-   frameworks,
-   cloud/on-prem distribution,
-   major technologies,
-   lifecycle distribution,
-   viability distribution.

### 37.2 Application Explorer

For one application:

-   business context,
-   repositories,
-   services,
-   dependencies,
-   runtime,
-   frameworks,
-   deployment topology,
-   infrastructure,
-   vulnerabilities,
-   viability profile,
-   modernization recommendations,
-   evidence.

### 37.3 Technology Explorer

For a technology/package/framework:

-   internal usage,
-   applications/business processes affected,
-   versions,
-   dependency paths,
-   OSS health,
-   ecosystem trajectory,
-   internal standards,
-   alternatives,
-   migration evidence.

### 37.4 Deployment Explorer

Views:

-   cloud vs on-prem,
-   provider,
-   region,
-   compute model,
-   runtime,
-   environment,
-   declared/observed drift,
-   platform modernization candidates.

### 37.5 Viability Dashboard

Portfolio view of:

-   low-supportability technologies,
-   aging runtimes,
-   abandoned dependencies,
-   security issues,
-   declining ecosystems,
-   architecture misalignment,
-   deployment fitness,
-   modernization potential.

### 37.6 Modernization Portfolio

Ranked opportunities:

-   action,
-   rationale,
-   business impact,
-   viability gap,
-   benefit,
-   effort,
-   confidence,
-   migration references.

### 37.7 Ask Your Estate

Natural-language investigation across all layers.

------------------------------------------------------------------------

## 38. Recommendation → execution

Long term:

``` text
OBSERVE
↓
UNDERSTAND
↓
ASSESS
↓
RECOMMEND
↓
APPROVE
↓
GENERATE CHANGE
↓
PR
↓
VERIFY
↓
OBSERVE
```

Example:

``` text
Recommendation:
Replace package X with Y

[View evidence]
[View internal examples]
[View OSS migration examples]
[Estimate migration]
[Generate migration plan]
[Generate PR]
```

Codex or another coding agent can become the **execution plane**.

StackGraph remains the **intelligence and control plane**.

This separation is strategically important: StackGraph decides *what
should change and why*; coding agents implement approved changes.

------------------------------------------------------------------------

## 39. Scanner / reasoning separation

A key engineering principle:

``` text
SCANNERS
What can we prove?

↓
GRAPH
What is connected?

↓
ANALYTICS
What does the evidence imply?

↓
LLM
What does it mean?

↓
RECOMMENDATION
What should we do?

↓
AGENT
Make the approved change.
```

Rules:

-   scanners do not make modernization recommendations,
-   LLMs do not manufacture estate facts,
-   assessments retain their inputs,
-   recommendations retain evidence and counter-signals,
-   external OSS claims retain provenance.

This prevents StackGraph from becoming an opaque LLM heuristic system.

------------------------------------------------------------------------

## 40. Storage / graph strategy

The chosen foundation is:

-   PostgreSQL as authoritative system of record,
-   Apache AGE for graph traversal.

Most activity is read-heavy.

Bulk writes occur during:

-   initial repository scans,
-   enrichment,
-   rescans,
-   OSS hydration,
-   external signal refresh.

Recommended flow:

``` text
scan
→ normalized facts
→ bulk relational writes
→ relationship/entity reconciliation
→ AGE projection
→ assessments
→ recommendations
```

Avoid per-import/per-file graph writes during scanning.

------------------------------------------------------------------------

## 41. External enrichment philosophy

StackGraph should integrate existing high-quality sources rather than
rebuild every adjacent product.

Potential enrichment:

-   OSV for vulnerabilities,
-   deps.dev for package/dependency metadata,
-   OpenSSF for supply-chain/security posture,
-   package registries,
-   GitHub public metadata,
-   official project lifecycle/support sources.

Later:

-   AWS/Azure/GCP,
-   Kubernetes,
-   Datadog/New Relic/OpenTelemetry,
-   service catalogs,
-   CMDB,
-   cloud cost,
-   performance telemetry.

------------------------------------------------------------------------

## 42. Security intelligence

Security remains important but should be contextualized.

A finding should answer:

-   Is the package vulnerable?
-   Is the affected version actually used?
-   Is it direct or transitive?
-   Is the vulnerable component reachable/used where determinable?
-   Which applications depend on it?
-   Which business processes are exposed?
-   Is an upgrade available?
-   Is replacement strategically better than upgrade?
-   Is the project itself viable?

The product should avoid reducing modernization to CVE remediation.

------------------------------------------------------------------------

## 43. Native capability replacement

A recurring modernization pattern is that runtimes absorb functionality
previously requiring packages.

Examples include:

-   native `fetch`,
-   native test runners,
-   improved standard HTTP routing,
-   native CSS capabilities.

The alternative engine must therefore include:

> **REMOVE dependency and use platform-native capability**

as a first-class recommendation.

------------------------------------------------------------------------

## 44. Architecture pattern recognition

StackGraph should eventually identify reference architecture patterns
from combinations of technologies.

Example:

``` text
Modern React Application

React
+
Next.js / router
+
server-state library
+
runtime validation
+
CSS/component system
+
unit tests
+
browser tests
```

Another:

``` text
Event-driven Java Service

Spring Boot
+
Kafka
+
schema/contract
+
PostgreSQL
+
Kubernetes
```

The product can compare enterprise applications to relevant reference
patterns and identify:

-   unusual technology choices,
-   missing standard components,
-   legacy components,
-   opportunities to simplify.

------------------------------------------------------------------------

## 45. Commonly-confused concepts

The knowledge layer should explicitly protect the recommendation engine
from category mistakes.

Examples:

-   server state ≠ client state,
-   API gateway ≠ service mesh,
-   message broker ≠ durable event log,
-   UI library ≠ meta-framework,
-   ORM ≠ database,
-   runtime ≠ web framework,
-   stream processing ≠ event transport.

This can be encoded as taxonomy constraints or explicit semantic
relationships.

------------------------------------------------------------------------

## 46. Initial MVP

Be aggressive about scope.

### V0 --- prove discovery and graph value

Support:

-   GitHub
-   TypeScript / JavaScript
-   Python
-   Docker
-   basic Terraform
-   basic Kubernetes
-   PostgreSQL
-   Apache AGE
-   OSV/dependency enrichment
-   curated OSS seed

Deliver:

1.  Software Estate
2.  Application Explorer
3.  Technology Explorer
4.  Viability Dashboard
5.  Ask Your Estate

### V1

Add:

-   business process/capability mapping,
-   richer deployment footprint,
-   alternative recommendations,
-   public OSS reference graph,
-   technology entropy,
-   internal reuse/consolidation recommendations,
-   modernization ranking,
-   migration graph.

### V2

Add live operational integrations:

-   AWS/Azure/GCP
-   Kubernetes
-   observability
-   CMDB/service catalog
-   cloud cost
-   runtime performance

Then compare declared architecture with observed architecture.

------------------------------------------------------------------------

## 47. Explicit non-goals for initial versions

StackGraph is not initially intended to be:

-   a full static-analysis replacement,
-   an IDE code-quality tool,
-   an exhaustive source-code knowledge graph,
-   a SIEM,
-   an APM product,
-   a cloud management platform,
-   a complete CMDB replacement,
-   an autonomous code-modification system,
-   a perfect business-process discovery system,
-   a crawler cloning all public GitHub repositories.

It should integrate with adjacent systems where appropriate.

------------------------------------------------------------------------

## 48. Suggested implementation stack

A pragmatic prototype:

``` text
Frontend
Next.js / TypeScript

API
FastAPI or TypeScript

Database
PostgreSQL

Graph
Apache AGE

Workers
Python

Queue
Postgres initially

Parsing
Tree-sitter
ecosystem-specific parsers
IaC parsers

External intelligence
GitHub
OSV
deps.dev
OpenSSF
package registries

Reasoning
LLM + deterministic SQL/graph tools

Source access
GitHub App with minimal read rights
```

------------------------------------------------------------------------

## 49. Success criteria for the first real pilot

The first milestone should not be "we scanned 100 repositories."

A better test:

> Connect a GitHub organization with 100+ repositories and, within
> roughly 20 minutes, identify at least five material facts or
> opportunities about the software estate that engineering leadership
> did not already know.

Examples:

-   unsupported runtimes,
-   abandoned dependencies actually used in production code,
-   duplicate capability implementations,
-   applications suitable for straightforward platform modernization,
-   Tier-1 processes dependent on aging/on-prem technology,
-   technology introduced outside organizational standards,
-   unused or removable dependencies,
-   internal reusable components that could replace duplicate
    implementations,
-   high-potential performance modernization candidates.

The "I didn't know that" reaction is the early product signal.

------------------------------------------------------------------------

## 50. Strategic moat

The moat is unlikely to be repository scanning alone.

Scanning is necessary infrastructure and can be reproduced.

The stronger compounding assets are:

### 50.1 Enterprise software graph

A continuously refreshed model of what an organization actually has and
how it connects to business value.

### 50.2 OSS reference graph

A normalized external model of technology purpose, dependencies,
ecosystem health, alternatives, adoption and trajectory.

### 50.3 Migration graph

Observed evidence of how real projects move between technologies and the
cost/patterns of those migrations.

### 50.4 Capability graph

A semantic model that allows StackGraph to reason about *function*
rather than merely package identity.

### 50.5 Internal reuse graph

Knowledge of which capabilities already have proven implementations
inside an organization.

### 50.6 Outcome feedback

Over time:

``` text
recommendation
→ accepted/rejected
→ migration performed
→ rescan
→ observed outcome
```

This can improve recommendation quality.

------------------------------------------------------------------------

## 51. Product positioning

Avoid positioning StackGraph as:

> "AI that scans GitHub for vulnerabilities."

That puts the product into a crowded security category and dramatically
understates the opportunity.

A stronger framing:

> **StackGraph is the intelligence layer for understanding and
> modernizing an enterprise software estate.**

Or:

> **Know what your software estate is made of, what it supports, where
> it runs, whether it is still viable, and what should change next.**

The emergence of coding agents strengthens the urgency:

> Software creation is becoming dramatically easier. Understanding the
> software estate is not.

------------------------------------------------------------------------

## 52. Final product model

The product ultimately connects:

``` text
BUSINESS
Value Chain
Function
Process
Capability

↓ enabled by

APPLICATION
Application
Service
Component
API

↓ implemented by

CODE
Repository
Language
Framework
Package
Dependency

↓ deployed as

DEPLOYMENT
Environment
Compute
Container
Runtime
Cloud / On-Prem
Region
Infrastructure

↔ compared against

OSS REFERENCE INTELLIGENCE
Projects
Packages
Versions
Capabilities
Dependencies
Maintainers
Releases
Adoption
Migrations
Alternatives
Reference Implementations
Vulnerabilities

↓ assessed by

VIABILITY INTELLIGENCE
Supportability
Security
Maintenance
Ecosystem
Runtime fit
Architecture fit
Org alignment
Performance opportunity
Replaceability
Deployment fitness

↓ converted into

MODERNIZATION INTELLIGENCE
Retain
Upgrade
Remove
Replace
Consolidate
Refactor
Rebuild
Replatform
Retire
Investigate

↓ optionally executed by

CODING AGENTS
Plan
Change
PR
Verify
Rescan
```

That is the foundational StackGraph product thesis: **an
evidence-backed, continuously updated map of enterprise software and its
external technology context, capable of turning visibility into
prioritized modernization decisions and eventually executable change.**
