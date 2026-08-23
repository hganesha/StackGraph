import type {
  CanvasCellState,
  ObservationStatus,
  CanvasComparisonCellStatus,
  CanvasOccupantPolicyStatus,
  CanvasPostureBand,
  CellApplicability,
  MeasureStatus,
} from "@stackgraph/shared";

/**
 * Every visual signal in the canvas has a text equivalent here. Cells render the
 * label alongside the tone, so state, policy, posture, and confidence are never
 * communicated by colour alone (spec §11.2).
 *
 * `tone` maps onto the four Strata tone classes in canvas.module.css. There is
 * deliberately no per-domain hue: domains are distinguished by label, icon, and
 * position, which keeps the colour budget for signal.
 */
export type CanvasTone = "neutral" | "positive" | "caution" | "danger" | "quiet";

export const CELL_STATE_LABEL: Record<CanvasCellState, string> = {
  POPULATED: "Populated",
  EMPTY: "None found",
  NOT_APPLICABLE: "Not applicable",
  UNOBSERVED: "Not observed",
  UNBOUND: "Not yet modelled",
};

export const CELL_STATE_DESCRIPTION: Record<CanvasCellState, string> = {
  POPULATED: "At least one implementation is evidenced here.",
  EMPTY: "Observation completed and found no implementation.",
  NOT_APPLICABLE: "A tenant or scope rule says this concern does not apply.",
  UNOBSERVED: "Required evidence is missing, stale, partial, or unsupported.",
  UNBOUND: "StackGraph has no supported sensor for this concern.",
};

/**
 * `EMPTY` is deliberately not a danger tone. An empty optional concern is a correct
 * result; severity comes from policy, not from emptiness (spec §11.2).
 */
export const CELL_STATE_TONE: Record<CanvasCellState, CanvasTone> = {
  POPULATED: "neutral",
  EMPTY: "neutral",
  NOT_APPLICABLE: "quiet",
  UNOBSERVED: "neutral",
  UNBOUND: "quiet",
};

export const POSTURE_LABEL: Record<CanvasPostureBand, string> = {
  STRONG: "Strong",
  ADEQUATE: "Adequate",
  WEAK: "Weak",
  AT_RISK: "At risk",
};

export const POSTURE_TONE: Record<CanvasPostureBand, CanvasTone> = {
  STRONG: "positive",
  ADEQUATE: "neutral",
  WEAK: "caution",
  AT_RISK: "danger",
};

/** Filled ticks out of five, matching the meter's rendering. */
export const POSTURE_TICKS: Record<CanvasPostureBand, number> = {
  STRONG: 5,
  ADEQUATE: 4,
  WEAK: 2,
  AT_RISK: 1,
};

export const POLICY_LABEL: Record<CanvasOccupantPolicyStatus, string> = {
  PREFERRED: "Preferred",
  ALLOWED: "Allowed",
  DISCOURAGED: "Discouraged",
  PROHIBITED: "Prohibited",
  // Carried by a policy exception rather than by the standing policy — a distinct
  // fact from "allowed", and one a reviewer needs to see.
  EXEMPTED: "Exempted",
  UNGOVERNED: "Ungoverned",
};

export const POLICY_TONE: Record<CanvasOccupantPolicyStatus, CanvasTone> = {
  PREFERRED: "positive",
  ALLOWED: "neutral",
  DISCOURAGED: "caution",
  PROHIBITED: "danger",
  // An exception is a deliberate, time-boxed decision, not a problem: caution, not danger.
  EXEMPTED: "caution",
  UNGOVERNED: "quiet",
};

export const APPLICABILITY_LABEL: Record<CellApplicability, string> = {
  REQUIRED: "Required",
  RECOMMENDED: "Recommended",
  OPTIONAL: "Optional",
  NOT_APPLICABLE: "Not applicable",
};

export const COMPARISON_LABEL: Record<CanvasComparisonCellStatus, string> = {
  ALIGNED: "Aligned",
  PREFERRED_IN_USE: "Preferred in use",
  ALLOWED_IN_USE: "Allowed in use",
  DISCOURAGED_IN_USE: "Discouraged in use",
  PROHIBITED_IN_USE: "Prohibited in use",
  REQUIRED_ABSENT: "Required but absent",
  NOT_APPLICABLE: "Not applicable",
  UNGOVERNED: "Ungoverned",
  UNEVALUABLE: "Cannot be evaluated",
};

/**
 * `UNEVALUABLE` is quiet, never danger: an incomplete observation must not read as
 * non-conformance (spec §7.4).
 */
export const COMPARISON_TONE: Record<CanvasComparisonCellStatus, CanvasTone> = {
  ALIGNED: "positive",
  PREFERRED_IN_USE: "positive",
  ALLOWED_IN_USE: "neutral",
  DISCOURAGED_IN_USE: "caution",
  PROHIBITED_IN_USE: "danger",
  REQUIRED_ABSENT: "caution",
  NOT_APPLICABLE: "quiet",
  UNGOVERNED: "quiet",
  UNEVALUABLE: "quiet",
};

export const MEASURE_STATUS_LABEL: Record<MeasureStatus, string> = {
  ELIGIBLE: "Measured",
  INSUFFICIENT_DATA: "Insufficient data",
  NOT_APPLICABLE: "Not applicable",
  NOT_CONFIGURED: "Not configured",
};

export const MEASURE_LABEL = {
  coverage: "Coverage",
  standardisation: "Standardisation",
  currency: "Currency",
  risk: "Risk",
  conformance: "Conformance",
} as const;

export const OBSERVATION_LABEL: Record<ObservationStatus, string> = {
  COMPLETE: "Complete",
  PARTIAL: "Partial",
  MISSING: "No observation",
  NOT_APPLICABLE: "Not applicable",
};
