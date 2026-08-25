import { useMutation, useQueryClient } from "@tanstack/react-query";
import { stackGraphClient, ApiRequestError, type OptimisticReviewRequest } from "@stackgraph/shared";

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

/**
 * Semantic retrieval is fail-closed by contract: with no evaluated embedding space
 * active, the API returns 503 rather than answering from a degraded one. That is a
 * state to explain, not an error to report — the surface degrades, the search does not
 * break.
 */
export function isUnavailable(error: unknown): boolean {
  return error instanceof ApiRequestError && error.status === 503;
}

/**
 * Why a similarity decision was made, offered as codes rather than free text so the
 * decisions stay analyzable. `application_similarity_feedback` records the code, the
 * rationale, the actor, and the candidate's method version and score at decision time.
 *
 * NOTE: the API accepts any reason_code string up to 100 characters, so this vocabulary
 * currently lives only in the client. It belongs in the contract as an enum, so a second
 * client cannot invent a parallel set — flagged as a contract follow-up.
 */
export type SimilarityDecision =
  | "CONFIRMED_SIMILAR"
  | "CONFIRMED_DISTINCT"
  | "CONSOLIDATION_CANDIDATE"
  | "DISMISSED";

export const SIMILARITY_DECISIONS: ReadonlyArray<{
  decision: SimilarityDecision;
  label: string;
  /** What the reviewer is asserting, in the words they would use. */
  prompt: string;
  reasonCodes: ReadonlyArray<{ code: string; label: string }>;
}> = [
  {
    decision: "CONFIRMED_SIMILAR",
    label: "Same purpose",
    prompt: "Why do these serve the same purpose?",
    reasonCodes: [
      { code: "SAME_CAPABILITY", label: "They implement the same capability" },
      { code: "DUPLICATE_IMPLEMENTATION", label: "One duplicates the other's implementation" },
      { code: "SHARED_OWNERSHIP", label: "Same team, same system, split by history" },
    ],
  },
  {
    decision: "CONFIRMED_DISTINCT",
    label: "Different things",
    prompt: "Why are these different?",
    reasonCodes: [
      { code: "DIFFERENT_CAPABILITY", label: "They implement different capabilities" },
      { code: "DIFFERENT_DOMAIN", label: "They serve different business domains" },
      { code: "SHARED_STACK_ONLY", label: "Only their technology stack overlaps" },
    ],
  },
  {
    decision: "CONSOLIDATION_CANDIDATE",
    label: "Consider consolidating",
    prompt: "Why is this worth consolidating?",
    reasonCodes: [
      { code: "OVERLAPPING_FUNCTION", label: "Their functions overlap enough to merge" },
      { code: "REDUNDANT_PLATFORM", label: "One could move onto the other's platform" },
      { code: "CONSOLIDATION_PLANNED", label: "A consolidation is already planned" },
    ],
  },
  {
    decision: "DISMISSED",
    label: "Not worth reviewing",
    prompt: "Why dismiss this candidate?",
    reasonCodes: [
      { code: "INSUFFICIENT_EVIDENCE", label: "Not enough evidence to judge either way" },
      { code: "NOT_ACTIONABLE", label: "True, but nothing would be done about it" },
      { code: "ALREADY_TRACKED", label: "Already tracked somewhere else" },
    ],
  },
];

/**
 * The three review-queue finding types that share the identity-bridge shape exactly:
 * a two-way CONFIRM/REJECT decision with a required rationale and optimistic concurrency.
 * Kept as one mutation factory so a fourth type never needs a fourth copy of this wiring.
 */
export type OptimisticReviewKind = "CAPABILITY_INFERENCE" | "DUPLICATE_CAPABILITY" | "MODERNIZATION_CANDIDATE";

const optimisticReviewFns: Record<
  OptimisticReviewKind,
  (id: string, body: OptimisticReviewRequest) => Promise<{ review_state: "CONFIRMED" | "REJECTED"; version: number }>
> = {
  CAPABILITY_INFERENCE: (id, body) => stackGraphClient.reviewCapabilityInference(id, body),
  DUPLICATE_CAPABILITY: (id, body) => stackGraphClient.reviewDuplicateCapabilityCandidate(id, body),
  MODERNIZATION_CANDIDATE: (id, body) => stackGraphClient.reviewModernizationCandidate(id, body),
};

export function useOptimisticReviewMutation(kind: OptimisticReviewKind, itemId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: { decision: ReviewDecision; rationale: string; expectedVersion: number }) =>
      optimisticReviewFns[kind](itemId, {
        decision: input.decision,
        rationale: input.rationale,
        expected_version: input.expectedVersion,
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["reviews", "queue"] }),
  });
}

export type ModernizationRecommendationDecision = "ACCEPT" | "REJECT" | "DISMISS";

/**
 * Decide a modernization recommendation (contract: three-way ACCEPT/REJECT/DISMISS,
 * distinct from the two-way CONFIRM/REJECT pattern used by the other finding types).
 */
export function useReviewModernizationRecommendation(recommendationId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: { decision: ModernizationRecommendationDecision; rationale: string; expectedVersion: number }) =>
      stackGraphClient.reviewModernizationRecommendation(recommendationId, {
        decision: input.decision,
        rationale: input.rationale,
        expected_version: input.expectedVersion,
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["reviews", "queue"] }),
  });
}
