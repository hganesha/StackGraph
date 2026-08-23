"use client";

import { useMemo } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  stackGraphClient,
  toComparisonView,
  toProjectionView,
  toReferenceModelView,
  type ArchitectureProfileDetail,
  type ArchitectureProfileList,
  type ArchitectureProfileStateModel,
  type CanvasComparisonRequest,
  type CanvasProjectionParams,
  type CanvasComparisonView,
  type CanvasProjectionView,
  type CanvasScope,
  type TenantCellPolicyModel,
} from "@stackgraph/shared";

// The reference model, taxonomy, and template are versioned, content-hashed artifacts.
// They change only on a publish, so they are cached hard; projections carry an `as_of`
// and are not.
const IMMUTABLE = { staleTime: 30 * 60_000, gcTime: 60 * 60_000 } as const;

/**
 * The adapted result callers actually use. Returned explicitly rather than by
 * spreading the react-query object, so no wire type leaks into an inferred signature.
 */
export interface CanvasQueryResult<T> {
  data: T | undefined;
  isLoading: boolean;
  isError: boolean;
  error: Error | null;
  refetch: () => void;
}

export const DEFAULT_REFERENCE_MODEL_KEY = "architecture.stackgraph.reference";
export const DEFAULT_TEMPLATE_KEY = "canvas.stackgraph.reference";

export function useArchitectureTaxonomy(options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: ["canvas", "taxonomy"],
    queryFn: () => stackGraphClient.getArchitectureTaxonomy(),
    enabled: options?.enabled ?? true,
    ...IMMUTABLE,
  });
}

/**
 * The renderer needs domains and aspects, which live in the taxonomy rather than on
 * the reference model, so the two are fetched together and merged into one view.
 */
export function useCanvasReferenceModel(key: string = DEFAULT_REFERENCE_MODEL_KEY) {
  const model = useQuery({
    queryKey: ["canvas", "reference-model", key],
    queryFn: () => stackGraphClient.getCanvasReferenceModel(key),
    ...IMMUTABLE,
  });
  const taxonomy = useArchitectureTaxonomy();
  const data = useMemo(
    () => (model.data && taxonomy.data ? toReferenceModelView(model.data, taxonomy.data) : undefined),
    [model.data, taxonomy.data],
  );
  return {
    data,
    isLoading: model.isLoading || taxonomy.isLoading,
    isError: model.isError || taxonomy.isError,
    error: model.error ?? taxonomy.error ?? null,
  };
}

/** The templates list returns full geometry, so there is no read-by-key to call. */
export function useCanvasTemplate(templateKey: string = DEFAULT_TEMPLATE_KEY) {
  const list = useQuery({
    queryKey: ["canvas", "templates"],
    queryFn: () => stackGraphClient.listCanvasTemplates(),
    ...IMMUTABLE,
  });
  const data = useMemo(
    () => list.data?.templates.find((entry) => entry.key === templateKey) ?? list.data?.templates[0],
    [list.data, templateKey],
  );
  return { data, isLoading: list.isLoading, isError: list.isError, error: list.error };
}

export function useCanvasProjection(
  params: CanvasProjectionParams,
  options?: { enabled?: boolean },
): CanvasQueryResult<CanvasProjectionView> {
  const query = useQuery({
    queryKey: [
      "canvas", "projection", params.scope, params.subjectId ?? null,
      params.referenceModelKey ?? DEFAULT_REFERENCE_MODEL_KEY,
      params.templateKey ?? DEFAULT_TEMPLATE_KEY,
    ],
    queryFn: () => stackGraphClient.getCanvasProjection(params),
    enabled: options?.enabled ?? true,
  });
  const data = useMemo<CanvasProjectionView | undefined>(
    () => (query.data ? toProjectionView(query.data) : undefined),
    [query.data],
  );
  return {
    data,
    isLoading: query.isLoading,
    isError: query.isError,
    error: query.error,
    refetch: () => void query.refetch(),
  };
}

/**
 * The target projection sits behind `review`, not `view`.
 *
 * It always resolves the revision in force: the published route takes no profile
 * selector, so a draft cannot be previewed here. Govern mode compensates by showing
 * the draft's own pending policies rather than pretending the target has changed.
 */
export function useCanvasTargetProjection(
  options?: { enabled?: boolean },
): CanvasQueryResult<CanvasProjectionView> {
  const query = useQuery({
    queryKey: ["canvas", "projection", "TARGET"],
    queryFn: () => stackGraphClient.getCanvasTargetProjection(),
    enabled: options?.enabled ?? true,
  });
  const data = useMemo<CanvasProjectionView | undefined>(
    () => (query.data ? toProjectionView(query.data) : undefined),
    [query.data],
  );
  return {
    data,
    isLoading: query.isLoading,
    isError: query.isError,
    error: query.error,
    refetch: () => void query.refetch(),
  };
}

export function useCanvasComparison(
  request: CanvasComparisonRequest | null,
  options?: { enabled?: boolean },
): CanvasQueryResult<CanvasComparisonView> {
  const query = useQuery({
    queryKey: ["canvas", "comparison", request],
    queryFn: () => stackGraphClient.createCanvasComparison(request as CanvasComparisonRequest),
    enabled: Boolean(request) && (options?.enabled ?? true),
  });
  const data = useMemo(() => (query.data ? toComparisonView(query.data) : undefined), [query.data]);
  return {
    data,
    isLoading: query.isLoading,
    isError: query.isError,
    error: query.error,
    refetch: () => void query.refetch(),
  };
}

export function useArchitectureProfiles(options?: { enabled?: boolean }) {
  return useQuery<ArchitectureProfileList>({
    queryKey: ["canvas", "architecture-profiles"],
    queryFn: () => stackGraphClient.listArchitectureProfiles(),
    enabled: options?.enabled ?? true,
  });
}

/**
 * Authoritative profile state, held only for revisions this session has read in full.
 *
 * The API publishes no read-by-id for a profile: the list returns summaries without
 * `state`, and full state comes back only from create and update. Since an update is
 * a whole-state PUT, writing from anything less than an authoritative copy would
 * silently drop policies this session never saw. So state is cached when the API
 * hands it over, and govern mode refuses to write when it is absent, rather than
 * guessing. See docs/architecture-canvas-api-gaps.md.
 */
export function useProfileDetailCache() {
  const queryClient = useQueryClient();
  return {
    read: (id: string) =>
      queryClient.getQueryData<ArchitectureProfileDetail>(["canvas", "architecture-profile", id]) ?? null,
    write: (detail: ArchitectureProfileDetail) =>
      queryClient.setQueryData(["canvas", "architecture-profile", detail.id], detail),
  };
}

export function useProfileDetail(id: string | null) {
  const queryClient = useQueryClient();
  return id
    ? queryClient.getQueryData<ArchitectureProfileDetail>(["canvas", "architecture-profile", id]) ?? null
    : null;
}

/**
 * Profile writes invalidate every projection: an expectation change can move a cell
 * from POPULATED to NOT_APPLICABLE, and a decision change rewrites conformance
 * everywhere. Narrower invalidation would leave a stale canvas on screen.
 */
function useProfileInvalidation() {
  const queryClient = useQueryClient();
  return (detail?: ArchitectureProfileDetail) => {
    if (detail) queryClient.setQueryData(["canvas", "architecture-profile", detail.id], detail);
    queryClient.invalidateQueries({ queryKey: ["canvas", "projection"] });
    queryClient.invalidateQueries({ queryKey: ["canvas", "comparison"] });
    queryClient.invalidateQueries({ queryKey: ["canvas", "architecture-profiles"] });
  };
}

export function useCreateArchitectureProfile() {
  const invalidate = useProfileInvalidation();
  return useMutation<ArchitectureProfileDetail, Error, { profileKey: string; state: ArchitectureProfileStateModel }>({
    mutationFn: ({ profileKey, state }) =>
      stackGraphClient.createArchitectureProfile({ profile_key: profileKey, state }),
    onSuccess: invalidate,
  });
}

export function useUpdateArchitectureProfile() {
  const invalidate = useProfileInvalidation();
  return useMutation<
    ArchitectureProfileDetail,
    Error,
    { id: string; expectedVersion: number; state: ArchitectureProfileStateModel }
  >({
    mutationFn: ({ id, expectedVersion, state }) =>
      stackGraphClient.updateArchitectureProfile(id, { expected_version: expectedVersion, state }),
    onSuccess: invalidate,
  });
}

export function usePublishArchitectureProfile() {
  const invalidate = useProfileInvalidation();
  return useMutation<ArchitectureProfileDetail, Error, { id: string; expectedVersion: number }>({
    mutationFn: ({ id, expectedVersion }) =>
      stackGraphClient.publishArchitectureProfile(id, { expected_version: expectedVersion }),
    onSuccess: invalidate,
  });
}

/**
 * The effective policies of the revision in force, read back off the target
 * projection. This is what a new draft is seeded from, so "new draft from active"
 * starts as a faithful copy rather than an empty profile.
 */
export function cellPoliciesFromProjection(
  projection: CanvasProjectionView | undefined,
): TenantCellPolicyModel[] {
  if (!projection) return [];
  return projection.cells
    .filter((cell) => cell.policy?.governed)
    .map((cell) => {
      const policy = cell.policy!;
      const ids = (decision: string) =>
        policy.decisions.filter((entry) => entry.decision === decision).map((entry) => entry.technology.id);
      return {
        cell_key: cell.cell_key,
        applicability: cell.expectation.applicability,
        minimum_implementations: cell.expectation.minimum_implementations,
        maximum_implementations: cell.expectation.maximum_implementations,
        allowed_diversity: cell.expectation.allowed_diversity,
        preferred_technology_ids: ids("PREFERRED"),
        allowed_technology_ids: ids("ALLOWED"),
        discouraged_technology_ids: ids("DISCOURAGED"),
        prohibited_technology_ids: ids("PROHIBITED"),
        rationale: policy.rationale ?? "",
        owner: policy.owner,
        effective_from: policy.effective_from,
        effective_to: policy.effective_to,
        scope_selector: policy.scope_selector ?? {},
        exceptions: policy.exceptions.map((exception) => ({
          key: exception.key,
          rationale: exception.rationale,
          subject_ids: exception.subject_ids,
          effective_from: exception.effective_from,
          effective_to: exception.effective_to,
        })),
      };
    });
}

export type { CanvasScope };
