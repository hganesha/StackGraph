"use client";

import { useState, type FormEvent } from "react";
import dynamic from "next/dynamic";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { IconAlertTriangle, IconPlayerPlay, IconShieldCheck, IconShieldLock } from "@tabler/icons-react";
import {
  stackGraphClient,
  type AgentControlDrillResult,
  type AgentAuthorizationDecisionModel,
  type CapabilityEnvelopeModel,
  type FlightRecordModel,
} from "@stackgraph/shared";
import { GateNotice, Skeleton } from "@stackgraph/design-system";
import styles from "./AgentControlSection.module.css";

// §36 is the last thing an operator reaches on this tab and the heaviest part of it, so it is
// split out of the admin entry bundle rather than paid for by everyone who opens the page.
const ImmuneSystemSection = dynamic(
  () => import("./ImmuneSystemSection").then((m) => m.ImmuneSystemSection),
  { loading: () => <Skeleton height={420} /> },
);

export function AgentControlSection() {
  const queryClient = useQueryClient();
  const killSwitch = useQuery({
    queryKey: ["agent-control", "kill-switch"],
    queryFn: () => stackGraphClient.getAgentKillSwitch(),
  });
  const [reason, setReason] = useState("Security-controlled operator update");
  const [objective, setObjective] = useState("Inspect the current estate without changing external systems");
  const [operationKey, setOperationKey] = useState("estate.read");
  const [requestedBand, setRequestedBand] = useState<"READ" | "EXECUTE" | "CONDITIONAL" | "PROHIBITED" | "ESCALATE">("READ");
  const [riskTier, setRiskTier] = useState<"TIER_0" | "TIER_1" | "TIER_2" | "TIER_3">("TIER_3");
  const [contextConfidence, setContextConfidence] = useState(1);
  const [envelope, setEnvelope] = useState<CapabilityEnvelopeModel | null>(null);
  const [authorization, setAuthorization] = useState<AgentAuthorizationDecisionModel | null>(null);
  const [flight, setFlight] = useState<FlightRecordModel | null>(null);
  const [drill, setDrill] = useState<AgentControlDrillResult | null>(null);

  const updateSwitch = useMutation({
    mutationFn: (engaged: boolean) => stackGraphClient.updateAgentKillSwitch({
      engaged,
      expected_version: killSwitch.data?.version ?? 0,
      reason: reason.trim(),
    }),
    onSuccess: (value) => queryClient.setQueryData(["agent-control", "kill-switch"], value),
  });
  const compile = useMutation({
    mutationFn: () => stackGraphClient.compileCapabilityEnvelope({
      objective: objective.trim(),
      environment: "local",
      estate_watermark: `local:${new Date().toISOString()}`,
      risk_tier: riskTier,
      context_confidence: contextConfidence,
      operations: [{
        operation_key: operationKey.trim(),
        requested_band: requestedBand,
        destructive: requestedBand === "EXECUTE" && /delete|remove|destroy|write/.test(operationKey),
        constraints: { source: "admin-control-plane" },
      }],
      evidence_fact_ids: [],
      subject_entity_ids: [],
      ttl_seconds: 900,
    }),
    onSuccess: (value) => { setEnvelope(value); setAuthorization(null); setFlight(null); },
  });
  const authorize = useMutation({
    mutationFn: () => stackGraphClient.authorizeAgentOperation(envelope!.id, {
      operation_key: operationKey,
      request_payload: { source: "admin-control-plane", dry_run: true },
    }),
    onSuccess: setAuthorization,
  });
  const createFlight = useMutation({
    mutationFn: () => stackGraphClient.createFlightRecord({ envelope_id: envelope!.id, objective }),
    onSuccess: setFlight,
  });
  const appendVerification = useMutation({
    mutationFn: () => stackGraphClient.appendFlightEvent(flight!.id, {
      event_type: "VERIFICATION",
      system_boundary: "stackgraph.local",
      payload: { dry_run: true, authorized_decision_id: authorization?.id ?? null },
      occurred_at: new Date().toISOString(),
    }),
    onSuccess: setFlight,
  });
  const finalizeFlight = useMutation({
    mutationFn: () => stackGraphClient.finalizeFlightRecord(flight!.id, {
      status: "SUCCEEDED", outcome: { dry_run: true, external_mutation: false },
    }),
    onSuccess: setFlight,
  });
  const runDrill = useMutation({
    mutationFn: (drillKind: "KILL_SWITCH" | "ROLLBACK" | "AUDIT_RECONSTRUCTION") =>
      stackGraphClient.runAgentControlDrill({
        drill_kind: drillKind,
        envelope_id: drillKind === "ROLLBACK" ? envelope?.id : undefined,
        flight_record_id: drillKind === "AUDIT_RECONSTRUCTION" ? flight?.id : undefined,
      }),
    onSuccess: setDrill,
  });

  const submitEnvelope = (event: FormEvent) => {
    event.preventDefault();
    if (objective.trim() && operationKey.trim()) compile.mutate();
  };

  const requestError = updateSwitch.error ?? compile.error ?? authorize.error ?? createFlight.error
    ?? appendVerification.error ?? finalizeFlight.error ?? runDrill.error;

  return (
    <div className={styles.section}>
      <section className={styles.card} aria-labelledby="agent-posture-heading">
        <header><IconShieldLock size={20} aria-hidden="true" /><div><h3 id="agent-posture-heading">Execution posture</h3><p>Two independent controls must permit a non-read operation: the release feature gate and this tenant kill switch.</p></div></header>
        {killSwitch.isLoading ? <Skeleton height={82} /> : killSwitch.isError ? <GateNotice verdict="BLOCKED" reason="The kill-switch state could not be read, so execution must be treated as disabled." /> : killSwitch.data ? (
          <div className={styles.posture} data-engaged={killSwitch.data.engaged}>
            <div><strong>{killSwitch.data.engaged ? "Kill switch engaged" : "Kill switch disengaged"}</strong><span>{killSwitch.data.reason}</span><small>Version {killSwitch.data.version} · {killSwitch.data.updated_by}</small></div>
            <label><span>Audited reason</span><input value={reason} onChange={(event) => setReason(event.target.value)} required /></label>
            <button type="button" disabled={!reason.trim() || updateSwitch.isPending} onClick={() => updateSwitch.mutate(!killSwitch.data.engaged)}>{killSwitch.data.engaged ? "Disengage tenant switch" : "Engage kill switch"}</button>
          </div>
        ) : null}
        <p className={styles.releaseGate}><IconAlertTriangle size={16} aria-hidden="true" />The deployment-level <code>CHANGE_EXECUTION</code> release gate remains authoritative. Disengaging the tenant switch alone cannot authorize execution.</p>
      </section>

      <section className={styles.card} aria-labelledby="permission-heading">
        <header><IconShieldCheck size={20} aria-hidden="true" /><div><h3 id="permission-heading">Permission compiler</h3><p>Compile a short-lived, least-privilege envelope and inspect its deterministic decision.</p></div></header>
        <form className={styles.form} onSubmit={submitEnvelope}>
          <label className={styles.wide}><span>Objective</span><textarea value={objective} onChange={(event) => setObjective(event.target.value)} required /></label>
          <label><span>Operation key</span><input value={operationKey} onChange={(event) => setOperationKey(event.target.value)} pattern="[a-z][a-z0-9._:-]{2,127}" required /></label>
          <label><span>Requested band</span><select value={requestedBand} onChange={(event) => setRequestedBand(event.target.value as typeof requestedBand)}>{["READ", "EXECUTE", "CONDITIONAL", "PROHIBITED", "ESCALATE"].map((band) => <option key={band}>{band}</option>)}</select></label>
          <label><span>Risk tier</span><select value={riskTier} onChange={(event) => setRiskTier(event.target.value as typeof riskTier)}>{["TIER_3", "TIER_2", "TIER_1", "TIER_0"].map((tier) => <option key={tier}>{tier}</option>)}</select></label>
          <label><span>Context confidence · {Math.round(contextConfidence * 100)}%</span><input type="range" min="0" max="1" step="0.05" value={contextConfidence} onChange={(event) => setContextConfidence(Number(event.target.value))} /></label>
          <button type="submit" disabled={compile.isPending}>{compile.isPending ? "Compiling…" : "Compile envelope"}</button>
        </form>
        {envelope ? <div className={styles.envelope}>
          <div className={styles.envelopeHead}><div><small>Envelope {envelope.id}</small><strong>{envelope.decision}</strong></div><span>Expires {new Date(envelope.valid_until).toLocaleTimeString()}</span></div>
          <div className={styles.bands}>{envelope.bands.map((band) => <div key={band.band}><b>{band.band}</b><span>{(band.operations ?? []).map((item) => item.operation_key).join(", ") || "—"}</span></div>)}</div>
          {envelope.decision_reasons?.map((item) => <GateNotice key={item.code} verdict={envelope.decision === "DENY" ? "BLOCKED" : envelope.decision === "ESCALATE" ? "ESCALATE" : "CONSTRAIN"} reason={item.message} />)}
          <div className={styles.actions}>
            <button type="button" onClick={() => authorize.mutate()} disabled={authorize.isPending}>Authorize dry run</button>
            <button type="button" onClick={() => createFlight.mutate()} disabled={createFlight.isPending}>Start flight record</button>
          </div>
          {authorization ? <p className={styles.decision}><strong>{authorization.decision}</strong> {authorization.reason_codes.join(" · ") || "No constraint reason"}</p> : null}
        </div> : null}
      </section>

      <section className={styles.card} aria-labelledby="flight-heading">
        <header><IconPlayerPlay size={20} aria-hidden="true" /><div><h3 id="flight-heading">Flight recorder and safety drills</h3><p>Reconstruct calls across boundaries, verify outcomes, and exercise rollback and kill-switch controls.</p></div></header>
        {flight ? <div className={styles.flight}><strong>{flight.status} · {flight.event_count} events</strong><code>{flight.chain_head ?? "No chain head yet"}</code><div className={styles.actions}><button type="button" onClick={() => appendVerification.mutate()} disabled={flight.status !== "ACTIVE" || appendVerification.isPending}>Append verification</button><button type="button" onClick={() => finalizeFlight.mutate()} disabled={flight.status !== "ACTIVE" || flight.event_count === 0 || finalizeFlight.isPending}>Finalize verified dry run</button></div></div> : <p className={styles.quiet}>Compile an envelope, then start a flight record. No external action is performed from this surface.</p>}
        <div className={styles.drills}>
          <button type="button" onClick={() => runDrill.mutate("KILL_SWITCH")} disabled={runDrill.isPending}>Run kill-switch drill</button>
          <button type="button" onClick={() => runDrill.mutate("ROLLBACK")} disabled={!envelope || runDrill.isPending}>Run rollback drill</button>
          <button type="button" onClick={() => runDrill.mutate("AUDIT_RECONSTRUCTION")} disabled={!flight || runDrill.isPending}>Run audit drill</button>
        </div>
        {drill ? <div className={styles.drillResult}><strong>{drill.drill_kind.replaceAll("_", " ")} · {drill.status}</strong><ul>{drill.checks.map((check, index) => <li key={index}>{String(check.check ?? "check")} — {check.passed ? "passed" : "failed"}</li>)}</ul></div> : null}
        {requestError ? <p className={styles.error} role="alert">{requestError.message}</p> : null}
      </section>

      <ImmuneSystemSection />
    </div>
  );
}
