/**
 * Five marks Tabler does not have, because nothing else in this category holds the
 * concepts they name (recommendations §6.1).
 *
 * Drawn in the same language as the rest of the iconography — 24px grid, 1.5px
 * stroke, outline only, no fill, `currentColor` throughout — so they sit beside
 * Tabler icons without announcing themselves as a different set. They are the
 * product's visual signature: attenuation, blast, spread, strata, drift.
 *
 * Each one is decorative by default and takes its meaning from the label beside it.
 * Pass `title` only where the glyph is the sole carrier of a distinction.
 */
export interface SignalGlyphProps {
  size?: number;
  /** Accessible name. Omit — the default — to render the mark as decoration. */
  title?: string;
  className?: string;
}

function frame({ size = 24, title, className }: SignalGlyphProps) {
  return {
    width: size,
    height: size,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.5,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    className,
    role: title ? ("img" as const) : undefined,
    "aria-label": title,
    "aria-hidden": title ? undefined : true,
  };
}

/** A wedge narrowing left to right: what survives each stage of a check. */
export function IconAttenuation(props: SignalGlyphProps) {
  return (
    <svg {...frame(props)}>
      <path d="M3 4v16" />
      <path d="M3 5h17l-5 6.5L20 18H3" />
      <path d="M9 9.5h6" />
      <path d="M11 14h3" />
    </svg>
  );
}

/** Concentric arcs from a point: how far a change reaches. */
export function IconBlast(props: SignalGlyphProps) {
  return (
    <svg {...frame(props)}>
      <circle cx="6" cy="12" r="1.6" />
      <path d="M10.5 7.5a6.4 6.4 0 0 1 0 9" />
      <path d="M14.5 5a10.4 10.4 0 0 1 0 14" />
      <path d="M18.5 2.8a14.2 14.2 0 0 1 0 18.4" />
    </svg>
  );
}

/** Scattered ticks on a baseline: how many different ways one thing is done. */
export function IconSpread(props: SignalGlyphProps) {
  return (
    <svg {...frame(props)}>
      <path d="M3 19h18" />
      <path d="M5 19v-4" />
      <path d="M9 19V8" />
      <path d="M12 19v-7" />
      <path d="M16 19V5" />
      <path d="M20 19v-9" />
    </svg>
  );
}

/** Five stacked bands, one broken: the layers, and where the knowledge runs out. */
export function IconStrata(props: SignalGlyphProps) {
  return (
    <svg {...frame(props)}>
      <path d="M3 5h18" />
      <path d="M3 9h18" />
      {/* The broken band is the point of the mark: a layer we cannot see through. */}
      <path d="M3 13h6" />
      <path d="M13 13h8" />
      <path d="M3 17h18" />
      <path d="M3 21h18" />
    </svg>
  );
}

/** Two diverging lines: what you run against what you said you would run. */
export function IconDrift(props: SignalGlyphProps) {
  return (
    <svg {...frame(props)}>
      <path d="M3 12h5" />
      <path d="M8 12l12-7" />
      <path d="M8 12l12 7" />
      <circle cx="8" cy="12" r="1.4" />
    </svg>
  );
}
