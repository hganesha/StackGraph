"use client";

import Image from "next/image";
import { IconContrast, IconMenu2, IconMoon, IconSearch, IconSun, IconX } from "@tabler/icons-react";
import { useTheme } from "@stackgraph/design-system";
import { config } from "@stackgraph/shared";
import { useSession } from "@/lib/session";
import styles from "./TopBar.module.css";

export function TopBar({
  onToggleNav,
  onOpenChange,
  navOpen = false,
}: {
  onToggleNav?: () => void;
  onOpenChange: () => void;
  navOpen?: boolean;
}) {
  const { choice, setChoice } = useTheme();
  const session = useSession();
  const cycle = () => setChoice(choice === "light" ? "dark" : choice === "dark" ? "system" : "light");
  const ThemeIcon = choice === "light" ? IconSun : choice === "dark" ? IconMoon : IconContrast;
  // A three-state cycle behind an icon that changes with the state gives a reader no
  // way to know which state they are in, or what pressing it will do (defect §7.8).
  // Both are now on the control itself.
  const THEME_LABEL = { light: "Light", dark: "Dark", system: "System" } as const;
  const NEXT_THEME = { light: "dark", dark: "system", system: "light" } as const;
  const initials = session.actorKey
    ? session.actorKey.split(/[^A-Za-z0-9]+/).filter(Boolean).slice(0, 2).map((part) => part[0]?.toUpperCase()).join("")
    : "SG";
  const signOut = async () => {
    await fetch(`${config.apiBaseUrl}/api/v1/auth/logout`, {
      method: "POST",
      credentials: "include",
    });
    window.location.assign("/login");
  };

  return (
    <header className={styles.bar}>
      <button
        className={styles.hamburger}
        type="button"
        onClick={onToggleNav}
        aria-label="Toggle navigation"
        aria-expanded={navOpen}
      >
        {navOpen ? <IconX size={18} stroke={1.5} /> : <IconMenu2 size={18} stroke={1.5} />}
      </button>
      <div className={styles.brand}>
        <Image className={styles.mark} src="/icon.svg" width={18} height={18} alt="" aria-hidden="true" />
        <span className={styles.name}>StackGraph</span>
      </div>

      <button className={styles.ask} type="button" aria-label="Plan an estate-backed change" onClick={onOpenChange}>
        <span className={styles.askLead} aria-hidden="true">
          <IconSearch size={16} stroke={1.5} />
        </span>
        <span className={styles.askText}>Plan an estate-backed change…</span>
        <kbd className={styles.kbd}>⌘K</kbd>
      </button>

      <div className={styles.right}>
        {config.dataSource === "fixtures" ? <span className={styles.badge}>fixtures</span> : null}
        <button
          className={styles.theme}
          type="button"
          onClick={cycle}
          aria-label={`Theme: ${THEME_LABEL[choice]}. Switch to ${THEME_LABEL[NEXT_THEME[choice]].toLowerCase()}.`}
          title={`Theme: ${THEME_LABEL[choice]} — switch to ${THEME_LABEL[NEXT_THEME[choice]].toLowerCase()}`}
        >
          <ThemeIcon size={17} stroke={1.5} aria-hidden="true" />
          <span className={styles.themeLabel}>{THEME_LABEL[choice]}</span>
        </button>
        <button
          className={styles.tenant}
          type="button"
          title={session.actorKey ? `Sign out ${session.actorKey}` : "Tenant session"}
          aria-label={session.actorKey ? `Sign out ${session.actorKey}` : "Tenant session"}
          onClick={session.actorKey ? signOut : undefined}
        >
          <span className={styles.tenantAvatar} aria-hidden="true">
            {initials || "SG"}
          </span>
        </button>
      </div>
    </header>
  );
}
