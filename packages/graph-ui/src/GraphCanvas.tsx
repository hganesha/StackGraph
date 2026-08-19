"use client";

import { useMemo, useState } from "react";
import {
  ReactFlow,
  ReactFlowProvider,
  Background,
  Controls,
  type Edge,
  type EdgeMarkerType,
  MarkerType,
} from "@xyflow/react";
import type { GraphNeighborhood, GraphEdge } from "@stackgraph/shared";
import { DomainNode, type DomainFlowNode } from "./DomainNode";
import { layoutNeighborhood } from "./layout";
import styles from "./graph.module.css";

const nodeTypes = { domain: DomainNode };

function edgeStyle(edge: GraphEdge, crossDomain: boolean, touchesSelection: boolean) {
  // Uncertain bridge (POSSIBLE): dashed neutral, no motion, labeled "possible match".
  if (edge.review_state === "POSSIBLE") {
    return {
      className: styles.edgePossible,
      style: { stroke: "var(--sg-text-muted)", strokeWidth: 1.5, strokeDasharray: "5 4" },
      label: "possible match",
      animated: false,
    };
  }
  // Confirmed cross-domain bridge: solid, domain-colored; pulses only when its selection is active.
  if (edge.review_state === "CONFIRMED" && crossDomain) {
    return {
      className: touchesSelection ? styles.edgeBridgeActive : styles.edgeBridge,
      style: { stroke: "var(--sg-color-domain-business-500)", strokeWidth: 2 },
      label: undefined,
      animated: false,
    };
  }
  // Regular edge (declared dependency etc.).
  return {
    className: styles.edgeRegular,
    style: { stroke: "var(--sg-surface-border-strong)", strokeWidth: 1.5 },
    label: undefined,
    animated: false,
  };
}

function InnerCanvas({
  graph,
  onSelect,
}: {
  graph: GraphNeighborhood;
  onSelect?: (nodeId: string | null) => void;
}) {
  const [selected, setSelected] = useState<string | null>(null);

  const nsById = useMemo(() => new Map(graph.nodes.map((n) => [n.id, n.namespace])), [graph.nodes]);

  const rfNodes: DomainFlowNode[] = useMemo(() => {
    const pos = layoutNeighborhood(graph);
    return graph.nodes.map((n) => ({
      id: n.id,
      type: "domain",
      position: { x: pos.get(n.id)?.x ?? 0, y: pos.get(n.id)?.y ?? 0 },
      data: {
        namespace: n.namespace,
        type: n.type,
        label: n.label,
        aggregate: n.aggregate,
        memberCount: n.member_count,
        isCenter: n.id === graph.center_id,
      },
    }));
  }, [graph]);

  const rfEdges: Edge[] = useMemo(() => {
    const marker: EdgeMarkerType = { type: MarkerType.ArrowClosed, width: 14, height: 14 };
    return graph.edges.map((e) => {
      const crossDomain = nsById.get(e.source) !== nsById.get(e.target);
      const touchesSelection = selected != null && (e.source === selected || e.target === selected);
      const s = edgeStyle(e, crossDomain, touchesSelection);
      return {
        id: e.id,
        source: e.source,
        target: e.target,
        label: s.label ?? e.predicate,
        className: s.className,
        style: s.style,
        animated: s.animated,
        markerEnd: marker,
        labelStyle: { fill: "var(--sg-text-muted)", fontSize: 11, fontFamily: "var(--sg-font-evidence)" },
        labelBgStyle: { fill: "var(--sg-surface-base)" },
      };
    });
  }, [graph.edges, nsById, selected]);

  return (
    <ReactFlow<DomainFlowNode, Edge>
      nodes={rfNodes}
      edges={rfEdges}
      nodeTypes={nodeTypes}
      // Read-only: no connect, delete, or drag-persist (plan §5.5).
      nodesDraggable={false}
      nodesConnectable={false}
      elementsSelectable
      deleteKeyCode={null}
      fitView
      fitViewOptions={{ padding: 0.2, minZoom: 0.4, maxZoom: 1.1 }}
      minZoom={0.3}
      maxZoom={1.5}
      proOptions={{ hideAttribution: true }}
      onSelectionChange={({ nodes }) => {
        const id = nodes[0]?.id ?? null;
        setSelected(id);
        onSelect?.(id);
      }}
    >
      <Background color="var(--sg-surface-border)" gap={22} size={1} />
      <Controls position="bottom-left" showInteractive={false} />
    </ReactFlow>
  );
}

/**
 * Bounded, read-only graph lens (plan §5.5). Renders a server-bounded neighborhood
 * (<=50 real nodes + aggregate clusters) with domain nodes and uncertain-bridge edges.
 * Ships an accessible text-equivalent list alongside the canvas (plan §8.1).
 */
export function GraphCanvas({
  graph,
  onSelect,
}: {
  graph: GraphNeighborhood;
  onSelect?: (nodeId: string | null) => void;
}) {
  return (
    <div className={styles.canvasWrap}>
      {graph.truncated ? (
        <div className={styles.truncation} role="status">
          Showing a bounded neighborhood
          {graph.truncation_reason ? ` — ${graph.truncation_reason}` : ""}. Nodes beyond one hop are clustered.
        </div>
      ) : null}
      <ReactFlowProvider>
        <InnerCanvas graph={graph} onSelect={onSelect} />
      </ReactFlowProvider>
      {/* Screen-reader / no-canvas equivalent */}
      <ul className={styles.srList}>
        {graph.edges.map((e) => {
          const s = graph.nodes.find((n) => n.id === e.source);
          const t = graph.nodes.find((n) => n.id === e.target);
          return (
            <li key={e.id}>
              {s?.label} {e.predicate.replace(/_/g, " ").toLowerCase()} {t?.label}
              {e.review_state === "POSSIBLE" ? " (possible match)" : ""}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
