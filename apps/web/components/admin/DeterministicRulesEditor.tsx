"use client";

import { useState } from "react";
import type { FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ApiRequestError,
  stackGraphClient,
  type DeterministicInsightRuleSummary,
  type InsightSeverity,
} from "@stackgraph/shared";
import styles from "./admin.module.css";

const SEVERITIES: InsightSeverity[] = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"];

function errorMessage(error: unknown) {
  if (error instanceof ApiRequestError && error.detail && typeof error.detail === "object") {
    const detail = error.detail as { message?: unknown };
    if (typeof detail.message === "string") return detail.message;
  }
  return error instanceof Error ? error.message : "The rule policy could not be saved.";
}

function RuleEditor({ rule }: { rule: DeterministicInsightRuleSummary }) {
  const queryClient = useQueryClient();
  const [enabled, setEnabled] = useState(rule.enabled);
  const [severity, setSeverity] = useState<InsightSeverity>(rule.severity);
  const [minimumRepositories, setMinimumRepositories] = useState(String(rule.minimum_repositories));
  const save = useMutation({
    mutationFn: () => stackGraphClient.updateDeterministicInsightRule(rule.rule_key, {
      enabled,
      severity,
      minimum_repositories: Math.max(1, Number(minimumRepositories) || 1),
      configuration: rule.configuration,
      expected_version: rule.version,
    }),
    onSuccess: (next) => queryClient.setQueryData(["admin", "deterministic-insight-governance"], next),
  });
  const changed = enabled !== rule.enabled
    || severity !== rule.severity
    || Number(minimumRepositories) !== rule.minimum_repositories;
  const unavailable = rule.readiness === "NEEDS_DATA";

  function submit(event: FormEvent) {
    event.preventDefault();
    save.mutate();
  }

  return (
    <form className={styles.ruleRow} onSubmit={submit}>
      <div className={styles.ruleIdentity}>
        <div className={styles.ruleTitleRow}>
          <strong>{rule.name}</strong>
          <span className={unavailable ? styles.statusMuted : rule.enabled ? styles.statusGood : styles.statusBad}>
            {unavailable ? "needs data" : rule.enabled ? "active" : "paused"}
          </span>
        </div>
        <code className={`${styles.ruleKey} sg-mono`}>{rule.rule_key}</code>
        <p>{rule.description}</p>
        <span className={styles.ruleFindingCount}>{rule.finding_count} current finding{rule.finding_count === 1 ? "" : "s"}</span>
        {rule.missing_inputs.length > 0 ? (
          <details className={styles.ruleInputs}>
            <summary>{rule.missing_inputs.length} required input{rule.missing_inputs.length === 1 ? "" : "s"}</summary>
            <ul>{rule.missing_inputs.map((item) => <li key={item}>{item}</li>)}</ul>
          </details>
        ) : null}
      </div>
      <div className={styles.ruleControls}>
        <label className={styles.checkLabel}>
          <input type="checkbox" checked={enabled} disabled={unavailable} onChange={(event) => setEnabled(event.target.checked)} />
          Enabled
        </label>
        <label className={styles.field}>
          <span className={styles.label}>Severity</span>
          <select className={styles.selectCompact} value={severity} onChange={(event) => setSeverity(event.target.value as InsightSeverity)}>
            {SEVERITIES.map((item) => <option key={item}>{item}</option>)}
          </select>
        </label>
        <label className={styles.field}>
          <span className={styles.label}>Min repositories</span>
          <input className={styles.inputSmall} type="number" min="1" value={minimumRepositories} onChange={(event) => setMinimumRepositories(event.target.value)} />
        </label>
        <button className={styles.ghost} type="submit" disabled={!changed || save.isPending}>
          {save.isPending ? "Saving…" : "Save rule"}
        </button>
      </div>
      {save.isError ? <p className={styles.ruleError} role="alert">{errorMessage(save.error)}</p> : null}
    </form>
  );
}

export function DeterministicRulesEditor() {
  const [phase, setPhase] = useState<1 | 2>(1);
  const governance = useQuery({
    queryKey: ["admin", "deterministic-insight-governance"],
    queryFn: () => stackGraphClient.getDeterministicInsightGovernance(),
  });

  if (governance.isLoading) return <p className={styles.empty}>Loading deterministic rule governance…</p>;
  if (governance.isError) return <p className={styles.error} role="alert">{errorMessage(governance.error)}</p>;
  if (!governance.data) return <p className={styles.empty}>Deterministic rule governance is unavailable.</p>;

  const state = governance.data;
  return (
    <section className={styles.governanceCard} aria-labelledby="deterministic-rules-heading">
      <div className={styles.governanceCardHead}>
        <div>
          <span className={styles.eyebrow}>Deterministic engine</span>
          <h2 id="deterministic-rules-heading" className={styles.cardTitle}>Insight rules and data readiness</h2>
        </div>
        <span className={styles.statusGood}>{state.active_rule_count} active</span>
      </div>
      <p className={styles.sectionNote}>
        These tenant-scoped rules decide whether a finding exists. AI can explain the resulting evidence, but cannot create, remove, or reprioritize a finding.
      </p>
      <dl className={styles.metricGrid}>
        <div><dt>Current findings</dt><dd>{state.finding_count}</dd></div>
        <div><dt>Evidence coverage</dt><dd>{Math.round(state.evidence_coverage * 100)}%</dd></div>
        <div><dt>Waiting on data</dt><dd>{state.needs_data_rule_count}</dd></div>
      </dl>
      <p className={styles.fingerprint}>Method <span className="sg-mono">{state.method_version}</span> · evaluated {new Date(state.last_evaluated_at).toLocaleString()}</p>
      <div className={styles.phaseTabs} role="tablist" aria-label="Insight rule phases">
        {[1, 2].map((item) => {
          const phaseNumber = item as 1 | 2;
          const count = state.rules.filter((rule) => rule.phase === phaseNumber).length;
          return (
            <button
              key={phaseNumber}
              type="button"
              role="tab"
              aria-selected={phase === phaseNumber}
              className={`${styles.phaseTab} ${phase === phaseNumber ? styles.phaseTabActive : ""}`}
              onClick={() => setPhase(phaseNumber)}
            >
              <span>Phase {phaseNumber}</span>
              <strong>{phaseNumber === 1 ? "Trustworthy findings" : "Code & business impact"}</strong>
              <small>{count} rules</small>
            </button>
          );
        })}
      </div>
      <div className={styles.phaseList}>
        {[phase].map((activePhase) => (
          <section key={activePhase} className={styles.phase} aria-labelledby={`deterministic-phase-${activePhase}`}>
            <header className={styles.phaseHead}>
              <div>
                <span className={styles.eyebrow}>Phase {activePhase}</span>
                <h3 id={`deterministic-phase-${activePhase}`}>
                  {activePhase === 1 ? "Trustworthy findings" : "Code and business impact"}
                </h3>
              </div>
              <span>{state.rules.filter((rule) => rule.phase === activePhase).length} rules</span>
            </header>
            <div className={styles.ruleList}>
              {state.rules.filter((rule) => rule.phase === activePhase).map((rule) => (
                <RuleEditor key={`${rule.rule_key}:${rule.version}`} rule={rule} />
              ))}
            </div>
          </section>
        ))}
      </div>
    </section>
  );
}
