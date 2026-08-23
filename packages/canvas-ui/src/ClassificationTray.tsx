"use client";

import { useState } from "react";
import type {
  CanvasClassificationTrayView,
  CanvasPolicyIntent,
  CanvasTrayReason,
} from "@stackgraph/shared";
import type { ResolvedCanvas } from "./layout";
import styles from "./canvas.module.css";

type TrayTab = CanvasTrayReason | "CONTRACT";

const TAB_LABEL: Record<TrayTab, string> = {
  UNCLASSIFIED: "Unclassified",
  AMBIGUOUS: "Ambiguous",
  UNRESOLVED_POLICY: "Unresolved policies",
  FILTERED: "Hidden by filters",
  CONTRACT: "Contract mismatches",
};

const TAB_NOTE: Record<TrayTab, string> = {
  UNCLASSIFIED: "Observed, but no binding matched. These are gaps in classification, not in the estate.",
  AMBIGUOUS: "Matched more than one mutually exclusive binding. A technology may legitimately occupy several cells; the counts must not double-count it.",
  UNRESOLVED_POLICY: "Tenant policy that resolves to no canonical or extension cell. Assigning one moves its decisions unchanged.",
  FILTERED: "Withheld by the active facets. Listed so the count is never silently lost.",
  CONTRACT: "The template, reference model, and projection disagree about which cells exist.",
};

const REASON_ORDER: CanvasTrayReason[] = ["UNCLASSIFIED", "AMBIGUOUS", "UNRESOLVED_POLICY", "FILTERED"];

/**
 * Everything the projection could not place, rendered where it cannot be missed
 * (spec §6.3: the canvas must never silently drop an observation).
 *
 * Two things are deliberately loud here. The server's own counts are shown rather
 * than the length of the item list, because a truncated list under-reports; and when
 * the server says it truncated, that is stated rather than inferred from arithmetic.
 * The tray also carries contract mismatches the renderer detected while resolving.
 */
export function ClassificationTray({
  tray,
  resolved,
  onSelectOccupant,
  onPolicyIntent,
}: {
  tray: CanvasClassificationTrayView;
  resolved: ResolvedCanvas;
  onSelectOccupant?: (technologyId: string, cellKey: string) => void;
  onPolicyIntent?: (intent: CanvasPolicyIntent) => void;
}) {
  const contractIssues =
    resolved.missingFromProjection.length +
    resolved.missingFromTemplate.length +
    resolved.unknownCellKeys.length;

  const tabs: Array<{ id: TrayTab; count: number }> = [
    ...REASON_ORDER.filter((reason) => tray.counts[reason] > 0).map((reason) => ({
      id: reason as TrayTab,
      count: tray.counts[reason],
    })),
    ...(contractIssues ? [{ id: "CONTRACT" as TrayTab, count: contractIssues }] : []),
  ];

  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState<TrayTab>(tabs[0]?.id ?? "UNCLASSIFIED");

  if (!tabs.length) return null;

  const items = tab === "CONTRACT" ? [] : tray.byReason[tab as CanvasTrayReason];
  const listedShortOfCount = tab !== "CONTRACT" && items.length < tray.counts[tab as CanvasTrayReason];

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
          {tray.total} observation{tray.total === 1 ? "" : "s"}
          {tray.truncated ? " · list truncated" : ""}
        </span>
      </button>

      {open ? (
        <div className={styles.trayBody} id="canvas-tray-body">
          {tray.truncated ? (
            <p className={styles.trayWarning} role="status">
              The server truncated this list. The counts above are complete; the rows below are not.
            </p>
          ) : null}

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
                {TAB_LABEL[entry.id]} <span className={styles.trayTabCount}>{entry.count}</span>
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
            <p className={styles.trayNote}>{TAB_NOTE[tab]}</p>

            {tab === "CONTRACT" ? (
              <ul className={styles.trayList}>
                {resolved.missingFromProjection.map((key) => (
                  <li key={`mp:${key}`}>
                    <div className={styles.trayRow}>
                      <span className={styles.trayRowName}>{key}</span>
                      <span className={styles.trayRowMeta}>laid out, not projected</span>
                      <span className={styles.trayRowReason}>
                        The template lays this cell out but the projection did not return it. The canvas
                        omitted it rather than inventing a state.
                      </span>
                    </div>
                  </li>
                ))}
                {resolved.missingFromTemplate.map((key) => (
                  <li key={`mt:${key}`}>
                    <div className={styles.trayRow}>
                      <span className={styles.trayRowName}>{key}</span>
                      <span className={styles.trayRowMeta}>projected, not laid out</span>
                      <span className={styles.trayRowReason}>
                        Returned by the projection but absent from this template.
                      </span>
                    </div>
                  </li>
                ))}
                {resolved.unknownCellKeys.map((key) => (
                  <li key={`uk:${key}`}>
                    <div className={styles.trayRow}>
                      <span className={styles.trayRowName}>{key}</span>
                      <span className={styles.trayRowMeta}>no definition</span>
                      <span className={styles.trayRowReason}>
                        No definition for this key in the active reference model.
                      </span>
                    </div>
                  </li>
                ))}
              </ul>
            ) : (
              <>
                <ul className={styles.trayList}>
                  {items.map((item) => {
                    const openable = tab !== "FILTERED" && Boolean(onSelectOccupant);
                    const body = (
                      <>
                        <span className={styles.trayRowName}>{item.entity.name}</span>
                        <span className={styles.trayRowMeta}>{item.entity.kind}</span>
                        <span className={styles.trayRowReason}>{item.detail}</span>
                      </>
                    );
                    return (
                      <li key={`${item.reason}:${item.entity.id}`}>
                        {openable ? (
                          <button
                            type="button"
                            className={styles.trayRow}
                            onClick={() => onSelectOccupant?.(item.entity.id, "")}
                          >
                            {body}
                          </button>
                        ) : (
                          <div className={styles.trayRow}>{body}</div>
                        )}
                        {tab === "UNRESOLVED_POLICY" && onPolicyIntent ? (
                          <button
                            type="button"
                            className={styles.trayAction}
                            onClick={() =>
                              onPolicyIntent({
                                kind: "RESOLVE_UNRESOLVED_POLICY",
                                policy_key: item.entity.id,
                                cell_key: null,
                              })
                            }
                          >
                            Assign a cell
                            <span className={styles.visuallyHidden}> for {item.entity.name}</span>
                          </button>
                        ) : null}
                      </li>
                    );
                  })}
                </ul>
                {listedShortOfCount ? (
                  <p className={styles.trayNote}>
                    Showing {items.length} of {tray.counts[tab as CanvasTrayReason]}.
                  </p>
                ) : null}
              </>
            )}
          </div>
        </div>
      ) : null}
    </section>
  );
}
