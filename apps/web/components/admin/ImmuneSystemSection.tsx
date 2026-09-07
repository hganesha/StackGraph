"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { IconBug, IconTrophy, IconVaccine } from "@tabler/icons-react";
import {
  stackGraphClient,
  type AdversarialScenarioList,
  type AdversarialScenarioModel,
  type HarnessEvaluationModel,
} from "@stackgraph/shared";
import { GateNotice, Skeleton } from "@stackgraph/design-system";
import styles from "./ImmuneSystemSection.module.css";

const CLASS_LABEL: Record<string, string> = {
  STALE_CONTEXT: "Stale context",
  CONFLICTING_DOCUMENTATION: "Conflicting documentation",
  PARTIAL_TOOL_OUTAGE: "Partial tool outage",
  MALFORMED_API_RESPONSE: "Malformed API response",
  UNEXPECTED_SCHEMA_CHANGE: "Unexpected schema change",
  MALICIOUS_REPOSITORY_CONTENT: "Malicious repository content",
  CONCURRENT_AGENT_ACTIONS: "Concurrent agent actions",
  TOPOLOGY_DOCUMENTATION_MISMATCH: "Topology differs from documentation",
};

// The four statuses answer different questions, and the copy has to keep them apart: a class
// with no scenarios is never the same claim as a class this estate is safe from.
const STATUS_LABEL: Record<string, string> = {
  GENERATED: "Derived",
  NOT_DERIVABLE: "No evidence in this estate",
  NOT_ATTEMPTED: "Not generated",
  GENERATION_DISABLED: "Generation disabled",
};

function ScenarioCard({
  scenario, selected, onToggle,
}: {
  scenario: AdversarialScenarioModel;
  selected: boolean;
  onToggle: () => void;
}) {
  const expected = scenario.expected_behaviour as {
    required_behaviours?: string[];
    forbidden_behaviours?: string[];
    rationale?: string;
  };
  return (
    <li className={styles.scenario} data-severity={scenario.severity}>
      <label className={styles.scenarioHead}>
        <input type="checkbox" checked={selected} onChange={onToggle} />
        <span>
          <strong>{scenario.title}</strong>
          <small>{CLASS_LABEL[scenario.scenario_class] ?? scenario.scenario_class} · {scenario.severity}</small>
        </span>
      </label>
      <p>{scenario.description}</p>
      <dl className={styles.expectations}>
        <div>
          <dt>Must</dt>
          <dd>{(expected.required_behaviours ?? []).join(", ") || "—"}</dd>
        </div>
        <div>
          <dt>Must not</dt>
          <dd>{(expected.forbidden_behaviours ?? []).join(", ") || "—"}</dd>
        </div>
      </dl>
      <small className={styles.provenance}>
        {(scenario.evidence_fact_ids ?? []).length > 0
          ? `${(scenario.evidence_fact_ids ?? []).length} supporting fact(s) · ${scenario.generator_version}`
          : `Derived without a direct fact citation · ${scenario.generator_version}`}
      </small>
    </li>
  );
}

export function ImmuneSystemSection() {
  const queryClient = useQueryClient();
  const scenarios = useQuery({
    queryKey: ["immune-system", "scenarios"],
    queryFn: () => stackGraphClient.listAdversarialScenarios({ limit: 50 }),
  });
  const [selected, setSelected] = useState<string[]>([]);
  const [harnessKey, setHarnessKey] = useState("agent-harness:local");
  const [harnessVersion, setHarnessVersion] = useState("1.0.0");
  const [evaluation, setEvaluation] = useState<HarnessEvaluationModel | null>(null);
  const [diagnosis, setDiagnosis] = useState("");

  const generate = useMutation({
    mutationFn: () => stackGraphClient.generateAdversarialScenarios({}),
    onSuccess: (value: AdversarialScenarioList) => {
      queryClient.setQueryData(["immune-system", "scenarios"], value);
      setSelected([]);
    },
  });
  const start = useMutation({
    mutationFn: () => stackGraphClient.startHarnessEvaluation({
      harness_key: harnessKey.trim(),
      harness_version: harnessVersion.trim(),
      scenario_ids: selected,
    }),
    onSuccess: setEvaluation,
  });
  const record = useMutation({
    mutationFn: ({ scenarioId, outcome }: {
      scenarioId: string;
      outcome: "PASSED" | "FAILED" | "INCONCLUSIVE";
    }) => stackGraphClient.recordHarnessEvaluationResult(evaluation!.id, {
      scenario_id: scenarioId,
      outcome,
      observed_behaviour: { recorded_from: "admin-control-plane" },
      diagnosis: outcome === "FAILED" ? diagnosis.trim() : null,
    }),
    onSuccess: (value) => { setEvaluation(value); setDiagnosis(""); },
  });
  const finish = useMutation({
    mutationFn: (status: "COMPLETED" | "ABANDONED") =>
      stackGraphClient.finishHarnessEvaluation(evaluation!.id, { status }),
    onSuccess: setEvaluation,
  });

  const champions = useQuery({
    queryKey: ["immune-system", "champions"],
    queryFn: () => stackGraphClient.listHarnessChampions(),
  });
  const nextScenario = evaluation?.unevaluated_scenario_ids?.[0] ?? null;
  const scenarioTitle = useMemo(() => {
    const found = (scenarios.data?.scenarios ?? []).find((item) => item.id === nextScenario);
    return found?.title ?? nextScenario ?? "";
  }, [nextScenario, scenarios.data]);
  const requestError = generate.error ?? start.error ?? record.error ?? finish.error;

  return (
    <>
      <section className={styles.card} aria-labelledby="immune-scenarios-heading">
        <header>
          <IconVaccine size={20} aria-hidden="true" />
          <div>
            <h3 id="immune-scenarios-heading">Adversarial scenarios</h3>
            <p>
              Failure modes derived from this estate, not from a catalogue. Every class states
              whether it was generated, could not be derived here, or was never attempted.
            </p>
          </div>
        </header>

        {scenarios.isLoading ? <Skeleton height={180} /> : scenarios.isError ? (
          <GateNotice
            verdict="BLOCKED"
            reason="The scenario inventory could not be read, so no claim can be made about what this estate is exposed to."
          />
        ) : scenarios.data ? (
          <>
            {!scenarios.data.generation_enabled ? (
              <GateNotice
                verdict="CONSTRAIN"
                reason="Adversarial generation is disabled for this tenant. An empty class below means nothing has been derived — not that the estate is unaffected by it."
              />
            ) : null}
            <table className={styles.coverage}>
              <caption className={styles.visuallyHidden}>Scenario coverage by failure class</caption>
              <thead>
                <tr><th scope="col">Failure class</th><th scope="col">Status</th><th scope="col">Count</th><th scope="col">Why</th></tr>
              </thead>
              <tbody>
                {scenarios.data.coverage.map((item) => (
                  <tr key={item.scenario_class} data-status={item.status}>
                    <th scope="row">{CLASS_LABEL[item.scenario_class] ?? item.scenario_class}</th>
                    <td>{STATUS_LABEL[item.status] ?? item.status}</td>
                    <td>{item.scenario_count}</td>
                    <td>{item.detail}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className={styles.actions}>
              <button
                type="button"
                onClick={() => generate.mutate()}
                disabled={!scenarios.data.generation_enabled || generate.isPending}
              >
                {generate.isPending ? "Generating…" : "Generate from current estate"}
              </button>
              {scenarios.data.estate_watermark ? (
                <small>Estate watermark {scenarios.data.estate_watermark}</small>
              ) : null}
            </div>
            <ul className={styles.scenarios}>
              {(scenarios.data.scenarios ?? []).map((scenario) => (
                <ScenarioCard
                  key={scenario.id}
                  scenario={scenario}
                  selected={selected.includes(scenario.id)}
                  onToggle={() => setSelected((current) => (
                    current.includes(scenario.id)
                      ? current.filter((item) => item !== scenario.id)
                      : [...current, scenario.id]
                  ))}
                />
              ))}
            </ul>
            <ul className={styles.limitations}>
              {(scenarios.data.limitations ?? []).map((item) => <li key={item}>{item}</li>)}
            </ul>
          </>
        ) : null}
      </section>

      <section className={styles.card} aria-labelledby="immune-evaluation-heading">
        <header>
          <IconBug size={20} aria-hidden="true" />
          <div>
            <h3 id="immune-evaluation-heading">Offline harness evaluation</h3>
            <p>
              Scenarios are replayed against a harness offline. Nothing here reaches a running
              system, and no result promotes anything.
            </p>
          </div>
        </header>

        <div className={styles.form}>
          <label><span>Harness key</span><input value={harnessKey} onChange={(event) => setHarnessKey(event.target.value)} /></label>
          <label><span>Harness version</span><input value={harnessVersion} onChange={(event) => setHarnessVersion(event.target.value)} /></label>
          <button
            type="button"
            onClick={() => start.mutate()}
            disabled={selected.length === 0 || !harnessKey.trim() || start.isPending}
          >
            {selected.length === 0 ? "Select scenarios above" : `Evaluate ${selected.length} scenario(s)`}
          </button>
        </div>

        {evaluation ? (
          <div className={styles.evaluation}>
            <div className={styles.tally}>
              <span><b>{evaluation.passed_count}</b> passed</span>
              <span><b>{evaluation.failed_count}</b> failed</span>
              <span><b>{evaluation.inconclusive_count}</b> inconclusive</span>
              <span><b>{evaluation.unevaluated_count}</b> unanswered</span>
            </div>
            {evaluation.status === "RUNNING" && nextScenario ? (
              <div className={styles.recorder}>
                <p>Recording: {scenarioTitle}</p>
                <label className={styles.wide}>
                  <span>Diagnosis (required to record a failure)</span>
                  <input value={diagnosis} onChange={(event) => setDiagnosis(event.target.value)} />
                </label>
                <div className={styles.actions}>
                  <button type="button" onClick={() => record.mutate({ scenarioId: nextScenario, outcome: "PASSED" })} disabled={record.isPending}>Passed</button>
                  <button type="button" onClick={() => record.mutate({ scenarioId: nextScenario, outcome: "INCONCLUSIVE" })} disabled={record.isPending}>Inconclusive</button>
                  <button type="button" onClick={() => record.mutate({ scenarioId: nextScenario, outcome: "FAILED" })} disabled={record.isPending || !diagnosis.trim()}>Failed</button>
                </div>
              </div>
            ) : null}
            {evaluation.status === "RUNNING" ? (
              <div className={styles.actions}>
                <button type="button" onClick={() => finish.mutate("COMPLETED")} disabled={evaluation.unevaluated_count > 0 || finish.isPending}>Complete</button>
                <button type="button" onClick={() => finish.mutate("ABANDONED")} disabled={finish.isPending}>Abandon</button>
              </div>
            ) : <p className={styles.terminal}>{evaluation.status} · recorded outcomes are immutable.</p>}
            {(evaluation.results ?? []).some((item) => item.outcome === "FAILED") ? (
              <ul className={styles.failures}>
                {(evaluation.results ?? []).filter((item) => item.outcome === "FAILED").map((item) => (
                  <li key={item.id}><strong>{item.scenario_key}</strong> — {item.diagnosis}</li>
                ))}
              </ul>
            ) : null}
            {evaluation.promotion.state === "ELIGIBLE" ? (
              <p className={styles.eligible}>{evaluation.promotion.reason}</p>
            ) : (
              <GateNotice
                verdict="CONSTRAIN"
                reason={evaluation.promotion.reason}
                action={
                  <span>Blocked by: {(evaluation.promotion.blocked_by ?? []).join(", ")}</span>
                }
              />
            )}
          </div>
        ) : (
          <p className={styles.quiet}>
            Select scenarios above to start an evaluation. Failures are recorded with a diagnosis
            so they can feed the Harness Factory; promotion of a challenger is not implemented.
          </p>
        )}
        {requestError ? <p className={styles.error} role="alert">{requestError.message}</p> : null}
      </section>

      <section className={styles.card} aria-labelledby="immune-promotion-heading">
        <header>
          <IconTrophy size={20} aria-hidden="true" />
          <div>
            <h3 id="immune-promotion-heading">Champion and challenger</h3>
            <p>
              A challenger becomes the champion only on evidence: a clean evaluation covering
              every derived class and everything the incumbent was tested against, a passed
              rollback drill, and a second person&apos;s approval.
            </p>
          </div>
        </header>

        {champions.isLoading ? <Skeleton height={140} /> : champions.isError ? (
          <GateNotice
            verdict="BLOCKED"
            reason="The champion record could not be read, so which harness version is current is unknown."
          />
        ) : champions.data ? (
          <>
            {!champions.data.promotion_enabled ? (
              <GateNotice
                verdict="CONSTRAIN"
                reason="Promotion is switched off for this tenant. An empty champion list below says nothing about whether a challenger would qualify."
              />
            ) : null}
            {(champions.data.champions ?? []).length > 0 ? (
              <ul className={styles.champions}>
                {(champions.data.champions ?? []).map((champion) => (
                  <li key={champion.harness_key}>
                    <strong>{champion.harness_key}</strong>
                    <span>
                      running {champion.harness_version}
                      {champion.previous_version ? ` · replaced ${champion.previous_version}` : ""}
                    </span>
                    <small>
                      promoted by {champion.promoted_by} on{" "}
                      {new Date(champion.promoted_at).toLocaleDateString()}
                    </small>
                  </li>
                ))}
              </ul>
            ) : (
              <p className={styles.quiet}>No harness has a recorded champion in this tenant.</p>
            )}

            {(champions.data.recent_promotions ?? []).length > 0 ? (
              <ol className={styles.promotions}>
                {(champions.data.recent_promotions ?? []).map((promotion) => (
                  <li key={promotion.id} data-status={promotion.status}>
                    <div>
                      <strong>
                        {promotion.harness_key} → {promotion.challenger_version}
                      </strong>
                      <span>
                        {promotion.status}
                        {promotion.decided_by ? ` · approved by ${promotion.decided_by}` : ""}
                        {promotion.rolled_back_by ? ` · rolled back by ${promotion.rolled_back_by}` : ""}
                      </span>
                    </div>
                    {(promotion.gate.reasons ?? []).length > 0 ? (
                      <ul className={styles.gateReasons}>
                        {(promotion.gate.reasons ?? []).map((reason) => (
                          <li key={reason.code}>{reason.message}</li>
                        ))}
                      </ul>
                    ) : null}
                  </li>
                ))}
              </ol>
            ) : null}
            <ul className={styles.limitations}>
              {(champions.data.limitations ?? []).map((item) => <li key={item}>{item}</li>)}
            </ul>
          </>
        ) : null}
      </section>
    </>
  );
}
