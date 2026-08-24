"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { formatRelative, type EntityGraphIntelligence, type GraphMetric } from "@stackgraph/shared";
import { Skeleton } from "@stackgraph/design-system";
import { useEntityBlastRadius, useReviewApplicationSimilarity, useSimilarApplications } from "@/lib/queries";
import { useEvidenceStore } from "@/lib/evidenceStore";
import styles from "./graph-intelligence-summary.module.css";

const METRIC_LABELS: Record<string, string> = {
  "reachability.upstream_impact": "Upstream impact",
  "reachability.downstream_dependencies": "Dependencies",
  "reachability.upstream_depth": "Impact depth",
  "reachability.downstream_depth": "Dependency depth",
  "centrality.pagerank": "PageRank",
  "centrality.betweenness": "Betweenness",
  "structure.articulation_point": "Bridge / SPOF",
  "degree.in": "Dependents",
  "degree.out": "Direct dependencies",
};

const STATUS_LABELS: Record<EntityGraphIntelligence["primary_status"], string> = {
  STRUCTURALLY_CRITICAL: "Structurally critical",
  ELEVATED: "Elevated",
  TYPICAL: "Typical",
  WAITING_FOR_DATA: "Waiting for data",
};

function displayMetric(metric: GraphMetric) {
  if (metric.metric_key === "structure.articulation_point") {
    return metric.numeric_value === 1 ? "Yes" : "No";
  }
  if (metric.numeric_value == null) return "—";
  if (metric.metric_key.includes("pagerank") || metric.metric_key.includes("betweenness")) {
    return metric.numeric_value.toLocaleString(undefined, { maximumFractionDigits: 4 });
  }
  return metric.numeric_value.toLocaleString(undefined, { maximumFractionDigits: 1 });
}

function displayDetail(value: unknown): string {
  if (Array.isArray(value)) return value.map(String).join(" · ");
  if (value && typeof value === "object") {
    return Object.entries(value as Record<string, unknown>)
      .map(([key, nested]) => `${key}: ${displayDetail(nested)}`)
      .join(" · ");
  }
  return value == null || value === "" ? "Not observed" : String(value);
}

function DetailList({ label, details }: { label: string; details: Record<string, unknown> }) {
  const entries = Object.entries(details);
  if (!entries.length) return null;
  return (
    <div className={styles.similarityDetails}>
      <h4>{label}</h4>
      <dl>
        {entries.map(([key, value]) => (
          <div key={key}><dt>{key.replaceAll("_", " ")}</dt><dd>{displayDetail(value)}</dd></div>
        ))}
      </dl>
    </div>
  );
}

export function GraphIntelligenceSummary({
  entityId,
  intelligence,
  graphHref,
  compact = false,
  similarityAvailable = false,
}: {
  entityId: string;
  intelligence?: EntityGraphIntelligence | null;
  graphHref: string;
  compact?: boolean;
  similarityAvailable?: boolean;
}) {
  const [showBlastRadius, setShowBlastRadius] = useState(false);
  const [showSimilarity, setShowSimilarity] = useState(false);
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const similarityCloseButtonRef = useRef<HTMLButtonElement>(null);
  const blastRadius = useEntityBlastRadius(entityId, showBlastRadius);
  const similarity = useSimilarApplications(entityId, showSimilarity && similarityAvailable);
  const similarityReview = useReviewApplicationSimilarity(entityId);
  const openEvidence = useEvidenceStore((state) => state.open);
  const metrics = useMemo(
    () => (intelligence?.metrics ?? [])
      .filter((metric) => METRIC_LABELS[metric.metric_key])
      .sort((left, right) => (right.percentile ?? -1) - (left.percentile ?? -1))
      .slice(0, compact ? 4 : 6),
    [compact, intelligence?.metrics],
  );

  useEffect(() => {
    if (!showBlastRadius && !showSimilarity) return;
    (showBlastRadius ? closeButtonRef : similarityCloseButtonRef).current?.focus();
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setShowBlastRadius(false);
        setShowSimilarity(false);
      }
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [showBlastRadius, showSimilarity]);

  const waiting = !intelligence || intelligence.primary_status === "WAITING_FOR_DATA";
  const limitations = intelligence?.limitations ?? [];

  return (
    <section className={styles.panel} aria-labelledby={`graph-intelligence-${entityId}`}>
      <header className={styles.head}>
        <div>
          <span className={styles.eyebrow}>Graph intelligence</span>
          <h2 id={`graph-intelligence-${entityId}`}>{waiting ? "Waiting for a complete graph snapshot" : STATUS_LABELS[intelligence.primary_status]}</h2>
        </div>
        {intelligence ? <span className={styles.freshness}>Updated {formatRelative(intelligence.as_of)}</span> : null}
      </header>

      {waiting ? (
        <p className={styles.waiting}>
          StackGraph will classify this entity after its tenant projection catches up and a complete runtime-dependency analysis succeeds.
        </p>
      ) : (
        <>
          <div className={styles.metrics}>
            {metrics.map((metric) => (
              <div key={`${metric.analysis_run_id}:${metric.metric_key}`} className={styles.metric}>
                <span>{METRIC_LABELS[metric.metric_key] ?? metric.metric_key}</span>
                <strong className="sg-mono">{displayMetric(metric)}</strong>
                <small>{metric.percentile == null ? "Percentile unavailable" : `${Math.round(metric.percentile * 100)}th estate percentile`}</small>
              </div>
            ))}
          </div>
          {intelligence.reasons.length ? (
            <ul className={styles.reasons}>
              {intelligence.reasons.slice(0, 2).map((reason) => <li key={reason}>{reason}</li>)}
            </ul>
          ) : null}
        </>
      )}

      {(limitations.length > 0 || intelligence?.snapshots.some((snapshot) => snapshot.limitations.length > 0)) ? (
        <p className={styles.limitation}>Coverage is limited; open the blast-radius detail for snapshot limitations.</p>
      ) : null}

      <div className={styles.actions}>
        <button type="button" onClick={() => setShowBlastRadius(true)} disabled={waiting}>View blast radius</button>
        <Link href={graphHref}>Explore dependencies</Link>
        {similarityAvailable ? <button type="button" onClick={() => setShowSimilarity(true)}>Similar applications</button> : null}
      </div>

      {showBlastRadius ? (
        <div className={styles.backdrop} role="presentation" onMouseDown={(event) => {
          if (event.currentTarget === event.target) setShowBlastRadius(false);
        }}>
          <aside className={styles.drawer} role="dialog" aria-modal="true" aria-labelledby="blast-radius-heading">
            <header className={styles.drawerHead}>
              <div>
                <span className={styles.eyebrow}>Evidence-backed traversal</span>
                <h2 id="blast-radius-heading">Blast radius</h2>
              </div>
              <button ref={closeButtonRef} type="button" onClick={() => setShowBlastRadius(false)} aria-label="Close blast radius">×</button>
            </header>
            {blastRadius.isLoading ? (
              <div className={styles.drawerLoading}><Skeleton height={72} /><Skeleton height={160} /></div>
            ) : blastRadius.isError || !blastRadius.data ? (
              <p className={styles.waiting} role="alert">Blast radius is temporarily unavailable. The last entity snapshot remains visible.</p>
            ) : (
              <div className={styles.drawerBody}>
                <dl className={styles.blastFacts}>
                  <div><dt>Affected entities</dt><dd>{blastRadius.data.affected_entity_count}</dd></div>
                  <div><dt>Maximum depth</dt><dd>{blastRadius.data.maximum_depth}</dd></div>
                </dl>
                {blastRadius.data.impacts.length ? (
                  <ol className={styles.paths}>
                    {blastRadius.data.impacts.map((impact) => (
                      <li key={`${impact.target.id}:${impact.entity_ids.join(":")}`}>
                        <div><strong>{impact.target.name}</strong><span>{impact.distance} hop{impact.distance === 1 ? "" : "s"} · {Math.round(impact.minimum_confidence * 100)}% minimum confidence</span></div>
                        <p className="sg-mono">{impact.entity_ids.join(" → ")}</p>
                        <div className={styles.facts}>
                          {impact.supporting_fact_ids.map((factId) => (
                            <button key={factId} type="button" onClick={() => openEvidence(factId, `Blast-radius path fact ${factId.slice(0, 8)}`)}>
                              Evidence {factId.slice(0, 8)}
                            </button>
                          ))}
                        </div>
                      </li>
                    ))}
                  </ol>
                ) : <p className={styles.waiting}>No application or capability impact path is present in this complete snapshot.</p>}
                {blastRadius.data.limitations.map((limitation, index) => (
                  <p key={`${String(limitation.code ?? "limitation")}:${index}`} className={styles.limitation}>
                    {String(limitation.message ?? limitation.code ?? "This result has a coverage limitation.")}
                  </p>
                ))}
              </div>
            )}
          </aside>
        </div>
      ) : null}

      {showSimilarity ? (
        <div className={styles.backdrop} role="presentation" onMouseDown={(event) => {
          if (event.currentTarget === event.target) setShowSimilarity(false);
        }}>
          <aside className={styles.drawer} role="dialog" aria-modal="true" aria-labelledby="similarity-heading">
            <header className={styles.drawerHead}>
              <div>
                <span className={styles.eyebrow}>Governed portfolio signal</span>
                <h2 id="similarity-heading">Similar applications</h2>
              </div>
              <button ref={similarityCloseButtonRef} type="button" onClick={() => setShowSimilarity(false)} aria-label="Close similar applications">×</button>
            </header>
            {similarity.isLoading ? (
              <div className={styles.drawerLoading}><Skeleton height={120} /><Skeleton height={120} /></div>
            ) : similarity.isError || !similarity.data ? (
              <p className={styles.waiting} role="alert">Similarity is unavailable until an evaluated semantic space and enough application context are active.</p>
            ) : similarity.data.candidates.length ? (
              <div className={styles.drawerBody}>
                <p className={styles.waiting}>Scores combine semantic meaning, rare dependencies, capabilities, and technology context. Review the evidence below before making a consolidation decision.</p>
                <ol className={styles.similarityList}>
                  {similarity.data.candidates.map((candidate) => (
                    <li key={candidate.id}>
                      <header>
                        <div><strong>{candidate.application.name}</strong><span>{candidate.review_state.replaceAll("_", " ").toLowerCase()}</span></div>
                        <span className="sg-mono">{Math.round(candidate.score * 100)}%</span>
                      </header>
                      <DetailList label="Why it matches" details={candidate.overlaps} />
                      <DetailList label="What is different" details={candidate.differences} />
                      <DetailList label="Signal coverage" details={candidate.coverage} />
                      {candidate.limitations.map((limitation, index) => (
                        <p key={`${String(limitation.code ?? "limitation")}:${index}`} className={styles.limitation}>{String(limitation.message ?? limitation.code ?? "A similarity input is incomplete.")}</p>
                      ))}
                      <div className={styles.candidateActions}>
                        <Link href={`/applications/${candidate.application.id}`}>Open application</Link>
                        {candidate.review_state === "UNREVIEWED" ? (
                          <>
                            <button type="button" disabled={similarityReview.isPending} onClick={() => similarityReview.mutate({ candidateId:candidate.id,decision:"CONFIRMED_SIMILAR" })}>Confirm match</button>
                            <button type="button" disabled={similarityReview.isPending} onClick={() => similarityReview.mutate({ candidateId:candidate.id,decision:"CONFIRMED_DISTINCT" })}>Mark distinct</button>
                            <button type="button" disabled={similarityReview.isPending} onClick={() => similarityReview.mutate({ candidateId:candidate.id,decision:"CONSOLIDATION_CANDIDATE" })}>Consider consolidation</button>
                          </>
                        ) : null}
                      </div>
                    </li>
                  ))}
                </ol>
                {similarity.data.limitations.map((limitation, index) => (
                  <p key={`${String(limitation.code ?? "limitation")}:${index}`} className={styles.limitation}>{String(limitation.message ?? limitation.code ?? "This result has a coverage limitation.")}</p>
                ))}
                {similarityReview.isError ? <p className={styles.limitation} role="alert">The review could not be saved. Your current similarity results are unchanged.</p> : null}
              </div>
            ) : <p className={styles.waiting}>No sufficiently similar applications are present in the evaluated candidate set.</p>}
          </aside>
        </div>
      ) : null}
    </section>
  );
}
