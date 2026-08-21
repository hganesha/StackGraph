"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import {
  IconChevronDown,
  IconChevronRight,
  IconExternalLink,
  IconSearch,
  IconX,
} from "@tabler/icons-react";
import type {
  ApplicationRepositoryDependencyHierarchy,
  ApplicationTechnologyGroup,
  ApplicationTechnologyUsage,
  Citation,
  TaxonomySummary,
} from "@stackgraph/shared";
import { ConfidenceChip } from "@stackgraph/design-system";
import { useEvidenceStore } from "@/lib/evidenceStore";
import { ApplicationDependencyHierarchy } from "./DependencyHierarchy";
import styles from "./application.module.css";

type ViewMode = "architecture" | "all";

interface TechnologyItem {
  usage: ApplicationTechnologyUsage;
  domain: TaxonomySummary;
  function: TaxonomySummary;
}

function uniqueCitations(citations: Citation[]): Citation[] {
  const labels = new Set<string>();
  return citations.filter((citation) => {
    const key = citation.label.trim().toLocaleLowerCase();
    if (labels.has(key)) return false;
    labels.add(key);
    return true;
  });
}

function sourceCount(citations: Citation[]): string {
  const count = uniqueCitations(citations).length;
  return `${count} ${count === 1 ? "source" : "sources"}`;
}

function classificationLabel(classification: ApplicationTechnologyUsage["classification"]): string {
  if (classification === "CURATED") return "Curated catalog";
  if (classification === "CATALOG_MATCH") return "Exact catalog match";
  return "Needs classification";
}

function matchesQuery(item: TechnologyItem, query: string): boolean {
  if (!query) return true;
  const searchable = [
    item.usage.technology.name,
    item.usage.technology.summary,
    item.usage.category?.name,
    item.domain.name,
    item.function.name,
  ]
    .filter(Boolean)
    .join(" ")
    .toLocaleLowerCase();
  return searchable.includes(query);
}

function TechnologyTable({
  items,
  selectedId,
  onSelect,
}: {
  items: TechnologyItem[];
  selectedId: string | null;
  onSelect: (item: TechnologyItem) => void;
}) {
  if (items.length === 0) {
    return <p className={styles.noMatches}>No technologies match this filter.</p>;
  }

  return (
    <div className={styles.tableScroll}>
      <table className={styles.technologyTable}>
        <thead>
          <tr>
            <th scope="col">Technology</th>
            <th scope="col">Role</th>
            <th scope="col">Confidence</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => {
            const { usage } = item;
            const selected = usage.technology.id === selectedId;
            return (
              <tr key={`${item.domain.key}:${item.function.key}:${usage.technology.id}`} className={selected ? styles.selectedRow : undefined}>
                <td>
                  <button
                    type="button"
                    className={`${styles.technologySelect} sg-mono`}
                    aria-pressed={selected}
                    onClick={() => onSelect(item)}
                  >
                    {usage.technology.name}
                  </button>
                </td>
                <td>{usage.category?.name ?? item.function.name}</td>
                <td>
                  {usage.classification === "UNCLASSIFIED" ? (
                    <span className={styles.quietValue}>Not assessed</span>
                  ) : (
                    <ConfidenceChip label={usage.confidence_label} value={usage.confidence} />
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function TechnologyInspector({
  item,
  onClose,
}: {
  item: TechnologyItem | null;
  onClose: () => void;
}) {
  const openEvidence = useEvidenceStore((state) => state.open);

  if (!item) {
    return (
      <aside className={`${styles.technologyInspector} ${styles.inspectorEmpty}`} aria-label="Technology inspector">
        <p>Select a technology to inspect its role, classification, and evidence.</p>
      </aside>
    );
  }

  const citations = uniqueCitations(item.usage.citations);

  return (
    <aside className={styles.technologyInspector} aria-label={`Inspecting ${item.usage.technology.name}`}>
      <header className={styles.inspectorHead}>
        <h3 className={`${styles.inspectorTitle} sg-mono`}>{item.usage.technology.name}</h3>
        <button type="button" className={styles.iconButton} aria-label="Close technology inspector" onClick={onClose}>
          <IconX size={18} stroke={1.75} aria-hidden="true" />
        </button>
      </header>

      {item.usage.technology.summary ? (
        <p className={styles.inspectorSummary}>{item.usage.technology.summary}</p>
      ) : null}

      <dl className={styles.inspectorFacts}>
        <dt>Role</dt>
        <dd>{item.usage.category?.name ?? item.function.name}</dd>
        <dt>Architecture</dt>
        <dd>{item.domain.name}</dd>
        <dt>Classification</dt>
        <dd>{classificationLabel(item.usage.classification)}</dd>
        {item.usage.classification !== "UNCLASSIFIED" ? (
          <>
            <dt>Confidence</dt>
            <dd>
              <ConfidenceChip label={item.usage.confidence_label} value={item.usage.confidence} />
            </dd>
          </>
        ) : null}
      </dl>

      <section className={styles.inspectorEvidence} aria-labelledby="technology-evidence-heading">
        <div className={styles.inspectorSectionHead}>
          <h4 id="technology-evidence-heading">Evidence</h4>
          <span>{sourceCount(item.usage.citations)}</span>
        </div>
        {citations.length > 0 ? (
          <ul className={styles.evidenceList}>
            {citations.map((citation) => (
              <li key={citation.fact_id}>
                <button
                  type="button"
                  className={styles.evidenceLink}
                  onClick={() => openEvidence(citation.fact_id, citation.label)}
                >
                  <span>{citation.label}</span>
                  <IconChevronRight size={16} stroke={1.75} aria-hidden="true" />
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <p className={styles.noEvidence}>No evidence source is linked yet.</p>
        )}
      </section>

      <Link href={`/technologies/${item.usage.technology.id}`} className={styles.openTechnology}>
        <IconExternalLink size={16} stroke={1.75} aria-hidden="true" />
        Open technology
      </Link>
    </aside>
  );
}

export function TechnologyWorkspace({
  applicationId,
  applicationName,
  groups,
  hierarchies,
}: {
  applicationId: string;
  applicationName: string;
  groups: ApplicationTechnologyGroup[];
  hierarchies: ApplicationRepositoryDependencyHierarchy[];
}) {
  const [query, setQuery] = useState("");
  const [view, setView] = useState<ViewMode>("architecture");

  const items = useMemo<TechnologyItem[]>(
    () =>
      groups.flatMap((group) =>
        group.functions.flatMap((item) =>
          item.technologies.map((usage) => ({ usage, domain: group.domain, function: item.function })),
        ),
      ),
    [groups],
  );

  const uniqueItems = useMemo(() => {
    const byTechnology = new Map<string, TechnologyItem>();
    for (const item of items) {
      const current = byTechnology.get(item.usage.technology.id);
      if (!current || current.usage.classification === "UNCLASSIFIED") {
        byTechnology.set(item.usage.technology.id, item);
      }
    }
    return [...byTechnology.values()].sort((a, b) => a.usage.technology.name.localeCompare(b.usage.technology.name));
  }, [items]);

  const firstClassified = items.find((item) => item.usage.classification !== "UNCLASSIFIED") ?? items[0] ?? null;
  const [selectedId, setSelectedId] = useState<string | null>(firstClassified?.usage.technology.id ?? null);
  const selectedItem = uniqueItems.find((item) => item.usage.technology.id === selectedId) ?? null;

  const firstDomainKey = groups.find((group) => group.domain.key !== "unclassified")?.domain.key;
  const firstFunctionKey = groups
    .find((group) => group.domain.key === firstDomainKey)
    ?.functions[0]?.function.key;
  const [openDomains, setOpenDomains] = useState<Set<string>>(() => new Set(firstDomainKey ? [firstDomainKey] : []));
  const [openFunctions, setOpenFunctions] = useState<Set<string>>(
    () => new Set(firstDomainKey && firstFunctionKey ? [`${firstDomainKey}:${firstFunctionKey}`] : []),
  );

  const normalizedQuery = query.trim().toLocaleLowerCase();
  const filteredUniqueItems = uniqueItems.filter((item) => matchesQuery(item, normalizedQuery));
  const dependencyCount = hierarchies.reduce(
    (total, hierarchy) =>
      total + hierarchy.components.reduce((componentTotal, component) => componentTotal + component.dependencies.length, 0),
    0,
  );

  const selectItem = (item: TechnologyItem) => setSelectedId(item.usage.technology.id);
  const toggleSet = (setter: React.Dispatch<React.SetStateAction<Set<string>>>, key: string) => {
    setter((current) => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  return (
    <section className={styles.technologyWorkspace} aria-labelledby="technology-landscape-heading">
      <div className={styles.workspaceToolbar}>
        <div className={styles.workspaceHeading}>
          <h2 id="technology-landscape-heading">Technology landscape</h2>
          <span>{uniqueItems.length} linked</span>
        </div>
        <div className={styles.workspaceControls}>
          <label className={styles.searchField}>
            <IconSearch size={16} stroke={1.75} aria-hidden="true" />
            <span className={styles.visuallyHidden}>Filter technologies</span>
            <input
              type="search"
              value={query}
              placeholder="Filter technologies"
              onChange={(event) => setQuery(event.target.value)}
            />
          </label>
          <div className={styles.viewSwitch} role="group" aria-label="Technology view">
            <button type="button" className={view === "architecture" ? styles.activeView : undefined} onClick={() => setView("architecture")}>
              By architecture
            </button>
            <button type="button" className={view === "all" ? styles.activeView : undefined} onClick={() => setView("all")}>
              All technologies
            </button>
          </div>
        </div>
      </div>

      <div className={styles.technologyLayout}>
        <div className={styles.technologyContent}>
          <details className={styles.dependencyDisclosure}>
            <summary>
              <span className={styles.disclosureIdentity}>
                <IconChevronRight className={styles.disclosureChevron} size={18} stroke={1.75} aria-hidden="true" />
                <span>
                  <strong>Dependency hierarchy</strong>
                  <small className="sg-mono">{applicationName} / repository root</small>
                </span>
              </span>
              <span>{dependencyCount} {dependencyCount === 1 ? "dependency" : "dependencies"}</span>
            </summary>
            <div className={styles.dependencyBody}>
              <div className={styles.dependencyActions}>
                <p>Manifest roots expand into their resolved transitive dependencies.</p>
                <Link href={`/applications/${applicationId}/graph`}>Explore graph</Link>
              </div>
              <ApplicationDependencyHierarchy hierarchies={hierarchies} technologyGroups={groups} embedded />
            </div>
          </details>

          {view === "all" ? (
            <section className={styles.allTechnologies} aria-label="All technologies">
              <TechnologyTable items={filteredUniqueItems} selectedId={selectedId} onSelect={selectItem} />
            </section>
          ) : (
            <div className={styles.architectureGroups}>
              {groups.map((group) => {
                const groupItems = group.functions.flatMap((item) =>
                  item.technologies
                    .map((usage) => ({ usage, domain: group.domain, function: item.function }))
                    .filter((technology) => matchesQuery(technology, normalizedQuery)),
                );
                if (normalizedQuery && groupItems.length === 0) return null;
                const domainOpen = normalizedQuery.length > 0 || openDomains.has(group.domain.key);
                const domainTechnologyCount = new Set(group.functions.flatMap((item) => item.technologies.map((usage) => usage.technology.id))).size;
                return (
                  <section key={group.domain.key} className={styles.architectureGroup}>
                    <button
                      type="button"
                      className={styles.groupDisclosure}
                      aria-expanded={domainOpen}
                      onClick={() => toggleSet(setOpenDomains, group.domain.key)}
                    >
                      {domainOpen ? <IconChevronDown size={18} stroke={1.75} aria-hidden="true" /> : <IconChevronRight size={18} stroke={1.75} aria-hidden="true" />}
                      <strong>{group.domain.name}</strong>
                      <span>{domainTechnologyCount} {domainTechnologyCount === 1 ? "technology" : "technologies"}</span>
                    </button>
                    {domainOpen ? (
                      <div className={styles.functionGroups}>
                        {group.functions.map((functionGroup) => {
                          const functionItems = functionGroup.technologies
                            .map((usage) => ({ usage, domain: group.domain, function: functionGroup.function }))
                            .filter((technology) => matchesQuery(technology, normalizedQuery));
                          if (normalizedQuery && functionItems.length === 0) return null;
                          const functionKey = `${group.domain.key}:${functionGroup.function.key}`;
                          const functionOpen = normalizedQuery.length > 0 || openFunctions.has(functionKey);
                          return (
                            <section key={functionKey} className={styles.functionGroup}>
                              <button
                                type="button"
                                className={styles.functionDisclosure}
                                aria-expanded={functionOpen}
                                onClick={() => toggleSet(setOpenFunctions, functionKey)}
                              >
                                {functionOpen ? <IconChevronDown size={16} stroke={1.75} aria-hidden="true" /> : <IconChevronRight size={16} stroke={1.75} aria-hidden="true" />}
                                <span>
                                  <strong>{functionGroup.function.name}</strong>
                                  {functionOpen && functionGroup.function.summary ? <small>{functionGroup.function.summary}</small> : null}
                                </span>
                                <span>{functionGroup.technologies.length}</span>
                              </button>
                              {functionOpen ? (
                                <TechnologyTable items={functionItems} selectedId={selectedId} onSelect={selectItem} />
                              ) : null}
                            </section>
                          );
                        })}
                      </div>
                    ) : null}
                  </section>
                );
              })}
              {normalizedQuery && filteredUniqueItems.length === 0 ? (
                <p className={styles.noMatches}>No technologies match “{query.trim()}”.</p>
              ) : null}
            </div>
          )}
        </div>

        <TechnologyInspector item={selectedItem} onClose={() => setSelectedId(null)} />
      </div>
    </section>
  );
}
