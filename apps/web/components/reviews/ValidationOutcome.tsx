"use client";

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { stackGraphClient, type ModernizationValidationOutcomeRequest } from "@stackgraph/shared";
import styles from "./UncertainBridge.module.css";

type ValidationStatus = ModernizationValidationOutcomeRequest["validation_status"];

const CHOICES: ReadonlyArray<{ status: ValidationStatus; label: string; buttonClass: keyof typeof styles }> = [
  { status: "SUCCEEDED", label: "Succeeded", buttonClass: "confirm" },
  { status: "PARTIAL", label: "Partial", buttonClass: "ghost" },
  { status: "FAILED", label: "Failed", buttonClass: "reject" },
];

/**
 * Closes the loop on an accepted recommendation (contract: modernization-recommendations
 * validation-outcomes, `POST` recorded once and read back nowhere else yet — this is the
 * only surface, so the resolved state lives entirely in this component's own mutation).
 */
export function ValidationOutcome({ recommendationId }: { recommendationId: string }) {
  const [pending, setPending] = useState<ValidationStatus | null>(null);
  const [notes, setNotes] = useState("");
  const record = useMutation({
    mutationFn: (input: { status: ValidationStatus; notes: string }) =>
      stackGraphClient.recordModernizationValidationOutcome(recommendationId, {
        validation_status: input.status,
        notes: input.notes,
      }),
  });

  if (record.isSuccess) {
    return (
      <div className={`${styles.resolved} ${record.data.validation_status === "SUCCEEDED" ? styles.confirmed : record.data.validation_status === "FAILED" ? styles.rejected : ""}`}>
        Outcome recorded: {record.data.validation_status.toLowerCase()}
      </div>
    );
  }

  const option = CHOICES.find((entry) => entry.status === pending);

  return (
    <div className={styles.bridge}>
      <p className={styles.text}>Did this recommendation work out once implemented?</p>

      {option ? (
        <form
          className={styles.rationale}
          onSubmit={(e) => {
            e.preventDefault();
            if (!notes.trim()) return;
            record.mutate({ status: option.status, notes: notes.trim() });
          }}
        >
          <label className={styles.label}>
            What happened?
            <input
              className={styles.input}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Notes (required)"
              autoFocus
            />
          </label>
          <div className={styles.rationaleActions}>
            <button type="button" className={styles.ghost} onClick={() => setPending(null)}>
              Cancel
            </button>
            <button type="submit" className={styles.primary} disabled={!notes.trim() || record.isPending}>
              {record.isPending ? "Saving…" : `Record ${option.label.toLowerCase()}`}
            </button>
          </div>
        </form>
      ) : (
        <div className={styles.actions}>
          {CHOICES.map((choice) => (
            <button
              key={choice.status}
              type="button"
              className={styles[choice.buttonClass]}
              onClick={() => setPending(choice.status)}
            >
              {choice.label}
            </button>
          ))}
        </div>
      )}

      {record.isError ? <p className={styles.error}>Couldn’t save the outcome. Try again.</p> : null}
    </div>
  );
}
