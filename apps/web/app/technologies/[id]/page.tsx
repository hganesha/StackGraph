"use client";

import { use } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { stackGraphClient, sanitizeOrigin } from "@stackgraph/shared";
import { DomainBadge, ConfidenceChip, CitationChip, Skeleton } from "@stackgraph/design-system";
import { useEvidenceStore } from "@/lib/evidenceStore";
import { DeterministicInsightsPanel } from "@/components/insights/DeterministicInsightsPanel";
import styles from "./technology.module.css";

const compactNumber = new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 });

function classificationLabel(value: string) {
  if (value === "CATALOG_MATCH") return "Matched to curated technology";
  if (value === "CURATED") return "Curated technology";
  return "OSS catalog metadata";
}

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
        <DeterministicInsightsPanel
          scopeEntityId={id}
          title="Technology findings"
          description="Dependency and portfolio findings deterministically tied to this technology and its observed estate usage."
          limit={12}
        />
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

      {data.catalog_profile ? (
        <section className={styles.catalog} aria-label="OSS catalog intelligence">
          <div className={styles.catalogMain}>
            <header className={styles.catalogHead}>
              <div>
                <span className={styles.catalogEyebrow}>
                  <DomainBadge namespace="OSS" /> Catalog intelligence
                </span>
                <h2>{data.catalog_profile.catalog_technology?.name ?? data.catalog_profile.package_name ?? data.technology.name}</h2>
              </div>
              <span className={styles.classification}>{classificationLabel(data.catalog_profile.classification)}</span>
            </header>
            {data.catalog_profile.summary ? <p className={styles.catalogSummary}>{data.catalog_profile.summary}</p> : null}
            <div className={styles.taxonomyList} aria-label="Technology classification">
              {data.catalog_profile.domain ? <span>{data.catalog_profile.domain.name}</span> : null}
              {data.catalog_profile.category ? <span>{data.catalog_profile.category.name}</span> : null}
              {data.catalog_profile.functions.map((item) => (
                <span key={item.key} title={item.summary ?? undefined}>{item.name}</span>
              ))}
            </div>
            {data.catalog_profile.installation_command ? (
              <code className={`${styles.installCommand} sg-mono`}>{data.catalog_profile.installation_command}</code>
            ) : null}
            <div className={styles.catalogLinks}>
              {data.catalog_profile.homepage ? (
                <a href={data.catalog_profile.homepage} target="_blank" rel="noreferrer">Homepage ↗</a>
              ) : null}
              {data.catalog_profile.repository_url ? (
                <a href={data.catalog_profile.repository_url} target="_blank" rel="noreferrer">Source repository ↗</a>
              ) : null}
              {data.catalog_profile.package_url ? (
                <a href={data.catalog_profile.package_url} target="_blank" rel="noreferrer">Package registry ↗</a>
              ) : null}
            </div>
            <div className={styles.catalogEvidence}>
              {data.catalog_profile.citations.map((citation) => (
                <CitationChip
                  key={citation.fact_id}
                  label={citation.label}
                  onOpen={() => openEvidence(citation.fact_id, citation.label)}
                />
              ))}
            </div>
          </div>
          <dl className={styles.catalogFacts}>
            {data.catalog_profile.ecosystem ? (
              <div><dt>Ecosystem</dt><dd>{data.catalog_profile.ecosystem}</dd></div>
            ) : null}
            {data.catalog_profile.license ? (
              <div><dt>License</dt><dd>{data.catalog_profile.license}</dd></div>
            ) : null}
            {data.catalog_profile.latest_version ? (
              <div><dt>Catalog version</dt><dd>{data.catalog_profile.latest_version}</dd></div>
            ) : null}
            {data.catalog_profile.weekly_downloads != null ? (
              <div><dt>Weekly downloads</dt><dd>{compactNumber.format(data.catalog_profile.weekly_downloads)}</dd></div>
            ) : null}
            {data.catalog_profile.dependents != null ? (
              <div><dt>Catalog dependents</dt><dd>{compactNumber.format(data.catalog_profile.dependents)}</dd></div>
            ) : null}
            {data.catalog_profile.versions != null ? (
              <div><dt>Published versions</dt><dd>{compactNumber.format(data.catalog_profile.versions)}</dd></div>
            ) : null}
          </dl>
        </section>
      ) : null}

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
                  <Link href={`/repositories/${r.id}`}>{r.name}</Link>
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

      <DeterministicInsightsPanel
        scopeEntityId={id}
        title="Technology findings"
        description="Dependency and portfolio findings deterministically tied to this technology and its observed estate usage."
        limit={12}
      />

      {/* Recommendation engine */}
      <section className={styles.section} aria-label="Recommendations">
        <h2 className={styles.h2}>Investigative recommendation</h2>
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
