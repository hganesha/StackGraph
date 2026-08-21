// Bridge between the workspace's client state (camelCase) and the API contract
// (snake_case string-keyed state). The reducer in useBusinessMap stays unchanged; only
// persistence goes through here.
import type {
  BusinessMapStateModel,
  BusinessMapFunctionNode,
  MaturityLevel as ApiMaturityLevel,
} from "@stackgraph/shared";
import type {
  BusinessFunction,
  MaturityLevel,
  ValueChainStep,
} from "./catalog";
import type { BusinessMapState } from "./useBusinessMap";

function serializeCatalog(catalog: BusinessFunction[]): BusinessMapFunctionNode[] {
  return catalog.map((fn) => ({
    id: fn.id,
    name: fn.name,
    description: fn.description ?? "",
    color: fn.color ?? "",
    gradient: fn.gradient ?? "",
    icon: fn.icon ?? "",
    processes: fn.processes.map((process) => ({
      id: process.id,
      name: process.name,
      description: process.description ?? "",
      capabilities: process.capabilities.map((capability) => ({
        id: capability.id,
        name: capability.name,
        description: capability.description ?? "",
        tags: capability.tags ?? [],
        kpis: capability.kpis ?? [],
        owner: capability.owner ?? null,
      })),
    })),
  }));
}

function serializeLane(step: ValueChainStep, index: number) {
  return {
    id: step.id,
    label: step.label,
    sublabel: step.sublabel ?? "",
    color: step.color ?? "",
    gradient: step.gradient ?? "",
    icon: step.icon ?? "",
    order: typeof step.order === "number" ? step.order : index,
  };
}

/** Client state → API contract payload. */
export function toApiState(map: BusinessMapState): BusinessMapStateModel {
  return {
    title: map.title,
    view_mode: map.viewMode,
    template_id: map.templateId,
    stages: map.stages.map(serializeLane),
    organization_units: map.organizationUnits.map(serializeLane),
    catalog: serializeCatalog(map.catalog),
    placements: map.placements.map((placement) => ({
      capability_id: placement.capabilityId,
      stage_id: placement.stageId,
      maturity: placement.maturity as ApiMaturityLevel,
      source_function_id: placement.sourceFunctionId || null,
    })),
    shared_groups: map.sharedGroups.map((group) => ({
      id: group.id,
      name: group.name,
      description: group.description ?? "",
      capability_ids: group.capabilityIds,
      start_stage_id: group.startStageId,
      end_stage_id: group.endStageId,
    })),
    function_assignments: map.functionAssignments.map((assignment) => ({
      function_id: assignment.functionId,
      unit_id: assignment.unitId,
    })),
    application_assignments: map.applicationAssignments.map((assignment) => ({
      capability_id: assignment.capabilityId,
      application_id: assignment.applicationId,
      application_name: assignment.applicationName,
    })),
  };
}

/** API contract payload → client state. */
export function fromApiState(state: BusinessMapStateModel): BusinessMapState {
  return {
    title: state.title,
    viewMode: state.view_mode,
    templateId: state.template_id,
    stages: state.stages.map((lane) => ({ ...lane })),
    organizationUnits: state.organization_units.map((lane) => ({ ...lane })),
    catalog: state.catalog.map((fn) => ({
      id: fn.id,
      name: fn.name,
      description: fn.description,
      color: fn.color,
      gradient: fn.gradient,
      icon: fn.icon,
      processes: fn.processes.map((process) => ({
        id: process.id,
        name: process.name,
        description: process.description,
        capabilities: process.capabilities.map((capability) => ({
          id: capability.id,
          name: capability.name,
          description: capability.description,
          tags: capability.tags,
          kpis: capability.kpis,
          owner: capability.owner ?? undefined,
        })),
      })),
    })),
    placements: state.placements.map((placement) => ({
      capabilityId: placement.capability_id,
      stageId: placement.stage_id,
      maturity: placement.maturity as MaturityLevel,
      sourceFunctionId: placement.source_function_id ?? "",
    })),
    sharedGroups: state.shared_groups.map((group) => ({
      id: group.id,
      name: group.name,
      description: group.description,
      capabilityIds: group.capability_ids,
      startStageId: group.start_stage_id,
      endStageId: group.end_stage_id,
    })),
    functionAssignments: state.function_assignments.map((assignment) => ({
      functionId: assignment.function_id,
      unitId: assignment.unit_id,
    })),
    applicationAssignments: (state.application_assignments ?? []).map((assignment) => ({
      capabilityId: assignment.capability_id,
      applicationId: assignment.application_id,
      applicationName: assignment.application_name,
    })),
  };
}
