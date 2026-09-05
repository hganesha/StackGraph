import styles from "./AttenuationBar.module.css";

export interface AttenuationStage {
  key: string;
  label: string;
  /** `null` means the stage was never checked — which is not the same as zero. */
  value: number | null;
}

export interface AttenuationBarProps {
  stages: AttenuationStage[];
  /** Eyebrow on the last stage that was actually checked. */
  actLabel?: string;
  locale?: string;
}

const MIN_VISIBLE = 1.5; // percent — a surviving count never collapses to nothing

function formatCount(value: number, locale?: string) {
  return value.toLocaleString(locale);
}

/**
 * The attenuation track: 1,240 present narrowing to 3 that matter.
 *
 * **The dropout is the product.** Every scanner on the market can tell you about the
 * 1,240; only StackGraph can show you the 1,237 falling away and name the evidence
 * class each one fell at. Rendered as eight numerals in a row, the collapse is
 * invisible — which is why this is a picture and not a table.
 *
 * Two rules the component enforces rather than leaves to callers:
 *
 *   - An unchecked stage is **hatched, never zero-width**. A stage nobody looked at
 *     must not read as "nothing survived here" — the same distinction the canvas
 *     already draws between "none found" and "not observed".
 *   - A stage that survived with a non-zero count keeps a visible sliver. Three out of
 *     twelve hundred is 0.24% of the track, and the whole argument rests on those
 *     three being findable.
 */
export function AttenuationBar({ stages, actLabel = "Act on these", locale }: AttenuationBarProps) {
  const known = stages.filter((stage): stage is AttenuationStage & { value: number } => stage.value != null);
  const unknownCount = stages.length - known.length;
  const head = known[0]?.value ?? 0;
  const lastKnownKey = known.length ? known[known.length - 1].key : null;

  // The sentence a screen reader gets. The shape is the whole point of the picture, so
  // its text equivalent has to be the shape too, not a list of eight numbers.
  const ariaLabel = known.length
    ? `${formatCount(head, locale)} ${known[0].label.toLowerCase()}, narrowing to ` +
      `${formatCount(known[known.length - 1].value, locale)} ${known[known.length - 1].label.toLowerCase()} ` +
      `across ${known.length} checked stage${known.length === 1 ? "" : "s"}` +
      (unknownCount ? `; ${unknownCount} stage${unknownCount === 1 ? "" : "s"} not checked.` : ".")
    : "No stage of this finding has been checked yet.";

  return (
    <div className={styles.track} role="region" aria-label={ariaLabel} tabIndex={0}>
      {stages.map((stage) => {
        const value = stage.value;
        const unchecked = value == null;
        const share = value == null || head <= 0 ? 0 : (value / head) * 100;
        const width = value == null ? 100 : value > 0 ? Math.max(share, MIN_VISIBLE) : 0;
        const isAct = stage.key === lastKnownKey;
        return (
          <div key={stage.key} className={styles.row}>
            <span className={styles.label}>{stage.label}</span>
            <span className={styles.bar}>
              <span
                className={`${styles.fill} ${unchecked ? styles.unchecked : ""} ${isAct ? styles.act : ""}`}
                style={{ inlineSize: `${width}%` }}
                aria-hidden="true"
              />
            </span>
            <span className={`${styles.value} sg-mono`}>
              {value == null ? "Not checked" : formatCount(value, locale)}
            </span>
            <span className={styles.eyebrow}>{isAct ? actLabel : ""}</span>
          </div>
        );
      })}
    </div>
  );
}
