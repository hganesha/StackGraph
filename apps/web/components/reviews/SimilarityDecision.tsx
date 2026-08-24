"use client";

import { useState } from "react";
import { ConfidenceChip, confidenceLabel } from "@stackgraph/design-system";
import { SIMILARITY_DECISIONS, type SimilarityDecision as Decision } from "@/lib/reviews";
import { useReviewApplicationSimilarity } from "@/lib/queries";
import styles from "./SimilarityDecision.module.css";

/**
 * Decide an application-similarity candidate from the review queue.
 *
 * The queue used to list these findings and then tell the reviewer to go and find
 * where they came from, so the only place a decision could be made was a drawer on
 * one of the two applications — a screen a reviewer working the queue never opens.
 *
 * Every decision carries a reason. The append-only feedback table stores the code and
 * the rationale beside the candidate's score and method version, which is what makes a
 * consolidation decision explainable a year later.
 *
 * NOTE: the queue item carries a title and a confidence, not the candidate's overlaps
 * and differences, so the "why it matches" evidence cannot be shown inline yet. That
 * needs a read for a single candidate by id — flagged as a contract follow-up. Until
 * then the link opens the application where the full explanation lives.
 */
export function SimilarityDecision({
  candidateId,
  title,
  confidence,
  entityId,
}: {
  candidateId: string;
  /** Omitted where the surrounding surface already names the pair. */
  title?: string;
  confidence: number;
  /** The application whose similarity list should refresh, when there is one. */
  entityId?: string;
}) {
  const [pending, setPending] = useState<Decision | null>(null);
  const [reasonCode, setReasonCode] = useState("");
  const [rationale, setRationale] = useState("");
  const review = useReviewApplicationSimilarity(entityId);

  const option = SIMILARITY_DECISIONS.find((entry) => entry.decision === pending);

  if (review.isSuccess) {
    return (
      <p className={styles.resolved}>
        Recorded as {review.data.review_state.replaceAll("_", " ").toLowerCase()}.
      </p>
    );
  }

  return (
    <div className={styles.decision}>
      {title ? (
        <div className={styles.summary}>
          <span className={styles.text}>
            possible duplicate: <span className="sg-mono">{title}</span>
          </span>
          <ConfidenceChip label={confidenceLabel(confidence)} value={confidence} />
        </div>
      ) : null}

      {option ? (
        <form
          className={styles.form}
          onSubmit={(event) => {
            event.preventDefault();
            if (!reasonCode) return;
            review.mutate({ candidateId, decision: option.decision, reasonCode, rationale });
          }}
        >
          <fieldset className={styles.fieldset}>
            <legend className={styles.legend}>{option.prompt}</legend>
            {option.reasonCodes.map(({ code, label }) => (
              <label key={code} className={styles.radio}>
                <input
                  type="radio"
                  name={`reason-${candidateId}`}
                  value={code}
                  checked={reasonCode === code}
                  onChange={() => setReasonCode(code)}
                />
                {label}
              </label>
            ))}
          </fieldset>

          <label className={styles.label}>
            Anything a future reader should know?
            <input
              className={styles.input}
              value={rationale}
              onChange={(event) => setRationale(event.target.value)}
              placeholder="Rationale (optional)"
            />
          </label>

          <div className={styles.formActions}>
            <button
              type="button"
              className={styles.ghost}
              onClick={() => {
                setPending(null);
                setReasonCode("");
              }}
            >
              Cancel
            </button>
            <button type="submit" className={styles.primary} disabled={!reasonCode || review.isPending}>
              {review.isPending ? "Saving…" : `Record ${option.label.toLowerCase()}`}
            </button>
          </div>
        </form>
      ) : (
        <div className={styles.actions}>
          {SIMILARITY_DECISIONS.map(({ decision, label }) => (
            <button
              key={decision}
              type="button"
              className={styles.choice}
              onClick={() => {
                setPending(decision);
                setReasonCode("");
              }}
            >
              {label}
            </button>
          ))}
        </div>
      )}

      {review.isError ? (
        <p className={styles.error} role="alert">
          Couldn’t save the decision. The candidate is unchanged — try again.
        </p>
      ) : null}
    </div>
  );
}
