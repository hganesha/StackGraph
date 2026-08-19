import styles from "./Skeleton.module.css";

/** Loading placeholder that reserves final dimensions — no layout shift (plan §1.3 calm). */
export function Skeleton({ height = 16, width = "100%", radius }: { height?: number | string; width?: number | string; radius?: string }) {
  return (
    <span
      className={styles.skeleton}
      aria-hidden="true"
      style={{ height, width, borderRadius: radius ?? "var(--sg-radius-control)" }}
    />
  );
}
