"use client";

import {
  IconAlertTriangle,
  IconCopy,
  IconInboxOff,
  IconLink,
  IconSparkles,
  IconTrendingUp,
  type Icon,
} from "@tabler/icons-react";
import { ConfidenceChip, Skeleton, confidenceLabel } from "@stackgraph/design-system";
import type { ReviewQueueItem } from "@stackgraph/shared";
import { useReviewQueue } from "@/lib/queries";
import { UncertainBridge } from "@/components/reviews/UncertainBridge";
import styles from "./reviews.module.css";

/** Each finding type carries a mono glyph beside its always-present text label. */
const typeMeta: Record<ReviewQueueItem["item_type"], { label: string; icon: Icon }> = {
  IDENTITY_ASSERTION: { label: "Identity", icon: IconLink },
  CAPABILITY_INFERENCE: { label: "Capability", icon: IconSparkles },
  DUPLICATE_CAPABILITY: { label: "Duplicate", icon: IconCopy },
  MODERNIZATION_CANDIDATE: { label: "Candidate", icon: IconTrendingUp },
  MODERNIZATION_RECOMMENDATION: { label: "Recommendation", icon: IconTrendingUp },
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
          Identity, capability, duplication, and modernization findings that need a human decision.
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
          <IconAlertTriangle size={22} stroke={1.5} aria-hidden="true" />
          <p className={styles.emptyTitle}>The review queue could not be loaded.</p>
          <p className={styles.emptyBody}>Check the API connection, then reload this page.</p>
        </div>
      ) : data.items.length === 0 ? (
        <div className={styles.empty}>
          <IconInboxOff size={22} stroke={1.5} aria-hidden="true" />
          <p className={styles.emptyTitle}>Nothing needs review.</p>
          <p className={styles.emptyBody}>All current findings are confirmed, rejected, or not applicable.</p>
        </div>
      ) : (
        <ul className={styles.list}>
          {data.items.map((item) => {
            const [sourceLabel, targetLabel] = identityLabels(item.title);
            const TypeIcon = typeMeta[item.item_type].icon;
            return (
              <li key={`${item.item_type}:${item.item_id}`} className={styles.item}>
                <div className={styles.itemHead}>
                  <span className={styles.typeLabel}>
                    <TypeIcon size={13} stroke={1.75} aria-hidden="true" />
                    {typeMeta[item.item_type].label}
                  </span>
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
