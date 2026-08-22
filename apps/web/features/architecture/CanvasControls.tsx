"use client";

import type { CanvasEmphasis, CanvasMode } from "@stackgraph/canvas-ui";
import type { CanvasProjection } from "@stackgraph/shared";
import styles from "./architecture.module.css";

export type CanvasView = "actual" | "target" | "drift";

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
  canReview,
  projection,
  summaryVisible = true,
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
  canReview: boolean;
  projection: CanvasProjection | null;
  summaryVisible?: boolean;
}) {
  return (
    <div className={styles.controls}>
      <fieldset className={styles.controlGroup}>
        <legend className={styles.controlLegend}>View</legend>
        <div className={styles.segmented} role="radiogroup" aria-label="Canvas view">
          {(
            [
              ["actual", "Actual", true],
              ["target", "Target", canReview],
              ["drift", "Drift", canReview],
            ] as Array<[CanvasView, string, boolean]>
          ).map(([value, label, allowed]) => (
            <button
              key={value}
              type="button"
              role="radio"
              aria-checked={view === value}
              disabled={!allowed}
              title={allowed ? undefined : "Target and drift require review access."}
              className={`${styles.segment} ${view === value ? styles.segmentActive : ""}`}
              onClick={() => onViewChange(value)}
            >
              {label}
            </button>
          ))}
        </div>
      </fieldset>

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
              onChange={(event) => onModeChange(event.target.checked ? "govern" : "read")}
            />
            <span>Govern target</span>
          </label>
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
