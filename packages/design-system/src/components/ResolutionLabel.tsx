import type { ReactNode } from "react";
import {
  RESOLUTION_DESCRIPTION,
  RESOLUTION_LABEL,
  type ResolutionState,
} from "../vocabulary/resolution";
import styles from "./ResolutionLabel.module.css";

export interface ResolutionLabelProps {
  state: ResolutionState;
  /** What the user typed or picked. */
  label: string;
  /** The canonical id behind a resolved subject — mono, on hover, never invented. */
  canonicalId?: string;
  /** How many estate entities matched, for INFERRED. */
  candidateCount?: number;
  /** Why nothing matched, for UNRESOLVED. Specific: "No package named 'tree'." */
  reason?: string;
  /** The inline chooser an inferred subject must offer. */
  children?: ReactNode;
}

/**
 * A subject as the product is willing to speak about it (R12).
 *
 * The three states take the typographic channel rather than a hue, because Strata
 * already encodes epistemic status in type: a resolved subject is a scanned
 * coordinate, so it is mono and unadorned; an inferred one is StackGraph's reading,
 * so it is sans and always shows its candidate count; an unresolved one is struck
 * through and carries its reason.
 *
 * An inferred subject cannot be resolved by ignoring it — the chooser renders inline,
 * beneath the label, rather than behind a click. That is the whole point of the
 * component: 100% ambiguity surfacing is a UI commitment, not a backend one.
 */
export function ResolutionLabel({
  state,
  label,
  canonicalId,
  candidateCount,
  reason,
  children,
}: ResolutionLabelProps) {
  const description = RESOLUTION_DESCRIPTION[state];
  return (
    <span className={styles.wrap}>
      <span className={styles.row}>
        <span
          className={`${styles.label} ${styles[state.toLowerCase()]} ${state === "RESOLVED" ? "sg-mono" : ""}`}
          title={state === "RESOLVED" ? canonicalId ?? description : description}
        >
          {label}
        </span>
        <span className={styles.state}>
          {RESOLUTION_LABEL[state]}
          {state === "INFERRED" && candidateCount != null ? (
            <> · {candidateCount} candidate{candidateCount === 1 ? "" : "s"}</>
          ) : null}
        </span>
        <span className={styles.visuallyHidden}>{description}</span>
      </span>
      {state === "UNRESOLVED" && reason ? <span className={styles.reason}>{reason}</span> : null}
      {state === "INFERRED" && children ? <span className={styles.chooser}>{children}</span> : null}
    </span>
  );
}
