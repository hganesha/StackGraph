"use client";

import { useCallback, useEffect, useId, useRef, useState } from "react";
import { GLOSSARY, type GlossaryEntry, type GlossaryKey } from "../glossary/terms";
import styles from "./Term.module.css";

/** Breathing room kept between the definition and the edge of whatever contains it. */
const EDGE_GUTTER = 8;
/** Matches the 22rem ceiling in the stylesheet; the measured space can only lower it. */
const PREFERRED_WIDTH = 352;

interface Placement {
  available: number;
  shift: number;
}

/**
 * The nearest ancestor that would clip the definition.
 *
 * A definition is positioned against the word it explains, but the word often sits
 * inside something that scrolls — a detail panel, a drawer, a table. Those clip their
 * absolutely-positioned descendants, so a definition anchored near the right edge gets
 * cut off mid-sentence rather than overflowing into the page.
 */
function clippingAncestor(node: HTMLElement | null): HTMLElement {
  const root = node?.ownerDocument?.documentElement ?? document.documentElement;
  for (let current = node?.parentElement; current; current = current.parentElement) {
    const { overflowX, overflowY } = getComputedStyle(current);
    if (overflowX !== "visible" || overflowY !== "visible") return current;
  }
  return root;
}

/** Keep the definition inside whatever would clip it, as close to its word as it fits. */
function placeWithin(anchor: HTMLElement): Placement {
  const clip = clippingAncestor(anchor);
  const clipRect = clip.getBoundingClientRect();
  // clientWidth excludes a vertical scrollbar; the border box does not.
  const clipStart = clipRect.left + clip.clientLeft;
  const available = Math.max(0, clip.clientWidth - EDGE_GUTTER * 2);
  const width = Math.min(PREFERRED_WIDTH, available);

  const anchorStart = anchor.getBoundingClientRect().left;
  const minStart = clipStart + EDGE_GUTTER;
  const maxStart = Math.max(minStart, clipStart + clip.clientWidth - EDGE_GUTTER - width);
  const start = Math.min(Math.max(anchorStart, minStart), maxStart);

  return { available, shift: Math.round(start - anchorStart) };
}

/**
 * A vocabulary word with its definition one hover or keypress away.
 *
 * The product's value is a precise vocabulary, so the answer to jargon is to define it
 * rather than to blunt it. Definitions come from one glossary module, so the same word
 * cannot mean two things on two screens.
 *
 * Accessibility notes, since a tooltip is easy to get wrong:
 *  - the trigger is a real button, so it is reachable and operable by keyboard;
 *  - the definition is hidden from the accessibility tree until it opens, and focusing
 *    the trigger opens it. Leaving it permanently exposed splices the whole definition
 *    into the middle of whatever sentence contains the term;
 *  - Escape closes it, and focus never moves, so it cannot trap anyone;
 *  - closed, it collapses to a one-pixel box. Laid out at full width it would still
 *    widen the scrollable area of a narrow container, giving panels a horizontal
 *    scrollbar with nothing in it.
 */
export function Term({
  id,
  children,
  className,
}: {
  id: GlossaryKey;
  /** Override the rendered word when the sentence needs a different form. */
  children?: React.ReactNode;
  className?: string;
}) {
  const entry: GlossaryEntry = GLOSSARY[id];
  const describedBy = useId();
  const [open, setOpen] = useState(false);
  const [placement, setPlacement] = useState<Placement | null>(null);
  const wrapRef = useRef<HTMLSpanElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);

  // Measured as it opens rather than after: the inputs are the word and its container,
  // both of which exist already, so there is no frame where the definition is misplaced.
  const reveal = useCallback(() => {
    if (triggerRef.current) setPlacement(placeWithin(triggerRef.current));
    setOpen(true);
  }, []);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    const onPointer = (event: PointerEvent) => {
      if (!wrapRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const onResize = () => {
      if (triggerRef.current) setPlacement(placeWithin(triggerRef.current));
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("pointerdown", onPointer);
    window.addEventListener("resize", onResize);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("pointerdown", onPointer);
      window.removeEventListener("resize", onResize);
    };
  }, [open]);

  return (
    <span
      className={`${styles.wrap} ${className ?? ""}`}
      ref={wrapRef}
      onMouseEnter={reveal}
      onMouseLeave={() => setOpen(false)}
    >
      <button
        type="button"
        ref={triggerRef}
        className={styles.trigger}
        // Described only while open. A permanently-referenced tooltip is also
        // permanently in the accessibility tree, so a screen reader reading the
        // surrounding sentence hears the whole definition spliced into the middle of
        // it. Focusing the trigger opens it, so a keyboard user still gets the
        // description at the moment they need it.
        aria-describedby={open ? describedBy : undefined}
        aria-expanded={open}
        onFocus={reveal}
        onBlur={() => setOpen(false)}
        // Opens rather than toggles: with a mouse the pointer has already triggered
        // the hover, so a toggle would close what the click was meant to open. Touch
        // has no hover and needs the click to open. Escape, blur, moving away, and a
        // click elsewhere all close it.
        onClick={reveal}
      >
        {children ?? entry.term}
      </button>
      <span
        role="tooltip"
        id={describedBy}
        aria-hidden={!open}
        className={`${styles.pop} ${open ? styles.popOpen : ""}`}
        style={placement ? {
          "--sg-term-available": `${placement.available}px`,
          "--sg-term-shift": `${placement.shift}px`,
        } as React.CSSProperties : undefined}
      >
        <span className={styles.popTerm}>{entry.term}</span>
        <span className={styles.popBody}>{entry.body}</span>
        {entry.note ? <span className={styles.popNote}>{entry.note}</span> : null}
      </span>
    </span>
  );
}

export { GLOSSARY };
export type { GlossaryKey, GlossaryEntry } from "../glossary/terms";
