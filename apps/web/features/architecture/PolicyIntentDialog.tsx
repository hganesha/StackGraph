"use client";

import { useEffect, useRef, useState } from "react";
import type { PolicyPrompt } from "./useCanvasPolicy";
import styles from "./architecture.module.css";

/**
 * Collects the rationale a governance decision needs before it is written. A target
 * decision without a recorded reason is an unexplainable policy, and the panel that
 * renders it later has nothing to show (spec §7.1, §7.2).
 */
export function PolicyIntentDialog({
  prompt,
  conflict,
  isSaving,
  onConfirm,
  onDismiss,
}: {
  prompt: PolicyPrompt;
  conflict: string | null;
  isSaving: boolean;
  onConfirm: (rationale: string) => void;
  onDismiss: () => void;
}) {
  const [rationale, setRationale] = useState("");
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const unsupported =
    prompt.intent.kind === "EDIT_POLICY_DETAILS" ||
    prompt.intent.kind === "RESOLVE_UNRESOLVED_POLICY" ||
    prompt.intent.kind === "SET_EXPECTATION";

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onDismiss();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onDismiss]);

  return (
    <div className={styles.dialogScrim} role="presentation" onClick={onDismiss}>
      <div
        className={styles.dialog}
        role="dialog"
        aria-modal="true"
        aria-labelledby="policy-dialog-title"
        onClick={(event) => event.stopPropagation()}
      >
        <h2 className={styles.dialogTitle} id="policy-dialog-title">
          {prompt.title}
        </h2>

        {conflict ? (
          <p className={styles.dialogConflict} role="alert">
            {conflict}
          </p>
        ) : null}

        {unsupported ? (
          <p className={styles.dialogBody}>
            Full target-policy editing lands with the governed-target phase. This action is recognised
            but not yet writable, so nothing has been changed.
          </p>
        ) : (
          <>
            <label className={styles.dialogLabel} htmlFor="policy-rationale">
              Rationale{prompt.requiresRationale ? "" : " (optional)"}
            </label>
            <textarea
              id="policy-rationale"
              ref={inputRef}
              className={styles.dialogInput}
              rows={4}
              value={rationale}
              onChange={(event) => setRationale(event.target.value)}
              placeholder="Why is this the right decision for the estate?"
            />
          </>
        )}

        <div className={styles.dialogActions}>
          <button type="button" className={styles.dialogSecondary} onClick={onDismiss}>
            {unsupported ? "Close" : "Cancel"}
          </button>
          {!unsupported ? (
            <button
              type="button"
              className={styles.dialogPrimary}
              disabled={isSaving || (prompt.requiresRationale && rationale.trim().length === 0)}
              onClick={() => onConfirm(rationale.trim())}
            >
              {isSaving ? "Saving…" : "Record decision"}
            </button>
          ) : null}
        </div>
      </div>
    </div>
  );
}
