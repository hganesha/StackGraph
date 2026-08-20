"use client";

import { ConfidenceChip, Skeleton, confidenceLabel } from "@stackgraph/design-system";
import type { ReviewQueueItem } from "@stackgraph/shared";
import { useReviewQueue } from "@/lib/queries";
import { UncertainBridge } from "@/components/reviews/UncertainBridge";
import styles from "./reviews.module.css";

const typeLabels: Record<ReviewQueueItem["item_type"], string> = {
  IDENTITY_ASSERTION: "Identity",
  CAPABILITY_INFERENCE: "Capability",
  DUPLICATE_CAPABILITY: "Duplicate",
  MODERNIZATION_CANDIDATE: "Candidate",
  MODERNIZATION_RECOMMENDATION: "Recommendation",
};

function identityLabels(title: string): [string, string] {
  const labels = title.split(/\s*(?:↔|→)\s*/, 2);
  return [labels[0] || title, labels[1] || "possible match"];
}

export default function ReviewsPage() {
  const { data, isLoading, isError } = useReviewQueue();

  return (
    <div className={styles.page}>
      <header className={styles.head}>
        <h1 className={styles.title}>Reviews</h1>
        <p className={styles.subtitle}>
          Evidence-backed identity, capability, duplication, and modernization findings awaiting a human decision.
        </p>
      </header>

      <div className={styles.note}>
        The cross-estate queue is tenant-scoped and ordered by confidence and recency. Decisions remain
        optimistic and audited by the originating workflow.
      </div>

      {isLoading ? (
        <div className={styles.list}>
          <Skeleton height={90} />
          <Skeleton height={90} />
        </div>
      ) : isError || !data ? (
        <div className={styles.empty} role="alert">
          <p className={styles.emptyTitle}>The review queue could not be loaded.</p>
          <p className={styles.emptyBody}>Check the API connection, then reload this page.</p>
        </div>
      ) : data.items.length === 0 ? (
        <div className={styles.empty}>
          <p className={styles.emptyTitle}>Nothing needs review.</p>
          <p className={styles.emptyBody}>All current findings are confirmed, rejected, or not applicable.</p>
        </div>
      ) : (
        <ul className={styles.list}>
          {data.items.map((item) => {
            const [sourceLabel, targetLabel] = identityLabels(item.title);
            return (
              <li key={`${item.item_type}:${item.item_id}`} className={styles.item}>
                <div className={styles.itemHead}>
                  <span className={styles.typeLabel}>{typeLabels[item.item_type]}</span>
                  <span className={styles.itemLabel}>{item.title}</span>
                  <span className={styles.confidence}>
                    <ConfidenceChip label={confidenceLabel(item.confidence)} value={item.confidence} />
                  </span>
                </div>
                {item.summary ? <p className={styles.summary}>{item.summary}</p> : null}
                {item.item_type === "IDENTITY_ASSERTION" ? (
                  <UncertainBridge
                    assertionId={item.item_id}
                    sourceLabel={sourceLabel}
                    targetLabel={targetLabel}
                    confidence={item.confidence}
                    expectedVersion={item.version}
                  />
                ) : (
                  <p className={styles.reviewHint}>Open the originating lens to review this finding.</p>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
