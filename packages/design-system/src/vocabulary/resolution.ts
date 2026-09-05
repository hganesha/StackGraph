/**
 * Resolution state — is this the thing you meant?
 *
 * Deliberately **not** confidence, and the two must never be collapsed into one
 * control. An entity can be resolved with certainty and still rest on a
 * low-confidence fact; it can be ambiguous between two candidates that are each
 * perfectly well evidenced. Confidence answers "how well is this known"; resolution
 * answers "is this the thing you meant" (recommendations R12).
 *
 * Strata already encodes epistemic status in type, so resolution takes the
 * typographic channel rather than a new hue: a resolved subject is a scanned
 * coordinate and renders mono; an inferred one is StackGraph's reading and renders
 * sans, always carrying its candidate count; an unresolved one is struck through and
 * carries its reason.
 *
 * The safety rule this exists to enforce: no inferred or unresolved entity may enter
 * a simulation silently. A resolved-looking chip over an ambiguous match is the most
 * dangerous single thing this product can render.
 */
export type ResolutionState = "RESOLVED" | "INFERRED" | "UNRESOLVED";

export const RESOLUTION_LABEL: Record<ResolutionState, string> = {
  RESOLVED: "Resolved",
  INFERRED: "Inferred",
  UNRESOLVED: "Unresolved",
};

export const RESOLUTION_DESCRIPTION: Record<ResolutionState, string> = {
  RESOLVED: "Matched to exactly one thing in your estate.",
  INFERRED: "Matched to more than one candidate. Choose which one you meant.",
  UNRESOLVED: "Nothing in your estate matches this.",
};

/**
 * Resolution carries no colour of its own — the tone is here only so a surface that
 * already speaks in tones has a correct answer, and so the axis inherits the "every
 * visual signal has a text equivalent" guarantee. `INFERRED` is caution rather than
 * danger: an ambiguous match is a question, not a fault.
 */
export const RESOLUTION_TONE: Record<ResolutionState, "neutral" | "caution" | "danger"> = {
  RESOLVED: "neutral",
  INFERRED: "caution",
  UNRESOLVED: "danger",
};

/** An inferred or unresolved subject cannot silently proceed into a mutation. */
export const RESOLUTION_BLOCKS: Record<ResolutionState, boolean> = {
  RESOLVED: false,
  INFERRED: false,
  UNRESOLVED: true,
};
