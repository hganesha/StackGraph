"use client";

import { useEffect, useId, useRef, useState } from "react";
import { GLOSSARY, type GlossaryEntry, type GlossaryKey } from "../glossary/terms";
import styles from "./Term.module.css";

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
 *  - Escape closes it, and focus never moves, so it cannot trap anyone.
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
  const wrapRef = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    const onPointer = (event: PointerEvent) => {
      if (!wrapRef.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("pointerdown", onPointer);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("pointerdown", onPointer);
    };
  }, [open]);

  return (
    <span
      className={`${styles.wrap} ${className ?? ""}`}
      ref={wrapRef}
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
    >
      <button
        type="button"
        className={styles.trigger}
        // Described only while open. A permanently-referenced tooltip is also
        // permanently in the accessibility tree, so a screen reader reading the
        // surrounding sentence hears the whole definition spliced into the middle of
        // it. Focusing the trigger opens it, so a keyboard user still gets the
        // description at the moment they need it.
        aria-describedby={open ? describedBy : undefined}
        aria-expanded={open}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        // Opens rather than toggles: with a mouse the pointer has already triggered
        // the hover, so a toggle would close what the click was meant to open. Touch
        // has no hover and needs the click to open. Escape, blur, moving away, and a
        // click elsewhere all close it.
        onClick={() => setOpen(true)}
      >
        {children ?? entry.term}
      </button>
      <span
        role="tooltip"
        id={describedBy}
        aria-hidden={!open}
        className={`${styles.pop} ${open ? styles.popOpen : ""}`}
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
