import { useInfiniteQuery, useQuery, type UseQueryOptions } from "@tanstack/react-query";
import { stackGraphClient, type EstateSummary, type Namespace } from "@stackgraph/shared";

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

export function useGraphNeighborhood(centerId: string, depth = 1) {
  return useQuery({
    queryKey: ["graph", centerId, depth],
    queryFn: () => stackGraphClient.getGraphNeighborhood(centerId, depth),
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
