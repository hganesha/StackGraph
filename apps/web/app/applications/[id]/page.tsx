"use client";

import { use, useEffect, useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { stackGraphClient } from "@stackgraph/shared";
import { ConfidenceChip, DomainBadge, Skeleton } from "@stackgraph/design-system";
import { ApplicationViewSwitch } from "./ApplicationViewSwitch";
import { TechnologyWorkspace } from "./TechnologyWorkspace";
import { DeterministicInsightsPanel } from "@/components/insights/DeterministicInsightsPanel";
import { GraphIntelligenceSummary } from "@/components/graph-intelligence/GraphIntelligenceSummary";
import { CriticalEdges } from "@/features/intelligence/CriticalEdges";
import { DescriptionEditor } from "@/components/entity/DescriptionEditor";
import styles from "./application.module.css";

type ApplicationTab = "overview" | "technology" | "assessments" | "recommendations";

const TABS: Array<{ id: ApplicationTab; label: string }> = [
  { id: "overview", label: "Overview" },
  { id: "technology", label: "Technology" },
  { id: "assessments", label: "Assessments" },
  { id: "recommendations", label: "Recommendations" },
];

function EmptyPanel({ children }: { children: string }) {
  return <p className={styles.emptyPanel}>{children}</p>;
}

export default function ApplicationPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ tab?: string | string[] }>;
}) {
  const { id } = use(params);
  const requestedTabValue = use(searchParams).tab;
  const requestedTab = typeof requestedTabValue === "string" ? requestedTabValue : undefined;
  const [activeTab, setActiveTab] = useState<ApplicationTab>(
    TABS.some((tab) => tab.id === requestedTab) ? requestedTab as ApplicationTab : "overview",
  );
  const { data, isLoading } = useQuery({
    queryKey: ["application", id],
    queryFn: () => stackGraphClient.getApplication(id),
  });

  useEffect(() => {
    if (data && activeTab === "overview" && window.location.hash === "#services") {
      requestAnimationFrame(() => document.getElementById("services")?.scrollIntoView({ block: "start" }));
    }
  }, [activeTab, data]);

  if (isLoading || !data) {
    return (
      <div className={styles.page}>
        <Skeleton height={18} width="28%" />
        <Skeleton height={32} width="42%" />
        <Skeleton height={44} width="100%" />
        <Skeleton height={360} width="100%" />
      </div>
    );
  }

  const dependencyHierarchies = data.dependency_hierarchies ?? [];
  const moveTabFocus = (current: ApplicationTab, direction: -1 | 1 | "first" | "last") => {
    const currentIndex = TABS.findIndex((tab) => tab.id === current);
    const nextIndex = direction === "first"
      ? 0
      : direction === "last"
        ? TABS.length - 1
        : (currentIndex + direction + TABS.length) % TABS.length;
    const nextTab = TABS[nextIndex].id;
    setActiveTab(nextTab);
    requestAnimationFrame(() => document.getElementById(`application-tab-${nextTab}`)?.focus());
  };

  return (
    <div className={styles.page}>
      <nav className={styles.crumbs} aria-label="Breadcrumb">
        <a href="/estate" className={styles.crumb}>Estate</a>
        <span aria-hidden="true">›</span>
        <span className={styles.crumbCurrent}>
          <DomainBadge namespace="ENTERPRISE" />
          <span className="sg-mono">{data.application.name}</span>
        </span>
      </nav>

      <header className={styles.head}>
        <div className={styles.headMain}>
          <h1 className={`${styles.title} sg-mono`}>{data.application.name}</h1>
          <DescriptionEditor
            kind="application"
            entityId={id}
            description={data.application.summary}
            queryKey={["application", id]}
          />
        </div>
        <ApplicationViewSwitch applicationId={id} active="hierarchy" />
      </header>

      <div className={styles.applicationTabs} role="tablist" aria-label="Application detail sections">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            type="button"
            role="tab"
            id={`application-tab-${tab.id}`}
            aria-controls={`application-panel-${tab.id}`}
            aria-selected={activeTab === tab.id}
            tabIndex={activeTab === tab.id ? 0 : -1}
            className={activeTab === tab.id ? styles.activeTab : undefined}
            onClick={() => setActiveTab(tab.id)}
            onKeyDown={(event) => {
              if (event.key === "ArrowLeft") {
                event.preventDefault();
                moveTabFocus(tab.id, -1);
              } else if (event.key === "ArrowRight") {
                event.preventDefault();
                moveTabFocus(tab.id, 1);
              } else if (event.key === "Home") {
                event.preventDefault();
                moveTabFocus(tab.id, "first");
              } else if (event.key === "End") {
                event.preventDefault();
                moveTabFocus(tab.id, "last");
              }
            }}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <div
        id={`application-panel-${activeTab}`}
        role="tabpanel"
        aria-labelledby={`application-tab-${activeTab}`}
        className={styles.tabPanel}
      >
        {activeTab === "overview" ? (
          <div className={styles.overviewLayout}>
            <div className={styles.graphIntelligenceSection}>
              <GraphIntelligenceSummary
                entityId={id}
                intelligence={data.graph_intelligence}
                graphHref={`/applications/${id}/graph`}
                similarityAvailable
              />
              <CriticalEdges entityId={id} />
            </div>
            <section className={styles.overviewSection} aria-labelledby="application-overview-heading">
              <h2 id="application-overview-heading">Application overview</h2>
              <dl className={styles.overviewFacts}>
                <div><dt>Repositories</dt><dd className="sg-mono">{data.repositories.length}</dd></div>
                <div><dt>Services</dt><dd className="sg-mono">{data.services.length}</dd></div>
                <div><dt>Technologies</dt><dd className="sg-mono">{data.technologies.length}</dd></div>
                <div><dt>Deployments</dt><dd className="sg-mono">{data.deployments.length}</dd></div>
                <div><dt>Recommendations</dt><dd className="sg-mono">{data.recommendations.length}</dd></div>
              </dl>
            </section>

            <section className={styles.overviewSection} aria-labelledby="business-context-heading">
              <h2 id="business-context-heading">Business context</h2>
              {data.business_context.length > 0 ? (
                <ul className={styles.entityList}>
                  {data.business_context.map((entity) => <li key={entity.id}>{entity.name}</li>)}
                </ul>
              ) : <EmptyPanel>No business context is linked yet.</EmptyPanel>}
            </section>

            <section className={styles.overviewSection} aria-labelledby="repositories-heading">
              <h2 id="repositories-heading">Repositories</h2>
              {data.repositories.length > 0 ? (
                <ul className={`${styles.entityList} sg-mono`}>
                  {data.repositories.map((repository) => (
                    <li key={repository.id}>
                      <Link className={styles.entityLink} href={`/repositories/${repository.id}`}>
                        {repository.name}
                      </Link>
                    </li>
                  ))}
                </ul>
              ) : <EmptyPanel>No repositories are linked yet.</EmptyPanel>}
            </section>

            <section id="services" className={styles.overviewSection} aria-labelledby="services-heading">
              <h2 id="services-heading">Services</h2>
              {data.services.length > 0 ? (
                <ul className={`${styles.entityList} sg-mono`}>
                  {data.services.map((service) => <li key={service.id}>{service.name}</li>)}
                </ul>
              ) : <EmptyPanel>No code or infrastructure-defined services are linked yet.</EmptyPanel>}
            </section>

            <section className={styles.overviewSection} aria-labelledby="deployments-heading">
              <h2 id="deployments-heading">Deployments</h2>
              {data.deployments.length > 0 ? (
                <ul className={`${styles.entityList} sg-mono`}>
                  {data.deployments.map((deployment) => <li key={deployment.id}>{deployment.name}</li>)}
                </ul>
              ) : <EmptyPanel>No deployments are linked yet.</EmptyPanel>}
            </section>
          </div>
        ) : null}

        {activeTab === "technology" ? (
          <TechnologyWorkspace
            applicationId={id}
            applicationName={data.application.name}
            groups={data.technology_groups}
            hierarchies={dependencyHierarchies}
          />
        ) : null}

        {activeTab === "assessments" ? (
          <section className={styles.focusSection} aria-labelledby="assessments-heading">
            <div className={styles.sectionHeading}>
              <h2 id="assessments-heading">Assessments</h2>
              <span>{data.assessments.length}</span>
            </div>
            {data.assessments.length > 0 ? (
              <ul className={styles.assessments}>
                {data.assessments.map((assessment) => (
                  <li key={assessment.id} className={styles.assessment}>
                    <span className={styles.dimension}>{assessment.dimension}</span>
                    <span className={`${styles.value} sg-mono`}>{assessment.categorical_value ?? assessment.score}</span>
                    <ConfidenceChip label={assessment.confidence_label} value={assessment.confidence} />
                  </li>
                ))}
              </ul>
            ) : <EmptyPanel>No assessments are available yet.</EmptyPanel>}
          </section>
        ) : null}

        {activeTab === "recommendations" ? (
          <div className={styles.recommendationWorkspace}>
            <DeterministicInsightsPanel
              scopeEntityId={id}
              title="Current application findings"
              description="Findings derived from the repositories, dependencies, runtime observations, and deployments currently linked to this application."
              limit={12}
            />
            <section className={styles.focusSection} aria-labelledby="recommendations-heading">
            <div className={styles.sectionHeading}>
              <div>
                <h2 id="recommendations-heading">Investigative recommendations</h2>
                <p>AI-assisted or analyst-reviewed actions that build on the deterministic evidence above.</p>
              </div>
              <span>{data.recommendations.length}</span>
            </div>
            {data.recommendations.length > 0 ? (
              <div className={styles.recommendations}>
                {data.recommendations.map((recommendation) => (
                  <article key={recommendation.id} className={styles.recommendation}>
                    <div className={styles.recommendationHead}>
                      <span className={`${styles.action} sg-mono`}>{recommendation.action}</span>
                      <ConfidenceChip label={recommendation.confidence_label} value={recommendation.confidence} />
                    </div>
                    <h3>{recommendation.title}</h3>
                    <p>{recommendation.rationale}</p>
                  </article>
                ))}
              </div>
            ) : <EmptyPanel>No recommendations are available yet.</EmptyPanel>}
            </section>
          </div>
        ) : null}
      </div>
    </div>
  );
}
