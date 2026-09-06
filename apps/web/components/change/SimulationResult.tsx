"use client";

import { useMemo } from "react";
import Link from "next/link";
import {
  IconBan,
  IconCircleCheck,
  IconClock,
  IconDownload,
  IconPlayerStop,
  IconRefresh,
  IconX,
} from "@tabler/icons-react";
import {
  AttenuationBar,
  ConfidenceChip,
  CorroborationMark,
  GateNotice,
  RunProvenance,
  Skeleton,
  confidenceLabel,
  simulationRunProvenance,
  type GateVerdict,
} from "@stackgraph/design-system";
import type { SimulationFinding, SimulationRunModel } from "@stackgraph/shared";
import { useCancelSimulation, useSimulation } from "@/lib/changeQueries";
import { useEvidenceStore } from "@/lib/evidenceStore";

import styles from "./SimulationResult.module.css";

const TERMINAL = new Set<SimulationRunModel["status"]>([
  "SUCCEEDED", "LIMITED", "NOT_SIMULATABLE", "FAILED", "CANCELLED",
]);

const STATUS_COPY: Record<SimulationRunModel["status"], { title: string; body: string }> = {
  QUEUED: { title: "Simulation queued", body: "The durable run is waiting for a worker. No partial findings are shown as complete." },
  RUNNING: { title: "Tracing the hypothetical estate", body: "The active policy is evaluating evidence-backed paths and stop boundaries." },
  SUCCEEDED: { title: "Simulation completed", body: "Deterministic findings are complete for the pinned estate watermark." },
  LIMITED: { title: "Completed with reduced coverage", body: "The findings are usable only with the listed limitations." },
  NOT_SIMULATABLE: { title: "This change cannot be simulated", body: "This is a terminal answer from the policy, not a system failure." },
  FAILED: { title: "Simulation failed", body: "The run ended without a trustworthy result. Missing findings are not treated as zero." },
  CANCELLED: { title: "Simulation cancelled", body: "The durable run remains available, but it did not produce a completed result." },
};

const CLASSIFICATIONS = ["DIRECT", "TRANSITIVE", "CONTEXT", "STOP", "INFORMATIONAL"] as const;

function findingQuantity(finding: SimulationFinding) {
  const match = finding.detail.match(/\b([\d,]+)\b/);
  return match ? Number(match[1].replaceAll(",", "")) : 1;
}

function StatusHeader({ run, onCancel, cancelling }: { run: SimulationRunModel; onCancel: () => void; cancelling: boolean }) {
  const copy = STATUS_COPY[run.status];
  const Icon = run.status === "SUCCEEDED" ? IconCircleCheck
    : run.status === "CANCELLED" ? IconX
      : run.status === "NOT_SIMULATABLE" || run.status === "FAILED" ? IconBan
        : IconClock;
  return (
    <header className={`${styles.runHeader} ${styles[`status${run.status}`]}`}>
      <span className={styles.statusIcon} aria-hidden="true"><Icon size={21} stroke={1.6} /></span>
      <div>
        <span className={styles.runId}>Simulation {run.id}</span>
        <h1>{copy.title}</h1>
        <p>{copy.body}</p>
        {run.replayed ? <strong className={styles.replayed}>Existing idempotent run · not recomputed</strong> : null}
      </div>
      {!TERMINAL.has(run.status) ? (
        <button type="button" className={styles.cancel} onClick={onCancel} disabled={cancelling}>
          <IconPlayerStop size={16} stroke={1.5} aria-hidden="true" /> {cancelling ? "Cancelling…" : "Cancel run"}
        </button>
      ) : null}
    </header>
  );
}

function ClassificationRing({ findings }: { findings: SimulationFinding[] }) {
  const counts = Object.fromEntries(CLASSIFICATIONS.map((kind) => [kind, findings.filter((item) => item.classification === kind).length]));
  return (
    <section className={styles.instrument} aria-labelledby="ring-heading">
      <div className={styles.instrumentHeading}>
        <span>Position = impact class</span>
        <h2 id="ring-heading">Classification ring</h2>
      </div>
      <div className={styles.ringLayout}>
        <div className={styles.ring} role="img" aria-label={CLASSIFICATIONS.map((kind) => `${kind.toLowerCase()}: ${counts[kind]} findings`).join("; ")}>
          <div className={`${styles.band} ${styles.infoBand}`} />
          <div className={`${styles.band} ${styles.stopBand}`} />
          <div className={`${styles.band} ${styles.contextBand}`} />
          <div className={`${styles.band} ${styles.transitiveBand}`} />
          <div className={`${styles.band} ${styles.directBand}`} />
          <span className={styles.ringTotal}>{findings.length}<small>findings</small></span>
        </div>
        <ol className={styles.ringLegend}>
          {CLASSIFICATIONS.map((kind) => <li key={kind}><span data-kind={kind} /> <strong>{kind.replaceAll("_", " ")}</strong><b>{counts[kind]}</b></li>)}
        </ol>
      </div>
    </section>
  );
}

function ImpactComparison({ findings }: { findings: SimulationFinding[] }) {
  const rows = CLASSIFICATIONS.map((kind) => ({
    kind,
    simulated: findings.filter((item) => item.classification === kind).reduce((sum, item) => sum + findingQuantity(item), 0),
  }));
  const max = Math.max(1, ...rows.map((row) => row.simulated));
  return (
    <section className={styles.instrument} aria-labelledby="comparison-heading">
      <div className={styles.instrumentHeading}>
        <span>Missing is never zero</span>
        <h2 id="comparison-heading">Impact comparison</h2>
      </div>
      <div className={styles.gridLegend}><span>Lower</span><i /><i /><i /><i /><i /><i /><span>Higher simulated reach</span></div>
      <div className={styles.impactGrid} role="table" aria-label="Now, simulated, and difference by classification">
        <div role="row" className={styles.gridHead}><span role="columnheader">Class</span><span role="columnheader">Now</span><span role="columnheader">Simulated</span><span role="columnheader">Difference</span></div>
        {rows.map((row) => {
          const level = Math.max(0, Math.min(5, Math.ceil((row.simulated / max) * 5)));
          return (
            <div role="row" className={styles.gridRow} key={row.kind}>
              <strong role="rowheader">{row.kind.toLowerCase()}</strong>
              <span role="cell" className={styles.unknown}>Not in run</span>
              <span role="cell" className={styles.heat} data-level={level}>{row.simulated.toLocaleString()}</span>
              <span role="cell" className={styles.unknown}>Not derivable</span>
            </div>
          );
        })}
      </div>
      <p className={styles.instrumentNote}>This run does not include a current-state baseline, so the comparison preserves it as unknown instead of inventing a zero or delta.</p>
    </section>
  );
}

function FindingsPartition({ run }: { run: SimulationRunModel }) {
  const openEvidence = useEvidenceStore((state) => state.open);
  const cited = new Set(run.interpretation.cited_finding_ids ?? []);
  return (
    <section className={styles.partition} aria-label="Simulation result">
      <section className={styles.found} aria-labelledby="found-heading">
        <div className={styles.partitionHeading}>
          <div><span>Deterministic · evidence-backed</span><h2 id="found-heading">Found</h2></div>
          <b>{run.findings.length} findings</b>
        </div>
        {run.findings.length ? (
          <ol className={styles.findings}>
            {run.findings.map((finding) => (
              <li key={finding.id} id={`finding-${finding.id}`}>
                <div className={styles.findingTop}>
                  <span className={styles.classification}>{finding.classification}</span>
                  <span className={styles.severity}>{finding.severity}</span>
                  <ConfidenceChip label={confidenceLabel(finding.confidence)} value={finding.confidence} />
                  <CorroborationMark sources={finding.evidence_fact_ids?.length ?? 0} />
                </div>
                <h3>{finding.title}</h3>
                <p>{finding.detail}</p>
                {finding.path?.length ? (
                  <ol className={styles.path} aria-label={`Impact path for ${finding.title}`}>
                    {finding.path.map((entity, index) => <li key={`${finding.id}-${entity.id}`}><span>{entity.kind}</span><strong>{entity.name}</strong>{index < finding.path!.length - 1 ? <b aria-hidden="true">→</b> : null}</li>)}
                  </ol>
                ) : null}
                <div className={styles.findingMeta}>
                  <code title={`${finding.rule_key}@${finding.rule_version}`}>{finding.rule_key}@{finding.rule_version}</code>
                  {finding.evidence_fact_ids?.length ? (
                    <button type="button" onClick={() => openEvidence(finding.evidence_fact_ids![0], finding.title)}>
                      Inspect evidence
                    </button>
                  ) : <span>No evidence reference returned</span>}
                </div>
              </li>
            ))}
          </ol>
        ) : <p className={styles.noFindings}>No completed findings were returned. This is not rendered as zero impact.</p>}
      </section>

      <section className={styles.interpreted} aria-labelledby="interpreted-heading">
        <div className={styles.partitionHeading}>
          <div><span>AI reading · cannot change findings</span><h2 id="interpreted-heading">Interpreted</h2></div>
          <b>{run.interpretation.status}</b>
        </div>
        {run.interpretation.status === "AVAILABLE" ? (
          <details open>
            <summary>Risk, rollout, and verification</summary>
            <div className={styles.interpretationBody}>
              {run.interpretation.risk ? <section><h3>Risk</h3><p>{run.interpretation.risk}</p></section> : null}
              {run.interpretation.explanation ? <section><h3>Reading</h3><p>{run.interpretation.explanation}</p></section> : null}
              {run.interpretation.rollout?.length ? <section><h3>Rollout</h3><ol>{run.interpretation.rollout.map((item) => <li key={item}>{item}</li>)}</ol></section> : null}
              {run.interpretation.verification?.length ? <section><h3>Verification</h3><ol>{run.interpretation.verification.map((item) => <li key={item}>{item}</li>)}</ol></section> : null}
              <div className={styles.citations}>
                <strong>Cites findings</strong>
                {(run.interpretation.cited_finding_ids ?? []).map((id) => (
                  <a key={id} href={`#finding-${id}`} className={run.findings.some((finding) => finding.id === id) ? "" : styles.uncited}>{id}</a>
                ))}
                {!run.interpretation.cited_finding_ids?.length ? <span>Not derived from the findings above</span> : null}
              </div>
              {run.findings.some((finding) => !cited.has(finding.id)) ? <p className={styles.limitation}>Interpretation does not cite every finding. Uncited findings remain visible and authoritative.</p> : null}
            </div>
          </details>
        ) : (
          <div className={`${styles.interpretationState} ${run.interpretation.status === "QUARANTINED" ? styles.quarantined : ""}`} role="status">
            <strong>{run.interpretation.status === "QUARANTINED" ? "Interpretation quarantined" : "Interpretation unavailable"}</strong>
            <p>{run.interpretation.limitation ?? (run.interpretation.status === "QUARANTINED" ? "The generated claims did not cite deterministic findings." : "AI interpretation is off. Deterministic findings are unchanged.")}</p>
          </div>
        )}
      </section>
    </section>
  );
}

export function SimulationResult({ id }: { id: string }) {
  const simulation = useSimulation(id);
  const cancel = useCancelSimulation(id);
  const run = simulation.data;
  const attenuation = useMemo(() => {
    if (!run) return [];
    return [
      { key: "direct", label: "Direct reach", value: run.findings.filter((item) => item.classification === "DIRECT").reduce((sum, item) => sum + findingQuantity(item), 0) || null },
      { key: "transitive", label: "Transitive reach", value: run.findings.filter((item) => item.classification === "TRANSITIVE").reduce((sum, item) => sum + findingQuantity(item), 0) || null },
      { key: "context", label: "Business context", value: run.findings.filter((item) => item.classification === "CONTEXT").reduce((sum, item) => sum + findingQuantity(item), 0) || null },
      { key: "constraints", label: "Constraints", value: run.findings.filter((item) => item.classification === "INFORMATIONAL").reduce((sum, item) => sum + findingQuantity(item), 0) || null },
    ];
  }, [run]);

  if (simulation.isLoading && !run) {
    return <div className={styles.page}><Skeleton height={132} /><div className={styles.loadingGrid}><Skeleton height={300} /><Skeleton height={300} /></div></div>;
  }
  if (simulation.isError || !run) {
    return (
      <div className={styles.errorState}>
        <IconBan size={28} stroke={1.5} aria-hidden="true" />
        <h1>Simulation unavailable</h1>
        <p>{simulation.error?.message ?? "The run could not be found."}</p>
        <Link href="/simulate">Start another simulation</Link>
      </div>
    );
  }

  const nonTerminal = !TERMINAL.has(run.status);
  const showResults = run.status === "SUCCEEDED" || run.status === "LIMITED";
  return (
    <article className={styles.page}>
      <header className={styles.printTitle}>
        <span>StackGraph · Estate-backed change analysis</span>
        <h1>Change Brief</h1>
        <p>Simulation {run.id}</p>
      </header>
      <StatusHeader run={run} onCancel={() => cancel.mutate()} cancelling={cancel.isPending} />
      {run.gate.state !== "CLEAR" ? (
        <GateNotice
          verdict={run.gate.state as GateVerdict}
          reason={run.gate.reasons?.map((reason) => <span key={reason.code}><code>{reason.code}</code> · {reason.message}</span>) ?? "The run is gated."}
        />
      ) : null}
      {nonTerminal ? (
        <section className={styles.progress} aria-live="polite">
          <span className={styles.progressBar} aria-hidden="true"><i /></span>
          <strong>{run.status === "QUEUED" ? "Waiting for a simulation worker" : "Evaluating the pinned estate snapshot"}</strong>
          <p>Findings will appear only after the deterministic run reaches a terminal state.</p>
        </section>
      ) : null}
      {showResults ? (
        <>
          {run.limitations.length ? (
            <section className={styles.limitations} aria-labelledby="limitations-heading">
              <h2 id="limitations-heading">Limitations on this result</h2>
              <ul>{run.limitations.map((item) => <li key={`${item.code}-${item.message}`}><code>{item.code}</code> · {item.message}</li>)}</ul>
            </section>
          ) : null}
          <div className={styles.actions}>
            <span>ChangeSet <code>{run.change_set_id}</code></span>
            <button type="button" onClick={() => window.print()}><IconDownload size={16} stroke={1.5} aria-hidden="true" /> Print Change Brief</button>
          </div>
          <div className={styles.instrumentGrid}>
            <ClassificationRing findings={run.findings} />
            <section className={styles.instrument} aria-labelledby="funnel-heading">
              <div className={styles.instrumentHeading}><span>The dropout is the product</span><h2 id="funnel-heading">Attenuation funnel</h2></div>
              <AttenuationBar stages={attenuation} actLabel="Review these" />
            </section>
          </div>
          <ImpactComparison findings={run.findings} />
          <FindingsPartition run={run} />
        </>
      ) : null}
      <RunProvenance {...simulationRunProvenance(run)} variant="card" />
      <footer className={styles.pageFooter}>
        <Link href="/simulate"><IconRefresh size={15} stroke={1.5} aria-hidden="true" /> Plan another change</Link>
      </footer>
    </article>
  );
}
