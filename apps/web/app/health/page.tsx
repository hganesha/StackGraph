"use client";

import { useMemo } from "react";
import Link from "next/link";
import { IconFileDescription, IconGitBranch, IconSortDescending } from "@tabler/icons-react";
import { StatTile, Skeleton } from "@stackgraph/design-system";
import { formatRelative } from "@stackgraph/shared";
import {
  useEnterpriseInsightReports,
  useEmbeddingStatus,
  useEstateSummary,
  useGraphIntelligenceStatus,
  useScanStatus,
  useServiceStatus,
} from "@/lib/queries";
import styles from "./health.module.css";

/** Scan health — observability surface (plan §11.4). Promotes the status strip into a full view. */
export default function HealthPage() {
  const { data, isLoading } = useEstateSummary();
  const insightReports = useEnterpriseInsightReports();
  const scanStatus = useScanStatus();
  const serviceStatus = useServiceStatus();
  const graphStatus = useGraphIntelligenceStatus();
  const embeddingStatus = useEmbeddingStatus();

  const freshness = useMemo(() => {
    const acc = { FRESH: 0, STALE: 0, UNKNOWN: 0 } as Record<string, number>;
    data?.ranked_items.forEach((i) => {
      acc[i.freshness.status] = (acc[i.freshness.status] ?? 0) + 1;
    });
    return acc;
  }, [data]);

  const distributions = useMemo(() => Object.entries(data?.distributions ?? {}), [data]);
  const assurance = useMemo(
    () => insightReports.data?.reports.find((report) => report.key === "assurance_coverage"),
    [insightReports.data],
  );
  const assuranceDimensions = useMemo(
    () => (assurance?.response.rows ?? []).slice(1).map((row) => ({
      dimension: String(row.dimension ?? ""),
      status: String(row.status ?? "NOT_EVALUATED"),
      covered: Number(row.covered ?? 0),
      inScope: Number(row.in_scope ?? 0),
      scope: String(row.scope ?? ""),
      detail: String(row.detail ?? ""),
    })),
    [assurance],
  );
  const dataServices = useMemo(() => serviceStatus.data?.services.filter(
    (service) => service.category === "INGESTION" || service.category === "ENRICHMENT",
  ) ?? [], [serviceStatus.data]);

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
        <h1 className={styles.title}>Scan health</h1>
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

      <section className={styles.coverage} aria-labelledby="assurance-coverage-heading">
        <div className={styles.coverageHead}>
          <div>
            <span className={styles.coverageEyebrow}>Can we trust this data?</span>
            <h2 id="assurance-coverage-heading">Repositories we can fully analyse</h2>
            <p>
              {assurance
                ? assurance.status === "WAITING_FOR_DATA"
                  ? "Coverage cannot be scored yet. Connect a source and complete one scan first."
                  : assurance.response.text
                : insightReports.isError
                  ? "Assurance coverage is temporarily unavailable."
                  : "Scoring how much of the estate StackGraph can reason over…"}
            </p>
          </div>
          <div className={styles.coverageScore}>
            <strong className="sg-mono">{assurance?.metric_value ?? "—"}</strong>
            <span className={`${styles.coverageBadge} ${assurance ? styles[`coverage${assurance.status}`] : ""}`}>
              {assurance ? assurance.status.replaceAll("_", " ").toLowerCase() : "evaluating"}
            </span>
          </div>
        </div>

        {assuranceDimensions.length > 0 ? (
          <ul className={styles.coverageDimensions}>
            {assuranceDimensions.map((dimension) => (
              <li key={dimension.dimension} title={dimension.detail}>
                <span className={styles.coverageDimensionName}>{dimension.dimension}</span>
                <span className={`${styles.coverageDimensionCount} sg-mono`}>
                  {dimension.covered}/{dimension.inScope} {dimension.scope.toLowerCase()}
                </span>
                <span className={`${styles.coverageBadge} ${styles[`coverage${dimension.status}`]}`}>
                  {dimension.status.replaceAll("_", " ").toLowerCase()}
                </span>
              </li>
            ))}
          </ul>
        ) : null}

        <Link className={styles.adminLink} href="/ask">
          Open coverage report <span aria-hidden="true">→</span>
        </Link>
      </section>

      <section className={styles.insightReadiness} aria-labelledby="insight-readiness-heading">
        <div>
          <span className={styles.insightEyebrow}>Ready to answer</span>
          <h2 id="insight-readiness-heading">Questions we can answer now</h2>
          <p>
            {insightReports.data
              ? `${insightReports.data.total_reports - insightReports.data.answerable_reports} reports are waiting on governed capability, platform, or lifecycle data.`
              : insightReports.isError
                ? "Questions we can answer now is temporarily unavailable."
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

      <section className={styles.card} aria-labelledby="graph-health-heading">
        <div className={styles.cardHead}>
          <div>
            <h2 id="graph-health-heading" className={styles.h2}>Graph intelligence</h2>
            <p className={styles.cardNote}>Neo4j projection freshness and active deterministic-analysis snapshots.</p>
          </div>
          <Link className={styles.adminLink} href="/admin?tab=operations">Manage service <span aria-hidden="true">→</span></Link>
        </div>
        {graphStatus.isLoading ? <Skeleton height={72} /> : graphStatus.isError || !graphStatus.data ? (
          <p className={styles.operationError} role="alert">Graph-intelligence health is temporarily unavailable.</p>
        ) : (
          <>
            <div className={styles.operationSummary}>
              <div><span>Deployment</span><strong>{graphStatus.data.deployment_state.toLowerCase()}</strong></div>
              <div><span>Projection lag</span><strong>{graphStatus.data.projection_lag.toLocaleString()}</strong></div>
              <div><span>Queued / running</span><strong>{graphStatus.data.pending_requests} / {graphStatus.data.running_requests}</strong></div>
              <div><span>Needs attention</span><strong>{graphStatus.data.failed_requests}</strong></div>
            </div>
            <p className={styles.cardNote}>
              Authoritative watermark {graphStatus.data.desired_change_watermark.toLocaleString()} · projected {graphStatus.data.neo4j_projection_watermark.toLocaleString()} · {graphStatus.data.snapshots.length} active policy snapshots.
            </p>
          </>
        )}
      </section>

      <section className={styles.card} aria-labelledby="embedding-health-heading">
        <div className={styles.cardHead}>
          <div>
            <h2 id="embedding-health-heading" className={styles.h2}>Semantic intelligence</h2>
            <p className={styles.cardNote}>Evaluated embedding spaces, tenant coverage, and durable worker backlog.</p>
          </div>
          <Link className={styles.adminLink} href="/admin?tab=operations">Manage service <span aria-hidden="true">→</span></Link>
        </div>
        {embeddingStatus.isLoading ? <Skeleton height={72} /> : embeddingStatus.isError || !embeddingStatus.data ? (
          <p className={styles.operationError} role="alert">Semantic-intelligence health is temporarily unavailable.</p>
        ) : (
          <>
            <div className={styles.operationSummary}>
              <div><span>Provider</span><strong>{embeddingStatus.data.provider}</strong></div>
              <div><span>Active coverage</span><strong>{embeddingStatus.data.active_spaces.length ? `${Math.round(Math.max(...embeddingStatus.data.active_spaces.map((space) => space.coverage_ratio)) * 100)}%` : "not active"}</strong></div>
              <div><span>Queued / running</span><strong>{embeddingStatus.data.pending_jobs} / {embeddingStatus.data.running_jobs}</strong></div>
              <div><span>Needs attention</span><strong>{embeddingStatus.data.failed_jobs}</strong></div>
            </div>
            <p className={styles.cardNote}>
              {embeddingStatus.data.active_spaces.length
                ? `${embeddingStatus.data.active_spaces.length} evaluated space${embeddingStatus.data.active_spaces.length === 1 ? "" : "s"} active; ${embeddingStatus.data.shadow_spaces.length} candidate space${embeddingStatus.data.shadow_spaces.length === 1 ? "" : "s"} awaiting evaluation.`
                : "No semantic space is active yet. Search and similarity remain unavailable until coverage and evaluation gates pass."}
            </p>
            {embeddingStatus.data.limitations.map((limitation, index) => (
              <p key={`${String(limitation.code ?? "limitation")}:${index}`} className={styles.operationError}>{String(limitation.message ?? limitation.code ?? "Semantic coverage is limited.")}</p>
            ))}
          </>
        )}
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

      <section className={styles.card} aria-labelledby="operations-heading">
        <div className={styles.cardHead}>
          <div>
            <h2 id="operations-heading" className={styles.h2}>Enrichment &amp; scan runs</h2>
            <p className={styles.cardNote}>
              Scan and enrichment activity. Updates every 15 seconds.
            </p>
          </div>
          <Link className={styles.adminLink} href="/admin?tab=operations">Manage operations <span aria-hidden="true">→</span></Link>
        </div>

        {scanStatus.isLoading || serviceStatus.isLoading ? (
          <div className={styles.operationLoading}><Skeleton height={68} /><Skeleton height={68} /></div>
        ) : scanStatus.isError || serviceStatus.isError ? (
          <p className={styles.operationError} role="alert">Can’t reach the operations data right now. Try again shortly.</p>
        ) : (
          <>
            <div className={styles.operationSummary}>
              <div><span>Scan policy</span><strong>{scanStatus.data?.policy.enabled ? scanStatus.data.policy.cadence.toLowerCase() : "paused"}</strong></div>
              <div><span>Active work</span><strong>{dataServices.reduce((sum, service) => sum + service.running, 0)}</strong></div>
              <div><span>Queued</span><strong>{dataServices.reduce((sum, service) => sum + service.pending, 0)}</strong></div>
              <div><span>Failed, needs attention</span><strong>{dataServices.reduce((sum, service) => sum + service.failed, 0)}</strong></div>
            </div>

            <div className={styles.operationCols}>
              <div>
                <h3>Data services</h3>
                {dataServices.length ? (
                  <ul className={styles.serviceList}>
                    {dataServices.map((service) => (
                      <li key={service.key}>
                        <div>
                          <strong>{service.name}</strong>
                          <span>{service.detail}</span>
                          {service.last_activity_at ? <small>Last activity {formatRelative(service.last_activity_at)}</small> : null}
                        </div>
                        <span className={`${styles.operationStatus} ${styles[`operation${service.state}`]}`}>{service.state.toLowerCase()}</span>
                      </li>
                    ))}
                  </ul>
                ) : <p className={styles.emptyState}>No scan or enrichment services connected yet. Connect a source in Admin to start.</p>}
              </div>

              <div>
                <h3>Recent rescans</h3>
                {scanStatus.data?.recent_jobs.length ? (
                  <ul className={styles.jobList}>
                    {scanStatus.data.recent_jobs.slice(0, 5).map((job) => (
                      <li key={job.id}>
                        <div>
                          <strong>{job.reason || "Estate rescan"}</strong>
                          <span>Requested {formatRelative(job.created_at)} by {job.requested_by}</span>
                          {job.last_error ? <small className={styles.jobError}>{job.last_error}</small> : null}
                        </div>
                        <span className={`${styles.operationStatus} ${styles[`operation${job.status}`]}`}>{job.status.toLowerCase()}</span>
                      </li>
                    ))}
                  </ul>
                ) : <p className={styles.emptyState}>No manual rescans yet.</p>}
              </div>
            </div>

            {scanStatus.data?.quotas.length ? (
              <div className={styles.quotaStrip} aria-label="Provider quota status">
                {scanStatus.data.quotas.map((quota) => (
                  <span key={quota.provider}>
                    <strong>{quota.provider.replaceAll("_", " ").toLowerCase()}</strong>
                    {quota.limit == null ? `${quota.used} used` : `${quota.used.toLocaleString()} / ${quota.limit.toLocaleString()}`}
                    <em className={styles[`quota${quota.status}`]}>{quota.status.toLowerCase()}</em>
                  </span>
                ))}
              </div>
            ) : null}
          </>
        )}
      </section>
    </div>
  );
}
