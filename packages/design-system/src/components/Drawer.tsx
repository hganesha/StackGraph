"use client";

import { useEffect, useRef, type ReactNode } from "react";
import styles from "./Drawer.module.css";

/**
 * Right-side drawer (evidence, inspector). Raised elevation.
 * Desktop: side panel. Mobile: full-height sheet. Esc closes; focus moves in on open.
 */
export function Drawer({
  open,
  onClose,
  title,
  children,
  labelId = "sg-drawer-title",
}: {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  children: ReactNode;
  labelId?: string;
}) {
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    panelRef.current?.focus();
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className={styles.layer}>
      <button className={styles.backdrop} aria-label="Close" onClick={onClose} />
      <div
        className={styles.panel}
        role="dialog"
        aria-modal="true"
        aria-labelledby={labelId}
        tabIndex={-1}
        ref={panelRef}
      >
        <header className={styles.header}>
          <h2 id={labelId} className={styles.title}>
            {title}
          </h2>
          <button className={styles.close} onClick={onClose} aria-label="Close drawer">
            ✕
          </button>
        </header>
        <div className={styles.content}>{children}</div>
      </div>
    </div>
  );
}
