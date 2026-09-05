"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import {
  formatRelative,
  type EntityGraphIntelligence,
  type GraphMetric,
  type Namespace,
} from "@stackgraph/shared";
import { Drawer, Skeleton, Term, type GlossaryKey } from "@stackgraph/design-system";
import {
  useEntityBlastRadius,
  useGraphIntelligenceCommunities,
  useGraphNeighborhood,
  useSimilarApplications,
} from "@/lib/queries";
import { ImpactPath, type ImpactHop } from "./ImpactPath";
import { SimilarityDecision } from "@/components/reviews/SimilarityDecision";
import { useEvidenceStore } from "@/lib/evidenceStore";
import styles from "./graph-intelligence-summary.module.css";

/**
 * Each metric carries the word it should be read with. The structural vocabulary —
 * blast radius, centrality, single point of failure — is the least self-explanatory
 * language in the product, so it is defined in place rather than left as a label.
 */
const METRIC_LABELS: Record<string, { label: string; term?: GlossaryKey }> = {
  "reachability.upstream_impact": { label: "Upstream impact", term: "blastRadius" },
  "reachability.downstream_dependencies": { label: "Dependencies" },
  "reachability.upstream_depth": { label: "Impact depth" },
  "reachability.downstream_depth": { label: "Dependency depth" },
  // The algorithm name is the gloss, not the label. A reader needs to know what the
  // number says about their estate, not which paper it came from (§4).
  "centrality.pagerank": { label: "How central", term: "centrality" },
  "centrality.betweenness": { label: "How often on the path between others", term: "centrality" },
  // Not "Single point of failure": that is the panel's own headline status, and a
  // metric row repeating it verbatim reads as the same claim made twice. This says what
  // the metric measures — the gloss carries the term.
  "structure.articulation_point": { label: "Splits the estate if removed", term: "articulationPoint" },
  "degree.in": { label: "Dependents" },
  "degree.out": { label: "Direct dependencies" },
};

const STATUS_LABELS: Record<EntityGraphIntelligence["primary_status"], string> = {
  // "Structurally critical" is what the model calls it; "single point of failure" is
  // what it means, and it is the phrase that gets a room's attention.
  STRUCTURALLY_CRITICAL: "Single point of failure",
  ELEVATED: "Elevated",
  TYPICAL: "Typical",
  WAITING_FOR_DATA: "Needs more data",
};

/** Sentence case, never a lower-cased enum. */
const REVIEW_STATE_LABELS: Record<string, string> = {
  CONFIRMED: "Confirmed",
  POSSIBLE: "Possible",
  REJECTED: "Rejected",
  NOT_APPLICABLE: "Not applicable",
  UNREVIEWED: "Not reviewed yet",
};

function displayMetric(metric: GraphMetric) {
  if (metric.metric_key === "structure.articulation_point") {
    return metric.numeric_value === 1 ? "Yes" : "No";
  }
  if (metric.numeric_value == null) return "—";
  if (metric.metric_key.includes("pagerank") || metric.metric_key.includes("betweenness")) {
    return metric.numeric_value.toLocaleString(undefined, { maximumFractionDigits: 4 });
  }
  return metric.numeric_value.toLocaleString(undefined, { maximumFractionDigits: 1 });
}

function displayDetail(value: unknown): string {
  if (Array.isArray(value)) return value.map(String).join(" · ");
  if (value && typeof value === "object") {
    return Object.entries(value as Record<string, unknown>)
      .map(([key, nested]) => `${key}: ${displayDetail(nested)}`)
      .join(" · ");
  }
  return value == null || value === "" ? "Not observed" : String(value);
}

function limitationText(limitation: Record<string, unknown>, fallback: string): string {
  return String(limitation.message ?? limitation.code ?? fallback);
}

/** Limitations belong beside the number they qualify, not behind a link to go looking. */
function Limitations({
  limitations,
  fallback,
}: {
  limitations: Array<Record<string, unknown>>;
  fallback: string;
}) {
  if (!limitations.length) return null;
  return (
    <>
      {limitations.map((limitation, index) => (
        <p key={`${String(limitation.code ?? "limitation")}:${index}`} className={styles.limitation}>
          {limitationText(limitation, fallback)}
        </p>
      ))}
    </>
  );
}

function DetailList({ label, details }: { label: string; details: Record<string, unknown> }) {
  const entries = Object.entries(details);
  if (!entries.length) return null;
  return (
    <div className={styles.similarityDetails}>
      <h4>{label}</h4>
      <dl>
        {entries.map(([key, value]) => (
          <div key={key}><dt>{key.replaceAll("_", " ")}</dt><dd>{displayDetail(value)}</dd></div>
        ))}
      </dl>
    </div>
  );
}

export function GraphIntelligenceSummary({
  entityId,
  intelligence,
  graphHref,
  compact = false,
  similarityAvailable = false,
}: {
  entityId: string;
  intelligence?: EntityGraphIntelligence | null;
  graphHref: string;
  compact?: boolean;
  similarityAvailable?: boolean;
}) {
  const [showBlastRadius, setShowBlastRadius] = useState(false);
  const [showSimilarity, setShowSimilarity] = useState(false);
  const blastRadius = useEntityBlastRadius(entityId, showBlastRadius);
  // Names for the hops between the subject and its target. Depth 2 covers most paths
  // the traversal returns; anything beyond it renders as an unnamed step rather than
  // as a UUID. Fetched only while the drawer is open.
  const neighborhood = useGraphNeighborhood(entityId, 2, { enabled: showBlastRadius });
  const communityKey = intelligence?.community_keys?.[0];
  const communities = useGraphIntelligenceCommunities({ enabled: Boolean(communityKey) });
  const similarity = useSimilarApplications(entityId, showSimilarity && similarityAvailable);
  const openEvidence = useEvidenceStore((state) => state.open);
  const metrics = useMemo(
    () => (intelligence?.metrics ?? [])
      .filter((metric) => METRIC_LABELS[metric.metric_key])
      .sort((left, right) => (right.percentile ?? -1) - (left.percentile ?? -1))
      .slice(0, compact ? 4 : 6),
    [compact, intelligence?.metrics],
  );

  const waiting = !intelligence || intelligence.primary_status === "WAITING_FOR_DATA";
  const community = useMemo(
    () => communities.data?.communities.find((entry) => entry.community_key === communityKey),
    [communities.data, communityKey],
  );
  // Representative entities include the subject itself; peers are the rest.
  const peers = useMemo(
    () => (community?.representative_entities ?? []).filter((entity) => entity.id !== entityId).slice(0, 3),
    [community, entityId],
  );
  // A hop is only nameable if it is in the neighbourhood we loaded. Everything else
  // renders as an unnamed step — never as its id.
  const nodesById = useMemo(() => {
    const index = new Map<string, { name: string; domain: Namespace }>();
    for (const node of neighborhood.data?.nodes ?? []) {
      index.set(node.id, { name: node.label, domain: node.namespace });
    }
    return index;
  }, [neighborhood.data]);

  // Snapshot limitations qualify the same numbers the entity limitations do, so they
  // are shown together rather than hidden one drawer away.
  const limitations = useMemo(
    () => [
      ...(intelligence?.limitations ?? []),
      ...(intelligence?.snapshots ?? []).flatMap((snapshot) => snapshot.limitations),
    ],
    [intelligence?.limitations, intelligence?.snapshots],
  );

  return (
    <section className={styles.panel} aria-labelledby={`graph-intelligence-${entityId}`}>
      <header className={styles.head}>
        <div>
          <span className={styles.eyebrow}>Graph intelligence</span>
          <h2 id={`graph-intelligence-${entityId}`}>{waiting ? "Waiting for a complete graph snapshot" : STATUS_LABELS[intelligence.primary_status]}</h2>
        </div>
        {intelligence ? (
          <span className={styles.freshness}>
            <Term id="analysisSnapshot">Snapshot</Term> {formatRelative(intelligence.as_of)}
          </span>
        ) : null}
      </header>

      {waiting ? (
        <p className={styles.waiting}>
          StackGraph will classify this entity after its tenant projection catches up and a complete runtime-dependency analysis succeeds.
        </p>
      ) : (
        <>
          <div className={styles.metrics}>
            {metrics.map((metric) => {
              const meta = METRIC_LABELS[metric.metric_key];
              return (
                <div key={`${metric.analysis_run_id}:${metric.metric_key}`} className={styles.metric}>
                  <span>{meta?.term ? <Term id={meta.term}>{meta.label}</Term> : meta?.label ?? metric.metric_key}</span>
                  <strong className="sg-mono">{displayMetric(metric)}</strong>
                  <small>{metric.percentile == null ? "Percentile unavailable" : `${Math.round(metric.percentile * 100)}th estate percentile`}</small>
                </div>
              );
            })}
          </div>
          {intelligence.reasons.length ? (
            <ul className={styles.reasons}>
              {intelligence.reasons.slice(0, 2).map((reason) => <li key={reason}>{reason}</li>)}
            </ul>
          ) : null}
        </>
      )}

      {communityKey && community ? (
        <p className={styles.community}>
          Sits in a <Term id="community">community</Term> of {community.member_count.toLocaleString()}{" "}
          {community.member_count === 1 ? "entity" : "entities"} that depend on each other
          {peers.length ? <> — alongside {peers.map((peer) => peer.name).join(", ")}</> : null}.{" "}
          <span className={styles.communityAlgorithm}>
            Grouped by {communities.data?.algorithm_key ?? "algorithm"} from the graph's shape, not by ownership.
          </span>
        </p>
      ) : null}

      <Limitations limitations={limitations} fallback="This entity's structural coverage is limited." />

      <div className={styles.actions}>
        <button type="button" onClick={() => setShowBlastRadius(true)} disabled={waiting}>View blast radius</button>
        <Link href={graphHref}>Explore dependencies</Link>
        {similarityAvailable ? <button type="button" onClick={() => setShowSimilarity(true)}>Similar applications</button> : null}
      </div>

      <Drawer
        open={showBlastRadius}
        onClose={() => setShowBlastRadius(false)}
        title="Blast radius"
        labelId="blast-radius-heading"
      >
        <div className={styles.drawerBody}>
          <p className={styles.eyebrow}>Evidence-backed traversal</p>
          {blastRadius.isLoading ? (
            <div className={styles.drawerLoading}><Skeleton height={72} /><Skeleton height={160} /></div>
          ) : blastRadius.isError || !blastRadius.data ? (
            <p className={styles.waiting} role="alert">Blast radius is temporarily unavailable. The last entity snapshot remains visible.</p>
          ) : (
            <>
              <dl className={styles.blastFacts}>
                <div><dt>Affected entities</dt><dd>{blastRadius.data.affected_entity_count}</dd></div>
                <div><dt>Maximum depth</dt><dd>{blastRadius.data.maximum_depth}</dd></div>
              </dl>
              {blastRadius.data.impacts.length ? (
                <ol className={styles.paths}>
                  {blastRadius.data.impacts.map((impact) => {
                    const hops: ImpactHop[] = impact.entity_ids.map((id, index) => {
                      const node = nodesById.get(id);
                      const isSubject = index === 0 && id === blastRadius.data.entity.id;
                      const isTarget = index === impact.entity_ids.length - 1 && id === impact.target.id;
                      return {
                        id,
                        name: isSubject
                          ? blastRadius.data.entity.name
                          : isTarget
                            ? impact.target.name
                            : node?.name ?? null,
                        domain: node?.domain,
                        kind: isTarget ? impact.target.kind : isSubject ? blastRadius.data.entity.kind : undefined,
                      };
                    });
                    return (
                      <li key={`${impact.target.id}:${impact.entity_ids.join(":")}`}>
                        <ImpactPath
                          hops={hops}
                          distance={impact.distance}
                          minimumConfidence={impact.minimum_confidence}
                          targetName={impact.target.name}
                          targetDomain={nodesById.get(impact.target.id)?.domain}
                        />
                        {/* The best thing in this drawer already. Left exactly as it was. */}
                        <div className={styles.facts}>
                          {impact.supporting_fact_ids.map((factId) => (
                            <button key={factId} type="button" onClick={() => openEvidence(factId, `Blast-radius path fact ${factId.slice(0, 8)}`)}>
                              Evidence {factId.slice(0, 8)}
                            </button>
                          ))}
                        </div>
                      </li>
                    );
                  })}
                </ol>
              ) : <p className={styles.waiting}>No application or capability impact path is present in this complete snapshot.</p>}
              <Limitations
                limitations={blastRadius.data.limitations}
                fallback="This result has a coverage limitation."
              />
            </>
          )}
        </div>
      </Drawer>

      <Drawer
        open={showSimilarity}
        onClose={() => setShowSimilarity(false)}
        title="Similar applications"
        labelId="similarity-heading"
      >
        <div className={styles.drawerBody}>
          <p className={styles.eyebrow}>Governed portfolio signal</p>
          {similarity.isLoading ? (
            <div className={styles.drawerLoading}><Skeleton height={120} /><Skeleton height={120} /></div>
          ) : similarity.isError || !similarity.data ? (
            <p className={styles.waiting} role="alert">Similarity is unavailable until an evaluated semantic space and enough application context are active.</p>
          ) : similarity.data.candidates.length ? (
            <>
              <p className={styles.waiting}>
                <Term id="semanticSimilarity">Scores</Term> combine semantic meaning, rare dependencies, capabilities, and technology context. Review the evidence below before making a consolidation decision.
              </p>
              <ol className={styles.similarityList}>
                {similarity.data.candidates.map((candidate) => (
                  <li key={candidate.id}>
                    <header>
                      <div><strong>{candidate.application.name}</strong><span>{REVIEW_STATE_LABELS[candidate.review_state] ?? candidate.review_state}</span></div>
                      <span className="sg-mono">{Math.round(candidate.score * 100)}%</span>
                    </header>
                    <DetailList label="Why it matches" details={candidate.overlaps} />
                    <DetailList label="What is different" details={candidate.differences} />
                    <DetailList label="Signal coverage" details={candidate.coverage} />
                    <Limitations
                      limitations={candidate.limitations}
                      fallback="A similarity input is incomplete."
                    />
                    <div className={styles.candidateActions}>
                      <Link href={`/applications/${candidate.application.id}`}>Open application</Link>
                    </div>
                    {candidate.review_state === "UNREVIEWED" ? (
                      <SimilarityDecision
                        candidateId={candidate.id}
                        confidence={candidate.score}
                        entityId={entityId}
                      />
                    ) : null}
                  </li>
                ))}
              </ol>
              <Limitations
                limitations={similarity.data.limitations}
                fallback="This result has a coverage limitation."
              />
            </>
          ) : <p className={styles.waiting}>No sufficiently similar applications are present in the evaluated candidate set.</p>}
        </div>
      </Drawer>
    </section>
  );
}
