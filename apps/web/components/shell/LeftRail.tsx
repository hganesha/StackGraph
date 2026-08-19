"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  IconActivityHeartbeat,
  IconApps,
  IconChecklist,
  IconHierarchy3,
  IconLayoutDashboard,
  IconMessageQuestion,
  IconSettings,
  IconStack2,
  IconTrendingUp,
  type Icon,
} from "@tabler/icons-react";
import styles from "./LeftRail.module.css";

// Nav mirrors the surfaces in spec §46 V0 order (plan §3.2).
const PRIMARY = [
  { href: "/estate", label: "Software Estate", icon: IconLayoutDashboard },
  { href: "/business-map", label: "Business Map", icon: IconHierarchy3 },
  { href: "/applications", label: "Applications", icon: IconApps },
  { href: "/technologies", label: "Technologies", icon: IconStack2 },
  { href: "/modernization", label: "Modernization", icon: IconTrendingUp },
  { href: "/ask", label: "Ask", icon: IconMessageQuestion },
];

const SECONDARY = [
  { href: "/reviews", label: "Reviews", icon: IconChecklist },
  { href: "/health", label: "Estate Health", icon: IconActivityHeartbeat },
];

const ADMIN = [{ href: "/admin", label: "Admin", icon: IconSettings }];

export function LeftRail({
  open = false,
  compact = false,
  onNavigate,
}: {
  open?: boolean;
  compact?: boolean;
  onNavigate?: () => void;
}) {
  const pathname = usePathname();
  const isActive = (href: string) => pathname === href || pathname.startsWith(`${href}/`);

  const renderItem = (item: { href: string; label: string; icon: Icon }) => {
    const ItemIcon = item.icon;
    return (
    <li key={item.href}>
      <Link
        href={item.href}
        className={`${styles.item} ${isActive(item.href) ? styles.active : ""}`}
        aria-current={isActive(item.href) ? "page" : undefined}
        onClick={onNavigate}
      >
        <span className={styles.icon} aria-hidden="true">
          <ItemIcon size={17} stroke={1.5} />
        </span>
        <span className={styles.label}>{item.label}</span>
      </Link>
    </li>
    );
  };

  return (
    <nav className={`${styles.rail} ${compact ? styles.compact : ""} ${open ? styles.open : ""}`} aria-label="Primary">
      <ul className={styles.group}>{PRIMARY.map(renderItem)}</ul>
      <div className={styles.divider} />
      <ul className={styles.group}>{SECONDARY.map(renderItem)}</ul>
      <div className={styles.spacer} />
      <ul className={styles.group}>{ADMIN.map(renderItem)}</ul>
    </nav>
  );
}
