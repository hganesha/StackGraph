"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { RankedTable, StatTile, Skeleton } from "@stackgraph/design-system";
import { stackGraphClient } from "@stackgraph/shared";
import { useModernization } from "@/lib/queries";
import { DeterministicInsightsPanel } from "@/components/insights/DeterministicInsightsPanel";
import styles from "./modernization.module.css";

export default function ModernizationPage() {
  const router = useRouter();
  const [budgetPoints, setBudgetPoints] = useState(21);
  const { data, isLoading } = useModernization();
  const scenario = useQuery({
    queryKey: ["modernization", "scenario", budgetPoints],
    queryFn: () => stackGraphClient.optimizeModernizationScenario({ budget_points: budgetPoints }),
  });
  const selectedItems = scenario.data?.items.filter((item) => item.selected) ?? [];
  const repositoryByRecommendation = new Map(
    scenario.data?.items.map((item) => [item.recommendation_id, item.repository.id]) ?? [],
  );
  const opportunities = data?.opportunities ?? [];
  const governed = opportunities.length > 0 && opportunities.every(
    (item) => !item.priority.method_version.includes("unconfigured"),
  );

  return (
    <div className={styles.page}>
      <header className={styles.head}>
        <h1 className={styles.title}>Modernization</h1>
        <p className={styles.subtitle}>What to do, in what order — ranked by opportunity, not by noise.</p>
      </header>

      <aside className={styles.investigative} aria-label="Pilot recommendation status">
        <strong>{governed ? "Governed portfolio scoring is active." : "Investigative during the pilot."}</strong>{" "}
        {governed
          ? "The active tenant policy and calibration corpus determine ranking and budget selection."
          : "Rankings support review and discovery until tenant policy and calibration are approved."}
      </aside>

      <section className={styles.hero} aria-label="Portfolio metrics">
        {isLoading || !data ? (
          <div className={styles.heroSkeleton}>
            <Skeleton height={12} width={140} />
            <Skeleton height={40} width={80} />
          </div>
        ) : (
          <div className={styles.metrics}>
            <StatTile label="Open opportunities" value={data.opportunities.length} hero sub="ranked by priority" />
            <StatTile label="Selected in scenario" value={selectedItems.length} sub={`${scenario.data?.used_points ?? 0} effort points`} />
            <StatTile label="Scenario value" value={Math.round(scenario.data?.total_score ?? 0)} sub="aggregate governed score" />
          </div>
        )}
      </section>

      <DeterministicInsightsPanel
        title="Current evidence findings"
        description="Portfolio-wide dependency, reachability, runtime, and deployment findings derived from current graph facts. Priority is calculated independently from evidence coverage."
        limit={50}
        showFilters
      />

      <section className={styles.scenario} aria-labelledby="scenario-title">
        <div>
          <h2 id="scenario-title">Budget scenario</h2>
          <p>Select the highest-value compatible portfolio within an effort-point ceiling.</p>
        </div>
        <label className={styles.budgetControl}>
          <span>Budget</span>
          <input
            type="range"
            min={0}
            max={100}
            step={1}
            value={budgetPoints}
            onChange={(event) => setBudgetPoints(Number(event.target.value))}
          />
          <output>{budgetPoints} points</output>
        </label>
        {scenario.isError ? (
          <p className={styles.scenarioError}>The scenario could not be calculated. The ranked portfolio remains available below.</p>
        ) : selectedItems.length > 0 ? (
          <ol className={styles.selectionList}>
            {selectedItems.map((item) => (
              <li key={item.recommendation_id}>
                <button type="button" onClick={() => router.push(`/repositories/${item.repository.id}`)}>
                  <span><strong>{item.title}</strong><small>{item.repository.name} · {item.action.toLowerCase()}</small></span>
                  <span className={styles.selectionScore}>{item.score.toFixed(1)}<small>{item.effort_points} pts</small></span>
                </button>
              </li>
            ))}
          </ol>
        ) : (
          <p className={styles.scenarioEmpty}>{scenario.isLoading ? "Optimizing scenario…" : "Increase the budget to select an opportunity."}</p>
        )}
      </section>

      <section aria-label="Opportunities">
        {isLoading || !data ? (
          <div className={styles.tableSkeleton}>
            {[0, 1, 2].map((i) => (
              <Skeleton key={i} height={40} />
            ))}
          </div>
        ) : data.opportunities.length === 0 ? (
          <div className={styles.empty}>
            <p className={styles.emptyTitle}>No modernization opportunities surfaced yet.</p>
            <p className={styles.emptyBody}>
              Opportunities appear as assessments run across the estate — unsupported runtimes, deprecated
              packages, and consolidation candidates rank here first.
            </p>
          </div>
        ) : (
          <RankedTable
            caption="Ranked modernization opportunities"
            items={data.opportunities}
            renderRowHref={(item) => {
              const repositoryId = repositoryByRecommendation.get(item.id);
              return repositoryId ? `/repositories/${repositoryId}` : "/reviews";
            }}
            onOpen={(item) => {
              const repositoryId = repositoryByRecommendation.get(item.id);
              router.push(repositoryId ? `/repositories/${repositoryId}` : "/reviews");
            }}
          />
        )}
      </section>
    </div>
  );
}
