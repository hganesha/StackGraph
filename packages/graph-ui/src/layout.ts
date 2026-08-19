// Deterministic left-to-right Dagre auto-layout for a bounded neighborhood.
// Derived from the Ladder Graph layout approach (Apache-2.0); see NOTICE.
// Simplified: StackGraph neighborhoods are server-bounded (<=50 nodes, no groups).
import dagre from "@dagrejs/dagre";
import type { GraphNeighborhood } from "@stackgraph/shared";

export const NODE_W = 210;
export const NODE_H = 68;

export interface Positioned {
  id: string;
  x: number;
  y: number;
}

export function layoutNeighborhood(graph: GraphNeighborhood): Map<string, Positioned> {
  const g = new dagre.graphlib.Graph().setDefaultEdgeLabel(() => ({}));
  g.setGraph({
    rankdir: "LR",
    ranksep: 90,
    nodesep: 32,
    marginx: 24,
    marginy: 24,
    ranker: "network-simplex",
  });

  const ids = new Set(graph.nodes.map((n) => n.id));
  for (const node of graph.nodes) {
    g.setNode(node.id, { width: NODE_W, height: NODE_H });
  }
  for (const edge of graph.edges) {
    if (ids.has(edge.source) && ids.has(edge.target)) g.setEdge(edge.source, edge.target);
  }

  dagre.layout(g);

  const out = new Map<string, Positioned>();
  for (const node of graph.nodes) {
    const p = g.node(node.id);
    // Dagre reports center coords; React Flow positions by top-left.
    out.set(node.id, { id: node.id, x: (p?.x ?? 0) - NODE_W / 2, y: (p?.y ?? 0) - NODE_H / 2 });
  }
  return out;
}
