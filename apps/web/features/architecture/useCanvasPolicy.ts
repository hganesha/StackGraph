"use client";

import { useCallback, useState } from "react";
import type {
  CanvasPolicyDecision,
  CanvasPolicyIntent,
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

const EMPTY_POLICY = (cellKey: string): TenantCellPolicy => ({
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
});

const DECISION_FIELD: Record<CanvasPolicyDecision, keyof Pick<
  TenantCellPolicy,
  "preferred_technology_ids" | "allowed_technology_ids" | "discouraged_technology_ids" | "prohibited_technology_ids"
>> = {
  PREFERRED: "preferred_technology_ids",
  ALLOWED: "allowed_technology_ids",
  DISCOURAGED: "discouraged_technology_ids",
  PROHIBITED: "prohibited_technology_ids",
};

/**
 * Turns a renderer intent into a profile write.
 *
 * The canvas package emits intents and knows nothing about permissions or the API
 * (spec §9.2). This hook is the application-layer half: it decides which intents need
 * a rationale, applies the change to the profile draft, and surfaces the optimistic
 * concurrency conflict rather than silently retrying it.
 */
export function useCanvasPolicy(profile: TenantArchitectureProfile | null) {
  const [prompt, setPrompt] = useState<PolicyPrompt | null>(null);
  const [conflict, setConflict] = useState<string | null>(null);
  const update = useUpdateArchitectureProfile();

  const applyDecision = useCallback(
    async (cellKey: string, technologyId: string, decision: CanvasPolicyDecision | "UNGOVERNED", rationale: string) => {
      if (!profile) return;
      setConflict(null);
      const overrides = [...profile.cell_overrides];
      const index = overrides.findIndex((entry) => entry.cell_key === cellKey);
      const base: TenantCellPolicy = index >= 0 ? { ...overrides[index] } : EMPTY_POLICY(cellKey);

      // A technology holds exactly one decision. Clear it everywhere, then re-add.
      for (const field of Object.values(DECISION_FIELD)) {
        base[field] = base[field].filter((id) => id !== technologyId);
      }
      if (decision !== "UNGOVERNED") {
        base[DECISION_FIELD[decision]] = [...base[DECISION_FIELD[decision]], technologyId];
      }
      base.rationale = rationale || base.rationale;

      if (index >= 0) overrides[index] = base;
      else overrides.push(base);

      try {
        await update.mutateAsync({
          id: profile.id,
          body: { expected_fingerprint: profile.fingerprint, cell_overrides: overrides },
        });
        setPrompt(null);
      } catch (error) {
        if (error instanceof ApiRequestError && error.status === 409) {
          setConflict(
            "This profile changed since it was loaded. Reload the canvas before saving so an earlier decision is not overwritten.",
          );
          return;
        }
        throw error;
      }
    },
    [profile, update],
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
          requiresRationale: intent.decision === "PROHIBITED" || intent.decision === "DISCOURAGED",
        });
        break;
      case "EDIT_POLICY_DETAILS":
        setPrompt({ intent, title: "Edit target policy", requiresRationale: false });
        break;
      case "RESOLVE_UNRESOLVED_POLICY":
        setPrompt({ intent, title: "Assign this policy to a cell", requiresRationale: false });
        break;
      case "SET_EXPECTATION":
        setPrompt({ intent, title: "Change the expectation", requiresRationale: true });
        break;
    }
  }, []);

  return {
    prompt,
    conflict,
    isSaving: update.isPending,
    error: update.error,
    handleIntent,
    dismiss: () => {
      setPrompt(null);
      setConflict(null);
    },
    applyDecision,
  };
}
