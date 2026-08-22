"use client";

import { useMutation, useQuery, useQueryClient, type UseQueryOptions } from "@tanstack/react-query";
import {
  stackGraphClient,
  type ArchitectureReferenceModel,
  type CanvasComparisonRequest,
  type CanvasProjection,
  type CanvasProjectionParams,
  type CanvasScope,
  type TenantArchitectureProfile,
  type TenantArchitectureProfileUpdateRequest,
} from "@stackgraph/shared";

// The reference model and template are versioned, content-hashed artifacts. They change
// only on a publish, so they are cached hard; projections carry an `as_of` and are not.
const IMMUTABLE = { staleTime: 30 * 60_000, gcTime: 60 * 60_000 } as const;

export const DEFAULT_REFERENCE_MODEL_KEY = "architecture.stackgraph.reference";
export const DEFAULT_TEMPLATE_KEY = "canvas.stackgraph.reference";

export function useCanvasReferenceModel(
  key: string = DEFAULT_REFERENCE_MODEL_KEY,
  options?: Pick<UseQueryOptions<ArchitectureReferenceModel>, "enabled">,
) {
  return useQuery({
    queryKey: ["canvas", "reference-model", key],
    queryFn: () => stackGraphClient.getCanvasReferenceModel(key),
    enabled: options?.enabled ?? true,
    ...IMMUTABLE,
  });
}

export function useCanvasTemplate(
  referenceModelKey: string = DEFAULT_REFERENCE_MODEL_KEY,
  templateKey: string = DEFAULT_TEMPLATE_KEY,
  options?: { enabled?: boolean },
) {
  return useQuery({
    queryKey: ["canvas", "template", referenceModelKey, templateKey],
    queryFn: () => stackGraphClient.getCanvasTemplate(templateKey),
    enabled: options?.enabled ?? true,
    ...IMMUTABLE,
  });
}

export function useCanvasTemplateList(
  referenceModelKey: string = DEFAULT_REFERENCE_MODEL_KEY,
  options?: { enabled?: boolean },
) {
  return useQuery({
    queryKey: ["canvas", "templates", referenceModelKey],
    queryFn: () => stackGraphClient.listCanvasTemplates(referenceModelKey),
    enabled: options?.enabled ?? true,
    ...IMMUTABLE,
  });
}

export function useCanvasProjection(
  params: CanvasProjectionParams,
  options?: { enabled?: boolean },
) {
  return useQuery({
    queryKey: [
      "canvas", "projection", params.scope, params.subjectId ?? null,
      params.referenceModelKey ?? DEFAULT_REFERENCE_MODEL_KEY,
      params.templateKey ?? DEFAULT_TEMPLATE_KEY, params.asOf ?? null,
    ],
    queryFn: () => stackGraphClient.getCanvasProjection(params),
    enabled: options?.enabled ?? true,
  });
}

/**
 * The target projection sits behind `review`, not `view` (spec §10.2). Callers must
 * gate on the capability; passing `enabled: false` keeps an unauthorised surface from
 * firing a request that would 403.
 */
export function useCanvasTargetProjection(options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: ["canvas", "projection", "TARGET"],
    queryFn: () => stackGraphClient.getCanvasTargetProjection(),
    enabled: options?.enabled ?? true,
  });
}

export function useCanvasComparison(
  request: CanvasComparisonRequest | null,
  options?: { enabled?: boolean },
) {
  return useQuery({
    queryKey: ["canvas", "comparison", request],
    queryFn: () => stackGraphClient.createCanvasComparison(request as CanvasComparisonRequest),
    enabled: Boolean(request) && (options?.enabled ?? true),
  });
}

export function useArchitectureProfiles(options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: ["canvas", "architecture-profiles"],
    queryFn: () => stackGraphClient.listArchitectureProfiles(),
    enabled: options?.enabled ?? true,
  });
}

/**
 * Profile writes invalidate every projection: an expectation change can move a cell
 * from POPULATED to NOT_APPLICABLE, and a decision change rewrites conformance
 * everywhere. Narrower invalidation would leave a stale canvas on screen.
 */
function useProfileInvalidation() {
  const queryClient = useQueryClient();
  return () => {
    queryClient.invalidateQueries({ queryKey: ["canvas", "projection"] });
    queryClient.invalidateQueries({ queryKey: ["canvas", "comparison"] });
    queryClient.invalidateQueries({ queryKey: ["canvas", "architecture-profiles"] });
  };
}

export function useUpdateArchitectureProfile() {
  const invalidate = useProfileInvalidation();
  return useMutation<
    TenantArchitectureProfile,
    Error,
    { id: string; body: TenantArchitectureProfileUpdateRequest }
  >({
    mutationFn: ({ id, body }) => stackGraphClient.updateArchitectureProfile(id, body),
    onSuccess: invalidate,
  });
}

export function usePublishArchitectureProfile() {
  const invalidate = useProfileInvalidation();
  return useMutation<TenantArchitectureProfile, Error, string>({
    mutationFn: (id) => stackGraphClient.publishArchitectureProfile(id),
    onSuccess: invalidate,
  });
}

/** Resolves the model, template, and projection a canvas surface needs in one call. */
export function useCanvasSurface(scope: CanvasScope, subjectId?: string) {
  const referenceModel = useCanvasReferenceModel();
  const template = useCanvasTemplate();
  const projection = useCanvasProjection({ scope, subjectId });
  return {
    referenceModel: referenceModel.data ?? null,
    template: template.data ?? null,
    projection: (projection.data as CanvasProjection | undefined) ?? null,
    isLoading: referenceModel.isLoading || template.isLoading || projection.isLoading,
    isError: referenceModel.isError || template.isError || projection.isError,
    error: referenceModel.error ?? template.error ?? projection.error ?? null,
    refetch: () => {
      void projection.refetch();
    },
  };
}
