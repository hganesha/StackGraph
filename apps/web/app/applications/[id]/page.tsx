"use client";

import { use } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { stackGraphClient } from "@stackgraph/shared";
import { DomainBadge, ConfidenceChip, CitationChip, Skeleton } from "@stackgraph/design-system";
import { useEvidenceStore } from "@/lib/evidenceStore";
import { ApplicationDependencyHierarchy } from "./DependencyHierarchy";
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

  const dependencyHierarchies = data.dependency_hierarchies ?? [];

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
        <div className={styles.headMain}>
          <h1 className={`${styles.title} sg-mono`}>{data.application.name}</h1>
          {data.application.summary ? <p className={styles.summary}>{data.application.summary}</p> : null}
        </div>
        <Link href={`/applications/${id}/graph`} className={styles.exploreBtn}>
          <span aria-hidden="true">◇</span> Explore neighborhood
        </Link>
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

      <section className={styles.section} aria-label="Technology landscape">
        <div className={styles.sectionHeading}>
          <h2 className={styles.h2}>Technology landscape</h2>
          <span className={styles.sectionCount}>{data.technologies.length} linked</span>
        </div>
        <ApplicationDependencyHierarchy
          hierarchies={dependencyHierarchies}
          technologyGroups={data.technology_groups}
        />
        <div className={styles.subsectionHeading}>
          <h3 className={styles.subsectionTitle}>Architecture classification</h3>
          <p>Technology roles inferred from curated catalog evidence.</p>
        </div>
        {data.technology_groups.length > 0 ? (
          <div className={styles.technologyGroups}>
            {data.technology_groups.map((group) => (
              <article key={group.domain.key} className={styles.technologyDomain}>
                <header className={styles.domainHead}>
                  <h3 className={styles.domainTitle}>{group.domain.name}</h3>
                  <span className={styles.domainCount}>
                    {new Set(group.functions.flatMap((item) => item.technologies.map((usage) => usage.technology.id))).size} technologies
                  </span>
                </header>
                <div className={styles.functionList}>
                  {group.functions.map((item) => (
                    <section key={item.function.key} className={styles.functionGroup}>
                      <div className={styles.functionHead}>
                        <div>
                          <h4 className={styles.functionTitle}>{item.function.name}</h4>
                          {item.function.summary ? (
                            <p className={styles.functionSummary}>{item.function.summary}</p>
                          ) : null}
                        </div>
                      </div>
                      <ul className={styles.technologyList}>
                        {item.technologies.map((usage) => (
                          <li key={usage.technology.id} className={styles.technologyRow}>
                            <div className={styles.technologyMain}>
                              <Link href={`/technologies/${usage.technology.id}`} className={`${styles.technologyName} sg-mono`}>
                                {usage.technology.name}
                              </Link>
                              {usage.technology.summary ? (
                                <p className={styles.technologySummary}>{usage.technology.summary}</p>
                              ) : null}
                              <div className={styles.technologyMeta}>
                                {usage.category ? <span className={styles.category}>{usage.category.name}</span> : null}
                                <span className={usage.classification === "UNCLASSIFIED" ? styles.needsClassification : styles.classification}>
                                  {usage.classification === "CURATED"
                                    ? "Curated catalog"
                                    : usage.classification === "CATALOG_MATCH"
                                      ? "Exact catalog match"
                                      : "Needs classification"}
                                </span>
                              </div>
                            </div>
                            <div className={styles.technologyEvidence}>
                              {usage.classification !== "UNCLASSIFIED" ? (
                                <ConfidenceChip label={usage.confidence_label} value={usage.confidence} />
                              ) : null}
                              {usage.citations.map((citation) => (
                                <CitationChip
                                  key={citation.fact_id}
                                  label={citation.label}
                                  onOpen={() => openEvidence(citation.fact_id, citation.label)}
                                />
                              ))}
                            </div>
                          </li>
                        ))}
                      </ul>
                    </section>
                  ))}
                </div>
              </article>
            ))}
          </div>
        ) : (
          <p className={styles.emptyTechnology}>No technology usage has been linked to this application yet.</p>
        )}
      </section>

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
        <h2 className={styles.h2}>Investigative recommendations</h2>
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
