"use client";

import { useDeferredValue, useMemo, useState } from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import type { TechnologyEstateHierarchyNode } from "@stackgraph/shared";
import { ConfidenceChip, CitationChip, DomainBadge, Skeleton } from "@stackgraph/design-system";
import { useGraphNeighborhood, useTechnologyEstateHierarchy } from "@/lib/queries";
import { useEvidenceStore } from "@/lib/evidenceStore";
import styles from "./technologies.module.css";

const ROOT = "__root__";
const compactNumber = new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 });
const GraphCanvas = dynamic(() => import("@stackgraph/graph-ui").then((module) => module.GraphCanvas), {
  ssr: false,
  loading: () => <Skeleton height="100%" />,
});

function classificationLabel(value: string) {
  if (value === "CATALOG_MATCH") return "Catalog matched";
  if (value === "CURATED") return "Curated technology";
  return "OSS metadata";
}

function TechnologyBranch({
  node,
  childrenByParent,
  selectedId,
  onSelect,
}: {
  node: TechnologyEstateHierarchyNode;
  childrenByParent: Map<string, TechnologyEstateHierarchyNode[]>;
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  const children = childrenByParent.get(node.technology.id) ?? [];
  const selected = selectedId === node.technology.id;
  const label = (
    <>
      <span className={styles.branchIdentity}>
        <span className={`${styles.branchName} sg-mono`}>{node.technology.name}</span>
        {node.catalog_profile?.domain ? (
          <span className={styles.catalogTag}>{node.catalog_profile.domain.name}</span>
        ) : (
          <span className={styles.kind}>{node.technology.kind}</span>
        )}
      </span>
      <span className={styles.branchMeta}>
        {node.parent_technology_id == null ? (
          <span className={node.direct ? styles.declared : styles.observed}>
            {node.direct ? "Declared" : "Observed"}
          </span>
        ) : null}
        <span>{node.dependent_applications.length} apps</span>
      </span>
    </>
  );

  return (
    <li className={styles.branch}>
      {children.length > 0 ? (
        <details className={styles.branchDetails}>
          <summary
            className={`${styles.branchRow} ${selected ? styles.selected : ""}`}
            onClick={() => onSelect(node.technology.id)}
          >
            {label}
          </summary>
          <ul className={styles.children}>
            {children.map((child) => (
              <TechnologyBranch
                key={child.technology.id}
                node={child}
                childrenByParent={childrenByParent}
                selectedId={selectedId}
                onSelect={onSelect}
              />
            ))}
          </ul>
        </details>
      ) : (
        <button
          type="button"
          className={`${styles.branchRow} ${styles.leafRow} ${selected ? styles.selected : ""}`}
          onClick={() => onSelect(node.technology.id)}
        >
          {label}
        </button>
      )}
    </li>
  );
}

function TechnologyGraphWorkspace({
  center,
  nodesById,
}: {
  center: TechnologyEstateHierarchyNode;
  nodesById: Map<string, TechnologyEstateHierarchyNode>;
}) {
  const { data, isLoading, isError } = useGraphNeighborhood(center.technology.id, 1);
  const openEvidence = useEvidenceStore((state) => state.open);
  const [selectedNodeId, setSelectedNodeId] = useState(center.technology.id);
  const selectedNode = data?.nodes.find((node) => node.id === selectedNodeId)
    ?? data?.nodes.find((node) => node.id === center.technology.id)
    ?? null;
  const selectedTechnology = selectedNode ? nodesById.get(selectedNode.id) ?? null : null;
  const connectedEdges = selectedNode && data
    ? data.edges.filter((edge) => edge.source === selectedNode.id || edge.target === selectedNode.id)
    : [];
  const entityHref = selectedNode
    ? selectedTechnology
      ? `/technologies/${selectedNode.id}`
      : selectedNode.namespace === "ENTERPRISE" && selectedNode.type === "Application"
        ? `/applications/${selectedNode.id}`
        : null
    : null;

  return (
    <div className={styles.workspace}>
      <section className={styles.graphPanel} aria-label={`${center.technology.name} dependency graph`}>
        <header className={styles.panelHead}>
          <div>
            <h2>Dependency graph</h2>
            <p className="sg-mono">{center.technology.name}</p>
          </div>
          {data ? <span>{data.nodes.length} nodes · {data.edges.length} edges</span> : null}
        </header>
        <div className={styles.graphCanvas}>
          {isLoading ? (
            <Skeleton height="100%" />
          ) : isError || !data ? (
            <div className={styles.graphEmpty}>
              <h3>Graph unavailable</h3>
              <p>The hierarchy remains available while this neighborhood is retried.</p>
            </div>
          ) : (
            <GraphCanvas graph={data} onSelect={(nodeId) => setSelectedNodeId(nodeId ?? center.technology.id)} />
          )}
        </div>
      </section>

      <aside className={styles.inspector} aria-label="Graph node inspector">
        {selectedNode ? (
          <>
            <header className={styles.inspectorHead}>
              <DomainBadge namespace={selectedNode.namespace} />
              <span className={styles.kind}>{selectedNode.type}</span>
            </header>
            <h2 className={`${styles.inspectorName} sg-mono`}>{selectedNode.label}</h2>
            {entityHref ? (
              <Link href={entityHref} className={styles.detailLink}>
                Open detail <span aria-hidden="true">→</span>
              </Link>
            ) : null}

            {selectedTechnology ? (
              <section className={styles.applicationSection}>
                <div className={styles.applicationHead}>
                  <h3>Dependent applications</h3>
                  <span>{selectedTechnology.dependent_applications.length}</span>
                </div>
                {selectedTechnology.dependent_applications.length > 0 ? (
                  <ul className={styles.applicationList}>
                    {selectedTechnology.dependent_applications.map((application) => (
                      <li key={application.id}>
                        <Link href={`/applications/${application.id}`} className={styles.applicationLink}>
                          <span className="sg-mono">{application.name}</span>
                          <span aria-hidden="true">→</span>
                        </Link>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className={styles.noApplications}>No connected applications.</p>
                )}
              </section>
            ) : null}

            <section className={styles.connectionSection}>
              <div className={styles.applicationHead}>
                <h3>Connections</h3>
                <span>{connectedEdges.length}</span>
              </div>
              {connectedEdges.length > 0 ? (
                <ul className={styles.connectionList}>
                  {connectedEdges.map((edge) => {
                    const otherId = edge.source === selectedNode.id ? edge.target : edge.source;
                    const other = data?.nodes.find((node) => node.id === otherId);
                    const factId = edge.citation_fact_ids[0];
                    return (
                      <li key={edge.id} className={styles.connectionItem}>
                        <span className={`${styles.connectionPredicate} sg-mono`}>{edge.predicate}</span>
                        <span>{other?.label ?? "Unknown entity"}</span>
                        {factId ? (
                          <CitationChip
                            label="evidence"
                            onOpen={() => openEvidence(factId, `${edge.predicate} evidence`)}
                          />
                        ) : null}
                      </li>
                    );
                  })}
                </ul>
              ) : (
                <p className={styles.noApplications}>No visible connections.</p>
              )}
            </section>
          </>
        ) : (
          <div className={styles.inspectorEmpty}>
            <h2>Select a graph node</h2>
            <p>Its connections, dependent applications, and evidence will appear here.</p>
          </div>
        )}
      </aside>
    </div>
  );
}

export function TechnologyHierarchyView() {
  const { data, isLoading } = useTechnologyEstateHierarchy();
  const openEvidence = useEvidenceStore((state) => state.open);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [view, setView] = useState<"hierarchy" | "graph">("hierarchy");
  const [search, setSearch] = useState("");
  const deferredSearch = useDeferredValue(search.trim().toLowerCase());

  const { childrenByParent, nodesById } = useMemo(() => {
    const children = new Map<string, TechnologyEstateHierarchyNode[]>();
    const nodes = new Map<string, TechnologyEstateHierarchyNode>();
    for (const node of data?.nodes ?? []) {
      nodes.set(node.technology.id, node);
      const parent = node.parent_technology_id ?? ROOT;
      children.set(parent, [...(children.get(parent) ?? []), node]);
    }
    return { childrenByParent: children, nodesById: nodes };
  }, [data?.nodes]);

  const searchResults = useMemo(() => {
    if (!deferredSearch || !data) return [];
    return data.nodes.filter((node) => {
      const technology = node.technology;
      return technology.name.toLowerCase().includes(deferredSearch)
        || technology.kind.toLowerCase().includes(deferredSearch)
        || technology.canonical_key?.toLowerCase().includes(deferredSearch)
        || node.catalog_profile?.summary?.toLowerCase().includes(deferredSearch)
        || node.catalog_profile?.domain?.name.toLowerCase().includes(deferredSearch)
        || node.catalog_profile?.category?.name.toLowerCase().includes(deferredSearch)
        || node.catalog_profile?.functions.some((item) => item.name.toLowerCase().includes(deferredSearch));
    });
  }, [data, deferredSearch]);
  const selected = selectedId ? nodesById.get(selectedId) ?? null : null;
  const roots = childrenByParent.get(ROOT) ?? [];

  return (
    <div className={styles.page}>
      <header className={styles.head}>
        <div>
          <h1 className={styles.title}>Technologies</h1>
          <p className={styles.subtitle}>
            Manifest technologies and their resolved dependencies, limited to connected repositories.
          </p>
        </div>
        <div className={styles.headActions}>
          {data ? <span className={styles.total}>{data.nodes.length} observed</span> : null}
          <div className={styles.viewSwitch} role="group" aria-label="Technology view">
            <button
              type="button"
              className={view === "hierarchy" ? styles.activeView : ""}
              aria-pressed={view === "hierarchy"}
              onClick={() => setView("hierarchy")}
            >
              Hierarchy
            </button>
            <button
              type="button"
              className={view === "graph" ? styles.activeView : ""}
              aria-pressed={view === "graph"}
              disabled={!selected}
              title={selected ? `Explore ${selected.technology.name}` : "Select a technology first"}
              onClick={() => setView("graph")}
            >
              Graph
            </button>
          </div>
        </div>
      </header>

      <label className={styles.searchLabel}>
        <span>Find technology</span>
        <input
          type="search"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Search package, runtime, or canonical key"
          className={styles.search}
        />
      </label>

      {isLoading || !data ? (
        <div className={styles.skeleton}>
          <Skeleton height={52} />
          <Skeleton height={52} />
          <Skeleton height={240} />
        </div>
      ) : data.nodes.length === 0 ? (
        <div className={styles.empty}>
          <h2>No technologies have been observed yet.</h2>
          <p>Connect and scan a Git repository to build the tenant-scoped technology hierarchy.</p>
        </div>
      ) : view === "graph" && selected ? (
        <TechnologyGraphWorkspace key={selected.technology.id} center={selected} nodesById={nodesById} />
      ) : (
        <div className={styles.workspace}>
          <section className={styles.treePanel} aria-label="Technology dependency hierarchy">
            <header className={styles.panelHead}>
              <div>
                <h2>Dependency hierarchy</h2>
                <p>{deferredSearch ? `${searchResults.length} matches` : `${roots.length} root technologies`}</p>
              </div>
              <span>Collapsed by default</span>
            </header>
            {deferredSearch ? (
              searchResults.length > 0 ? (
                <ul className={styles.searchResults}>
                  {searchResults.map((node) => (
                    <li key={node.technology.id}>
                      <button
                        type="button"
                        className={`${styles.searchResult} ${selectedId === node.technology.id ? styles.selected : ""}`}
                        onClick={() => setSelectedId(node.technology.id)}
                      >
                        <span className="sg-mono">{node.technology.name}</span>
                        <span>{node.depth === 1 ? "Root" : `Depth ${node.depth}`} · {node.dependent_applications.length} apps</span>
                      </button>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className={styles.noMatches}>No technologies match “{search}”.</p>
              )
            ) : (
              <ul className={styles.roots}>
                {roots.map((node) => (
                  <TechnologyBranch
                    key={node.technology.id}
                    node={node}
                    childrenByParent={childrenByParent}
                    selectedId={selectedId}
                    onSelect={setSelectedId}
                  />
                ))}
              </ul>
            )}
            {data.truncated ? (
              <p className={styles.truncated}>Showing the first 1,000 observed technologies.</p>
            ) : null}
          </section>

          <aside className={styles.inspector} aria-label="Selected technology inspector">
            {selected ? (
              <>
                <header className={styles.inspectorHead}>
                  <span className={styles.kind}>{selected.technology.kind}</span>
                  <ConfidenceChip label={selected.confidence_label} value={selected.confidence} />
                </header>
                <h2 className={`${styles.inspectorName} sg-mono`}>{selected.technology.name}</h2>
                {selected.catalog_profile ? (
                  <section className={styles.catalogProfile} aria-label="OSS catalog profile">
                    <div className={styles.catalogProfileHead}>
                      <span>OSS catalog</span>
                      <span>{classificationLabel(selected.catalog_profile.classification)}</span>
                    </div>
                    {selected.catalog_profile.summary ? (
                      <p className={styles.summary}>{selected.catalog_profile.summary}</p>
                    ) : null}
                    <div className={styles.taxonomyList}>
                      {selected.catalog_profile.domain ? (
                        <span>{selected.catalog_profile.domain.name}</span>
                      ) : null}
                      {selected.catalog_profile.category ? (
                        <span>{selected.catalog_profile.category.name}</span>
                      ) : null}
                      {selected.catalog_profile.functions.map((item) => (
                        <span key={item.key}>{item.name}</span>
                      ))}
                    </div>
                    <dl className={styles.catalogStats}>
                      {selected.catalog_profile.latest_version ? (
                        <div><dt>Catalog version</dt><dd>{selected.catalog_profile.latest_version}</dd></div>
                      ) : null}
                      {selected.catalog_profile.license ? (
                        <div><dt>License</dt><dd>{selected.catalog_profile.license}</dd></div>
                      ) : null}
                      {selected.catalog_profile.weekly_downloads != null ? (
                        <div><dt>Weekly downloads</dt><dd>{compactNumber.format(selected.catalog_profile.weekly_downloads)}</dd></div>
                      ) : null}
                      {selected.catalog_profile.dependents != null ? (
                        <div><dt>Dependents</dt><dd>{compactNumber.format(selected.catalog_profile.dependents)}</dd></div>
                      ) : null}
                    </dl>
                    <div className={styles.catalogLinks}>
                      {selected.catalog_profile.homepage ? (
                        <a href={selected.catalog_profile.homepage} target="_blank" rel="noreferrer">Homepage ↗</a>
                      ) : null}
                      {selected.catalog_profile.repository_url ? (
                        <a href={selected.catalog_profile.repository_url} target="_blank" rel="noreferrer">Source ↗</a>
                      ) : null}
                      {selected.catalog_profile.package_url ? (
                        <a href={selected.catalog_profile.package_url} target="_blank" rel="noreferrer">Registry ↗</a>
                      ) : null}
                    </div>
                  </section>
                ) : selected.technology.summary ? (
                  <p className={styles.summary}>{selected.technology.summary}</p>
                ) : null}
                {selected.technology.canonical_key ? (
                  <p className={`${styles.canonicalKey} sg-mono`}>{selected.technology.canonical_key}</p>
                ) : null}
                <Link href={`/technologies/${selected.technology.id}`} className={styles.detailLink}>
                  Open technology detail <span aria-hidden="true">→</span>
                </Link>
                <button type="button" className={styles.graphLink} onClick={() => setView("graph")}>
                  Explore dependency graph <span aria-hidden="true">→</span>
                </button>

                <section className={styles.applicationSection}>
                  <div className={styles.applicationHead}>
                    <h3>Dependent applications</h3>
                    <span>{selected.dependent_applications.length}</span>
                  </div>
                  {selected.dependent_applications.length > 0 ? (
                    <ul className={styles.applicationList}>
                      {selected.dependent_applications.map((application) => (
                        <li key={application.id}>
                          <Link href={`/applications/${application.id}`} className={styles.applicationLink}>
                            <span className="sg-mono">{application.name}</span>
                            <span aria-hidden="true">→</span>
                          </Link>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className={styles.noApplications}>
                      No connected application currently resolves through this technology.
                    </p>
                  )}
                </section>

                <div className={styles.evidence}>
                  {selected.catalog_profile?.citations.map((citation) => (
                    <CitationChip
                      key={`catalog-${citation.fact_id}`}
                      label={citation.label}
                      onOpen={() => openEvidence(citation.fact_id, citation.label)}
                    />
                  ))}
                  {selected.citations.map((citation) => (
                    <CitationChip
                      key={citation.fact_id}
                      label={citation.label}
                      onOpen={() => openEvidence(citation.fact_id, citation.label)}
                    />
                  ))}
                </div>
              </>
            ) : (
              <div className={styles.inspectorEmpty}>
                <span aria-hidden="true">◇</span>
                <h2>Select a technology</h2>
                <p>Its dependent applications and evidence will appear here.</p>
              </div>
            )}
          </aside>
        </div>
      )}
    </div>
  );
}
