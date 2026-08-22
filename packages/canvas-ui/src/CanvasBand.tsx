"use client";

import { useMemo, type RefObject } from "react";
import type { CanvasPolicyIntent } from "@stackgraph/shared";
import { CanvasCell, type CanvasEmphasis, type CanvasMode } from "./CanvasCell";
import type { ResolvedBand, ResolvedCell } from "./layout";
import styles from "./canvas.module.css";

export interface CanvasBandProps {
  band: ResolvedBand;
  columns: number;
  mode: CanvasMode;
  emphasis: CanvasEmphasis;
  density: "comfortable" | "compact";
  selectedCellKey: string | null;
  focusedFlatIndex: number;
  isDimmed: (cellKey: string) => boolean;
  cellRefs: RefObject<Map<number, HTMLDivElement>>;
  onSelect: (cellKey: string) => void;
  onSelectOccupant?: (technologyId: string, cellKey: string) => void;
  onPolicyIntent?: (intent: CanvasPolicyIntent) => void;
  onFocusCell: (flatIndex: number) => void;
}

/**
 * One architecture domain: a header block plus a real ARIA grid.
 *
 * Each band is its own `role="grid"` rather than the whole canvas being one, because
 * a grid's children must be rows and a canvas-wide grid would have to put band
 * headers inside the grid structure. Per-band grids also make `aria-rowcount` honest.
 *
 * Rows are explicit `role="row"` elements that each lay out one row of the CSS grid.
 * A single wrapping grid with `display: contents` rows would render identically but
 * relies on assistive technology handling `display: contents` correctly; explicit
 * per-row grids do not. The column count is passed in rather than read from CSS, so
 * the ARIA indices always describe the geometry actually rendered (spec §11.1).
 */
export function CanvasBand({
  band,
  columns,
  mode,
  emphasis,
  density,
  selectedCellKey,
  focusedFlatIndex,
  isDimmed,
  cellRefs,
  onSelect,
  onSelectOccupant,
  onPolicyIntent,
  onFocusCell,
}: CanvasBandProps) {
  const headingId = `canvas-band-${band.domainKey}`;
  const populated = band.cells.filter((cell) => cell.projection.state === "POPULATED").length;
  const unobserved = band.cells.filter((cell) => cell.projection.state === "UNOBSERVED").length;

  const rows = useMemo(() => {
    const chunked: ResolvedCell[][] = [];
    for (let index = 0; index < band.cells.length; index += columns) {
      chunked.push(band.cells.slice(index, index + columns));
    }
    return chunked;
  }, [band.cells, columns]);

  return (
    <section className={styles.band} aria-labelledby={headingId}>
      <header className={styles.bandHead}>
        <h3 className={styles.bandTitle} id={headingId}>
          {band.label}
        </h3>
        {band.question ? <p className={styles.bandQuestion}>{band.question}</p> : null}
        <p className={styles.bandCounts}>
          {populated} of {band.cells.length} populated
          {unobserved ? ` · ${unobserved} not observed` : ""}
        </p>
      </header>
      <div
        role="grid"
        aria-labelledby={headingId}
        aria-readonly={mode === "read"}
        aria-rowcount={rows.length}
        aria-colcount={columns}
        className={styles.bandGrid}
      >
        {rows.map((row, rowIndex) => (
          <div
            key={row[0]?.key ?? rowIndex}
            role="row"
            aria-rowindex={rowIndex + 1}
            className={styles.bandRow}
            style={{ "--canvas-columns": columns } as React.CSSProperties}
          >
            {row.map((cell, columnIndex) => (
              <CanvasCell
                key={cell.key}
                ref={(node) => {
                  if (node) cellRefs.current?.set(cell.flatIndex, node);
                  else cellRefs.current?.delete(cell.flatIndex);
                }}
                cell={cell}
                mode={mode}
                emphasis={emphasis}
                density={density}
                columns={columns}
                rowIndex={rowIndex + 1}
                columnIndex={columnIndex + 1}
                selected={selectedCellKey === cell.key}
                dimmed={isDimmed(cell.key)}
                tabbable={focusedFlatIndex === cell.flatIndex}
                onSelect={onSelect}
                onSelectOccupant={onSelectOccupant}
                onPolicyIntent={onPolicyIntent}
                onFocusCell={onFocusCell}
              />
            ))}
          </div>
        ))}
      </div>
    </section>
  );
}
