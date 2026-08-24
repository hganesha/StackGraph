"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import {
  stackGraphClient,
  type DeterministicInsight,
  type InsightSeverity,
} from "@stackgraph/shared";
import { CitationChip, Skeleton } from "@stackgraph/design-system";
import { useEvidenceStore } from "@/lib/evidenceStore";
import styles from "./deterministic-insights.module.css";

type SeverityFilter = "ALL" | InsightSeverity;

const SEVERITY_ORDER: InsightSeverity[] = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"];
const STAGES: Array<{ key: keyof DeterministicInsight["stages"]; label: string }> = [
  { key: "present", label: "Present" },
  { key: "referenced", label: "Referenced" },
  { key: "statically_reachable", label: "Reachable" },
  { key: "runtime_observed", label: "Runtime" },
  { key: "deployed", label: "Deploy config" },
  { key: "production", label: "Prod config" },
  { key: "externally_exposed", label: "Public config" },
  { key: "business_critical", label: "Biz critical" },
];

function severityClass(severity: InsightSeverity) {
  if (severity === "CRITICAL") return styles.severityCritical;
  if (severity === "HIGH") return styles.severityHigh;
  if (severity === "MEDIUM") return styles.severityMedium;
  return styles.severityLow;
}

function effortLabel(value: string) {
  return value.toLowerCase().replaceAll("_", " ");
}

function InsightCard({ insight }: { insight: DeterministicInsight }) {
  const openEvidence = useEvidenceStore((state) => state.open);
  const visibleRepositories = insight.affected_repositories.slice(0, 3);

  return (
    <article className={styles.card}>
      <header className={styles.cardHead}>
        <div className={styles.badges}>
          <span className={`${styles.severity} ${severityClass(insight.severity)}`}>{insight.severity}</span>
          <span className={styles.rule}>{insight.rule_key}</span>
        </div>
        <div className={styles.score} aria-label={`Priority ${insight.priority_score.toFixed(1)} out of 100`}>
          <span>{insight.priority_score.toFixed(1)}</span>
          <small>priority</small>
        </div>
      </header>

      <div className={styles.cardBody}>
        <div>
          <h3>{insight.title}</h3>
          <p>{insight.summary}</p>
        </div>
        <dl className={styles.impactCounts} aria-label="Affected estate scope">
          <div><dt>Repositories</dt><dd>{insight.affected_repository_count}</dd></div>
          <div><dt>Applications</dt><dd>{insight.affected_application_count}</dd></div>
          <div><dt>Deploy definitions</dt><dd>{insight.affected_deployment_count}</dd></div>
          <div><dt>Evidence</dt><dd>{Math.round(insight.evidence_coverage * 100)}%</dd></div>
        </dl>
      </div>

      <div
        className={styles.funnel}
        role="region"
        aria-label="Observed impact stages"
        tabIndex={0}
      >
        {STAGES.map(({ key, label }) => {
          const value = insight.stages[key];
          const known = value != null;
          return (
            <div key={key} className={known ? styles.stageKnown : styles.stageUnknown}>
              <span>{label}</span>
              <strong>{known ? value : "Unknown"}</strong>
            </div>
          );
        })}
      </div>

      {insight.recommendation ? (
        <div className={styles.recommendation}>
          <div>
            <span className={styles.recommendationEyebrow}>
              {insight.recommendation.action} · {effortLabel(insight.recommendation.estimated_effort)} effort
            </span>
            <strong>{insight.recommendation.title}</strong>
          </div>
          <p>{insight.recommendation.rationale}</p>
        </div>
      ) : null}

      <footer className={styles.cardFoot}>
        <div className={styles.repositoryLinks}>
          {visibleRepositories.map((repository) => (
            <Link key={repository.id} href={`/repositories/${repository.id}`}>{repository.name}</Link>
          ))}
          {insight.affected_repository_count > visibleRepositories.length ? (
            <span>+{insight.affected_repository_count - visibleRepositories.length} more</span>
          ) : null}
        </div>
        <div className={styles.evidenceLinks}>
          {insight.supporting_fact_ids.slice(0, 2).map((factId, index) => (
            <CitationChip
              key={factId}
              label={index === 0 ? "Primary evidence" : `Evidence ${index + 1}`}
              onOpen={() => openEvidence(factId, `${insight.title} evidence`)}
            />
          ))}
        </div>
      </footer>

      {insight.missing_inputs.length > 0 ? (
        <details className={styles.limitations}>
          <summary>{insight.missing_inputs.length} unknown input{insight.missing_inputs.length === 1 ? "" : "s"} excluded from priority</summary>
          <ul>{insight.missing_inputs.map((item) => <li key={item}>{item}</li>)}</ul>
        </details>
      ) : null}
    </article>
  );
}

export function DeterministicInsightsPanel({
  scopeEntityId,
  title = "Deterministic findings",
  description = "Rule-derived findings from admitted graph facts. AI may explain these results, but it does not decide whether a finding exists.",
  limit = 20,
  showFilters = false,
}: {
  scopeEntityId?: string;
  title?: string;
  description?: string;
  limit?: number;
  showFilters?: boolean;
}) {
  const [severity, setSeverity] = useState<SeverityFilter>("ALL");
  const query = useQuery({
    queryKey: ["deterministic-insights", scopeEntityId ?? "portfolio", limit],
    queryFn: () => stackGraphClient.listDeterministicInsights({ scopeEntityId, limit }),
  });
  const insights = useMemo(() => {
    const values = query.data?.insights ?? [];
    return severity === "ALL" ? values : values.filter((item) => item.severity === severity);
  }, [query.data?.insights, severity]);
  const availableSeverities = useMemo(() => new Set((query.data?.insights ?? []).map((item) => item.severity)), [query.data?.insights]);

  return (
    <section className={styles.panel} aria-labelledby={`deterministic-insights-${scopeEntityId ?? "portfolio"}`}>
      <header className={styles.panelHead}>
        <div>
          <span className={styles.eyebrow}>Deterministic evidence</span>
          <h2 id={`deterministic-insights-${scopeEntityId ?? "portfolio"}`}>{title}</h2>
          <p>{description}</p>
        </div>
        {query.data ? (
          <dl className={styles.summary}>
            <div><dt>Findings</dt><dd>{query.data.summary.total}</dd></div>
            <div><dt>Critical / high</dt><dd>{query.data.summary.critical + query.data.summary.high}</dd></div>
            <div><dt>Repositories</dt><dd>{query.data.summary.affected_repositories}</dd></div>
          </dl>
        ) : null}
      </header>

      {showFilters && query.data ? (
        <div className={styles.filters} role="group" aria-label="Filter deterministic findings by severity">
          <button type="button" aria-pressed={severity === "ALL"} onClick={() => setSeverity("ALL")}>All</button>
          {SEVERITY_ORDER.filter((item) => availableSeverities.has(item)).map((item) => (
            <button key={item} type="button" aria-pressed={severity === item} onClick={() => setSeverity(item)}>{item.toLowerCase()}</button>
          ))}
        </div>
      ) : null}

      {query.isLoading ? (
        <div className={styles.loading}>
          <Skeleton height={220} />
          <Skeleton height={220} />
        </div>
      ) : query.isError ? (
        <p className={styles.error} role="alert">Deterministic findings could not be loaded.</p>
      ) : insights.length === 0 ? (
        <div className={styles.empty}>
          <strong>No deterministic findings in this scope.</strong>
          <span>As dependency, reachability, capability-map, and repository infrastructure facts arrive, matching rules will appear here.</span>
        </div>
      ) : (
        <div className={styles.list}>{insights.map((insight) => <InsightCard key={insight.id} insight={insight} />)}</div>
      )}
    </section>
  );
}
