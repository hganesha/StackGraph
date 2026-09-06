import { useQuery } from "@tanstack/react-query";
import { stackGraphClient } from "@stackgraph/shared";

export function useEstateStrataReadModel() {
  return useQuery({
    queryKey: ["estate", "strata"],
    queryFn: () => stackGraphClient.getEstateStrata(),
    staleTime: 60_000,
  });
}

export function useComponents(cursor?: string, limit = 50) {
  return useQuery({
    queryKey: ["components", "list", cursor, limit],
    queryFn: () => stackGraphClient.listComponents(cursor, limit),
    staleTime: 60_000,
  });
}

export function useComponent(id: string) {
  return useQuery({
    queryKey: ["components", "detail", id],
    queryFn: () => stackGraphClient.getComponent(id),
    enabled: Boolean(id),
    staleTime: 60_000,
  });
}

export function useRepositoryContainerCompositions(repositoryId: string) {
  return useQuery({
    queryKey: ["repositories", repositoryId, "container-compositions"],
    queryFn: () => stackGraphClient.listRepositoryContainerCompositions(repositoryId),
    enabled: Boolean(repositoryId),
    staleTime: 60_000,
  });
}

export function useRepositoryDeploymentProfiles(repositoryId: string) {
  return useQuery({
    queryKey: ["repositories", repositoryId, "deployment-profiles"],
    queryFn: () => stackGraphClient.listRepositoryDeploymentProfiles(repositoryId),
    enabled: Boolean(repositoryId),
    staleTime: 60_000,
  });
}

export function useContradictions(subjectId?: string, limit = 50) {
  return useQuery({
    queryKey: ["contradictions", subjectId, limit],
    queryFn: () => stackGraphClient.listContradictions(subjectId, limit),
    staleTime: 60_000,
  });
}
