import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  stackGraphClient,
  type ActionPredicate,
  type GraphAnalysisRequestCreate,
  type MutationCompileRequest,
  type ObservedMutationCreateRequest,
  type RecommendationCompileRequest,
  type SimulationRunModel,
} from "@stackgraph/shared";

const TERMINAL = new Set<SimulationRunModel["status"]>([
  "SUCCEEDED", "LIMITED", "NOT_SIMULATABLE", "FAILED", "CANCELLED",
]);

export function createIdempotencyKey(prefix: string) {
  const suffix = globalThis.crypto?.randomUUID?.()
    ?? `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  return `${prefix}:${suffix}`;
}

export function useActionTypes(enabled = true) {
  return useQuery({
    queryKey: ["changes", "action-types"],
    queryFn: () => stackGraphClient.listActionTypes(),
    enabled,
    staleTime: 300_000,
  });
}

export function useActionSubjects(predicate: ActionPredicate | null, query: string, enabled = true) {
  return useQuery({
    queryKey: ["changes", "subjects", predicate, query.trim()],
    queryFn: () => stackGraphClient.listActionSubjects(predicate!, query.trim() || undefined),
    enabled: enabled && Boolean(predicate),
    staleTime: 60_000,
  });
}

export function useValidTargets(entityId: string | null, enabled = true) {
  return useQuery({
    queryKey: ["changes", "targets", entityId],
    queryFn: () => stackGraphClient.listValidTargets(entityId!),
    enabled: enabled && Boolean(entityId),
    staleTime: 60_000,
  });
}

export function useChangeScopes(entityId: string | null, enabled = true) {
  return useQuery({
    queryKey: ["changes", "scopes", entityId],
    queryFn: () => stackGraphClient.listChangeScopes(entityId!),
    enabled: enabled && Boolean(entityId),
    staleTime: 60_000,
  });
}

export function useCompileMutation() {
  return useMutation({ mutationFn: (body: MutationCompileRequest) => stackGraphClient.compileMutation(body) });
}

export function useValidateMutation() {
  return useMutation({ mutationFn: (changeSetId: string) => stackGraphClient.validateMutation({ change_set_id: changeSetId }) });
}

export function useCompileRecommendation(id: string) {
  return useMutation({
    mutationFn: (body: RecommendationCompileRequest) => stackGraphClient.compileModernizationRecommendation(id, body),
  });
}

export function useCreateSimulation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: { changeSetId: string; idempotencyKey: string }) => stackGraphClient.createSimulation({
      change_set_id: body.changeSetId,
      idempotency_key: body.idempotencyKey,
    }),
    onSuccess: (run) => queryClient.setQueryData(["changes", "simulation", run.id], run),
  });
}

export function useSimulation(id: string) {
  return useQuery({
    queryKey: ["changes", "simulation", id],
    queryFn: () => stackGraphClient.getSimulation(id),
    enabled: Boolean(id),
    refetchInterval: (query) => {
      const run = query.state.data;
      return run && TERMINAL.has(run.status) ? false : 1_000;
    },
    retry: (failureCount, error) => {
      const status = typeof error === "object" && error && "status" in error ? Number(error.status) : 0;
      return status === 404 ? false : failureCount < 2;
    },
  });
}

export function useCancelSimulation(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => stackGraphClient.cancelSimulation(id),
    onSuccess: (run) => queryClient.setQueryData(["changes", "simulation", id], run),
  });
}

export function useEntityChangeHistory(id: string, limit = 20) {
  return useQuery({
    queryKey: ["changes", "history", id, limit],
    queryFn: () => stackGraphClient.listEntityChangeHistory(id, limit),
    enabled: Boolean(id),
  });
}

export function useRecordObservedMutation() {
  return useMutation({ mutationFn: (body: ObservedMutationCreateRequest) => stackGraphClient.recordObservedMutation(body) });
}

export function useRepositoryFingerprints(id: string, limit = 20) {
  return useQuery({
    queryKey: ["repositories", id, "fingerprints", limit],
    queryFn: () => stackGraphClient.listRepositoryFingerprints(id, limit),
    enabled: Boolean(id),
  });
}

export function useEntityCriticalEdges(id: string) {
  return useQuery({
    queryKey: ["graph-intelligence", "critical-edges", id],
    queryFn: () => stackGraphClient.listEntityCriticalEdges(id),
    enabled: Boolean(id),
  });
}

export function useGraphAnomalies(cohortKey?: string, limit = 50) {
  return useQuery({
    queryKey: ["graph-intelligence", "anomalies", cohortKey, limit],
    queryFn: () => stackGraphClient.listGraphIntelligenceAnomalies(cohortKey, limit),
  });
}

export function useGraphMotifs(motifKey?: string, limit = 50) {
  return useQuery({
    queryKey: ["graph-intelligence", "motifs", motifKey, limit],
    queryFn: () => stackGraphClient.listGraphIntelligenceMotifs(motifKey, limit),
  });
}

export function useRequestGraphAnalysis() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: GraphAnalysisRequestCreate) => stackGraphClient.requestGraphAnalysis(body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["graph-intelligence"] }),
  });
}
