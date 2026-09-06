"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import {
  stackGraphClient,
  type DeterministicInsight,
  type InsightSeverity,
} from "@stackgraph/shared";
import {
  AttenuationBar,
  CitationChip,
  IconAttenuation,
  Skeleton,
  Term,
  type AttenuationStage,
} from "@stackgraph/design-system";
import { useEvidenceStore } from "@/lib/evidenceStore";
import { SimulateRecommendation } from "@/features/change/SimulateRecommendation";
import { RecommendationSimulationUnavailable } from "@/features/change/RecommendationSimulationUnavailable";
import styles from "./deterministic-insights.module.css";

type SeverityFilter = "ALL" | InsightSeverity;

const SEVERITY_ORDER: InsightSeverity[] = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"];

/** Sentence case, always. A shouted enum is a machine talking (§4). */
const SEVERITY_LABEL: Record<InsightSeverity, string> = {
  CRITICAL: "Critical",
  HIGH: "High",
  MEDIUM: "Medium",
  LOW: "Low",
  INFO: "Info",
};
/**
 * The eight evidence classes, in the order a finding narrows through them.
 *
 * Labels say what was established, not which config file said so: "Deploy config" and
 * "Public config" name our inputs, and a reader does not have our inputs (§4).
 */
const STAGES: Array<{ key: keyof DeterministicInsight["stages"]; label: string }> = [
  { key: "present", label: "Present" },
  { key: "referenced", label: "Referenced" },
  { key: "statically_reachable", label: "Reachable in code" },
  { key: "runtime_observed", label: "Seen at runtime" },
  { key: "deployed", label: "Deployed" },
  { key: "production", label: "In production" },
  { key: "externally_exposed", label: "Internet-facing" },
  { key: "business_critical", label: "Business-critical" },
];

/**
 * `dependency.unsupported-runtime` → "Unsupported runtime".
 *
 * The rule key is a stable identifier we route on; it is not a name for a human. It
 * keeps its place on the `title`, where an engineer filing a bug can still copy it
 * (defect §7.3).
 */
function ruleLabel(ruleKey: string): string {
  const leaf = ruleKey.split(".").pop() ?? ruleKey;
  const words = leaf.replaceAll("-", " ").replaceAll("_", " ").trim();
  return words.charAt(0).toUpperCase() + words.slice(1);
}

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
  const stages: AttenuationStage[] = STAGES.map(({ key, label }) => ({
    key,
    label,
    value: insight.stages[key] ?? null,
  }));

  return (
    <article className={styles.card}>
      <header className={styles.cardHead}>
        <div className={styles.badges}>
          <span className={`${styles.severity} ${severityClass(insight.severity)}`}>{SEVERITY_LABEL[insight.severity]}</span>
          <span className={styles.rule} title={`Rule ${insight.rule_key}`}>{ruleLabel(insight.rule_key)}</span>
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
          {/* Non-negotiable 14: a repository count is not a component count. This one
              genuinely is repository-level — the rule is that a figure says which it
              is, and the title says so where the label cannot. */}
          <div>
            <dt title="Whole repositories, not the components inside them.">Repositories</dt>
            <dd>{insight.affected_repository_count}</dd>
          </div>
          <div><dt>Applications</dt><dd>{insight.affected_application_count}</dd></div>
          <div><dt>Deploy definitions</dt><dd>{insight.affected_deployment_count}</dd></div>
          <div><dt>Evidence</dt><dd>{Math.round(insight.evidence_coverage * 100)}%</dd></div>
        </dl>
      </div>

      <div className={styles.funnel}>
        <div className={styles.funnelHead}>
          <IconAttenuation size={16} />
          <span>
            How far this actually reaches
          </span>
          <small>
            Each row is an independent class of evidence. The drop between them is what
            separates <Term id="attenuation">a finding worth acting on</Term> from a
            lockfile entry.
          </small>
        </div>
        <AttenuationBar stages={stages} />
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
          {/* R1: an estate finding must reach a simulation without manual re-entry. Upgrade and
              consolidation findings now compile against the estate's own consolidation target;
              the rest still say why they cannot, rather than offering a button that fails. */}
          {insight.recommendation.action === "UPGRADE" || insight.recommendation.action === "CONSOLIDATE" ? (
            <SimulateRecommendation
              recommendationId={insight.id}
              source="DETERMINISTIC_INSIGHT"
              label="Simulate finding"
              compact
            />
          ) : (
            <RecommendationSimulationUnavailable
              reason={`a ${insight.recommendation.action.toLowerCase()} finding cannot yet compile to an exact target state`}
            />
          )}
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
            <button key={item} type="button" aria-pressed={severity === item} onClick={() => setSeverity(item)}>{SEVERITY_LABEL[item]}</button>
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
