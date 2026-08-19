"use client";

import { use } from "react";
import { useQuery } from "@tanstack/react-query";
import { stackGraphClient } from "@stackgraph/shared";
import { DomainBadge, ConfidenceChip, CitationChip, Skeleton } from "@stackgraph/design-system";
import { useEvidenceStore } from "@/lib/evidenceStore";
import styles from "./application.module.css";

export default function ApplicationPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const openEvidence = useEvidenceStore((s) => s.open);
  const { data, isLoading } = useQuery({
    queryKey: ["application", id],
    queryFn: () => stackGraphClient.getApplication(id),
  });

  if (isLoading || !data) {
    return (
      <div className={styles.page}>
        <Skeleton height={28} width="40%" />
        <Skeleton height={16} width="70%" />
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <nav className={styles.crumbs} aria-label="Breadcrumb">
        <a href="/estate" className={styles.crumb}>
          Estate
        </a>
        <span aria-hidden="true">›</span>
        <span className={styles.crumbCurrent}>
          <DomainBadge namespace="ENTERPRISE" /> <span className="sg-mono">{data.application.name}</span>
        </span>
      </nav>

      <header className={styles.head}>
        <h1 className={`${styles.title} sg-mono`}>{data.application.name}</h1>
        {data.application.summary ? <p className={styles.summary}>{data.application.summary}</p> : null}
      </header>

      {data.business_context.length > 0 ? (
        <section className={styles.section} aria-label="Business context">
          <h2 className={styles.h2}>Business context</h2>
          <div className={styles.chips}>
            {data.business_context.map((e) => (
              <span key={e.id} className={styles.chip}>
                <DomainBadge namespace="BUSINESS" /> {e.name}
              </span>
            ))}
          </div>
        </section>
      ) : null}

      <section className={styles.section} aria-label="Assessments">
        <h2 className={styles.h2}>Assessments</h2>
        <ul className={styles.assessments}>
          {data.assessments.map((a) => {
            const cite = a.citations[0];
            return (
              <li key={a.id} className={styles.assessment}>
                <span className={styles.dimension}>{a.dimension}</span>
                <span className={`${styles.value} sg-mono`}>{a.categorical_value ?? a.score}</span>
                <span className={styles.assessTail}>
                  <ConfidenceChip label={a.confidence_label} value={a.confidence} />
                  {cite ? <CitationChip label={cite.label} onOpen={() => openEvidence(cite.fact_id, cite.label)} /> : null}
                </span>
              </li>
            );
          })}
        </ul>
      </section>

      <section className={styles.section} aria-label="Recommendations">
        <h2 className={styles.h2}>Recommendations</h2>
        <div className={styles.recs}>
          {data.recommendations.map((r) => (
            <article key={r.id} className={styles.rec}>
              <div className={styles.recHead}>
                <span className={`${styles.action} sg-mono`}>{r.action}</span>
                <ConfidenceChip label={r.confidence_label} value={r.confidence} />
              </div>
              <h3 className={styles.recTitle}>{r.title}</h3>
              <p className={styles.recRationale}>{r.rationale}</p>
            </article>
          ))}
        </div>
      </section>

      <p className={styles.footnote}>
        Full evidence drawer, viability radar, and uncertain-bridge actions land in Phase 1–2.
      </p>
    </div>
  );
}
