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
  useCanvasTemplate,
} from "@/lib/canvasQueries";
import { useCan } from "@/lib/session";
import { CanvasControls, type CanvasView } from "./CanvasControls";
import { CanvasDetailPanel } from "./CanvasDetailPanel";
import { PolicyIntentDialog } from "./PolicyIntentDialog";
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

  const referenceModel = useCanvasReferenceModel();
  const template = useCanvasTemplate();

  const activeScope: CanvasScope = view === "target" ? "TARGET" : scope;
  const projection = useCanvasProjection(
    { scope: activeScope, subjectId, referenceModelKey: DEFAULT_REFERENCE_MODEL_KEY, templateKey: DEFAULT_TEMPLATE_KEY },
    { enabled: view !== "target" || canReview },
  );

  const comparisonRequest: CanvasComparisonRequest | null = useMemo(() => {
    if (view !== "drift" || !canReview) return null;
    return {
      comparison_kind: "ACTUAL_TO_TARGET",
      reference_model_key: DEFAULT_REFERENCE_MODEL_KEY,
      reference_model_version: referenceModel.data?.version ?? "1.0.0",
      actual: { scope, subject_id: subjectId },
      baseline: { scope: "TARGET" },
    };
  }, [canReview, referenceModel.data?.version, scope, subjectId, view]);
  const comparison = useCanvasComparison(comparisonRequest);

  const profiles = useArchitectureProfiles({ enabled: canGovern });
  const activeProfile =
    profiles.data?.profiles.find((entry) => entry.status === "ACTIVE") ?? profiles.data?.profiles[0] ?? null;
  const policy = useCanvasPolicy(activeProfile);

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
        emphasis={effectiveEmphasis}
        onEmphasisChange={setEmphasis}
        density={density}
        onDensityChange={setDensity}
        mode={mode}
        onModeChange={variant === "workspace" ? setMode : undefined}
        canGovern={canGovern}
        canReview={canReview}
        projection={projection.data ?? null}
        summaryVisible={variant === "workspace"}
      />

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
              comparison={view === "drift" ? comparison.data ?? null : null}
              mode={view === "target" && mode === "govern" ? "govern" : view === "drift" ? "compare" : "read"}
              density={density}
              emphasis={effectiveEmphasis}
              selectedCellKey={selectedCellKey}
              activeAspectKey={activeAspectKey}
              onSelectCell={setSelectedCellKey}
              onSelectOccupant={onSelectOccupant}
              onSelectAspect={setActiveAspectKey}
              onPolicyIntent={canGovern ? policy.handleIntent : undefined}
            />
          </div>

          {selectedDefinition && selectedCell ? (
            <CanvasDetailPanel
              definition={selectedDefinition}
              cell={selectedCell}
              comparison={selectedComparison}
              canGovern={canGovern}
              onClose={() => setSelectedCellKey(null)}
              onPolicyIntent={canGovern ? policy.handleIntent : undefined}
            />
          ) : null}
        </div>
      )}

      {policy.prompt ? (
        <PolicyIntentDialog
          prompt={policy.prompt}
          conflict={policy.conflict}
          isSaving={policy.isSaving}
          onDismiss={policy.dismiss}
          onConfirm={(rationale) => {
            const intent = policy.prompt?.intent;
            if (!intent) return;
            if (intent.kind === "PROMOTE_FROM_ACTUAL") {
              void policy.applyDecision(intent.cell_key, intent.technology_id, "PREFERRED", rationale);
            } else if (intent.kind === "SET_TECHNOLOGY_DECISION") {
              void policy.applyDecision(intent.cell_key, intent.technology_id, intent.decision, rationale);
            } else {
              policy.dismiss();
            }
          }}
        />
      ) : null}
    </div>
  );
}
