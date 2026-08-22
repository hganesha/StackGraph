"use client";

import type { CanvasOccupant } from "@stackgraph/shared";
import { POLICY_LABEL, POLICY_TONE } from "./vocabulary";
import styles from "./canvas.module.css";

/**
 * One technology placement inside a cell. The policy status is spelled out, and the
 * placement keys that put the technology here are exposed as the chip's title and in
 * the detail panel — a technology legitimately appears in several cells, and the
 * reason must always be inspectable (spec §4.7, §6.4).
 */
export function OccupantChip({
  occupant,
  cellKey,
  onSelect,
  compact = false,
}: {
  occupant: CanvasOccupant;
  cellKey: string;
  onSelect?: (technologyId: string, cellKey: string) => void;
  compact?: boolean;
}) {
  const tone = POLICY_TONE[occupant.policy_status];
  const policyLabel = POLICY_LABEL[occupant.policy_status];
  const placement = occupant.placement_keys.length
    ? `Placed by ${occupant.placement_keys.join(", ")}`
    : "Placement keys unavailable";
  const label = `${occupant.technology.name}, ${policyLabel.toLowerCase()}, ${occupant.confidence_label.toLowerCase()} confidence`;

  const content = (
    <>
      <span className={styles.chipName}>{occupant.technology.name}</span>
      <span className={`${styles.chipPolicy} ${styles[`tone-${tone}`]}`}>{policyLabel}</span>
      {!compact ? (
        <span className={styles.chipAdoption}>
          {occupant.adoption.applications}
          <span className={styles.visuallyHidden}> applications</span>
          <span aria-hidden="true"> apps</span>
        </span>
      ) : null}
    </>
  );

  if (!onSelect) {
    return (
      <span className={`${styles.chip} ${styles[`chipTone-${tone}`]}`} title={placement} aria-label={label}>
        {content}
      </span>
    );
  }

  return (
    <button
      type="button"
      className={`${styles.chip} ${styles.chipButton} ${styles[`chipTone-${tone}`]}`}
      title={placement}
      aria-label={`${label}. Open technology detail.`}
      onClick={(event) => {
        event.stopPropagation();
        onSelect(occupant.technology.id, cellKey);
      }}
    >
      {content}
    </button>
  );
}
