"use client";

import { useCallback, useState } from "react";
import type {
  CanvasPolicyDecision,
  CanvasPolicyIntent,
  CanvasUnresolvedPolicy,
  CellExpectation,
  PolicyException,
  TenantArchitectureProfile,
  TenantCellPolicy,
} from "@stackgraph/shared";
import { ApiRequestError } from "@stackgraph/shared";
import { useUpdateArchitectureProfile } from "@/lib/canvasQueries";

export interface PolicyPrompt {
  intent: CanvasPolicyIntent;
  title: string;
  /** Rationale is mandatory for a decision that changes what teams may ship. */
  requiresRationale: boolean;
}

export const DECISION_FIELD: Record<CanvasPolicyDecision, keyof Pick<
  TenantCellPolicy,
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

export function emptyCellPolicy(cellKey: string): TenantCellPolicy {
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
 * The canvas package emits intents and knows nothing about permissions or the API
 * (spec §9.2). This hook is the application-layer half: it decides which intents need
 * a rationale, applies the change to the active profile, and surfaces the optimistic
 * concurrency conflict rather than silently retrying it — a retry here would overwrite
 * somebody else's governance decision.
 */
export function useCanvasPolicy(profile: TenantArchitectureProfile | null) {
  const [prompt, setPrompt] = useState<PolicyPrompt | null>(null);
  const [conflict, setConflict] = useState<string | null>(null);
  const update = useUpdateArchitectureProfile();

  /** Applies `mutate` to the named cell's override, creating it if it does not exist. */
  const writeCell = useCallback(
    async (cellKey: string, mutate: (policy: TenantCellPolicy) => TenantCellPolicy) => {
      if (!profile) return;
      setConflict(null);
      const overrides = [...profile.cell_overrides];
      const index = overrides.findIndex((entry) => entry.cell_key === cellKey);
      const base = index >= 0 ? { ...overrides[index] } : emptyCellPolicy(cellKey);
      const next = mutate(base);
      if (index >= 0) overrides[index] = next;
      else overrides.push(next);

      try {
        await update.mutateAsync({
          id: profile.id,
          body: { expected_fingerprint: profile.fingerprint, cell_overrides: overrides },
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
    [profile, update],
  );

  /** A technology holds exactly one decision: clear it everywhere, then re-add. */
  const applyDecision = useCallback(
    (cellKey: string, technologyId: string, decision: CanvasPolicyDecision | "UNGOVERNED", rationale: string) =>
      writeCell(cellKey, (policy) => {
        const next = { ...policy };
        for (const field of DECISION_FIELDS) {
          next[field] = next[field].filter((id) => id !== technologyId);
        }
        if (decision !== "UNGOVERNED") {
          next[DECISION_FIELD[decision]] = [...next[DECISION_FIELD[decision]], technologyId];
        }
        next.rationale = rationale || next.rationale;
        return next;
      }),
    [writeCell],
  );

  const applyExpectation = useCallback(
    (cellKey: string, expectation: CellExpectation, rationale: string) =>
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
    (cellKey: string, exceptions: PolicyException[]) =>
      writeCell(cellKey, (policy) => ({ ...policy, exceptions })),
    [writeCell],
  );

  /**
   * Moves an unresolved legacy or custom policy onto a canonical cell, preserving each
   * technology's decision. §7.3 is explicit that migration must not invent REQUIRED or
   * PREFERRED, so applicability is left untouched and only the decisions move.
   */
  const resolveUnresolvedPolicy = useCallback(
    (cellKey: string, unresolved: CanvasUnresolvedPolicy, rationale: string) =>
      writeCell(cellKey, (policy) => {
        const next = { ...policy };
        for (const entry of unresolved.technologies) {
          for (const field of DECISION_FIELDS) {
            next[field] = next[field].filter((id) => id !== entry.technology.id);
          }
          next[DECISION_FIELD[entry.decision]] = [
            ...next[DECISION_FIELD[entry.decision]],
            entry.technology.id,
          ];
        }
        next.rationale = rationale || next.rationale;
        return next;
      }),
    [writeCell],
  );

  const handleIntent = useCallback((intent: CanvasPolicyIntent) => {
    switch (intent.kind) {
      case "PROMOTE_FROM_ACTUAL":
        setPrompt({
          intent,
          title: `Make ${intent.technology_name} the standard`,
          requiresRationale: true,
        });
        break;
      case "SET_TECHNOLOGY_DECISION":
        setPrompt({
          intent,
          title: `Set ${intent.technology_name} to ${intent.decision.toLowerCase()}`,
          // Narrowing what teams may ship needs a reason on the record; widening does not.
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
    isSaving: update.isPending,
    error: update.error,
    handleIntent,
    openPrompt: setPrompt,
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
