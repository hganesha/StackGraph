"use client";

import { useMemo } from "react";
import Link from "next/link";
import type {
  ApplicationComponentDependencyHierarchy,
  ApplicationRepositoryDependencyHierarchy,
  ApplicationTechnologyGroup,
} from "@stackgraph/shared";
import { ConfidenceChip, CitationChip } from "@stackgraph/design-system";
import { useEvidenceStore } from "@/lib/evidenceStore";
import styles from "./application.module.css";

const ROOT_DEPENDENCY = "__root__";

function DependencyTree({
  component,
  classifications,
}: {
  component: ApplicationComponentDependencyHierarchy;
  classifications: Map<string, string[]>;
}) {
  const openEvidence = useEvidenceStore((state) => state.open);
  const children = useMemo(() => {
    const grouped = new Map<string, typeof component.dependencies>();
    for (const dependency of component.dependencies) {
      const parent = dependency.parent_technology_id ?? ROOT_DEPENDENCY;
      grouped.set(parent, [...(grouped.get(parent) ?? []), dependency]);
    }
    return grouped;
  }, [component.dependencies]);

  const renderLevel = (parentId: string, depth: number) => {
    const level = children.get(parentId) ?? [];
    if (level.length === 0) return null;
    return (
      <ul className={depth === 0 ? styles.dependencyRoots : styles.dependencyChildren}>
        {level.map((dependency) => {
          const labels = classifications.get(dependency.technology.id) ?? [];
          const citation = dependency.citations[0];
          return (
            <li key={dependency.technology.id} className={styles.dependencyNode}>
              <div className={styles.dependencyRow}>
                <div className={styles.dependencyMain}>
                  <div className={styles.dependencyIdentity}>
                    <Link
                      href={`/technologies/${dependency.technology.id}`}
                      className={`${styles.dependencyName} sg-mono`}
                    >
                      {dependency.technology.name}
                    </Link>
                    <span className={dependency.direct ? styles.directBadge : styles.transitiveBadge}>
                      {dependency.direct ? "Direct" : "Transitive"}
                    </span>
                  </div>
                  <div className={styles.dependencyMeta}>
                    {dependency.scope ? <span>{dependency.scope}</span> : null}
                    {dependency.requirement ? (
                      <span className="sg-mono">requires {dependency.requirement}</span>
                    ) : null}
                    {dependency.dependency_relation ? <span>{dependency.dependency_relation}</span> : null}
                    {labels.map((label) => (
                      <span key={label} className={styles.architectureLabel}>{label}</span>
                    ))}
                  </div>
                </div>
                <div className={styles.dependencyEvidence}>
                  <ConfidenceChip label={dependency.confidence_label} value={dependency.confidence} />
                  {citation ? (
                    <CitationChip
                      label={citation.label}
                      onOpen={() => openEvidence(citation.fact_id, citation.label)}
                    />
                  ) : null}
                </div>
              </div>
              {renderLevel(dependency.technology.id, depth + 1)}
            </li>
          );
        })}
      </ul>
    );
  };

  return (
    <details className={styles.componentHierarchy}>
      <summary className={styles.componentSummary}>
        <span className="sg-mono">{component.component_path}</span>
        <span>{component.dependencies.length} dependencies</span>
      </summary>
      <div className={styles.dependencyTree}>
        {renderLevel(ROOT_DEPENDENCY, 0)}
        {component.truncated ? (
          <p className={styles.truncatedNotice}>Showing the first 250 dependencies for this component.</p>
        ) : null}
      </div>
    </details>
  );
}

export function ApplicationDependencyHierarchy({
  hierarchies,
  technologyGroups,
}: {
  hierarchies: ApplicationRepositoryDependencyHierarchy[];
  technologyGroups: ApplicationTechnologyGroup[];
}) {
  const classifications = useMemo(() => {
    const result = new Map<string, string[]>();
    for (const group of technologyGroups) {
      if (group.domain.key === "unclassified") continue;
      for (const item of group.functions) {
        for (const usage of item.technologies) {
          const label = `${group.domain.name} · ${item.function.name}`;
          const existing = result.get(usage.technology.id) ?? [];
          if (!existing.includes(label)) result.set(usage.technology.id, [...existing, label]);
        }
      }
    }
    return result;
  }, [technologyGroups]);

  return (
    <section className={styles.dependencySection} aria-label="Dependency hierarchy">
      <div className={styles.subsectionHeading}>
        <h2 className={styles.subsectionTitle}>Dependency hierarchy</h2>
        <p>Manifest roots expand into their resolved transitive dependencies.</p>
      </div>
      {hierarchies.length > 0 ? (
        <div className={styles.dependencyHierarchies}>
          {hierarchies.map((hierarchy) => (
            <article key={hierarchy.repository.id} className={styles.repositoryHierarchy}>
              <header className={styles.repositoryHead}>
                <div>
                  <span className={styles.repositoryLabel}>Repository</span>
                  <h3 className={`${styles.repositoryName} sg-mono`}>{hierarchy.repository.name}</h3>
                </div>
                <span className={styles.domainCount}>{hierarchy.components.length} components</span>
              </header>
              <div className={styles.componentList}>
                {hierarchy.components.map((component) => (
                  <DependencyTree
                    key={component.component_path}
                    component={component}
                    classifications={classifications}
                  />
                ))}
              </div>
            </article>
          ))}
        </div>
      ) : (
        <p className={styles.emptyTechnology}>
          No manifest-declared dependency roots have been linked to this application&apos;s repositories yet.
        </p>
      )}
    </section>
  );
}
