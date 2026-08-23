"use client";

import Link from "next/link";
import type {
  CanvasCellComparisonView,
  CanvasCellProjectionView,
  CanvasOccupantView,
  CanvasPolicyDecision,
  CanvasPolicyIntent,
  ArchitectureCellView,
  MeasureResultModel,
} from "@stackgraph/shared";
import { CitationChip, ConfidenceChip, Term } from "@stackgraph/design-system";
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
/** Target-decision controls for one resolved version. */
function DecisionControls({
  cellKey,
  occupant,
  onPolicyIntent,
}: {
  cellKey: string;
  occupant: CanvasOccupantView;
  onPolicyIntent: (intent: CanvasPolicyIntent) => void;
}) {
  return (
    <div className={styles.decisionControls}>
      {occupant.policy_status !== "PREFERRED" ? (
        <button
          type="button"
          className={styles.panelAction}
          onClick={() =>
            onPolicyIntent({
              kind: "PROMOTE_FROM_ACTUAL",
              cell_key: cellKey,
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
              cell_key: cellKey,
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
  );
}

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
          What we found
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
          What's expected here
        </h3>
        <dl className={styles.panelFacts}>
          <div>
            <dt>Required?</dt>
            <dd>{APPLICABILITY_LABEL[cell.expectation.applicability]}</dd>
          </div>
          <div>
            <dt>How many</dt>
            <dd>
              {cell.expectation.minimum_implementations ?? "—"} to{" "}
              {cell.expectation.maximum_implementations ?? "unbounded"}
            </dd>
          </div>
          <div>
            <dt>How many different</dt>
            <dd>{cell.expectation.allowed_diversity ?? "unbounded"}</dd>
          </div>
          <div>
            <dt>Set by</dt>
            <dd>{cell.expectation.source === "TENANT_PROFILE" ? "Your standard" : "StackGraph default"}</dd>
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
            Change what's expected
          </button>
        ) : null}
      </section>

      {cell.occupant_groups.length ? (
        <section className={styles.panelSection} aria-labelledby="panel-occupants">
          <h3 className={styles.panelSectionTitle} id="panel-occupants">
            In use ({cell.occupant_groups.length} package
            {cell.occupant_groups.length === 1 ? "" : "s"}
            {cell.occupant_total > cell.occupant_groups.length
              ? `, ${cell.occupant_total} versions`
              : ""}
            )
          </h3>
          <ul className={styles.occupantList}>
            {cell.occupant_groups.map((group) => {
              const multiple = group.members.length > 1;
              const newest = group.members[0];
              return (
                <li key={group.key}>
                  <div className={styles.occupantRow}>
                    <Link href={`/technologies/${newest.technology.id}`} className={styles.occupantName}>
                      {group.label}
                    </Link>
                    <span className={styles.occupantPolicy}>{POLICY_LABEL[group.policy_status]}</span>
                    <ConfidenceChip label={group.confidence_label} value={group.confidence} />
                  </div>
                  <p className={styles.occupantMeta}>
                    {group.classification.replace("_", " ").toLowerCase()} ·{" "}
                    {group.adoption.applications} apps · {group.adoption.repositories} repos ·{" "}
                    {group.adoption.deployments} deployments
                  </p>

                  {multiple ? (
                    <details className={styles.versionDetails}>
                      <summary className={styles.versionSummary}>
                        {group.members.length} resolved versions
                        {group.policy_status === "PROHIBITED" || group.policy_status === "DISCOURAGED"
                          ? " — not all are permitted"
                          : ""}
                      </summary>
                      {/* Per version, because the decision that matters is usually about
                          one of them: an old major is prohibited while the current one
                          is preferred, and a collapsed row cannot say which is which. */}
                      <ul className={styles.versionList}>
                        {group.members.map((member) => (
                          <li key={member.technology.id}>
                            <div className={styles.occupantRow}>
                              <Link
                                href={`/technologies/${member.technology.id}`}
                                className={styles.versionName}
                              >
                                {member.technology.name}
                              </Link>
                              <span className={styles.occupantPolicy}>
                                {POLICY_LABEL[member.policy_status]}
                              </span>
                            </div>
                            <p className={styles.occupantMeta}>
                              {member.adoption.applications} apps · {member.adoption.repositories} repos
                              {member.placement_keys.length
                                ? ` · placed by ${member.placement_keys.join(", ")}`
                                : ""}
                            </p>
                            <div className={styles.citationRow}>
                              {member.citations.map((citation) => (
                                <CitationChip
                                  key={citation.fact_id}
                                  label={citation.label}
                                  onOpen={() => openEvidence(citation.fact_id, citation.label)}
                                />
                              ))}
                            </div>
                            {canGovern && onPolicyIntent ? (
                              <DecisionControls
                                cellKey={cell.cell_key}
                                occupant={member}
                                onPolicyIntent={onPolicyIntent}
                              />
                            ) : null}
                          </li>
                        ))}
                      </ul>
                    </details>
                  ) : (
                    <>
                      {newest.placement_keys.length ? (
                        <p className={styles.occupantMeta}>
                          <Term id="placement">Placed here</Term> by: {newest.placement_keys.join(", ")}
                        </p>
                      ) : null}
                      <div className={styles.citationRow}>
                        {newest.citations.map((citation) => (
                          <CitationChip
                            key={citation.fact_id}
                            label={citation.label}
                            onOpen={() => openEvidence(citation.fact_id, citation.label)}
                          />
                        ))}
                      </div>
                      {canGovern && onPolicyIntent ? (
                        <DecisionControls
                          cellKey={cell.cell_key}
                          occupant={newest}
                          onPolicyIntent={onPolicyIntent}
                        />
                      ) : null}
                    </>
                  )}
                </li>
              );
            })}
          </ul>
        </section>
      ) : null}

      <section className={styles.panelSection} aria-labelledby="panel-observation">
        <h3 className={styles.panelSectionTitle} id="panel-observation">
          What we checked
        </h3>
        <p className={styles.panelMeta}>
          Based on <Term id="evidence">evidence</Term> from your connected repositories.
        </p>
        <p className={styles.panelLead}>
          <strong>{OBSERVATION_LABEL[observation.status]}</strong> · {observation.subjects_observed} of{" "}
          {observation.subjects_in_scope} subjects · {observation.subjects_fresh} fresh
        </p>
        <dl className={styles.panelFacts}>
          <div>
            <dt>Needs</dt>
            <dd>{observation.required_sensor_kinds.join(", ") || "—"}</dd>
          </div>
          <div>
            <dt>Available</dt>
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
          Scores
        </h3>
        <p className={styles.panelMeta}>
          How this area&apos;s <Term id="posture">health</Term> is worked out.
        </p>
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
                <p className={styles.panelBody}>Not scored because we're missing:</p>
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
            Not scored yet — we need a completed scan and an applicable expectation first.
          </p>
        )}
      </section>

      <section className={styles.panelSection} aria-labelledby="panel-policy">
        <h3 className={styles.panelSectionTitle} id="panel-policy">
          Your standard
        </h3>
        <p className={styles.panelMeta}>
          From your <Term id="profile">architecture profile</Term>.
        </p>
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
                        {` · ${exception.subject_ids.length} scoped subject${exception.subject_ids.length === 1 ? "" : "s"}`}
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
            No standard set for this area yet. That is never counted against you.
          </p>
        )}
        {canGovern && onPolicyIntent ? (
          <button
            type="button"
            className={styles.panelAction}
            onClick={() => onPolicyIntent({ kind: "EDIT_POLICY_DETAILS", cell_key: cell.cell_key })}
          >
            {cell.policy?.governed ? "Edit your standard" : "Set a standard"}
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
