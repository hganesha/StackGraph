import { useQuery } from "@tanstack/react-query";
import { stackGraphClient, type EstateSummary, type Namespace } from "@stackgraph/shared";

export function useEstateSummary() {
  return useQuery({
    queryKey: ["estate", "summary"],
    queryFn: () => stackGraphClient.getEstateSummary(),
  });
}

export function useEstateDomainSummary(domains: Namespace[]) {
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
  });
}

export function useModernization() {
  return useQuery({
    queryKey: ["modernization"],
    queryFn: () => stackGraphClient.listModernization(),
  });
}

export function useGraphNeighborhood(centerId: string) {
  return useQuery({
    queryKey: ["graph", centerId],
    queryFn: () => stackGraphClient.getGraphNeighborhood(centerId),
  });
}

export function useReviewQueue() {
  return useQuery({
    queryKey: ["reviews", "queue"],
    queryFn: () => stackGraphClient.getReviewQueue({ limit: 50 }),
  });
}
