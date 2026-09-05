"use client";

import { useMemo, useState } from "react";
import { COMPARISON_LABEL, COMPARISON_TONE, type CanvasTone } from "@stackgraph/canvas-ui";
import { IconDrift } from "@stackgraph/design-system";
import type { CanvasComparisonCellStatus, CanvasComparisonView } from "@stackgraph/shared";
import styles from "./architecture.module.css";

/**
 * The whole comparison as one 100%-width band.
 *
 * "You are 71% aligned to your own standard, 6% in breach, and 12% unjudgeable" is a
 * board-level number nobody else in this market can produce, because nobody else holds
 * a governed target model *and* the observed estate in one object. Today that number
 * exists implicitly across forty cells and is never stated (recommendations R6).
 *
 * `UNEVALUABLE` stays quiet, never red. `vocabulary.ts` is explicit that an incomplete
 * observation must not read as non-conformance, and a stacked band is the easiest place
 * in the product to break that rule by accident — a grey segment beside a red one is
 * the difference between "we could not check" and "you are in breach".
 */
const ORDER: CanvasComparisonCellStatus[] = [
  "ALIGNED",
  "PREFERRED_IN_USE",
  "ALLOWED_IN_USE",
  "DISCOURAGED_IN_USE",
  "PROHIBITED_IN_USE",
  "REQUIRED_ABSENT",
  "UNGOVERNED",
  "NOT_APPLICABLE",
  "UNEVALUABLE",
];

/** Under this share a segment is unreadable, so it folds into "+n other". */
const COLLAPSE_BELOW = 0.04;

interface Segment {
  status: CanvasComparisonCellStatus;
  label: string;
  tone: CanvasTone;
  count: number;
  share: number;
}

export function ConformanceRibbon({ comparison }: { comparison: CanvasComparisonView }) {
  const [expanded, setExpanded] = useState(false);

  const { segments, collapsed, total } = useMemo(() => {
    const counts = new Map<CanvasComparisonCellStatus, number>();
    for (const cell of comparison.cells) {
      counts.set(cell.status, (counts.get(cell.status) ?? 0) + 1);
    }
    const totalCells = comparison.cells.length;
    const all: Segment[] = ORDER.filter((status) => (counts.get(status) ?? 0) > 0).map((status) => ({
      status,
      label: COMPARISON_LABEL[status],
      tone: COMPARISON_TONE[status],
      count: counts.get(status) ?? 0,
      share: totalCells > 0 ? (counts.get(status) ?? 0) / totalCells : 0,
    }));
    if (expanded) return { segments: all, collapsed: [] as Segment[], total: totalCells };
    return {
      segments: all.filter((segment) => segment.share >= COLLAPSE_BELOW),
      collapsed: all.filter((segment) => segment.share < COLLAPSE_BELOW),
      total: totalCells,
    };
  }, [comparison.cells, expanded]);

  if (!total) return null;

  const collapsedCount = collapsed.reduce((sum, segment) => sum + segment.count, 0);
  const collapsedShare = total > 0 ? collapsedCount / total : 0;
  const aligned = segments.find((segment) => segment.status === "ALIGNED");
  const prohibited = segments.find((segment) => segment.status === "PROHIBITED_IN_USE");
  const unevaluable = segments.find((segment) => segment.status === "UNEVALUABLE");

  const pct = (share: number) => Math.round(share * 100);
  const sentence = [
    aligned ? `${pct(aligned.share)}% matches your standard` : null,
    prohibited ? `${pct(prohibited.share)}% is in breach` : null,
    unevaluable ? `${pct(unevaluable.share)}% cannot be judged` : null,
  ]
    .filter(Boolean)
    .join(", ");

  return (
    <section className={styles.ribbon} aria-labelledby="conformance-ribbon-heading">
      <header className={styles.ribbonHead}>
        <h3 id="conformance-ribbon-heading">
          <IconDrift size={16} /> Across {total} area{total === 1 ? "" : "s"}
        </h3>
        {sentence ? <p className={styles.ribbonSentence}>{sentence}.</p> : null}
      </header>

      {/* The band is decoration: it carries no label a reader cannot get from the list
          below it, and it holds no controls. Keeping it out of the accessibility tree
          means the counts are announced once, as text, in the legend — rather than
          twice, once as a summarised image and once as a list. */}
      <div className={styles.ribbonTrack} aria-hidden="true">
        {segments.map((segment) => (
          <span
            key={segment.status}
            className={`${styles.ribbonSegment} ${styles[`ribbonTone-${segment.tone}`]}`}
            style={{ inlineSize: `${segment.share * 100}%` }}
            title={`${segment.label} · ${segment.count} of ${total}`}
          >
            <span className={`${styles.ribbonCount} sg-mono`}>{segment.count}</span>
          </span>
        ))}
        {collapsedCount ? (
          <span
            className={`${styles.ribbonSegment} ${styles.ribbonOther}`}
            style={{ inlineSize: `${Math.max(collapsedShare * 100, 4)}%` }}
            title={collapsed.map((segment) => `${segment.label}: ${segment.count}`).join(" · ")}
          >
            <span className={`${styles.ribbonCount} sg-mono`}>+{collapsed.length}</span>
          </span>
        ) : null}
      </div>

      {/* Every tone ships with its label, and the legend is where the counts actually
          live — the band above only shows their proportion. */}
      <ul className={styles.ribbonLegend}>
        {segments.map((segment) => (
          <li key={segment.status}>
            <span className={`${styles.ribbonSwatch} ${styles[`ribbonTone-${segment.tone}`]}`} aria-hidden="true" />
            <span>{segment.label}</span>
            <span className={`${styles.ribbonLegendCount} sg-mono`}>{segment.count}</span>
          </li>
        ))}
        {collapsedCount ? (
          <li>
            <button type="button" className={styles.ribbonExpand} onClick={() => setExpanded(true)}>
              Show {collapsed.length} smaller state{collapsed.length === 1 ? "" : "s"}
            </button>
          </li>
        ) : null}
      </ul>
    </section>
  );
}
