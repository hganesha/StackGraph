# StackGraph Phase 2 Improvements

## 1. Phase 2 Vision

StackGraph should evolve from an enterprise estate discovery and
recommendation platform into a **semantic control plane for enterprise
change**.

The target lifecycle is:

**Discover → Understand → Recommend → Compile → Simulate → Govern →
Execute → Verify → Learn**

The core principle is:

> **Free-form intent. Constrained semantics. Deterministic execution.**

StackGraph owns the enterprise nouns, valid predicates, relationships,
evidence, and facts. AI assists with interpretation and explanation, but
does not invent enterprise entities or determine blast radius.

The longer-term goal is an **Enterprise Change Compiler**: a
platform-agnostic capability that compiles human or AI intent against
the actual enterprise estate, validates whether the proposed action is
meaningful, simulates its consequences, and produces evidence-backed
execution constraints before changes occur.

------------------------------------------------------------------------

## 2. Product Positioning

Phase 2 should not position StackGraph as merely:

-   an enterprise knowledge graph;
-   a dependency graph;
-   an AI context provider;
-   a blast-radius analyzer;
-   a modernization recommendation engine; or
-   another copilot/agent platform.

Those capabilities are individually useful but increasingly
commoditized.

The differentiated product thesis is:

> **StackGraph determines which enterprise changes are semantically
> valid, simulates their consequences using verified estate knowledge,
> and provides a deterministic control boundary between AI intent and
> enterprise action.**

The graph is the substrate, not the final product.

------------------------------------------------------------------------

## 3. Enterprise Change Compiler

Introduce a first-class change compilation pipeline:

``` text
Human / Agent Intent
        ↓
Intent Interpretation
        ↓
Enterprise Action Grammar
        ↓
Entity Resolution
        ↓
Semantic Validation
        ↓
Mutation IR
        ↓
Impact Simulation
        ↓
Policy / Risk Evaluation
        ↓
Execution + Verification Plan
```

Anything above the Mutation IR may use probabilistic AI.

Anything below the Mutation IR must be deterministic and
evidence-backed.

An invalid request such as:

``` text
Plant a tree in my garden
```

must fail grounding because neither the predicate nor subject maps to a
valid StackGraph enterprise action. No simulation should occur.

------------------------------------------------------------------------

## 4. Enterprise Action Grammar

StackGraph should dynamically expose the valid language of change based
on the enterprise estate.

Initial grammar:

``` text
<Action> <Subject> [<Target State>] [<Scope>]
```

Initial predicates should remain deliberately bounded:

-   `UPGRADE`
-   `REPLACE`
-   `REMOVE`
-   `DEPRECATE`
-   `MIGRATE`
-   `MOVE`

Initial subject types:

-   Package
-   Runtime
-   Framework
-   API
-   Database
-   Service

Examples:

``` text
UPGRADE Package → Version
REPLACE Package → Package
REMOVE Package
DEPRECATE API
MIGRATE Database → Platform
MOVE Service → Platform
```

Avoid broad predicates such as `CHANGE`, `IMPROVE`, or `TRANSFORM` until
their semantics can be deterministic.

### Deriving the grammar

Do not make the action vocabulary purely manually administered.

Prefer:

``` text
Connectors discover nouns
        ↓
Ontology determines applicable verbs
        ↓
Authoritative providers determine valid target states
        ↓
StackGraph determines valid scope and impact
```

Example:

``` text
Newtonsoft.Json
type = Package
ecosystem = NuGet
        ↓
Package ontology
        ↓
NuGet semantic provider
        ↓
UPGRADE / DOWNGRADE / REMOVE / REPLACE
        ↓
valid target versions
```

------------------------------------------------------------------------

## 5. First-Class Contextual Command Experience

Do not make an unconstrained chatbot the primary simulator interface.

The preferred UX is a contextual command surface combining IDE
autocomplete, Spotlight-style discovery, and Terraform-plan-like review.

Typing:

``` text
upgrade
```

should surface only estate-backed candidates, for example:

``` text
Library       2,847 detected
Runtime          17 detected
Framework         8 detected
Database          6 detected
Platform          9 detected
```

Typing:

``` text
upgrade newt
```

should resolve against canonical StackGraph entities:

``` text
Newtonsoft.Json
Newtonsoft.Json.Schema
Newtonsoft.Json.Bson
```

Selecting an entity converts the interaction into deterministic UI
tokens:

``` text
[ Upgrade ] [ Newtonsoft.Json ] [ → target ]
```

Autocomplete candidates must originate from StackGraph evidence rather
than LLM generation.

### Resolution states

Expose three explicit states:

-   **Resolved** --- exact canonical graph identity.
-   **Inferred** --- multiple plausible graph entities; user resolution
    required.
-   **Unresolved** --- no enterprise entity exists.

Material unresolved components must block simulation.

------------------------------------------------------------------------

## 6. Contextual Target Autofill

After resolving a subject, StackGraph should determine legal target
states.

Example:

``` text
Upgrade Newtonsoft.Json → [target]

Current estate
10.x    21 repos
11.x    47 repos
12.x   143 repos
13.x   171 repos

Suggested targets
13.x    Consolidate estate
14.x    Candidate upgrade
Latest  Resolve at execution time
```

Target suggestions may use:

-   observed estate versions;
-   package/runtime registries;
-   platform policies;
-   compatibility metadata;
-   organizational standards;
-   lifecycle/support information.

The selected target must still resolve to a deterministic state
transition before simulation.

------------------------------------------------------------------------

## 7. Alternative Simulation Entry Points

Natural-language entry should be only one mutation compiler.

Support multiple sources:

``` text
Natural language ─────┐
Autocomplete ─────────┤
Recommendation ───────┤
GitHub PR ────────────┤
Change ticket ────────┼──→ Mutation IR → Simulator
Architecture change ──┤
Agent proposal ───────┤
API call ─────────────┘
```

### PR/change-set simulation

A PR may automatically compile into:

``` text
ChangeSet
 ├── Upgrade(Package: Newtonsoft.Json, 12.0.3 → 14.0.1)
 ├── Upgrade(Runtime: .NET, 6 → 8)
 ├── Modify(API: /customer/address)
 └── Modify(Config: AUTH_MODE)
```

This is preferable to requiring users to manually describe changes
StackGraph can already observe.

------------------------------------------------------------------------

## 8. Suggested Changes

Avoid the blank-page problem.

StackGraph should proactively surface estate-backed changes worth
simulating:

``` text
HIGH  Internal API /customer/v1 scheduled for retirement
      31 known consumers

MED   React 19 adoption opportunity
      143 repositories on React 18

MED   PostgreSQL estate fragmented across four major versions
      37 databases
```

Sources may include:

-   StackGraph recommendations;
-   lifecycle events;
-   deprecated APIs;
-   version fragmentation;
-   unsupported runtimes;
-   security findings;
-   architecture policy violations;
-   pending PRs/change requests.

Every actionable recommendation should support **Simulate
recommendation**.

------------------------------------------------------------------------

## 9. Mutation Intermediate Representation

Introduce a platform-neutral `Mutation` as the hard contract accepted by
the simulator.

Suggested model:

``` text
Mutation
--------
id
predicate
subject
before
after
scope
constraints
provenance
```

Example:

``` json
{
  "predicate": "UPGRADE",
  "subject": {
    "entityId": "pkg:nuget/Newtonsoft.Json"
  },
  "before": {
    "version": "<13"
  },
  "after": {
    "version": "14"
  },
  "scope": {
    "type": "ESTATE"
  }
}
```

Multiple mutations form a `ChangeSet`.

Natural language must never be consumed directly by the deterministic
impact engine.

------------------------------------------------------------------------

## 10. Canonical Entity Identity

Entity identity becomes safety-critical in Phase 2.

Every simulatable entity should have a stable canonical identity, for
example:

``` text
pkg:nuget/Newtonsoft.Json
runtime:dotnet
github:org/payments-api
service:payments/payment-authorization
```

Autocomplete, mutation compilation, traversal, findings, and evidence
must operate on canonical IDs rather than fuzzy display labels.

Recommended resolution order:

1.  authoritative external ID;
2.  exact canonical identifier;
3.  known alias;
4.  structural match;
5.  semantic candidate;
6.  LLM-assisted candidate generation.

Low-confidence matches must never silently enter deterministic
simulation.

Suggested quality goals:

``` text
Canonical entity precision       >99%
Ambiguity surfaced               100%
Relationship provenance          ~100% for simulation edges
Silent unresolved guesses         0%
```

------------------------------------------------------------------------

## 11. Backend Data Model Changes

Phase 2 requires backend persistence/model changes, not just UI/service
changes.

Core additions:

``` text
Entity
EntityType
Relationship

ActionType
ActionCapability
ImpactPolicy

Mutation
ChangeSet
SimulationRun
Finding
EvidenceRef
```

### ActionCapability

Suggested fields:

``` text
entity_type
predicate
target_schema
validation_rules
semantic_provider
```

This answers deterministically:

-   what can be upgraded?
-   what actions apply to an API?
-   does a target state need to be supplied?
-   what constitutes a valid transition?

### ImpactPolicy

Suggested fields:

``` text
entity_type
predicate
edge_type
direction
max_depth
weight
stop_condition
classification
```

Classifications may include:

-   direct impact;
-   transitive impact;
-   contextual;
-   stop;
-   informational.

### Persistence strategy

Persist:

-   saved mutations;
-   submitted/executed ChangeSets;
-   SimulationRuns;
-   Findings;
-   evidence references;
-   actual outcomes.

Do **not** clone the complete enterprise graph for each simulation.

------------------------------------------------------------------------

## 12. Impact Traversal Engine

Blast radius must not mean generic `N-hop` graph traversal.

Impact traversal should depend on:

``` text
predicate + subject type + impact policy
```

For example, a package upgrade might use:

``` text
DIRECT
Package <-USES- Repository

TRANSITIVE
Repository <-BUILT_FROM- Application
Application <-DEPENDS_ON- Application
Application -EXPOSES-> API
Application <-ENABLED_BY- BusinessCapability

STOP
Owner
Documentation
Tag

CONTEXT
Team
CostCenter
Lifecycle
```

An API removal would use a different traversal policy.

This turns StackGraph from a descriptive graph into a **change-aware
enterprise graph**.

------------------------------------------------------------------------

## 13. Hypothetical Estate State

Simulation requires explicit before/after reasoning.

Conceptually:

``` text
Base estate G
    +
Mutation Δ
    =
Hypothetical estate G'
```

Implement `G'` as a virtual overlay/diff rather than a full persisted
graph clone.

The simulator can then evaluate:

``` text
diff(G, G')
```

This enables more than blast radius:

-   newly invalid dependencies;
-   resolved or introduced policy violations;
-   compatibility failures;
-   lifecycle/support changes;
-   vulnerabilities removed or introduced;
-   new contradictions;
-   newly satisfied enterprise standards.

------------------------------------------------------------------------

## 14. Separate Deterministic Findings from AI Interpretation

The simulation engine should produce facts such as:

``` text
Direct repositories             382
Applications                     71
Business capabilities             8
Public APIs                      12
Dependency constraint conflicts  23
Missing tests                    17
Unsupported runtimes affected     3
```

Each finding should include:

``` text
fact
evidence
rule
confidence
provenance
```

AI may then produce:

-   risk explanation;
-   summary;
-   rollout recommendation;
-   verification plan;
-   remediation suggestions.

AI must not manufacture the underlying impact graph.

Suggested result structure:

``` text
Simulation
 ├── Findings[]
 ├── ImpactGraph
 ├── Evidence[]
 └── Interpretation
      ├── risk
      ├── explanation
      ├── rollout
      └── verification
```

------------------------------------------------------------------------

## 15. Context API

Add an API layer close to StackGraph rather than exposing the underlying
graph store directly to clients.

Potential endpoints:

``` text
GET  /action-types
GET  /action-types/{predicate}/subjects
GET  /entities/{id}/valid-targets
GET  /entities/{id}/scopes

POST /mutations/compile
POST /mutations/validate
POST /simulations
GET  /simulations/{id}
```

This allows the same semantic layer to support:

-   StackGraph UI;
-   IDE extensions;
-   GitHub workflows;
-   CI/CD;
-   ServiceNow/change systems;
-   AI agents;
-   Harness Factory;
-   third-party APIs.

------------------------------------------------------------------------

## 16. Recommendation Engine Integration

Extend the recommendation schema with a proposed mutation or ChangeSet
whenever possible.

Instead of only:

``` text
Upgrade applications to Java 21
```

emit:

``` text
Recommendation
 ├── explanation
 ├── evidence
 ├── confidence
 └── proposedChangeSet
```

This creates:

``` text
Recommendation
      ↓
Simulate
      ↓
Govern
      ↓
Execute
      ↓
Verify
```

The recommendation engine therefore becomes an upstream producer of
deterministic change proposals.

------------------------------------------------------------------------

# Area Improvements

## 17. Investment Principle

Do not attempt to become best-in-class in every enterprise tooling
category.

Use this rule:

> **Invest deeply when the capability materially increases the fidelity
> of the Enterprise Change Compiler. Integrate when it primarily
> recreates an established specialist category.**

------------------------------------------------------------------------

## 18. Entity Resolution --- Very High Priority

Entity resolution becomes foundational because incorrect identity
produces incorrect blast radius.

Improvements:

-   canonical ID enforcement;
-   alias registries;
-   authoritative connector identifiers;
-   deterministic resolution before semantic matching;
-   ambiguity detection;
-   confidence scoring;
-   explicit unresolved states;
-   duplicate/entity reconciliation;
-   resolution provenance.

No unresolved entity should silently become a Mutation subject.

------------------------------------------------------------------------

## 19. Relationship Provenance --- Very High Priority

Prefer fewer trustworthy edges over a huge noisy graph.

Every relationship relevant to simulation should ideally answer:

``` text
Why does StackGraph believe this relationship exists?
Where was it observed?
When was it last observed?
How confident are we?
What evidence corroborates it?
```

Example:

``` text
PaymentService
DEPENDS_ON
CustomerService

Evidence
✓ generated OpenAPI client
✓ endpoint reference in source
✓ runtime traffic
✓ architecture documentation
```

Relationship provenance directly affects simulation trust.

------------------------------------------------------------------------

## 20. Cross-Repository Relationships --- High Priority

StackGraph should become strong at relationships spanning repositories
because enterprise change rarely respects repository boundaries.

Improve:

-   shared libraries;
-   API clients;
-   generated artifacts;
-   shared schemas;
-   build dependencies;
-   CI/CD relationships;
-   service-to-repository mappings;
-   transitive dependencies.

Do not necessarily compete with specialist AST/code graph products.
Consume their output where appropriate and connect it to the broader
estate.

------------------------------------------------------------------------

## 21. Package, Runtime, and Framework Intelligence --- High Priority

This area is directly relevant to deterministic upgrades and
modernization.

Improve knowledge of:

-   observed versions;
-   version ranges;
-   dependency constraints;
-   supported versions;
-   compatibility;
-   runtime/framework relationships;
-   organizational standards;
-   lifecycle status;
-   migration paths.

Semantic providers should be pluggable by ecosystem.

------------------------------------------------------------------------

## 22. Business Capability Mapping --- Very High Priority

This is an important differentiator.

Extend relationships beyond technical topology:

``` text
Repository
 ↓
Application
 ↓
Service
 ↓
Business System
 ↓
Business Capability
 ↓
Business Process
 ↓
Criticality
 ↓
Regulatory / Policy Obligation
```

A blast radius of `73 repositories` is much less meaningful than:

> Payment Authorization, a Tier-0 business capability, is affected.

Business context should influence risk and governance decisions.

------------------------------------------------------------------------

## 23. Data Lineage --- High Priority

AI-heavy enterprises increasingly depend on data propagation.

StackGraph should eventually understand:

``` text
Column
 ↓
Table
 ↓
Pipeline
 ↓
Lakehouse/Warehouse
 ↓
Feature
 ↓
Model
 ↓
Agent
 ↓
API
 ↓
Business Process
```

This enables simulation of schema changes, dataset migration, field
removal, and AI context changes.

Prefer integration with existing lineage systems where available while
normalizing the relationships into StackGraph.

------------------------------------------------------------------------

## 24. Service Dependency Graph --- High Priority

Strengthen service-to-service dependencies using multiple sources:

-   source code;
-   API definitions;
-   service catalogs;
-   runtime telemetry;
-   deployment configuration;
-   architecture metadata.

Runtime evidence should corroborate static relationships rather than
requiring StackGraph to become a full observability platform.

------------------------------------------------------------------------

## 25. Infrastructure Topology --- Medium Priority / Integrate

Infrastructure context matters to blast radius but StackGraph should not
attempt to replace infrastructure management or observability products.

Ingest and normalize:

-   workloads;
-   clusters;
-   cloud resources;
-   deployment targets;
-   regions;
-   environments;
-   networking relationships;
-   infrastructure-as-code mappings.

Use external authoritative systems where possible.

------------------------------------------------------------------------

## 26. Observability --- Integrate Rather Than Rebuild

Do not build another Datadog-style platform.

Consume telemetry to:

-   validate dependencies;
-   detect actual traffic;
-   observe failures after change;
-   verify predictions;
-   establish runtime criticality.

StackGraph's job is to correlate runtime evidence with the enterprise
semantic graph.

------------------------------------------------------------------------

## 27. Vulnerability Intelligence --- Consume Rather Than Rebuild

Do not build another Snyk-style vulnerability database.

Consume vulnerability/security findings and connect them to:

-   canonical packages;
-   applications;
-   services;
-   business capabilities;
-   recommendations;
-   proposed mutations.

Security findings become another input into the Change Compiler.

------------------------------------------------------------------------

## 28. Code Intelligence --- Strong Enough, Not the Primary Moat

Do not attempt to outbuild specialist code-property-graph and
semantic-code-analysis vendors unless a missing capability directly
blocks StackGraph.

StackGraph should be able to consume relationships such as:

``` text
method → calls → method
code → accesses → table
repository → exposes → API
```

Its differentiated value is connecting these relationships to the
broader enterprise estate.

------------------------------------------------------------------------

# Enterprise Change Memory

## 29. Change History --- Very High Priority

Start capturing not just what exists, but:

``` text
What changed?
What happened afterward?
```

Introduce an `ObservedMutation` model:

``` text
predicate
subject
before
after
scope
observed_impact
unexpected_impact
successful
rollback
evidence
```

Potential sources:

-   Git commits;
-   PRs;
-   dependency changes;
-   deployment history;
-   configuration changes;
-   change tickets;
-   incidents;
-   rollbacks;
-   postmortems.

------------------------------------------------------------------------

## 30. Predicted vs. Actual Impact

For every meaningful simulated/executed change, capture:

``` text
Graph state before
        ↓
Predicted impact
        ↓
Execution
        ↓
Actual impact
        ↓
Incidents / interventions
        ↓
Resolution
```

This allows StackGraph to learn which graph paths are actually
predictive.

Eventually the platform can report:

``` text
142 similar historical changes

119 successful
18 required intervention
5 rolled back

Strongest failure predictors
Runtime mismatch           7.8×
High schema fan-out        4.1×
Tier-0 dependency          3.7×
Low test coverage          2.9×
```

This organizational change memory may become a significant long-term
moat.

------------------------------------------------------------------------

## 31. AI Dependency Graph

Extend the enterprise dependency model to include AI-specific
components:

``` text
Application
 ↓
Agent
 ↓
Harness
 ↓
Model
 ↓
Prompt / Instruction Set
 ↓
Context Source
 ↓
Tool
 ↓
API
 ↓
Dataset
 ↓
Business Capability
```

This should answer questions such as:

-   which business processes depend on a particular model?
-   which agents can indirectly modify production?
-   which AI systems consume a specific dataset?
-   what happens if a model/provider/tool is removed?
-   which workflows depend on stale or unsupported context?

This becomes an AI supply-chain graph rather than merely an AI
inventory.

------------------------------------------------------------------------

## 32. Enterprise Assumption Registry

Extract and maintain assumptions embedded across:

-   code;
-   architecture;
-   documentation;
-   configuration;
-   data;
-   agent instructions;
-   historical trajectories.

Examples:

``` text
Customer IDs are globally unique.
OrdersDB is authoritative.
API responses are backward compatible.
Service X owns customer identity.
```

Store:

``` text
assumption
supporting evidence
contradicting evidence
confidence
dependent assets
dependent AI workflows
last verified
```

Detect assumption drift because an AI acting correctly against an
obsolete assumption can still cause harmful enterprise outcomes.

------------------------------------------------------------------------

## 33. Enterprise Contradiction Engine

Detect where enterprise sources disagree.

Examples:

``` text
Code          Node 18
Docker        Node 20
Documentation Node 16
Policy        Node 22
```

or:

``` text
Architecture:
PaymentsService owns payment processing.

Observed estate:
17 repositories independently implement payment logic.
```

or:

``` text
AI context:
OrdersDB is authoritative.

Estate:
OrderService migrated to LedgerDB.
```

StackGraph does not need to immediately determine truth. It should
surface the conflict, evidence, confidence, and affected dependencies.

------------------------------------------------------------------------

# Agent Control Plane

## 34. AI Permission / Capability Compiler

Longer term, extend the Change Compiler into an AI capability boundary.

Instead of static RBAC alone:

``` text
objective
+ environment
+ estate context
+ risk
+ evidence
→ executable capability envelope
```

Example:

``` text
Agent: ProductionIncidentResolver

READ
logs
metrics
deployment history

EXECUTE
restart_service
rollback_deployment

CONDITIONAL
modify_config when environment != production

PROHIBITED
delete_database
modify_identity_policy

ESCALATE
blast radius > threshold
confidence < threshold
Tier-0 capability affected
```

This allows StackGraph to mediate actions from arbitrary
agents/platforms.

------------------------------------------------------------------------

## 35. Enterprise AI Flight Recorder

Capture semantic execution history:

``` text
Objective
 ↓
Context retrieved
 ↓
Evidence considered
 ↓
Tools available
 ↓
Tool calls
 ↓
Decisions
 ↓
Actions
 ↓
Assets affected
 ↓
Verification
 ↓
Outcome
```

The important feature is cross-system reconstruction rather than basic
logging.

Connect:

``` text
proposed mutation
→ simulation
→ approval
→ code/config change
→ deployment
→ telemetry
→ incident
→ rollback
```

This supports auditability and provides training/evaluation evidence for
future harness improvements.

------------------------------------------------------------------------

## 36. Enterprise AI Immune System --- Longer-Term

Use the estate and Change Compiler to generate adversarial scenarios for
agents/harnesses:

-   stale context;
-   conflicting documentation;
-   partial tool outages;
-   malformed API responses;
-   unexpected schema changes;
-   malicious repository content;
-   conflicting concurrent agent actions;
-   topology differing from documentation.

Evaluate harnesses against these scenarios and feed failures into the
Harness Factory:

``` text
failure
 ↓
diagnosis
 ↓
harness mutation
 ↓
simulation
 ↓
evaluation
 ↓
champion/challenger promotion
```

This should remain a later-stage capability after deterministic
simulation is mature.

------------------------------------------------------------------------

# Architecture

## 37. Proposed StackGraph Phase 2 Structure

``` text
stackgraph/
│
├── domain/
│   ├── entities/
│   ├── relationships/
│   ├── actions/
│   │   ├── predicates
│   │   ├── capabilities
│   │   └── target-schema
│   ├── mutations/
│   │   ├── mutation
│   │   ├── changeset
│   │   └── validation
│   └── simulation/
│       ├── impact-policy
│       ├── finding
│       └── simulation-result
│
├── services/
│   ├── resolver/
│   ├── recommendation/
│   ├── action-context/
│   ├── mutation-compiler/
│   └── impact-simulator/
│
├── graph/
│   ├── queries/
│   └── simulation/
│       ├── impact-traversal
│       └── overlay
│
└── api/
    ├── entities/
    ├── recommendations/
    ├── actions/
    ├── mutations/
    └── simulations/
```

This is conceptual; adapt to the existing StackGraph repository
structure rather than forcing a large reorganization solely to match
these names.

------------------------------------------------------------------------

# Recommended Delivery Sequence

## 38. Phase 2A --- Deterministic Foundation

Build first:

1.  canonical entity identity hardening;
2.  entity-resolution confidence and ambiguity handling;
3.  relationship provenance improvements;
4.  bounded action ontology;
5.  `ActionCapability`;
6.  Mutation IR and ChangeSet;
7.  mutation validation;
8.  initial Context API.

Success criterion:

> StackGraph can deterministically compile a supported user or API
> request into a validated Mutation or reject it without guessing.

------------------------------------------------------------------------

## 39. Phase 2B --- Change Simulator

Build:

1.  `ImpactPolicy`;
2.  predicate-aware graph traversal;
3.  direct/transitive/context impact classifications;
4.  hypothetical graph overlay;
5.  deterministic Findings;
6.  evidence-backed SimulationRun;
7.  AI explanation layer;
8.  contextual simulator UI.

Start with one excellent vertical slice, for example:

``` text
UPGRADE Package
```

Then expand to runtime/framework/API/database/service changes.

Success criterion:

> A package upgrade can be compiled and simulated end-to-end with every
> material impact traceable to graph evidence.

------------------------------------------------------------------------

## 40. Phase 2C --- Recommendation-to-Action Loop

Extend recommendation output with proposed ChangeSets.

Build:

``` text
Discover
 ↓
Recommend
 ↓
Simulate
 ↓
Execution plan
 ↓
Verify
```

Add suggested simulations to the product home experience.

Success criterion:

> A user can move from an estate finding to an evidence-backed
> simulation without manually re-entering the recommendation.

------------------------------------------------------------------------

## 41. Phase 2D --- Enterprise Change Memory

Build:

-   ObservedMutation;
-   historical change ingestion;
-   deployment correlation;
-   incident/rollback correlation;
-   predicted-vs-actual impact;
-   similar-change retrieval;
-   historical risk factors.

Success criterion:

> Simulation can use the organization's own previous changes as evidence
> in addition to static graph topology.

------------------------------------------------------------------------

## 42. Phase 2E --- Broader Estate Fidelity

Prioritize improvements that strengthen simulation:

1.  business capability mapping;
2.  data lineage;
3.  service dependencies;
4.  package/runtime/framework intelligence;
5.  AI dependency graph;
6.  infrastructure topology integration.

Integrate rather than rebuild specialist observability, security, and
deep code-analysis capabilities.

------------------------------------------------------------------------

## 43. Phase 2F --- AI Control Plane

Once simulation quality is proven:

``` text
Agent proposes action
        ↓
StackGraph compiles Mutation
        ↓
Semantic validation
        ↓
Impact simulation
        ↓
Policy evaluation
        ↓
ALLOW / CONSTRAIN / ESCALATE / DENY
        ↓
Execution
        ↓
Verification
        ↓
Change memory
```

Add capability compilation, flight recording, and eventually adversarial
harness evaluation.

------------------------------------------------------------------------

# MVP Weekend Vertical Slice

## 44. Recommended Initial Demo

Implement:

``` text
UPGRADE Package
```

Flow:

``` text
1. User types "upgrade".
2. StackGraph returns valid subject categories.
3. User types "newt".
4. StackGraph returns canonical estate entities.
5. User selects Newtonsoft.Json.
6. StackGraph returns current versions and valid target states.
7. User selects target version.
8. Backend creates Mutation.
9. Mutation validation succeeds.
10. ImpactPolicy selects traversal semantics.
11. Graph computes deterministic blast radius.
12. Simulator emits evidence-backed Findings.
13. AI generates risk explanation, rollout, and verification plan.
```

Demo output should emphasize business impact, not merely repository
counts:

``` text
Risk: HIGH

Direct
382 repositories

Transitive
71 applications
12 public APIs

Business
8 capabilities
1 Tier-0 capability: Payment Authorization

Evidence-backed risks
23 incompatible dependency constraints
17 applications missing required tests
3 unsupported runtime combinations

Recommended rollout
Wave 1: low-risk applications
Wave 2: moderate dependencies
Wave 3: Tier-0 / business-critical systems
```

------------------------------------------------------------------------

# What Not to Build

## 45. Explicit Non-Goals

Phase 2 should not turn StackGraph into:

-   another generic chatbot;
-   another generic RAG system;
-   another code search engine;
-   another full observability platform;
-   another vulnerability database;
-   another CMDB;
-   another standalone data-lineage product;
-   another agent framework;
-   another generic workflow engine.

Use and integrate existing systems for commodity capabilities.

Own the semantic layer that connects them.

------------------------------------------------------------------------

# Phase 2 Strategic Moat

## 46. Defensibility

The individual ingredients are not sufficient moats:

``` text
Knowledge graph       → increasingly common
Dependency graph      → common
Blast radius          → common
AI context            → rapidly commoditizing
LLM explanation       → commodity
```

The potential moat is their composition:

``` text
Enterprise semantic model
        +
Canonical entity identity
        +
Evidence/provenance
        +
Estate-derived action grammar
        +
Typed Mutation IR
        +
Deterministic change simulation
        +
Business capability context
        +
Historical change outcomes
        =
Enterprise Change Intelligence
```

Over time, StackGraph can accumulate organization-specific evidence
about which relationships actually predict successful or failed changes.

That creates an increasingly valuable enterprise change memory
unavailable to generic foundation models or static dependency tools.

------------------------------------------------------------------------

## 47. North-Star Product Loop

The desired StackGraph architecture is:

``` text
                        STACKGRAPH

                           ESTATE
                             │
                  ┌──────────┴──────────┐
                  ↓                     ↓
             What exists?         What changed?
                  │                     │
                  └──────────┬──────────┘
                             ↓
                          ANALYZE
                             ↓
                         RECOMMEND
                             ↓
                          COMPILE
                             ↓
                     Valid Mutation IR
                             ↓
                         SIMULATE
                             ↓
              Technical + Business Impact
                             ↓
                          GOVERN
                             ↓
               Allow / Constrain / Escalate
                             ↓
                          EXECUTE
                             ↓
                    Human / Agent / CI
                             ↓
                          VERIFY
                             ↓
                      Actual Outcome
                             ↓
                          LEARN
                             │
                             └──────────→ ESTATE
```

The resulting product principle is:

> **StackGraph understands what exists, determines what can meaningfully
> change, predicts what that change will affect, constrains how it can
> be executed, verifies what actually happened, and learns from the
> outcome.**
