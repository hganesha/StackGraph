"use client";

import { useMemo, useState, type CSSProperties } from "react";
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
import { layoutNeighborhood, NODE_H, NODE_W } from "./layout";
import styles from "./graph.module.css";

const nodeTypes = { domain: DomainNode };
// SVG marker identifiers cannot reliably contain CSS var() expressions. Keep
// this value aligned with --sg-color-domain-enterprise-300.
const EDGE_COLOR = "#92A9C9";

function edgeStyle(edge: GraphEdge, crossDomain: boolean, touchesSelection: boolean) {
  // Uncertain bridge (POSSIBLE): dashed neutral, no motion, labeled "possible match".
  if (edge.review_state === "POSSIBLE") {
    return {
      className: styles.edgePossible,
      style: { stroke: "var(--sg-text-secondary)", strokeWidth: 2, strokeDasharray: "6 5", opacity: 0.9 },
      label: "possible match",
      animated: false,
    };
  }
  // Confirmed cross-domain bridge: solid, domain-colored; pulses only when its selection is active.
  if (edge.review_state === "CONFIRMED" && crossDomain) {
    return {
      className: touchesSelection ? styles.edgeBridgeActive : styles.edgeBridge,
      style: { stroke: "var(--sg-color-domain-business-500)", strokeWidth: 2.5, opacity: 0.95 },
      label: undefined,
      animated: false,
    };
  }
  // Regular edge (declared dependency etc.).
  return {
    className: styles.edgeRegular,
    // The initial bounded-graph fit can reduce the canvas to 40% zoom. A 1.5px
    // border-token stroke becomes a sub-pixel, low-contrast line at that scale.
    style: { stroke: EDGE_COLOR, strokeWidth: 3.5 },
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
    const marker: EdgeMarkerType = {
      type: MarkerType.ArrowClosed,
      width: 16,
      height: 16,
      color: EDGE_COLOR,
    };
    return graph.edges.map((e) => {
      const crossDomain = nsById.get(e.source) !== nsById.get(e.target);
      const touchesSelection = selected != null && (e.source === selected || e.target === selected);
      const s = edgeStyle(e, crossDomain, touchesSelection);
      return {
        id: e.id,
        source: e.source,
        target: e.target,
        // Dense graph predicates remain available in the inspector and the
        // accessible edge list. Inline labels covered short connections at the
        // default zoom, making the edge itself appear to be missing.
        label: s.label,
        className: s.className,
        style: s.style,
        animated: s.animated,
        markerEnd: marker,
        labelStyle: {
          fill: "var(--sg-text-secondary)",
          fontSize: 11,
          fontWeight: 500,
          fontFamily: "var(--sg-font-evidence)",
        },
        labelBgStyle: { fill: "var(--sg-surface-card)", fillOpacity: 0.94 },
        labelBgPadding: [4, 2] as [number, number],
        labelBgBorderRadius: 3,
      };
    });
  }, [graph.edges, nsById, selected]);

  const paintSurface = useMemo(() => {
    const width = Math.max(...rfNodes.map((node) => node.position.x + NODE_W), NODE_W) + 24;
    const height = Math.max(...rfNodes.map((node) => node.position.y + NODE_H), NODE_H) + 24;
    return {
      ["--sg-graph-paint-width" as string]: `${Math.ceil(width)}px`,
      ["--sg-graph-paint-height" as string]: `${Math.ceil(height)}px`,
    } as CSSProperties;
  }, [rfNodes]);

  return (
    <ReactFlow<DomainFlowNode, Edge>
      style={paintSurface}
      nodes={rfNodes}
      edges={rfEdges}
      nodeTypes={nodeTypes}
      // Read-only: no connect, delete, or drag-persist (plan §5.5).
      nodesDraggable={false}
      nodesConnectable={false}
      elementsSelectable
      deleteKeyCode={null}
      onInit={(instance) => {
        const center = rfNodes.find((node) => node.id === graph.center_id);
        if (!center) return;
        // Begin on the entity the user chose. Fitting a 50-node bounded graph
        // made the center and its connecting lines land outside the viewport.
        void instance.setCenter(
          center.position.x + NODE_W / 2,
          center.position.y + NODE_H / 2,
          { zoom: 0.65, duration: 0 },
        );
      }}
      minZoom={0.08}
      maxZoom={1.5}
      proOptions={{ hideAttribution: true }}
      onSelectionChange={({ nodes }) => {
        const id = nodes[0]?.id ?? null;
        setSelected(id);
        onSelect?.(id);
      }}
      onNodeClick={(_, node) => {
        setSelected(node.id);
        onSelect?.(node.id);
      }}
      onPaneClick={() => {
        setSelected(null);
        onSelect?.(null);
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
