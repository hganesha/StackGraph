/**
 * Labels for the Phase 2 change vocabulary.
 *
 * The rule these exist to keep: no identifier, version string, or `SCREAMING_SNAKE`
 * enum ever reaches a user-facing surface. `NOT_SIMULATABLE` rendered through
 * `replaceAll("_", " ")` becomes "NOT SIMULATABLE", and `.toLowerCase()` becomes
 * "not simulatable" — both are a machine talking. Sentence case, always, and the enum
 * keeps its place on a `title` for anyone filing a bug.
 *
 * Every map here is exhaustive over its contract enum, so adding a value to the
 * contract is a type error here rather than a shrug on screen.
 */

/** `SimulationRunModel.status`. */
export type SimulationRunStatus =
  | "QUEUED"
  | "RUNNING"
  | "SUCCEEDED"
  | "LIMITED"
  | "NOT_SIMULATABLE"
  | "FAILED"
  | "CANCELLED";

export const SIMULATION_STATUS_LABEL: Record<SimulationRunStatus, string> = {
  QUEUED: "Queued",
  RUNNING: "Running",
  SUCCEEDED: "Complete",
  LIMITED: "Complete, reduced coverage",
  NOT_SIMULATABLE: "Cannot be simulated",
  FAILED: "Failed",
  CANCELLED: "Cancelled",
};

/**
 * `LIMITED` and `NOT_SIMULATABLE` are not failures and must not read as one:
 * a run that completed with reduced coverage, and a run that honestly reports it
 * cannot answer the question, are both correct results.
 */
export const SIMULATION_STATUS_IS_TERMINAL: Record<SimulationRunStatus, boolean> = {
  QUEUED: false,
  RUNNING: false,
  SUCCEEDED: true,
  LIMITED: true,
  NOT_SIMULATABLE: true,
  FAILED: true,
  CANCELLED: true,
};

/** `SimulationInterpretation.status`. */
export type InterpretationStatus = "AVAILABLE" | "UNAVAILABLE" | "QUARANTINED";

export const INTERPRETATION_STATUS_LABEL: Record<InterpretationStatus, string> = {
  AVAILABLE: "AI interpretation",
  UNAVAILABLE: "AI interpretation unavailable",
  QUARANTINED: "AI interpretation withheld",
};

/**
 * Why the interpretation half of the partition is empty. The findings half is identical
 * in all three cases — that is the guarantee — so the reader is told which of the three
 * they are looking at rather than left to guess.
 */
export const INTERPRETATION_STATUS_DESCRIPTION: Record<InterpretationStatus, string> = {
  AVAILABLE: "Read against the findings above, which it cites.",
  UNAVAILABLE: "AI was switched off or did not answer. The findings above are unchanged.",
  QUARANTINED:
    "The interpretation could not cite the findings above, so it is withheld rather than shown. The findings above are unchanged.",
};

/** `SimulationFinding.classification`. */
export type ImpactClassification =
  | "DIRECT"
  | "TRANSITIVE"
  | "CONTEXT"
  | "STOP"
  | "INFORMATIONAL";

export const CLASSIFICATION_LABEL: Record<ImpactClassification, string> = {
  DIRECT: "Directly affected",
  TRANSITIVE: "Affected through a dependency",
  CONTEXT: "Context",
  STOP: "Traversal stopped here",
  INFORMATIONAL: "Informational",
};

export const CLASSIFICATION_DESCRIPTION: Record<ImpactClassification, string> = {
  DIRECT: "The change lands on this entity itself.",
  TRANSITIVE: "Reached by following a dependency the policy allows.",
  CONTEXT: "Not affected, but needed to read the result.",
  STOP: "The policy deliberately stopped looking here, and why.",
  INFORMATIONAL: "Sits outside the impact set and is never counted as impact.",
};

/** `ActionTypeSummary.predicate` and `MutationIR.predicate`. */
export type ChangePredicate =
  | "UPGRADE"
  | "REPLACE"
  | "REMOVE"
  | "DEPRECATE"
  | "MIGRATE"
  | "MOVE";

export const PREDICATE_LABEL: Record<ChangePredicate, string> = {
  UPGRADE: "Upgrade",
  REPLACE: "Replace",
  REMOVE: "Remove",
  DEPRECATE: "Deprecate",
  MIGRATE: "Migrate",
  MOVE: "Move",
};

/** `MutationCompileResult.command_state`. */
export type CommandState = "EMPTY" | "RESOLVING" | "TOKENISED" | "COMPILED";

export const COMMAND_STATE_LABEL: Record<CommandState, string> = {
  EMPTY: "Start typing",
  RESOLVING: "Matching your estate",
  TOKENISED: "Subject chosen",
  COMPILED: "Ready to simulate",
};

/** `MutationIR.lifecycle` and `ChangeSetModel.lifecycle`. */
export type MutationLifecycle =
  | "DRAFT"
  | "VALIDATED"
  | "REJECTED"
  | "SUPERSEDED"
  | "SUBMITTED"
  | "EXECUTED"
  | "CANCELLED";

export const MUTATION_LIFECYCLE_LABEL: Record<MutationLifecycle, string> = {
  DRAFT: "Draft",
  VALIDATED: "Validated",
  REJECTED: "Rejected",
  SUPERSEDED: "Superseded",
  SUBMITTED: "Submitted",
  EXECUTED: "Executed",
  CANCELLED: "Cancelled",
};

/** `ValidTarget.support` and `ValidTarget.freshness` — two independent axes. */
export type TargetSupport = "SUPPORTED" | "UNKNOWN" | "UNSUPPORTED";

export const TARGET_SUPPORT_LABEL: Record<TargetSupport, string> = {
  SUPPORTED: "Supported",
  UNKNOWN: "Support unknown",
  UNSUPPORTED: "Unsupported",
};

export type TargetFreshness = "FRESH" | "STALE" | "UNKNOWN";

export const TARGET_FRESHNESS_LABEL: Record<TargetFreshness, string> = {
  FRESH: "Checked recently",
  STALE: "Last checked a while ago",
  UNKNOWN: "Never checked",
};
