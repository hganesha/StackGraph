import type { ReactNode } from "react";
import { IconAlertOctagon, IconLock, IconScissors } from "@tabler/icons-react";
import { GATE_DESCRIPTION, GATE_LABEL, GATE_RENDERS, type GateVerdict } from "../vocabulary/gates";
import styles from "./GateNotice.module.css";

const GLYPH: Record<Exclude<GateVerdict, "CLEAR">, typeof IconLock> = {
  BLOCKED: IconAlertOctagon,
  ESCALATE: IconLock,
  CONSTRAIN: IconScissors,
};

export interface GateNoticeProps {
  verdict: GateVerdict;
  /**
   * What specifically is in the way — the unresolved subject, the contradicted fact,
   * the scope that was removed. A gate that cannot name its blocker is not a gate;
   * it is a caution tone wearing a barrier's clothes.
   */
  reason: ReactNode;
  /** Required on ESCALATE: who can clear it. Named, not "an administrator". */
  approver?: string;
  /** Evidence, the blocking entity, or the request-approval control. Never a dismiss. */
  action?: ReactNode;
  /** The control this gate governs, so screen readers reach the barrier from it. */
  id?: string;
}

/**
 * The barrier bar. The one filled surface in the product (§11.2), used nowhere else.
 *
 * `BLOCKED` and `ESCALATE` fill because they are the only two states where the reader
 * must not be able to skim past. `CONSTRAIN` stays hairline — it is a narrowing, not a
 * wall. `CLEAR` renders nothing: absence is the signal, and a green "all good" banner
 * would teach people to ignore the position the real barrier occupies.
 *
 * There is no `onDismiss`, deliberately. A gate that can be waved away is advisory,
 * and the advisory vocabulary already exists.
 */
export function GateNotice({ verdict, reason, approver, action, id }: GateNoticeProps) {
  if (!GATE_RENDERS[verdict]) return null;
  const kind = verdict as Exclude<GateVerdict, "CLEAR">;
  const Glyph = GLYPH[kind];
  return (
    <div
      id={id}
      className={`${styles.gate} ${styles[kind.toLowerCase()]}`}
      role={kind === "CONSTRAIN" ? "status" : "alert"}
    >
      <span className={styles.glyph} aria-hidden="true">
        <Glyph size={17} stroke={1.75} />
      </span>
      <div className={styles.body}>
        <strong className={styles.label}>
          {GATE_LABEL[kind]}
          {kind === "ESCALATE" && approver ? <> · {approver}</> : null}
        </strong>
        {/* The reason sits inline, never only in a tooltip: a barrier whose cause is
            behind a hover cannot be acted on by anyone reading it on a keyboard. */}
        <span className={styles.reason}>{reason}</span>
        <span className={styles.meaning}>{GATE_DESCRIPTION[kind]}</span>
      </div>
      {action ? <div className={styles.action}>{action}</div> : null}
    </div>
  );
}
