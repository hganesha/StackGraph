"use client";

import { useMemo } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  IconActivityHeartbeat,
  IconApps,
  IconGitBranch,
  IconChecklist,
  IconHierarchy3,
  IconInfoCircle,
  IconLayoutDashboard,
  IconSettings,
  IconStack2,
  IconTrendingUp,
  IconLayoutGrid,
  IconPlayerPlay,
  IconMessageQuestion,
  type Icon,
} from "@tabler/icons-react";
import { useReviewQueue, useServiceStatus } from "@/lib/queries";
import styles from "./LeftRail.module.css";

interface RailItem {
  href: string;
  label: string;
  icon: Icon;
}

interface RailGroup {
  key: string;
  /**
   * The rail already grouped its items with a bare divider — the structure existed and
   * was invisible. Three verbs tell a new user what the product is for before they
   * click anything (recommendations R10b).
   */
  label: string;
  items: RailItem[];
}

const GROUPS: RailGroup[] = [
  {
    key: "understand",
    label: "Understand",
    items: [
      { href: "/estate", label: "Estate", icon: IconLayoutDashboard },
      { href: "/business-map", label: "Business Map", icon: IconHierarchy3 },
      { href: "/applications", label: "Applications", icon: IconApps },
      { href: "/repositories", label: "Repositories", icon: IconGitBranch },
      { href: "/technologies", label: "Technologies", icon: IconStack2 },
      { href: "/architecture", label: "Architecture", icon: IconLayoutGrid },
      { href: "/ask", label: "Ask", icon: IconMessageQuestion },
    ],
  },
  {
    key: "change",
    label: "Change",
    items: [
      { href: "/simulate", label: "Simulate", icon: IconPlayerPlay },
      { href: "/modernization", label: "Modernization", icon: IconTrendingUp },
      { href: "/reviews", label: "Reviews", icon: IconChecklist },
    ],
  },
  {
    key: "operate",
    label: "Operate",
    items: [
      { href: "/health", label: "Scan health", icon: IconActivityHeartbeat },
      { href: "/about", label: "About", icon: IconInfoCircle },
      { href: "/admin", label: "Admin", icon: IconSettings },
    ],
  },
];

/** A service that needs someone to look at it, as distinct from one that is simply idle. */
const UNHEALTHY = new Set(["DEGRADED", "OFFLINE"]);

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
  const isActive = (href: string) => pathname === href || Boolean(pathname?.startsWith(`${href}/`));

  // Both queries are already in flight elsewhere in the app, so hoisting them into the
  // shell reuses their cache keys rather than opening a new request path. A reviewer
  // should never have to open Reviews to discover it is empty (recommendations R10a).
  const reviewQueue = useReviewQueue();
  const serviceStatus = useServiceStatus();

  const reviewDepth = reviewQueue.data?.page_info?.has_next_page
    ? `${reviewQueue.data.items.length}+`
    : reviewQueue.data
      ? String(reviewQueue.data.items.length)
      : null;

  const degraded = useMemo(
    () => (serviceStatus.data?.services ?? []).filter((service) => UNHEALTHY.has(service.state)),
    [serviceStatus.data],
  );

  const badgeFor = (href: string) => {
    if (href === "/reviews" && reviewDepth && reviewDepth !== "0") {
      return {
        node: <span className={styles.count}>{reviewDepth}</span>,
        description: `${reviewDepth} waiting for a decision`,
      };
    }
    if (href === "/health" && degraded.length) {
      return {
        // A dot, not a count: the number of degraded services is not the point, the
        // fact that any are is.
        node: <span className={styles.dot} />,
        description: `${degraded.length} service${degraded.length === 1 ? "" : "s"} degraded or offline`,
      };
    }
    return null;
  };

  const renderItem = (item: RailItem) => {
    const ItemIcon = item.icon;
    const badge = badgeFor(item.href);
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
          {badge ? (
            <span className={styles.badge} title={badge.description}>
              {badge.node}
              <span className={styles.visuallyHidden}>{` — ${badge.description}`}</span>
            </span>
          ) : null}
        </Link>
      </li>
    );
  };

  return (
    <nav className={`${styles.rail} ${compact ? styles.compact : ""} ${open ? styles.open : ""}`} aria-label="Primary">
      {/* The group name lives on the list's accessible name rather than in a heading:
          the rail sits before the page's own <h1>, and a heading here would put the
          document's outline in the navigation instead of in the content. */}
      {GROUPS.map((group) => (
        <div key={group.key} className={styles.group}>
          <span className={styles.groupLabel} aria-hidden="true">
            {group.label}
          </span>
          <ul className={styles.groupList} aria-label={group.label}>
            {group.items.map(renderItem)}
          </ul>
        </div>
      ))}
    </nav>
  );
}
