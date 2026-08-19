import type { AssertionClass } from "@stackgraph/shared";
import styles from "./AssertionTag.module.css";

// Evidence class → whether it's a raw fact (machine-read) or reasoned.
// DECLARED/OBSERVED/EXTERNAL_MEASURED/CURATED = raw; INFERRED = reasoned (design language §evidence).
const REASONED: AssertionClass = "INFERRED";

/** Mono tag naming the evidence class of a fact. INFERRED reads as reasoning, the rest as raw facts. */
export function AssertionTag({ assertionClass }: { assertionClass: AssertionClass }) {
  const reasoned = assertionClass === REASONED;
  return (
    <span className={`${styles.tag} ${reasoned ? styles.reasoned : styles.raw} sg-mono`}>{assertionClass}</span>
  );
}
