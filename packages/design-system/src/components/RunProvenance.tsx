import { SIMULATION_STATUS_LABEL, type SimulationRunStatus } from "../vocabulary/change";
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
  /** The estate watermark the result was pinned to, where it is a counter. */
  watermark?: number;
  /** The estate watermark where it is an opaque token rather than a counter. */
  watermarkToken?: string;
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
  /** Simulation only: which semantic provider produced the target facts. */
  providerVersion?: string;
  /** What the run could and could not see. Primitive entries only; never raw JSON. */
  coverage?: Record<string, unknown>;
  /**
   * `stamp` is a single line that qualifies the numbers beside it, and is the default
   * because that is where provenance usually belongs. `card` is the fuller block for a
   * surface where reproducibility is the subject rather than a caveat — the simulation
   * result page.
   */
  variant?: "stamp" | "card";
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
  watermarkToken,
  authoritativeWatermark,
  statusLabel,
  limited = false,
  resultHash,
  scannerVersions,
  replayed = false,
  providerVersion,
  coverage,
  variant = "stamp",
  locale,
}: RunProvenanceFacts) {
  const lag =
    watermark != null && authoritativeWatermark != null
      ? Math.max(0, authoritativeWatermark - watermark)
      : null;
  // A simulation's watermark is an opaque token rather than a counter, so there is
  // nothing to subtract. Say when it was pinned if the token carries a timestamp, and
  // otherwise say nothing — "age not encoded" is the component talking about itself.
  const watermarkLabel =
    lag == null && watermarkToken
      ? (() => {
          const stamp = /\d{4}-\d{2}-\d{2}T[^;\s]+/.exec(watermarkToken)?.[0];
          return stamp ? `Pinned at ${formatAsOf(stamp, locale)}` : undefined;
        })()
      : undefined;

  const machine = [
    policyKey ? `policy ${policyKey}${policyVersion != null ? `@${policyVersion}` : ""}` : null,
    providerVersion ? `provider ${providerVersion}` : null,
    policyHash ? `hash ${policyHash}` : null,
    watermark != null ? `watermark ${watermark}` : null,
    watermarkToken ? `watermark ${watermarkToken}` : null,
    authoritativeWatermark != null ? `authoritative ${authoritativeWatermark}` : null,
    resultHash ? `result ${resultHash}` : null,
    scannerVersions?.length ? `scanners ${scannerVersions.join(", ")}` : null,
  ]
    .filter(Boolean)
    .join(" · ");

  // Only primitive coverage entries are renderable. `JSON.stringify` of an object is
  // raw machine output and never reaches a reader.
  const coverageEntries = Object.entries(coverage ?? {}).filter(
    ([, value]) => typeof value === "string" || typeof value === "number" || typeof value === "boolean",
  );

  if (variant === "card") {
    return (
      <section className={styles.card} title={machine || undefined}>
        <h3 className={styles.cardHeading}>How this result can be reproduced</h3>
        <dl className={styles.cardList}>
          <div>
            <dt>Checked</dt>
            <dd>{formatAsOf(asOf, locale)}</dd>
          </div>
          {statusLabel ? (
            <div>
              <dt>Result</dt>
              <dd className={limited ? styles.behind : undefined}>{statusLabel}</dd>
            </div>
          ) : null}
          {policyLabel ? (
            <div>
              <dt>Standard</dt>
              <dd>
                {policyLabel}
                {policyVersion != null ? ` v${policyVersion}` : null}
              </dd>
            </div>
          ) : null}
          <div>
            <dt>Estate as it stood</dt>
            <dd>
              {lag == null
                ? watermarkLabel ?? "Pinned at run time"
                : lag === 0
                  ? "Current"
                  : `${lag.toLocaleString(locale)} change${lag === 1 ? "" : "s"} behind`}
            </dd>
          </div>
          {replayed ? (
            <div>
              <dt>Replayed</dt>
              <dd className={styles.replayed}>Returned from an earlier identical run, not recomputed</dd>
            </div>
          ) : null}
          {resultHash ? (
            <div>
              <dt>Determinism hash</dt>
              <dd className={`${styles.hash} sg-mono`} title={resultHash}>
                {resultHash.slice(0, 20)}…
              </dd>
            </div>
          ) : null}
          {scannerVersions?.length ? (
            <div>
              <dt>Read by</dt>
              <dd>{scannerVersions.join(" · ")}</dd>
            </div>
          ) : null}
          {coverageEntries.length ? (
            <div>
              <dt>Coverage</dt>
              <dd>
                {coverageEntries
                  .map(([key, value]) => `${key.replaceAll("_", " ")} ${String(value)}`)
                  .join(" · ")}
              </dd>
            </div>
          ) : null}
        </dl>
      </section>
    );
  }

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
      ) : watermarkLabel ? (
        <span className={styles.item}>{watermarkLabel}</span>
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

/**
 * Map a `SimulationRunModel`-shaped value onto the same stamp.
 *
 * The two read models describe one idea in different words, which is exactly why this
 * mapping lives beside the graph one rather than in a second component.
 */
export function simulationRunProvenance(run: {
  created_at: string;
  started_at?: string | null;
  completed_at?: string | null;
  status: string;
  policy_version: string;
  provider_version?: string;
  scanner_versions?: string[];
  estate_watermark: string;
  result_hash?: string | null;
  replayed?: boolean;
}): RunProvenanceFacts {
  const status = run.status as SimulationRunStatus;
  return {
    asOf: run.completed_at ?? run.started_at ?? run.created_at,
    policyVersion: run.policy_version,
    watermarkToken: run.estate_watermark,
    statusLabel: SIMULATION_STATUS_LABEL[status] ?? run.status,
    limited: status === "LIMITED" || status === "NOT_SIMULATABLE",
    resultHash: run.result_hash ?? undefined,
    scannerVersions: run.scanner_versions,
    providerVersion: run.provider_version,
    replayed: run.replayed ?? false,
  };
}
