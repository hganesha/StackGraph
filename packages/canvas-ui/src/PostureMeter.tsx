"use client";

import type { CanvasCellMeasures } from "@stackgraph/shared";
import { POSTURE_LABEL, POSTURE_TICKS, POSTURE_TONE } from "./vocabulary";
import styles from "./canvas.module.css";

/**
 * Five hairline ticks rather than a traffic light. The band label is always rendered
 * beside it, so the meter is redundant reinforcement and never the only channel
 * (spec §11.2). A cell with no eligible composite renders "Not scored" — a null
 * score is a statement, not a blank.
 */
export function PostureMeter({
  measures,
  labelled = true,
}: {
  measures: CanvasCellMeasures | null;
  labelled?: boolean;
}) {
  const band = measures?.posture_band ?? null;
  const filled = band ? POSTURE_TICKS[band] : 0;
  const tone = band ? POSTURE_TONE[band] : "quiet";
  const text = band
    ? `${POSTURE_LABEL[band]}${measures?.overall_score !== null && measures?.overall_score !== undefined ? ` · ${measures.overall_score}` : ""}`
    : "Not scored";

  return (
    <span className={`${styles.meter} ${styles[`tone-${tone}`]}`}>
      <span className={styles.meterTicks} aria-hidden="true">
        {[1, 2, 3, 4, 5].map((tick) => (
          <span
            key={tick}
            className={`${styles.meterTick} ${tick <= filled ? styles.meterTickOn : ""}`}
            style={{ blockSize: `${4 + tick * 1.6}px` }}
          />
        ))}
      </span>
      {labelled ? <span className={styles.meterLabel}>{text}</span> : <span className={styles.visuallyHidden}>{text}</span>}
    </span>
  );
}
