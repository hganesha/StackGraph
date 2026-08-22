"use client";

import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type RefObject } from "react";
import type {
  ArchitectureReferenceModel,
  CanvasComparison,
  CanvasPolicyIntent,
  CanvasProjection,
  CanvasTemplate,
} from "@stackgraph/shared";
import { CanvasAspectRail } from "./CanvasAspectRail";
import { CanvasBand } from "./CanvasBand";
import type { CanvasEmphasis, CanvasMode } from "./CanvasCell";
import { ClassificationTray } from "./ClassificationTray";
import {
  ASPECT_RAIL_MIN_WIDTH,
  DEFAULT_CANVAS_WIDTH,
  effectiveColumns,
  moveFocus,
  resolveCanvas,
  type CanvasArrow,
  type ResolvedCanvas,
} from "./layout";
import styles from "./canvas.module.css";

export interface ArchitectureCanvasProps {
  template: CanvasTemplate;
  referenceModel: ArchitectureReferenceModel;
  projection: CanvasProjection;
  comparison?: CanvasComparison | null;
  mode?: CanvasMode;
  density?: "comfortable" | "compact";
  emphasis?: CanvasEmphasis;
  selectedCellKey?: string | null;
  /** Aspect lens; the host owns the value so it can survive navigation. */
  activeAspectKey?: string | null;
  onSelectCell?: (cellKey: string | null) => void;
  onSelectOccupant?: (technologyId: string, cellKey: string) => void;
  onSelectAspect?: (aspectKey: string | null) => void;
  onPolicyIntent?: (intent: CanvasPolicyIntent) => void;
}

const ARROW_KEYS = new Set(["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Home", "End"]);

/**
 * useLayoutEffect on the client, useEffect on the server, so the measurement below
 * runs before paint without warning during SSR.
 */
const useIsomorphicLayoutEffect = typeof window === "undefined" ? useEffect : useLayoutEffect;

/**
 * Measures a container so the layout responds to the space the canvas actually has,
 * not the space the window has — opening the detail panel is a reflow that never
 * changes the window size.
 *
 * Two mechanisms, deliberately:
 *  - a synchronous measurement before paint, which is what makes the first render
 *    correct. ResizeObserver alone is not enough: its callbacks are driven by the
 *    rendering lifecycle, so in a hidden or throttled document they never arrive and
 *    the grid would stay pinned to the server default, crushing four columns into a
 *    phone-width container.
 *  - the observer, for every later change.
 *
 * The initial state matches the server so hydration does not mismatch; the layout
 * effect corrects it before the browser paints.
 */
function useElementWidth(ref: RefObject<HTMLElement | null>): number {
  const [width, setWidth] = useState(DEFAULT_CANVAS_WIDTH);

  useIsomorphicLayoutEffect(() => {
    const node = ref.current;
    if (!node) return;
    const measure = () => {
      const measured = node.getBoundingClientRect().width;
      if (measured > 0) setWidth((current) => (Math.abs(current - measured) < 1 ? current : measured));
    };
    measure();
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(measure);
    observer.observe(node);
    return () => observer.disconnect();
  }, [ref]);

  return width;
}

export function ArchitectureCanvas({
  template,
  referenceModel,
  projection,
  comparison = null,
  mode = "read",
  density = "comfortable",
  emphasis = "posture",
  selectedCellKey = null,
  activeAspectKey = null,
  onSelectCell,
  onSelectOccupant,
  onSelectAspect,
  onPolicyIntent,
}: ArchitectureCanvasProps) {
  const shellRef = useRef<HTMLDivElement>(null);
  const gridRef = useRef<HTMLDivElement>(null);
  // Two measurements, because they answer different questions: the shell decides
  // where the aspect rail goes, the grid decides how many columns fit inside what is
  // left once the rail has taken its share.
  const shellWidth = useElementWidth(shellRef);
  const gridWidth = useElementWidth(gridRef);
  const cellRefs = useRef<Map<number, HTMLDivElement>>(new Map());
  const [focusedFlatIndex, setFocusedFlatIndex] = useState(0);
  // Arrow keys can outrun React's re-render when a key is held down. The ref is the
  // authority for the next move so a burst of keystrokes chains instead of all
  // resolving against the same stale index.
  const focusedRef = useRef(0);

  const nominalColumns = useMemo(
    () => Math.max(...template.bands.map((band) => band.columns), 1),
    [template],
  );
  const columns = effectiveColumns(gridWidth, nominalColumns);
  const railAsBand = shellWidth < ASPECT_RAIL_MIN_WIDTH;

  const fullResolved: ResolvedCanvas = useMemo(
    () => resolveCanvas(template, referenceModel, projection, comparison),
    [template, referenceModel, projection, comparison],
  );

  /**
   * An aspect lens dims cells rather than removing them. Comparison views may not
   * hide canonical cells (spec §5.4), and a filter that deletes half the frame turns
   * the fixed geometry into a moving one.
   */
  const resolved = fullResolved;
  const aspectMatches = useCallback(
    (cellKey: string) => {
      if (!activeAspectKey) return true;
      const cell = fullResolved.flatCells.find((entry) => entry.key === cellKey);
      return Boolean(cell?.definition.aspect_keys.includes(activeAspectKey));
    },
    [activeAspectKey, fullResolved],
  );

  const focusCell = useCallback((flatIndex: number) => {
    focusedRef.current = flatIndex;
    setFocusedFlatIndex(flatIndex);
    cellRefs.current.get(flatIndex)?.focus();
  }, []);

  const noteFocus = useCallback((flatIndex: number) => {
    focusedRef.current = flatIndex;
    setFocusedFlatIndex(flatIndex);
  }, []);

  const onKeyDown = useCallback(
    (event: React.KeyboardEvent<HTMLDivElement>) => {
      if (event.key === "Escape") {
        if (selectedCellKey) {
          event.preventDefault();
          onSelectCell?.(null);
        }
        return;
      }
      if (!ARROW_KEYS.has(event.key)) return;
      const next = moveFocus(resolved.bands, columns, focusedRef.current, event.key as CanvasArrow);
      if (next === null) return;
      event.preventDefault();
      focusCell(next);
    },
    [columns, focusCell, onSelectCell, resolved.bands, selectedCellKey],
  );

  // Keep the roving tabindex on a cell that still exists after a projection swap.
  useEffect(() => {
    if (!resolved.flatCells.some((cell) => cell.flatIndex === focusedFlatIndex)) {
      const fallback = resolved.flatCells[0]?.flatIndex ?? 0;
      focusedRef.current = fallback;
      setFocusedFlatIndex(fallback);
    }
  }, [focusedFlatIndex, resolved.flatCells]);

  const summary = projection.summary;

  return (
    <div ref={shellRef} className={`${styles.canvas} ${railAsBand ? styles.canvasStacked : ""}`}>
      <div className={styles.canvasMain}>
        <p className={styles.canvasCaption} id="canvas-caption">
          {summary.cells_total} canonical cells · {summary.by_state.POPULATED} populated ·{" "}
          {summary.by_state.EMPTY} none found · {summary.by_state.UNOBSERVED} not observed ·{" "}
          {summary.by_state.NOT_APPLICABLE} not applicable · {summary.by_state.UNBOUND} not yet modelled
          {activeAspectKey ? " · aspect lens active" : ""}
        </p>

        {/*
          The wrapper is not itself a grid: each band is (see CanvasBand). It owns the
          keydown handler so arrow keys cross band boundaries as one continuous
          surface, and it is the element measured for the column count.
        */}
        <div
          ref={gridRef}
          className={`${styles.grid} ${activeAspectKey ? styles.gridLensed : ""}`}
          onKeyDown={onKeyDown}
        >
          {resolved.bands.map((band) => (
            <div key={band.domainKey} className={styles.bandSlot}>
              <CanvasBand
                band={band}
                columns={columns}
                mode={mode}
                emphasis={emphasis}
                density={density}
                selectedCellKey={selectedCellKey}
                focusedFlatIndex={focusedFlatIndex}
                isDimmed={(cellKey) => !aspectMatches(cellKey)}
                cellRefs={cellRefs}
                onSelect={(cellKey) => onSelectCell?.(cellKey === selectedCellKey ? null : cellKey)}
                onSelectOccupant={onSelectOccupant}
                onPolicyIntent={onPolicyIntent}
                onFocusCell={noteFocus}
              />
            </div>
          ))}
        </div>

        <ClassificationTray
          tray={projection.classification_tray}
          resolved={resolved}
          onSelectOccupant={onSelectOccupant}
          onPolicyIntent={onPolicyIntent}
          onSelectCell={(cellKey) => onSelectCell?.(cellKey)}
        />
      </div>

      <CanvasAspectRail
        aspects={referenceModel.aspects}
        resolved={resolved}
        projection={projection}
        activeAspect={activeAspectKey}
        onSelectAspect={(aspectKey) => onSelectAspect?.(aspectKey)}
        variant={railAsBand ? "band" : "rail"}
      />
    </div>
  );
}
