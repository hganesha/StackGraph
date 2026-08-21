"use client";

import Image from "next/image";
import { useRouter } from "next/navigation";
import { IconContrast, IconMenu2, IconMoon, IconSearch, IconSun, IconX } from "@tabler/icons-react";
import { useTheme } from "@stackgraph/design-system";
import { config } from "@stackgraph/shared";
import { useSession } from "@/lib/session";
import styles from "./TopBar.module.css";

export function TopBar({ onToggleNav, navOpen = false }: { onToggleNav?: () => void; navOpen?: boolean }) {
  const { choice, setChoice } = useTheme();
  const session = useSession();
  const router = useRouter();
  const cycle = () => setChoice(choice === "light" ? "dark" : choice === "dark" ? "system" : "light");
  const ThemeIcon = choice === "light" ? IconSun : choice === "dark" ? IconMoon : IconContrast;
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

      {/* Ask your estate — the one global input, present on every screen (plan §3.1). Wired in P2. */}
      <button className={styles.ask} type="button" aria-label="Ask your estate" onClick={() => router.push("/ask")}>
        <span className={styles.askLead} aria-hidden="true">
          <IconSearch size={16} stroke={1.5} />
        </span>
        <span className={styles.askText}>Ask your estate…</span>
        <kbd className={styles.kbd}>⌘K</kbd>
      </button>

      <div className={styles.right}>
        {config.dataSource === "fixtures" ? <span className={styles.badge}>fixtures</span> : null}
        <button className={styles.iconBtn} type="button" onClick={cycle} aria-label={`Theme: ${choice}`} title={`Theme: ${choice}`}>
          <ThemeIcon size={17} stroke={1.5} />
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
