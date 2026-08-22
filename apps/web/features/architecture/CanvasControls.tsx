"use client";

import Link from "next/link";
import type { CanvasEmphasis, CanvasMode } from "@stackgraph/canvas-ui";
import type { CanvasProjection } from "@stackgraph/shared";
import styles from "./architecture.module.css";

export type CanvasView = "actual" | "target" | "drift" | "compare";

const EMPHASIS_OPTIONS: Array<{ value: CanvasEmphasis; label: string; hint: string }> = [
  { value: "posture", label: "Posture", hint: "Tone follows the measured posture band." },
  { value: "conformance", label: "Conformance", hint: "Tone follows alignment with the target policy." },
  { value: "coverage", label: "Coverage", hint: "Tone follows applicability against what was found." },
  { value: "none", label: "None", hint: "No tone; read the labels only." },
];

/**
 * Controls above the canvas. Each control changes emphasis or filtering — none of
 * them removes a canonical cell, so the frame a reader learns stays the frame they
 * keep (spec §3.1, §5.4).
 */
export function CanvasControls({
  view,
  onViewChange,
  emphasis,
  onEmphasisChange,
  density,
  onDensityChange,
  mode,
  onModeChange,
  canGovern,
  canWritePolicy = false,
  draftVersion = null,
  canReview,
  projection,
  summaryVisible = true,
  subjectId,
  baselineSubjectId,
  onBaselineChange,
  comparableApplications = [],
}: {
  view: CanvasView;
  onViewChange: (view: CanvasView) => void;
  emphasis: CanvasEmphasis;
  onEmphasisChange: (emphasis: CanvasEmphasis) => void;
  density: "comfortable" | "compact";
  onDensityChange: (density: "comfortable" | "compact") => void;
  mode: CanvasMode;
  onModeChange?: (mode: CanvasMode) => void;
  canGovern: boolean;
  canWritePolicy?: boolean;
  draftVersion?: number | null;
  canReview: boolean;
  projection: CanvasProjection | null;
  summaryVisible?: boolean;
  subjectId?: string;
  baselineSubjectId: string | null;
  onBaselineChange: (subjectId: string | null) => void;
  comparableApplications?: Array<{ id: string; name: string }>;
}) {
  return (
    <div className={styles.controls}>
      <fieldset className={styles.controlGroup}>
        <legend className={styles.controlLegend}>View</legend>
        <div className={styles.segmented} role="radiogroup" aria-label="Canvas view">
          {(
            [
              ["actual", "Actual", true, undefined],
              ["target", "Target", canReview, "Target and drift require review access."],
              ["drift", "Drift", canReview, "Target and drift require review access."],
              [
                "compare",
                "Compare",
                Boolean(subjectId) && comparableApplications.length > 0,
                "Comparison needs an application in scope and at least one other to compare against.",
              ],
            ] as Array<[CanvasView, string, boolean, string | undefined]>
          ).map(([value, label, allowed, blockedReason]) => (
            <button
              key={value}
              type="button"
              role="radio"
              aria-checked={view === value}
              disabled={!allowed}
              title={allowed ? undefined : blockedReason}
              className={`${styles.segment} ${view === value ? styles.segmentActive : ""}`}
              onClick={() => onViewChange(value)}
            >
              {label}
            </button>
          ))}
        </div>
      </fieldset>

      {view === "compare" ? (
        <fieldset className={styles.controlGroup}>
          <legend className={styles.controlLegend}>Compare against</legend>
          <select
            className={styles.controlSelect}
            aria-label="Baseline application"
            value={baselineSubjectId ?? ""}
            onChange={(event) => onBaselineChange(event.target.value || null)}
          >
            <option value="">Choose an application…</option>
            {comparableApplications.map((application) => (
              <option key={application.id} value={application.id}>
                {application.name}
              </option>
            ))}
          </select>
        </fieldset>
      ) : null}

      <fieldset className={styles.controlGroup}>
        <legend className={styles.controlLegend}>Emphasis</legend>
        <div className={styles.segmented} role="radiogroup" aria-label="Cell emphasis">
          {EMPHASIS_OPTIONS.map((option) => (
            <button
              key={option.value}
              type="button"
              role="radio"
              aria-checked={emphasis === option.value}
              title={option.hint}
              className={`${styles.segment} ${emphasis === option.value ? styles.segmentActive : ""}`}
              onClick={() => onEmphasisChange(option.value)}
            >
              {option.label}
            </button>
          ))}
        </div>
      </fieldset>

      <fieldset className={styles.controlGroup}>
        <legend className={styles.controlLegend}>Density</legend>
        <div className={styles.segmented} role="radiogroup" aria-label="Canvas density">
          {(["comfortable", "compact"] as const).map((value) => (
            <button
              key={value}
              type="button"
              role="radio"
              aria-checked={density === value}
              className={`${styles.segment} ${density === value ? styles.segmentActive : ""}`}
              onClick={() => onDensityChange(value)}
            >
              {value === "comfortable" ? "Comfortable" : "Compact"}
            </button>
          ))}
        </div>
      </fieldset>

      {canGovern && onModeChange ? (
        <fieldset className={styles.controlGroup}>
          <legend className={styles.controlLegend}>Editing</legend>
          <label className={styles.toggle}>
            <input
              type="checkbox"
              checked={mode === "govern"}
              disabled={!canWritePolicy}
              onChange={(event) => onModeChange(event.target.checked ? "govern" : "read")}
            />
            <span>
              {canWritePolicy ? `Govern draft v${draftVersion}` : "Govern target"}
            </span>
          </label>
          {!canWritePolicy ? (
            <p className={styles.controlNote}>
              No draft revision is open. Edits are made against a draft and take effect when it is
              published — <Link href="/admin?tab=governance">start one in Admin</Link>.
            </p>
          ) : null}
        </fieldset>
      ) : null}

      {summaryVisible && projection ? (
        <p className={styles.provenance}>
          As of {new Date(projection.as_of).toLocaleString()} · model{" "}
          {projection.reference_model_key}@{projection.reference_model_version} · template{" "}
          {projection.template_key}@{projection.template_version} · {projection.method_version}
        </p>
      ) : null}
    </div>
  );
}
