"use client";

import { useState } from "react";
import { ConfidenceChip, confidenceLabel } from "@stackgraph/design-system";
import {
  useOptimisticReviewMutation,
  isConflict,
  type OptimisticReviewKind,
  type ReviewDecision,
} from "@/lib/reviews";
import styles from "./UncertainBridge.module.css";

const NOUN: Record<OptimisticReviewKind, string> = {
  CAPABILITY_INFERENCE: "capability inference",
  DUPLICATE_CAPABILITY: "duplicate capability match",
  MODERNIZATION_CANDIDATE: "modernization candidate",
};

/**
 * Confirm/Reject for the three finding types that share the identity-bridge shape:
 * two-way decision, required rationale, optimistic concurrency via expected_version.
 */
export function OptimisticReviewDecision({
  kind,
  itemId,
  title,
  confidence,
  expectedVersion = 1,
}: {
  kind: OptimisticReviewKind;
  itemId: string;
  title: string;
  confidence: number;
  expectedVersion?: number;
}) {
  const [pending, setPending] = useState<ReviewDecision | null>(null);
  const [rationale, setRationale] = useState("");
  const review = useOptimisticReviewMutation(kind, itemId);
  const noun = NOUN[kind];

  if (review.isSuccess) {
    const decided = review.data.review_state;
    return (
      <div className={`${styles.resolved} ${decided === "CONFIRMED" ? styles.confirmed : styles.rejected}`}>
        {noun[0].toUpperCase()}{noun.slice(1)} {decided.toLowerCase()} · v{review.data.version}
      </div>
    );
  }

  return (
    <div className={styles.bridge}>
      <div className={styles.summary}>
        <span className={styles.dashed} aria-hidden="true" />
        <span className={styles.text}>
          {noun}: <span className="sg-mono">{title}</span>
        </span>
        <ConfidenceChip label={confidenceLabel(confidence)} value={confidence} />
      </div>

      {pending ? (
        <form
          className={styles.rationale}
          onSubmit={(e) => {
            e.preventDefault();
            if (!rationale.trim()) return;
            review.mutate({ decision: pending, rationale: rationale.trim(), expectedVersion });
          }}
        >
          <label className={styles.label}>
            Why {pending === "CONFIRM" ? "confirm" : "reject"} this {noun}?
            <input
              className={styles.input}
              value={rationale}
              onChange={(e) => setRationale(e.target.value)}
              placeholder="Rationale (required)"
              autoFocus
            />
          </label>
          <div className={styles.rationaleActions}>
            <button type="button" className={styles.ghost} onClick={() => setPending(null)}>
              Cancel
            </button>
            <button type="submit" className={styles.primary} disabled={!rationale.trim() || review.isPending}>
              {review.isPending ? "Saving…" : `Submit ${pending === "CONFIRM" ? "confirm" : "reject"}`}
            </button>
          </div>
        </form>
      ) : (
        <div className={styles.actions}>
          <button type="button" className={styles.confirm} onClick={() => setPending("CONFIRM")}>
            Confirm
          </button>
          <button type="button" className={styles.reject} onClick={() => setPending("REJECT")}>
            Reject
          </button>
        </div>
      )}

      {review.isError ? (
        <p className={styles.error}>
          {isConflict(review.error)
            ? "This was already reviewed by someone else. Reload to see the current state."
            : "Couldn’t save the review. Try again."}
        </p>
      ) : null}
    </div>
  );
}
