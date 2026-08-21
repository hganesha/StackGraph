"use client";

import { useMemo } from "react";
import { IconFileDescription, IconGitBranch, IconSortDescending } from "@tabler/icons-react";
import { StatTile, Skeleton } from "@stackgraph/design-system";
import { formatRelative } from "@stackgraph/shared";
import { useEstateSummary } from "@/lib/queries";
import styles from "./health.module.css";

/** Estate Health — observability surface (plan §11.4). Promotes the status strip into a full view. */
export default function HealthPage() {
  const { data, isLoading } = useEstateSummary();

  const freshness = useMemo(() => {
    const acc = { FRESH: 0, STALE: 0, UNKNOWN: 0 } as Record<string, number>;
    data?.ranked_items.forEach((i) => {
      acc[i.freshness.status] = (acc[i.freshness.status] ?? 0) + 1;
    });
    return acc;
  }, [data]);

  const distributions = useMemo(() => Object.entries(data?.distributions ?? {}), [data]);

  if (isLoading || !data) {
    return (
      <div className={styles.page}>
        <Skeleton height={28} width="30%" />
        <Skeleton height={90} />
      </div>
    );
  }

  const cov = data.coverage;
  const pct = cov.repositories_total > 0 ? Math.round((cov.repositories_scanned / cov.repositories_total) * 100) : 0;

  return (
    <div className={styles.page}>
      <header className={styles.head}>
        <h1 className={styles.title}>Estate Health</h1>
        <p className={styles.subtitle}>
          Scan coverage, fact freshness, and enrichment progress across the estate. Updated{" "}
          {formatRelative(data.as_of)}.
        </p>
      </header>

      <section className={styles.tiles} aria-label="Coverage">
        <StatTile label="Repositories scanned" value={`${cov.repositories_scanned}/${cov.repositories_total}`} hero sub={`${pct}% coverage`} icon={IconGitBranch} />
        <StatTile label="Facts with evidence" value={`${Math.round(cov.facts_with_evidence_ratio * 100)}%`} sub="of all facts" icon={IconFileDescription} />
        <StatTile label="Ranked items" value={data.ranked_items.length} sub="in the estate" icon={IconSortDescending} />
      </section>

      <div className={styles.cols}>
        <section className={styles.card} aria-label="Freshness">
          <h2 className={styles.h2}>Freshness</h2>
          <ul className={styles.bars}>
            {(["FRESH", "STALE", "UNKNOWN"] as const).map((k) => {
              const n = freshness[k] ?? 0;
              const total = data.ranked_items.length || 1;
              return (
                <li key={k} className={styles.barRow}>
                  <span className={`${styles.barLabel} ${k === "STALE" ? styles.stale : ""}`}>{k}</span>
                  <span className={styles.barTrack}>
                    <span
                      className={`${styles.barFill} ${k === "STALE" ? styles.barStale : k === "UNKNOWN" ? styles.barUnknown : ""}`}
                      style={{ inlineSize: `${(n / total) * 100}%` }}
                    />
                  </span>
                  <span className={`${styles.barCount} sg-mono`}>{n}</span>
                </li>
              );
            })}
          </ul>
        </section>

        <section className={styles.card} aria-label="Distributions">
          <h2 className={styles.h2}>Runtime &amp; deployment mix</h2>
          <ul className={styles.dist}>
            {distributions.map(([k, v]) => (
              <li key={k} className={styles.distRow}>
                <span className={`${styles.distKey} sg-mono`}>{k}</span>
                <span className={`${styles.distVal} sg-mono`}>{v}</span>
              </li>
            ))}
          </ul>
        </section>
      </div>

      <section className={styles.card} aria-label="Enrichment and scan runs">
        <h2 className={styles.h2}>Enrichment &amp; scan runs</h2>
        <p className={styles.pending}>
          Per-source enrichment progress (deps.dev / OSV) and scan-run history (COMPLETE / PARTIAL, file and fact
          counts, diagnostics) render here once the backend exposes an ingestion-status read model. The backend
          enrichment lanes (OSV, deps.dev, npm) have landed; this surface is ready to bind when the status endpoint is added.
        </p>
      </section>
    </div>
  );
}
