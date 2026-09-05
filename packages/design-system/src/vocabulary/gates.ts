/**
 * The blocking vocabulary.
 *
 * Everything else in the design system is advisory. Tones describe a state — an
 * `EMPTY` cell is a correct result, an `UNEVALUABLE` cell is quiet, and severity
 * comes from policy rather than from emptiness. That restraint is right for a
 * system that *describes* an estate, and it is insufficient for one that **gates
 * changes to it** (recommendations §11.2).
 *
 * A gate is therefore not a louder tone. It is a different class of object: a
 * `danger` chip on a table row and a wall that stops you submitting a change must
 * not look the same, or the chip becomes unreadable and the wall becomes skippable.
 *
 * Three rules travel with this module, and they are review gates on every surface
 * that renders one:
 *
 *   1. A gate always names the *specific* blocking entity or contradiction, and
 *      links to its evidence. "Something is unresolved" is not a gate.
 *   2. A gate is never dismissible.
 *   3. `BLOCKED` and `ESCALATE` own the only filled surfaces in the product. No
 *      other component may fill, and a gate never uses the domain ramps.
 */
export type GateVerdict = "BLOCKED" | "ESCALATE" | "CONSTRAIN" | "CLEAR";

export const GATE_LABEL: Record<GateVerdict, string> = {
  BLOCKED: "Blocked",
  ESCALATE: "Needs approval",
  CONSTRAIN: "Narrowed",
  CLEAR: "Nothing in the way",
};

export const GATE_DESCRIPTION: Record<GateVerdict, string> = {
  BLOCKED: "Cannot proceed. A required input is unresolved or contradicted.",
  ESCALATE: "Can proceed once a named approver signs off.",
  CONSTRAIN: "Can proceed, but narrower than you asked for.",
  CLEAR: "Nothing is in the way.",
};

/**
 * `CLEAR` renders nothing at all — absence is the signal. Anything mapping a verdict
 * to a component honours that, so it is stated here once rather than re-decided on
 * each surface.
 */
export const GATE_RENDERS: Record<GateVerdict, boolean> = {
  BLOCKED: true,
  ESCALATE: true,
  CONSTRAIN: true,
  CLEAR: false,
};
