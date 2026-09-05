/**
 * Squarified treemap layout — ~70 lines, no library.
 *
 * Bruls, Huizing and van Wijk's algorithm: lay items into the shorter side of the
 * remaining rectangle, extending the current row while doing so improves its worst
 * aspect ratio, and starting a new row the moment it stops. Squarish cells are the
 * point — a long thin cell makes its area impossible to compare against its
 * neighbours, and area is the encoding.
 *
 * Deliberately not `d3-hierarchy`. Every picture in this product is under 150 lines
 * of inline SVG or CSS, and pulling in a charting library would import a visual
 * language that fights the hairline-and-flat discipline the rest of the UI keeps.
 */
export interface TreemapInput<T> {
  item: T;
  /** Relative area. Non-positive values are dropped by the caller, not here. */
  value: number;
}

export interface TreemapTile<T> {
  item: T;
  x: number;
  y: number;
  width: number;
  height: number;
}

interface Rect {
  x: number;
  y: number;
  width: number;
  height: number;
}

/** Worst (largest) aspect ratio in a row, given the row's total and the side it sits on. */
function worstRatio(row: number[], rowSum: number, side: number): number {
  if (rowSum <= 0 || side <= 0) return Number.POSITIVE_INFINITY;
  const scale = (side * side) / (rowSum * rowSum);
  let worst = 0;
  for (const value of row) {
    worst = Math.max(worst, Math.max(value * scale, 1 / (value * scale)));
  }
  return worst;
}

export function squarify<T>(
  inputs: Array<TreemapInput<T>>,
  width: number,
  height: number,
): Array<TreemapTile<T>> {
  const positive = inputs.filter((input) => input.value > 0);
  const total = positive.reduce((sum, input) => sum + input.value, 0);
  if (!positive.length || total <= 0 || width <= 0 || height <= 0) return [];

  // Work in area units so the row arithmetic is in the same space as the rectangle.
  const scale = (width * height) / total;
  const queue = positive
    .map((input) => ({ item: input.item, area: input.value * scale }))
    .sort((left, right) => right.area - left.area);

  const tiles: Array<TreemapTile<T>> = [];
  let rect: Rect = { x: 0, y: 0, width, height };
  let index = 0;

  while (index < queue.length) {
    const side = Math.min(rect.width, rect.height);
    const row: Array<{ item: T; area: number }> = [];
    let rowSum = 0;

    // Extend the row while doing so improves the worst aspect ratio in it.
    while (index < queue.length) {
      const next = queue[index];
      const areas = row.map((entry) => entry.area);
      const current = row.length ? worstRatio(areas, rowSum, side) : Number.POSITIVE_INFINITY;
      const extended = worstRatio([...areas, next.area], rowSum + next.area, side);
      if (row.length && extended > current) break;
      row.push(next);
      rowSum += next.area;
      index += 1;
    }

    // Lay the row out across the shorter side, then shrink the rectangle behind it.
    const thickness = side > 0 ? rowSum / side : 0;
    const horizontal = rect.width >= rect.height;
    let offset = 0;
    for (const entry of row) {
      const extent = rowSum > 0 ? (entry.area / rowSum) * side : 0;
      tiles.push(
        horizontal
          ? { item: entry.item, x: rect.x, y: rect.y + offset, width: thickness, height: extent }
          : { item: entry.item, x: rect.x + offset, y: rect.y, width: extent, height: thickness },
      );
      offset += extent;
    }
    rect = horizontal
      ? { x: rect.x + thickness, y: rect.y, width: Math.max(rect.width - thickness, 0), height: rect.height }
      : { x: rect.x, y: rect.y + thickness, width: rect.width, height: Math.max(rect.height - thickness, 0) };
  }

  return tiles;
}
