"use client";

import { useEffect, useState, type ReactNode } from "react";
import { usePathname } from "next/navigation";
import dynamic from "next/dynamic";
import { StatusStrip } from "@stackgraph/design-system";
import { useCapabilityFootprints, useEstateSummary } from "@/lib/queries";
import { useEstateStrata } from "@/lib/useEstateStrata";
import { TopBar } from "./TopBar";
import { LeftRail } from "./LeftRail";
import { EvidenceDrawerHost } from "@/components/evidence/EvidenceDrawerHost";
import styles from "./AppShell.module.css";

// The compiler and its target/scope visualizations are substantial and optional on
// most routes. Keep them out of the shared shell chunk until the command is opened.
const ChangeCommandPalette = dynamic(
  () => import("@/components/change/ChangeCommandPalette").then((module) => module.ChangeCommandPalette),
  { ssr: false },
);

/** Stable three-region shell (plan §3.1). On mobile the rail becomes an off-canvas drawer. */
export function AppShell({ children }: { children: ReactNode }) {
  const { data } = useEstateSummary();
  // One request, generously cached, shared with the capability heat grid. It is what
  // gives the Business band a denominator.
  const footprints = useCapabilityFootprints();
  const strata = useEstateStrata(data, footprints.data);
  const [navOpen, setNavOpen] = useState(false);
  const [changeOpen, setChangeOpen] = useState(false);
  const pathname = usePathname();
  const fullBleed = pathname?.startsWith("/business-map") ?? false;

  // Close the drawer on route change and when returning to desktop width.
  useEffect(() => setNavOpen(false), [pathname]);

  // The change compiler is the one global command surface. It is an overlay so the
  // user's current estate context remains visible when they open it.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setChangeOpen(true);
      }
    };
    const onOpen = () => setChangeOpen(true);
    document.addEventListener("keydown", onKey);
    window.addEventListener("stackgraph:open-change-command", onOpen);
    return () => {
      document.removeEventListener("keydown", onKey);
      window.removeEventListener("stackgraph:open-change-command", onOpen);
    };
  }, []);
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
      <TopBar
        onToggleNav={() => setNavOpen((v) => !v)}
        onOpenChange={() => setChangeOpen(true)}
        navOpen={navOpen}
      />
      <div className={styles.body}>
        <LeftRail open={navOpen} onNavigate={() => setNavOpen(false)} />
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
          layers={strata.layers}
          weakestLayer={strata.weakest}
        />
      ) : (
        <div className={styles.statusPlaceholder} />
      )}
      <EvidenceDrawerHost />
      <ChangeCommandPalette open={changeOpen} onClose={() => setChangeOpen(false)} />
    </div>
  );
}
