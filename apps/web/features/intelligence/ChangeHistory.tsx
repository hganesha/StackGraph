"use client";

import { useMemo } from "react";
import { PREDICATE_LABEL, Skeleton, Sparkline, Term, type ChangePredicate } from "@stackgraph/design-system";
import type { ObservedMutationModel } from "@stackgraph/shared";
import { useEntityChangeHistory } from "@/lib/changeQueries";
import styles from "./change-history.module.css";

/**
 * What happened last time somebody changed this.
 *
 * Part I noted the product had no time-based view at all — no trend, no delta, no
 * "since last week". `/entities/{id}/change-history` is the series, and it carries
 * outcomes rather than only events: `success`, `rolled_back`, `intervention_required`,
 * and `predicted_simulation_run_id` linking an observed change back to the simulation
 * that predicted it.
 *
 * Two rules this surface exists to keep. Every rate carries its denominator
 * (non-negotiable 17), because "20% rolled back" from five changes is not a rate. And
 * the calibration reading publishes the product's own miss rate rather than only its
 * successes — a system that predicts impact and never reports how often it was wrong is
 * asking for trust it has not evidenced.
 */
const MINIMUM_SAMPLE = 5;

interface Outcomes {
  total: number;
  succeeded: number;
  intervened: number;
  rolledBack: number;
  predicted: number;
  unexpected: number;
}

function countUnexpected(mutation: ObservedMutationModel): boolean {
  const unexpected = mutation.unexpected_impact;
  return Boolean(unexpected && typeof unexpected === "object" && Object.keys(unexpected).length > 0);
}

function CalibrationPlot({ outcomes }: { outcomes: ObservedMutationModel[] }) {
  const points = outcomes.filter((item) => item.predicted_finding_count != null).map((item) => ({
    id: item.id,
    label: `${item.subject.name} on ${new Date(item.observed_at).toLocaleDateString()}`,
    predicted: item.predicted_finding_count ?? 0,
    actual: (item.observed_impact_count ?? 0) + (item.unexpected_impact_count ?? 0),
  }));
  if (!points.length) return null;
  const maximum = Math.max(1, ...points.flatMap((point) => [point.predicted, point.actual]));
  const x = (value: number) => 30 + (value / maximum) * 180;
  const y = (value: number) => 130 - (value / maximum) * 100;
  return (
    <div className={styles.plotWrap}>
      <div>
        <h4>Predicted versus actual</h4>
        <p>{points.length} simulated outcome{points.length === 1 ? "" : "s"}; diagonal means finding count matched observed impact quantity.</p>
      </div>
      <svg className={styles.plot} viewBox="0 0 240 160" role="img" aria-label={`Calibration plot for ${points.length} outcomes. Predicted findings are horizontal and observed impact is vertical.`}>
        <path d="M30 130H220M30 130V20" className={styles.axis} />
        <path d="M30 130L210 30" className={styles.ideal} />
        {points.map((point) => <circle key={point.id} cx={x(point.predicted)} cy={y(point.actual)} r="4"><title>{point.label}: {point.predicted} predicted, {point.actual} observed</title></circle>)}
        <text x="124" y="153">Predicted findings</text><text x="8" y="77" transform="rotate(-90 8 77)">Observed impact</text>
      </svg>
      <ul className={styles.plotText}>{points.map((point) => <li key={point.id}>{point.label}: {point.predicted} predicted; {point.actual} observed.</li>)}</ul>
    </div>
  );
}

export function ChangeHistory({ entityId, entityName }: { entityId: string; entityName?: string }) {
  const query = useEntityChangeHistory(entityId);
  const outcomes = query.data?.outcomes ?? [];
  const similarOutcomes = query.data?.similar_outcomes ?? [];

  const stats = useMemo<Outcomes>(() => {
    let succeeded = 0;
    let intervened = 0;
    let rolledBack = 0;
    let predicted = 0;
    let unexpected = 0;
    for (const item of outcomes) {
      if (item.success) succeeded += 1;
      if (item.intervention_required) intervened += 1;
      if (item.rolled_back) rolledBack += 1;
      if (item.predicted_simulation_run_id) predicted += 1;
      if (countUnexpected(item)) unexpected += 1;
    }
    return { total: outcomes.length, succeeded, intervened, rolledBack, predicted, unexpected };
  }, [outcomes]);

  // Oldest first, so the line reads left to right the way time does. One point per
  // change, 1 for a clean outcome and 0 otherwise.
  const series = useMemo(
    () =>
      [...outcomes]
        .sort((a, b) => new Date(a.observed_at).getTime() - new Date(b.observed_at).getTime())
        .map((item) => (item.success && !item.rolled_back ? 1 : 0)),
    [outcomes],
  );
  const driftSeries = useMemo(
    () => [...outcomes, ...similarOutcomes]
      .filter((item) => item.predicted_simulation_run_id)
      .sort((a, b) => new Date(a.observed_at).getTime() - new Date(b.observed_at).getTime())
      .map((item) => countUnexpected(item) ? 1 : 0),
    [outcomes, similarOutcomes],
  );

  if (query.isLoading) {
    return (
      <section className={styles.panel}>
        <Skeleton height={22} width="40%" />
        <Skeleton height={110} />
      </section>
    );
  }

  if (query.isError) {
    return (
      <section className={styles.panel}>
        <h3>Previous changes</h3>
        <p className={styles.quiet} role="alert">Change history is temporarily unavailable.</p>
      </section>
    );
  }

  if (!stats.total) {
    return (
      <section className={styles.panel} aria-labelledby={`change-history-${entityId}`}>
        <h3 id={`change-history-${entityId}`}>Previous changes</h3>
        <p className={styles.quiet}>
          Nothing has been recorded changing {entityName ?? "this"} yet. Once changes are
          observed, what happened last time appears here.
        </p>
      </section>
    );
  }

  const rate = (n: number) => `${Math.round((n / stats.total) * 100)}%`;
  const thin = stats.total < MINIMUM_SAMPLE;

  return (
    <section className={styles.panel} aria-labelledby={`change-history-${entityId}`}>
      <header className={styles.head}>
        <div>
          <h3 id={`change-history-${entityId}`}>Previous changes</h3>
          <p>
            What happened the last {stats.total} time{stats.total === 1 ? "" : "s"} this was
            changed. Read alongside any simulation of it.
          </p>
        </div>
        {series.length > 1 ? (
          <Sparkline
            points={series}
            label={`Outcome of the last ${series.length} changes, oldest first. A high point is a clean outcome.`}
          />
        ) : null}
      </header>

      {/* Below the sample threshold the counts are shown and the rates are not. A
          percentage drawn from three changes reads as a finding and is a coincidence. */}
      {thin ? (
        <p className={styles.thin}>
          {stats.total} recorded change{stats.total === 1 ? "" : "s"} is too few to state a
          rate. The counts are below; a share would imply confidence nothing here supports.
        </p>
      ) : null}

      <dl className={styles.stats}>
        <div>
          <dt>Went cleanly</dt>
          <dd>
            <strong className="sg-mono">{thin ? stats.succeeded : rate(stats.succeeded)}</strong>
            <small>
              {stats.succeeded} of {stats.total}
            </small>
          </dd>
        </div>
        <div>
          <dt>Needed intervention</dt>
          <dd>
            <strong className="sg-mono">{thin ? stats.intervened : rate(stats.intervened)}</strong>
            <small>
              {stats.intervened} of {stats.total}
            </small>
          </dd>
        </div>
        <div>
          <dt>Rolled back</dt>
          <dd>
            <strong className="sg-mono">{thin ? stats.rolledBack : rate(stats.rolledBack)}</strong>
            <small>
              {stats.rolledBack} of {stats.total}
            </small>
          </dd>
        </div>
        <div>
          <dt>
            <Term id="blastRadius">Impact</Term> we did not predict
          </dt>
          <dd>
            <strong className="sg-mono">{thin ? stats.unexpected : rate(stats.unexpected)}</strong>
            <small>
              {stats.unexpected} of {stats.total}
            </small>
          </dd>
        </div>
      </dl>

      {/* Publishing the miss rate is the point. A predictor that only reports its hits
          is asking for trust it has not evidenced. */}
      {stats.predicted > 0 ? (
        <p className={styles.calibration}>
          {stats.predicted} of these {stats.total} were simulated first
          {stats.unexpected > 0 ? (
            <>
              , and {stats.unexpected} produced impact the simulation did not predict. That
              is StackGraph&apos;s own miss rate on this subject, not a claim about yours.
            </>
          ) : (
            <>, and none produced impact the simulation missed.</>
          )}
        </p>
      ) : (
        <p className={styles.quiet}>
          None of these were simulated beforehand, so there is nothing to compare a
          prediction against yet.
        </p>
      )}

      <CalibrationPlot outcomes={[...outcomes, ...similarOutcomes]} />

      {driftSeries.length > 1 ? (
        <div className={styles.drift}>
          <div><h4>Prediction drift</h4><p>Misses across exact and comparable simulated changes, oldest first. A high point is an unexpected impact.</p></div>
          <Sparkline points={driftSeries} label={`Prediction drift across ${driftSeries.length} simulated changes. High points are misses.`} />
        </div>
      ) : null}

      <ol className={styles.list}>
        {[...outcomes]
          .sort((a, b) => new Date(b.observed_at).getTime() - new Date(a.observed_at).getTime())
          .slice(0, 8)
          .map((item) => (
            <li key={item.id}>
              <span className={styles.predicate}>
                {PREDICATE_LABEL[item.predicate as ChangePredicate] ?? item.predicate}
              </span>
              <span className={`${styles.versions} sg-mono`}>
                {String((item.before as Record<string, unknown>)?.version ?? "—")} →{" "}
                {String((item.after as Record<string, unknown>)?.version ?? "—")}
              </span>
              <span className={styles.outcome}>
                {item.rolled_back
                  ? "Rolled back"
                  : item.intervention_required
                    ? "Needed intervention"
                    : item.success
                      ? "Went cleanly"
                      : "Outcome not recorded"}
              </span>
              <span className={styles.when}>
                {new Date(item.observed_at).toLocaleDateString(undefined, {
                  day: "numeric",
                  month: "short",
                  year: "numeric",
                })}
              </span>
            </li>
          ))}
      </ol>

      <div className={styles.similar}>
        <h4>Comparable changes</h4>
        <p>Deterministic filter: same subject type and predicate in this tenant. No semantic similarity is claimed.</p>
        {similarOutcomes.length ? <ol>{similarOutcomes.slice(0, 6).map((item) => <li key={item.id}><strong>{item.subject.name}</strong><span>{PREDICATE_LABEL[item.predicate as ChangePredicate] ?? item.predicate}</span><span>{item.rolled_back ? "Rolled back" : item.intervention_required ? "Intervention" : item.success ? "Went cleanly" : "Unknown outcome"}</span><time dateTime={item.observed_at}>{new Date(item.observed_at).toLocaleDateString()}</time></li>)}</ol> : <p className={styles.quiet}>No comparable changes are recorded elsewhere yet.</p>}
      </div>
      {query.data?.limitations?.map((item) => <p key={item.code} className={styles.thin}>{item.message}</p>)}
    </section>
  );
}
