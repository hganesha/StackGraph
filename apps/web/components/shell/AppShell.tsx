"use client";

import { useEffect, useState, type ReactNode } from "react";
import { usePathname, useRouter } from "next/navigation";
import { StatusStrip } from "@stackgraph/design-system";
import { useEstateSummary } from "@/lib/queries";
import { TopBar } from "./TopBar";
import { LeftRail } from "./LeftRail";
import { EvidenceDrawerHost } from "@/components/evidence/EvidenceDrawerHost";
import styles from "./AppShell.module.css";

/** Stable three-region shell (plan §3.1). On mobile the rail becomes an off-canvas drawer. */
export function AppShell({ children }: { children: ReactNode }) {
  const { data } = useEstateSummary();
  const [navOpen, setNavOpen] = useState(false);
  const pathname = usePathname();
  const router = useRouter();
  const fullBleed = pathname.startsWith("/business-map");

  // Close the drawer on route change and when returning to desktop width.
  useEffect(() => setNavOpen(false), [pathname]);

  // ⌘K / Ctrl-K opens Ask your estate from anywhere (plan §3.1, §4.3).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        router.push("/ask");
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [router]);
  useEffect(() => {
    if (!navOpen) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setNavOpen(false);
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [navOpen]);

  return (
    <div className={styles.shell}>
      <a href="#main" className={styles.skipLink}>
        Skip to content
      </a>
      <TopBar onToggleNav={() => setNavOpen((v) => !v)} navOpen={navOpen} />
      <div className={styles.body}>
        <LeftRail open={navOpen} compact={fullBleed} onNavigate={() => setNavOpen(false)} />
        {navOpen ? <button className={styles.backdrop} aria-label="Close navigation" onClick={() => setNavOpen(false)} /> : null}
        <main className={`${styles.workspace} ${fullBleed ? styles.workspaceFullBleed : ""}`} id="main">
          {children}
        </main>
      </div>
      {data ? (
        <StatusStrip
          repositoriesScanned={data.coverage.repositories_scanned}
          repositoriesTotal={data.coverage.repositories_total}
          evidenceRatio={data.coverage.facts_with_evidence_ratio}
          asOf={data.as_of}
          contractVersion={data.contract_version}
        />
      ) : (
        <div className={styles.statusPlaceholder} />
      )}
      <EvidenceDrawerHost />
    </div>
  );
}
