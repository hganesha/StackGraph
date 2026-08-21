"use client";

import { useMemo } from "react";
import Link from "next/link";
import { StatTile, Skeleton } from "@stackgraph/design-system";
import { formatRelative } from "@stackgraph/shared";
import { useEnterpriseInsightReports, useEstateSummary } from "@/lib/queries";
import styles from "./health.module.css";

/** Estate Health — observability surface (plan §11.4). Promotes the status strip into a full view. */
export default function HealthPage() {
  const { data, isLoading } = useEstateSummary();
  const insightReports = useEnterpriseInsightReports();

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
          Coverage, freshness, and enrichment — the trust telemetry behind every number. Updated{" "}
          {formatRelative(data.as_of)}.
        </p>
      </header>

      <section className={styles.tiles} aria-label="Coverage">
        <StatTile label="Repositories scanned" value={`${cov.repositories_scanned}/${cov.repositories_total}`} hero sub={`${pct}% coverage`} />
        <StatTile label="Facts with evidence" value={`${Math.round(cov.facts_with_evidence_ratio * 100)}%`} sub="of all facts" />
        <StatTile label="Ranked items" value={data.ranked_items.length} sub="in the estate" />
      </section>

      <section className={styles.insightReadiness} aria-labelledby="insight-readiness-heading">
        <div>
          <span className={styles.insightEyebrow}>Decision intelligence</span>
          <h2 id="insight-readiness-heading">Insight readiness</h2>
          <p>
            {insightReports.data
              ? `${insightReports.data.total_reports - insightReports.data.answerable_reports} reports are waiting on governed capability, platform, or lifecycle data.`
              : insightReports.isError
                ? "Insight readiness is temporarily unavailable."
                : "Evaluating governed report coverage…"}
          </p>
        </div>
        <div className={styles.insightScore}>
          <strong className="sg-mono">
            {insightReports.data ? `${insightReports.data.answerable_reports}/${insightReports.data.total_reports}` : "—"}
          </strong>
          <span>reports answerable</span>
        </div>
        <Link href="/ask">View insights <span aria-hidden="true">→</span></Link>
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
