import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  stackGraphClient,
  type AssumptionCreateRequest,
  type ContradictionResolveRequest,
} from "@stackgraph/shared";

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

export function useEstateLineage(entityId?: string, limit = 100) {
  return useQuery({
    queryKey: ["estate", "lineage", entityId, limit],
    queryFn: () => stackGraphClient.listEstateLineage(entityId, limit),
    staleTime: 60_000,
  });
}

export function useAISupplyChain() {
  return useQuery({
    queryKey: ["estate", "ai-supply-chain"],
    queryFn: () => stackGraphClient.getAISupplyChain(),
    staleTime: 60_000,
  });
}

export function useAssumptions(subjectId?: string, status?: string, limit = 50) {
  return useQuery({
    queryKey: ["estate", "assumptions", subjectId, status, limit],
    queryFn: () => stackGraphClient.listAssumptions(subjectId, status, limit),
    staleTime: 60_000,
  });
}

export function useCreateAssumption() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: AssumptionCreateRequest) => stackGraphClient.createAssumption(body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["estate", "assumptions"] }),
  });
}

export function useResolveContradiction() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: ContradictionResolveRequest }) =>
      stackGraphClient.resolveContradiction(id, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["contradictions"] });
      queryClient.invalidateQueries({ queryKey: ["estate", "assumptions"] });
    },
  });
}
