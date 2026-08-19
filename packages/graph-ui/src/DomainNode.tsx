import { Handle, Position, type NodeProps, type Node } from "@xyflow/react";
import type { Namespace } from "@stackgraph/shared";
import { DomainBadge } from "@stackgraph/design-system";
import styles from "./graph.module.css";

const FAMILY: Record<Namespace, string> = {
  BUSINESS: "business",
  ENTERPRISE: "enterprise",
  TECHNOLOGY: "enterprise",
  OSS: "oss",
  DEPLOYMENT: "enterprise",
  INTELLIGENCE: "intelligence",
};

export interface DomainNodeData extends Record<string, unknown> {
  namespace: Namespace;
  type: string;
  label: string;
  aggregate: boolean;
  memberCount?: number;
  isCenter: boolean;
}

export type DomainFlowNode = Node<DomainNodeData, "domain">;

/** A bounded-neighborhood node: domain-badged, mono label, cluster styling for aggregates. */
export function DomainNode({ data, selected }: NodeProps<DomainFlowNode>) {
  const family = FAMILY[data.namespace];
  return (
    <div
      className={`${styles.node} ${data.aggregate ? styles.aggregate : ""} ${data.isCenter ? styles.center : ""} ${
        selected ? styles.selected : ""
      }`}
      style={{ ["--accent" as string]: `var(--sg-color-domain-${family}-500)` }}
    >
      <Handle type="target" position={Position.Left} className={styles.handle} />
      <div className={styles.nodeHead}>
        <DomainBadge namespace={data.namespace} />
        <span className={styles.nodeType}>{data.type}</span>
      </div>
      <div className={`${styles.nodeLabel} sg-mono`}>
        {data.aggregate && data.memberCount ? `+${data.memberCount} ${data.label}` : data.label}
      </div>
      <Handle type="source" position={Position.Right} className={styles.handle} />
    </div>
  );
}
