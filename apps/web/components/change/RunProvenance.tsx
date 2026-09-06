import type { GraphAnalysisSnapshot, SimulationRunModel } from "@stackgraph/shared";
import styles from "./RunProvenance.module.css";

export interface NormalizedRunProvenance {
  asOf: string;
  policyKey?: string;
  policyVersion: string;
  watermark: string;
  coverage?: string;
  status: string;
  resultHash?: string | null;
  providerVersion?: string;
  scannerVersions?: string[];
  replayed?: boolean;
}

export function simulationProvenance(run: SimulationRunModel): NormalizedRunProvenance {
  return {
    asOf: run.completed_at ?? run.started_at ?? run.created_at,
    policyVersion: run.policy_version,
    watermark: run.estate_watermark,
    status: run.status,
    resultHash: run.result_hash,
    providerVersion: run.provider_version,
    scannerVersions: run.scanner_versions,
    replayed: run.replayed,
  };
}

export function graphProvenance(snapshot: GraphAnalysisSnapshot): NormalizedRunProvenance {
  return {
    asOf: snapshot.as_of,
    policyKey: snapshot.policy_key,
    policyVersion: String(snapshot.policy_version),
    watermark: String(snapshot.neo4j_projection_watermark),
    coverage: snapshot.coverage ? JSON.stringify(snapshot.coverage) : undefined,
    status: snapshot.status,
  };
}

function ageLabel(watermark: string, asOf: string) {
  const match = watermark.match(/\d{4}-\d{2}-\d{2}T[^;\s]+/);
  if (!match) return "Age not encoded";
  const ageMs = new Date(asOf).getTime() - new Date(match[0]).getTime();
  if (!Number.isFinite(ageMs) || ageMs < 0) return "Age unavailable";
  const minutes = Math.round(ageMs / 60_000);
  return minutes < 60 ? `${minutes} min old` : `${Math.round(minutes / 60)} hr old`;
}

function MachineValue({ value }: { value: string }) {
  return <code title={value}>{value}</code>;
}

export function RunProvenance({ value }: { value: NormalizedRunProvenance }) {
  return (
    <section className={styles.card} aria-labelledby="run-provenance-heading">
      <div className={styles.heading}>
        <div>
          <span>Reproducibility stamp</span>
          <h2 id="run-provenance-heading">Run provenance</h2>
        </div>
        {value.replayed ? <strong>Replayed result</strong> : null}
      </div>
      <dl>
        <div><dt>As of</dt><dd>{new Date(value.asOf).toLocaleString()}</dd></div>
        <div><dt>Status</dt><dd className={styles.status}>{value.status.replaceAll("_", " ")}</dd></div>
        {value.policyKey ? <div><dt>Policy</dt><dd><MachineValue value={value.policyKey} /></dd></div> : null}
        <div><dt>Policy version</dt><dd><MachineValue value={value.policyVersion} /></dd></div>
        <div><dt>Estate watermark</dt><dd><MachineValue value={value.watermark} /><small>{ageLabel(value.watermark, value.asOf)}</small></dd></div>
        {value.providerVersion ? <div><dt>Provider</dt><dd><MachineValue value={value.providerVersion} /></dd></div> : null}
        {value.resultHash ? <div><dt>Result hash</dt><dd><MachineValue value={value.resultHash} /></dd></div> : null}
        {value.coverage ? <div><dt>Coverage</dt><dd><MachineValue value={value.coverage} /></dd></div> : null}
        {value.scannerVersions?.length ? (
          <div><dt>Scanners</dt><dd>{value.scannerVersions.map((item) => <MachineValue value={item} key={item} />)}</dd></div>
        ) : null}
      </dl>
    </section>
  );
}
