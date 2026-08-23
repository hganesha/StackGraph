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
      aria-label="How much of your estate has been scanned, and when"
      tabIndex={0}
    >
      {/* "Coverage" reads as test coverage to most people, and a bare percentage
          invites the wrong reading. Say what was counted. */}
      <span className={styles.item} title="Repositories StackGraph has scanned, out of those connected.">
        <span className={styles.k}>Scanned</span>
        <span className={`${styles.v} sg-mono`}>
          {repositoriesScanned} of {repositoriesTotal} repos · {pct}%
        </span>
      </span>
      <span className={styles.sep} aria-hidden="true" />
      <span
        className={styles.item}
        title="Share of facts that link back to the file and line they came from."
      >
        <span className={styles.k}>With evidence</span>
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
