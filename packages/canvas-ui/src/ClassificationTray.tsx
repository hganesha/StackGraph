"use client";

import { useState } from "react";
import type { CanvasClassificationTray, CanvasPolicyIntent } from "@stackgraph/shared";
import type { ResolvedCanvas } from "./layout";
import styles from "./canvas.module.css";

type TrayTab = "unclassified" | "ambiguous" | "policies" | "contract";

/**
 * Everything the projection could not place, rendered where it cannot be missed.
 * The canvas must never silently drop an observation (spec §6.3), so the tray also
 * carries contract mismatches the renderer detected while resolving: canonical cells
 * laid out but not projected, projected but not laid out, or referencing an unknown
 * definition.
 */
export function ClassificationTray({
  tray,
  resolved,
  onSelectOccupant,
  onPolicyIntent,
  onSelectCell,
}: {
  tray: CanvasClassificationTray;
  resolved: ResolvedCanvas;
  onSelectOccupant?: (technologyId: string, cellKey: string) => void;
  onPolicyIntent?: (intent: CanvasPolicyIntent) => void;
  onSelectCell?: (cellKey: string) => void;
}) {
  const contractIssues =
    resolved.missingFromProjection.length +
    resolved.missingFromTemplate.length +
    resolved.unknownCellKeys.length;

  const tabs: Array<{ id: TrayTab; label: string; count: number }> = [
    { id: "unclassified", label: "Unclassified", count: tray.unclassified_technologies.length },
    { id: "ambiguous", label: "Ambiguous", count: tray.ambiguous_observations.length },
    { id: "policies", label: "Unresolved policies", count: tray.unresolved_policies.length },
    ...(contractIssues ? [{ id: "contract" as const, label: "Contract mismatches", count: contractIssues }] : []),
  ];
  const total = tabs.reduce((sum, tab) => sum + tab.count, 0) + tray.filtered_out_total;
  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState<TrayTab>("unclassified");

  if (total === 0) return null;

  return (
    <section className={styles.tray} aria-labelledby="canvas-tray-heading">
      <button
        type="button"
        className={styles.trayToggle}
        aria-expanded={open}
        aria-controls="canvas-tray-body"
        onClick={() => setOpen((value) => !value)}
      >
        <h3 className={styles.trayTitle} id="canvas-tray-heading">
          Not placed on the canvas
        </h3>
        <span className={styles.trayCount}>
          {total} observation{total === 1 ? "" : "s"}
          {tray.filtered_out_total ? ` · ${tray.filtered_out_total} hidden by filters` : ""}
        </span>
      </button>

      {open ? (
        <div className={styles.trayBody} id="canvas-tray-body">
          <div className={styles.trayTabs} role="tablist" aria-label="Unplaced observation categories">
            {tabs.map((entry) => (
              <button
                key={entry.id}
                type="button"
                role="tab"
                id={`canvas-tray-tab-${entry.id}`}
                aria-selected={tab === entry.id}
                aria-controls={`canvas-tray-panel-${entry.id}`}
                tabIndex={tab === entry.id ? 0 : -1}
                className={`${styles.trayTab} ${tab === entry.id ? styles.trayTabActive : ""}`}
                onClick={() => setTab(entry.id)}
              >
                {entry.label} <span className={styles.trayTabCount}>{entry.count}</span>
              </button>
            ))}
          </div>

          <div
            role="tabpanel"
            id={`canvas-tray-panel-${tab}`}
            aria-labelledby={`canvas-tray-tab-${tab}`}
            className={styles.trayPanel}
            tabIndex={0}
          >
            {tab === "unclassified" ? (
              <ul className={styles.trayList}>
                {tray.unclassified_technologies.map((entry) => (
                  <li key={entry.technology.id}>
                    <button
                      type="button"
                      className={styles.trayRow}
                      onClick={() => onSelectOccupant?.(entry.technology.id, "")}
                    >
                      <span className={styles.trayRowName}>{entry.technology.name}</span>
                      <span className={styles.trayRowMeta}>{entry.ecosystem ?? "unknown ecosystem"}</span>
                      <span className={styles.trayRowReason}>{entry.reason}</span>
                    </button>
                  </li>
                ))}
              </ul>
            ) : null}

            {tab === "ambiguous" ? (
              <ul className={styles.trayList}>
                {tray.ambiguous_observations.map((entry) => (
                  <li key={entry.technology.id}>
                    <div className={styles.trayRow}>
                      <span className={styles.trayRowName}>{entry.technology.name}</span>
                      <span className={styles.trayRowMeta}>
                        {entry.candidate_cell_keys.map((key) => (
                          <button
                            key={key}
                            type="button"
                            className={styles.trayLink}
                            onClick={() => onSelectCell?.(key)}
                          >
                            {resolved.flatCells.find((cell) => cell.key === key)?.definition.label ?? key}
                          </button>
                        ))}
                      </span>
                      <span className={styles.trayRowReason}>{entry.reason}</span>
                    </div>
                  </li>
                ))}
              </ul>
            ) : null}

            {tab === "policies" ? (
              <ul className={styles.trayList}>
                {tray.unresolved_policies.map((entry) => (
                  <li key={entry.policy_key}>
                    <div className={styles.trayRow}>
                      <span className={styles.trayRowName}>{entry.label}</span>
                      <span className={styles.trayRowMeta}>
                        {entry.source.toLowerCase()} · {entry.technology_count} technolog
                        {entry.technology_count === 1 ? "y" : "ies"}
                      </span>
                      <span className={styles.trayRowReason}>{entry.reason}</span>
                      {onPolicyIntent ? (
                        <button
                          type="button"
                          className={styles.trayAction}
                          onClick={() =>
                            onPolicyIntent({
                              kind: "RESOLVE_UNRESOLVED_POLICY",
                              policy_key: entry.policy_key,
                              cell_key: null,
                            })
                          }
                        >
                          Assign a cell
                        </button>
                      ) : null}
                    </div>
                  </li>
                ))}
              </ul>
            ) : null}

            {tab === "contract" ? (
              <ul className={styles.trayList}>
                {resolved.missingFromProjection.map((key) => (
                  <li key={`mp:${key}`}>
                    <div className={styles.trayRow}>
                      <span className={styles.trayRowName}>{key}</span>
                      <span className={styles.trayRowReason}>
                        Laid out by the template but absent from the projection. The canvas omitted it rather than
                        inventing a state.
                      </span>
                    </div>
                  </li>
                ))}
                {resolved.missingFromTemplate.map((key) => (
                  <li key={`mt:${key}`}>
                    <div className={styles.trayRow}>
                      <span className={styles.trayRowName}>{key}</span>
                      <span className={styles.trayRowReason}>
                        Returned by the projection but not laid out by this template.
                      </span>
                    </div>
                  </li>
                ))}
                {resolved.unknownCellKeys.map((key) => (
                  <li key={`uk:${key}`}>
                    <div className={styles.trayRow}>
                      <span className={styles.trayRowName}>{key}</span>
                      <span className={styles.trayRowReason}>
                        No definition for this key in the active reference model.
                      </span>
                    </div>
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
        </div>
      ) : null}
    </section>
  );
}
