import styles from "./StatusStrip.module.css";

export interface StatusStripProps {
  repositoriesScanned: number;
  repositoriesTotal: number;
  evidenceRatio: number;
  asOf: string;
  contractVersion: string;
  locale?: string;
}

/** Always-visible trust telemetry (plan §3.1). Makes a coverage gap visible before it becomes a wrong conclusion. */
export function StatusStrip({
  repositoriesScanned,
  repositoriesTotal,
  evidenceRatio,
  asOf,
  contractVersion,
  locale,
}: StatusStripProps) {
  const pct = repositoriesTotal > 0 ? Math.round((repositoriesScanned / repositoriesTotal) * 100) : 0;
  const asOfLabel = new Intl.DateTimeFormat(locale, { dateStyle: "medium", timeStyle: "short" }).format(new Date(asOf));
  return (
    <div
      className={styles.strip}
      role="status"
      aria-label="Estate coverage and freshness"
      tabIndex={0}
    >
      <span className={styles.item}>
        <span className={styles.k}>Coverage</span>
        <span className={`${styles.v} sg-mono`}>
          {repositoriesScanned}/{repositoriesTotal} repos · {pct}%
        </span>
      </span>
      <span className={styles.sep} aria-hidden="true" />
      <span className={styles.item}>
        <span className={styles.k}>Evidence</span>
        <span className={`${styles.v} sg-mono`}>{Math.round(evidenceRatio * 100)}%</span>
      </span>
      <span className={styles.sep} aria-hidden="true" />
      <span className={styles.item}>
        <span className={styles.k}>As of</span>
        <span className={`${styles.v} sg-mono`}>{asOfLabel}</span>
      </span>
      <span className={styles.spacer} />
      <span className={`${styles.item} ${styles.contract}`}>
        <span className={`${styles.v} sg-mono`}>contract {contractVersion}</span>
      </span>
    </div>
  );
}
