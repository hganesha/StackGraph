import { useQuery } from "@tanstack/react-query";
import { stackGraphClient } from "@stackgraph/shared";

export function useEstateSummary() {
  return useQuery({
    queryKey: ["estate", "summary"],
    queryFn: () => stackGraphClient.getEstateSummary(),
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
