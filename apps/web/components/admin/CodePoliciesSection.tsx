"use client";

import { useDeferredValue, useMemo, useState } from "react";
import { IconCategory, IconChecklist } from "@tabler/icons-react";
import type { FormEvent } from "react";
import {
  ApiRequestError,
  config,
  stackGraphClient,
  type CodeFunctionStatus,
  type TenantCodeFunctionSummary,
  type TenantCodeFunctionUpsertRequest,
  type TenantCodePolicyState,
} from "@stackgraph/shared";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import styles from "./admin.module.css";

const NEW_FUNCTION = "__new__";

function errorMessage(error: unknown): string {
  if (error instanceof ApiRequestError && error.detail && typeof error.detail === "object") {
    const message = (error.detail as { message?: unknown }).message;
    if (typeof message === "string") return message;
  }
  return error instanceof Error ? error.message : "The code-policy operation could not be completed.";
}

function shortFingerprint(value: string): string {
  return value.length > 24 ? `${value.slice(0, 15)}…${value.slice(-8)}` : value;
}

function PolicyEditor({
  state,
  selected,
  onSaved,
}: {
  state: TenantCodePolicyState;
  selected?: TenantCodeFunctionSummary;
  onSaved: (functionKey: string) => void;
}) {
  const queryClient = useQueryClient();
  const isPrimary = selected?.source === "PRIMARY";
  const [functionKey, setFunctionKey] = useState(selected?.function_key ?? "");
  const [name, setName] = useState(selected?.name ?? "");
  const [description, setDescription] = useState(selected?.description ?? "");
  const [domainKey, setDomainKey] = useState(selected?.domain_key ?? "frontend");
  const [status, setStatus] = useState<CodeFunctionStatus>(selected?.status ?? "ACTIVE");
  const [allowedIds, setAllowedIds] = useState<string[]>(selected?.policy?.allowed_technology_ids ?? []);
  const [prohibitedIds, setProhibitedIds] = useState<string[]>(selected?.policy?.prohibited_technology_ids ?? []);
  const [technologySearch, setTechnologySearch] = useState("");
  const deferredSearch = useDeferredValue(technologySearch.trim().toLowerCase());
  const visibleTechnologies = useMemo(() => state.available_technologies.filter((item) => {
    if (!deferredSearch) return item.detected_repository_count > 0 || allowedIds.includes(item.technology.id) || prohibitedIds.includes(item.technology.id);
    return [item.technology.name, item.technology.canonical_key, item.domain_key, item.category_key]
      .some((value) => value?.toLowerCase().includes(deferredSearch));
  }).slice(0, 100), [allowedIds, deferredSearch, prohibitedIds, state.available_technologies]);

  const save = useMutation({
    mutationFn: ({ key, body }: { key: string; body: TenantCodeFunctionUpsertRequest }) => (
      stackGraphClient.upsertTenantCodeFunction(key, body)
    ),
    onSuccess: (next, variables) => {
      queryClient.setQueryData(["admin", "code-policies"], next);
      onSaved(variables.key);
    },
  });

  function setTechnologyDecision(technologyId: string, decision: "" | "ALLOW" | "PROHIBIT") {
    setAllowedIds((current) => decision === "ALLOW"
      ? [...new Set([...current, technologyId])]
      : current.filter((item) => item !== technologyId));
    setProhibitedIds((current) => decision === "PROHIBIT"
      ? [...new Set([...current, technologyId])]
      : current.filter((item) => item !== technologyId));
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    const key = (selected?.function_key ?? functionKey).trim().toLowerCase();
    save.mutate({
      key,
      body: {
        source: selected?.source ?? "CUSTOM",
        name: (isPrimary ? selected.name : name).trim(),
        description: (isPrimary ? selected.description : description).trim(),
        domain_key: (isPrimary ? selected.domain_key : domainKey).trim().toLowerCase(),
        status: isPrimary ? "ACTIVE" : status,
        allowed_technology_ids: allowedIds,
        prohibited_technology_ids: prohibitedIds,
      },
    });
  }

  return (
    <form className={styles.governanceForm} onSubmit={submit}>
      <div className={styles.fieldGrid}>
        <label className={styles.field}>
          <span className={styles.label}>Function key</span>
          <input
            className={styles.input}
            value={selected?.function_key ?? functionKey}
            onChange={(event) => setFunctionKey(event.target.value)}
            pattern="[a-z][a-z0-9.-]{1,127}"
            placeholder="tenant-design-tokens"
            readOnly={Boolean(selected)}
            required
          />
        </label>
        <label className={styles.field}>
          <span className={styles.label}>Domain</span>
          <input className={styles.input} value={isPrimary ? selected.domain_key : domainKey} onChange={(event) => setDomainKey(event.target.value)} readOnly={isPrimary} required />
        </label>
      </div>
      <label className={styles.field}>
        <span className={styles.label}>Function name</span>
        <input className={styles.input} value={isPrimary ? selected.name : name} onChange={(event) => setName(event.target.value)} readOnly={isPrimary} required />
      </label>
      <label className={styles.field}>
        <span className={styles.label}>Definition</span>
        <textarea className={styles.textarea} value={isPrimary ? selected.description : description} onChange={(event) => setDescription(event.target.value)} readOnly={isPrimary} />
        <span className={styles.help}>{isPrimary ? "Primary definitions come from StackGraph’s curated catalog." : "Custom functions extend the primary catalog for tenant-specific classification."}</span>
      </label>
      {!isPrimary && selected ? (
        <label className={styles.field}>
          <span className={styles.label}>Custom function status</span>
          <select className={styles.select} value={status} onChange={(event) => setStatus(event.target.value as CodeFunctionStatus)}>
            <option value="ACTIVE">Active</option>
            <option value="RETIRED">Retired</option>
          </select>
        </label>
      ) : null}

      <div className={styles.policyBoundary}>
        <div>
          <h3 className={styles.subheading}>Technology boundary</h3>
          <p className={styles.help}>A non-empty allowlist is exclusive. Prohibited always takes precedence.</p>
        </div>
        <label className={styles.field}>
          <span className={styles.label}>Find detected or catalog technology</span>
          <input className={styles.input} type="search" value={technologySearch} onChange={(event) => setTechnologySearch(event.target.value)} placeholder="Redux, Zustand, React…" />
        </label>
        <div className={styles.technologyPolicyList}>
          {visibleTechnologies.map((item) => {
            const decision = prohibitedIds.includes(item.technology.id) ? "PROHIBIT" : allowedIds.includes(item.technology.id) ? "ALLOW" : "";
            return (
              <label key={item.technology.id} className={styles.technologyPolicyRow}>
                <span className={styles.technologyPolicyName}>
                  <strong>{item.technology.name}</strong>
                  <small>{item.classification.toLowerCase().replace("_", " ")} · {item.detected_repository_count} repositories</small>
                </span>
                <select
                  className={styles.selectCompact}
                  aria-label={`Policy decision for ${item.technology.name}`}
                  value={decision}
                  onChange={(event) => setTechnologyDecision(item.technology.id, event.target.value as "" | "ALLOW" | "PROHIBIT")}
                >
                  <option value="">Unspecified</option>
                  <option value="ALLOW">Allowed</option>
                  <option value="PROHIBIT">Prohibited</option>
                </select>
              </label>
            );
          })}
          {!visibleTechnologies.length ? <p className={styles.empty}>No matching technology. Try a catalog name or connect and scan the repository first.</p> : null}
        </div>
        {state.technology_catalog_truncated ? <p className={styles.help}>The picker is limited to the first 2,000 detected and curated technologies.</p> : null}
      </div>

      <div className={styles.actions}>
        <button className={styles.primary} type="submit" disabled={save.isPending || (!selected && !functionKey.trim())}>
          {save.isPending ? "Saving…" : "Save function policy"}
        </button>
        <span className={styles.help}>{allowedIds.length} allowed · {prohibitedIds.length} prohibited</span>
      </div>
      {save.isError ? <p className={styles.error} role="alert">{errorMessage(save.error)}</p> : null}
      {save.isSuccess ? <p className={styles.success} role="status">Policy saved. Existing repository results are now stale until reevaluated.</p> : null}
    </form>
  );
}

function EvaluationResults({ state }: { state: TenantCodePolicyState }) {
  const queryClient = useQueryClient();
  const evaluate = useMutation({
    mutationFn: () => stackGraphClient.evaluateTenantCodePolicies(),
    onSuccess: (next) => queryClient.setQueryData(["admin", "code-policies"], next),
  });
  return (
    <section className={styles.governanceCard} aria-labelledby="code-policy-evaluation-heading">
      <div className={styles.governanceCardHead}>
        <div>
          <span className={styles.eyebrow}>Estate alignment</span>
          <h2 id="code-policy-evaluation-heading" className={styles.cardTitle}>Repository evaluation</h2>
        </div>
        <button className={styles.primary} type="button" onClick={() => evaluate.mutate()} disabled={evaluate.isPending}>
          {evaluate.isPending ? "Evaluating…" : "Evaluate all repositories"}
        </button>
      </div>
      <dl className={styles.metricGrid}>
        <div><dt>Compliant</dt><dd>{state.summary.compliant_repositories}</dd></div>
        <div><dt>Misaligned</dt><dd>{state.summary.misaligned_repositories}</dd></div>
        <div><dt>Stale</dt><dd>{state.summary.stale_repositories}</dd></div>
        <div><dt>Evaluated</dt><dd>{state.summary.evaluated_repositories}</dd></div>
      </dl>
      {evaluate.isError ? <p className={styles.error} role="alert">{errorMessage(evaluate.error)}</p> : null}
      {state.evaluations.length ? (
        <ul className={styles.policyEvaluationList}>
          {state.evaluations.map((evaluation) => (
            <li key={evaluation.id} className={styles.policyEvaluationItem}>
              <div className={styles.governanceCardHead}>
                <div>
                  <strong>{evaluation.repository.name}</strong>
                  <p className={styles.help}>Evaluated {new Date(evaluation.evaluated_at).toLocaleString()} by {evaluation.evaluated_by}</p>
                </div>
                <span className={evaluation.status === "COMPLIANT" ? styles.statusGood : evaluation.status === "MISALIGNED" ? styles.statusBad : styles.statusMuted}>{evaluation.status.toLowerCase()}</span>
              </div>
              {evaluation.violations.length ? (
                <ul className={styles.reasonList}>
                  {evaluation.violations.map((violation) => (
                    <li key={`${violation.rule}:${violation.function_key}:${violation.technology.id}`}>
                      {violation.message} {violation.fact_ids.map((factId) => <a key={factId} href={`${config.apiBaseUrl}/api/v1/facts/${factId}/evidence`}>Evidence</a>)}
                    </li>
                  ))}
                </ul>
              ) : null}
              {evaluation.unclassified_technologies.length ? <p className={styles.help}>{evaluation.unclassified_technologies.length} technologies remain unclassified and can be assigned through a custom function.</p> : null}
            </li>
          ))}
        </ul>
      ) : <p className={styles.empty}>No repository evaluations yet.</p>}
    </section>
  );
}

export function CodePoliciesSection() {
  const [selectedKey, setSelectedKey] = useState(NEW_FUNCTION);
  const [view, setView] = useState<"functions" | "evaluation">("functions");
  const policies = useQuery({
    queryKey: ["admin", "code-policies"],
    queryFn: () => stackGraphClient.getTenantCodePolicies(),
  });
  if (policies.isLoading) return <p className={styles.empty}>Loading tenant code policies…</p>;
  if (policies.isError) return <p className={styles.error} role="alert">{errorMessage(policies.error)}</p>;
  if (!policies.data) return <p className={styles.empty}>Tenant code-policy state is unavailable.</p>;

  const state = policies.data;
  const selected = state.functions.find((item) => item.function_key === selectedKey);
  return (
    <div className={styles.section}>
      <p className={styles.sectionNote}>Define tenant-specific technology boundaries by code function, then evaluate the estate against the saved policy set. StackGraph’s curated classification stays primary; custom functions provide a governed overlay.</p>
      <div className={styles.subtabs} role="tablist" aria-label="Code policy areas">
        <button
          id="code-policy-tab-functions"
          className={`${styles.subtab} ${view === "functions" ? styles.subtabActive : ""}`}
          type="button"
          role="tab"
          aria-selected={view === "functions"}
          aria-controls="code-policy-panel-functions"
          onClick={() => setView("functions")}
        >
          <span className={styles.subtabLabel}>
            <IconCategory size={15} stroke={1.5} aria-hidden="true" />
            <strong>Function policies</strong>
          </span>
          <small>{state.summary.governed_functions} governed</small>
        </button>
        <button
          id="code-policy-tab-evaluation"
          className={`${styles.subtab} ${view === "evaluation" ? styles.subtabActive : ""}`}
          type="button"
          role="tab"
          aria-selected={view === "evaluation"}
          aria-controls="code-policy-panel-evaluation"
          onClick={() => setView("evaluation")}
        >
          <span className={styles.subtabLabel}>
            <IconChecklist size={15} stroke={1.5} aria-hidden="true" />
            <strong>Repository alignment</strong>
          </span>
          <small>{state.summary.misaligned_repositories} misaligned</small>
        </button>
      </div>
      <div
        id={`code-policy-panel-${view}`}
        className={styles.subtabPanel}
        role="tabpanel"
        aria-labelledby={`code-policy-tab-${view}`}
      >
        {view === "functions" ? (
          <section className={styles.governanceCard} aria-labelledby="code-policy-editor-heading">
            <div className={styles.governanceCardHead}>
              <div>
                <span className={styles.eyebrow}>Tenant policy</span>
                <h2 id="code-policy-editor-heading" className={styles.cardTitle}>Function technology policy</h2>
              </div>
              <span className={styles.statusMuted}>{state.summary.governed_functions} governed</span>
            </div>
            <p className={styles.fingerprint} title={state.policy_set_fingerprint}>Policy set <span className="sg-mono">{shortFingerprint(state.policy_set_fingerprint)}</span></p>
            <label className={styles.field}>
              <span className={styles.label}>Function to govern</span>
              <select className={styles.select} value={selectedKey} onChange={(event) => setSelectedKey(event.target.value)}>
                <option value={NEW_FUNCTION}>Create a custom function</option>
                {state.functions.map((item) => <option key={item.function_key} value={item.function_key}>{item.name} · {item.source.toLowerCase()}{item.policy ? " · governed" : ""}</option>)}
              </select>
            </label>
            <PolicyEditor key={selectedKey} state={state} selected={selected} onSaved={setSelectedKey} />
          </section>
        ) : <EvaluationResults state={state} />}
      </div>
    </div>
  );
}
