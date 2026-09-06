"use client";

import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { useRouter } from "next/navigation";
import { IconArrowRight, IconCheck, IconPlayerPlay, IconSearch, IconX } from "@tabler/icons-react";
import {
  GateNotice,
  ResolutionLabel,
  Skeleton,
  type GateVerdict,
  formatScopeCount,
  type EstateLevel,
} from "@stackgraph/design-system";
import {
  config,
  type ActionPredicate,
  type ActionSubject,
  type MutationCompileResult,
} from "@stackgraph/shared";
import {
  createIdempotencyKey,
  useActionSubjects,
  useActionTypes,
  useChangeScopes,
  useCompileMutation,
  useCreateSimulation,
  useValidTargets,
} from "@/lib/changeQueries";
import { useEvidenceStore } from "@/lib/evidenceStore";
import { VersionSpreadComb } from "./VersionSpreadComb";
import styles from "./ChangeCommandPalette.module.css";

type LocalState = "EMPTY" | "RESOLVING" | "TOKENISED" | "COMPILED";

/** Sentence case, never a lower-cased enum. */
const TARGET_RECOMMENDATION: Record<string, string> = {
  CONSOLIDATE: "Consolidate the estate",
  CANDIDATE: "Candidate upgrade",
  LATEST_KNOWN: "Latest collected",
};

export function ChangeCommandPalette({ open, onClose }: { open: boolean; onClose: () => void }) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const router = useRouter();
  const openEvidence = useEvidenceStore((state) => state.open);
  const [predicate, setPredicate] = useState<ActionPredicate | null>(null);
  const [subjectQuery, setSubjectQuery] = useState("");
  const [subject, setSubject] = useState<ActionSubject | null>(null);
  const [targetVersion, setTargetVersion] = useState<string | null>(null);
  const [scopeId, setScopeId] = useState<string | null>(null);
  const [compileResult, setCompileResult] = useState<MutationCompileResult | null>(null);
  const [announcement, setAnnouncement] = useState("");
  const compile = useCompileMutation();
  const createSimulation = useCreateSimulation();
  const actions = useActionTypes(open && config.phase2ChangesEnabled);
  const subjects = useActionSubjects(predicate, subjectQuery, open && !subject);
  const targets = useValidTargets(subject?.entity.id ?? null, open && Boolean(subject));
  const scopes = useChangeScopes(subject?.entity.id ?? null, open && Boolean(subject));

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (open && !dialog.open) {
      dialog.showModal();
      requestAnimationFrame(() => inputRef.current?.focus());
    } else if (!open && dialog.open) {
      dialog.close();
    }
  }, [open]);

  useEffect(() => {
    if (!open) return;
    setAnnouncement("Change command opened. Choose an action or type a bounded change command.");
  }, [open]);

  const localState: LocalState = compileResult?.command_state
    ?? (subject ? "TOKENISED" : predicate ? "RESOLVING" : "EMPTY");
  const selectedScope = scopes.data?.scopes.find((item) => item.id === scopeId) ?? null;
  const validationFields = useMemo(
    () => new Set(compileResult?.draft.validation_errors?.map((item) => item.field) ?? []),
    [compileResult],
  );

  const reset = () => {
    setPredicate(null);
    setSubjectQuery("");
    setSubject(null);
    setTargetVersion(null);
    setScopeId(null);
    setCompileResult(null);
    compile.reset();
    createSimulation.reset();
    requestAnimationFrame(() => inputRef.current?.focus());
  };

  const chooseAction = (next: ActionPredicate) => {
    setPredicate(next);
    setCompileResult(null);
    setAnnouncement(`${next.toLowerCase()} selected. Search for an estate entity.`);
    requestAnimationFrame(() => inputRef.current?.focus());
  };

  const chooseSubject = (next: ActionSubject) => {
    setSubject(next);
    setSubjectQuery("");
    setCompileResult(null);
    setTargetVersion(null);
    setScopeId(null);
    setAnnouncement(`${next.entity.name} resolved to ${next.entity.canonical_key ?? next.entity.id}. Choose a target and scope.`);
  };

  const compileStructured = async () => {
    if (!predicate || !subject || !targetVersion || !scopeId) return;
    const result = await compile.mutateAsync({
      idempotency_key: createIdempotencyKey("command"),
      predicate,
      subject_id: subject.entity.id,
      target_version: targetVersion,
      scope_id: scopeId,
    });
    setCompileResult(result);
    setAnnouncement(result.command_state === "COMPILED"
      ? "Mutation compiled and validated. It is ready to simulate."
      : `Compilation blocked. ${result.gate.reasons?.map((reason) => reason.message).join(" ")}`);
  };

  const compileIntent = async () => {
    const intent = subjectQuery.trim();
    if (!intent) return;
    const result = await compile.mutateAsync({ idempotency_key: createIdempotencyKey("intent"), intent });
    setCompileResult(result);
    if (result.draft.subject.entity) {
      setPredicate(result.draft.predicate);
      setSubject({ entity: result.draft.subject.entity, resolution: "RESOLVED" });
      setTargetVersion(typeof result.draft.after.version === "string" ? result.draft.after.version : null);
      setScopeId(result.draft.scope?.id ?? null);
    }
    setAnnouncement(result.command_state === "COMPILED"
      ? "The sentence resolved into canonical mutation tokens."
      : `Command could not compile. ${result.gate.reasons?.map((reason) => reason.message).join(" ")}`);
  };

  const onInputKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key !== "Enter" || compile.isPending) return;
    if (!predicate || /\s+to\s+/i.test(subjectQuery)) {
      event.preventDefault();
      void compileIntent();
    }
  };

  const simulate = async () => {
    const changeSetId = compileResult?.change_set?.id;
    if (!changeSetId) return;
    const run = await createSimulation.mutateAsync({
      changeSetId,
      idempotencyKey: createIdempotencyKey("simulation"),
    });
    setAnnouncement(run.replayed ? "Existing simulation opened." : "Simulation queued.");
    onClose();
    router.push(`/simulations/${run.id}`);
  };

  const inferredCandidates = compileResult?.draft.subject.candidates ?? [];
  const gate = compileResult?.gate;

  return (
    <dialog
      ref={dialogRef}
      className={styles.dialog}
      aria-labelledby="change-command-title"
      aria-describedby="change-command-description"
      onCancel={(event) => { event.preventDefault(); onClose(); }}
      onClick={(event) => { if (event.target === dialogRef.current) onClose(); }}
    >
      <div className={styles.panel}>
        <header className={styles.header}>
          <div>
            <span className={styles.eyebrow}>Change compiler · {localState.toLowerCase()}</span>
            <h2 id="change-command-title">Plan an estate-backed change</h2>
            <p id="change-command-description">Compile an exact change before anything is simulated.</p>
          </div>
          <button type="button" className={styles.close} onClick={onClose} aria-label="Close change command">
            <IconX size={18} stroke={1.5} />
          </button>
        </header>

        {!config.phase2ChangesEnabled ? (
          <div className={styles.disabled} role="status">
            Change simulation is not enabled for this tenant yet. Existing estate views remain available.
          </div>
        ) : (
          <>
            <div className={styles.commandLine}>
              {predicate ? <button type="button" className={styles.token} onClick={reset}>{predicate.toLowerCase()}</button> : null}
              {subject ? (
                <span className={styles.subjectToken}>
                  <ResolutionLabel
                    state="RESOLVED"
                    label={subject.entity.name}
                    canonicalId={subject.entity.canonical_key ?? subject.entity.id}
                  />
                </span>
              ) : (
                <label className={styles.inputWrap}>
                  <IconSearch size={17} stroke={1.5} aria-hidden="true" />
                  <span className={styles.srOnly}>{predicate ? "Search estate subjects" : "Type a bounded change command"}</span>
                  <input
                    ref={inputRef}
                    value={subjectQuery}
                    onChange={(event) => { setSubjectQuery(event.target.value); setCompileResult(null); }}
                    onKeyDown={onInputKeyDown}
                    placeholder={predicate ? "Search packages in your estate…" : "Try “upgrade Newtonsoft.Json to 14.0.1 in estate”"}
                    autoComplete="off"
                  />
                </label>
              )}
              {targetVersion ? <span className={styles.token}>→ {targetVersion}</span> : null}
              {selectedScope ? <span className={styles.token}>{selectedScope.label}</span> : null}
            </div>

            {compile.isError || createSimulation.isError ? (
              <p className={styles.requestError} role="alert">
                {compile.error?.message ?? createSimulation.error?.message ?? "The change service could not complete the request."}
              </p>
            ) : null}

            {localState === "EMPTY" && !compileResult ? (
              <section className={styles.section} aria-labelledby="action-heading">
                <div className={styles.sectionHeading}>
                  <h3 id="action-heading">Choose a bounded action</h3>
                  <span>{actions.data?.policy_version}</span>
                </div>
                {actions.isLoading ? (
                  <div className={styles.skeletons}><Skeleton height={52} /><Skeleton height={52} /></div>
                ) : actions.isError ? (
                  <p className={styles.empty}>Actions are temporarily unavailable. No candidate has been inferred.</p>
                ) : (
                  <div className={styles.actionGrid}>
                    {actions.data?.action_types.map((action) => (
                      <button
                        key={action.predicate}
                        type="button"
                        disabled={!action.enabled}
                        className={styles.action}
                        onClick={() => chooseAction(action.predicate)}
                      >
                        <strong>{action.label}</strong>
                        <span>{action.subject_types.join(" · ")}</span>
                        <IconArrowRight size={16} stroke={1.5} aria-hidden="true" />
                      </button>
                    ))}
                  </div>
                )}
              </section>
            ) : null}

            {localState === "RESOLVING" && !subject && !compileResult ? (
              <section className={`${styles.section} ${validationFields.has("subject") ? styles.fieldError : ""}`} aria-labelledby="subject-heading">
                <div className={styles.sectionHeading}>
                  <h3 id="subject-heading">Resolve one canonical subject</h3>
                  <span>{subjects.data?.subjects.length ?? 0} matches</span>
                </div>
                {subjects.isFetching ? (
                  <div className={styles.skeletons}><Skeleton height={58} /><Skeleton height={58} /></div>
                ) : subjects.isError ? (
                  <p className={styles.empty}>Subject search failed. StackGraph will not invent a replacement.</p>
                ) : subjects.data?.subjects.length ? (
                  <ul className={styles.subjects}>
                    {subjects.data.subjects.map((item) => (
                      <li key={item.entity.id}>
                        <button type="button" onClick={() => chooseSubject(item)}>
                          <span>
                            <strong>{item.entity.name}</strong>
                            <code>{item.entity.canonical_key}</code>
                          </span>
                          <span className={styles.subjectMeta}>{item.dependent_count ?? 0} dependents · Resolved</span>
                        </button>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className={styles.empty}>{subjectQuery ? `No estate entity matches “${subjectQuery}”.` : "Start typing to narrow the estate-backed list."}</p>
                )}
              </section>
            ) : null}

            {subject && localState !== "COMPILED" ? (
              <div className={styles.tokenised}>
                <section className={`${styles.section} ${validationFields.has("target_version") ? styles.fieldError : ""}`} aria-labelledby="target-heading">
                  <div className={styles.sectionHeading}>
                    <h3 id="target-heading">Choose an exact target</h3>
                    <span>{targets.data?.policy_version}</span>
                  </div>
                  {targets.isLoading ? <Skeleton height={152} /> : targets.isError ? (
                    <p className={styles.empty}>Targets are unavailable. The change cannot proceed with a guessed version.</p>
                  ) : (
                    <div className={styles.targetList} role="radiogroup" aria-label="Exact target version">
                      {targets.data?.targets.map((target) => (
                        <button
                          type="button"
                          role="radio"
                          aria-checked={targetVersion === target.version}
                          key={target.canonical_key}
                          className={`${styles.target} ${targetVersion === target.version ? styles.selected : ""}`}
                          onClick={() => { setTargetVersion(target.version); setCompileResult(null); }}
                        >
                          <span>
                            <strong className="sg-mono">{target.version}</strong>
                            <small>{target.source} · observed {new Date(target.observed_at).toLocaleDateString()}</small>
                            {/* §6: say why a version is worth choosing, not just that it exists. */}
                            {target.recommendation && target.recommendation !== "NONE" ? (
                              <small className={styles.targetReason}>
                                {TARGET_RECOMMENDATION[target.recommendation]}
                                {target.recommendation_detail ? ` · ${target.recommendation_detail}` : ""}
                              </small>
                            ) : null}
                          </span>
                          <span className={styles.axes}>
                            <span data-support={target.support ?? "UNKNOWN"}>{target.support ?? "UNKNOWN"}</span>
                            <span>{target.freshness}</span>
                          </span>
                        </button>
                      ))}
                    </div>
                  )}
                  {/* A short list must not read as a short registry. */}
                  {targets.data?.coverage?.registry_enumeration === "NOT_COLLECTED" ? (
                    <p className={styles.coverageNote} role="note">{targets.data.coverage.detail}</p>
                  ) : null}
                </section>

                <section className={`${styles.section} ${validationFields.has("scope_id") ? styles.fieldError : ""}`} aria-labelledby="scope-heading">
                  <div className={styles.sectionHeading}>
                    <h3 id="scope-heading">Choose the blast-radius promise</h3>
                    <span>{scopes.data?.policy_version}</span>
                  </div>
                  {scopes.isLoading ? <Skeleton height={132} /> : scopes.isError ? (
                    <p className={styles.empty}>Scopes are unavailable. The change cannot proceed without an observed boundary.</p>
                  ) : (
                    <div className={styles.scopeList} role="radiogroup" aria-label="Change scope">
                      {scopes.data?.scopes.map((scope) => (
                        <button
                          type="button"
                          role="radio"
                          aria-checked={scopeId === scope.id}
                          key={scope.id}
                          className={`${styles.scope} ${scopeId === scope.id ? styles.selected : ""}`}
                          onClick={() => { setScopeId(scope.id); setCompileResult(null); }}
                        >
                          <span className={styles.scopeKind}>{scope.kind}</span>
                          <span><strong>{scope.label}</strong>{scope.component_path ? <code>{scope.component_path}</code> : null}</span>
                          <span>{scope.affected_count} affected</span>
                        </button>
                      ))}
                    </div>
                  )}
                </section>

                {selectedScope ? <VersionSpreadComb scope={selectedScope} targets={targets.data?.targets ?? []} /> : null}

                <div className={styles.compileRow}>
                  <p>Suggestions come from your estate. Mutable aliases must resolve before simulation.</p>
                  <button
                    type="button"
                    className={styles.primary}
                    disabled={!targetVersion || !scopeId || compile.isPending}
                    onClick={() => void compileStructured()}
                  >
                    {compile.isPending ? "Compiling…" : "Compile change"}
                    <IconArrowRight size={16} stroke={1.5} aria-hidden="true" />
                  </button>
                </div>
              </div>
            ) : null}

            {compileResult && compileResult.draft.subject.state !== "RESOLVED" ? (
              <section className={styles.resolution} aria-label="Subject resolution">
                <ResolutionLabel
                  state={compileResult.draft.subject.state}
                  label={subjectQuery || "Unresolved subject"}
                  candidateCount={inferredCandidates.length}
                  reason={compileResult.draft.subject.state === "UNRESOLVED" ? gate?.reasons?.[0]?.message : undefined}
                >
                  {inferredCandidates.length ? (
                    <ul className={styles.candidates}>
                      {inferredCandidates.map((candidate) => (
                        <li key={candidate.entity.id}>
                          <button type="button" onClick={() => chooseSubject({ entity: candidate.entity, resolution: "RESOLVED" })}>
                            {candidate.entity.name} <span>{Math.round(candidate.confidence * 100)}%</span>
                          </button>
                        </li>
                      ))}
                    </ul>
                  ) : null}
                </ResolutionLabel>
              </section>
            ) : null}

            {gate ? (
              <GateNotice
                id="change-command-gate"
                verdict={gate.state as GateVerdict}
                reason={gate.reasons?.length ? (
                  <span className={styles.gateReasons}>
                    {gate.reasons.map((reason) => (
                      <span key={`${reason.code}-${reason.message}`}>
                        <code>{reason.code}</code> · {reason.message}
                        {reason.evidence_fact_ids?.[0] ? (
                          <button type="button" onClick={() => openEvidence(reason.evidence_fact_ids![0], reason.message)}>View evidence</button>
                        ) : null}
                      </span>
                    ))}
                  </span>
                ) : "No blocking reason was returned."}
              />
            ) : null}

            {compileResult?.command_state === "COMPILED" && compileResult.change_set?.id ? (
              <section className={styles.compiled} aria-labelledby="compiled-heading">
                <div className={styles.compiledIcon} aria-hidden="true"><IconCheck size={19} stroke={1.8} /></div>
                <div>
                  <h3 id="compiled-heading">Mutation ready</h3>
                  <p>
                    {formatScopeCount(
                      (compileResult.draft.scope?.kind ?? "ESTATE") as EstateLevel,
                      compileResult.draft.scope?.affected_count ?? 0,
                    )}{" "}
                    in scope.
                    {compileResult.replayed ? " This existing ChangeSet was reused." : " A validated ChangeSet was created."}
                  </p>
                  <code>{compileResult.change_set.id}</code>
                </div>
                <button type="button" className={styles.primary} disabled={createSimulation.isPending} onClick={() => void simulate()}>
                  <IconPlayerPlay size={16} stroke={1.5} aria-hidden="true" />
                  {createSimulation.isPending ? "Queueing…" : "Simulate"}
                </button>
              </section>
            ) : null}

            <footer className={styles.footer}>
              <span>Estate-backed candidates only</span>
              <button type="button" onClick={reset}>Start over</button>
            </footer>
          </>
        )}
        <p className={styles.srOnly} aria-live="polite">{announcement}</p>
      </div>
    </dialog>
  );
}
