"use client";

import { DomainBadge, Skeleton } from "@stackgraph/design-system";
import { useGraphNeighborhood } from "@/lib/queries";
import { UncertainBridge } from "@/components/reviews/UncertainBridge";
import styles from "./reviews.module.css";

// The center whose neighborhood we scan for uncertain bridges in fixture mode.
const DEMO_CENTER = "00000000-0000-4000-8000-000000000204";

export default function ReviewsPage() {
  const { data, isLoading } = useGraphNeighborhood(DEMO_CENTER);
  const possible = data?.edges.filter((e) => e.review_state === "POSSIBLE") ?? [];

  return (
    <div className={styles.page}>
      <header className={styles.head}>
        <h1 className={styles.title}>Reviews</h1>
        <p className={styles.subtitle}>
          Uncertain cross-domain bridges awaiting a human decision. Confirming or rejecting updates the graph.
        </p>
      </header>

      <div className={styles.note}>
        A dedicated review-queue endpoint is a pending backend addition; this view aggregates uncertain
        bridges from the current neighborhood.
      </div>

      {isLoading || !data ? (
        <div className={styles.list}>
          <Skeleton height={90} />
          <Skeleton height={90} />
        </div>
      ) : possible.length === 0 ? (
        <div className={styles.empty}>
          <p className={styles.emptyTitle}>No bridges need review.</p>
          <p className={styles.emptyBody}>Every cross-domain join is currently confirmed or not applicable.</p>
        </div>
      ) : (
        <ul className={styles.list}>
          {possible.map((e) => {
            const src = data.nodes.find((n) => n.id === e.source);
            const tgt = data.nodes.find((n) => n.id === e.target);
            return (
              <li key={e.id} className={styles.item}>
                <div className={styles.itemHead}>
                  {src ? <DomainBadge namespace={src.namespace} /> : null}
                  <span className={`${styles.itemLabel} sg-mono`}>{src?.label}</span>
                  <span aria-hidden="true" className={styles.arrow}>
                    →
                  </span>
                  {tgt ? <DomainBadge namespace={tgt.namespace} /> : null}
                  <span className={`${styles.itemLabel} sg-mono`}>{tgt?.label}</span>
                </div>
                <UncertainBridge
                  assertionId={e.id}
                  sourceLabel={src?.label ?? "?"}
                  targetLabel={tgt?.label ?? "?"}
                  confidence={e.confidence}
                />
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
