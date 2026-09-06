"use client";

import { CitationChip, CorroborationMark, Skeleton, Term } from "@stackgraph/design-system";
import type { CriticalGraphEdge } from "@stackgraph/shared";
import { useEntityCriticalEdges } from "@/lib/changeQueries";
import { useEvidenceStore } from "@/lib/evidenceStore";
import styles from "./critical-edges.module.css";

/**
 * The relationships this entity actually rests on, and how well each one is known.
 *
 * `/entities/{id}/critical-edges` has shipped for some time with no client method and
 * no surface, which is why the product could rank *entities* by systemic risk but never
 * say which single relationship carried the risk. An edge is the thing a change breaks;
 * an entity is only where the break shows up.
 *
 * This is also the first place corroboration depth is mandatory rather than decorative
 * (R9′). `supporting_fact_ids.length` is how many independent facts assert the edge, and
 * the whole "prefer fewer trustworthy edges over a huge noisy graph" preference is only
 * real if a one-source edge visibly looks weaker than a four-source one.
 */
function metricLabel(key: string | undefined): string {
  if (!key) return "Relationship";
  const words = key.replaceAll("-", " ").replaceAll("_", " ").replaceAll(".", " · ").trim();
  return words.charAt(0).toUpperCase() + words.slice(1);
}

/** Primitive component entries only — an object rendered as JSON is machine output. */
function componentReadings(components: unknown): Array<[string, string]> {
  if (!components || typeof components !== "object") return [];
  return Object.entries(components as Record<string, unknown>)
    .filter(([, v]) => typeof v === "string" || typeof v === "number" || typeof v === "boolean")
    .map(([k, v]) => [k.replaceAll("_", " "), String(v)]);
}

function EdgeRow({ edge }: { edge: CriticalGraphEdge }) {
  const openEvidence = useEvidenceStore((state) => state.open);
  const sources = edge.supporting_fact_ids?.length ?? 0;
  const readings = componentReadings(edge.components);

  return (
    <li className={styles.row}>
      <div className={styles.edge}>
        <span className={`${styles.node} sg-mono`}>{edge.source.name}</span>
        <span className={styles.arrow} aria-hidden="true">→</span>
        <span className={`${styles.node} sg-mono`}>{edge.target.name}</span>
      </div>
      <div className={styles.meta}>
        <span className={styles.metric}>{metricLabel(edge.metric_key)}</span>
        <span className={`${styles.score} sg-mono`} title={`Score ${edge.score}`}>
          {Math.round((edge.score ?? 0) * 100)}
        </span>
        {/* Mandatory here, not decorative: this edge can enter a simulation. */}
        <CorroborationMark sources={sources} />
        <span className={styles.sources}>
          {sources === 0
            ? "No corroborating fact"
            : `${sources} corroborating fact${sources === 1 ? "" : "s"}`}
        </span>
      </div>
      {readings.length ? (
        <p className={styles.readings}>
          {readings.map(([key, value]) => `${key} ${value}`).join(" · ")}
        </p>
      ) : null}
      {edge.fact_id ? (
        <div className={styles.evidence}>
          <CitationChip
            label="Evidence"
            onOpen={() => openEvidence(edge.fact_id, `${edge.source.name} → ${edge.target.name}`)}
          />
        </div>
      ) : null}
    </li>
  );
}

export function CriticalEdges({ entityId }: { entityId: string }) {
  const query = useEntityCriticalEdges(entityId);

  if (query.isLoading) {
    return (
      <section className={styles.panel} aria-labelledby={`critical-edges-${entityId}`}>
        <Skeleton height={22} width="40%" />
        <Skeleton height={140} />
      </section>
    );
  }

  if (query.isError || !query.data) {
    return (
      <section className={styles.panel} aria-labelledby={`critical-edges-${entityId}`}>
        <h3 id={`critical-edges-${entityId}`}>Relationships this rests on</h3>
        <p className={styles.quiet} role="alert">
          Critical edges are temporarily unavailable. Everything else on this page still works.
        </p>
      </section>
    );
  }

  const edges = query.data.edges ?? [];
  // A weakly corroborated edge in a high-scoring position is the finding, so it leads.
  const weakest = edges.filter((edge) => (edge.supporting_fact_ids?.length ?? 0) <= 1).length;

  return (
    <section className={styles.panel} aria-labelledby={`critical-edges-${entityId}`}>
      <header className={styles.head}>
        <div>
          <h3 id={`critical-edges-${entityId}`}>Relationships this rests on</h3>
          <p>
            The individual relationships carrying the most weight, and how many independent
            facts assert each one. <Term id="corroboration">Corroboration</Term> is what
            separates a relationship worth simulating from a guess.
          </p>
        </div>
      </header>

      {edges.length ? (
        <>
          {weakest > 0 ? (
            <p className={styles.weakest}>
              {weakest} of these {edges.length} rest{weakest === 1 ? "s" : ""} on a single
              fact. A change simulated across {weakest === 1 ? "it" : "them"} is only as good
              as that one source.
            </p>
          ) : null}
          <ul className={styles.list}>
            {edges.map((edge) => (
              <EdgeRow key={`${edge.source.id}:${edge.target.id}:${edge.metric_key}`} edge={edge} />
            ))}
          </ul>
        </>
      ) : (
        <p className={styles.quiet}>
          No relationship here scored highly enough to be called critical. That is a result,
          not a gap — this entity does not sit on a load-bearing edge.
        </p>
      )}

      {query.data.limitations?.map((limitation, index) => (
        <p className={styles.quiet} key={`limitation-${index}`}>
          {String(
            (limitation as Record<string, unknown>).message ??
              (limitation as Record<string, unknown>).code ??
              "This ranking has a coverage limitation.",
          )}
        </p>
      ))}
    </section>
  );
}
