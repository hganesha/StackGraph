"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Skeleton } from "@stackgraph/design-system";
import { stackGraphClient } from "@stackgraph/shared";
import { presentRecommendationTitle } from "@/lib/modernizationPresentation";
import { SimulateRecommendation } from "./SimulateRecommendation";
import styles from "./suggested-changes.module.css";

/**
 * Three changes worth simulating, above the fold.
 *
 * Phase 2 §8 calls this the answer to the blank-page problem, and R15 revised the
 * estate fold from "three findings" to "three simulatable changes" — the difference
 * being that a finding ends in a link and a change ends in an action.
 *
 * Estate opened onto four count tiles. Four counts are inventory, not intelligence, and
 * nobody's first question is how many repositories they have. This sits above them.
 *
 * Only recommendations that can actually be compiled belong here, and the compile call
 * is what decides that — so a row that cannot produce a valid proposal shows its gate
 * on click rather than being silently filtered out. Hiding an uncompilable
 * recommendation would make the fold look healthier than the estate is.
 */
/** Sentence case, never a lower-cased enum (§4). */
const ACTION_LABEL: Record<string, string> = {
  CONSOLIDATE: "Consolidate",
  REPLACE: "Replace",
  UPGRADE: "Upgrade",
  REFACTOR: "Refactor",
  INVESTIGATE: "Investigate",
};

/**
 * A small budget on purpose. The fold is three things worth doing next, not a plan —
 * the plan lives on Modernization, where the budget is the reader's to move.
 */
const FOLD_BUDGET_POINTS = 21;

export function SuggestedChanges() {
  const scenario = useQuery({
    queryKey: ["modernization", "scenario", FOLD_BUDGET_POINTS],
    queryFn: () =>
      stackGraphClient.optimizeModernizationScenario({ budget_points: FOLD_BUDGET_POINTS }),
    staleTime: 300_000,
  });

  if (scenario.isLoading) {
    return (
      <section className={styles.panel} aria-label="Suggested changes">
        <Skeleton height={18} width="30%" />
        <Skeleton height={92} />
      </section>
    );
  }

  const recommendations = (scenario.data?.items ?? [])
    .filter((item) => item.selected)
    .slice(0, 3);

  // The fold is additive. If the optimiser has nothing to propose, the estate below is
  // unchanged rather than carrying an empty promise above it.
  if (scenario.isError || !recommendations.length) {
    return null;
  }

  return (
    <section className={styles.panel} aria-labelledby="suggested-changes-heading">
      <div className={styles.head}>
        <h2 id="suggested-changes-heading">Worth changing</h2>
        <Link href="/modernization">See everything</Link>
      </div>
      <ul className={styles.list}>
        {recommendations.map((item) => (
          <li key={item.recommendation_id}>
            <span className={styles.severity}>
              {ACTION_LABEL[item.action] ?? item.action}
            </span>
            <div className={styles.body}>
              <strong>{presentRecommendationTitle(item.title)}</strong>
              <small>
                {item.repository.name} · {item.effort_points} pt
                {item.effort_points === 1 ? "" : "s"} of effort
              </small>
            </div>
            <SimulateRecommendation recommendationId={item.recommendation_id} compact />
          </li>
        ))}
      </ul>
      <p className={styles.note}>
        Every one of these was found in your estate. Simulating one compiles it into a
        change and shows what it would touch, without committing anything.
      </p>
    </section>
  );
}
