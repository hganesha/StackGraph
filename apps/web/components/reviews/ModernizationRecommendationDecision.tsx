"use client";

import { useState } from "react";
import { ConfidenceChip, confidenceLabel } from "@stackgraph/design-system";
import {
  useReviewModernizationRecommendation,
  isConflict,
  type ModernizationRecommendationDecision as Decision,
} from "@/lib/reviews";
import styles from "./UncertainBridge.module.css";

const CHOICES: ReadonlyArray<{ decision: Decision; label: string; verb: string; buttonClass: keyof typeof styles }> = [
  { decision: "ACCEPT", label: "Accept", verb: "accept", buttonClass: "confirm" },
  { decision: "REJECT", label: "Reject", verb: "reject", buttonClass: "reject" },
  { decision: "DISMISS", label: "Dismiss", verb: "dismiss", buttonClass: "ghost" },
];

function resolvedClass(state: string) {
  if (state === "ACCEPTED") return styles.confirmed;
  if (state === "REJECTED") return styles.rejected;
  return "";
}

/**
 * Decide a modernization recommendation: ACCEPT/REJECT/DISMISS, distinct from the
 * two-way pattern used elsewhere (contract: `modernizationRecommendation.review_state`).
 * `reviewState` carries whatever the entity already has on load, since — unlike a queue
 * row, which only ever appears while UNREVIEWED — this also renders on a detail page for
 * a recommendation that may have been decided in an earlier session.
 */
export function ModernizationRecommendationDecision({
  recommendationId,
  reviewState,
  confidence,
  expectedVersion,
  onResolved,
}: {
  recommendationId: string;
  reviewState: "UNREVIEWED" | "ACCEPTED" | "REJECTED" | "DISMISSED";
  confidence: number;
  expectedVersion: number;
  onResolved?: (state: "ACCEPTED" | "REJECTED" | "DISMISSED", version: number) => void;
}) {
  const [pending, setPending] = useState<Decision | null>(null);
  const [rationale, setRationale] = useState("");
  const review = useReviewModernizationRecommendation(recommendationId);

  const decidedState = review.data?.review_state ?? (reviewState !== "UNREVIEWED" ? reviewState : null);
  if (decidedState) {
    return (
      <div className={`${styles.resolved} ${resolvedClass(decidedState)}`}>
        Recommendation {decidedState.toLowerCase()}
        {review.data ? ` · v${review.data.version}` : null}
      </div>
    );
  }

  const option = CHOICES.find((entry) => entry.decision === pending);

  return (
    <div className={styles.bridge}>
      <div className={styles.summary}>
        <span className={styles.text}>Decide this recommendation</span>
        <ConfidenceChip label={confidenceLabel(confidence)} value={confidence} />
      </div>

      {option ? (
        <form
          className={styles.rationale}
          onSubmit={(e) => {
            e.preventDefault();
            if (!rationale.trim()) return;
            review.mutate(
              { decision: option.decision, rationale: rationale.trim(), expectedVersion },
              { onSuccess: (result) => onResolved?.(result.review_state, result.version) },
            );
          }}
        >
          <label className={styles.label}>
            Why {option.verb} this recommendation?
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
              {review.isPending ? "Saving…" : `Submit ${option.verb}`}
            </button>
          </div>
        </form>
      ) : (
        <div className={styles.actions}>
          {CHOICES.map((choice) => (
            <button
              key={choice.decision}
              type="button"
              className={styles[choice.buttonClass]}
              onClick={() => setPending(choice.decision)}
            >
              {choice.label}
            </button>
          ))}
        </div>
      )}

      {review.isError ? (
        <p className={styles.error}>
          {isConflict(review.error)
            ? "This recommendation was already decided by someone else. Reload to see the current state."
            : "Couldn’t save the decision. Try again."}
        </p>
      ) : null}
    </div>
  );
}
