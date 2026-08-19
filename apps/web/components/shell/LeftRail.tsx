"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import styles from "./LeftRail.module.css";

// Nav mirrors the surfaces in spec §46 V0 order (plan §3.2).
const PRIMARY = [
  { href: "/estate", label: "Software Estate", icon: "▦" },
  { href: "/applications", label: "Applications", icon: "▤" },
  { href: "/technologies", label: "Technologies", icon: "◈" },
  { href: "/modernization", label: "Modernization", icon: "↑" },
  { href: "/ask", label: "Ask", icon: "?" },
];

const SECONDARY = [
  { href: "/reviews", label: "Reviews", icon: "◇" },
  { href: "/health", label: "Estate Health", icon: "◉" },
];

const ADMIN = [{ href: "/admin", label: "Admin", icon: "⚙" }];

export function LeftRail({ open = false, onNavigate }: { open?: boolean; onNavigate?: () => void }) {
  const pathname = usePathname();
  const isActive = (href: string) => pathname === href || pathname.startsWith(`${href}/`);

  const renderItem = (item: { href: string; label: string; icon: string }) => (
    <li key={item.href}>
      <Link
        href={item.href}
        className={`${styles.item} ${isActive(item.href) ? styles.active : ""}`}
        aria-current={isActive(item.href) ? "page" : undefined}
        onClick={onNavigate}
      >
        <span className={styles.icon} aria-hidden="true">
          {item.icon}
        </span>
        <span className={styles.label}>{item.label}</span>
      </Link>
    </li>
  );

  return (
    <nav className={`${styles.rail} ${open ? styles.open : ""}`} aria-label="Primary">
      <ul className={styles.group}>{PRIMARY.map(renderItem)}</ul>
      <div className={styles.divider} />
      <ul className={styles.group}>{SECONDARY.map(renderItem)}</ul>
      <div className={styles.spacer} />
      <ul className={styles.group}>{ADMIN.map(renderItem)}</ul>
    </nav>
  );
}
