"use client";

import { useId, useState } from "react";
import { IconChevronDown, IconChevronRight } from "@tabler/icons-react";
import styles from "./StratumBar.module.css";

export interface StratumLayerFact {
  label: string;
  value: string;
}

export interface StratumLayer {
  key: string;
  label: string;
  /**
   * How much of this layer is filled in, 0..1. `null` means nothing measures it yet —
   * which is a different statement from zero, and is drawn differently.
   */
  ratio: number | null;
  /** The one-line reading beneath the band: "9 of 12 repositories scanned". */
  reading: string;
  /** Required when `ratio` is null: why there is no measure. */
  unmeasuredReason?: string;
  /** Rows shown when the bar is expanded. */
  facts?: StratumLayerFact[];
}

/**
 * The product's own metaphor, drawn.
 *
 * Every tool in this category has a coverage percentage. None of them show *which
 * layer of the stack the knowledge runs out at* — and that is the single most useful
 * thing to tell a customer in their first month, because a bar that is full at
 * Technology and thin at Business says "we know what you run, we don't yet know what
 * it is for" without anyone reading a paragraph (recommendations R4).
 *
 * Collapsed it is five hairline bands, no taller than the strip it replaced. Expanded
 * it is the per-layer drill-down, which is the natural home for the counts that used
 * to sit in four tiles above the estate fold.
 *
 * An unmeasured layer is **hatched, never empty**. "We have no measure for this yet"
 * and "there is nothing here" are different facts, and collapsing them would make the
 * bar lie in exactly the direction that flatters us.
 */
export function StratumBar({
  layers,
  weakestLayerLabel,
}: {
  layers: StratumLayer[];
  /** Named in the accessible label, so the headline is spoken, not just drawn. */
  weakestLayerLabel?: string;
}) {
  const [open, setOpen] = useState(false);
  const panelId = useId();

  const measured = layers.filter((layer) => layer.ratio != null);
  const summary = weakestLayerLabel
    ? `Estate layers. Weakest measured layer: ${weakestLayerLabel}.`
    : "Estate layers.";
  const detail = layers
    .map((layer) =>
      layer.ratio == null
        ? `${layer.label}: not measured`
        : `${layer.label}: ${Math.round(layer.ratio * 100)}%`,
    )
    .join(", ");

  return (
    <div className={styles.wrap}>
      <button
        type="button"
        className={styles.toggle}
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((value) => !value)}
        title={measured.length ? undefined : "No layer has a coverage measure yet."}
      >
        <span className={styles.chevron} aria-hidden="true">
          {open ? <IconChevronDown size={14} stroke={1.75} /> : <IconChevronRight size={14} stroke={1.75} />}
        </span>
        <span className={styles.bands} aria-hidden="true">
          {layers.map((layer) => (
            <span key={layer.key} className={styles.band}>
              <span
                className={`${styles.fill} ${layer.ratio == null ? styles.unmeasured : ""}`}
                style={layer.ratio == null ? undefined : { inlineSize: `${Math.round(layer.ratio * 100)}%` }}
              />
            </span>
          ))}
        </span>
        <span className={styles.legend} aria-hidden="true">
          {layers.map((layer) => (
            <span key={layer.key} className={styles.legendItem}>
              {layer.label}
            </span>
          ))}
        </span>
        <span className={styles.visuallyHidden}>{`${summary} ${detail}. Open for per-layer detail.`}</span>
      </button>

      {open ? (
        <div id={panelId} className={styles.panel}>
          <table className={styles.table}>
            <caption className={styles.visuallyHidden}>Estate layers, what is populated and how much is measured</caption>
            <tbody>
              {layers.map((layer) => (
                <tr key={layer.key}>
                  <th scope="row">{layer.label}</th>
                  <td className={styles.cellBand}>
                    <span className={styles.rowBand}>
                      <span
                        className={`${styles.fill} ${layer.ratio == null ? styles.unmeasured : ""}`}
                        style={layer.ratio == null ? undefined : { inlineSize: `${Math.round(layer.ratio * 100)}%` }}
                      />
                    </span>
                  </td>
                  <td className={`${styles.cellValue} sg-mono`}>
                    {layer.ratio == null ? "Not measured" : `${Math.round(layer.ratio * 100)}%`}
                  </td>
                  <td className={styles.cellReading}>
                    <span>{layer.reading}</span>
                    {layer.ratio == null && layer.unmeasuredReason ? (
                      <small className={styles.reason}>{layer.unmeasuredReason}</small>
                    ) : null}
                    {layer.facts?.length ? (
                      <small className={styles.facts}>
                        {layer.facts.map((fact) => `${fact.label} ${fact.value}`).join(" · ")}
                      </small>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  );
}
