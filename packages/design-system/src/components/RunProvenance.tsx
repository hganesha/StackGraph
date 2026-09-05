import styles from "./RunProvenance.module.css";

/**
 * What a derived number was computed from.
 *
 * Deliberately not shaped like any one read model. `GraphAnalysisSnapshot` and
 * `SimulationRunModel` describe the same idea in different words — `as_of` against
 * `completed_at`, `neo4j_projection_watermark` against `estate_watermark` — so each
 * caller maps into this rather than the component learning both. Building two
 * provenance renderers is the failure mode this exists to prevent.
 */
export interface RunProvenanceFacts {
  /** When the run that produced these numbers finished. */
  asOf: string;
  /** The traversal or simulation policy, by name a reader can hold. */
  policyLabel?: string;
  policyVersion?: string | number;
  /** Machine identifiers. Never rendered; carried on the title for a bug report. */
  policyKey?: string;
  policyHash?: string;
  /** The estate watermark the result was pinned to. */
  watermark?: number;
  /** The authoritative watermark, if known, so the lag can be stated. */
  authoritativeWatermark?: number;
  /** Run status, already in sentence case. */
  statusLabel?: string;
  /** True when the status means "complete, but with reduced coverage". */
  limited?: boolean;
  /** Simulation only: the determinism hash, and what produced the inputs. */
  resultHash?: string;
  scannerVersions?: string[];
  /** Simulation only: this result was replayed, not recomputed. */
  replayed?: boolean;
  locale?: string;
}

function formatAsOf(value: string, locale?: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(locale, {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

/**
 * The stamp that travels with every derived number.
 *
 * A traversal result is only reconstructable if the reader can see which policy version
 * and which watermark produced it, and a determinism guarantee nobody can check on
 * screen is a guarantee that lives only in a test. Under the §4 language rule the keys
 * and hashes stay on the `title`; what shows is which standard, when, and how far behind
 * the graph was.
 *
 * The lag reading is the one that changes a decision: a result computed against a graph
 * that is thousands of changes behind is a different claim from one computed against a
 * current graph, and neither the timestamp nor the policy version says so.
 */
export function RunProvenance({
  asOf,
  policyLabel,
  policyVersion,
  policyKey,
  policyHash,
  watermark,
  authoritativeWatermark,
  statusLabel,
  limited = false,
  resultHash,
  scannerVersions,
  replayed = false,
  locale,
}: RunProvenanceFacts) {
  const lag =
    watermark != null && authoritativeWatermark != null
      ? Math.max(0, authoritativeWatermark - watermark)
      : null;

  const machine = [
    policyKey ? `policy ${policyKey}${policyVersion != null ? `@${policyVersion}` : ""}` : null,
    policyHash ? `hash ${policyHash}` : null,
    watermark != null ? `watermark ${watermark}` : null,
    authoritativeWatermark != null ? `authoritative ${authoritativeWatermark}` : null,
    resultHash ? `result ${resultHash}` : null,
    scannerVersions?.length ? `scanners ${scannerVersions.join(", ")}` : null,
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <p className={styles.provenance} title={machine || undefined}>
      {policyLabel ? (
        <span className={styles.item}>
          Standard: {policyLabel}
          {policyVersion != null ? ` v${policyVersion}` : null}
        </span>
      ) : null}
      <span className={styles.item}>Checked {formatAsOf(asOf, locale)}</span>
      {lag != null ? (
        <span className={`${styles.item} ${lag > 0 ? styles.behind : ""}`}>
          {lag === 0
            ? "Graph current"
            : `Graph ${lag.toLocaleString(locale)} change${lag === 1 ? "" : "s"} behind`}
        </span>
      ) : null}
      {statusLabel ? (
        <span className={`${styles.item} ${limited ? styles.behind : ""}`}>{statusLabel}</span>
      ) : null}
      {/* A replayed result was not recomputed. A reader who believes it was fresh has
          been misled by everything else on the line being true. */}
      {replayed ? <span className={`${styles.item} ${styles.replayed}`}>Replayed</span> : null}
      {resultHash ? (
        <span className={`${styles.item} ${styles.hash} sg-mono`}>{resultHash.slice(0, 12)}</span>
      ) : null}
    </p>
  );
}

/** Map a `GraphAnalysisSnapshot`-shaped value onto the stamp. */
export function graphSnapshotProvenance(snapshot: {
  as_of: string;
  policy_key: string;
  policy_version: number;
  policy_hash: string;
  status: string;
  requested_change_watermark: number;
  neo4j_projection_watermark: number;
}): RunProvenanceFacts {
  return {
    asOf: snapshot.as_of,
    // `runtime-dependency` reads as a standard; the key reads as a routing handle.
    policyLabel: snapshot.policy_key.replaceAll("-", " ").replaceAll(".", " · "),
    policyVersion: snapshot.policy_version,
    policyKey: snapshot.policy_key,
    policyHash: snapshot.policy_hash,
    watermark: snapshot.neo4j_projection_watermark,
    authoritativeWatermark: snapshot.requested_change_watermark,
    statusLabel:
      snapshot.status === "SUCCEEDED_WITH_LIMITATIONS" ? "Reduced coverage" : undefined,
    limited: snapshot.status === "SUCCEEDED_WITH_LIMITATIONS",
  };
}
