"use client";

import { useCallback, useState } from "react";
import type {
  ArchitectureProfileDetail,
  ArchitectureProfileSummary,
  CanvasPolicyDecision,
  CanvasPolicyIntent,
  CellExpectationModel,
  TenantCellPolicyModel,
} from "@stackgraph/shared";
import { ApiRequestError } from "@stackgraph/shared";
import { useUpdateArchitectureProfile } from "@/lib/canvasQueries";

export interface PolicyPrompt {
  intent: CanvasPolicyIntent;
  title: string;
  /** Rationale is mandatory for a decision that narrows what teams may ship. */
  requiresRationale: boolean;
}

export const DECISION_FIELD: Record<CanvasPolicyDecision, keyof Pick<
  TenantCellPolicyModel,
  | "preferred_technology_ids"
  | "allowed_technology_ids"
  | "discouraged_technology_ids"
  | "prohibited_technology_ids"
>> = {
  PREFERRED: "preferred_technology_ids",
  ALLOWED: "allowed_technology_ids",
  DISCOURAGED: "discouraged_technology_ids",
  PROHIBITED: "prohibited_technology_ids",
};

const DECISION_FIELDS = Object.values(DECISION_FIELD);

export function emptyCellPolicy(cellKey: string): TenantCellPolicyModel {
  return {
    cell_key: cellKey,
    applicability: "RECOMMENDED",
    minimum_implementations: 1,
    maximum_implementations: null,
    allowed_diversity: null,
    scope_selector: {},
    preferred_technology_ids: [],
    allowed_technology_ids: [],
    discouraged_technology_ids: [],
    prohibited_technology_ids: [],
    rationale: "",
    owner: null,
    effective_from: null,
    effective_to: null,
    exceptions: [],
  };
}

/**
 * Turns a renderer intent into a profile write.
 *
 * Two properties of the published API shape this hook:
 *
 *   * an update is a whole-state PUT, so it must start from an authoritative copy of
 *     the draft. `detail` is that copy. When it is absent the hook reports itself as
 *     unwritable rather than PUTting a state assembled from guesses, which would drop
 *     every policy this session had not seen.
 *   * concurrency is guarded by version, not fingerprint, and a successful write
 *     increments it. The conflict is surfaced rather than retried: a retry here would
 *     overwrite somebody else's governance decision.
 */
export function useCanvasPolicy(
  summary: ArchitectureProfileSummary | null,
  detail: ArchitectureProfileDetail | null,
) {
  const [prompt, setPrompt] = useState<PolicyPrompt | null>(null);
  const [conflict, setConflict] = useState<string | null>(null);
  const update = useUpdateArchitectureProfile();

  const writable = Boolean(summary && detail && detail.id === summary.id);

  const writeCell = useCallback(
    async (cellKey: string, mutate: (policy: TenantCellPolicyModel) => TenantCellPolicyModel) => {
      if (!summary || !detail) return;
      setConflict(null);
      const policies = [...(detail.state.cell_policies ?? [])];
      const index = policies.findIndex((entry) => entry.cell_key === cellKey);
      const base = index >= 0 ? { ...policies[index] } : emptyCellPolicy(cellKey);
      const next = mutate(base);
      if (index >= 0) policies[index] = next;
      else policies.push(next);

      try {
        await update.mutateAsync({
          id: summary.id,
          // The cached detail is the version this edit was composed against.
          expectedVersion: detail.version,
          state: {
            name: detail.state.name,
            reference_model_key: detail.reference_model_key,
            reference_model_version: detail.reference_model_version,
            cell_policies: policies,
            extension_cells: detail.state.extension_cells ?? [],
          },
        });
        setPrompt(null);
      } catch (error) {
        if (error instanceof ApiRequestError && error.status === 409) {
          setConflict(
            "This profile changed since it was loaded. Reload the canvas before saving, so an earlier decision is not overwritten.",
          );
          return;
        }
        throw error;
      }
    },
    [detail, summary, update],
  );

  /** A technology holds exactly one decision: clear it everywhere, then re-add. */
  const applyDecision = useCallback(
    (cellKey: string, technologyId: string, decision: CanvasPolicyDecision | "UNGOVERNED", rationale: string) =>
      writeCell(cellKey, (policy) => {
        const next = { ...policy };
        for (const field of DECISION_FIELDS) {
          next[field] = (next[field] ?? []).filter((id) => id !== technologyId);
        }
        if (decision !== "UNGOVERNED") {
          next[DECISION_FIELD[decision]] = [...(next[DECISION_FIELD[decision]] ?? []), technologyId];
        }
        next.rationale = rationale || next.rationale;
        return next;
      }),
    [writeCell],
  );

  const applyExpectation = useCallback(
    (cellKey: string, expectation: CellExpectationModel, rationale: string) =>
      writeCell(cellKey, (policy) => ({ ...policy, ...expectation, rationale: rationale || policy.rationale })),
    [writeCell],
  );

  const applyPolicyDetails = useCallback(
    (
      cellKey: string,
      details: { rationale: string; owner: string | null; effective_from: string | null; effective_to: string | null },
    ) => writeCell(cellKey, (policy) => ({ ...policy, ...details })),
    [writeCell],
  );

  const applyExceptions = useCallback(
    (cellKey: string, exceptions: TenantCellPolicyModel["exceptions"]) =>
      writeCell(cellKey, (policy) => ({ ...policy, exceptions })),
    [writeCell],
  );

  /**
   * Moves an unresolved policy's decisions onto a canonical cell. Migration never
   * invents REQUIRED or PREFERRED, so applicability is untouched and only the
   * decisions move (spec §7.3).
   */
  const resolveUnresolvedPolicy = useCallback(
    (cellKey: string, technologyIds: string[], decision: CanvasPolicyDecision, rationale: string) =>
      writeCell(cellKey, (policy) => {
        const next = { ...policy };
        for (const id of technologyIds) {
          for (const field of DECISION_FIELDS) {
            next[field] = (next[field] ?? []).filter((entry) => entry !== id);
          }
          next[DECISION_FIELD[decision]] = [...(next[DECISION_FIELD[decision]] ?? []), id];
        }
        next.rationale = rationale || next.rationale;
        return next;
      }),
    [writeCell],
  );

  const handleIntent = useCallback((intent: CanvasPolicyIntent) => {
    switch (intent.kind) {
      case "PROMOTE_FROM_ACTUAL":
        setPrompt({ intent, title: `Make ${intent.technology_name} the standard`, requiresRationale: true });
        break;
      case "SET_TECHNOLOGY_DECISION":
        setPrompt({
          intent,
          title: `Set ${intent.technology_name} to ${intent.decision.toLowerCase()}`,
          requiresRationale: intent.decision === "PROHIBITED" || intent.decision === "DISCOURAGED",
        });
        break;
      case "SET_EXPECTATION":
        setPrompt({ intent, title: "Change the expectation", requiresRationale: true });
        break;
      case "EDIT_POLICY_DETAILS":
        setPrompt({ intent, title: "Target policy details", requiresRationale: false });
        break;
      case "RESOLVE_UNRESOLVED_POLICY":
        setPrompt({ intent, title: "Assign this policy to a cell", requiresRationale: true });
        break;
    }
  }, []);

  return {
    prompt,
    conflict,
    writable,
    isSaving: update.isPending,
    error: update.error,
    handleIntent,
    dismiss: () => {
      setPrompt(null);
      setConflict(null);
    },
    applyDecision,
    applyExpectation,
    applyPolicyDetails,
    applyExceptions,
    resolveUnresolvedPolicy,
  };
}
