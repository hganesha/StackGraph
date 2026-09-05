"use client";

import { POLICY_LABEL, POLICY_TONE } from "./vocabulary";
import type { CanvasOccupantPolicyStatus } from "@stackgraph/shared";
import styles from "./canvas.module.css";

/**
 * Version spread, as a shape.
 *
 * Every SCA tool on the market lists versions. None of them show version spread as a
 * *shape*, which is the thing that actually predicts migration cost: three ticks
 * bunched to the right is one upgrade; three ticks strung across the strip is a decade
 * of drift sitting in one package (recommendations R7).
 *
 * Ticks are positioned by version recency, not evenly, so the gaps carry the meaning.
 * The leading tick takes the group's most severe policy status, because a group whose
 * newest version is preferred and whose oldest is prohibited is a governance problem
 * and the picture must not launder it — the same rule `groupOccupants` already applies
 * to the chip's headline.
 */
const WIDTH = 40;
const HEIGHT = 12;

/** Leading numeric segments as one comparable number. `null` when nothing parses. */
function versionRank(version: string): number | null {
  const parts = version.split(/[.\-+]/, 3).map((part) => (/^\d+$/.test(part) ? Number(part) : null));
  if (parts[0] == null) return null;
  return parts[0] * 1_000_000 + (parts[1] ?? 0) * 1_000 + (parts[2] ?? 0);
}

export function VersionComb({
  versions,
  policyStatus,
  label,
}: {
  /** Newest first, as `CanvasOccupantGroupView.versions` supplies them. */
  versions: string[];
  policyStatus: CanvasOccupantPolicyStatus;
  label: string;
}) {
  if (versions.length < 2) return null;

  const ranks = versions.map(versionRank);
  // A single unparseable version would distort every position, so a group with any
  // unparseable member falls back to even spacing and says so in the title.
  const ranked = ranks.every((rank): rank is number => rank != null);
  const min = ranked ? Math.min(...ranks as number[]) : 0;
  const max = ranked ? Math.max(...ranks as number[]) : 0;
  const span = max - min;

  const ticks = versions.map((version, index) => {
    const position = ranked
      ? span > 0
        ? ((ranks[index] as number) - min) / span
        : 1
      : versions.length > 1
        ? 1 - index / (versions.length - 1)
        : 1;
    return { version, x: 1 + position * (WIDTH - 2), leading: index === 0 };
  });

  const tone = POLICY_TONE[policyStatus];
  const title = ranked
    ? `${label}: ${versions.join(", ")} — oldest on the left, newest on the right. Most severe: ${POLICY_LABEL[policyStatus].toLowerCase()}.`
    : `${label}: ${versions.join(", ")} — versions could not be ordered numerically, so ticks are evenly spaced. Most severe: ${POLICY_LABEL[policyStatus].toLowerCase()}.`;

  return (
    <svg
      className={styles.comb}
      width={WIDTH}
      height={HEIGHT}
      viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
      role="img"
      aria-label={title}
    >
      <title>{title}</title>
      <line className={styles.combBase} x1={0} y1={HEIGHT - 1} x2={WIDTH} y2={HEIGHT - 1} />
      {ticks.map((tick) => (
        <line
          key={tick.version}
          className={`${styles.combTick} ${tick.leading ? `${styles.combLeading} ${styles[`tone-${tone}`]}` : ""}`}
          x1={tick.x}
          y1={tick.leading ? 1 : 4}
          x2={tick.x}
          y2={HEIGHT - 1}
        />
      ))}
    </svg>
  );
}
