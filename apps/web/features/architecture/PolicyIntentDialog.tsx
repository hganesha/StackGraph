"use client";

import { useEffect, useId, useMemo, useRef, useState } from "react";
import type {
  ArchitectureCellDefinition,
  CanvasCellProjection,
  CanvasUnresolvedPolicy,
  CellApplicability,
  CellExpectation,
} from "@stackgraph/shared";
import { APPLICABILITY_LABEL, POLICY_LABEL } from "@stackgraph/canvas-ui";
import type { PolicyPrompt } from "./useCanvasPolicy";
import styles from "./architecture.module.css";

const APPLICABILITIES: CellApplicability[] = ["REQUIRED", "RECOMMENDED", "OPTIONAL", "NOT_APPLICABLE"];

export interface PolicySubmission {
  rationale: string;
  expectation?: CellExpectation;
  details?: { rationale: string; owner: string | null; effective_from: string | null; effective_to: string | null };
  targetCellKey?: string;
}

/**
 * Collects what a governance decision needs before it is written.
 *
 * A target decision without a recorded reason is an unexplainable policy, and the
 * panel that renders it later has nothing to show (spec §7.1, §7.2). The dialog is
 * therefore the only path to a profile write, and the rationale field is required for
 * every decision that narrows what teams may ship.
 */
export function PolicyIntentDialog({
  prompt,
  cell,
  definition,
  cells,
  unresolvedPolicy,
  conflict,
  isSaving,
  onConfirm,
  onDismiss,
}: {
  prompt: PolicyPrompt;
  cell: CanvasCellProjection | null;
  definition: ArchitectureCellDefinition | null;
  cells: ArchitectureCellDefinition[];
  unresolvedPolicy: CanvasUnresolvedPolicy | null;
  conflict: string | null;
  isSaving: boolean;
  onConfirm: (submission: PolicySubmission) => void;
  onDismiss: () => void;
}) {
  const fieldId = useId();
  const dialogRef = useRef<HTMLDivElement>(null);
  const firstFieldRef = useRef<HTMLElement>(null);

  const [rationale, setRationale] = useState(
    prompt.intent.kind === "EDIT_POLICY_DETAILS" ? cell?.policy?.rationale ?? "" : "",
  );
  const [owner, setOwner] = useState(cell?.policy?.owner ?? "");
  const [effectiveFrom, setEffectiveFrom] = useState(cell?.policy?.effective_from?.slice(0, 10) ?? "");
  const [effectiveTo, setEffectiveTo] = useState(cell?.policy?.effective_to?.slice(0, 10) ?? "");
  const [expectation, setExpectation] = useState<CellExpectation>({
    applicability: cell?.expectation.applicability ?? "RECOMMENDED",
    minimum_implementations: cell?.expectation.minimum_implementations ?? 1,
    maximum_implementations: cell?.expectation.maximum_implementations ?? null,
    allowed_diversity: cell?.expectation.allowed_diversity ?? null,
  });
  const [targetCellKey, setTargetCellKey] = useState("");

  const sortedCells = useMemo(
    () => [...cells].sort((a, b) => a.label.localeCompare(b.label)),
    [cells],
  );

  useEffect(() => {
    firstFieldRef.current?.focus();
  }, []);

  // Focus stays inside the dialog while it is open, and Escape always leaves.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onDismiss();
        return;
      }
      if (event.key !== "Tab" || !dialogRef.current) return;
      const focusable = dialogRef.current.querySelectorAll<HTMLElement>(
        'button:not([disabled]), input, select, textarea, [href], [tabindex]:not([tabindex="-1"])',
      );
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onDismiss]);

  const kind = prompt.intent.kind;
  const needsTargetCell = kind === "RESOLVE_UNRESOLVED_POLICY";
  const rationaleMissing = prompt.requiresRationale && rationale.trim().length === 0;
  const targetMissing = needsTargetCell && !targetCellKey;
  const blocked = isSaving || rationaleMissing || targetMissing;

  const submit = () => {
    if (blocked) return;
    onConfirm({
      rationale: rationale.trim(),
      expectation: kind === "SET_EXPECTATION" ? expectation : undefined,
      details:
        kind === "EDIT_POLICY_DETAILS"
          ? {
              rationale: rationale.trim(),
              owner: owner.trim() || null,
              effective_from: effectiveFrom ? new Date(effectiveFrom).toISOString() : null,
              effective_to: effectiveTo ? new Date(effectiveTo).toISOString() : null,
            }
          : undefined,
      targetCellKey: needsTargetCell ? targetCellKey : undefined,
    });
  };

  return (
    <div className={styles.dialogScrim} role="presentation" onClick={onDismiss}>
      <div
        ref={dialogRef}
        className={styles.dialog}
        role="dialog"
        aria-modal="true"
        aria-labelledby={`${fieldId}-title`}
        onClick={(event) => event.stopPropagation()}
      >
        <h2 className={styles.dialogTitle} id={`${fieldId}-title`}>
          {prompt.title}
        </h2>
        {definition ? <p className={styles.dialogBody}>{definition.label}</p> : null}

        {conflict ? (
          <p className={styles.dialogConflict} role="alert">
            {conflict}
          </p>
        ) : null}

        {kind === "SET_EXPECTATION" ? (
          <div className={styles.dialogFields}>
            <label className={styles.dialogLabel} htmlFor={`${fieldId}-applicability`}>
              Applicability
            </label>
            <select
              id={`${fieldId}-applicability`}
              ref={firstFieldRef as React.RefObject<HTMLSelectElement>}
              className={styles.dialogSelect}
              value={expectation.applicability}
              onChange={(event) =>
                setExpectation((current) => ({
                  ...current,
                  applicability: event.target.value as CellApplicability,
                }))
              }
            >
              {APPLICABILITIES.map((value) => (
                <option key={value} value={value}>
                  {APPLICABILITY_LABEL[value]}
                </option>
              ))}
            </select>

            <div className={styles.dialogRow}>
              <span className={styles.dialogField}>
                <label className={styles.dialogLabel} htmlFor={`${fieldId}-min`}>
                  Minimum
                </label>
                <input
                  id={`${fieldId}-min`}
                  className={styles.dialogInputLine}
                  type="number"
                  min={0}
                  value={expectation.minimum_implementations ?? ""}
                  onChange={(event) =>
                    setExpectation((current) => ({
                      ...current,
                      minimum_implementations: event.target.value === "" ? null : Number(event.target.value),
                    }))
                  }
                />
              </span>
              <span className={styles.dialogField}>
                <label className={styles.dialogLabel} htmlFor={`${fieldId}-max`}>
                  Maximum
                </label>
                <input
                  id={`${fieldId}-max`}
                  className={styles.dialogInputLine}
                  type="number"
                  min={0}
                  placeholder="unbounded"
                  value={expectation.maximum_implementations ?? ""}
                  onChange={(event) =>
                    setExpectation((current) => ({
                      ...current,
                      maximum_implementations: event.target.value === "" ? null : Number(event.target.value),
                    }))
                  }
                />
              </span>
              <span className={styles.dialogField}>
                <label className={styles.dialogLabel} htmlFor={`${fieldId}-diversity`}>
                  Allowed diversity
                </label>
                <input
                  id={`${fieldId}-diversity`}
                  className={styles.dialogInputLine}
                  type="number"
                  min={0}
                  placeholder="unbounded"
                  value={expectation.allowed_diversity ?? ""}
                  onChange={(event) =>
                    setExpectation((current) => ({
                      ...current,
                      allowed_diversity: event.target.value === "" ? null : Number(event.target.value),
                    }))
                  }
                />
              </span>
            </div>
            <p className={styles.dialogHint}>
              Marking a concern not applicable removes it from coverage and conformance denominators.
              It stays on the canvas, labelled, so the decision is visible rather than silent.
            </p>
          </div>
        ) : null}

        {kind === "EDIT_POLICY_DETAILS" ? (
          <div className={styles.dialogFields}>
            <label className={styles.dialogLabel} htmlFor={`${fieldId}-owner`}>
              Owner
            </label>
            <input
              id={`${fieldId}-owner`}
              ref={firstFieldRef as React.RefObject<HTMLInputElement>}
              className={styles.dialogInputLine}
              value={owner}
              placeholder="team or role accountable for this decision"
              onChange={(event) => setOwner(event.target.value)}
            />
            <div className={styles.dialogRow}>
              <span className={styles.dialogField}>
                <label className={styles.dialogLabel} htmlFor={`${fieldId}-from`}>
                  Effective from
                </label>
                <input
                  id={`${fieldId}-from`}
                  className={styles.dialogInputLine}
                  type="date"
                  value={effectiveFrom}
                  onChange={(event) => setEffectiveFrom(event.target.value)}
                />
              </span>
              <span className={styles.dialogField}>
                <label className={styles.dialogLabel} htmlFor={`${fieldId}-to`}>
                  Effective to
                </label>
                <input
                  id={`${fieldId}-to`}
                  className={styles.dialogInputLine}
                  type="date"
                  value={effectiveTo}
                  onChange={(event) => setEffectiveTo(event.target.value)}
                />
              </span>
            </div>
          </div>
        ) : null}

        {needsTargetCell ? (
          <div className={styles.dialogFields}>
            {unresolvedPolicy ? (
              <>
                <p className={styles.dialogBody}>
                  {unresolvedPolicy.reason} Each decision below moves to the chosen cell unchanged —
                  migration never invents a required or preferred state.
                </p>
                <ul className={styles.dialogList}>
                  {unresolvedPolicy.technologies.map((entry) => (
                    <li key={entry.technology.id}>
                      <span>{entry.technology.name}</span>
                      <span className={styles.dialogListState}>{POLICY_LABEL[entry.decision]}</span>
                    </li>
                  ))}
                </ul>
              </>
            ) : null}
            <label className={styles.dialogLabel} htmlFor={`${fieldId}-cell`}>
              Destination cell
            </label>
            <select
              id={`${fieldId}-cell`}
              ref={firstFieldRef as React.RefObject<HTMLSelectElement>}
              className={styles.dialogSelect}
              value={targetCellKey}
              onChange={(event) => setTargetCellKey(event.target.value)}
              required
            >
              <option value="">Choose a cell…</option>
              {sortedCells.map((entry) => (
                <option key={entry.key} value={entry.key}>
                  {entry.label}
                </option>
              ))}
            </select>
          </div>
        ) : null}

        <label className={styles.dialogLabel} htmlFor={`${fieldId}-rationale`}>
          Rationale{prompt.requiresRationale ? "" : " (optional)"}
        </label>
        <textarea
          id={`${fieldId}-rationale`}
          ref={
            kind === "PROMOTE_FROM_ACTUAL" || kind === "SET_TECHNOLOGY_DECISION"
              ? (firstFieldRef as React.RefObject<HTMLTextAreaElement>)
              : undefined
          }
          className={styles.dialogInput}
          rows={3}
          value={rationale}
          onChange={(event) => setRationale(event.target.value)}
          placeholder="Why is this the right decision for the estate?"
          aria-describedby={rationaleMissing ? `${fieldId}-rationale-hint` : undefined}
        />
        {rationaleMissing ? (
          <p className={styles.dialogHint} id={`${fieldId}-rationale-hint`}>
            A decision that narrows what teams may ship needs a reason on the record.
          </p>
        ) : null}

        <div className={styles.dialogActions}>
          <button type="button" className={styles.dialogSecondary} onClick={onDismiss}>
            Cancel
          </button>
          <button type="button" className={styles.dialogPrimary} disabled={blocked} onClick={submit}>
            {isSaving ? "Saving…" : "Record decision"}
          </button>
        </div>
      </div>
    </div>
  );
}
