import { useInfiniteQuery, useMutation, useQuery, useQueryClient, type UseQueryOptions } from "@tanstack/react-query";
import { stackGraphClient, type EstateSummary, type Namespace } from "@stackgraph/shared";
import type { SimilarityDecision } from "./reviews";

export function useEstateSummary() {
  return useQuery({
    queryKey: ["estate", "summary"],
    queryFn: () => stackGraphClient.getEstateSummary(),
  });
}

export function useInfiniteEstateSummary(
  domains: Namespace[] = [],
  options?: { enabled?: boolean },
) {
  return useInfiniteQuery({
    queryKey: ["estate", "summary", "infinite", "domains", ...domains],
    queryFn: ({ pageParam }) => stackGraphClient.getEstateSummary({
      cursor: pageParam ?? undefined,
      limit: 50,
      domains,
    }),
    initialPageParam: null as string | null,
    getNextPageParam: (lastPage) => lastPage.page_info?.has_next_page
      ? lastPage.page_info.next_cursor ?? undefined
      : undefined,
    enabled: options?.enabled ?? true,
  });
}

export function useEstateDomainSummary(
  domains: Namespace[],
  options?: Pick<UseQueryOptions<EstateSummary>, "enabled">,
) {
  return useQuery({
    queryKey: ["estate", "summary", "domains", ...domains],
    queryFn: async () => {
      let cursor: string | undefined;
      let combined: EstateSummary | undefined;
      do {
        const page = await stackGraphClient.getEstateSummary({
          cursor,
          limit: 100,
          domains,
        });
        combined = combined
          ? { ...combined, as_of: page.as_of, ranked_items: [...combined.ranked_items, ...page.ranked_items], page_info: page.page_info }
          : page;
        cursor = page.page_info?.has_next_page
          ? page.page_info.next_cursor ?? undefined
          : undefined;
      } while (cursor);
      if (!combined) throw new Error("Estate summary did not return a page.");
      return combined;
    },
    enabled: options?.enabled ?? true,
  });
}

export function useModernization() {
  return useQuery({
    queryKey: ["modernization"],
    queryFn: () => stackGraphClient.listModernization(),
  });
}

export function useEnterpriseInsightReports() {
  return useQuery({
    queryKey: ["insights", "enterprise-reports"],
    queryFn: () => stackGraphClient.listEnterpriseInsightReports(),
    staleTime: 60_000,
  });
}

export function useScanStatus() {
  return useQuery({
    queryKey: ["admin", "scan-status"],
    queryFn: () => stackGraphClient.getScanStatus(),
    refetchInterval: 15_000,
  });
}

export function useServiceStatus() {
  return useQuery({
    queryKey: ["admin", "service-status"],
    queryFn: () => stackGraphClient.getServiceStatus(),
    refetchInterval: 15_000,
  });
}

export function useGraphNeighborhood(centerId: string, depth = 1) {
  return useQuery({
    queryKey: ["graph", centerId, depth],
    queryFn: () => stackGraphClient.getGraphNeighborhood(centerId, depth),
  });
}

export function useGraphIntelligenceStatus() {
  return useQuery({
    queryKey: ["graph-intelligence", "status"],
    queryFn: () => stackGraphClient.getGraphIntelligenceStatus(),
    refetchInterval: 30_000,
  });
}

export function useEntityGraphMetrics(entityId: string) {
  return useQuery({
    queryKey: ["graph-intelligence", "entity", entityId],
    queryFn: () => stackGraphClient.getEntityGraphMetrics(entityId),
    enabled: Boolean(entityId),
  });
}

export function useEntityBlastRadius(entityId: string, enabled = true) {
  return useQuery({
    queryKey: ["graph-intelligence", "blast-radius", entityId],
    queryFn: () => stackGraphClient.getEntityBlastRadius(entityId),
    enabled: Boolean(entityId) && enabled,
  });
}

export function useGraphIntelligenceRisks(limit = 20) {
  return useQuery({
    queryKey: ["graph-intelligence", "risks", limit],
    queryFn: () => stackGraphClient.listGraphIntelligenceRisks(limit),
    staleTime: 60_000,
  });
}

export function useEmbeddingStatus() {
  return useQuery({
    queryKey: ["embeddings", "status"],
    queryFn: () => stackGraphClient.getEmbeddingStatus(),
    refetchInterval: 30_000,
  });
}

export function useSimilarApplications(entityId: string, enabled = true, limit = 10) {
  return useQuery({
    queryKey: ["embeddings", "similar-applications", entityId, limit],
    queryFn: () => stackGraphClient.listSimilarApplications(entityId, limit),
    enabled: Boolean(entityId) && enabled,
    staleTime: 60_000,
  });
}

/**
 * Record a similarity decision. The reason and rationale come from the reviewer:
 * `application_similarity_feedback` is append-only and stores both, so a decision
 * saved without them is a decision nobody can later explain.
 *
 * `entityId` is optional because the review queue decides candidates without an
 * application in context.
 */
export function useReviewApplicationSimilarity(entityId?: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ candidateId, decision, reasonCode, rationale }: {
      candidateId: string;
      decision: SimilarityDecision;
      reasonCode: string;
      rationale?: string;
    }) => stackGraphClient.reviewApplicationSimilarity(candidateId, {
      decision, reason_code: reasonCode, rationale: rationale?.trim() || undefined,
    }),
    onSuccess: () => Promise.all([
      // Without an entity in context, invalidate every similarity list rather than a
      // key ending in undefined, which would match nothing.
      queryClient.invalidateQueries({
        queryKey: entityId
          ? ["embeddings", "similar-applications", entityId]
          : ["embeddings", "similar-applications"],
      }),
      queryClient.invalidateQueries({ queryKey: ["reviews", "queue"] }),
    ]),
  });
}

export function useTechnologyEstateHierarchy() {
  return useQuery({
    queryKey: ["technologies", "hierarchy"],
    queryFn: () => stackGraphClient.getTechnologyEstateHierarchy(),
  });
}

export function useReviewQueue() {
  return useQuery({
    queryKey: ["reviews", "queue"],
    queryFn: () => stackGraphClient.getReviewQueue({ limit: 50 }),
  });
}
