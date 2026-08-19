import type { AssertionClass } from "@stackgraph/shared";
import { AssertionTag } from "./AssertionTag";
import styles from "./EvidenceRow.module.css";

/**
 * One evidence line (design language §evidence row): mono class tag + mono source path +
 * one line of sans description. Mono/sans split makes "raw fact vs. reasoning" legible before reading.
 */
export function EvidenceRow({
  assertionClass,
  source,
  description,
}: {
  assertionClass: AssertionClass;
  source?: string;
  description?: string;
}) {
  return (
    <li className={styles.row}>
      <AssertionTag assertionClass={assertionClass} />
      <div className={styles.body}>
        {source ? <code className={`${styles.source} sg-mono`}>{source}</code> : null}
        {description ? <span className={styles.desc}>{description}</span> : null}
      </div>
    </li>
  );
}
