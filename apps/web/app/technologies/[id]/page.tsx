"use client";

import { use } from "react";
import { useQuery } from "@tanstack/react-query";
import { stackGraphClient, sanitizeOrigin } from "@stackgraph/shared";
import { DomainBadge, ConfidenceChip, CitationChip, Skeleton } from "@stackgraph/design-system";
import { useEvidenceStore } from "@/lib/evidenceStore";
import styles from "./technology.module.css";

export default function TechnologyPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const openEvidence = useEvidenceStore((s) => s.open);
  const { data, isLoading } = useQuery({
    queryKey: ["technology", id],
    queryFn: () => stackGraphClient.getTechnology(id),
  });

  if (isLoading || !data) {
    return (
      <div className={styles.page}>
        <Skeleton height={28} width="45%" />
        <Skeleton height={16} width="70%" />
      </div>
    );
  }

  const visBadge = (v: string) =>
    v === "PRIVATE" ? styles.visPrivate : v === "PUBLIC" ? styles.visPublic : styles.visUnknown;

  return (
    <div className={styles.page}>
      <nav className={styles.crumbs} aria-label="Breadcrumb">
        <a href="/technologies" className={styles.crumb}>
          Technologies
        </a>
        <span aria-hidden="true">›</span>
        <span className={styles.crumbCurrent}>
          <DomainBadge namespace="TECHNOLOGY" /> <span className="sg-mono">{data.technology.name}</span>
        </span>
      </nav>

      <header className={styles.head}>
        <div className={styles.headMain}>
          <h1 className={`${styles.title} sg-mono`}>{data.technology.name}</h1>
          {data.technology.canonical_key ? (
            <code className={`${styles.canonical} sg-mono`}>{data.technology.canonical_key}</code>
          ) : null}
        </div>
        {/* This package is a bridge concept — the entry into the bounded Graph Explore lens (plan §5.5). */}
        <a href={`/technologies/${id}/graph`} className={styles.exploreBtn}>
          <span aria-hidden="true">◇</span> Explore neighborhood
        </a>
      </header>

      <div className={styles.panes}>
        {/* Internal estate */}
        <section className={styles.pane} aria-label="Internal usage">
          <h2 className={styles.h2}>Internal estate</h2>
          <div className={styles.usageStats}>
            <div className={styles.usageStat}>
              <span className={`${styles.usageNum} sg-mono`}>{data.internal_usage.repository_count}</span>
              <span className={styles.usageLabel}>repositories</span>
            </div>
            <div className={styles.usageStat}>
              <span className={`${styles.usageNum} sg-mono`}>{data.internal_usage.application_count}</span>
              <span className={styles.usageLabel}>applications</span>
            </div>
          </div>
          {data.internal_usage.repositories && data.internal_usage.repositories.length > 0 ? (
            <ul className={styles.chipList}>
              {data.internal_usage.repositories.map((r) => (
                <li key={r.id} className={`${styles.chip} sg-mono`}>
                  {r.name}
                </li>
              ))}
            </ul>
          ) : null}
        </section>

        {/* OSS intelligence — first-class, not enrichment */}
        <section className={styles.pane} aria-label="OSS intelligence">
          <h2 className={styles.h2}>
            <DomainBadge namespace="OSS" /> OSS intelligence
          </h2>
          {data.projects.length > 0 ? (
            <div className={styles.subgroup}>
              <span className={styles.subLabel}>Projects</span>
              <ul className={styles.chipList}>
                {data.projects.map((p) => (
                  <li key={p.id} className={styles.chip}>
                    {p.name}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          {data.alternatives && data.alternatives.length > 0 ? (
            <div className={styles.subgroup}>
              <span className={styles.subLabel}>Alternatives</span>
              <ul className={styles.chipList}>
                {data.alternatives.map((a) => (
                  <li key={a.id} className={styles.chip}>
                    {a.name}
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <p className={styles.empty}>No alternatives identified yet.</p>
          )}
        </section>
      </div>

      {/* Registry sources — private-registry honesty; origins are sanitized */}
      {data.registry_sources && data.registry_sources.length > 0 ? (
        <section className={styles.section} aria-label="Registry sources">
          <h2 className={styles.h2}>Registry sources</h2>
          <ul className={styles.registryList}>
            {data.registry_sources.map((s) => (
              <li key={s.registry_key} className={styles.registry}>
                <span className={`${styles.registryKey} sg-mono`}>{s.registry_key}</span>
                <code className={`${styles.registryOrigin} sg-mono`}>{sanitizeOrigin(s.origin)}</code>
                <span className={`${styles.vis} ${visBadge(s.visibility)}`}>{s.visibility}</span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {/* Recommendation engine */}
      <section className={styles.section} aria-label="Recommendations">
        <h2 className={styles.h2}>Recommendation</h2>
        {data.recommendations.length > 0 ? (
          <div className={styles.recs}>
            {data.recommendations.map((r) => (
              <article key={r.id} className={styles.rec}>
                <div className={styles.recHead}>
                  <span className={`${styles.action} sg-mono`}>{r.action}</span>
                  <ConfidenceChip label={r.confidence_label} value={r.confidence} />
                </div>
                <h3 className={styles.recTitle}>{r.title}</h3>
                <p className={styles.recRationale}>{r.rationale}</p>
                {r.counter_signals && r.counter_signals.length > 0 ? (
                  <div className={styles.counter}>
                    <span className={styles.counterLabel}>Counter-signals</span>
                    <ul>
                      {r.counter_signals.map((c, i) => (
                        <li key={i}>{c}</li>
                      ))}
                    </ul>
                  </div>
                ) : null}
                {r.citations[0] ? (
                  <CitationChip
                    label={r.citations[0].label}
                    onOpen={() => openEvidence(r.citations[0]!.fact_id, r.citations[0]!.label)}
                  />
                ) : null}
              </article>
            ))}
          </div>
        ) : (
          <p className={styles.empty}>
            No recommendation yet — resolved once capability, viability, and migration evidence are assessed.
          </p>
        )}
      </section>
    </div>
  );
}
