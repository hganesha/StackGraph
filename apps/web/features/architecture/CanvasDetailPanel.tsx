"use client";

import Link from "next/link";
import type {
  CanvasCellComparisonView,
  CanvasCellProjectionView,
  CanvasPolicyDecision,
  CanvasPolicyIntent,
  ArchitectureCellView,
  MeasureResultModel,
} from "@stackgraph/shared";
import { CitationChip, ConfidenceChip } from "@stackgraph/design-system";
import {
  APPLICABILITY_LABEL,
  CELL_STATE_DESCRIPTION,
  CELL_STATE_LABEL,
  COMPARISON_LABEL,
  MEASURE_LABEL,
  MEASURE_STATUS_LABEL,
  OBSERVATION_LABEL,
  POLICY_LABEL,
  PostureMeter,
} from "@stackgraph/canvas-ui";
import { useEvidenceStore } from "@/lib/evidenceStore";
import styles from "./architecture.module.css";

/**
 * The cell detail panel (spec §11.3). Everything the cell had to compress is expanded
 * here in a fixed order: what is here, what was expected, what was observed, what was
 * measured, what the target says, and what the evidence is. Nothing is omitted because
 * it is null — a null measure states why it is null.
 */
export function CanvasDetailPanel({
  definition,
  cell,
  comparison,
  canGovern,
  onClose,
  onPolicyIntent,
  onRemoveException,
}: {
  definition: ArchitectureCellView;
  cell: CanvasCellProjectionView;
  comparison: CanvasCellComparisonView | null;
  canGovern: boolean;
  onClose: () => void;
  onPolicyIntent?: (intent: CanvasPolicyIntent) => void;
  onRemoveException?: (cellKey: string, exceptionId: string) => void;
}) {
  const openEvidence = useEvidenceStore((state) => state.open);
  const observation = cell.observation;
  const measures = cell.measures;

  return (
    <aside className={styles.panel} aria-label={`${definition.label} detail`}>
      <header className={styles.panelHead}>
        <div>
          <h2 className={styles.panelTitle}>{definition.label}</h2>
          <p className={styles.panelDefinition}>{definition.definition}</p>
        </div>
        <button type="button" className={styles.panelClose} onClick={onClose} aria-label="Close cell detail">
          ×
        </button>
      </header>

      <section className={styles.panelSection} aria-labelledby="panel-state">
        <h3 className={styles.panelSectionTitle} id="panel-state">
          State
        </h3>
        <p className={styles.panelLead}>
          <strong>{CELL_STATE_LABEL[cell.state]}</strong> — {CELL_STATE_DESCRIPTION[cell.state]}
        </p>
        <p className={styles.panelBody}>{cell.state_reason}</p>
        {comparison ? (
          <p className={styles.panelBody}>
            <strong>{COMPARISON_LABEL[comparison.status]}</strong> — {comparison.status_reason}
          </p>
        ) : null}
      </section>

      <section className={styles.panelSection} aria-labelledby="panel-expectation">
        <h3 className={styles.panelSectionTitle} id="panel-expectation">
          Expectation
        </h3>
        <dl className={styles.panelFacts}>
          <div>
            <dt>Applicability</dt>
            <dd>{APPLICABILITY_LABEL[cell.expectation.applicability]}</dd>
          </div>
          <div>
            <dt>Implementations</dt>
            <dd>
              {cell.expectation.minimum_implementations ?? "—"} to{" "}
              {cell.expectation.maximum_implementations ?? "unbounded"}
            </dd>
          </div>
          <div>
            <dt>Allowed diversity</dt>
            <dd>{cell.expectation.allowed_diversity ?? "unbounded"}</dd>
          </div>
          <div>
            <dt>Source</dt>
            <dd>{cell.expectation.source === "TENANT_PROFILE" ? "Tenant profile" : "Reference model"}</dd>
          </div>
        </dl>
        {cell.expectation.rationale ? (
          <p className={styles.panelBody}>
            {cell.expectation.rationale}
            {cell.expectation.owner ? ` — ${cell.expectation.owner}` : ""}
          </p>
        ) : null}
        {canGovern && onPolicyIntent ? (
          <button
            type="button"
            className={styles.panelAction}
            onClick={() =>
              onPolicyIntent({
                kind: "SET_EXPECTATION",
                cell_key: cell.cell_key,
                expectation: {
                  applicability: cell.expectation.applicability,
                  minimum_implementations: cell.expectation.minimum_implementations,
                  maximum_implementations: cell.expectation.maximum_implementations,
                  allowed_diversity: cell.expectation.allowed_diversity,
                },
              })
            }
          >
            Change the expectation
          </button>
        ) : null}
      </section>

      {cell.occupants.length ? (
        <section className={styles.panelSection} aria-labelledby="panel-occupants">
          <h3 className={styles.panelSectionTitle} id="panel-occupants">
            Implementations ({cell.occupant_total})
          </h3>
          <ul className={styles.occupantList}>
            {cell.occupants.map((occupant) => (
              <li key={`${occupant.technology.id}:${occupant.placement_keys.join("|")}`}>
                <div className={styles.occupantRow}>
                  <Link href={`/technologies/${occupant.technology.id}`} className={styles.occupantName}>
                    {occupant.technology.name}
                  </Link>
                  <span className={styles.occupantPolicy}>{POLICY_LABEL[occupant.policy_status]}</span>
                  <ConfidenceChip label={occupant.confidence_label} value={occupant.confidence} />
                </div>
                <p className={styles.occupantMeta}>
                  {occupant.classification.replace("_", " ").toLowerCase()} ·{" "}
                  {occupant.adoption.applications} apps · {occupant.adoption.repositories} repos ·{" "}
                  {occupant.adoption.deployments} deployments
                </p>
                {occupant.placement_keys.length ? (
                  <p className={styles.occupantMeta}>
                    Placed here by: {occupant.placement_keys.join(", ")}
                  </p>
                ) : null}
                <div className={styles.citationRow}>
                  {occupant.citations.map((citation) => (
                    <CitationChip
                      key={citation.fact_id}
                      label={citation.label}
                      onOpen={() => openEvidence(citation.fact_id, citation.label)}
                    />
                  ))}
                </div>
                {canGovern && onPolicyIntent ? (
                  <div className={styles.decisionControls}>
                    {occupant.policy_status !== "PREFERRED" ? (
                      <button
                        type="button"
                        className={styles.panelAction}
                        onClick={() =>
                          onPolicyIntent({
                            kind: "PROMOTE_FROM_ACTUAL",
                            cell_key: cell.cell_key,
                            technology_id: occupant.technology.id,
                            technology_name: occupant.technology.name,
                          })
                        }
                      >
                        Make this the standard
                      </button>
                    ) : null}
                    <label className={styles.decisionSelectLabel}>
                      <span className={styles.visuallyHidden}>
                        Target decision for {occupant.technology.name}
                      </span>
                      <select
                        className={styles.decisionSelect}
                        value={occupant.policy_status}
                        onChange={(event) =>
                          onPolicyIntent({
                            kind: "SET_TECHNOLOGY_DECISION",
                            cell_key: cell.cell_key,
                            technology_id: occupant.technology.id,
                            technology_name: occupant.technology.name,
                            decision: event.target.value as CanvasPolicyDecision | "UNGOVERNED",
                          })
                        }
                      >
                        {(["PREFERRED", "ALLOWED", "DISCOURAGED", "PROHIBITED", "UNGOVERNED"] as const).map(
                          (decision) => (
                            <option key={decision} value={decision}>
                              {POLICY_LABEL[decision]}
                            </option>
                          ),
                        )}
                      </select>
                    </label>
                  </div>
                ) : null}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <section className={styles.panelSection} aria-labelledby="panel-observation">
        <h3 className={styles.panelSectionTitle} id="panel-observation">
          Observation
        </h3>
        <p className={styles.panelLead}>
          <strong>{OBSERVATION_LABEL[observation.status]}</strong> · {observation.subjects_observed} of{" "}
          {observation.subjects_in_scope} subjects · {observation.subjects_fresh} fresh
        </p>
        <dl className={styles.panelFacts}>
          <div>
            <dt>Required sensors</dt>
            <dd>{observation.required_sensor_kinds.join(", ") || "—"}</dd>
          </div>
          <div>
            <dt>Supported sensors</dt>
            <dd>{observation.supported_sensor_kinds.join(", ") || "none"}</dd>
          </div>
        </dl>
        {observation.missing_inputs.length ? (
          <ul className={styles.missingList}>
            {observation.missing_inputs.map((input) => (
              <li key={input}>{input}</li>
            ))}
          </ul>
        ) : null}
        <p className={styles.panelFingerprint}>
          {observation.rule_key} · {observation.method_version}
        </p>
      </section>

      <section className={styles.panelSection} aria-labelledby="panel-measures">
        <h3 className={styles.panelSectionTitle} id="panel-measures">
          Measures
        </h3>
        {measures ? (
          <>
            <p className={styles.panelLead}>
              <PostureMeter measures={measures} />
            </p>
            <ul className={styles.measureList}>
              {(["coverage", "standardisation", "currency", "risk", "conformance"] as const).map((key) => {
                const result: MeasureResultModel = measures.components[key];
                return (
                  <li key={key} className={styles.measureRow}>
                    <span className={styles.measureName}>{MEASURE_LABEL[key]}</span>
                    <span className={styles.measureValue}>
                      {result.value === null || result.value === undefined
                        ? MEASURE_STATUS_LABEL[result.status]
                        : `${Math.round(result.value * 100)}`}
                    </span>
                    <span className={styles.measureInputs}>{result.inputs.join(", ")}</span>
                  </li>
                );
              })}
            </ul>
            {measures.missing_inputs.length ? (
              <>
                <p className={styles.panelBody}>Not enough evidence for:</p>
                <ul className={styles.missingList}>
                  {measures.missing_inputs.map((input) => (
                    <li key={input}>{input}</li>
                  ))}
                </ul>
              </>
            ) : null}
            <p className={styles.panelFingerprint}>{measures.method_version}</p>
          </>
        ) : (
          <p className={styles.panelBody}>
            No measures are produced for a cell in this state. Measurement requires an applicable
            expectation and a completed observation.
          </p>
        )}
      </section>

      <section className={styles.panelSection} aria-labelledby="panel-policy">
        <h3 className={styles.panelSectionTitle} id="panel-policy">
          Target policy
        </h3>
        {cell.policy?.governed ? (
          <>
            <ul className={styles.decisionList}>
              {cell.policy.decisions.map((decision) => (
                <li key={`${decision.technology.id}:${decision.decision}`}>
                  <span className={decision.resolved ? styles.decisionName : styles.decisionUnresolved}>
                    {decision.technology.name}
                  </span>
                  <span className={styles.decisionState}>{POLICY_LABEL[decision.decision]}</span>
                </li>
              ))}
            </ul>
            {cell.policy.rationale ? <p className={styles.panelBody}>{cell.policy.rationale}</p> : null}
            {cell.policy.owner ? <p className={styles.panelMeta}>Owner: {cell.policy.owner}</p> : null}
            {cell.policy.exceptions.length ? (
              <>
                <h4 className={styles.panelSubTitle}>Exceptions</h4>
                <ul className={styles.exceptionList}>
                  {cell.policy.exceptions.map((exception) => (
                    <li key={exception.key}>
                      <span className={styles.exceptionText}>
                        {exception.rationale}
                        {exception.effective_to ? ` (until ${exception.effective_to.slice(0, 10)})` : ""}
                        {exception.subject_ids.length
                          ? ` · ${exception.subject_ids.length} scoped subject${exception.subject_ids.length === 1 ? "" : "s"}`
                          : " · estate-wide"}
                      </span>
                      {canGovern && onRemoveException ? (
                        <button
                          type="button"
                          className={styles.exceptionRemove}
                          onClick={() => onRemoveException(cell.cell_key, exception.key)}
                        >
                          Remove
                          <span className={styles.visuallyHidden}> exception: {exception.rationale}</span>
                        </button>
                      ) : null}
                    </li>
                  ))}
                </ul>
              </>
            ) : null}
            {cell.policy.unresolved_decision_count ? (
              <p className={styles.panelMeta}>
                {cell.policy.unresolved_decision_count} governed technolog
                {cell.policy.unresolved_decision_count === 1 ? "y is" : "ies are"} not present in this
                projection, so only an identifier is available
                {cell.policy.unresolved_decision_count === 1 ? " for it." : " for them."}
              </p>
            ) : null}
          </>
        ) : (
          <p className={styles.panelBody}>
            No target decision has been recorded for this concern. An ungoverned cell is never
            reported as non-conformant.
          </p>
        )}
        {canGovern && onPolicyIntent ? (
          <button
            type="button"
            className={styles.panelAction}
            onClick={() => onPolicyIntent({ kind: "EDIT_POLICY_DETAILS", cell_key: cell.cell_key })}
          >
            {cell.policy?.governed ? "Edit target policy" : "Set a target policy"}
          </button>
        ) : null}
      </section>

      {cell.citations.length ? (
        <section className={styles.panelSection} aria-labelledby="panel-citations">
          <h3 className={styles.panelSectionTitle} id="panel-citations">
            Evidence
          </h3>
          <div className={styles.citationRow}>
            {cell.citations.map((citation) => (
              <CitationChip
                key={citation.fact_id}
                label={citation.label}
                onOpen={() => openEvidence(citation.fact_id, citation.label)}
              />
            ))}
          </div>
        </section>
      ) : null}
    </aside>
  );
}
