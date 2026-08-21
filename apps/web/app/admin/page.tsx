"use client";

import { useState } from "react";
import { useCan } from "@/lib/session";
import { ConnectionsSection } from "@/components/admin/ConnectionsSection";
import { ScanSection } from "@/components/admin/ScanSection";
import { IntelligenceSection } from "@/components/admin/IntelligenceSection";
import { GovernanceSection } from "@/components/admin/GovernanceSection";
import { CodePoliciesSection } from "@/components/admin/CodePoliciesSection";
import { MembersSection } from "@/components/admin/MembersSection";
import { ServicesSection } from "@/components/admin/ServicesSection";
import styles from "@/components/admin/admin.module.css";

const TABS = [
  { key: "connections", label: "Connections" },
  { key: "scan", label: "Scan & Refresh" },
  { key: "intelligence", label: "Intelligence / AI" },
  { key: "governance", label: "Modernization" },
  { key: "code-policies", label: "Code Policies" },
  { key: "services", label: "Services" },
  { key: "members", label: "Members & Roles" },
] as const;

type TabKey = (typeof TABS)[number]["key"];

export default function AdminPage() {
  const isAdmin = useCan("admin");
  const [tab, setTab] = useState<TabKey>("connections");

  if (!isAdmin) {
    return (
      <div className={styles.denied}>
        <h1 className={styles.title}>Admin</h1>
        <p>You don’t have the admin capability. Ask a workspace admin for access.</p>
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <header className={styles.head}>
        <h1 className={styles.title}>Admin</h1>
        <p className={styles.subtitle}>
          Connections, refresh schedules, AI settings, modernization governance, and roles. Changes here are written to the audit log.
        </p>
      </header>

      <div className={styles.tabs} role="tablist" aria-label="Admin sections">
        {TABS.map((t) => (
          <button
            key={t.key}
            role="tab"
            aria-selected={tab === t.key}
            className={`${styles.tab} ${tab === t.key ? styles.tabActive : ""}`}
            onClick={() => setTab(t.key)}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className={styles.panel}>
        {tab === "connections" ? <ConnectionsSection /> : null}
        {tab === "scan" ? <ScanSection /> : null}
        {tab === "intelligence" ? <IntelligenceSection /> : null}
        {tab === "governance" ? <GovernanceSection /> : null}
        {tab === "code-policies" ? <CodePoliciesSection /> : null}
        {tab === "services" ? <ServicesSection /> : null}
        {tab === "members" ? <MembersSection /> : null}
      </div>
    </div>
  );
}
