import type {
  ArchitectureCellView,
  ArchitectureReferenceModelView,
  CanvasBandLayoutModel,
  CanvasCellComparisonView,
  CanvasCellProjectionView,
  CanvasComparisonView,
  CanvasProjectionView,
  CanvasTemplateModel,
} from "@stackgraph/shared";

/**
 * Effective column counts.
 *
 * Breakpoints are measured against the CONTAINER, not the viewport: opening the
 * detail panel narrows the grid without changing the window, and a viewport-based
 * count would leave four columns crammed into half the width. The measured count
 * drives both the CSS grid and the ARIA grid indices, so the announced geometry can
 * never drift from the visual one after a reflow (spec §11.1).
 */
export const CANVAS_BREAKPOINTS = [
  { minWidth: 1120, columns: null },  // null = honour the template's nominal count
  { minWidth: 840, columns: 3 },
  { minWidth: 560, columns: 2 },
  { minWidth: 0, columns: 1 },
] as const;

/**
 * Below this container width the aspect rail reflows beneath the bands. Tuned so a
 * 1440px desktop inside the app shell still gets the rail beside the canvas, and the
 * grid keeps at least three columns once the rail has taken its share.
 */
export const ASPECT_RAIL_MIN_WIDTH = 1080;

/** Server-render width. Desktop, so SSR emits the full layout and hydration matches. */
export const DEFAULT_CANVAS_WIDTH = 1280;

export function effectiveColumns(containerWidth: number, templateColumns: number): number {
  const bracket = CANVAS_BREAKPOINTS.find((entry) => containerWidth >= entry.minWidth);
  const columns = bracket?.columns ?? templateColumns;
  return Math.max(1, Math.min(columns ?? templateColumns, templateColumns));
}

// ─── Resolved view model ─────────────────────────────────────────────────────
// The renderer never joins template, reference model, and projection ad hoc in JSX.
// It resolves once, here, so a cell missing from any of the three is surfaced as a
// contract error rather than silently dropped (spec §6.3: never silently drop).

export interface ResolvedCell {
  key: string;
  definition: ArchitectureCellView;
  projection: CanvasCellProjectionView;
  comparison: CanvasCellComparisonView | null;
  span: 1 | 2 | 3;
  /** Flat index across every band, used for roving-tabindex navigation. */
  flatIndex: number;
}

export interface ResolvedBand {
  domainKey: string;
  label: string;
  question: string;
  order: number;
  columns: number;
  cells: ResolvedCell[];
}

export interface ResolvedCanvas {
  bands: ResolvedBand[];
  /** Every cell in DOM/reading order, band by band. */
  flatCells: ResolvedCell[];
  /**
   * Canonical cells the template lays out but the projection did not return, or the
   * reverse. Rendered as an explicit warning: a comparison must never quietly omit a
   * canonical cell (spec §3.1, §5.4).
   */
  missingFromProjection: string[];
  missingFromTemplate: string[];
  unknownCellKeys: string[];
}

function bandOrder(template: CanvasTemplateModel): CanvasBandLayoutModel[] {
  return [...template.bands].sort((a, b) => a.order - b.order);
}

export function resolveCanvas(
  template: CanvasTemplateModel,
  referenceModel: ArchitectureReferenceModelView,
  projection: CanvasProjectionView,
  comparison?: CanvasComparisonView | null,
): ResolvedCanvas {
  const definitions = new Map(referenceModel.cells.map((cell) => [cell.key, cell]));
  const projected = new Map(projection.cells.map((cell) => [cell.cell_key, cell]));
  const compared = new Map((comparison?.cells ?? []).map((cell) => [cell.cell_key, cell]));
  const domains = new Map(referenceModel.domains.map((domain) => [domain.key, domain]));

  const laidOut = new Set<string>();
  const missingFromProjection: string[] = [];
  const unknownCellKeys: string[] = [];
  const flatCells: ResolvedCell[] = [];

  const bands: ResolvedBand[] = bandOrder(template).map((band) => {
    const domain = domains.get(band.domain_key);
    const cells: ResolvedCell[] = [];
    for (const entry of band.cells) {
      laidOut.add(entry.cell_key);
      const definition = definitions.get(entry.cell_key);
      const cellProjection = projected.get(entry.cell_key);
      if (!definition) {
        unknownCellKeys.push(entry.cell_key);
        continue;
      }
      if (!cellProjection) {
        missingFromProjection.push(entry.cell_key);
        continue;
      }
      const resolved: ResolvedCell = {
        key: entry.cell_key,
        definition,
        projection: cellProjection,
        comparison: compared.get(entry.cell_key) ?? null,
        span: entry.span ?? 1,
        flatIndex: flatCells.length,
      };
      cells.push(resolved);
      flatCells.push(resolved);
    }
    return {
      domainKey: band.domain_key,
      label: domain?.label ?? band.domain_key,
      question: domain?.question ?? "",
      order: band.order,
      columns: band.columns,
      cells,
    };
  });

  const missingFromTemplate = projection.cells
    .map((cell) => cell.cell_key)
    .filter((key) => !laidOut.has(key));

  return { bands, flatCells, missingFromProjection, missingFromTemplate, unknownCellKeys };
}

// ─── Keyboard navigation ─────────────────────────────────────────────────────

export interface GridPosition {
  bandIndex: number;
  row: number;
  column: number;
}

export function positionOf(bands: ResolvedBand[], columns: number, flatIndex: number): GridPosition | null {
  for (let bandIndex = 0; bandIndex < bands.length; bandIndex += 1) {
    const cells = bands[bandIndex].cells;
    const offset = cells.findIndex((cell) => cell.flatIndex === flatIndex);
    if (offset >= 0) {
      return { bandIndex, row: Math.floor(offset / columns), column: offset % columns };
    }
  }
  return null;
}

export type CanvasArrow = "ArrowLeft" | "ArrowRight" | "ArrowUp" | "ArrowDown" | "Home" | "End";

/**
 * Arrow movement across a stack of independently-wrapped band grids. Vertical
 * movement off the top or bottom of one band continues into the neighbouring band
 * at the nearest column, so the whole canvas is one continuous keyboard surface.
 * Returns the destination flat index, or null when the move is a no-op.
 */
export function moveFocus(
  bands: ResolvedBand[],
  columns: number,
  fromFlatIndex: number,
  key: CanvasArrow,
): number | null {
  const position = positionOf(bands, columns, fromFlatIndex);
  if (!position) return null;
  const band = bands[position.bandIndex];
  const offset = position.row * columns + position.column;

  const at = (bandIndex: number, cellOffset: number): number | null => {
    const cells = bands[bandIndex]?.cells;
    if (!cells?.length) return null;
    const clamped = Math.max(0, Math.min(cellOffset, cells.length - 1));
    return cells[clamped].flatIndex;
  };

  const previousBandWithCells = (from: number) => {
    for (let index = from - 1; index >= 0; index -= 1) if (bands[index].cells.length) return index;
    return -1;
  };
  const nextBandWithCells = (from: number) => {
    for (let index = from + 1; index < bands.length; index += 1) if (bands[index].cells.length) return index;
    return -1;
  };

  switch (key) {
    case "ArrowRight":
      return offset + 1 < band.cells.length ? band.cells[offset + 1].flatIndex : null;
    case "ArrowLeft":
      return offset - 1 >= 0 ? band.cells[offset - 1].flatIndex : null;
    case "Home":
      return band.cells[0]?.flatIndex ?? null;
    case "End":
      return band.cells[band.cells.length - 1]?.flatIndex ?? null;
    case "ArrowDown": {
      const below = offset + columns;
      if (below < band.cells.length) return band.cells[below].flatIndex;
      const next = nextBandWithCells(position.bandIndex);
      return next === -1 ? null : at(next, position.column);
    }
    case "ArrowUp": {
      const above = offset - columns;
      if (above >= 0) return band.cells[above].flatIndex;
      const previous = previousBandWithCells(position.bandIndex);
      if (previous === -1) return null;
      const cells = bands[previous].cells;
      const lastRow = Math.floor((cells.length - 1) / columns);
      return at(previous, lastRow * columns + position.column);
    }
    default:
      return null;
  }
}
