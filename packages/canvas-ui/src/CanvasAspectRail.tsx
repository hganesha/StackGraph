"use client";

import type { ArchitectureAspectView, CanvasProjectionView } from "@stackgraph/shared";
import type { ResolvedCanvas } from "./layout";
import styles from "./canvas.module.css";

/**
 * Aspects are a many-to-many lens over cells, never a re-parenting of them
 * (spec §4.5). The rail therefore reports coverage — how many of the cells carrying
 * an aspect are populated, and how many cannot be evaluated — and filters the canvas
 * rather than owning any cell of its own.
 */
export function CanvasAspectRail({
  aspects,
  resolved,
  projection,
  activeAspect,
  onSelectAspect,
  variant,
}: {
  aspects: ArchitectureAspectView[];
  resolved: ResolvedCanvas;
  projection: CanvasProjectionView;
  activeAspect: string | null;
  onSelectAspect: (aspectKey: string | null) => void;
  variant: "rail" | "band";
}) {
  if (!aspects.length) return null;

  const rows = aspects.map((aspect) => {
    const cells = resolved.flatCells.filter((cell) => cell.definition.aspect_keys.includes(aspect.key));
    const populated = cells.filter((cell) => cell.projection.state === "POPULATED").length;
    const unevaluable = cells.filter(
      (cell) => cell.projection.state === "UNOBSERVED" || cell.projection.state === "UNBOUND",
    ).length;
    return { aspect, total: cells.length, populated, unevaluable };
  });

  return (
    <aside
      className={`${styles.rail} ${variant === "band" ? styles.railAsBand : ""}`}
      aria-labelledby="canvas-aspect-rail-heading"
    >
      <header className={styles.railHead}>
        <h3 className={styles.railTitle} id="canvas-aspect-rail-heading">
          Cross-cutting aspects
        </h3>
        <p className={styles.railNote}>
          Lenses over the cells above. Selecting one filters the canvas; it does not move any concern.
        </p>
      </header>
      <ul className={styles.railList}>
        {rows.map(({ aspect, total, populated, unevaluable }) => {
          const active = activeAspect === aspect.key;
          return (
            <li key={aspect.key}>
              <button
                type="button"
                className={`${styles.railItem} ${active ? styles.railItemActive : ""}`}
                aria-pressed={active}
                onClick={() => onSelectAspect(active ? null : aspect.key)}
                title={aspect.definition}
              >
                <span className={styles.railItemLabel}>{aspect.label}</span>
                <span className={styles.railItemCounts}>
                  {total === 0 ? (
                    "no cells"
                  ) : (
                    <>
                      {populated}/{total} populated
                      {unevaluable ? ` · ${unevaluable} unevaluable` : ""}
                    </>
                  )}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
      {projection.scope === "TARGET" ? (
        <p className={styles.railNote}>Aspect coverage reflects target decisions, not observed evidence.</p>
      ) : null}
    </aside>
  );
}
