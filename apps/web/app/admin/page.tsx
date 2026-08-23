"use client";

import { useState } from "react";
import { useSearchParams } from "next/navigation";
import {
  IconBrain,
  IconDatabase,
  IconFileCode,
  IconLayoutGrid,
  IconPlugConnected,
  IconRefresh,
  IconScale,
  IconServer2,
  IconSparkles,
  IconTrendingUp,
  IconUsers,
  type Icon,
} from "@tabler/icons-react";
import { useCan } from "@/lib/session";
import { ConnectionsSection } from "@/components/admin/ConnectionsSection";
import { ScanSection } from "@/components/admin/ScanSection";
import { IntelligenceSection } from "@/components/admin/IntelligenceSection";
import { GovernanceSection } from "@/components/admin/GovernanceSection";
import { CodePoliciesSection } from "@/components/admin/CodePoliciesSection";
import { ArchitectureProfilesSection } from "@/components/admin/ArchitectureProfilesSection";
import { MembersSection } from "@/components/admin/MembersSection";
import { ServicesSection } from "@/components/admin/ServicesSection";
import styles from "@/components/admin/admin.module.css";

const TABS = [
  { key: "data", label: "Data & sources", description: "Connections and refresh", icon: IconDatabase },
  { key: "intelligence", label: "Intelligence", description: "AI models and services", icon: IconBrain },
  { key: "governance", label: "Policies & rules", description: "Modernization and code policy", icon: IconScale },
  { key: "access", label: "People & access", description: "Members and roles", icon: IconUsers },
] as const;

type TabKey = (typeof TABS)[number]["key"];

const DATA_VIEWS = [
  { key: "connections", label: "Connections", detail: "Sources and repositories", icon: IconPlugConnected },
  { key: "scan", label: "Scan & refresh", detail: "Cadence, quotas, and rescans", icon: IconRefresh },
] as const;

const INTELLIGENCE_VIEWS = [
  { key: "ai", label: "AI provider", detail: "Models and data residency", icon: IconSparkles },
  { key: "services", label: "Worker services", detail: "Queues and processing state", icon: IconServer2 },
] as const;

const GOVERNANCE_VIEWS = [
  { key: "modernization", label: "Modernization", detail: "Rules, eligibility, and calibration", icon: IconTrendingUp },
  { key: "code", label: "Code policies", detail: "Function technology boundaries", icon: IconFileCode },
  { key: "architecture", label: "Architecture profile", detail: "Revisions, expectations, and publishing", icon: IconLayoutGrid },
] as const;

function SectionTabs({
  scope,
  label,
  items,
  active,
  onChange,
}: {
  scope: string;
  label: string;
  items: readonly { key: string; label: string; detail: string; icon: Icon }[];
  active: string;
  onChange: (key: string) => void;
}) {
  return (
    <div className={styles.subtabs} role="tablist" aria-label={label}>
      {items.map((item) => {
        const Glyph = item.icon;
        return (
          <button
            key={item.key}
            id={`${scope}-tab-${item.key}`}
            className={`${styles.subtab} ${active === item.key ? styles.subtabActive : ""}`}
            type="button"
            role="tab"
            aria-selected={active === item.key}
            aria-controls={`${scope}-panel-${item.key}`}
            onClick={() => onChange(item.key)}
          >
            <span className={styles.subtabLabel}>
              <Glyph size={15} stroke={1.5} aria-hidden="true" />
              <strong>{item.label}</strong>
            </span>
            <small>{item.detail}</small>
          </button>
        );
      })}
    </div>
  );
}

export default function AdminPage() {
  const searchParams = useSearchParams();
  const isAdmin = useCan("admin");
  const requestedTab = searchParams.get("tab");
  const [tab, setTab] = useState<TabKey>(
    TABS.some((item) => item.key === requestedTab) ? requestedTab as TabKey : "data",
  );
  const [dataView, setDataView] = useState<(typeof DATA_VIEWS)[number]["key"]>("connections");
  const [intelligenceView, setIntelligenceView] = useState<(typeof INTELLIGENCE_VIEWS)[number]["key"]>("ai");
  const [governanceView, setGovernanceView] = useState<(typeof GOVERNANCE_VIEWS)[number]["key"]>("modernization");
  const activeTab = TABS.find((item) => item.key === tab) ?? TABS[0];

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
        <div>
          <h1 className={styles.title}>Admin</h1>
          <p className={styles.subtitle}>
            Configure sources, automation, governance, and access for this workspace.
          </p>
        </div>
        <span className={styles.auditBadge}>All changes audited</span>
      </header>

      <div className={styles.adminWorkspace}>
        <div className={styles.tabs} role="tablist" aria-label="Admin sections">
          {TABS.map((item) => {
            const Icon = item.icon;
            return (
              <button
                key={item.key}
                id={`admin-tab-${item.key}`}
                role="tab"
                aria-controls={`admin-panel-${item.key}`}
                aria-selected={tab === item.key}
                className={`${styles.tab} ${tab === item.key ? styles.tabActive : ""}`}
                onClick={() => setTab(item.key)}
              >
                <Icon className={styles.tabIcon} size={18} stroke={1.8} aria-hidden="true" />
                <span className={styles.tabCopy}>
                  <strong>{item.label}</strong>
                  <small>{item.description}</small>
                </span>
              </button>
            );
          })}
        </div>

        <div
          id={`admin-panel-${tab}`}
          className={styles.panel}
          role="tabpanel"
          aria-labelledby={`admin-tab-${tab}`}
        >
          <header className={styles.panelHead}>
            <div>
              <span className={styles.pageEyebrow}>Admin section</span>
              <h2>{activeTab.label}</h2>
            </div>
            <p>{activeTab.description}</p>
          </header>
          <div className={styles.panelBody}>
            {tab === "data" ? (
              <div className={styles.section}>
                <SectionTabs scope="data" label="Data and source settings" items={DATA_VIEWS} active={dataView} onChange={(key) => setDataView(key as typeof dataView)} />
                <div id={`data-panel-${dataView}`} role="tabpanel" aria-labelledby={`data-tab-${dataView}`}>
                  {dataView === "connections" ? <ConnectionsSection /> : <ScanSection />}
                </div>
              </div>
            ) : null}
            {tab === "intelligence" ? (
              <div className={styles.section}>
                <SectionTabs scope="intelligence" label="Intelligence settings" items={INTELLIGENCE_VIEWS} active={intelligenceView} onChange={(key) => setIntelligenceView(key as typeof intelligenceView)} />
                <div id={`intelligence-panel-${intelligenceView}`} role="tabpanel" aria-labelledby={`intelligence-tab-${intelligenceView}`}>
                  {intelligenceView === "ai" ? <IntelligenceSection /> : <ServicesSection />}
                </div>
              </div>
            ) : null}
            {tab === "governance" ? (
              <div className={styles.section}>
                <SectionTabs scope="policy" label="Policy and rule settings" items={GOVERNANCE_VIEWS} active={governanceView} onChange={(key) => setGovernanceView(key as typeof governanceView)} />
                <div id={`policy-panel-${governanceView}`} role="tabpanel" aria-labelledby={`policy-tab-${governanceView}`}>
            {governanceView === "modernization" ? (
              <GovernanceSection initialView={searchParams.get("area")} />
            ) : governanceView === "code" ? (
              <CodePoliciesSection />
            ) : (
              <ArchitectureProfilesSection />
            )}
                </div>
              </div>
            ) : null}
            {tab === "access" ? <MembersSection /> : null}
          </div>
        </div>
      </div>
    </div>
  );
}
