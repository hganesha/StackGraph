# StackGraph Architecture Canvas Specification

**Status:** Proposal

**Revision:** 2

**Date:** 2026-08-22

**Supersedes:** Architecture Canvas proposal dated 2026-08-22

**Decision state:** The six architecture questions in section 13 are resolved for implementation planning.

## 0. How to read this document

Sections 1–3 establish the product problem and the architectural boundary. Section 4 defines the canonical taxonomy work that must precede a trustworthy canvas. Sections 5–8 define reference models, projection, governance, comparison, and scoring. Sections 9–11 define the UI boundary, contracts, and interaction treatment. Section 12 is the delivery sequence. Section 13 records the six resolved decisions and section 14 lists the remaining implementation risks.

The terms **namespace**, **architecture domain**, **concern**, **capability**, **role**, **resource kind**, **aspect**, and **ecosystem** are intentionally distinct. Implementations must not collapse them into a single `domain/category` hierarchy.

## 1. The ask, stated precisely

StackGraph currently presents an estate through relationship-oriented views:

- `GraphCanvas` shows a bounded neighbourhood and is suited to “what touches this thing?”
- `TechnologyHierarchyView` shows dependency structure and is suited to “what depends on what?”

Neither provides a stable coverage frame for these questions:

- What architectural concerns should this scope address?
- What technologies and resources address each concern?
- Which concerns are intentionally not applicable?
- Which concerns are absent despite sufficient evidence?
- Which concerns cannot be evaluated because StackGraph lacks evidence or classification?
- How does the observed architecture differ from the tenant’s governed target?

The Architecture Canvas is a fixed semantic frame filled from evidence. Its geometry remains recognizable between applications, estates, target profiles, and time points. It complements graph and hierarchy views; it does not replace them.

## 2. Organising claim

The canvas is a projection over existing evidence, backed by a new versioned architecture reference model and projection contract.

This replaces the earlier claim that the canvas is “not a new data model.” Existing facts, relationships, citations, code-policy evaluations, resource observations, and deterministic insights remain authoritative. The canvas nevertheless introduces new governed semantics:

- a canonical multidimensional technical taxonomy;
- versioned architecture reference models;
- layout templates that reference those models;
- tenant architecture profiles and applicability rules;
- observation-completeness rules;
- projection and comparison contracts;
- scoring attribution and sufficiency rules.

The renderer does not become a second source of estate truth. It receives a complete, server-produced projection and never invents placement, absence, posture, or policy state.

### 2.1 Existing foundations that are reused

| Foundation | Reuse |
|---|---|
| Evidence-bearing entities and facts | Source of observed occupants and citations |
| `ApplicationDetail.technology_groups` | Input to application projection, after taxonomy-v2 mapping |
| Deployment and resource observations | Input to Platform, Delivery, and Data cells after evidence-bearing read models are added |
| `TenantCodeFunctionSummary` and code policies | Migration source for tenant architecture policy v2 |
| `RepositoryCodePolicyEvaluation` | Input to conformance measures |
| Deterministic insights | Input to risk and currency measures after explicit cell attribution |
| Business-map application assignments | Cross-link from business capability to applications to architecture cells |
| Business-map revision patterns | Precedent for tenant-profile revision and audit handling |

### 2.2 Foundations that are not sufficient as-is

- `EstateSummary` does not provide per-cell occupants or adoption counts.
- `CapabilityFootprintModel` is keyed by business capabilities, not technical architecture cells.
- Existing deployment summaries do not carry the cell-level citations required by this contract.
- Existing allowed/prohibited technology policies do not express required, preferred, optional, or not-applicable architecture expectations.
- The seed capability entities and `capability_definition` inference taxonomy are separate registries with overlapping but divergent identifiers.

These gaps are implementation work, not client-side binding exceptions.

## 3. Design principles

### 3.1 Fixed semantic frame

Cell identity and meaning stay stable across scopes. A layout may responsively reflow, but it must not change cell semantics or silently omit canonical cells during a comparison.

### 3.2 Job-first classification

Placement follows the job a technology or resource performs, not its programming-language ecosystem. Language, runtime, vendor, hosting model, and classification method are facets.

### 3.3 Evidence before appearance

Every populated assertion has at least one citation. The canvas distinguishes absence, lack of observation, lack of applicability, and lack of platform binding.

### 3.4 Canonical semantics, tenant-specific policy

StackGraph owns canonical reference-model keys and meanings. Tenants may tailor applicability, expectations, labels, visibility, and extensions without mutating canonical semantics.

### 3.5 Deterministic and method-versioned

Projection, comparison, and scoring are deterministic over identified inputs. Every result includes taxonomy, reference-model, template, method, and input fingerprints.

### 3.6 No universal score by default

Version 1 presents state distributions and component measures. It does not publish a single band or estate architecture score.

## 4. Canonical technical taxonomy v2

Taxonomy v2 is a Phase 0 prerequisite. Canvas contracts must not be published against the current mixed `domain/category/function` structure.

### 4.1 Namespace is not architecture domain

Ontology namespaces continue to describe the kind of graph entity and its context:

`BUSINESS | ENTERPRISE | TECHNOLOGY | DEPLOYMENT | OSS | INTELLIGENCE`

Architecture domains describe where technical concerns sit in a reference architecture. They are not namespaces and must not use the `Namespace` contract type.

### 4.2 Required taxonomy axes

| Axis | Definition | Cardinality |
|---|---|---|
| Architecture domain | Stable top-level technical plane | A concern has one canonical domain |
| Concern | Canvas-sized grouping of related jobs | A capability has one canonical concern |
| Technical capability | Atomic job performed | A technology may provide many capabilities |
| Architecture role | How an implementation participates | A technology may have many roles |
| Resource kind | Operated resource classification | An observed resource has one primary kind and optional subkind |
| Aspect | Cross-cutting quality, control, or policy lens | Many-to-many |
| Ecosystem | Language/package/runtime ecosystem | Many-to-many facet |
| Use case | Context in which a capability is applied | Many-to-many and evidence-bound |

### 4.3 Canonical architecture domains

The initial canonical domain set is:

| Key | Label | Question answered |
|---|---|---|
| `experience` | Experience & Channels | How do humans and external clients interact with the system? |
| `application` | Application & Services | Where do application behaviour and service responsibilities execute? |
| `integration` | Integration & Messaging | How do requests, events, and workflows cross boundaries? |
| `data` | Data & Information | How is information stored, retrieved, moved, and processed? |
| `platform` | Platform & Runtime | On what runtime, compute, network, and managed platform does the system operate? |
| `delivery` | Delivery & Operations | How is software built, tested, configured, released, observed, and operated? |

`business` remains in the business map and canonical ontology. It is not a technical canvas domain.

### 4.4 Initial concern set

The exact leaf capabilities remain versioned data, but the v2 reference model must cover at least the following concerns.

#### Experience & Channels

- UI rendering and interaction
- Web/meta-framework and server rendering
- Client navigation
- Client and server-state consumption
- Forms and input validation
- Design systems and accessible UI
- Mobile, desktop, and embedded channels

#### Application & Services

- Service and API delivery
- Domain/application logic
- Data access and persistence adapters
- Outbound clients and integration adapters
- Background jobs and scheduling
- Workflow/process execution
- Runtime and application frameworks

#### Integration & Messaging

- Edge proxy and API gateway
- API contracts and interchange
- Service-to-service connectivity
- Message routing and queues
- Durable event streams
- Stream processing
- Integration orchestration
- Shared identity, authentication, authorization, and access-policy services

#### Data & Information

- Relational persistence
- Document, key-value, and graph persistence
- Cache and session state
- Search and vector retrieval
- Object and file storage
- Warehouse, lake, and lakehouse
- Batch and streaming data processing
- Data movement and orchestration

#### Platform & Runtime

- Language and runtime
- Container and artifact runtime
- Compute targets
- Container orchestration
- Serverless and managed compute
- Network, ingress, and service connectivity
- Cloud and on-premises platform services

#### Delivery & Operations

- Source/build/package management
- Automated testing and quality controls
- CI/CD automation
- Infrastructure as code
- Configuration and secret delivery
- Release and deployment management
- Telemetry collection and observability operations
- Reliability and incident operations

### 4.5 Cross-cutting aspects

The canvas may display an aspect rail, but the taxonomy does not re-parent concerns into that rail. Aspects are many-to-many classifications over cells, capabilities, evidence, policies, and insights.

Initial aspects are:

- Security & privacy
- Identity & access
- Governance & compliance
- Reliability & resilience
- Observability
- Developer experience
- Cost & efficiency
- Data governance

Internationalisation and accessibility are scoped product-quality aspects. They apply primarily to Experience and relevant Application concerns; they are not universal rail cells.

CI/CD and configuration management have primary homes in Delivery & Operations and may additionally carry cross-cutting aspects.

### 4.6 Canonical capability registry

StackGraph must have one canonical, versioned technical-capability registry.

The Phase 0 migration must:

1. Reconcile `stackgraph-foundation/seed/capabilities.json` with `services/intelligence/ai-services/capabilities/default.json`.
2. Select one canonical capability key for every equivalent job.
3. Store legacy keys as aliases, not parallel definitions.
4. Relate every capability to one concern and one architecture domain.
5. Sync the canonical artifact into `capability_taxonomy_version` and `capability_definition`.
6. Ensure technology `PROVIDES` relationships and package/symbol mappings point to the same definitions.
7. Migrate tenant code policies through the key crosswalk while preserving fingerprints and audit history.

The current category IDs may remain as compatibility metadata during migration. New projection code must bind to canonical concern or capability keys.

### 4.7 Technology placement

A technology does not own one authoritative canvas domain. Its placements are derived from cited capability or resource observations.

Examples:

- Redis may populate cache, session-state, and message-routing cells when the relevant uses are evidenced.
- NGINX may populate reverse-proxy or ingress concerns, depending on observed configuration.
- Next.js may populate rendering, routing, build, and service-boundary capabilities.

It is valid for a technology to appear in multiple cells. Aggregate summaries must distinguish unique technologies from technology-cell placements.

### 4.8 Taxonomy coverage gate

Before a canonical cell may be published, it must declare:

- its capability or resource bindings;
- supported evidence sources;
- observation-completeness rule;
- applicability default;
- at least one test fixture for populated and unobserved behaviour;
- whether absence can ever be asserted safely;
- known classification gaps.

Cells without a valid binding may appear only as explicitly `UNBOUND` preview cells and are excluded from governance and scoring denominators.

## 5. Reference models, templates, and tenant profiles

The earlier proposal used “template” for semantics, policy, and layout. These are now separate contracts.

### 5.1 Architecture reference model

The reference model owns canonical cell identity and meaning.

```ts
interface ArchitectureReferenceModel {
  key: string;
  version: string;
  name: string;
  description: string;
  taxonomy_key: string;
  taxonomy_version: string;
  taxonomy_content_hash: string;
  content_hash: string;
  cells: ArchitectureCellDefinition[];
}

interface ArchitectureCellDefinition {
  key: string;
  concern_key: string;
  label: string;
  definition: string;
  bindings: CanvasBinding[];
  aspect_keys: string[];
  default_expectation: CellExpectation;
  observation_rule_key: string;
}
```

Canonical cell keys are globally stable within a reference-model major version. A canonical capability key may bind to at most one cell in the same reference model. Resource and aspect bindings are validated for unintended overlap.

### 5.2 Layout template

The template owns presentation geometry only.

```ts
interface CanvasTemplate {
  key: string;
  version: string;
  reference_model_key: string;
  reference_model_version: string;
  content_hash: string;
  bands: CanvasBandLayout[];
}

interface CanvasBandLayout {
  domain_key: string;
  order: number;
  columns: number;
  cells: Array<{ cell_key: string; span?: 1 | 2 | 3 }>;
}
```

Colour and CSS custom-property names do not cross the API boundary. The UI maps semantic domain keys to Strata design tokens. Icons are semantic registry keys validated by the UI package.

### 5.3 Tenant architecture profile

A tenant profile overlays canonical defaults without mutating the reference model.

```ts
interface TenantArchitectureProfile {
  id: string;
  reference_model_key: string;
  reference_model_version: string;
  version: number;
  status: "DRAFT" | "ACTIVE" | "ARCHIVED";
  cell_overrides: TenantCellPolicy[];
  extension_cells: TenantExtensionCell[];
  fingerprint: string;
}
```

Allowed canonical overrides are:

- applicability and scope selector;
- expectation/cardinality;
- preferred, allowed, discouraged, and prohibited technologies;
- rationale, owner, exception, and effective dates.

Tenants may not change the binding or meaning of a canonical cell. Tenant extension cells use tenant-namespaced keys and appear in a separate extension section. Canonical cross-tenant comparisons operate only on canonical cells and disclose excluded extensions.

### 5.4 Canonical geometry

Application, estate, target, and comparison views use the same reference model and canonical cell geometry. They are modes or projections, not separate reduced semantic templates.

At small viewports, bands and aspect rails may reflow vertically. Reflow must preserve reading order and cell identity. Comparison views may not hide canonical cells.

## 6. Projection

A projection is:

```text
(tenant, reference model, template, scope, subject, as_of, tenant profile) -> filled cells
```

It is computed server-side and returned as one contract object. Client-side assembly is not an implementation phase.

### 6.1 Projection scopes

| Scope | Subject | Contents |
|---|---|---|
| `ESTATE` | Tenant | Deduplicated observed placements plus adoption counts |
| `APPLICATION` | Application | Placements attributable to the application and its repositories/deployments |
| `REPOSITORY` | Repository | Placements attributable to repository evidence |
| `TARGET` | Tenant profile | Required, preferred, allowed, discouraged, and prohibited target decisions |

`DRIFT` is not a scope. It is a comparison between an actual projection and a target projection.

### 6.2 Cell state

```ts
type CanvasCellState =
  | "POPULATED"
  | "EMPTY"
  | "NOT_APPLICABLE"
  | "UNOBSERVED"
  | "UNBOUND";
```

| State | Meaning |
|---|---|
| `POPULATED` | At least one occupant placement is present; observed placements have fact citations and target placements have policy provenance |
| `EMPTY` | The concern is applicable, the required sensors are sufficiently complete and fresh, and no occupant was found |
| `NOT_APPLICABLE` | An effective tenant or scope rule says the concern does not apply |
| `UNOBSERVED` | The concern is bound, but required evidence is missing, stale, partial, or unsupported for this scope |
| `UNBOUND` | The reference model has no supported platform binding |

`EMPTY` is never inferred merely from an empty query result. It requires a successful observation-completeness rule. `NOT_APPLICABLE`, `UNOBSERVED`, and `UNBOUND` are excluded from coverage denominators.

### 6.3 Unmapped and ambiguous observations

Every projection includes an explicit classification tray:

- unclassified technologies;
- observations that match more than one mutually exclusive binding;
- tenant policies that cannot be resolved to a canonical or extension cell;
- observations excluded by active filters.

These counts appear in the projection summary. The canvas must never silently drop them.
The first contract bounds returned tray items to 200, reports the complete per-reason and total
counts, and sets `truncated` when more items are available. A later pagination route may expose
the remainder without making the primary projection response unbounded.

### 6.4 Cell payload

```ts
interface CanvasCellProjection {
  cell_key: string;
  state: CanvasCellState;
  state_reason: string;
  occupants: CanvasOccupant[];
  occupant_total: number;
  unique_technology_total: number;
  observation: CellObservationStatus;
  expectation: EffectiveCellExpectation;
  measures: CanvasCellMeasures | null;
  policy: CanvasCellPolicy | null;
  insight_refs: string[];
  citations: Citation[];
}

interface CanvasOccupant {
  technology: EntitySummary;
  placement_keys: string[];
  classification: TechnologyClassification;
  confidence: number;
  confidence_label: ConfidenceLabel;
  adoption_applications: number;
  adoption_repositories: number;
  adoption_deployments: number;
  policy_status:
    | "PREFERRED"
    | "ALLOWED"
    | "DISCOURAGED"
    | "PROHIBITED"
    | "EXEMPTED"
    | "UNGOVERNED";
  citations: Citation[];
  policy_reference: string | null;
}
```

Each occupant contains the capability, role, or resource placement keys that caused it to enter the cell. This makes multi-cell technologies explainable.

### 6.5 Observation completeness

`CellObservationStatus` reports:

- required sensor kinds;
- supported sensor kinds;
- last successful observations;
- in-scope and observed subject counts;
- freshness status;
- unsupported ecosystems;
- missing inputs;
- method version and fingerprint.

The analytical-assurance measures used by Estate Health are reused here. The canvas does not create a second definition of repository coverage or evidence freshness.

### 6.6 Historical projections

Historical `as_of` projections are deferred until comparison/export phase. When enabled, the server must resolve facts, taxonomy version, reference-model version, tenant-profile revision, and scoring method as of the requested time. It must not apply today’s policy retroactively to historical evidence without explicitly labelling that comparison mode.

## 7. Expectations and the golden target

The existing allowed/prohibited code-policy model is a migration source, not a complete golden architecture model.

### 7.1 Effective expectation

```ts
interface CellExpectation {
  applicability: "REQUIRED" | "RECOMMENDED" | "OPTIONAL" | "NOT_APPLICABLE";
  minimum_implementations: number | null;
  maximum_implementations: number | null;
  allowed_diversity: number | null;
}

interface TenantCellPolicy extends CellExpectation {
  cell_key: string;
  scope_selector: ScopeSelector;
  preferred_technology_ids: string[];
  allowed_technology_ids: string[];
  discouraged_technology_ids: string[];
  prohibited_technology_ids: string[];
  rationale: string;
  owner: string | null;
  effective_from: string | null;
  effective_to: string | null;
  exceptions: PolicyException[];
}
```

The reference model supplies defaults. The active tenant profile supplies scoped overrides. Effective policy is deterministic and explainable.

### 7.2 Golden mode

Golden mode renders the `TARGET` projection over the same canonical geometry.

Each cell displays:

- applicability and cardinality;
- preferred technologies;
- allowed technologies;
- discouraged technologies;
- prohibited technologies;
- rationale, owner, exceptions, and effective dates;
- unresolved legacy/custom policies.

“Make this the standard” creates or updates a **preferred** decision. It does not merely add the technology to an allowed list.

### 7.3 Legacy code-policy migration

Existing policies migrate as follows:

- allowed -> `ALLOWED`;
- prohibited -> `PROHIBITED`;
- a governed function with no architecture-cell resolution -> unresolved policy tray;
- custom functions -> tenant extension cells when explicitly mapped, otherwise unresolved policy tray.

Migration does not infer `REQUIRED` or `PREFERRED`. Those decisions require tenant action or an explicitly approved migration rule.

### 7.4 Comparison and drift

Drift is a first-class comparison result:

```ts
interface CanvasComparison {
  comparison_kind: "ACTUAL_TO_TARGET" | "ACTUAL_TO_ACTUAL" | "TIME_TO_TIME";
  actual_projection_fingerprint: string;
  baseline_projection_fingerprint: string;
  cells: CanvasCellComparison[];
  summary: CanvasComparisonSummary;
  method_version: string;
  input_fingerprint: string;
}
```

Actual-to-target comparison distinguishes:

- preferred in use;
- allowed in use;
- discouraged in use;
- prohibited in use;
- required but absent;
- policy not applicable;
- ungoverned;
- unevaluable because observation is incomplete.

Comparison never converts unevaluable cells into non-conformance.

## 8. Measures and scoring

### 8.1 Version 1 output

Version 1 returns component measures and a posture band only when enough components are eligible. It does not return a mandatory universal 0–100 score.

```ts
interface CanvasCellMeasures {
  posture_band: "STRONG" | "ADEQUATE" | "WEAK" | "AT_RISK" | null;
  overall_score: number | null;
  components: {
    coverage: MeasureResult;
    standardisation: MeasureResult;
    currency: MeasureResult;
    risk: MeasureResult;
    conformance: MeasureResult;
  };
  confidence: number;
  confidence_label: ConfidenceLabel;
  method_version: string;
  missing_inputs: string[];
}

interface MeasureResult {
  value: number | null;
  status: "ELIGIBLE" | "INSUFFICIENT_DATA" | "NOT_APPLICABLE" | "NOT_CONFIGURED";
  inputs: string[];
  supporting_fact_ids: string[];
  method_version: string;
}
```

### 8.2 Component definitions

| Component | Meaning | Eligibility notes |
|---|---|---|
| Coverage | Whether an applicable concern meets its minimum expectation | Requires applicability and sufficient observation |
| Standardisation | Whether implementation diversity is within effective policy | Requires a meaningful comparison population |
| Currency | Version, support, deprecation, and lifecycle posture | May be meaningful for one repository |
| Risk | Evidence-backed vulnerability and deterministic insight exposure | May be meaningful for one repository; it is exposure, not peer comparison |
| Conformance | Alignment with the effective target policy | Requires an applicable target policy and sufficient attribution |

### 8.3 Small-sample policy

There is no blanket “fewer than three repositories means no posture” rule.

- Standardisation is `INSUFFICIENT_DATA` below its subject/adoption threshold.
- Coverage may be evaluated for one repository when applicability and observation are known.
- Currency, risk, and conformance may be evaluated for one repository.
- A composite score remains `null` when the eligible component set or confidence is insufficient.
- The UI shows component facts and missing inputs even when no composite exists.

Thresholds belong to the versioned measure registry and are testable method inputs, not UI constants.

### 8.4 Attribution rules

Measures are computed against placement evidence, not name matching.

- Technical-cell standardisation is computed from technology-cell placements, not `CapabilityFootprintModel` business-capability entropy.
- Risk insights enter a cell only through an explicit subject/occupant/fact attribution path.
- Currency uses versioned package/runtime observations attributable to occupants in that cell.
- Conformance uses the effective tenant profile and resolved cell placement.

### 8.5 Relationship to Estate Health

Estate Health answers: **Can StackGraph reliably reason about this estate?**

The canvas answers: **What architecture is present and how does it compare with the governed target?**

They share a method-versioned measure registry for observation completeness, evidence coverage, freshness, currency, risk, and policy conformance. They do not publish competing definitions of those inputs and do not need to aggregate them into the same result.

The canvas consumes analytical assurance as an eligibility and confidence input. Estate Health does not average canvas cells into an estate-health score.

## 9. Component architecture

### 9.1 Package boundary

Create `packages/canvas-ui`, sibling to `packages/graph-ui`:

```text
packages/canvas-ui/
  src/
    ArchitectureCanvas.tsx
    CanvasBand.tsx
    CanvasCell.tsx
    CanvasAspectRail.tsx
    PostureMeter.tsx
    OccupantChip.tsx
    ClassificationTray.tsx
    layout.ts
    canvas.module.css
    index.ts
```

The package contains no fetching, routing, tenant-policy mutation, evidence-drawer implementation, or taxonomy inference.

### 9.2 Component contract

```ts
interface ArchitectureCanvasProps {
  template: CanvasTemplate;
  projection: CanvasProjection;
  comparison?: CanvasComparison;
  mode?: "read" | "govern" | "compare";
  density?: "comfortable" | "compact";
  emphasis?: "posture" | "conformance" | "coverage" | "none";
  selectedCellKey?: string | null;
  onSelectCell?: (cellKey: string | null) => void;
  onSelectOccupant?: (technologyId: string, cellKey: string) => void;
  onPolicyIntent?: (intent: CanvasPolicyIntent) => void;
}
```

The UI emits policy intents. The application layer validates permissions, collects rationale where required, calls the API, and refreshes projections.

### 9.3 Product surfaces

| Surface | Placement |
|---|---|
| Estate | Canvas view beside existing estate views |
| Application | Canvas tab in application view switch |
| Repository | Architecture coverage section or tab |
| Technology | “Where this is used” mini-canvas and placement list |
| Architecture | Full estate/target/comparison workspace |
| Admin | Tenant architecture profile and policy governance |

The Architecture workspace is the primary canvas surface. Admin owns profile lifecycle, permissions, and audit history; it does not need a second canvas implementation.

### 9.4 Relationship to the business map

The business map and architecture canvas remain separate authored and derived frames.

The supported join is:

```text
business capability -> assigned applications -> repositories/deployments -> architecture placements
```

This enables questions such as “which architecture concerns does Order Fulfilment depend on?” without merging the two editing models.

## 10. Contracts and routes

### 10.1 Projection contract

```ts
interface CanvasProjection {
  contract_version: "1.0.0";
  as_of: string;
  method_version: string;
  taxonomy_key: string;
  taxonomy_version: string;
  taxonomy_content_hash: string;
  reference_model_key: string;
  reference_model_version: string;
  reference_model_content_hash: string;
  template_key: string;
  template_version: string;
  tenant_profile_fingerprint: string | null;
  scope: "ESTATE" | "APPLICATION" | "REPOSITORY" | "TARGET";
  subject: EntitySummary | null;
  cells: CanvasCellProjection[];
  classification_tray: CanvasClassificationTray;
  summary: CanvasProjectionSummary;
  input_fingerprint: string;
}
```

The summary carries counts by state, policy status, posture band, unmapped observations, and ambiguous observations. It does not carry a band or canvas average.

### 10.2 Routes and access

| Method | Path | Capability | Purpose |
|---|---|---|---|
| `GET` | `/canvas/reference-models` | `view` | List canonical reference models |
| `GET` | `/canvas/reference-models/{key}` | `view` | Fetch one versioned model |
| `GET` | `/canvas/templates` | `view` | List compatible layouts |
| `GET` | `/canvas/projection` | `view` | Actual estate/application/repository projection |
| `GET` | `/canvas/target-projection` | `review` | Effective target projection |
| `POST` | `/canvas/comparisons` | `review` | Actual-to-target or other comparison |
| `GET` | `/admin/architecture-profiles` | `admin` | List profile aggregates and lifecycle state |
| `POST` | `/admin/architecture-profiles` | `admin` | Create a draft profile |
| `PUT` | `/admin/architecture-profiles/{id}` | `admin` | Update a draft with optimistic concurrency |
| `POST` | `/admin/architecture-profiles/{id}/publish` | `admin` | Publish an effective revision |

Ordinary `view` access does not expose target policies or drift. Deployments may grant broader target visibility through the existing capability ladder, but the default cannot be weaker than the current code-policy boundary.

### 10.3 Contract validation

Validation must enforce:

- canonical key uniqueness;
- capability-to-cell uniqueness per reference model;
- taxonomy/reference/template version compatibility;
- server-computed content hashes;
- valid extension namespaces;
- no overlapping technology decision states;
- citations on every populated occupant placement;
- state and observation-rule consistency;
- `EMPTY` only after observation completeness succeeds;
- comparison compatibility or an explicit migration crosswalk.

## 11. Interaction and visual treatment

### 11.1 Layout

- Domains stack vertically with a header and cell grid.
- The optional aspect rail appears on the right at wide widths and reflows below the domains on narrow widths.
- No horizontal page scroll is introduced.
- Vertical scrolling is allowed when taxonomy depth or accessibility zoom requires it.
- A sticky domain index may aid navigation without changing geometry.
- Compact mode targets a useful 1440×900 overview, but semantic coverage is not capped solely to force every cell into one viewport.

### 11.2 Cell treatments

| State | Treatment |
|---|---|
| `POPULATED` | Standard card, ranked occupant chips, eligible measures |
| `EMPTY` | Calm dashed treatment and “none found”; severity comes from policy, not emptiness alone |
| `NOT_APPLICABLE` | Muted treatment with applicable rule and rationale |
| `UNOBSERVED` | Dashed treatment with missing/stale sensor reason |
| `UNBOUND` | Lowest contrast with platform limitation; excluded from denominators |

Policy, posture, confidence, and observation state are communicated with text and structure, never colour alone.

### 11.3 Controls and details

Facets include ecosystem, classification, confidence, policy status, application, team, and evidence freshness.

Selecting a cell opens a details panel containing:

- full occupant list and placement reasons;
- effective expectation and applicability;
- observation completeness;
- component measures and missing inputs;
- attributed insights;
- policy decisions and exceptions;
- citations;
- unmapped or ambiguous observations relevant to the cell.

Keyboard navigation follows grid semantics. Responsive reflow must preserve DOM reading order. Build acceptance includes WCAG 2.2 AA keyboard, focus, contrast, zoom, and assistive-technology checks.

### 11.4 Export

Export is server-produced and includes:

- SVG and PNG visual output;
- structured projection or comparison JSON;
- `as_of` time;
- taxonomy, reference-model, template, tenant-profile, and method versions;
- input fingerprint;
- a classification/observation coverage summary;
- stable evidence references.

The visual file need not embed every citation body, but it must carry a trace identifier that resolves to the structured export and its evidence while retained.

## 12. Delivery plan

### Phase 0 — Taxonomy and policy foundations

- Publish canonical technical taxonomy v2.
- Reconcile the seed and inference capability registries.
- Add concern, architecture-role, resource-kind, aspect, ecosystem, and use-case relationships.
- Seed Data as a first-class architecture domain.
- Expand Application/backend concerns and provider mappings.
- Define evidence and observation-completeness rules per proposed cell.
- Produce legacy-key and code-policy migration crosswalks.

**Exit:** every canonical preview cell has a stable key, binding, observation rule, fixture, and known gap; golden-policy identifiers resolve to the same capability registry used by inference.

### Phase 1 — Read-only application canvas

- Ship the first versioned reference model and layout template.
- Add the server-side `APPLICATION` projection.
- Render state, occupants, citations, observation status, and classification tray.
- Mount the canvas in application detail.
- Do not score or infer absence without observation completeness.

**Exit:** the server and renderer produce a trustworthy application canvas from real fixtures and pilot data.

### Phase 2 — Estate and repository coverage

- Add `ESTATE` and `REPOSITORY` projections.
- Add evidence-bearing deployment and resource read models.
- Add Data, Platform, and Delivery placements.
- Add application/team facets and the Architecture workspace.
- Integrate shared analytical-assurance inputs from Estate Health.

**Exit:** state distinctions remain correct under partial scans, unsupported ecosystems, stale evidence, and unmapped observations.

### Phase 3 — Governed target and drift

- Add tenant architecture profiles and revision/audit persistence.
- Migrate existing allowed/prohibited policies.
- Add applicability, cardinality, preferred/allowed/discouraged/prohibited states, rationale, and exceptions.
- Add `TARGET` projection and actual-to-target comparison.
- Add promote-from-actual as a preferred-policy intent.

**Exit:** no legacy/custom policy is silently dropped, and unevaluable cells never become violations.

### Phase 4 — Component measures

- Implement the shared measure registry.
- Add coverage, standardisation, currency, risk, and conformance measures.
- Apply component-specific small-sample and confidence rules.
- Validate outputs against a representative pilot cohort and architecture-review feedback.
- Keep band/canvas averages disabled.

**Exit:** each measure is deterministic, cited, method-versioned, calibrated, and explainable from the cell panel.

### Phase 5 — Extensions, comparison, and export

- Add tenant extension cells and safe presentation overrides.
- Add application-to-application and time-to-time comparison.
- Add historical policy/evidence resolution.
- Add server-rendered SVG/PNG and structured export.
- Evaluate whether any aggregate architecture score is useful after at least one quarter of observed use.

**Exit:** comparisons disclose semantic incompatibility, excluded extensions, unmapped observations, and all relevant versions.

## 13. Resolved architecture decisions

### Decision 1 — Data domain

**Decision:** Data becomes a first-class seeded architecture domain in Phase 0.

Resource bindings remain evidence adapters for database, cache, storage, search, queue, warehouse/lake, and related observations. They do not define hardcoded canvas-only semantics.

### Decision 2 — Template ownership

**Decision:** StackGraph owns canonical reference models and compatible layout templates. Tenants own versioned overlays and tenant-namespaced extension cells.

Tenants may not rebind or redefine canonical cell keys. Canonical benchmarking uses canonical cells only and discloses excluded tenant extensions.

### Decision 3 — Cell expectations

**Decision:** Canonical reference models provide defaults; the active tenant architecture profile provides effective scoped overrides.

Expectations use applicability, minimum/maximum implementations, and allowed diversity. They do not use only `one | many | optional`.

### Decision 4 — Backend depth

**Decision:** The current five-capability backend band does not ship as the official governed reference band.

It may support an explicitly experimental, unscored prototype, but Phase 0 must expand Application & Services concerns and populate their deterministic provider or inference mappings before the reference model is published.

### Decision 5 — Small-scope scoring

**Decision:** Sufficiency is evaluated per component. There is no blanket suppression below three repositories.

Standardisation requires a comparison population; coverage, currency, risk, and conformance may be meaningful for one repository when their own eligibility conditions are satisfied. Composite output remains null when the eligible evidence is insufficient.

### Decision 6 — Relationship to Estate Health

**Decision:** Estate Health and Architecture Canvas share measurement primitives but have different outcomes.

Estate Health evaluates analytical and operational assurance. The canvas evaluates observed architecture and alignment with a governed target. Analytical assurance gates canvas state, eligibility, and confidence; the two surfaces do not publish competing definitions or average each other’s scores.

## 14. Remaining risks and validation questions

These are implementation validations rather than undecided product architecture:

1. Determine which Phase 0 cells have enough deterministic evidence for `EMPTY`, rather than only `UNOBSERVED`.
2. Validate the six-domain frame and initial concern granularity with architects from at least three materially different estates.
3. Measure multi-placement frequency for technologies such as Redis, NGINX, Next.js, Kafka, and OpenTelemetry.
4. Define migration behaviour for tenant custom functions that overlap future canonical capabilities.
5. Establish retention and authorization for export trace identifiers and evidence resolution.
6. Benchmark projection and comparison queries at pilot and target estate sizes.
7. Decide whether the Architecture workspace replaces or supplements the current select-based code-policy editor after Phase 3 acceptance testing.

No scoring or governance phase should proceed while canonical cell mappings, observation completeness, or policy migration can silently omit estate data.
