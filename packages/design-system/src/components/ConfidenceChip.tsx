import type { ConfidenceLabel } from "@stackgraph/shared";
import { formatConfidence, segmentsFor } from "@stackgraph/shared";
import styles from "./ConfidenceChip.module.css";

/**
 * Confidence chip — 3-segment bar + text label. Neutral ink except LOW (the one danger accent).
 * Decimal is available on hover/inspect, never hidden (plan §1.2 P3).
 * Confidence is NOT a color: the bar + label carry it, red only marks LOW.
 */
export function ConfidenceChip({
  label,
  value,
  locale,
}: {
  label: ConfidenceLabel;
  value?: number;
  locale?: string;
}) {
  const filled = segmentsFor(label);
  const isLow = label === "LOW";
  const title = value !== undefined ? `${label} · ${formatConfidence(value, locale)}` : label;
  return (
    <span className={`${styles.chip} ${isLow ? styles.low : ""}`} title={title} aria-label={title}>
      <span className={styles.bars} aria-hidden="true">
        {[0, 1, 2].map((i) => (
          <span key={i} className={`${styles.seg} ${i < filled ? styles.on : ""}`} />
        ))}
      </span>
      <span className={`${styles.label} sg-mono`}>{label}</span>
    </span>
  );
}
