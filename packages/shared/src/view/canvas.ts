// Architecture Canvas view models.
//
// The API publishes wire contracts in contracts/openapi.generated.ts. The renderer
// consumes the shapes below. They are deliberately not the same thing — components
// are never bound to raw read models (UX plan §7.2) — and this module is the only
// place the two meet.
//
// The mapping is not cosmetic. Three things happen here that a component must not do
// for itself:
//   * counts the wire summary does not carry are derived once, from the cells;
//   * technology identifiers in tenant policy are resolved to names, and the ones
//     that cannot be resolved are counted rather than rendered as raw UUIDs;
//   * a comparison's headline status is derived from its counters, so every surface
//     tells the same story about the same cell.

import type {
  ArchitectureCellDefinitionModel,
  ArchitectureProfileDetail,
  ArchitectureProfileList,
  ArchitectureProfileStateModel,
  ArchitectureProfileSummary,
  ArchitectureReferenceModel as ArchitectureReferenceModelWire,
  ArchitectureTaxonomyResponse,
  CanvasCellComparisonModel,
  CanvasCellProjectionModel,
  CanvasClassificationTrayItemModel,
  CanvasComparison as CanvasComparisonWire,
  CanvasOccupantModel,
  CanvasBandLayoutModel,
  CanvasComparisonRequest,
  CanvasProjection as CanvasProjectionWire,
  CanvasTemplateList,
  CanvasTemplateModel,
  CellExpectationModel,
  CellObservationStatusModel,
  MeasureResultModel,
  TenantCellPolicyModel,
  // Wire-side EntitySummary/Citation: these permit explicit nulls where the curated
  // facade permits only undefined, and the view model has to hold what actually
  // arrives rather than a narrower shape it wishes had arrived.
  Citation,
  EntitySummary,
} from "../contracts/openapi.generated";
import type { ConfidenceLabel } from "../contracts/read-models";

// ─── Re-exported wire types ──────────────────────────────────────────────────
// Surfaces that talk to the API (queries, mutations) use these directly.

export type {
  ArchitectureCellDefinitionModel,
  ArchitectureProfileDetail,
  ArchitectureProfileList,
  ArchitectureProfileStateModel,
  ArchitectureProfileSummary,
  ArchitectureTaxonomyResponse,
  CanvasBandLayoutModel,
  CanvasComparisonRequest,
  CanvasTemplateList,
  CanvasTemplateModel,
  CellExpectationModel,
  MeasureResultModel,
  TenantCellPolicyModel,
};
export type ArchitectureReferenceModelWireType = ArchitectureReferenceModelWire;
export type CanvasProjectionWireType = CanvasProjectionWire;
export type CanvasComparisonWireType = CanvasComparisonWire;

export type CanvasScope = "ESTATE" | "APPLICATION" | "REPOSITORY" | "TARGET";
export type CanvasCellState = "POPULATED" | "EMPTY" | "NOT_APPLICABLE" | "UNOBSERVED" | "UNBOUND";
export type CanvasPostureBand = "STRONG" | "ADEQUATE" | "WEAK" | "AT_RISK";
export type CellApplicability = "REQUIRED" | "RECOMMENDED" | "OPTIONAL" | "NOT_APPLICABLE";
export type MeasureStatus = "ELIGIBLE" | "INSUFFICIENT_DATA" | "NOT_APPLICABLE" | "NOT_CONFIGURED";
export type ObservationStatus = "COMPLETE" | "PARTIAL" | "MISSING" | "NOT_APPLICABLE";

/**
 * `EXEMPTED` exists on the wire and is not the same as `ALLOWED`: it means a policy
 * exception is carrying this technology, which is a fact a reviewer needs to see.
 */
export type CanvasOccupantPolicyStatus =
  | "PREFERRED"
  | "ALLOWED"
  | "DISCOURAGED"
  | "PROHIBITED"
  | "EXEMPTED"
  | "UNGOVERNED";

export type CanvasPolicyDecision = "PREFERRED" | "ALLOWED" | "DISCOURAGED" | "PROHIBITED";
export type ArchitectureDomainKey =
  | "experience" | "application" | "integration" | "data" | "platform" | "delivery";

// ─── Reference model view ────────────────────────────────────────────────────

export interface ArchitectureDomainView {
  key: ArchitectureDomainKey;
  label: string;
  question: string;
  order: number;
}

export interface ArchitectureAspectView {
  key: string;
  label: string;
  definition: string;
  order: number;
}

export interface ArchitectureCellView {
  key: string;
  concern_key: string;
  domain_key: ArchitectureDomainKey;
  label: string;
  definition: string;
  aspect_keys: string[];
  default_expectation: CellExpectationModel;
  observation_rule_key: string;
  required_sensor_kinds: string[];
  /** Whether `EMPTY` can ever be asserted here, or only `UNOBSERVED` (spec §4.8). */
  absence_assertable: boolean;
  /** Presentation only. Derived from the concern key; icons never cross the API boundary. */
  icon: string;
}

export interface ArchitectureReferenceModelView {
  key: string;
  version: string;
  name: string;
  description: string;
  taxonomy_key: string;
  taxonomy_version: string;
  content_hash: string;
  domains: ArchitectureDomainView[];
  aspects: ArchitectureAspectView[];
  cells: ArchitectureCellView[];
}

// ─── Projection view ─────────────────────────────────────────────────────────

export interface CanvasOccupantView {
  technology: EntitySummary;
  placement_keys: string[];
  classification: CanvasOccupantModel["classification"];
  confidence: number;
  confidence_label: ConfidenceLabel;
  adoption: { applications: number; repositories: number; deployments: number };
  policy_status: CanvasOccupantPolicyStatus;
  policy_reference: string | null;
  citations: Citation[];
}

/**
 * Occupants that are the same package at different resolved versions.
 *
 * A technology entity is a resolved coordinate, so `react@18.3.1` and `react@16.14.0`
 * arrive as two occupants of one cell. Listing every version flat is what makes a
 * populated cell unreadable — and it buries the thing that matters, because version
 * spread is usually a single fact ("we are on three Reacts"), not three facts.
 */
export interface CanvasOccupantGroupView {
  /** Version-less package identity: the purl coordinate where there is one. */
  key: string;
  label: string;
  members: CanvasOccupantView[];
  /** Resolved versions, newest-looking first. Empty when none could be parsed. */
  versions: string[];
  /**
   * The most severe status any version holds. A group whose newest version is
   * preferred and whose oldest is prohibited is a governance problem, and the headline
   * must not launder it.
   */
  policy_status: CanvasOccupantPolicyStatus;
  /** Union is unknowable from per-version counts; the largest member is the floor. */
  adoption: { applications: number; repositories: number; deployments: number };
  confidence: number;
  confidence_label: ConfidenceLabel;
  classification: CanvasOccupantModel["classification"];
}

export interface CanvasPolicyDecisionView {
  technology: EntitySummary;
  decision: CanvasPolicyDecision;
  /** False when only an identifier was available; the panel says so rather than showing a UUID. */
  resolved: boolean;
}

export interface CanvasCellPolicyView {
  governed: boolean;
  decisions: CanvasPolicyDecisionView[];
  unresolved_decision_count: number;
  exceptions: Array<{
    key: string;
    rationale: string;
    subject_ids: string[];
    effective_from: string | null;
    effective_to: string | null;
  }>;
  rationale: string | null;
  owner: string | null;
  effective_from: string | null;
  effective_to: string | null;
  scope_selector: TenantCellPolicyModel["scope_selector"] | null;
}

export interface EffectiveCellExpectationView {
  applicability: CellApplicability;
  minimum_implementations: number | null;
  maximum_implementations: number | null;
  allowed_diversity: number | null;
  /** Inferred: an expectation accompanied by a tenant policy came from the profile. */
  source: "REFERENCE_MODEL" | "TENANT_PROFILE";
  rationale: string | null;
  owner: string | null;
  effective_from: string | null;
  effective_to: string | null;
}

export interface CellObservationView {
  rule_key: string;
  status: ObservationStatus;
  required_sensor_kinds: string[];
  supported_sensor_kinds: string[];
  subjects_in_scope: number;
  subjects_observed: number;
  subjects_fresh: number;
  missing_inputs: string[];
  method_version: string;
  input_fingerprint: string;
}

export interface CanvasCellMeasuresView {
  posture_band: CanvasPostureBand | null;
  overall_score: number | null;
  components: {
    coverage: MeasureResultModel;
    standardisation: MeasureResultModel;
    currency: MeasureResultModel;
    risk: MeasureResultModel;
    conformance: MeasureResultModel;
  };
  confidence: number;
  confidence_label: ConfidenceLabel;
  method_version: string;
  missing_inputs: string[];
}

export interface CanvasCellProjectionView {
  cell_key: string;
  state: CanvasCellState;
  state_reason: string;
  occupants: CanvasOccupantView[];
  /** Occupants folded by package. One entry per package, however many versions. */
  occupant_groups: CanvasOccupantGroupView[];
  occupant_total: number;
  unique_technology_total: number;
  observation: CellObservationView;
  expectation: EffectiveCellExpectationView;
  measures: CanvasCellMeasuresView | null;
  policy: CanvasCellPolicyView | null;
  insight_refs: string[];
  citations: Citation[];
}

export type CanvasTrayReason = "UNCLASSIFIED" | "AMBIGUOUS" | "UNRESOLVED_POLICY" | "FILTERED";

export interface CanvasTrayItemView {
  entity: EntitySummary;
  reason: CanvasTrayReason;
  detail: string;
  citations: Citation[];
}

export interface CanvasClassificationTrayView {
  items: CanvasTrayItemView[];
  byReason: Record<CanvasTrayReason, CanvasTrayItemView[]>;
  counts: Record<CanvasTrayReason, number>;
  total: number;
  /** The server withheld items. Surfaced, because §6.3 forbids dropping silently. */
  truncated: boolean;
}

export interface CanvasProjectionSummaryView {
  cells_total: number;
  by_state: Record<CanvasCellState, number>;
  by_posture_band: Record<CanvasPostureBand, number> & { UNSCORED: number };
  by_policy_status: Record<CanvasOccupantPolicyStatus, number>;
  unique_technologies: number;
  placements_total: number;
  governed_cells: number;
  cells_with_violations: number;
}

export interface CanvasProjectionView {
  as_of: string;
  method_version: string;
  taxonomy_key: string;
  taxonomy_version: string;
  reference_model_key: string;
  reference_model_version: string;
  template_key: string;
  template_version: string;
  tenant_profile_fingerprint: string | null;
  scope: CanvasScope;
  subject: EntitySummary | null;
  cells: CanvasCellProjectionView[];
  classification_tray: CanvasClassificationTrayView;
  summary: CanvasProjectionSummaryView;
  input_fingerprint: string;
}

// ─── Comparison view ─────────────────────────────────────────────────────────

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

export interface CanvasCellComparisonView {
  cell_key: string;
  status: CanvasComparisonCellStatus;
  status_reason: string;
  actual_state: CanvasCellState;
  baseline_state: CanvasCellState;
  counts: {
    preferred_in_use: number;
    allowed_in_use: number;
    discouraged_in_use: number;
    prohibited_in_use: number;
    ungoverned_in_use: number;
  };
  required_but_absent: boolean;
  unevaluable: boolean;
}

export interface CanvasComparisonView {
  comparison_kind: "ACTUAL_TO_TARGET" | "ACTUAL_TO_ACTUAL";
  cells: CanvasCellComparisonView[];
  summary: CanvasComparisonWire["summary"];
  method_version: string;
  input_fingerprint: string;
}

// ─── Icon derivation ─────────────────────────────────────────────────────────

/**
 * Reference-model cells carry no icon: colour and glyph choices do not cross the API
 * boundary (spec §5.2). The concern key is the stable semantic handle, so the icon is
 * derived from it here and validated by the UI package's registry.
 */
export function iconForConcern(concernKey: string): string {
  const leaf = concernKey.split(".").pop() ?? concernKey;
  return leaf;
}

// ─── Adapters ────────────────────────────────────────────────────────────────

export function toReferenceModelView(
  model: ArchitectureReferenceModelWire,
  taxonomy: ArchitectureTaxonomyResponse,
): ArchitectureReferenceModelView {
  const concernDomain = new Map(taxonomy.concerns.map((c) => [c.key, c.domain_key]));
  return {
    key: model.key,
    version: model.version,
    name: model.name,
    description: model.description,
    taxonomy_key: model.taxonomy_key,
    taxonomy_version: model.taxonomy_version,
    content_hash: model.content_hash,
    domains: [...taxonomy.domains]
      .sort((a, b) => a.order - b.order)
      .map((d) => ({ key: d.key, label: d.label, question: d.question, order: d.order })),
    aspects: taxonomy.aspects.map((a, index) => ({
      key: a.key,
      label: a.label,
      definition: a.definition,
      order: index,
    })),
    cells: model.cells.map((cell) => toCellView(cell, concernDomain)),
  };
}

function toCellView(
  cell: ArchitectureCellDefinitionModel,
  concernDomain: Map<string, ArchitectureDomainKey>,
): ArchitectureCellView {
  return {
    key: cell.key,
    concern_key: cell.concern_key,
    // The wire cell has no domain; it is reachable only through its concern.
    domain_key: concernDomain.get(cell.concern_key) ?? "application",
    label: cell.label,
    definition: cell.definition,
    aspect_keys: cell.aspect_keys ?? [],
    default_expectation: cell.default_expectation,
    observation_rule_key: cell.observation_rule_key,
    required_sensor_kinds: cell.required_sensor_kinds ?? [],
    absence_assertable: cell.absence_assertable ?? false,
    icon: iconForConcern(cell.concern_key),
  };
}

function toOccupantView(occupant: CanvasOccupantModel): CanvasOccupantView {
  return {
    technology: occupant.technology,
    placement_keys: occupant.placement_keys,
    classification: occupant.classification,
    confidence: occupant.confidence,
    confidence_label: occupant.confidence_label,
    adoption: {
      applications: occupant.adoption_applications,
      repositories: occupant.adoption_repositories,
      deployments: occupant.adoption_deployments,
    },
    policy_status: occupant.policy_status,
    policy_reference: occupant.policy_reference ?? null,
    citations: occupant.citations ?? [],
  };
}

// ─── Version grouping ────────────────────────────────────────────────────────

/** Severity order: a group takes its headline from its worst member, never its newest. */
const POLICY_SEVERITY: CanvasOccupantPolicyStatus[] = [
  "PROHIBITED",
  "DISCOURAGED",
  "EXEMPTED",
  "UNGOVERNED",
  "ALLOWED",
  "PREFERRED",
];

/**
 * Splits a technology into its package identity and resolved version.
 *
 * Prefers the purl coordinate, which is authoritative, and falls back to a trailing
 * `@version` on the display name. Anything unparseable is its own group of one — an
 * unrecognised naming scheme must not silently merge two different technologies.
 */
export function splitPackageVersion(technology: EntitySummary): {
  key: string;
  label: string;
  version: string | null;
} {
  const purl = technology.canonical_key ?? "";
  if (purl.startsWith("pkg:")) {
    const at = purl.lastIndexOf("@");
    // A scoped npm package starts with @, so only a later one delimits the version.
    const slash = purl.indexOf("/");
    if (at > slash && at !== -1) {
      const coordinate = purl.slice(0, at);
      const label = technology.name.replace(/@[^@]*$/, "").trim() || coordinate;
      return { key: coordinate, label, version: purl.slice(at + 1) };
    }
    return { key: purl, label: technology.name, version: null };
  }
  const match = /^(.*?)@([^@]+)$/.exec(technology.name);
  if (match && match[1].trim()) {
    return { key: `name:${match[1].trim().toLowerCase()}`, label: match[1].trim(), version: match[2] };
  }
  return { key: technology.id, label: technology.name, version: null };
}

/** Descending version sort, numeric where the segments are numeric. */
function compareVersions(a: string, b: string): number {
  const parse = (value: string) => value.split(/[.\-+]/).map((part) => (/^\d+$/.test(part) ? Number(part) : part));
  const left = parse(a);
  const right = parse(b);
  for (let index = 0; index < Math.max(left.length, right.length); index += 1) {
    const l = left[index];
    const r = right[index];
    if (l === undefined) return 1;
    if (r === undefined) return -1;
    if (l === r) continue;
    if (typeof l === "number" && typeof r === "number") return r - l;
    return String(r).localeCompare(String(l));
  }
  return 0;
}

export function groupOccupants(occupants: CanvasOccupantView[]): CanvasOccupantGroupView[] {
  const groups = new Map<string, { label: string; members: CanvasOccupantView[]; versions: string[] }>();
  for (const occupant of occupants) {
    const { key, label, version } = splitPackageVersion(occupant.technology);
    const group = groups.get(key) ?? { label, members: [], versions: [] };
    group.members.push(occupant);
    if (version) group.versions.push(version);
    groups.set(key, group);
  }

  return [...groups.entries()].map(([key, group]) => {
    const severity = Math.min(
      ...group.members.map((member) => POLICY_SEVERITY.indexOf(member.policy_status)),
    );
    const confidence = Math.min(...group.members.map((member) => member.confidence));
    return {
      key,
      label: group.label,
      members: [...group.members].sort((a, b) => {
        const av = splitPackageVersion(a.technology).version;
        const bv = splitPackageVersion(b.technology).version;
        if (av && bv) return compareVersions(av, bv);
        return a.technology.name.localeCompare(b.technology.name);
      }),
      versions: [...new Set(group.versions)].sort(compareVersions),
      policy_status: POLICY_SEVERITY[severity] ?? "UNGOVERNED",
      adoption: {
        applications: Math.max(...group.members.map((m) => m.adoption.applications)),
        repositories: Math.max(...group.members.map((m) => m.adoption.repositories)),
        deployments: Math.max(...group.members.map((m) => m.adoption.deployments)),
      },
      confidence,
      confidence_label: confidence >= 0.85 ? "HIGH" : confidence >= 0.6 ? "MEDIUM" : "LOW",
      classification: group.members[0].classification,
    };
  });
}

function toObservationView(
  observation: CellObservationStatusModel,
  ruleKey: string,
): CellObservationView {
  return {
    rule_key: ruleKey,
    status: observation.status,
    required_sensor_kinds: observation.required_sensor_kinds,
    supported_sensor_kinds: observation.supported_sensor_kinds,
    subjects_in_scope: observation.in_scope_subjects,
    subjects_observed: observation.observed_subjects,
    subjects_fresh: observation.fresh_subjects,
    missing_inputs: observation.missing_inputs,
    method_version: observation.method_version,
    input_fingerprint: observation.input_fingerprint,
  };
}

const DECISION_FIELDS: Array<[CanvasPolicyDecision, keyof TenantCellPolicyModel]> = [
  ["PREFERRED", "preferred_technology_ids"],
  ["ALLOWED", "allowed_technology_ids"],
  ["DISCOURAGED", "discouraged_technology_ids"],
  ["PROHIBITED", "prohibited_technology_ids"],
];

function toPolicyView(
  policy: TenantCellPolicyModel | null | undefined,
  names: Map<string, EntitySummary>,
): CanvasCellPolicyView | null {
  if (!policy) return null;
  const decisions: CanvasPolicyDecisionView[] = [];
  let unresolved = 0;
  for (const [decision, field] of DECISION_FIELDS) {
    for (const id of (policy[field] as string[] | undefined) ?? []) {
      const known = names.get(id);
      if (!known) unresolved += 1;
      decisions.push({
        technology: known ?? { id, kind: "Technology", name: `Unnamed technology · ${id.slice(0, 8)}` },
        decision,
        resolved: Boolean(known),
      });
    }
  }
  return {
    governed: decisions.length > 0,
    decisions,
    unresolved_decision_count: unresolved,
    exceptions: (policy.exceptions ?? []).map((exception) => ({
      key: exception.key,
      rationale: exception.rationale,
      subject_ids: exception.subject_ids,
      effective_from: exception.effective_from ?? null,
      effective_to: exception.effective_to ?? null,
    })),
    rationale: policy.rationale || null,
    owner: policy.owner ?? null,
    effective_from: policy.effective_from ?? null,
    effective_to: policy.effective_to ?? null,
    scope_selector: policy.scope_selector ?? null,
  };
}

function toExpectationView(
  expectation: CellExpectationModel,
  policy: TenantCellPolicyModel | null | undefined,
): EffectiveCellExpectationView {
  return {
    applicability: expectation.applicability ?? "OPTIONAL",
    minimum_implementations: expectation.minimum_implementations ?? null,
    maximum_implementations: expectation.maximum_implementations ?? null,
    allowed_diversity: expectation.allowed_diversity ?? null,
    // The wire carries no provenance, but a cell that has a tenant policy has an
    // expectation that came from the profile. Inferred, and labelled as such.
    source: policy ? "TENANT_PROFILE" : "REFERENCE_MODEL",
    rationale: policy?.rationale || null,
    owner: policy?.owner ?? null,
    effective_from: policy?.effective_from ?? null,
    effective_to: policy?.effective_to ?? null,
  };
}

function toMeasuresView(
  measures: CanvasCellProjectionModel["measures"],
): CanvasCellMeasuresView | null {
  if (!measures) return null;
  return {
    posture_band: measures.posture_band ?? null,
    overall_score: measures.overall_score ?? null,
    components: {
      coverage: measures.coverage,
      standardisation: measures.standardisation,
      currency: measures.currency,
      risk: measures.risk,
      conformance: measures.conformance,
    },
    confidence: measures.confidence,
    confidence_label: measures.confidence_label,
    method_version: measures.method_version,
    missing_inputs: measures.missing_inputs,
  };
}

const TRAY_REASONS: CanvasTrayReason[] = ["UNCLASSIFIED", "AMBIGUOUS", "UNRESOLVED_POLICY", "FILTERED"];

function toTrayView(
  tray: CanvasProjectionWire["classification_tray"],
): CanvasClassificationTrayView {
  const items: CanvasTrayItemView[] = (tray.items ?? []).map(
    (item: CanvasClassificationTrayItemModel) => ({
      entity: item.entity,
      reason: item.reason,
      detail: item.detail,
      citations: item.citations ?? [],
    }),
  );
  const byReason = Object.fromEntries(
    TRAY_REASONS.map((reason) => [reason, items.filter((item) => item.reason === reason)]),
  ) as Record<CanvasTrayReason, CanvasTrayItemView[]>;
  return {
    items,
    byReason,
    // Server counts win over what the item list happens to contain: when the list is
    // truncated they are the only honest total.
    counts: {
      UNCLASSIFIED: tray.unclassified_count,
      AMBIGUOUS: tray.ambiguous_count,
      UNRESOLVED_POLICY: tray.unresolved_policy_count,
      FILTERED: tray.filtered_count,
    },
    total: tray.total_count,
    truncated: tray.truncated,
  };
}

/** Names for every technology the projection mentions, for resolving policy ids. */
function technologyIndex(projection: CanvasProjectionWire): Map<string, EntitySummary> {
  const index = new Map<string, EntitySummary>();
  for (const cell of projection.cells) {
    for (const occupant of cell.occupants) index.set(occupant.technology.id, occupant.technology);
  }
  for (const item of projection.classification_tray.items ?? []) {
    index.set(item.entity.id, item.entity);
  }
  return index;
}

export function toProjectionView(projection: CanvasProjectionWire): CanvasProjectionView {
  const names = technologyIndex(projection);
  const cells = projection.cells.map((cell: CanvasCellProjectionModel) => {
    const occupants = cell.occupants.map(toOccupantView);
    return {
    cell_key: cell.cell_key,
    state: cell.state,
    state_reason: cell.state_reason,
    occupants,
    occupant_groups: groupOccupants(occupants),
    occupant_total: cell.occupant_total,
    unique_technology_total: cell.unique_technology_total,
    observation: toObservationView(cell.observation, cell.cell_key),
    expectation: toExpectationView(cell.expectation, cell.policy),
    measures: toMeasuresView(cell.measures),
    policy: toPolicyView(cell.policy, names),
    insight_refs: cell.insight_refs,
    citations: cell.citations,
    };
  });

  const summary = projection.summary;
  const byPolicyStatus: Record<CanvasOccupantPolicyStatus, number> = {
    PREFERRED: 0, ALLOWED: 0, DISCOURAGED: 0, PROHIBITED: 0, EXEMPTED: 0, UNGOVERNED: 0,
  };
  for (const cell of cells) {
    for (const occupant of cell.occupants) byPolicyStatus[occupant.policy_status] += 1;
  }
  const banded = summary.strong + summary.adequate + summary.weak + summary.at_risk;

  return {
    as_of: projection.as_of,
    method_version: projection.method_version,
    taxonomy_key: projection.taxonomy_key,
    taxonomy_version: projection.taxonomy_version,
    reference_model_key: projection.reference_model_key,
    reference_model_version: projection.reference_model_version,
    template_key: projection.template_key,
    template_version: projection.template_version,
    tenant_profile_fingerprint: projection.tenant_profile_fingerprint ?? null,
    scope: projection.scope,
    subject: projection.subject ?? null,
    cells,
    classification_tray: toTrayView(projection.classification_tray),
    summary: {
      cells_total:
        summary.populated_cells + summary.empty_cells + summary.not_applicable_cells +
        summary.unobserved_cells + summary.unbound_cells,
      by_state: {
        POPULATED: summary.populated_cells,
        EMPTY: summary.empty_cells,
        NOT_APPLICABLE: summary.not_applicable_cells,
        UNOBSERVED: summary.unobserved_cells,
        UNBOUND: summary.unbound_cells,
      },
      by_posture_band: {
        STRONG: summary.strong,
        ADEQUATE: summary.adequate,
        WEAK: summary.weak,
        AT_RISK: summary.at_risk,
        // A populated cell with no eligible composite is unscored, not zero.
        UNSCORED: Math.max(0, summary.populated_cells - banded),
      },
      by_policy_status: byPolicyStatus,
      unique_technologies: summary.unique_technologies,
      placements_total: summary.technology_cell_placements,
      governed_cells: summary.governed_cells,
      cells_with_violations: summary.cells_with_violations,
    },
    input_fingerprint: projection.input_fingerprint,
  };
}

/**
 * The wire comparison carries counters, not a verdict. The headline is derived here so
 * every surface tells the same story about the same cell — and so the one rule that
 * matters cannot be broken by a caller: an unevaluable cell is never non-conformance
 * (spec §7.4).
 */
function comparisonStatus(cell: CanvasCellComparisonModel): {
  status: CanvasComparisonCellStatus;
  reason: string;
} {
  if (cell.unevaluable) {
    return { status: "UNEVALUABLE", reason: "Observation is incomplete, so conformance cannot be asserted." };
  }
  if (cell.actual_state === "NOT_APPLICABLE" || cell.baseline_state === "NOT_APPLICABLE") {
    return { status: "NOT_APPLICABLE", reason: "The concern does not apply to this scope." };
  }
  if (cell.prohibited_in_use > 0) {
    return {
      status: "PROHIBITED_IN_USE",
      reason: `${cell.prohibited_in_use} prohibited technolog${cell.prohibited_in_use === 1 ? "y" : "ies"} in use.`,
    };
  }
  if (cell.required_but_absent) {
    return { status: "REQUIRED_ABSENT", reason: "A required concern has no observed implementation." };
  }
  if (cell.discouraged_in_use > 0) {
    return {
      status: "DISCOURAGED_IN_USE",
      reason: `${cell.discouraged_in_use} discouraged technolog${cell.discouraged_in_use === 1 ? "y" : "ies"} still in use.`,
    };
  }
  const governed = cell.preferred_in_use + cell.allowed_in_use;
  if (governed === 0 && cell.ungoverned_in_use > 0) {
    return { status: "UNGOVERNED", reason: "No target decision covers what is in use here." };
  }
  if (cell.preferred_in_use > 0 && cell.allowed_in_use === 0) {
    return { status: "PREFERRED_IN_USE", reason: "Only preferred technologies are in use." };
  }
  if (cell.allowed_in_use > 0) {
    return { status: "ALLOWED_IN_USE", reason: "In-use technologies are allowed but not preferred." };
  }
  return { status: "ALIGNED", reason: "Observed state matches the target." };
}

export function toComparisonView(comparison: CanvasComparisonWire): CanvasComparisonView {
  return {
    comparison_kind: comparison.comparison_kind,
    cells: comparison.cells.map((cell) => {
      const { status, reason } = comparisonStatus(cell);
      return {
        cell_key: cell.cell_key,
        status,
        status_reason: reason,
        actual_state: cell.actual_state,
        baseline_state: cell.baseline_state,
        counts: {
          preferred_in_use: cell.preferred_in_use,
          allowed_in_use: cell.allowed_in_use,
          discouraged_in_use: cell.discouraged_in_use,
          prohibited_in_use: cell.prohibited_in_use,
          ungoverned_in_use: cell.ungoverned_in_use,
        },
        required_but_absent: cell.required_but_absent,
        unevaluable: cell.unevaluable,
      };
    }),
    summary: comparison.summary,
    method_version: comparison.method_version,
    input_fingerprint: comparison.input_fingerprint,
  };
}

// ─── Profile helpers ─────────────────────────────────────────────────────────

/** Builds the full-state update body the API expects from an edited policy list. */
export function toProfileUpdateState(
  detail: ArchitectureProfileDetail,
  cellPolicies: TenantCellPolicyModel[],
): ArchitectureProfileStateModel {
  return {
    name: detail.state.name,
    reference_model_key: detail.reference_model_key,
    reference_model_version: detail.reference_model_version,
    cell_policies: cellPolicies,
    extension_cells: detail.state.extension_cells ?? [],
  };
}


// ─── UI-side policy intents (spec §9.2) ──────────────────────────────────────

/**
 * The renderer emits intents; the application layer validates permissions, collects
 * rationale, and calls the API. Intents are UI-local — not part of the wire contract —
 * but they live here so the surfaces and the package agree on one vocabulary.
 */
export type CanvasPolicyIntent =
  | {
      kind: "SET_TECHNOLOGY_DECISION";
      cell_key: string;
      technology_id: string;
      technology_name: string;
      decision: CanvasPolicyDecision | "UNGOVERNED";
    }
  | { kind: "PROMOTE_FROM_ACTUAL"; cell_key: string; technology_id: string; technology_name: string }
  | { kind: "SET_EXPECTATION"; cell_key: string; expectation: CellExpectationModel }
  | { kind: "EDIT_POLICY_DETAILS"; cell_key: string }
  | { kind: "RESOLVE_UNRESOLVED_POLICY"; policy_key: string; cell_key: string | null };
