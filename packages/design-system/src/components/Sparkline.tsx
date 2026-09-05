import styles from "./Sparkline.module.css";

export interface SparklineProps {
  /** Oldest first. Fewer than two points renders nothing — one point is not a trend. */
  points: number[];
  width?: number;
  height?: number;
  /**
   * The sentence a screen reader gets. Required: the shape carries no value on its
   * own, and the numeral beside a sparkline is the only thing that does.
   */
  label: string;
}

/**
 * A 64×18 trend line and nothing else — no axes, no gridlines, no tooltip, no dots.
 *
 * The numeral printed beside it carries the value; this carries only the shape, which
 * is the one thing a numeral cannot show. Anything more turns an instrument panel into
 * a dashboard, and this one is read under pressure.
 */
export function Sparkline({ points, width = 64, height = 18, label }: SparklineProps) {
  if (points.length < 2) return null;
  const min = Math.min(...points);
  const max = Math.max(...points);
  const span = max - min;
  const inset = 1.5;
  const usable = height - inset * 2;
  const step = (width - inset * 2) / (points.length - 1);
  // A flat series has no range to normalise against; draw it on the midline rather
  // than dividing by zero and rendering a line at the top of the box.
  const y = (value: number) =>
    span === 0 ? height / 2 : inset + usable - ((value - min) / span) * usable;
  const d = points.map((value, index) => `${index === 0 ? "M" : "L"}${(inset + index * step).toFixed(2)},${y(value).toFixed(2)}`).join(" ");

  return (
    <svg
      className={styles.spark}
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label={label}
    >
      <path d={d} fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
