export { GraphCanvas } from "./GraphCanvas";
export { DomainNode } from "./DomainNode";
export type { DomainNodeData, DomainFlowNode } from "./DomainNode";
export { layoutNeighborhood, NODE_W, NODE_H } from "./layout";

/** Contract-enforced cap on real (non-aggregate) rendered nodes. */
export const GRAPH_UI_MAX_REAL_NODES = 50;
