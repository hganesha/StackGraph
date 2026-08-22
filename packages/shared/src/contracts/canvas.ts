// Architecture Canvas contract types.
//
// Hand-curated facade for the canvas surface, mirroring the wire contract the API
// publishes. Kept in its own module (rather than folded into read-models.ts) so the
// frontend and backend workstreams can land independently: the API owns
// models.py -> openapi.json -> openapi.generated.ts, this file is the curated view
// the app binds against, and CI's contracts:check compares the generated artifact.
//
// Source of truth for the shapes below: docs/stackgraph-architecture-canvas-spec.md
// revision 2. Section references appear against each block. Types the spec names but
// does not fully expand are completed here and marked [COMPLETES SPEC] — those are the
// blocks to review against the server implementation before Phase 1 exit.

import type {
  Citation,
  Confidence,
  ConfidenceLabel,
  EntitySummary,
  Freshness,
  FreshnessStatus,
  TechnologyClassification,
  Timestamp,
  UUID,
} from "./read-models";

// ─── Taxonomy v2 (spec §4) ───────────────────────────────────────────────────

/**
 * Architecture domain keys are versioned reference-model data, not a closed
 * contract enum (spec §4.1: they are NOT the `Namespace` type). The six canonical
 * keys of the initial model are listed for editor completion; the type stays open
 * so a new reference-model version does not require a client release.
 */
export type ArchitectureDomainKey =
  | "experience"
  | "application"
  | "integration"
  | "data"
  | "platform"
  | "delivery"
  | (string & {});

/** Cross-cutting lenses (spec §4.5). Many-to-many over cells; never re-parents them. */
export type ArchitectureAspectKey =
  | "security-privacy"
  | "identity-access"
  | "governance-compliance"
  | "reliability-resilience"
  | "observability"
  | "developer-experience"
  | "cost-efficiency"
  | "data-governance"
  | (string & {});

// ─── Bindings (spec §4.8, §5.1) ──────────────────────────────────────────────

/**
 * [COMPLETES SPEC] §5.1 declares `bindings: CanvasBinding[]` without expanding the
 * union. Members follow the taxonomy axes in §4.2. A cell with only an `unbound`
 * member is a preview cell: excluded from governance and scoring denominators (§4.8).
 */
export type CanvasBinding =
  | { kind: "capability"; capability_keys: string[] }
  | { kind: "role"; role_keys: string[] }
  | { kind: "resource"; resource_kinds: string[]; resource_subkinds?: string[] }
  | { kind: "aspect"; aspect_keys: ArchitectureAspectKey[] }
  | { kind: "tenant-policy"; policy_function_keys: string[] }
  | { kind: "unbound"; reason: string };

// ─── Expectations (spec §7.1) ────────────────────────────────────────────────

export type CellApplicability = "REQUIRED" | "RECOMMENDED" | "OPTIONAL" | "NOT_APPLICABLE";

export interface CellExpectation {
  applicability: CellApplicability;
  minimum_implementations: number | null;
  maximum_implementations: number | null;
  allowed_diversity: number | null;
}

/** [COMPLETES SPEC] Scope selector for tenant policy targeting (§7.1). */
export interface ScopeSelector {
  application_ids?: UUID[];
  repository_ids?: UUID[];
  team_keys?: string[];
  tags?: string[];
  /** Empty/absent selector means "every subject in the tenant". */
  description?: string;
}

/** [COMPLETES SPEC] A time-boxed, owned carve-out from an effective policy (§7.1). */
export interface PolicyException {
  id: UUID;
  scope_selector: ScopeSelector;
  rationale: string;
  owner: string | null;
  effective_from: Timestamp | null;
  effective_to: Timestamp | null;
}

/**
 * [COMPLETES SPEC] The resolved expectation for one cell in one projection, carrying
 * where it came from so the panel can explain it (§7.1: "effective policy is
 * deterministic and explainable").
 */
export interface EffectiveCellExpectation extends CellExpectation {
  source: "REFERENCE_MODEL" | "TENANT_PROFILE";
  scope_selector: ScopeSelector | null;
  rationale: string | null;
  owner: string | null;
  effective_from: Timestamp | null;
  effective_to: Timestamp | null;
}

// ─── Reference model and layout template (spec §5.1, §5.2) ───────────────────

export interface ArchitectureCellDefinition {
  key: string;
  concern_key: string;
  domain_key: ArchitectureDomainKey;
  label: string;
  definition: string;
  bindings: CanvasBinding[];
  aspect_keys: ArchitectureAspectKey[];
  default_expectation: CellExpectation;
  observation_rule_key: string;
  /** Semantic icon registry key; validated by the UI package, never a colour (§5.2). */
  icon: string;
}

export interface ArchitectureDomainDefinition {
  key: ArchitectureDomainKey;
  label: string;
  question: string;
  order: number;
}

export interface ArchitectureAspectDefinition {
  key: ArchitectureAspectKey;
  label: string;
  definition: string;
  order: number;
}

export interface ArchitectureReferenceModel {
  contract_version: "1.0.0";
  key: string;
  version: string;
  name: string;
  description: string;
  taxonomy_key: string;
  taxonomy_version: string;
  taxonomy_content_hash: string;
  content_hash: string;
  domains: ArchitectureDomainDefinition[];
  aspects: ArchitectureAspectDefinition[];
  cells: ArchitectureCellDefinition[];
}

export interface ArchitectureReferenceModelList {
  contract_version: "1.0.0";
  models: Array<Pick<
    ArchitectureReferenceModel,
    "key" | "version" | "name" | "description" | "content_hash"
  >>;
}

export interface CanvasBandLayoutCell {
  cell_key: string;
  span?: 1 | 2 | 3;
}

export interface CanvasBandLayout {
  domain_key: ArchitectureDomainKey;
  order: number;
  columns: number;
  cells: CanvasBandLayoutCell[];
}

/**
 * Presentation geometry only. Colour and CSS custom-property names do not cross the
 * API boundary (§5.2); the UI maps `domain_key` to Strata tokens.
 */
export interface CanvasTemplate {
  contract_version: "1.0.0";
  key: string;
  version: string;
  name: string;
  reference_model_key: string;
  reference_model_version: string;
  content_hash: string;
  bands: CanvasBandLayout[];
  /** Aspect rail order; empty means the template renders no rail. */
  aspect_rail: ArchitectureAspectKey[];
}

export interface CanvasTemplateList {
  contract_version: "1.0.0";
  templates: Array<Pick<
    CanvasTemplate,
    "key" | "version" | "name" | "reference_model_key" | "reference_model_version" | "content_hash"
  >>;
}

// ─── Projection (spec §6) ────────────────────────────────────────────────────

export type CanvasScope = "ESTATE" | "APPLICATION" | "REPOSITORY" | "TARGET";

export type CanvasCellState =
  | "POPULATED"
  | "EMPTY"
  | "NOT_APPLICABLE"
  | "UNOBSERVED"
  | "UNBOUND";

export type CanvasOccupantPolicyStatus =
  | "PREFERRED"
  | "ALLOWED"
  | "DISCOURAGED"
  | "PROHIBITED"
  | "UNGOVERNED";

export type CanvasPolicyDecision = "PREFERRED" | "ALLOWED" | "DISCOURAGED" | "PROHIBITED";

/** [COMPLETES SPEC] One sensor's contribution to a cell's observation rule (§6.5). */
export interface CanvasSensorStatus {
  sensor_kind: string;
  supported: boolean;
  last_observed_at: Timestamp | null;
  freshness: Freshness | null;
}

/**
 * [COMPLETES SPEC] §6.5 enumerates the fields this must report. `status` is the
 * gate: `EMPTY` is only legal when it is `COMPLETE` (§6.2).
 */
export interface CellObservationStatus {
  rule_key: string;
  status: "COMPLETE" | "PARTIAL" | "STALE" | "UNSUPPORTED" | "ABSENT";
  required_sensor_kinds: string[];
  supported_sensor_kinds: string[];
  sensors: CanvasSensorStatus[];
  subjects_in_scope: number;
  subjects_observed: number;
  freshness_status: FreshnessStatus;
  unsupported_ecosystems: string[];
  missing_inputs: string[];
  method_version: string;
  input_fingerprint: string;
}

export type MeasureStatus =
  | "ELIGIBLE"
  | "INSUFFICIENT_DATA"
  | "NOT_APPLICABLE"
  | "NOT_CONFIGURED";

export interface MeasureResult {
  value: number | null;
  status: MeasureStatus;
  inputs: string[];
  supporting_fact_ids: UUID[];
  method_version: string;
}

export type CanvasPostureBand = "STRONG" | "ADEQUATE" | "WEAK" | "AT_RISK";

export interface CanvasCellMeasures {
  posture_band: CanvasPostureBand | null;
  overall_score: number | null;
  components: {
    coverage: MeasureResult;
    standardisation: MeasureResult;
    currency: MeasureResult;
    risk: MeasureResult;
    conformance: MeasureResult;
  };
  confidence: Confidence;
  confidence_label: ConfidenceLabel;
  method_version: string;
  missing_inputs: string[];
}

export interface CanvasOccupant {
  technology: EntitySummary;
  /** Capability/role/resource keys that placed this occupant here (§6.4). */
  placement_keys: string[];
  classification: TechnologyClassification;
  confidence: Confidence;
  confidence_label: ConfidenceLabel;
  adoption: {
    applications: number;
    repositories: number;
    deployments: number;
  };
  policy_status: CanvasOccupantPolicyStatus;
  citations: Citation[];
}

/** [COMPLETES SPEC] One governed technology decision inside a cell (§7.1, §7.2). */
export interface CanvasPolicyTechnologyDecision {
  technology: EntitySummary;
  decision: CanvasPolicyDecision;
  rationale: string | null;
}

/** [COMPLETES SPEC] Resolved policy state for one cell, as golden mode renders it (§7.2). */
export interface CanvasCellPolicy {
  governed: boolean;
  profile_id: UUID | null;
  profile_version: number | null;
  decisions: CanvasPolicyTechnologyDecision[];
  exceptions: PolicyException[];
  rationale: string | null;
  owner: string | null;
  effective_from: Timestamp | null;
  effective_to: Timestamp | null;
  /** Legacy code-policy function keys that resolved to this cell (§7.3). */
  migrated_function_keys: string[];
  fingerprint: string;
}

export interface CanvasCellProjection {
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
  insight_refs: UUID[];
  citations: Citation[];
}

// ─── Classification tray (spec §6.3) ─────────────────────────────────────────

/** [COMPLETES SPEC] An observation the projection could not place. */
export interface CanvasUnclassifiedObservation {
  technology: EntitySummary;
  reason: string;
  ecosystem: string | null;
  citations: Citation[];
}

/** [COMPLETES SPEC] An observation matching more than one mutually exclusive binding. */
export interface CanvasAmbiguousObservation {
  technology: EntitySummary;
  candidate_cell_keys: string[];
  reason: string;
  citations: Citation[];
}

/** [COMPLETES SPEC] A tenant policy with no canonical or extension cell (§6.3, §7.3). */
export interface CanvasUnresolvedPolicy {
  policy_key: string;
  label: string;
  source: "PRIMARY" | "CUSTOM";
  reason: string;
  technology_count: number;
  /**
   * [COMPLETES SPEC] The decisions the unresolved policy carries. §7.3 requires that
   * no legacy or custom policy is silently dropped, which means the UI has to be able
   * to move one onto a cell — and it cannot do that from a count alone.
   */
  technologies: CanvasPolicyTechnologyDecision[];
}

export interface CanvasClassificationTray {
  unclassified_technologies: CanvasUnclassifiedObservation[];
  ambiguous_observations: CanvasAmbiguousObservation[];
  unresolved_policies: CanvasUnresolvedPolicy[];
  /** Observations withheld by the active facet filters, so the count is never silently lost. */
  filtered_out_total: number;
}

// ─── Projection envelope (spec §10.1) ────────────────────────────────────────

/** Counts only. The summary deliberately carries no band or canvas average (§3.6, §10.1). */
export interface CanvasProjectionSummary {
  cells_total: number;
  by_state: Record<CanvasCellState, number>;
  by_posture_band: Record<CanvasPostureBand, number> & { UNSCORED: number };
  by_policy_status: Record<CanvasOccupantPolicyStatus, number>;
  unique_technologies: number;
  placements_total: number;
  governed_cells: number;
  unmapped_observations: number;
  ambiguous_observations: number;
  unresolved_policies: number;
}

export interface CanvasProjection {
  contract_version: "1.0.0";
  as_of: Timestamp;
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
  scope: CanvasScope;
  subject: EntitySummary | null;
  cells: CanvasCellProjection[];
  classification_tray: CanvasClassificationTray;
  summary: CanvasProjectionSummary;
  input_fingerprint: string;
}

// ─── Comparison (spec §7.4) ──────────────────────────────────────────────────

export type CanvasComparisonKind = "ACTUAL_TO_TARGET" | "ACTUAL_TO_ACTUAL" | "TIME_TO_TIME";

/**
 * [COMPLETES SPEC] §7.4 enumerates eight distinctions a comparison must make. They
 * are not mutually exclusive per cell, so the contract carries counts plus one
 * headline status for the cell's treatment. `UNEVALUABLE` never becomes
 * non-conformance (§7.4 closing rule).
 */
export type CanvasComparisonCellStatus =
  | "ALIGNED"
  | "PREFERRED_IN_USE"
  | "ALLOWED_IN_USE"
  | "DISCOURAGED_IN_USE"
  | "PROHIBITED_IN_USE"
  | "REQUIRED_ABSENT"
  | "NOT_APPLICABLE"
  | "UNGOVERNED"
  | "UNEVALUABLE";

export interface CanvasCellComparison {
  cell_key: string;
  status: CanvasComparisonCellStatus;
  status_reason: string;
  counts: {
    preferred_in_use: number;
    allowed_in_use: number;
    discouraged_in_use: number;
    prohibited_in_use: number;
    required_absent: number;
  };
  /** Populated for ACTUAL_TO_ACTUAL and TIME_TO_TIME. */
  added_technologies: EntitySummary[];
  removed_technologies: EntitySummary[];
  unevaluable_reason: string | null;
}

export interface CanvasComparisonSummary {
  cells_total: number;
  by_status: Record<CanvasComparisonCellStatus, number>;
  /** Canonical cells excluded because the two sides are semantically incompatible (§12 Phase 5). */
  incompatible_cells: string[];
  excluded_extension_cells: string[];
}

export interface CanvasComparison {
  contract_version: "1.0.0";
  comparison_kind: CanvasComparisonKind;
  actual_projection_fingerprint: string;
  baseline_projection_fingerprint: string;
  cells: CanvasCellComparison[];
  summary: CanvasComparisonSummary;
  method_version: string;
  input_fingerprint: string;
}

export interface CanvasComparisonRequest {
  comparison_kind: CanvasComparisonKind;
  reference_model_key: string;
  reference_model_version: string;
  actual: { scope: CanvasScope; subject_id?: UUID; as_of?: Timestamp };
  baseline: { scope: CanvasScope; subject_id?: UUID; as_of?: Timestamp };
}

// ─── Tenant architecture profile (spec §5.3) ─────────────────────────────────

export interface TenantCellPolicy extends CellExpectation {
  cell_key: string;
  scope_selector: ScopeSelector;
  preferred_technology_ids: UUID[];
  allowed_technology_ids: UUID[];
  discouraged_technology_ids: UUID[];
  prohibited_technology_ids: UUID[];
  rationale: string;
  owner: string | null;
  effective_from: Timestamp | null;
  effective_to: Timestamp | null;
  exceptions: PolicyException[];
  /** Presentation overrides permitted by §5.3; never a rebinding. */
  display_label?: string | null;
  display_description?: string | null;
  hidden?: boolean;
}

/** [COMPLETES SPEC] Tenant-namespaced cell; rendered in a separate extension section (§5.3). */
export interface TenantExtensionCell {
  key: string;
  domain_key: ArchitectureDomainKey;
  label: string;
  definition: string;
  bindings: CanvasBinding[];
  default_expectation: CellExpectation;
}

export type TenantArchitectureProfileStatus = "DRAFT" | "ACTIVE" | "ARCHIVED";

export interface TenantArchitectureProfile {
  contract_version: "1.0.0";
  id: UUID;
  name: string;
  reference_model_key: string;
  reference_model_version: string;
  version: number;
  status: TenantArchitectureProfileStatus;
  cell_overrides: TenantCellPolicy[];
  extension_cells: TenantExtensionCell[];
  fingerprint: string;
  updated_by: string;
  updated_at: Timestamp;
}

export interface TenantArchitectureProfileList {
  contract_version: "1.0.0";
  profiles: TenantArchitectureProfile[];
}

export interface TenantArchitectureProfileCreateRequest {
  name: string;
  reference_model_key: string;
  reference_model_version: string;
  /** Copy the given revision's overrides into the new draft. */
  copy_from_profile_id?: UUID;
}

export interface TenantArchitectureProfileUpdateRequest {
  /** Optimistic concurrency, mirroring the business-map save contract. */
  expected_fingerprint: string;
  name?: string;
  cell_overrides?: TenantCellPolicy[];
  extension_cells?: TenantExtensionCell[];
}

// ─── UI-side policy intents (spec §9.2) ──────────────────────────────────────

/**
 * [COMPLETES SPEC] The renderer emits intents; the application layer validates
 * permissions, collects rationale, and calls the API (§9.2). Intents are UI-local —
 * they are not part of the wire contract, but they live here so the surfaces and the
 * package agree on one vocabulary.
 */
export type CanvasPolicyIntent =
  | {
      kind: "SET_TECHNOLOGY_DECISION";
      cell_key: string;
      technology_id: UUID;
      technology_name: string;
      decision: CanvasPolicyDecision | "UNGOVERNED";
    }
  | { kind: "PROMOTE_FROM_ACTUAL"; cell_key: string; technology_id: UUID; technology_name: string }
  | { kind: "SET_EXPECTATION"; cell_key: string; expectation: CellExpectation }
  | { kind: "EDIT_POLICY_DETAILS"; cell_key: string }
  | { kind: "RESOLVE_UNRESOLVED_POLICY"; policy_key: string; cell_key: string | null };
