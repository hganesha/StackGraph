import styles from "./StatTile.module.css";

/** Compact estate count/distribution tile. `hero` renders the 32px display type (entropy/viability). */
export function StatTile({
  label,
  value,
  sub,
  hero = false,
}: {
  label: string;
  value: string | number;
  sub?: string;
  hero?: boolean;
}) {
  return (
    <div className={styles.tile}>
      <div className={styles.label}>{label}</div>
      <div className={`${hero ? styles.hero : styles.value} sg-mono`}>{value}</div>
      {sub ? <div className={styles.sub}>{sub}</div> : null}
    </div>
  );
}
