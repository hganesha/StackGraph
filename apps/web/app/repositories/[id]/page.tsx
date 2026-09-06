"use client";

import { use, useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { stackGraphClient, type RepositoryActivityWindow } from "@stackgraph/shared";
import { CitationChip, ConfidenceChip, DomainBadge, Skeleton } from "@stackgraph/design-system";
import { useEvidenceStore } from "@/lib/evidenceStore";
import { useEntityGraphMetrics } from "@/lib/queries";
import { DeterministicInsightsPanel } from "@/components/insights/DeterministicInsightsPanel";
import { GraphIntelligenceSummary } from "@/components/graph-intelligence/GraphIntelligenceSummary";
import { CriticalEdges } from "@/features/intelligence/CriticalEdges";
import { ChangeHistory } from "@/features/intelligence/ChangeHistory";
import { RepositoryFingerprint } from "@/features/intelligence/RepositoryFingerprint";
import { DescriptionEditor } from "@/components/entity/DescriptionEditor";
import { RecommendationFocus } from "./RecommendationFocus";
import { RepositoryActivityPanel } from "./RepositoryActivityPanel";
import styles from "./repository.module.css";

function EntityLinks({
  items,
  kind,
}: {
  items: Array<{ id: string; name: string }>;
  kind: "applications" | "technologies";
}) {
  if (items.length === 0) return <p className={styles.empty}>None linked yet.</p>;
  return (
    <ul className={styles.entityList}>
      {items.map((item) => (
        <li key={item.id}>
          <Link href={`/${kind}/${item.id}`}>{item.name}</Link>
        </li>
      ))}
    </ul>
  );
}

function TagList({ values }: { values: string[] }) {
  if (values.length === 0) return <span className={styles.unknown}>Not observed</span>;
  return (
    <ul className={styles.tags}>
      {values.map((value) => <li key={value}>{value}</li>)}
    </ul>
  );
}

export default function RepositoryPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ recommendation?: string }>;
}) {
  const { id } = use(params);
  const { recommendation } = use(searchParams);
  const [activityWindow, setActivityWindow] = useState<RepositoryActivityWindow>("30d");
  const [findingsExpanded, setFindingsExpanded] = useState(false);
  const openEvidence = useEvidenceStore((state) => state.open);
  const { data, isLoading } = useQuery({
    queryKey: ["repository", id],
    queryFn: () => stackGraphClient.getRepository(id),
  });
  const activity = useQuery({
    queryKey: ["repository-activity", id, activityWindow],
    queryFn: () => stackGraphClient.getRepositoryActivity(id, { window: activityWindow, limit: 6 }),
  });
  const graphIntelligence = useEntityGraphMetrics(id);

  if (isLoading || !data) {
    return (
      <div className={styles.page}>
        <Skeleton height={18} width="26%" />
        <Skeleton height={36} width="48%" />
        <Skeleton height={150} width="100%" />
        <Skeleton height={260} width="100%" />
      </div>
    );
  }

  if (recommendation) {
    return <RecommendationFocus recommendationId={recommendation} repository={data} />;
  }

  const { profile } = data;
  return (
    <div className={styles.page}>
      <nav className={styles.crumbs} aria-label="Breadcrumb">
        <Link href="/estate">Estate</Link>
        <span aria-hidden="true">›</span>
        <span className={styles.crumbCurrent}>
          <DomainBadge namespace="ENTERPRISE" />
          <span className="sg-mono">{data.repository.name}</span>
        </span>
      </nav>

      <header className={styles.head}>
        <div>
          <span className={styles.eyebrow}>Repository profile</span>
          <h1 className={`${styles.title} sg-mono`}>{data.repository.name}</h1>
          {data.repository.canonical_key ? (
            <code className={`${styles.canonical} sg-mono`}>{data.repository.canonical_key}</code>
          ) : null}
          <DescriptionEditor
            kind="repository"
            entityId={id}
            description={data.repository.summary}
            queryKey={["repository", id]}
          />
          {activity.data ? (
            <div className={styles.repositoryMeta} aria-label="Repository metadata">
              {activity.data.source.full_name ? <span>{activity.data.source.full_name}</span> : null}
              <span>Default branch: {activity.data.source.default_branch ?? "unknown"}</span>
              <span>{activity.data.source.visibility.toLowerCase()}</span>
              {activity.data.source.archived ? <span>Archived</span> : null}
            </div>
          ) : null}
        </div>
        <span className={styles.freshness}>{data.freshness.status}</span>
      </header>

      <section className={styles.purpose} aria-labelledby="repository-purpose-heading">
        <div className={styles.sectionHead}>
          <div>
            <span className={styles.eyebrow}>Declared intent</span>
            <h2 id="repository-purpose-heading">What this repository does</h2>
          </div>
          {profile ? <ConfidenceChip label={profile.confidence_label} value={profile.confidence} /> : null}
        </div>
        <p className={profile?.purpose ? styles.purposeText : styles.empty}>
          {profile?.purpose ?? "No purpose statement was found in the admitted README or manifest files."}
        </p>
        {profile ? (
          <div className={styles.provenance}>
            <span>
              Source {profile.purpose_source ?? "repository inventory"} · revision{" "}
              <code className="sg-mono">{profile.source_revision.slice(0, 12)}</code>
            </span>
            {profile.citations.map((citation) => (
              <CitationChip
                key={citation.fact_id}
                label={citation.label}
                onOpen={() => openEvidence(citation.fact_id, citation.label)}
              />
            ))}
          </div>
        ) : null}
      </section>

      <RepositoryActivityPanel
        data={activity.data}
        isLoading={activity.isLoading}
        isError={activity.isError}
        window={activityWindow}
        onWindowChange={setActivityWindow}
      />

      <section className={styles.context} aria-labelledby="repository-context-heading">
        <div>
          <span className={styles.eyebrow}>Repository context</span>
          <h2 id="repository-context-heading">How it fits into the estate</h2>
        </div>
        <p>Graph-derived relationships and admitted repository inventory.</p>
      </section>

      <GraphIntelligenceSummary
        entityId={id}
        intelligence={graphIntelligence.data}
        graphHref={`/repositories/${id}/graph`}
        compact
      />

      <RepositoryFingerprint repositoryId={id} repositoryName={data.repository.name} />

      <CriticalEdges entityId={id} />

      <ChangeHistory entityId={id} entityName={data.repository.name} />

      <div className={styles.grid}>
        <section className={styles.card} aria-labelledby="repository-shape-heading">
          <h2 id="repository-shape-heading">Repository shape</h2>
          <dl className={styles.profileFacts}>
            <div><dt>Languages</dt><dd><TagList values={profile?.languages ?? []} /></dd></div>
            <div><dt>Components</dt><dd><TagList values={profile?.components ?? []} /></dd></div>
            <div><dt>Operational signals</dt><dd><TagList values={profile?.operational_signals ?? []} /></dd></div>
          </dl>
        </section>

        <section className={styles.card} aria-labelledby="repository-sources-heading">
          <h2 id="repository-sources-heading">Summary sources</h2>
          <TagList values={profile?.key_files ?? []} />
          {profile && profile.descriptions.length > 1 ? (
            <div className={styles.additionalDescription}>
              <span>Additional declared description</span>
              <p>{profile.descriptions[1]}</p>
            </div>
          ) : null}
        </section>

        <section className={styles.card} aria-labelledby="repository-applications-heading">
          <div className={styles.cardHeading}>
            <h2 id="repository-applications-heading">Applications</h2>
            <span>{data.applications.length}</span>
          </div>
          <EntityLinks items={data.applications} kind="applications" />
        </section>

        <section className={styles.card} aria-labelledby="repository-technologies-heading">
          <div className={styles.cardHeading}>
            <h2 id="repository-technologies-heading">Technologies</h2>
            <span>{data.technologies.length}</span>
          </div>
          <EntityLinks items={data.technologies} kind="technologies" />
        </section>
      </div>

      <DeterministicInsightsPanel
        scopeEntityId={id}
        title="Repository findings"
        description="Current deterministic findings whose evidence or affected scope includes this repository."
        limit={findingsExpanded ? 12 : 3}
      />
      <div className={styles.findingsAction}>
        <button type="button" onClick={() => setFindingsExpanded((value) => !value)}>
          {findingsExpanded ? "Show fewer findings" : "Show all findings"}
        </button>
      </div>

      {profile && profile.limitations.length > 0 ? (
        <aside className={styles.limitations} aria-label="Profile limitations">
          <strong>Interpretation limits</strong>
          <ul>{profile.limitations.map((value) => <li key={value}>{value}</li>)}</ul>
        </aside>
      ) : null}
    </div>
  );
}
