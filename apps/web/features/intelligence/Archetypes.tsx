"use client";

import { useMemo } from "react";
import Link from "next/link";
import { IconSpread, Skeleton, Term } from "@stackgraph/design-system";
import type { GraphAnomaly, GraphMotif } from "@stackgraph/shared";
import { useGraphAnomalies, useGraphMotifs } from "@/lib/changeQueries";
import styles from "./archetypes.module.css";

/**
 * The shapes the estate has settled into, and the things that do not fit one.
 *
 * `scanner-improvements.md` §5 asks for this as a distribution — "Serverless SaaS stack
 * 84 apps · Azure enterprise stack 312 apps · Bespoke / anomalous 28 apps" — and frames
 * the payoff as the recommendation that follows: *"these 14 applications appear
 * functionally identical to your standard architecture but use a bespoke deployment
 * pattern."*
 *
 * That plan puts archetypes behind deployment-profile detection (S2). They do not have
 * to wait for it. `/graph-intelligence/anomalies` already returns a `cohort_key` and a
 * `cohort_size` per entity, and a cohort with a size *is* a distribution. When S2 lands
 * this surface re-points at deployment archetypes and the layout does not move.
 *
 * The one thing to keep right: **an anomalous member is not a fault.** It is an
 * observation that something differs from its peers — the same class of statement as
 * `UNEVALUABLE`, and it takes the same quiet treatment. A bespoke architecture may be
 * the correct answer to a problem nobody else in the estate has.
 */
function cohortLabel(key: string | undefined): string {
  if (!key) return "Unclassified";
  const words = key.replaceAll("-", " ").replaceAll("_", " ").replaceAll(".", " · ").trim();
  return words.charAt(0).toUpperCase() + words.slice(1);
}

function entityHref(entity: { id: string; kind: string }): string {
  if (entity.kind === "Repository") return `/repositories/${entity.id}`;
  if (entity.kind === "Technology" || entity.kind === "Package") return `/technologies/${entity.id}`;
  if (entity.kind === "Application") return `/applications/${entity.id}`;
  return "/estate";
}

interface Cohort {
  key: string;
  label: string;
  size: number;
  outliers: GraphAnomaly[];
}

export function Archetypes() {
  const anomalies = useGraphAnomalies();
  const motifs = useGraphMotifs();

  const cohorts = useMemo<Cohort[]>(() => {
    const byKey = new Map<string, Cohort>();
    for (const anomaly of anomalies.data?.anomalies ?? []) {
      const key = anomaly.cohort_key ?? "unclassified";
      const existing = byKey.get(key);
      if (existing) {
        // `cohort_size` is a property of the cohort, not of the member, so the largest
        // reported value is the cohort's size rather than a sum over its outliers.
        existing.size = Math.max(existing.size, anomaly.cohort_size ?? 0);
        existing.outliers.push(anomaly);
      } else {
        byKey.set(key, {
          key,
          label: cohortLabel(anomaly.cohort_key),
          size: anomaly.cohort_size ?? 0,
          outliers: [anomaly],
        });
      }
    }
    return [...byKey.values()].sort((left, right) => right.size - left.size);
  }, [anomalies.data]);

  const totalMembers = cohorts.reduce((sum, cohort) => sum + cohort.size, 0);
  const totalOutliers = cohorts.reduce((sum, cohort) => sum + cohort.outliers.length, 0);

  if (anomalies.isLoading) {
    return (
      <div className={styles.loading}>
        <Skeleton height={28} width="45%" />
        <Skeleton height={220} />
      </div>
    );
  }

  if (anomalies.isError) {
    return (
      <p className={styles.quiet} role="alert">
        Cohort analysis is temporarily unavailable. The ranked list and canvas still work.
      </p>
    );
  }

  if (!cohorts.length) {
    return (
      <div className={styles.empty} role="status">
        <h2>No cohorts have formed yet</h2>
        <p>
          Cohorts are found from the graph&apos;s own shape, so they need enough of the
          estate scanned to have a shape. Connect more sources and this fills in.
        </p>
      </div>
    );
  }

  return (
    <section className={styles.wrap} aria-labelledby="archetypes-heading">
      <header className={styles.head}>
        <div>
          <h2 id="archetypes-heading">The shapes your estate has settled into</h2>
          <p>
            Entities grouped by how they are built rather than by who owns them. The last
            column is the one to read: an entity that sits far from its own cohort is
            doing something the rest of the group does not.
          </p>
        </div>
        {totalMembers > 0 ? (
          <div className={styles.headline}>
            <strong className={`${styles.display} sg-mono`}>{cohorts.length}</strong>
            <span>cohorts</span>
            <small>{totalOutliers} entities sit outside their own</small>
          </div>
        ) : null}
      </header>

      <table className={styles.table}>
        <caption>
          {cohorts.length} cohort{cohorts.length === 1 ? "" : "s"} across {totalMembers} entities
        </caption>
        <thead>
          <tr>
            <th scope="col">Cohort</th>
            <th scope="col">Members</th>
            <th scope="col">Outside the pattern</th>
          </tr>
        </thead>
        <tbody>
          {cohorts.map((cohort) => (
            <tr key={cohort.key}>
              <th scope="row">{cohort.label}</th>
              <td className="sg-mono">{cohort.size}</td>
              <td className="sg-mono">{cohort.outliers.length}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <section className={styles.outliers} aria-labelledby="outliers-heading">
        <h3 id="outliers-heading">
          <IconSpread size={16} /> Entities that do not match their cohort
        </h3>
        <p className={styles.quiet}>
          Different is not wrong. A bespoke shape may be the right answer to a problem
          nobody else in the estate has — the reasons below say what differs, and the
          decision stays yours.
        </p>
        <ul className={styles.outlierList}>
          {cohorts.flatMap((cohort) =>
            cohort.outliers.map((anomaly) => (
              <li key={anomaly.id}>
                <div className={styles.outlierHead}>
                  <Link href={entityHref(anomaly.entity)} className={styles.outlierName}>
                    {anomaly.entity.name}
                  </Link>
                  <span className={styles.outlierCohort}>{cohort.label}</span>
                  <span className={`${styles.percentile} sg-mono`}>
                    {anomaly.percentile == null
                      ? "—"
                      : `${Math.round(anomaly.percentile * 100)}th`}
                  </span>
                </div>
                {anomaly.reasons?.length ? (
                  <ul className={styles.reasons}>
                    {anomaly.reasons.map((reason) => (
                      <li key={reason}>{reason}</li>
                    ))}
                  </ul>
                ) : (
                  <p className={styles.quiet}>No reason was recorded for this difference.</p>
                )}
              </li>
            )),
          )}
        </ul>
      </section>

      <MotifList motifs={motifs.data?.motifs ?? []} loading={motifs.isLoading} error={motifs.isError} />
    </section>
  );
}

/**
 * Motifs are the other half of the same idea: a cohort says *these things resemble each
 * other*, a motif says *this exact arrangement recurs*. A recurring arrangement is the
 * thing worth turning into a standard, so it is listed rather than charted.
 */
function MotifList({
  motifs,
  loading,
  error,
}: {
  motifs: GraphMotif[];
  loading: boolean;
  error: boolean;
}) {
  if (loading) return <Skeleton height={120} />;
  if (error) {
    return <p className={styles.quiet}>Recurring patterns are temporarily unavailable.</p>;
  }
  if (!motifs.length) {
    return (
      <section className={styles.motifs} aria-labelledby="motifs-heading">
        <h3 id="motifs-heading">Arrangements that recur</h3>
        <p className={styles.quiet}>
          No structural pattern has recurred often enough to be named yet.
        </p>
      </section>
    );
  }
  return (
    <section className={styles.motifs} aria-labelledby="motifs-heading">
      <h3 id="motifs-heading">Arrangements that recur</h3>
      <p className={styles.quiet}>
        The same structural shape, found in more than one place. A pattern that keeps
        appearing is a candidate for a <Term id="referenceModel">reference model</Term>.
      </p>
      <ul className={styles.motifList}>
        {motifs.map((motif) => (
          <li key={motif.id}>
            <strong>{cohortLabel(motif.motif_key)}</strong>
            <span className={styles.quiet}>
              {motif.members?.length ?? 0} member{(motif.members?.length ?? 0) === 1 ? "" : "s"}
              {motif.minimum_confidence != null
                ? ` · weakest link ${Math.round(motif.minimum_confidence * 100)}%`
                : null}
            </span>
            {motif.members?.length ? (
              <p className={styles.motifMembers}>
                {motif.members.map((member) => member.name).join(" · ")}
              </p>
            ) : null}
          </li>
        ))}
      </ul>
    </section>
  );
}
