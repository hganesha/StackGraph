import { StratumBar, type StratumLayer } from "./StratumBar";
import styles from "./StatusStrip.module.css";

export interface StatusStripProps {
  repositoriesScanned: number;
  repositoriesTotal: number;
  evidenceRatio: number;
  asOf: string;
  /**
   * Operator telemetry, not a user-facing fact. It stays reachable — on the strip's
   * `title` and on Scan health — but it no longer occupies a slot in a strip that is
   * on screen on every page (defect §7.2).
   */
  contractVersion: string;
  /** The five estate layers. Omit and the strip renders as it always did. */
  layers?: StratumLayer[];
  /** The thinnest measured layer, spoken in the strip's accessible name. */
  weakestLayer?: { label: string; reading: string } | null;
  locale?: string;
}

/** Always-visible trust telemetry (plan §3.1). Makes a coverage gap visible before it becomes a wrong conclusion. */
export function StatusStrip({
  repositoriesScanned,
  repositoriesTotal,
  evidenceRatio,
  asOf,
  contractVersion,
  layers,
  weakestLayer,
  locale,
}: StatusStripProps) {
  const pct = repositoriesTotal > 0 ? Math.round((repositoriesScanned / repositoriesTotal) * 100) : 0;
  const asOfLabel = new Intl.DateTimeFormat(locale, { dateStyle: "medium", timeStyle: "short" }).format(new Date(asOf));
  const ariaLabel = weakestLayer
    ? `How much of your estate has been scanned, and when. Weakest layer: ${weakestLayer.label} — ${weakestLayer.reading}`
    : "How much of your estate has been scanned, and when";
  return (
    <div
      className={styles.strip}
      role="status"
      aria-label={ariaLabel}
      title={`Read model contract ${contractVersion}`}
      tabIndex={0}
    >
      {layers?.length ? (
        <>
          <StratumBar layers={layers} weakestLayerLabel={weakestLayer?.label} />
          <span className={styles.sep} aria-hidden="true" />
        </>
      ) : null}
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
      {weakestLayer ? (
        <span className={`${styles.item} ${styles.weakest}`}>
          <span className={styles.k}>Weakest layer</span>
          <span className={styles.v}>
            {weakestLayer.label} — {weakestLayer.reading}
          </span>
        </span>
      ) : null}
    </div>
  );
}
