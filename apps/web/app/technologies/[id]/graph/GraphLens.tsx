"use client";

import { useMemo, useState } from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { DomainBadge, ConfidenceChip, CitationChip, Skeleton, confidenceLabel } from "@stackgraph/design-system";
import { useGraphNeighborhood } from "@/lib/queries";
import { useEvidenceStore } from "@/lib/evidenceStore";
import { UncertainBridge } from "@/components/reviews/UncertainBridge";
import styles from "./graphlens.module.css";

// React Flow is browser-only — load the canvas without SSR.
const GraphCanvas = dynamic(() => import("@stackgraph/graph-ui").then((m) => m.GraphCanvas), {
  ssr: false,
  loading: () => <Skeleton height="100%" />,
});

export function GraphLens({
  centerId,
  centerName,
  collectionHref,
  collectionLabel,
  depth = 1,
}: {
  centerId: string;
  centerName: string;
  collectionHref: string;
  collectionLabel: string;
  depth?: number;
}) {
  const { data, isLoading } = useGraphNeighborhood(centerId, depth);
  const [selected, setSelected] = useState<string | null>(null);
  const openEvidence = useEvidenceStore((s) => s.open);
  const detailHref = `${collectionHref}/${centerId}`;

  const selectedNode = useMemo(() => data?.nodes.find((n) => n.id === selected) ?? null, [data, selected]);
  const connectedEdges = useMemo(
    () => (data && selected ? data.edges.filter((e) => e.source === selected || e.target === selected) : []),
    [data, selected],
  );

  return (
    <div className={styles.lens}>
      <header className={styles.head}>
        <nav className={styles.crumbs} aria-label="Breadcrumb">
          <Link href={collectionHref} className={styles.crumb}>
            {collectionLabel}
          </Link>
          <span aria-hidden="true">›</span>
          <Link href={detailHref} className={styles.crumb}>
            <span className="sg-mono">{centerName}</span>
          </Link>
          <span aria-hidden="true">›</span>
          <span className={styles.lensTag}>Graph lens</span>
        </nav>
        <Link href={detailHref} className={styles.close} aria-label="Exit graph lens">
          ✕ Exit
        </Link>
      </header>

      <div className={styles.stage}>
        <div className={styles.canvas}>
          {isLoading || !data ? (
            <Skeleton height="100%" />
          ) : (
            <GraphCanvas graph={data} onSelect={setSelected} />
          )}
        </div>

        {selectedNode ? (
          <aside className={styles.inspector} aria-label="Selected node">
            <div className={styles.inspectorHead}>
              <DomainBadge namespace={selectedNode.namespace} />
              <span className={styles.inspectorType}>{selectedNode.type}</span>
            </div>
            <h2 className={`${styles.inspectorLabel} sg-mono`}>{selectedNode.label}</h2>
            {selectedNode.confidence != null ? (
              <ConfidenceChip label={confidenceLabel(selectedNode.confidence)} value={selectedNode.confidence} />
            ) : null}

            <h3 className={styles.inspectorH3}>Connections</h3>
            <ul className={styles.edgeList}>
              {connectedEdges.map((e) => {
                const other = data?.nodes.find((n) => n.id === (e.source === selected ? e.target : e.source));
                const factId = e.citation_fact_ids[0];
                return (
                  <li key={e.id} className={styles.edgeItem}>
                    <span className={`${styles.predicate} sg-mono`}>{e.predicate}</span>
                    <span className={styles.other}>{other?.label}</span>
                    {factId ? (
                      <CitationChip label="evidence" onOpen={() => openEvidence(factId, `${e.predicate} evidence`)} />
                    ) : null}
                  </li>
                );
              })}
            </ul>

            {connectedEdges
              .filter((e) => e.review_state === "POSSIBLE")
              .map((e) => {
                const src = data?.nodes.find((n) => n.id === e.source);
                const tgt = data?.nodes.find((n) => n.id === e.target);
                return (
                  <div key={`review-${e.id}`} className={styles.bridgeSlot}>
                    <h3 className={styles.inspectorH3}>Uncertain bridge</h3>
                    <UncertainBridge
                      assertionId={e.id}
                      sourceLabel={src?.label ?? "?"}
                      targetLabel={tgt?.label ?? "?"}
                      confidence={e.confidence}
                    />
                  </div>
                );
              })}
          </aside>
        ) : (
          <aside className={styles.inspectorEmpty}>
            <p>Select a node to inspect its connections and evidence.</p>
          </aside>
        )}
      </div>
    </div>
  );
}
