import type { Icon } from "@tabler/icons-react";
import styles from "./StatTile.module.css";

/**
 * Compact estate count/distribution tile. `hero` renders the 32px display type
 * (entropy/viability). `icon` is decorative — the label always carries the meaning.
 */
export function StatTile({
  label,
  value,
  sub,
  hero = false,
  icon: Glyph,
}: {
  label: string;
  value: string | number;
  sub?: string;
  hero?: boolean;
  icon?: Icon;
}) {
  return (
    <div className={styles.tile}>
      <div className={styles.label}>
        {Glyph ? <Glyph size={14} stroke={1.5} className={styles.icon} aria-hidden="true" /> : null}
        <span>{label}</span>
      </div>
      <div className={`${hero ? styles.hero : styles.value} sg-mono`}>{value}</div>
      {sub ? <div className={styles.sub}>{sub}</div> : null}
    </div>
  );
}
