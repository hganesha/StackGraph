"use client";

import { useState } from "react";
import type { FormEvent } from "react";
import {
  ApiRequestError,
  stackGraphClient,
  type CalibrationCorpusPublishRequest,
  type EcosystemAdmissionSummary,
  type EcosystemName,
  type InternalCatalogComponentUpsertRequest,
  type ModernizationGovernanceState,
  type ModernizationPolicyPublishRequest,
  type ModernizationPolicySummary,
} from "@stackgraph/shared";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { DeterministicRulesEditor } from "./DeterministicRulesEditor";
import styles from "./admin.module.css";

type SecurityStatus = "CLEAR" | "WARN" | "BLOCKED" | "UNKNOWN";

const SECURITY_STATUSES: readonly SecurityStatus[] = ["CLEAR", "WARN", "BLOCKED", "UNKNOWN"];

function errorMessage(error: unknown): string {
  if (error instanceof ApiRequestError && error.detail && typeof error.detail === "object") {
    const message = (error.detail as { message?: unknown }).message;
    if (typeof message === "string") return message;
  }
  return error instanceof Error ? error.message : "The governance change could not be saved.";
}

function splitValues(value: string): string[] {
  return [...new Set(value.split(/[\n,]/).map((item) => item.trim()).filter(Boolean))];
}

function parseKeyValues(value: string): Record<string, string> {
  return Object.fromEntries(splitValues(value).flatMap((item) => {
    const separator = item.indexOf("=");
    return separator > 0 ? [[item.slice(0, separator).trim(), item.slice(separator + 1).trim()]] : [];
  }));
}

function formatKeyValues(value: Record<string, string>): string {
  return Object.entries(value).map(([key, item]) => `${key}=${item}`).join("\n");
}

function nextVersion(version: string | undefined): string {
  if (!version) return "1.0.0";
  const parts = version.split(".");
  const patch = Number(parts.at(-1));
  if (Number.isInteger(patch)) return [...parts.slice(0, -1), String(patch + 1)].join(".");
  return `${version}.1`;
}

function shortFingerprint(value: string): string {
  return value.length > 24 ? `${value.slice(0, 15)}…${value.slice(-8)}` : value;
}

function PolicyEditor({ policy }: { policy?: ModernizationPolicySummary | null }) {
  const queryClient = useQueryClient();
  const [policyKey, setPolicyKey] = useState(policy?.policy_key ?? "modernization.default");
  const [version, setVersion] = useState(nextVersion(policy?.version));
  const [runtimeVersions, setRuntimeVersions] = useState(formatKeyValues(
    policy?.runtime_versions ?? { node: "20", python: "3.12", dotnet: "8" },
  ));
  const [licenses, setLicenses] = useState((policy?.allowed_licenses ?? []).join(", "));
  const [deniedOptions, setDeniedOptions] = useState((policy?.denied_option_keys ?? []).join("\n"));
  const [requiredTags, setRequiredTags] = useState((policy?.required_policy_tags ?? []).join(", "));
  const [securityStatuses, setSecurityStatuses] = useState<SecurityStatus[]>(
    (policy?.allowed_security_statuses.filter(
      (item): item is SecurityStatus => SECURITY_STATUSES.includes(item as SecurityStatus),
    ) ?? ["CLEAR", "UNKNOWN"]),
  );
  const publish = useMutation({
    mutationFn: (body: ModernizationPolicyPublishRequest) => stackGraphClient.publishModernizationPolicy(body),
    onSuccess: (state) => queryClient.setQueryData(["admin", "modernization-governance"], state),
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    publish.mutate({
      policy_key: policyKey.trim(), version: version.trim(),
      runtime_versions: parseKeyValues(runtimeVersions),
      allowed_licenses: splitValues(licenses), denied_option_keys: splitValues(deniedOptions),
      allowed_security_statuses: securityStatuses, required_policy_tags: splitValues(requiredTags),
    });
  }

  return (
    <section className={styles.governanceCard} aria-labelledby="modernization-policy-heading">
      <div className={styles.governanceCardHead}>
        <div>
          <span className={styles.eyebrow}>Tenant policy</span>
          <h2 id="modernization-policy-heading" className={styles.cardTitle}>Modernization eligibility</h2>
        </div>
        {policy ? <span className={styles.statusGood}>Active · {policy.version}</span> : <span className={styles.statusMuted}>Not configured</span>}
      </div>
      {policy ? (
        <p className={styles.fingerprint} title={policy.configuration_fingerprint}>
          Current fingerprint <span className="sg-mono">{shortFingerprint(policy.configuration_fingerprint)}</span>
        </p>
      ) : null}
      <form className={styles.governanceForm} onSubmit={submit}>
        <div className={styles.fieldGrid}>
          <label className={styles.field}>
            <span className={styles.label}>Policy key</span>
            <input className={styles.input} value={policyKey} onChange={(event) => setPolicyKey(event.target.value)} required />
          </label>
          <label className={styles.field}>
            <span className={styles.label}>New immutable version</span>
            <input className={styles.input} value={version} onChange={(event) => setVersion(event.target.value)} required />
          </label>
        </div>
        <label className={styles.field}>
          <span className={styles.label}>Minimum supported runtime baselines</span>
          <textarea className={styles.textarea} value={runtimeVersions} onChange={(event) => setRuntimeVersions(event.target.value)} placeholder={"node=20\npython=3.12"} />
          <span className={styles.help}>One <span className="sg-mono">runtime=version</span> pair per line. StackGraph compares these baselines with runtime images declared in Dockerfiles, Compose, and Kubernetes code.</span>
        </label>
        <div className={styles.fieldGrid}>
          <label className={styles.field}>
            <span className={styles.label}>Allowed licenses</span>
            <input className={styles.input} value={licenses} onChange={(event) => setLicenses(event.target.value)} placeholder="MIT, Apache-2.0" />
          </label>
          <label className={styles.field}>
            <span className={styles.label}>Required policy tags</span>
            <input className={styles.input} value={requiredTags} onChange={(event) => setRequiredTags(event.target.value)} placeholder="supported, platform-owned" />
          </label>
        </div>
        <fieldset className={styles.checkGroup}>
          <legend className={styles.label}>Allowed security statuses</legend>
          {SECURITY_STATUSES.map((status) => (
            <label key={status} className={styles.checkLabel}>
              <input
                type="checkbox"
                checked={securityStatuses.includes(status)}
                onChange={(event) => setSecurityStatuses((current) => (
                  event.target.checked ? [...current, status] : current.filter((item) => item !== status)
                ))}
              />
              {status.toLowerCase()}
            </label>
          ))}
        </fieldset>
        <label className={styles.field}>
          <span className={styles.label}>Denied option keys</span>
          <textarea className={styles.textarea} value={deniedOptions} onChange={(event) => setDeniedOptions(event.target.value)} placeholder="One option key per line" />
        </label>
        <div className={styles.actions}>
          <button className={styles.primary} disabled={publish.isPending || securityStatuses.length === 0} type="submit">
            {publish.isPending ? "Publishing…" : "Publish policy and reanalyze"}
          </button>
          <span className={styles.help}>Publishing enqueues the latest complete snapshot under a new fingerprint.</span>
        </div>
        {publish.isError ? <p className={styles.error} role="alert">{errorMessage(publish.error)}</p> : null}
        {publish.isSuccess ? <p className={styles.success} role="status">Policy published and estate reanalysis queued.</p> : null}
      </form>
    </section>
  );
}

function InternalCatalogEditor({ state }: { state: ModernizationGovernanceState }) {
  const queryClient = useQueryClient();
  const componentCandidates = state.internal_component_candidates ?? [];
  const [componentKey, setComponentKey] = useState("");
  const [entityId, setEntityId] = useState("");
  const [capabilityId, setCapabilityId] = useState("");
  const [version, setVersion] = useState("1.0.0");
  const [owner, setOwner] = useState("");
  const [factIds, setFactIds] = useState("");
  const [license, setLicense] = useState("");
  const [policyTags, setPolicyTags] = useState("");
  const [apiSymbols, setApiSymbols] = useState("");
  const [status, setStatus] = useState<InternalCatalogComponentUpsertRequest["status"]>("APPROVED");
  const [securityStatus, setSecurityStatus] = useState<InternalCatalogComponentUpsertRequest["security_status"]>("UNKNOWN");
  const [decision, setDecision] = useState<InternalCatalogComponentUpsertRequest["decision"]>("APPROVE");
  const [selectedCandidateId, setSelectedCandidateId] = useState("");
  const govern = useMutation({
    mutationFn: (body: InternalCatalogComponentUpsertRequest) => (
      stackGraphClient.governInternalCatalogComponent(componentKey.trim(), body)
    ),
    onSuccess: (next) => {
      queryClient.setQueryData(["admin", "modernization-governance"], next);
      setComponentKey(""); setEntityId(""); setCapabilityId(""); setFactIds("");
    },
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    govern.mutate({
      component_entity_id: entityId.trim(), capability_definition_id: capabilityId.trim(),
      version: version.trim(), status, api_symbols: splitValues(apiSymbols),
      license: license.trim() || null, security_status: securityStatus,
      policy_tags: splitValues(policyTags), supporting_fact_ids: splitValues(factIds),
      owner: owner.trim(), decision,
    });
  }

  function selectCandidate(candidateId: string) {
    setSelectedCandidateId(candidateId);
    const candidate = componentCandidates.find((item) => item.candidate_id === candidateId);
    if (!candidate) return;
    setComponentKey(candidate.component_key);
    setEntityId(candidate.component_entity_id);
    setCapabilityId(candidate.capability_definition_id);
    setFactIds(candidate.supporting_fact_ids.join("\n"));
    setApiSymbols(candidate.name);
  }

  return (
    <section className={styles.governanceCard} aria-labelledby="internal-catalog-heading">
      <div className={styles.governanceCardHead}>
        <div><span className={styles.eyebrow}>Internal catalog</span><h2 id="internal-catalog-heading" className={styles.cardTitle}>Approved replacement components</h2></div>
        <span className={styles.statusMuted}>{state.internal_components.length} governed</span>
      </div>
      {state.internal_components.length ? (
        <ul className={styles.governanceList}>
          {state.internal_components.map((component) => (
            <li key={component.id} className={styles.governanceListItem}>
              <div><strong>{component.name}</strong><span>{component.component_key} · {component.version} · owner {component.owner ?? "unassigned"}</span></div>
              <span className={component.review_state === "APPROVED" ? styles.statusGood : styles.statusBad}>{component.review_state.toLowerCase()}</span>
            </li>
          ))}
        </ul>
      ) : <p className={styles.empty}>No internal components have been governed yet.</p>}
      {componentCandidates.length ? (
        <label className={styles.field}>
          <span className={styles.label}>Manifest-backed internal package proposal</span>
          <select
            className={styles.select}
            value={selectedCandidateId}
            onChange={(event) => selectCandidate(event.target.value)}
          >
            <option value="">Select a declared internal package…</option>
            {componentCandidates.map((candidate) => (
              <option key={candidate.candidate_id} value={candidate.candidate_id}>
                {candidate.repository_name} · {candidate.capability} · {candidate.name} · {Math.round(candidate.confidence * 100)}%
              </option>
            ))}
          </select>
          <span className={styles.help}>Proposals require a package manifest plus a declared custom registry. Selecting one fills the package, capability, and fact identifiers; approval remains an explicit decision and requires an owner.</span>
        </label>
      ) : <p className={styles.empty}>No ungoverned package has both custom-registry publication evidence and a high-confidence capability classification.</p>}
      <form className={styles.governanceForm} onSubmit={submit}>
        <div className={styles.fieldGrid}>
          <label className={styles.field}><span className={styles.label}>Component key</span><input className={styles.input} value={componentKey} onChange={(event) => setComponentKey(event.target.value)} required /></label>
          <label className={styles.field}><span className={styles.label}>Version</span><input className={styles.input} value={version} onChange={(event) => setVersion(event.target.value)} required /></label>
          <label className={styles.field}><span className={styles.label}>Component entity UUID</span><input className={styles.input} value={entityId} onChange={(event) => setEntityId(event.target.value)} required /></label>
          <label className={styles.field}><span className={styles.label}>Capability definition UUID</span><input className={styles.input} value={capabilityId} onChange={(event) => setCapabilityId(event.target.value)} required /></label>
          <label className={styles.field}><span className={styles.label}>Owner</span><input className={styles.input} value={owner} onChange={(event) => setOwner(event.target.value)} required /></label>
          <label className={styles.field}><span className={styles.label}>License</span><input className={styles.input} value={license} onChange={(event) => setLicense(event.target.value)} /></label>
          <label className={styles.field}><span className={styles.label}>Catalog status</span><select className={styles.select} value={status} onChange={(event) => setStatus(event.target.value as typeof status)}><option>APPROVED</option><option>DEPRECATED</option><option>BLOCKED</option></select></label>
          <label className={styles.field}><span className={styles.label}>Security status</span><select className={styles.select} value={securityStatus} onChange={(event) => setSecurityStatus(event.target.value as typeof securityStatus)}>{SECURITY_STATUSES.map((item) => <option key={item}>{item}</option>)}</select></label>
        </div>
        <label className={styles.field}><span className={styles.label}>Supporting fact UUIDs</span><textarea className={styles.textarea} value={factIds} onChange={(event) => setFactIds(event.target.value)} required /><span className={styles.help}>One current tenant fact per line. Approval fails closed if any evidence is missing.</span></label>
        <div className={styles.fieldGrid}>
          <label className={styles.field}><span className={styles.label}>API symbols</span><input className={styles.input} value={apiSymbols} onChange={(event) => setApiSymbols(event.target.value)} /></label>
          <label className={styles.field}><span className={styles.label}>Policy tags</span><input className={styles.input} value={policyTags} onChange={(event) => setPolicyTags(event.target.value)} /></label>
        </div>
        <div className={styles.actions}>
          <select className={styles.selectCompact} aria-label="Governance decision" value={decision} onChange={(event) => setDecision(event.target.value as typeof decision)}><option value="APPROVE">Approve</option><option value="REJECT">Reject</option></select>
          <button className={decision === "REJECT" ? styles.danger : styles.primary} disabled={govern.isPending} type="submit">{govern.isPending ? "Saving…" : "Record governed decision"}</button>
        </div>
        {govern.isError ? <p className={styles.error} role="alert">{errorMessage(govern.error)}</p> : null}
      </form>
    </section>
  );
}

function CalibrationEditor({ state }: { state: ModernizationGovernanceState }) {
  const queryClient = useQueryClient();
  const current = state.active_calibration;
  const [version, setVersion] = useState(nextVersion(current?.version));
  const [cases, setCases] = useState("");
  const [candidatePrecision, setCandidatePrecision] = useState("0.80");
  const [acceptance, setAcceptance] = useState("0.50");
  const [validationSuccess, setValidationSuccess] = useState("0.80");
  const [scopeMae, setScopeMae] = useState("0.25");
  const [effortAccuracy, setEffortAccuracy] = useState("0.70");
  const [minimumCases, setMinimumCases] = useState("20");
  const publish = useMutation({
    mutationFn: (body: CalibrationCorpusPublishRequest) => stackGraphClient.publishCalibrationCorpus(body),
    onSuccess: (next) => queryClient.setQueryData(["admin", "modernization-governance"], next),
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    publish.mutate({
      corpus_key: "modernization.pilot", version: version.trim(), case_fingerprints: splitValues(cases),
      minimum_candidate_precision: Number(candidatePrecision),
      minimum_recommendation_acceptance: Number(acceptance),
      minimum_validation_success: Number(validationSuccess),
      maximum_affected_scope_mae: Number(scopeMae),
      minimum_effort_accuracy: Number(effortAccuracy),
      minimum_reviewed_cases: Number(minimumCases),
    });
  }

  return (
    <section className={styles.governanceCard} aria-labelledby="calibration-heading">
      <div className={styles.governanceCardHead}>
        <div><span className={styles.eyebrow}>Promotion gate</span><h2 id="calibration-heading" className={styles.cardTitle}>Calibration corpus</h2></div>
        {current ? <span className={current.promotion_passed ? styles.statusGood : styles.statusBad}>{current.promotion_passed ? "Promoted" : "Gate failed"}</span> : <span className={styles.statusMuted}>No corpus</span>}
      </div>
      {current ? <p className={styles.sectionNote}>{current.case_count} reviewed cases · evaluated {new Date(current.evaluated_at).toLocaleString()}</p> : null}
      {current ? (
        <dl className={styles.metricGrid}>
          <div><dt>Candidate precision</dt><dd>{current.observed_metrics.candidate_precision == null ? "Unavailable" : `${(current.observed_metrics.candidate_precision * 100).toFixed(1)}%`}</dd></div>
          <div><dt>Recommendation acceptance</dt><dd>{current.observed_metrics.recommendation_acceptance == null ? "Unavailable" : `${(current.observed_metrics.recommendation_acceptance * 100).toFixed(1)}%`}</dd></div>
          <div><dt>Validation success</dt><dd>{current.observed_metrics.validation_success == null ? "Unavailable" : `${(current.observed_metrics.validation_success * 100).toFixed(1)}%`}</dd></div>
          <div><dt>Normalized scope MAE</dt><dd>{current.observed_metrics.affected_scope_mae == null ? "Unavailable" : current.observed_metrics.affected_scope_mae.toFixed(3)}</dd></div>
          <div><dt>Effort accuracy</dt><dd>{current.observed_metrics.effort_accuracy == null ? "Unavailable" : `${(current.observed_metrics.effort_accuracy * 100).toFixed(1)}%`}</dd></div>
        </dl>
      ) : null}
      {current?.promotion_failures.length ? <ul className={styles.reasonList}>{current.promotion_failures.map((reason) => <li key={reason}>{reason}</li>)}</ul> : null}
      <form className={styles.governanceForm} onSubmit={submit}>
        <div className={styles.fieldGrid}>
          <label className={styles.field}><span className={styles.label}>New corpus version</span><input className={styles.input} value={version} onChange={(event) => setVersion(event.target.value)} required /></label>
          <label className={styles.field}><span className={styles.label}>Minimum reviewed cases</span><input className={styles.input} type="number" min="1" value={minimumCases} onChange={(event) => setMinimumCases(event.target.value)} required /></label>
        </div>
        <label className={styles.field}><span className={styles.label}>Reviewed analysis fingerprints</span><textarea className={`${styles.textarea} ${styles.codeTextarea}`} value={cases} onChange={(event) => setCases(event.target.value)} placeholder="sha256:…" required /><span className={styles.help}>Candidate or recommendation fingerprints must already have a human review.</span></label>
        <div className={styles.metricGrid}>
          <label className={styles.field}><span className={styles.label}>Minimum candidate precision</span><input className={styles.input} type="number" min="0" max="1" step="0.01" value={candidatePrecision} onChange={(event) => setCandidatePrecision(event.target.value)} required /></label>
          <label className={styles.field}><span className={styles.label}>Minimum recommendation acceptance</span><input className={styles.input} type="number" min="0" max="1" step="0.01" value={acceptance} onChange={(event) => setAcceptance(event.target.value)} required /></label>
          <label className={styles.field}><span className={styles.label}>Minimum validation success</span><input className={styles.input} type="number" min="0" max="1" step="0.01" value={validationSuccess} onChange={(event) => setValidationSuccess(event.target.value)} required /></label>
          <label className={styles.field}><span className={styles.label}>Maximum normalized scope MAE</span><input className={styles.input} type="number" min="0" step="0.01" value={scopeMae} onChange={(event) => setScopeMae(event.target.value)} required /></label>
          <label className={styles.field}><span className={styles.label}>Minimum effort accuracy</span><input className={styles.input} type="number" min="0" max="1" step="0.01" value={effortAccuracy} onChange={(event) => setEffortAccuracy(event.target.value)} required /></label>
        </div>
        <p className={styles.help}>Observed metrics are computed server-side from the persisted reviews and latest validation outcomes in this immutable case manifest.</p>
        <button className={styles.primary} disabled={publish.isPending || splitValues(cases).length === 0} type="submit">{publish.isPending ? "Evaluating…" : "Evaluate and publish corpus"}</button>
        {publish.isError ? <p className={styles.error} role="alert">{errorMessage(publish.error)}</p> : null}
      </form>
    </section>
  );
}

function EcosystemCard({ admission }: { admission: EcosystemAdmissionSummary }) {
  const queryClient = useQueryClient();
  const [minimumRepositories, setMinimumRepositories] = useState(String(admission.minimum_repositories));
  const [minimumShare, setMinimumShare] = useState(String(admission.minimum_dependency_share));
  const evaluate = useMutation({
    mutationFn: () => stackGraphClient.evaluateEcosystemAdmission(admission.ecosystem, {
      minimum_repositories: Number(minimumRepositories), minimum_dependency_share: Number(minimumShare),
    }),
    onSuccess: (next) => queryClient.setQueryData(["admin", "modernization-governance"], next),
  });
  const statusClass = admission.status === "ADMITTED"
    ? styles.statusGood
    : admission.status === "PROPOSED" || admission.status === "STALE"
      ? styles.statusBad
      : styles.statusMuted;

  return (
    <article className={styles.ecosystemCard}>
      <div className={styles.governanceCardHead}>
        <div><span className={styles.eyebrow}>Sequence {admission.sequence}</span><h3 className={styles.cardTitle}>{admission.ecosystem}</h3></div>
        <span className={statusClass}>{admission.status.toLowerCase().replace("_", " ")}</span>
      </div>
      <dl className={styles.admissionMetrics}>
        <div><dt>Repositories</dt><dd>{admission.observed_repositories}</dd></div>
        <div><dt>Dependency share</dt><dd>{(admission.observed_dependency_share * 100).toFixed(1)}%</dd></div>
        <div><dt>Metadata parity</dt><dd>{admission.metadata_parity ? "Ready" : "Missing"}</dd></div>
        <div><dt>Calibration</dt><dd>{admission.calibration_gate_passed ? "Passed" : "Blocked"}</dd></div>
      </dl>
      {admission.reasons.length ? <ul className={styles.reasonList}>{admission.reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul> : <p className={styles.success}>All admission gates pass.</p>}
      <div className={styles.thresholdRow}>
        <label className={styles.field}><span className={styles.label}>Min repos</span><input className={styles.inputSmall} type="number" min="1" value={minimumRepositories} onChange={(event) => setMinimumRepositories(event.target.value)} /></label>
        <label className={styles.field}><span className={styles.label}>Min share</span><input className={styles.inputSmall} type="number" min="0" max="1" step="0.01" value={minimumShare} onChange={(event) => setMinimumShare(event.target.value)} /></label>
      </div>
      <button className={styles.ghost} type="button" disabled={evaluate.isPending} onClick={() => evaluate.mutate()}>{evaluate.isPending ? "Evaluating…" : "Evaluate current evidence"}</button>
      {evaluate.isError ? <p className={styles.error} role="alert">{errorMessage(evaluate.error)}</p> : null}
    </article>
  );
}

function EcosystemAdmissions({ state }: { state: ModernizationGovernanceState }) {
  return (
    <section className={styles.governanceCard} aria-labelledby="ecosystem-admission-heading">
      <div className={styles.governanceCardHead}>
        <div><span className={styles.eyebrow}>Bounded expansion</span><h2 id="ecosystem-admission-heading" className={styles.cardTitle}>Ecosystem admission</h2></div>
      </div>
      <p className={styles.sectionNote}>Demand is recalculated from current, active dependency evidence. PyPI metadata parity is implemented; later ecosystems stay blocked until their adapter exists and every preceding gate is current.</p>
      <div className={styles.ecosystemGrid}>{state.ecosystem_admissions.map((admission) => <EcosystemCard key={admission.ecosystem} admission={admission} />)}</div>
    </section>
  );
}

type GovernanceView = "rules" | "eligibility" | "catalog" | "calibration" | "ecosystems";
const GOVERNANCE_VIEWS: readonly GovernanceView[] = ["rules", "eligibility", "catalog", "calibration", "ecosystems"];

export function GovernanceSection({ initialView }: { initialView?: string | null }) {
  const [view, setView] = useState<GovernanceView>(
    GOVERNANCE_VIEWS.includes(initialView as GovernanceView) ? initialView as GovernanceView : "rules",
  );
  const governance = useQuery({
    queryKey: ["admin", "modernization-governance"],
    queryFn: () => stackGraphClient.getModernizationGovernance(),
  });

  if (governance.isLoading) return <p className={styles.empty}>Loading modernization governance…</p>;
  if (governance.isError) return <p className={styles.error} role="alert">{errorMessage(governance.error)}</p>;
  if (!governance.data) return <p className={styles.empty}>Governance state is unavailable.</p>;

  const state = governance.data;
  const views = [
    { key: "rules", label: "Insight rules", detail: "Finding logic" },
    { key: "eligibility", label: "Eligibility", detail: "Ranking policy" },
    { key: "catalog", label: "Replacements", detail: "Internal catalog" },
    { key: "calibration", label: "Calibration", detail: "Promotion gate" },
    { key: "ecosystems", label: "Ecosystems", detail: "Expansion gates" },
  ] as const;
  return (
    <div className={styles.section}>
      <p className={styles.sectionNote}>Govern the evidence and policy boundaries used by modernization ranking. Choose one policy area to review or change; updates remain audited and trigger fingerprinted estate reanalysis.</p>
      <div className={styles.subtabs} role="tablist" aria-label="Modernization governance areas">
        {views.map((item) => (
          <button
            key={item.key}
            id={`governance-tab-${item.key}`}
            className={`${styles.subtab} ${view === item.key ? styles.subtabActive : ""}`}
            type="button"
            role="tab"
            aria-selected={view === item.key}
            aria-controls={`governance-panel-${item.key}`}
            onClick={() => setView(item.key)}
          >
            <strong>{item.label}</strong>
            <small>{item.detail}</small>
          </button>
        ))}
      </div>
      <div
        id={`governance-panel-${view}`}
        className={styles.subtabPanel}
        role="tabpanel"
        aria-labelledby={`governance-tab-${view}`}
      >
        {view === "rules" ? <DeterministicRulesEditor /> : null}
        {view === "eligibility" ? <PolicyEditor key={`${state.active_policy?.id ?? "new"}:${state.active_policy?.configuration_fingerprint ?? "none"}`} policy={state.active_policy} /> : null}
        {view === "catalog" ? <InternalCatalogEditor state={state} /> : null}
        {view === "calibration" ? <CalibrationEditor key={state.active_calibration?.evaluation_fingerprint ?? "new"} state={state} /> : null}
        {view === "ecosystems" ? <EcosystemAdmissions state={state} /> : null}
      </div>
    </div>
  );
}
