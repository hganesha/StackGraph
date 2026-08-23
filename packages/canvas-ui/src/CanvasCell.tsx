"use client";

import { forwardRef } from "react";
import type { CanvasPolicyIntent } from "@stackgraph/shared";
import { CellIcon } from "./icons";
import { OccupantChip } from "./OccupantChip";
import { PostureMeter } from "./PostureMeter";
import type { ResolvedCell } from "./layout";
import {
  APPLICABILITY_LABEL,
  CELL_STATE_DESCRIPTION,
  CELL_STATE_LABEL,
  COMPARISON_LABEL,
  COMPARISON_TONE,
  OBSERVATION_LABEL,
  POLICY_LABEL,
  POSTURE_LABEL,
  POSTURE_TONE,
} from "./vocabulary";
import styles from "./canvas.module.css";

/** How many occupants a cell shows before it collapses into a count. */
const VISIBLE_OCCUPANTS = 4;

export type CanvasEmphasis = "posture" | "conformance" | "coverage" | "none";
export type CanvasMode = "read" | "govern" | "compare";

export interface CanvasCellProps {
  cell: ResolvedCell;
  mode: CanvasMode;
  emphasis: CanvasEmphasis;
  density: "comfortable" | "compact";
  selected: boolean;
  tabbable: boolean;
  /** Aspect lens is active and this cell is not in it. Dimmed, never removed (spec §5.4). */
  dimmed: boolean;
  columns: number;
  rowIndex: number;
  columnIndex: number;
  onSelect: (cellKey: string) => void;
  onSelectOccupant?: (technologyId: string, cellKey: string) => void;
  onPolicyIntent?: (intent: CanvasPolicyIntent) => void;
  onFocusCell: (flatIndex: number) => void;
}

/**
 * Emphasis picks which single signal drives the cell's tone. Every emphasis renders
 * the same content; only the tone and the leading status line change, so switching
 * emphasis never hides information (spec §9.2, §11.2).
 */
function emphasisSignal(cell: ResolvedCell, emphasis: CanvasEmphasis) {
  const { projection, comparison } = cell;
  if (emphasis === "conformance" && comparison) {
    return {
      tone: COMPARISON_TONE[comparison.status],
      label: COMPARISON_LABEL[comparison.status],
      detail: comparison.status_reason,
    };
  }
  if (emphasis === "conformance") {
    const governed = projection.policy?.governed ?? false;
    return {
      tone: governed ? ("neutral" as const) : ("quiet" as const),
      label: governed ? "Governed" : "Ungoverned",
      detail: governed
        ? `${projection.policy?.decisions.length ?? 0} target decisions recorded.`
        : "No target decision exists for this concern.",
    };
  }
  if (emphasis === "posture") {
    const band = projection.measures?.posture_band ?? null;
    return {
      tone: band ? POSTURE_TONE[band] : ("quiet" as const),
      label: band ? `${POSTURE_LABEL[band]} · ${CELL_STATE_LABEL[projection.state]}` : CELL_STATE_LABEL[projection.state],
      detail: projection.state_reason,
    };
  }
  if (emphasis === "coverage") {
    const applicability = projection.expectation.applicability;
    const shortfall =
      projection.state === "EMPTY" && (applicability === "REQUIRED" || applicability === "RECOMMENDED");
    return {
      tone: shortfall ? ("caution" as const) : projection.state === "POPULATED" ? ("positive" as const) : ("quiet" as const),
      label: `${APPLICABILITY_LABEL[applicability]} · ${CELL_STATE_LABEL[projection.state]}`,
      detail: projection.state_reason,
    };
  }
  return { tone: "neutral" as const, label: CELL_STATE_LABEL[projection.state], detail: projection.state_reason };
}

export const CanvasCell = forwardRef<HTMLDivElement, CanvasCellProps>(function CanvasCell(
  {
    cell,
    mode,
    emphasis,
    density,
    selected,
    tabbable,
    dimmed,
    rowIndex,
    columnIndex,
    onSelect,
    onSelectOccupant,
    onPolicyIntent,
    onFocusCell,
  },
  ref,
) {
  const { definition, projection, comparison } = cell;
  const state = projection.state;
  const signal = emphasisSignal(cell, emphasis);
  // Packages, not resolved versions: a cell shows what is in use, and three Reacts is
  // one thing in use, not three.
  const groups = projection.occupant_groups;
  const visible = groups.slice(0, density === "compact" ? 3 : VISIBLE_OCCUPANTS);
  const overflow = groups.length - visible.length;
  const observation = projection.observation;
  const headingId = `canvas-cell-${cell.key}`;

  // The accessible name carries everything the tone conveys, in order, so a screen
  // reader hears the same summary a sighted reader sees (spec §11.2).
  const accessibleSummary = [
    definition.label,
    CELL_STATE_LABEL[state],
    APPLICABILITY_LABEL[projection.expectation.applicability],
    projection.measures?.posture_band ? `posture ${projection.measures.posture_band.toLowerCase().replace("_", " ")}` : "not scored",
    comparison ? COMPARISON_LABEL[comparison.status].toLowerCase() : null,
    groups.length
      ? `${groups.length} package${groups.length === 1 ? "" : "s"}${
          projection.occupant_total > groups.length
            ? `, ${projection.occupant_total} resolved versions`
            : ""
        }`
      : null,
  ]
    .filter(Boolean)
    .join(", ");

  return (
    <div
      ref={ref}
      role="gridcell"
      aria-rowindex={rowIndex}
      aria-colindex={columnIndex}
      aria-selected={selected}
      aria-label={accessibleSummary}
      aria-describedby={`${headingId}-reason`}
      tabIndex={tabbable ? 0 : -1}
      data-cell-key={cell.key}
      data-state={state}
      data-tone={signal.tone}
      className={[
        styles.cell,
        styles[`cellState-${state}`],
        styles[`tone-${signal.tone}`],
        selected ? styles.cellSelected : "",
        dimmed ? styles.cellDimmed : "",
        density === "compact" ? styles.cellCompact : "",
        cell.span > 1 ? styles[`span-${cell.span}`] : "",
      ]
        .filter(Boolean)
        .join(" ")}
      onClick={() => onSelect(cell.key)}
      onFocus={() => onFocusCell(cell.flatIndex)}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onSelect(cell.key);
        }
      }}
    >
      <div className={styles.cellHead}>
        <span className={styles.cellGlyph}>
          <CellIcon name={definition.icon} domainKey={definition.domain_key} size={density === "compact" ? 14 : 16} />
        </span>
        <h4 className={styles.cellTitle} id={headingId}>
          {definition.label}
        </h4>
        {projection.expectation.applicability === "REQUIRED" ? (
          <span className={styles.requiredFlag}>Required</span>
        ) : null}
      </div>

      <p className={styles.cellStatus}>
        <span className={`${styles.statusDot} ${styles[`tone-${signal.tone}`]}`} aria-hidden="true" />
        {/* The state is explained on hover rather than spelled out in the cell: the
            distinction between "none found" and "not observed" is the one readers most
            often miss, and there is no room to make it in a chip. */}
        <span className={styles.statusLabel} title={CELL_STATE_DESCRIPTION[state]}>
          {signal.label}
        </span>
      </p>

      {state === "POPULATED" ? (
        <>
          <ul className={styles.occupants}>
            {visible.map((group) => (
              <li key={group.key}>
                <OccupantChip
                  group={group}
                  cellKey={cell.key}
                  onSelect={onSelectOccupant}
                  compact={density === "compact"}
                />
              </li>
            ))}
            {overflow > 0 ? (
              <li>
                <span className={styles.overflow}>+{overflow} more</span>
              </li>
            ) : null}
          </ul>
          <div className={styles.cellFoot}>
            <PostureMeter measures={projection.measures} labelled={density !== "compact"} />
            {projection.insight_refs.length ? (
              <span className={styles.insightFlag}>
                {projection.insight_refs.length} insight{projection.insight_refs.length === 1 ? "" : "s"}
              </span>
            ) : null}
          </div>
        </>
      ) : (
        <div className={styles.cellVacant}>
          <p className={styles.vacantReason} id={`${headingId}-reason`}>
            {projection.state_reason}
          </p>
          {state === "UNOBSERVED" ? (
            <p className={styles.observationNote}>
              Observation {OBSERVATION_LABEL[observation.status].toLowerCase()}
              {observation.subjects_in_scope
                ? ` · ${observation.subjects_observed} of ${observation.subjects_in_scope} subjects`
                : ""}
            </p>
          ) : null}
        </div>
      )}

      {state === "POPULATED" ? (
        <p className={styles.visuallyHidden} id={`${headingId}-reason`}>
          {projection.state_reason} {CELL_STATE_DESCRIPTION[state]}
        </p>
      ) : null}

      {mode === "govern" && onPolicyIntent ? (
        <div className={styles.governBar}>
          <button
            type="button"
            className={styles.governAction}
            onClick={(event) => {
              event.stopPropagation();
              onPolicyIntent({ kind: "EDIT_POLICY_DETAILS", cell_key: cell.key });
            }}
          >
            {projection.policy?.governed ? "Edit target" : "Set target"}
          </button>
          {projection.policy?.governed ? (
            <span className={styles.governSummary}>
              {projection.policy.decisions.filter((decision) => decision.decision === "PREFERRED").length} preferred
              {projection.policy.decisions.some((decision) => decision.decision === "PROHIBITED")
                ? ` · ${projection.policy.decisions.filter((d) => d.decision === "PROHIBITED").length} ${POLICY_LABEL.PROHIBITED.toLowerCase()}`
                : ""}
            </span>
          ) : null}
        </div>
      ) : null}
    </div>
  );
});
