"use client";

import { useMemo } from "react";
import type { RepositoryActivityContributor } from "@stackgraph/shared";
import styles from "./change-actor-mix.module.css";

/**
 * Who and what is changing this repository, by class.
 *
 * `README.md` opens by framing StackGraph as a response to software creation
 * accelerating through coding agents. `RepositoryActivityActor.classification` carries
 * the taxonomy that makes the claim checkable — HUMAN, BOT, DEPENDENCY_BOT,
 * CI_AUTOMATION, AI_AGENT, AI_ASSISTED_HUMAN, UNKNOWN — and until now it shipped to the
 * UI and was rendered nowhere, while a ranked list of named individuals was rendered
 * instead.
 *
 * This is the class-level reading, and it replaces that list deliberately
 * (non-negotiable 16). The integrated plan's own risk table names the failure mode:
 * *"Actor data becomes employee surveillance — purpose limitation, aggregation,
 * retention, RBAC, audit, no individual scoring by default."* A per-person leaderboard
 * of commit counts is individual scoring by default, and it answers a question about
 * people. The question the product exists to answer is about the estate: how much of
 * this is changing by hand, and how much by agent.
 *
 * `classification_basis` and `classification_confidence` carry the evidence class, and
 * they matter: `AI_ASSISTED` from Copilot metadata is a different claim from
 * `POSSIBLY_AI_ASSISTED` inferred from commit style, and the scanner plan is explicit
 * that *"code-style detection by itself should never be considered authoritative."*
 * The Strata rule already encodes this — an authoritative signal is a scanned fact and
 * renders mono, an inferred one is StackGraph's reading and renders sans.
 */
type ActorClass = RepositoryActivityContributor["actor"]["classification"];

const ACTOR_LABEL: Record<ActorClass, string> = {
  HUMAN: "By hand",
  AI_ASSISTED_HUMAN: "AI-assisted",
  AI_AGENT: "Agent",
  DEPENDENCY_BOT: "Dependency bot",
  CI_AUTOMATION: "Automation",
  BOT: "Other bot",
  UNKNOWN: "Unattributed",
};

/** Fixed order, so the mix reads the same on every repository. */
const ACTOR_ORDER: ActorClass[] = [
  "HUMAN",
  "AI_ASSISTED_HUMAN",
  "AI_AGENT",
  "DEPENDENCY_BOT",
  "CI_AUTOMATION",
  "BOT",
  "UNKNOWN",
];

/**
 * Below this many attributed events, a share is a coincidence rather than a mix.
 * Publishing "50% agent" from two commits would be worse than publishing nothing.
 */
const MINIMUM_EVENTS = 8;

export function ChangeActorMix({
  contributors,
  windowLabel,
}: {
  contributors: RepositoryActivityContributor[];
  windowLabel: string;
}) {
  const { rows, total, inferredShare } = useMemo(() => {
    const counts = new Map<ActorClass, number>();
    let events = 0;
    let inferred = 0;
    for (const contributor of contributors) {
      const cls = contributor.actor.classification;
      const n = contributor.total_events || 0;
      counts.set(cls, (counts.get(cls) ?? 0) + n);
      events += n;
      // Anything not asserted at high confidence is StackGraph's reading, not a fact.
      if ((contributor.actor.classification_confidence ?? 0) < 0.85) inferred += n;
    }
    return {
      rows: ACTOR_ORDER.filter((cls) => (counts.get(cls) ?? 0) > 0).map((cls) => ({
        cls,
        count: counts.get(cls) ?? 0,
        share: events > 0 ? (counts.get(cls) ?? 0) / events : 0,
      })),
      total: events,
      inferredShare: events > 0 ? inferred / events : 0,
    };
  }, [contributors]);

  if (total < MINIMUM_EVENTS) {
    return (
      <aside className={styles.panel} aria-labelledby="actor-mix-heading">
        <h3 id="actor-mix-heading">What is changing this</h3>
        <p className={styles.quiet}>
          {total === 0
            ? "No attributed changes in this window."
            : `Too few attributed changes in this window to state a mix — ${total} of a minimum ${MINIMUM_EVENTS}. A share drawn from this little would be a coincidence.`}
        </p>
      </aside>
    );
  }

  return (
    <aside className={styles.panel} aria-labelledby="actor-mix-heading">
      <div className={styles.head}>
        <h3 id="actor-mix-heading">What is changing this</h3>
        <span className={styles.window}>{windowLabel}</span>
      </div>

      <ul className={styles.rows}>
        {rows.map((row) => (
          <li key={row.cls}>
            <span className={styles.label}>{ACTOR_LABEL[row.cls]}</span>
            <span className={styles.bar} aria-hidden="true">
              <span className={styles.fill} style={{ inlineSize: `${row.share * 100}%` }} />
            </span>
            <span className={`${styles.share} sg-mono`}>{Math.round(row.share * 100)}%</span>
            {/* The denominator travels with every rate (non-negotiable 17). */}
            <span className={styles.count}>
              {row.count} of {total}
            </span>
          </li>
        ))}
      </ul>

      {inferredShare > 0 ? (
        <p className={styles.quiet}>
          {Math.round(inferredShare * 100)}% of these are StackGraph&apos;s reading rather
          than an authoritative signal from the source. Commit style alone is never treated
          as proof of authorship.
        </p>
      ) : null}
      {/* Stated once, on the surface, rather than only in a policy document. */}
      <p className={styles.quiet}>
        Shown by class. StackGraph does not score individuals.
      </p>
    </aside>
  );
}
