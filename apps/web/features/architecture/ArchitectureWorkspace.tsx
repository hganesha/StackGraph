"use client";

import { useCallback, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { ArchitectureCanvas, type CanvasEmphasis, type CanvasMode } from "@stackgraph/canvas-ui";
import { Skeleton } from "@stackgraph/design-system";
import type { CanvasComparisonRequest, CanvasScope } from "@stackgraph/shared";
import {
  DEFAULT_REFERENCE_MODEL_KEY,
  DEFAULT_TEMPLATE_KEY,
  useArchitectureProfiles,
  useCanvasComparison,
  useCanvasProjection,
  useCanvasReferenceModel,
  useCanvasTargetProjection,
  useCanvasTemplate,
  useProfileDetail,
} from "@/lib/canvasQueries";
import { useEstateDomainSummary } from "@/lib/queries";
import { useCan } from "@/lib/session";
import { CanvasControls, type CanvasView } from "./CanvasControls";
import { CanvasDetailPanel } from "./CanvasDetailPanel";
import { PolicyIntentDialog, type PolicySubmission } from "./PolicyIntentDialog";
import { useCanvasPolicy } from "./useCanvasPolicy";
import styles from "./architecture.module.css";

export interface ArchitectureWorkspaceProps {
  scope: CanvasScope;
  subjectId?: string;
  /** Surfaces embedded in a tab hide the view switch and run read-only. */
  variant?: "workspace" | "embedded";
  initialEmphasis?: CanvasEmphasis;
  initialDensity?: "comfortable" | "compact";
}

export function ArchitectureWorkspace({
  scope,
  subjectId,
  variant = "workspace",
  initialEmphasis = "posture",
  initialDensity = "comfortable",
}: ArchitectureWorkspaceProps) {
  const router = useRouter();
  const canReview = useCan("review");
  const canGovern = useCan("admin");

  const [view, setView] = useState<CanvasView>("actual");
  const [emphasis, setEmphasis] = useState<CanvasEmphasis>(initialEmphasis);
  const [density, setDensity] = useState<"comfortable" | "compact">(initialDensity);
  const [mode, setMode] = useState<CanvasMode>("read");
  const [selectedCellKey, setSelectedCellKey] = useState<string | null>(null);
  const [activeAspectKey, setActiveAspectKey] = useState<string | null>(null);
  // Application-to-application comparison: the same frame twice, so a difference is a
  // real difference and not a relayout.
  const [baselineSubjectId, setBaselineSubjectId] = useState<string | null>(null);

  const referenceModel = useCanvasReferenceModel();
  const template = useCanvasTemplate();

  const showingTarget = view === "target";
  const actualProjection = useCanvasProjection(
    { scope, subjectId, referenceModelKey: DEFAULT_REFERENCE_MODEL_KEY, templateKey: DEFAULT_TEMPLATE_KEY },
    { enabled: !showingTarget },
  );

  const comparisonRequest: CanvasComparisonRequest | null = useMemo(() => {
    const version = referenceModel.data?.version ?? "1.0.0";
    if (view === "compare" && baselineSubjectId) {
      return {
        comparison_kind: "ACTUAL_TO_ACTUAL",
        reference_model_key: DEFAULT_REFERENCE_MODEL_KEY,
        reference_model_version: version,
        actual: { scope, subject_id: subjectId },
        baseline: { scope: "APPLICATION", subject_id: baselineSubjectId },
      };
    }
    if (view !== "drift" || !canReview) return null;
    return {
      comparison_kind: "ACTUAL_TO_TARGET",
      reference_model_key: DEFAULT_REFERENCE_MODEL_KEY,
      reference_model_version: version,
      actual: { scope, subject_id: subjectId },
      baseline: { scope: "TARGET" },
    };
  }, [baselineSubjectId, canReview, referenceModel.data?.version, scope, subjectId, view]);
  const comparison = useCanvasComparison(comparisonRequest);

  // Comparison peers are only meaningful when the canvas is already scoped to one
  // application, so the estate list is fetched lazily rather than on every surface.
  const applications = useEstateDomainSummary(["ENTERPRISE"], {
    enabled: scope === "APPLICATION" && Boolean(subjectId),
  });
  const comparableApplications = useMemo(
    () =>
      (applications.data?.ranked_items ?? [])
        .filter((item) => item.kind === "Application" && item.id !== subjectId)
        .map((item) => ({ id: item.id, name: item.name })),
    [applications.data, subjectId],
  );

  const profiles = useArchitectureProfiles({ enabled: canGovern });
  // Governance edits target a DRAFT revision, never the one in force: PUT
  // /admin/architecture-profiles/{id} updates a draft (spec §10.2), and editing the
  // active standard in place would skip the publish step that makes a change
  // deliberate. With no draft open, govern mode is read-only and says why.
  const draftProfile = useMemo(
    () =>
      [...(profiles.data?.profiles ?? [])]
        .filter((entry) => entry.status === "DRAFT")
        .sort((a, b) => b.version - a.version)[0] ?? null,
    [profiles.data],
  );
  const draftDetail = useProfileDetail(draftProfile?.id ?? null);
  const policy = useCanvasPolicy(draftProfile ?? null, draftDetail);
  const canWritePolicy = canGovern && policy.writable;
  const governing = showingTarget && mode === "govern" && canWritePolicy;

  // The target projection always resolves the revision in force: the published route
  // takes no profile selector, so a draft cannot be previewed through it. Govern mode
  // therefore says plainly that it is editing a draft whose effect is not yet visible
  // here, rather than implying the target has already moved.
  const targetProjection = useCanvasTargetProjection({ enabled: showingTarget && canReview });
  const projection = showingTarget ? targetProjection : actualProjection;

  const selectedDefinition = useMemo(
    () => referenceModel.data?.cells.find((cell) => cell.key === selectedCellKey) ?? null,
    [referenceModel.data, selectedCellKey],
  );
  const selectedCell = useMemo(
    () => projection.data?.cells.find((cell) => cell.cell_key === selectedCellKey) ?? null,
    [projection.data, selectedCellKey],
  );
  const selectedComparison = useMemo(
    () => comparison.data?.cells.find((cell) => cell.cell_key === selectedCellKey) ?? null,
    [comparison.data, selectedCellKey],
  );
  const promptCellKey =
    policy.prompt && "cell_key" in policy.prompt.intent ? policy.prompt.intent.cell_key : null;
  const promptCell = useMemo(
    () => projection.data?.cells.find((cell) => cell.cell_key === promptCellKey) ?? null,
    [projection.data, promptCellKey],
  );
  const promptDefinition = useMemo(
    () => referenceModel.data?.cells.find((cell) => cell.key === promptCellKey) ?? null,
    [referenceModel.data, promptCellKey],
  );
  const promptUnresolvedPolicy = useMemo(() => {
    if (policy.prompt?.intent.kind !== "RESOLVE_UNRESOLVED_POLICY") return null;
    const key = policy.prompt.intent.policy_key;
    return (
      projection.data?.classification_tray.byReason.UNRESOLVED_POLICY.find(
        (entry) => entry.entity.id === key,
      ) ?? null
    );
  }, [policy.prompt, projection.data]);

  const removeException = useCallback(
    (cellKey: string, exceptionId: string) => {
      const existing = projection.data?.cells.find((cell) => cell.cell_key === cellKey)?.policy?.exceptions ?? [];
      void policy.applyExceptions(
        cellKey,
        existing
          .filter((exception) => exception.key !== exceptionId)
          .map((exception) => ({
            key: exception.key,
            rationale: exception.rationale,
            subject_ids: exception.subject_ids,
            effective_from: exception.effective_from,
            effective_to: exception.effective_to,
          })),
      );
    },
    [policy, projection.data],
  );

  const submitPolicy = useCallback(
    (submission: PolicySubmission) => {
      const intent = policy.prompt?.intent;
      if (!intent) return;
      switch (intent.kind) {
        case "PROMOTE_FROM_ACTUAL":
          void policy.applyDecision(intent.cell_key, intent.technology_id, "PREFERRED", submission.rationale);
          break;
        case "SET_TECHNOLOGY_DECISION":
          void policy.applyDecision(intent.cell_key, intent.technology_id, intent.decision, submission.rationale);
          break;
        case "SET_EXPECTATION":
          if (submission.expectation) {
            void policy.applyExpectation(intent.cell_key, submission.expectation, submission.rationale);
          }
          break;
        case "EDIT_POLICY_DETAILS":
          if (submission.details) void policy.applyPolicyDetails(intent.cell_key, submission.details);
          break;
        case "RESOLVE_UNRESOLVED_POLICY":
          if (submission.targetCellKey && promptUnresolvedPolicy) {
            void policy.resolveUnresolvedPolicy(
              submission.targetCellKey,
              [promptUnresolvedPolicy.entity.id],
              submission.migrationDecision ?? "ALLOWED",
              submission.rationale,
            );
          }
          break;
      }
    },
    [policy, promptUnresolvedPolicy],
  );

  const onSelectOccupant = useCallback(
    (technologyId: string) => {
      if (technologyId) router.push(`/technologies/${technologyId}`);
    },
    [router],
  );

  const isLoading = referenceModel.isLoading || template.isLoading || projection.isLoading;
  const isError = referenceModel.isError || template.isError || projection.isError;

  // Drift is an emphasis on top of the actual projection; forcing it here means the
  // control and the rendering can never disagree about what the tone is showing.
  const effectiveEmphasis: CanvasEmphasis = view === "drift" ? "conformance" : emphasis;
  // Govern is only reachable from the target view: editing the estate's observed state
  // is meaningless, and editing while looking at drift would hide what changed.
  const canvasMode: CanvasMode =
    view === "target" && mode === "govern"
      ? "govern"
      : view === "drift" || view === "compare"
        ? "compare"
        : "read";

  return (
    <div className={styles.workspace}>
      {variant === "workspace" ? (
        <header className={styles.header}>
          <div>
            <h1 className={styles.title}>Architecture</h1>
            <p className={styles.subtitle}>
              A fixed frame of the concerns a stack must address, filled from evidence. Cells never move,
              so the same picture compares an application, the estate, and the governed target.
            </p>
          </div>
        </header>
      ) : null}

      <CanvasControls
        view={view}
        onViewChange={(next) => {
          setView(next);
          setSelectedCellKey(null);
        }}
        baselineSubjectId={baselineSubjectId}
        onBaselineChange={setBaselineSubjectId}
        subjectId={subjectId}
        comparableApplications={comparableApplications}
        emphasis={effectiveEmphasis}
        onEmphasisChange={setEmphasis}
        density={density}
        onDensityChange={setDensity}
        mode={mode}
        onModeChange={variant === "workspace" ? setMode : undefined}
        canGovern={canGovern}
        canWritePolicy={canWritePolicy}
        draftVersion={draftProfile?.version ?? null}
        canReview={canReview}
        projection={projection.data ?? null}
        summaryVisible={variant === "workspace"}
      />

      {governing && draftProfile ? (
        <p className={styles.draftBanner} role="status">
          Editing draft revision v{draftProfile.version}. The cells below show the revision
          currently in force — the API has no way to preview a draft — so changes will not appear
          here until the draft is published.
        </p>
      ) : null}
      {showingTarget && canGovern && draftProfile && !policy.writable ? (
        <p className={styles.draftBanner} role="status">
          Draft v{draftProfile.version} exists but its contents were not loaded in this session, and
          the API publishes no way to read a single revision back. Create or edit a draft here to
          govern it, so an edit is never written over policies that could not be read.
        </p>
      ) : null}

      {isLoading ? (
        <Skeleton height="480px" />
      ) : isError || !referenceModel.data || !template.data || !projection.data ? (
        <div className={styles.empty} role="status">
          <h2>Canvas unavailable</h2>
          <p>
            {view === "target" && !canReview
              ? "The governed target requires review access."
              : "The reference model, layout, or projection could not be loaded. Graph and hierarchy views remain available."}
          </p>
        </div>
      ) : (
        <div className={styles.canvasRow}>
          <div className={styles.canvasColumn}>
            <ArchitectureCanvas
              template={template.data}
              referenceModel={referenceModel.data}
              projection={projection.data}
              comparison={view === "drift" || view === "compare" ? comparison.data ?? null : null}
              mode={canvasMode}
              density={density}
              emphasis={effectiveEmphasis}
              selectedCellKey={selectedCellKey}
              activeAspectKey={activeAspectKey}
              onSelectCell={setSelectedCellKey}
              onSelectOccupant={onSelectOccupant}
              onSelectAspect={setActiveAspectKey}
              onPolicyIntent={canWritePolicy ? policy.handleIntent : undefined}
            />
          </div>

          {selectedDefinition && selectedCell ? (
            <CanvasDetailPanel
              definition={selectedDefinition}
              cell={selectedCell}
              comparison={selectedComparison}
              canGovern={canWritePolicy}
              onClose={() => setSelectedCellKey(null)}
              onPolicyIntent={canWritePolicy ? policy.handleIntent : undefined}
              onRemoveException={canWritePolicy ? removeException : undefined}
            />
          ) : null}
        </div>
      )}

      {policy.prompt ? (
        <PolicyIntentDialog
          prompt={policy.prompt}
          cell={promptCell}
          definition={promptDefinition}
          cells={referenceModel.data?.cells ?? []}
          unresolvedPolicy={promptUnresolvedPolicy}
          conflict={policy.conflict}
          isSaving={policy.isSaving}
          onDismiss={policy.dismiss}
          onConfirm={submitPolicy}
        />
      ) : null}

    </div>
  );
}
