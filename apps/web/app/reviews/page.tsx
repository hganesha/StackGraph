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
import Link from "next/link";
import { ConfidenceChip, Skeleton, confidenceLabel } from "@stackgraph/design-system";
import type { ReviewQueueItem } from "@stackgraph/shared";
import { useReviewQueue } from "@/lib/queries";
import { UncertainBridge } from "@/components/reviews/UncertainBridge";
import { SimilarityDecision } from "@/components/reviews/SimilarityDecision";
import { OptimisticReviewDecision } from "@/components/reviews/OptimisticReviewDecision";
import { ModernizationRecommendationDecision } from "@/components/reviews/ModernizationRecommendationDecision";
import styles from "./reviews.module.css";

/** Each finding type carries a mono glyph beside its always-present text label. */
const typeMeta: Record<ReviewQueueItem["item_type"], { label: string; icon: Icon }> = {
  IDENTITY_ASSERTION: { label: "Identity", icon: IconLink },
  CAPABILITY_INFERENCE: { label: "Capability", icon: IconSparkles },
  DUPLICATE_CAPABILITY: { label: "Duplicate", icon: IconCopy },
  MODERNIZATION_CANDIDATE: { label: "Candidate", icon: IconTrendingUp },
  MODERNIZATION_RECOMMENDATION: { label: "Recommendation", icon: IconTrendingUp },
  APPLICATION_SIMILARITY: { label: "Application match", icon: IconCopy },
};

function identityLabels(title: string): [string, string] {
  const labels = title.split(/\s*(?:↔|→)\s*/, 2);
  return [labels[0] || title, labels[1] || "possible match"];
}

/**
 * Where a finding can be reviewed, for the types that are not yet decided in place.
 * Every row used to end in the same dead sentence telling the reader to go and find
 * it themselves; a link is the least this queue owes them.
 */
function reviewLocation(item: ReviewQueueItem): { href: string; label: string } | null {
  if (item.repository_id) {
    return { href: `/repositories/${item.repository_id}`, label: "Open the repository" };
  }
  return null;
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
        Everything waiting on a decision across your estate, most confident and most recent
        first. Your decision applies immediately and is recorded in the audit trail.
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
            const location = reviewLocation(item);
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
                ) : item.item_type === "APPLICATION_SIMILARITY" ? (
                  <SimilarityDecision
                    candidateId={item.item_id}
                    title={item.title}
                    confidence={item.confidence}
                  />
                ) : item.item_type === "MODERNIZATION_RECOMMENDATION" ? (
                  <ModernizationRecommendationDecision
                    recommendationId={item.item_id}
                    reviewState="UNREVIEWED"
                    confidence={item.confidence}
                    expectedVersion={item.version}
                  />
                ) : item.item_type === "CAPABILITY_INFERENCE" ||
                  item.item_type === "DUPLICATE_CAPABILITY" ||
                  item.item_type === "MODERNIZATION_CANDIDATE" ? (
                  <OptimisticReviewDecision
                    kind={item.item_type}
                    itemId={item.item_id}
                    title={item.title}
                    confidence={item.confidence}
                    expectedVersion={item.version}
                  />
                ) : location ? (
                  <Link className={styles.reviewHint} href={location.href}>
                    {location.label} <span aria-hidden="true">→</span>
                  </Link>
                ) : (
                  <p className={styles.reviewHint}>
                    This finding is decided where it was found, on the repository it came from.
                  </p>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
