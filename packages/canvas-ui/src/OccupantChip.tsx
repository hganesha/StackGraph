"use client";

import type { CanvasOccupantGroupView, CanvasOccupantView } from "@stackgraph/shared";
import { POLICY_LABEL, POLICY_TONE } from "./vocabulary";
import styles from "./canvas.module.css";

/**
 * One package in a cell, however many versions of it are resolved there.
 *
 * A technology entity is a resolved coordinate, so a cell can hold `react@18.3.1`,
 * `react@18.2.0` and `react@16.14.0` as three occupants. Listing them flat is what
 * makes a populated cell unreadable, and it also misleads: version spread is one fact
 * about one package, not three facts about three technologies. The chip therefore
 * shows the package, and the version count when there is more than one; the detail
 * panel carries the per-version breakdown.
 */
export function OccupantChip({
  group,
  cellKey,
  onSelect,
  compact = false,
}: {
  group: CanvasOccupantGroupView;
  cellKey: string;
  onSelect?: (technologyId: string, cellKey: string) => void;
  compact?: boolean;
}) {
  const tone = POLICY_TONE[group.policy_status];
  const policyLabel = POLICY_LABEL[group.policy_status];
  const multiple = group.members.length > 1;
  const single = group.versions.length === 1 ? group.versions[0] : null;

  // The chip's accessible name has to carry the same warning its tone does: a group
  // is labelled by its most severe member, so "3 versions, worst is prohibited".
  const label = multiple
    ? `${group.label}, ${group.members.length} versions, most severe ${policyLabel.toLowerCase()}, ${group.confidence_label.toLowerCase()} confidence`
    : `${group.label}${single ? ` ${single}` : ""}, ${policyLabel.toLowerCase()}, ${group.confidence_label.toLowerCase()} confidence`;

  const title = multiple
    ? `Versions in use: ${group.versions.join(", ")}`
    : group.members[0].placement_keys.length
      ? `Placed by ${group.members[0].placement_keys.join(", ")}`
      : group.label;

  const content = (
    <>
      <span className={styles.chipName}>{group.label}</span>
      {multiple ? (
        <span className={styles.chipVersions}>
          {group.members.length} versions
        </span>
      ) : single ? (
        <span className={styles.chipVersion}>{single}</span>
      ) : null}
      <span className={`${styles.chipPolicy} ${styles[`tone-${tone}`]}`}>{policyLabel}</span>
      {!compact ? (
        <span className={styles.chipAdoption}>
          {group.adoption.applications}
          <span className={styles.visuallyHidden}>
            {group.adoption.applications === 1 ? " application" : " applications"}
          </span>
          <span aria-hidden="true">{group.adoption.applications === 1 ? " app" : " apps"}</span>
        </span>
      ) : null}
    </>
  );

  if (!onSelect) {
    return (
      <span className={`${styles.chip} ${styles[`chipTone-${tone}`]}`} title={title} aria-label={label}>
        {content}
      </span>
    );
  }

  return (
    <button
      type="button"
      className={`${styles.chip} ${styles.chipButton} ${styles[`chipTone-${tone}`]}`}
      title={title}
      aria-label={`${label}. Open technology detail.`}
      onClick={(event) => {
        event.stopPropagation();
        // The newest member is the one a reader means by "this package".
        onSelect(group.members[0].technology.id, cellKey);
      }}
    >
      {content}
    </button>
  );
}

/** A single resolved version, as the detail panel lists them beneath their package. */
export function VersionRow({ occupant }: { occupant: CanvasOccupantView }) {
  const tone = POLICY_TONE[occupant.policy_status];
  return (
    <span className={`${styles.chip} ${styles[`chipTone-${tone}`]}`}>
      <span className={styles.chipName}>{occupant.technology.name}</span>
      <span className={`${styles.chipPolicy} ${styles[`tone-${tone}`]}`}>
        {POLICY_LABEL[occupant.policy_status]}
      </span>
    </span>
  );
}
