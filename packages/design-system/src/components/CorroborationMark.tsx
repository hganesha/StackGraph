import styles from "./CorroborationMark.module.css";

export interface CorroborationMarkProps {
  /** How many independent sources agree. Clamped to the four the mark can show. */
  sources: number;
  /** Names the sources, for the title and the accessible name. */
  sourceLabels?: string[];
}

const MAX = 4;

/**
 * Corroboration depth: one to four stacked hairlines beside a claim (R9′).
 *
 * Four independent corroborations is a materially different claim from one, and a
 * single presence marker cannot say so. On any edge that feeds a simulation this is
 * mandatory rather than decorative: "prefer fewer trustworthy edges over a huge noisy
 * graph" is only a real preference if a one-source edge visibly looks weaker than a
 * four-source one.
 *
 * Never a colour, never a badge. Absent means the number is a direct count rather than
 * an inference drawn from sources — that absence is itself information.
 */
export function CorroborationMark({ sources, sourceLabels }: CorroborationMarkProps) {
  if (sources <= 0) return null;
  const filled = Math.min(sources, MAX);
  const suffix = sources > MAX ? ` (${sources} in total)` : "";
  const label = sourceLabels?.length
    ? `${sources} corroborating source${sources === 1 ? "" : "s"}: ${sourceLabels.join(", ")}`
    : `${sources} corroborating source${sources === 1 ? "" : "s"}${suffix}`;
  return (
    <span className={styles.mark} title={label} aria-label={label} role="img">
      {[0, 1, 2, 3].map((index) => (
        <span key={index} className={`${styles.line} ${index < filled ? styles.on : ""}`} aria-hidden="true" />
      ))}
    </span>
  );
}
