"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { RankedTable, Skeleton } from "@stackgraph/design-system";
import { stackGraphClient } from "@stackgraph/shared";
import { useModernization } from "@/lib/queries";
import { presentRecommendationSummary, presentRecommendationTitle } from "@/lib/modernizationPresentation";
import styles from "./modernization.module.css";

const INITIAL_OPPORTUNITY_COUNT = 10;

export default function ModernizationPage() {
  const router = useRouter();
  const [budgetPoints, setBudgetPoints] = useState(21);
  const [showAllOpportunities, setShowAllOpportunities] = useState(false);
  const { data, isLoading } = useModernization();
  const scenario = useQuery({
    queryKey: ["modernization", "scenario", budgetPoints],
    queryFn: () => stackGraphClient.optimizeModernizationScenario({ budget_points: budgetPoints }),
  });
  const selectedItems = scenario.data?.items.filter((item) => item.selected) ?? [];
  const repositoryByRecommendation = new Map(
    scenario.data?.items.map((item) => [item.recommendation_id, item.repository.id]) ?? [],
  );
  const opportunities = (data?.opportunities ?? []).map((item) => ({
    ...item,
    name: presentRecommendationTitle(item.name),
    summary: presentRecommendationSummary(item.summary),
  }));
  const visibleOpportunities = showAllOpportunities
    ? opportunities
    : opportunities.slice(0, INITIAL_OPPORTUNITY_COUNT);
  const governed = opportunities.length > 0 && opportunities.every(
    (item) => !item.priority.method_version.includes("unconfigured"),
  );
  const usedPoints = scenario.data?.used_points ?? 0;
  const remainingPoints = Math.max(0, budgetPoints - usedPoints);

  return (
    <div className={styles.page}>
      <header className={styles.head}>
        <h1 className={styles.title}>Modernization</h1>
        <p className={styles.subtitle}>
          Modernization opportunities across the estate, ranked by priority, with the effort each one carries.
        </p>
      </header>

      <aside className={styles.status} aria-label="Recommendation status">
        <span className={styles.eyebrow}>Recommendation status</span>
        <div>
          <strong>{governed ? "Governed scoring active" : "Pilot guidance"}</strong>
          <p>
            {governed
              ? "Rankings follow the active policy and approved calibration set."
              : "Use these rankings to focus review; final decisions still need approval."}
          </p>
        </div>
      </aside>

      <section className={styles.plan} aria-labelledby="scenario-title">
        <div className={styles.planHeader}>
          <div className={styles.sectionIntro}>
            <span className={styles.eyebrow}>Budget scenario</span>
            <h2 id="scenario-title">Recommended plan</h2>
            <p>Set an effort budget to see which initiatives fit inside it.</p>
          </div>
          <label className={styles.budgetControl}>
            <span className={styles.budgetLabel}>Effort budget</span>
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
        </div>

        {isLoading || !data ? (
          <div className={styles.planSkeleton}>
            <Skeleton height={64} />
            <Skeleton height={56} />
          </div>
        ) : (
          <dl className={styles.planStats} aria-label="Plan summary">
            <div>
              <dt>Open opportunities</dt>
              <dd>{opportunities.length}</dd>
            </div>
            <div>
              <dt>Recommended now</dt>
              <dd>{selectedItems.length}</dd>
            </div>
            <div>
              <dt>Effort used</dt>
              <dd>{usedPoints}<span> / {budgetPoints}</span></dd>
            </div>
            <div>
              <dt>Portfolio value</dt>
              <dd>{Math.round(scenario.data?.total_score ?? 0)}</dd>
            </div>
          </dl>
        )}

        {scenario.isError ? (
          <p className={styles.scenarioError}>The scenario could not be calculated. The ranked portfolio remains available below.</p>
        ) : selectedItems.length > 0 ? (
          <div className={styles.selection}>
            <div className={styles.selectionHeader}>
              <h3>{selectedItems.length} {selectedItems.length === 1 ? "initiative" : "initiatives"} fit this budget</h3>
              <span>{remainingPoints} {remainingPoints === 1 ? "point" : "points"} remaining</span>
            </div>
            <ol className={styles.selectionList}>
              {selectedItems.map((item, index) => (
                <li key={item.recommendation_id}>
                  <button
                    type="button"
                    onClick={() => router.push(`/repositories/${item.repository.id}?recommendation=${item.recommendation_id}`)}
                  >
                    <span className={styles.selectionRank} aria-hidden="true">{index + 1}</span>
                    <span className={styles.selectionDetails}>
                      <strong>{presentRecommendationTitle(item.title)}</strong>
                      <small>{item.repository.name} · {item.action.toLowerCase()}</small>
                    </span>
                    <span className={styles.selectionMeta}>
                      <strong>{item.effort_points} pts</strong>
                      <small>Value {item.score.toFixed(1)}</small>
                    </span>
                  </button>
                </li>
              ))}
            </ol>
          </div>
        ) : (
          <p className={styles.scenarioEmpty}>{scenario.isLoading ? "Optimizing scenario…" : "Increase the budget to select an opportunity."}</p>
        )}
      </section>

      <section className={styles.opportunities} aria-labelledby="opportunities-title">
        <div className={styles.opportunityHeader}>
          <div className={styles.sectionIntro}>
            <span className={styles.eyebrow}>Full list</span>
            <h2 id="opportunities-title">Ranked opportunities</h2>
            <p>Start with the highest-priority items, then open a repository to review the evidence.</p>
          </div>
          {!isLoading && data ? <span className={styles.total}>{opportunities.length} total</span> : null}
        </div>
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
            caption={`Showing ${visibleOpportunities.length} of ${opportunities.length} opportunities`}
            items={visibleOpportunities}
            renderRowHref={(item) => {
              const repositoryId = repositoryByRecommendation.get(item.id);
              return repositoryId
                ? `/repositories/${repositoryId}?recommendation=${item.id}`
                : "/reviews";
            }}
            onOpen={(item) => {
              const repositoryId = repositoryByRecommendation.get(item.id);
              router.push(
                repositoryId
                  ? `/repositories/${repositoryId}?recommendation=${item.id}`
                  : "/reviews",
              );
            }}
          />
        )}
        {opportunities.length > INITIAL_OPPORTUNITY_COUNT ? (
          <button
            type="button"
            className={styles.showMore}
            onClick={() => setShowAllOpportunities((current) => !current)}
          >
            {showAllOpportunities
              ? "Show top 10 opportunities"
              : `Show all ${opportunities.length} opportunities`}
          </button>
        ) : null}
      </section>
    </div>
  );
}
