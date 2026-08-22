"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useMutation } from "@tanstack/react-query";
import {
  formatRelative,
  stackGraphClient,
  type AskResponse,
  type EnterpriseInsightCategory,
  type EnterpriseInsightReport,
  type EnterpriseInsightReportList,
} from "@stackgraph/shared";
import { CitationChip } from "@stackgraph/design-system";
import { useEvidenceStore } from "@/lib/evidenceStore";
import { useEnterpriseInsightReports } from "@/lib/queries";
import styles from "./ask.module.css";

interface ContextLink {
  label: string;
  href: string;
}

interface Turn {
  id: number;
  question: string;
  response?: AskResponse;
  error?: boolean;
  contextLink?: ContextLink;
}

interface BusinessMapContext {
  title: string;
  template: string;
  viewMode?: "value-chain" | "organization";
  stages: Array<{
    name: string;
    capabilities: Array<{ name: string; maturity: number }>;
  }>;
  organizationUnits?: Array<{
    name: string;
    functions: string[];
  }>;
}

interface AskRequest {
  id: number;
  requestQuestion: string;
}

const SUGGESTIONS = [
  "Show me the top 20 dependencies representing systemic enterprise risk.",
  "Which vulnerabilities are actually reachable in production Tier-1 applications?",
  "Where have teams independently implemented the same capability?",
  "Which unsupported dependencies block our Node/Python/.NET modernization?",
  "If package next disappeared tomorrow, what business capabilities would be affected?",
  "Which package categories have the most unnecessary technology diversity?",
  "Which internal libraries should become enterprise standards?",
  "Which custom implementations should be replaced by existing internal platforms?",
  "What are our best application retirement/consolidation candidates?",
  "What are the 10 engineering standardization initiatives with the largest enterprise payoff?",
  "What share of our estate is analytically covered?",
  "Which technologies were introduced into the estate in the last 90 days?",
  "Which critical business capabilities have no application behind them?",
  "Which accepted decisions have not been implemented?",
];

const MAP_SUGGESTIONS = [
  "Where are the largest gaps in this business map?",
  "Which mapped capabilities need the most maturity attention?",
  "What capabilities should we consider adding next?",
];

const PHASE2_ACTIONS: Partial<Record<string, { label: string; href: string }>> = {
  reachable_vulnerabilities: { label: "Map Tier-1 applications", href: "/business-map" },
  package_business_blast_radius: { label: "Map applications to capabilities", href: "/business-map" },
  application_retirement_consolidation: { label: "Complete portfolio mappings", href: "/business-map" },
  modernization_blockers: { label: "Set runtime baselines", href: "/admin?tab=governance&area=eligibility" },
  custom_to_internal_platform: { label: "Govern platform replacements", href: "/admin?tab=governance&area=catalog" },
  internal_library_standards: { label: "Govern internal standards", href: "/admin?tab=governance&area=catalog" },
  assurance_coverage: { label: "Connect a source", href: "/admin?tab=data" },
  technology_introduction: { label: "Connect a source", href: "/admin?tab=data" },
  business_dark_capability: { label: "Govern critical capabilities", href: "/business-map" },
  decision_lag: { label: "Review modernization decisions", href: "/reviews" },
};

// Reports whose rows describe governed Business Map records rather than graph
// facts keep a link back to the map they were read from.
const REPORT_CONTEXT_LINKS: Partial<Record<string, ContextLink>> = {
  business_dark_capability: { label: "Open the Business Map", href: "/business-map" },
};

function serializeBusinessMap(context: BusinessMapContext): string {
  if (context.viewMode === "organization" && context.organizationUnits) {
    const units = context.organizationUnits.map((unit) =>
      `${unit.name}: ${unit.functions.length ? unit.functions.join(", ") : "no assigned functions"}`,
    );
    return `Organization map \"${context.title}\". ${units.join(" | ")}`;
  }
  const stages = context.stages.map((stage) => {
    const capabilities = stage.capabilities.length
      ? stage.capabilities.map((capability) => `${capability.name} (maturity ${capability.maturity}/5)`).join(", ")
      : "no mapped capabilities";
    return `${stage.name}: ${capabilities}`;
  });
  return `Business map \"${context.title}\" using the ${context.template} template. ${stages.join(" | ")}`;
}

export default function AskPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [mode, setMode] = useState<"overview" | "ask">("overview");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [businessMapContext, setBusinessMapContext] = useState<BusinessMapContext | null>(null);
  const openEvidence = useEvidenceStore((s) => s.open);
  const nextId = useRef(1);
  const listEndRef = useRef<HTMLDivElement>(null);
  const insightReports = useEnterpriseInsightReports();

  useEffect(() => {
    if (searchParams.get("view") === "ask") setMode("ask");
    else if (searchParams.get("source") !== "business-map") setMode("overview");
    if (searchParams.get("source") !== "business-map") return;
    setMode("ask");
    try {
      const raw = window.sessionStorage.getItem("stackgraph.ask.business-map-context");
      if (raw) setBusinessMapContext(JSON.parse(raw) as BusinessMapContext);
    } catch {
      // An unavailable map snapshot should fall back to the standard Ask experience.
    }
  }, [searchParams]);

  const ask = useMutation({
    mutationFn: (request: AskRequest) => stackGraphClient.ask({ question: request.requestQuestion }),
    onSuccess: (response, request) => {
      setTurns((t) => t.map((turn) => (turn.id === request.id ? { ...turn, response } : turn)));
      requestAnimationFrame(() => listEndRef.current?.scrollIntoView({ behavior: "smooth" }));
    },
    onError: (_e, request) => {
      setTurns((t) => t.map((turn) => (turn.id === request.id ? { ...turn, error: true } : turn)));
    },
  });

  const submit = (question: string) => {
    const q = question.trim();
    if (!q) return;
    const id = nextId.current++;
    setTurns((t) => [...t, { id, question: q }]);
    setInput("");
    ask.mutate({
      id,
      requestQuestion: businessMapContext ? `${q}\n\nAttached business-map context:\n${serializeBusinessMap(businessMapContext)}` : q,
    });
  };

  const suggestions = businessMapContext ? MAP_SUGGESTIONS : SUGGESTIONS;

  const openReport = (report: EnterpriseInsightReport) => {
    const action = report.status === "WAITING_FOR_DATA" ? PHASE2_ACTIONS[report.key] : undefined;
    if (action) {
      router.push(action.href);
      return;
    }
    const id = nextId.current++;
    setTurns([{
      id, question: report.question, response: report.response,
      contextLink: REPORT_CONTEXT_LINKS[report.key],
    }]);
    setMode("ask");
    router.replace("/ask?view=ask", { scroll: false });
    requestAnimationFrame(() => window.scrollTo({ top: 0, behavior: "smooth" }));
  };

  return (
    <div className={`${styles.page} ${mode === "overview" ? styles.pageWide : ""}`}>
      <header className={styles.head}>
        <h1 className={styles.title}>Insights</h1>
        <p className={styles.subtitle}>
          {mode === "overview"
            ? "Standing reports on enterprise risk, rationalization, and portfolio decisions, rebuilt from current graph facts."
            : businessMapContext
              ? "Questions are answered against the attached business map and the evidence already in your estate."
              : "Answers are built from facts already recorded in your estate, and each one carries the citations it was drawn from."}
        </p>
        <div className={styles.modeTabs} role="tablist" aria-label="Insight views">
          <button
            type="button"
            role="tab"
            aria-selected={mode === "overview"}
            className={mode === "overview" ? styles.modeTabActive : styles.modeTab}
            onClick={() => router.replace("/ask", { scroll: false })}
          >
            Overview
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={mode === "ask"}
            className={mode === "ask" ? styles.modeTabActive : styles.modeTab}
            onClick={() => router.replace("/ask?view=ask", { scroll: false })}
          >
            Ask
          </button>
        </div>
        {mode === "ask" && businessMapContext ? (
          <div className={styles.contextBanner}>
            <span className="sg-mono">BIZ MAP</span>
            <strong>{businessMapContext.title}</strong>
            <small>
              {businessMapContext.viewMode === "organization" && businessMapContext.organizationUnits
                ? `${businessMapContext.organizationUnits.length} units · ${businessMapContext.organizationUnits.reduce((total, unit) => total + unit.functions.length, 0)} mapped functions`
                : `${businessMapContext.stages.length} stages · ${businessMapContext.stages.reduce((total, stage) => total + stage.capabilities.length, 0)} mapped capabilities`}
            </small>
            <button
              type="button"
              onClick={() => {
                window.sessionStorage.removeItem("stackgraph.ask.business-map-context");
                setBusinessMapContext(null);
              }}
            >
              Detach
            </button>
          </div>
        ) : null}
      </header>

      {mode === "overview" ? (
        <InsightOverview
          data={insightReports.data}
          loading={insightReports.isLoading}
          error={insightReports.isError}
          onOpen={openReport}
        />
      ) : (
        <>
          {turns.length === 0 ? (
            <div className={styles.empty}>
              <p className={styles.emptyLabel}>Try asking</p>
              <div className={styles.suggestions}>
                {suggestions.map((s) => (
                  <button key={s} type="button" className={styles.suggestion} onClick={() => submit(s)}>
                    {s}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className={styles.thread}>
              {turns.map((turn) => (
                <div key={turn.id} className={styles.turn}>
                  <div className={styles.question}>
                    <span className={styles.qMark} aria-hidden="true">?</span>
                    <span>{turn.question}</span>
                  </div>
                  <div className={styles.answer}>
                    {turn.error ? (
                      <p className={styles.errorText}>Couldn’t reach the estate. Try again.</p>
                    ) : turn.response ? (
                      <AnswerView
                        response={turn.response}
                        onCite={openEvidence}
                        contextLink={turn.contextLink}
                      />
                    ) : (
                      <p className={styles.thinking}>
                        <span className={styles.dot} />
                        <span className={styles.dot} />
                        <span className={styles.dot} />
                      </p>
                    )}
                  </div>
                </div>
              ))}
              <div ref={listEndRef} />
            </div>
          )}

          <form
            className={styles.composer}
            onSubmit={(e) => {
              e.preventDefault();
              submit(input);
            }}
          >
            <input
              className={styles.composerInput}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Ask your estate…"
              aria-label="Ask your estate"
            />
            <button className={styles.send} type="submit" disabled={!input.trim() || ask.isPending}>
              Ask
            </button>
          </form>
        </>
      )}
    </div>
  );
}

const CATEGORY_LABELS: Record<EnterpriseInsightCategory, string> = {
  ENTERPRISE_RISK: "Enterprise risk",
  TECHNOLOGY_RATIONALIZATION: "Technology rationalization",
  PORTFOLIO_DECISIONS: "Portfolio decisions",
};

const CATEGORY_ORDER = Object.keys(CATEGORY_LABELS) as EnterpriseInsightCategory[];

function InsightOverview({
  data,
  loading,
  error,
  onOpen,
}: {
  data?: EnterpriseInsightReportList;
  loading: boolean;
  error: boolean;
  onOpen: (report: EnterpriseInsightReport) => void;
}) {
  if (loading) {
    return (
      <div className={styles.reportLoading} role="status" aria-label="Loading enterprise insight reports">
        {Array.from({ length: 6 }, (_, index) => <span key={index} />)}
      </div>
    );
  }
  if (error || !data) {
    return <p className={styles.reportError}>Insight reports couldn’t be evaluated. Try refreshing this view.</p>;
  }

  return (
    <div className={styles.overview}>
      <div className={styles.readiness}>
        <div>
          <span className={styles.readinessValue}>{data.answerable_reports}/{data.total_reports}</span>
          <span>reports answerable</span>
        </div>
        <p>
          {data.total_reports - data.answerable_reports > 0
            ? `${data.total_reports - data.answerable_reports} awaiting governed capability, platform, or lifecycle data.`
            : "Every enterprise report has the governed evidence it needs."}
        </p>
        <span className="sg-mono">Evaluated {formatRelative(data.evaluated_at)}</span>
      </div>

      {CATEGORY_ORDER.map((category) => {
        const reports = data.reports.filter((report) => report.category === category);
        return (
          <section key={category} className={styles.reportSection} aria-labelledby={`insight-${category}`}>
            <div className={styles.reportSectionHead}>
              <h2 id={`insight-${category}`}>{CATEGORY_LABELS[category]}</h2>
              <span>{reports.length} reports</span>
            </div>
            <div className={styles.reportGrid}>
              {reports.map((report) => (
                <button
                  key={report.key}
                  type="button"
                  className={styles.reportCard}
                  aria-label={`${report.title}: ${report.metric_value} ${report.metric_label}. ${report.status.replaceAll("_", " ")}`}
                  onClick={() => onOpen(report)}
                >
                  <span className={`${styles.reportStatus} ${styles[`status${report.status}`]}`}>
                    {report.status.replaceAll("_", " ")}
                  </span>
                  <strong>{report.title}</strong>
                  <span className={styles.reportMetric}>{report.metric_value}</span>
                  <span className={styles.reportMetricLabel}>{report.metric_label}</span>
                  <p>{report.summary}</p>
                  <span className={styles.reportMeta}>
                    {report.confidence != null ? `${Math.round(report.confidence * 100)}% confidence · ` : ""}
                    {report.evidence_count} evidence
                  </span>
                  <span className={styles.openReport}>
                    {report.status === "WAITING_FOR_DATA" && PHASE2_ACTIONS[report.key]
                      ? PHASE2_ACTIONS[report.key]?.label
                      : "Open report"} <span aria-hidden="true">→</span>
                  </span>
                </button>
              ))}
            </div>
          </section>
        );
      })}
    </div>
  );
}

function AnswerView({
  response,
  onCite,
  contextLink,
}: {
  response: AskResponse;
  onCite: (factId: string, label?: string) => void;
  contextLink?: ContextLink;
}) {
  const [showAllCitations, setShowAllCitations] = useState(false);
  const citationLimit = 12;
  const visibleCitations = showAllCitations
    ? response.citations
    : response.citations.slice(0, citationLimit);
  const hiddenCitationCount = response.citations.length - visibleCitations.length;

  return (
    <div className={styles.answerBody}>
      {response.result_kind === "UNSUPPORTED" ? (
        <p className={styles.unsupported}>{response.text}</p>
      ) : (
        <p className={styles.answerText}>{response.text}</p>
      )}

      {response.result_kind === "TABLE" && response.rows && response.rows.length > 0 ? (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                {Object.keys(response.rows[0]).map((k) => (
                  <th key={k}>{k.replaceAll("_", " ")}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {response.rows.map((row, i) => (
                <tr key={i}>
                  {Object.values(row).map((v, j) => (
                    <td key={j} className="sg-mono">
                      {v == null ? "—" : String(v)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      {contextLink ? (
        <Link className={styles.contextLink} href={contextLink.href}>
          {contextLink.label} <span aria-hidden="true">→</span>
        </Link>
      ) : null}

      {response.citations.length > 0 ? (
        <div className={styles.citations}>
          {visibleCitations.map((c) => (
            <CitationChip key={c.fact_id} label={c.label} onOpen={() => onCite(c.fact_id, c.label)} />
          ))}
          {hiddenCitationCount > 0 ? (
            <button
              type="button"
              className={styles.citationToggle}
              onClick={() => setShowAllCitations(true)}
            >
              Show {hiddenCitationCount} more evidence citations
            </button>
          ) : showAllCitations && response.citations.length > citationLimit ? (
            <button
              type="button"
              className={styles.citationToggle}
              onClick={() => setShowAllCitations(false)}
            >
              Show fewer citations
            </button>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
