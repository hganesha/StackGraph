"use client";

import { useState } from "react";
import { ConfidenceChip, confidenceLabel } from "@stackgraph/design-system";
import { useReviewMutation, isConflict, type ReviewDecision } from "@/lib/reviews";
import styles from "./UncertainBridge.module.css";

/**
 * The uncertain-bridge control (plan §4, §5.2): a dashed "possible match" join with
 * Confirm/Reject. A rationale is required (contract). Optimistic concurrency via expected_version.
 *
 * NOTE: the graph edge read model does not (yet) carry an identity_assertion_id; here the edge id
 * stands in for it. Reviewing a bridge from the graph needs the backend to expose that id — flagged
 * as a contract follow-up in the UX plan open decisions.
 */
export function UncertainBridge({
  assertionId,
  sourceLabel,
  targetLabel,
  confidence,
  expectedVersion = 1,
  onResolved,
}: {
  assertionId: string;
  sourceLabel: string;
  targetLabel: string;
  confidence: number;
  expectedVersion?: number;
  onResolved?: (decision: ReviewDecision) => void;
}) {
  const [pending, setPending] = useState<ReviewDecision | null>(null);
  const [rationale, setRationale] = useState("");
  const review = useReviewMutation(assertionId);

  if (review.isSuccess) {
    const decided = review.data.review_state;
    return (
      <div className={`${styles.resolved} ${decided === "CONFIRMED" ? styles.confirmed : styles.rejected}`}>
        Bridge {decided.toLowerCase()} · v{review.data.version}
      </div>
    );
  }

  return (
    <div className={styles.bridge}>
      <div className={styles.summary}>
        <span className={styles.dashed} aria-hidden="true" />
        <span className={styles.text}>
          possible match: <span className="sg-mono">{sourceLabel}</span> →{" "}
          <span className="sg-mono">{targetLabel}</span>
        </span>
        <ConfidenceChip label={confidenceLabel(confidence)} value={confidence} />
      </div>

      {pending ? (
        <form
          className={styles.rationale}
          onSubmit={(e) => {
            e.preventDefault();
            if (!rationale.trim()) return;
            review.mutate(
              { decision: pending, rationale: rationale.trim(), expectedVersion },
              { onSuccess: () => onResolved?.(pending) },
            );
          }}
        >
          <label className={styles.label}>
            Why {pending === "CONFIRM" ? "confirm" : "reject"} this match?
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
            ? "This bridge was already reviewed by someone else. Reload to see the current state."
            : "Couldn’t save the review. Try again."}
        </p>
      ) : null}
    </div>
  );
}
