import { useMutation } from "@tanstack/react-query";
import { stackGraphClient, ApiRequestError } from "@stackgraph/shared";

export type ReviewDecision = "CONFIRM" | "REJECT";

/**
 * Review an uncertain identity bridge (plan §5.2, §8.3). Sends expected_version for
 * optimistic concurrency; a 409 means someone else reviewed it first — surface, never overwrite.
 */
export function useReviewMutation(assertionId: string) {
  return useMutation({
    mutationFn: (input: { decision: ReviewDecision; rationale: string; expectedVersion: number }) =>
      stackGraphClient.reviewIdentityAssertion(assertionId, {
        decision: input.decision,
        rationale: input.rationale,
        expected_version: input.expectedVersion,
      }),
  });
}

export function isConflict(error: unknown): boolean {
  return error instanceof ApiRequestError && error.status === 409;
}
