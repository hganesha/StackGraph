"use client";

import { useTheme } from "@stackgraph/design-system";
import { config } from "@stackgraph/shared";
import styles from "./TopBar.module.css";

export function TopBar({ onToggleNav, navOpen = false }: { onToggleNav?: () => void; navOpen?: boolean }) {
  const { choice, setChoice } = useTheme();
  const cycle = () => setChoice(choice === "light" ? "dark" : choice === "dark" ? "system" : "light");
  const themeIcon = choice === "light" ? "☀" : choice === "dark" ? "☾" : "◐";

  return (
    <header className={styles.bar}>
      <button
        className={styles.hamburger}
        type="button"
        onClick={onToggleNav}
        aria-label="Toggle navigation"
        aria-expanded={navOpen}
      >
        {navOpen ? "✕" : "☰"}
      </button>
      <div className={styles.brand}>
        <span className={styles.mark} aria-hidden="true" />
        <span className={styles.name}>StackGraph</span>
      </div>

      {/* Ask your estate — the one global input, present on every screen (plan §3.1). Wired in P2. */}
      <button className={styles.ask} type="button" aria-label="Ask your estate">
        <span className={styles.askLead} aria-hidden="true">
          ⌕
        </span>
        <span className={styles.askText}>Ask your estate…</span>
        <kbd className={styles.kbd}>⌘K</kbd>
      </button>

      <div className={styles.right}>
        {config.dataSource === "fixtures" ? <span className={styles.badge}>fixtures</span> : null}
        <button className={styles.iconBtn} type="button" onClick={cycle} aria-label={`Theme: ${choice}`} title={`Theme: ${choice}`}>
          {themeIcon}
        </button>
        <span className={styles.tenant} title="Tenant (from your session)">
          <span className={styles.tenantAvatar} aria-hidden="true">
            SG
          </span>
        </span>
      </div>
    </header>
  );
}
