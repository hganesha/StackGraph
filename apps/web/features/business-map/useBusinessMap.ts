"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { stackGraphClient, ApiRequestError } from "@stackgraph/shared";
import { useCan, useSession } from "@/lib/session";
import { useEstateDomainSummary } from "@/lib/queries";
import {
  BUSINESS_FUNCTIONS,
  ORGANIZATION_UNIT_TEMPLATE,
  VALUE_CHAIN_TEMPLATES,
  type BusinessFunction,
  type Capability,
  type MaturityLevel,
  type Process,
  type ValueChainStep,
} from "./catalog";
import { fromApiState, toApiState } from "./serialize";

// A single canonical map per tenant for now; the workspace loads or creates it by this key.
const MAP_KEY = "enterprise.value-chain";

export type PanelMode = "capability" | null;

export interface FunctionInput {
  name: string;
  description: string;
}

export interface ProcessInput extends FunctionInput {
  functionId: string;
}

export interface CapabilityInput extends FunctionInput {
  functionId: string;
  processId: string;
  tags: string[];
  kpis: string[];
  owner?: string;
}

export interface SharedGroupInput extends FunctionInput {
  capabilityIds: string[];
  startStageId: string;
  endStageId: string;
}

export interface SharedCapabilityGroup extends SharedGroupInput {
  id: string;
}

export interface FunctionAssignment {
  functionId: string;
  unitId: string;
}

export interface CapabilityApplicationAssignment {
  capabilityId: string;
  applicationId: string;
  applicationName: string;
}

export type MapViewMode = "value-chain" | "organization";

export interface CapabilityPlacement {
  capabilityId: string;
  stageId: string | null;
  maturity: MaturityLevel;
  sourceFunctionId: string;
}

export interface BusinessMapState {
  title: string;
  viewMode: MapViewMode;
  templateId: string;
  stages: ValueChainStep[];
  placements: CapabilityPlacement[];
  catalog: BusinessFunction[];
  sharedGroups: SharedCapabilityGroup[];
  organizationUnits: ValueChainStep[];
  functionAssignments: FunctionAssignment[];
  applicationAssignments: CapabilityApplicationAssignment[];
}

const STORAGE_KEY = "stackgraph.business-map.v3";
const PREVIOUS_STORAGE_KEY = "stackgraph.business-map.v2";
const LEGACY_STORAGE_KEY = "stackgraph.business-map.v1";

const FUNCTION_STAGE_HINTS: Record<string, number[]> = {
  strategy: [0, 1, 4],
  innovation: [0, 1, 3],
  customer: [2, 3, 4],
  operations: [0, 1, 2],
  technology: [0, 1, 2, 4],
  finance: [0, 1, 4],
  people: [0, 1, 4],
  legal: [0, 1, 4],
};

function cloneTemplate(templateId: string): ValueChainStep[] {
  const template = VALUE_CHAIN_TEMPLATES[templateId] ?? VALUE_CHAIN_TEMPLATES.porter;
  return template.map((stage, index) => ({ ...stage, id: `${templateId}:${index}` }));
}

function cloneCatalog(): BusinessFunction[] {
  return BUSINESS_FUNCTIONS.map((fn) => ({
    ...fn,
    processes: fn.processes.map((process) => ({
      ...process,
      capabilities: process.capabilities.map((capability) => ({
        ...capability,
        tags: capability.tags ? [...capability.tags] : [],
        kpis: capability.kpis ? [...capability.kpis] : [],
      })),
    })),
  }));
}

function cloneOrganizationUnits(): ValueChainStep[] {
  return ORGANIZATION_UNIT_TEMPLATE.map((unit, index) => ({ ...unit, order: index }));
}

function seedFunctionAssignments(catalog: BusinessFunction[], units: ValueChainStep[]): FunctionAssignment[] {
  const unitByFunction: Record<string, number> = {
    strategy: 0,
    innovation: 1,
    customer: 1,
    operations: 2,
    finance: 3,
    people: 3,
    legal: 3,
    technology: 4,
  };
  return catalog.map((fn) => ({
    functionId: fn.id,
    unitId: units[Math.min(unitByFunction[fn.id] ?? 0, units.length - 1)]?.id ?? "",
  }));
}

function makeId(prefix: string): string {
  return `${prefix}:${globalThis.crypto?.randomUUID?.() ?? Date.now()}`;
}

function createInitialState(): BusinessMapState {
  const catalog = cloneCatalog();
  const organizationUnits = cloneOrganizationUnits();
  return {
    title: "Enterprise Value Chain",
    viewMode: "value-chain",
    templateId: "porter",
    stages: cloneTemplate("porter"),
    placements: [],
    catalog,
    sharedGroups: [],
    organizationUnits,
    functionAssignments: seedFunctionAssignments(catalog, organizationUnits),
    applicationAssignments: [],
  };
}

function sourceFunctionId(catalog: BusinessFunction[], capabilityId: string): string {
  return (
    catalog.find((fn) =>
      fn.processes.some((process) => process.capabilities.some((capability) => capability.id === capabilityId)),
    )?.id ?? catalog[0]?.id ?? ""
  );
}

function isSavedState(value: unknown): value is BusinessMapState {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Partial<BusinessMapState>;
  return (
    typeof candidate.title === "string" &&
    typeof candidate.templateId === "string" &&
    Array.isArray(candidate.stages) &&
    Array.isArray(candidate.placements)
  );
}

export function useBusinessMap() {
  // Editing writes to the server; a view-only session stays on the local draft only.
  const { ready: sessionReady } = useSession();
  const canEdit = useCan("execute");
  const estateApplicationsQuery = useEstateDomainSummary(["ENTERPRISE"]);
  const [map, setMap] = useState<BusinessMapState>(createInitialState);
  const [selectedCapabilityId, setSelectedCapabilityId] = useState<string | null>(null);
  const [panel, setPanel] = useState<PanelMode>(null);
  const [libraryOpen, setLibraryOpen] = useState(true);
  const [showGrid, setShowGrid] = useState(true);
  const [zoom, setZoomState] = useState(1);
  const [hydrated, setHydrated] = useState(false);
  const [savedAt, setSavedAt] = useState<number | null>(null);
  const [serverBacked, setServerBacked] = useState(false);
  const skipFirstSave = useRef(true);
  // Server identity/version for optimistic-concurrency saves; refs so the debounced
  // save reads the latest without re-subscribing.
  const mapIdRef = useRef<string | null>(null);
  const versionRef = useRef<number>(0);
  const savingRef = useRef(false);
  const seededRef = useRef<BusinessMapState | null>(null);
  const reconciledRef = useRef(false);

  // Seed instantly from the local draft (offline-first) so the workspace renders without
  // waiting on the network. The server reconcile happens in the next effect.
  useEffect(() => {
    let seeded = createInitialState();
    try {
      const raw = window.localStorage.getItem(STORAGE_KEY)
        ?? window.localStorage.getItem(PREVIOUS_STORAGE_KEY)
        ?? window.localStorage.getItem(LEGACY_STORAGE_KEY);
      if (raw) {
        const parsed: unknown = JSON.parse(raw);
        if (isSavedState(parsed)) {
          const defaults = createInitialState();
          const catalog = Array.isArray(parsed.catalog) ? parsed.catalog : defaults.catalog;
          const organizationUnits = Array.isArray(parsed.organizationUnits) ? parsed.organizationUnits : defaults.organizationUnits;
          seeded = {
            ...defaults,
            ...parsed,
            viewMode: parsed.viewMode === "organization" ? "organization" : "value-chain",
            catalog,
            sharedGroups: Array.isArray(parsed.sharedGroups) ? parsed.sharedGroups : [],
            organizationUnits,
            functionAssignments: Array.isArray(parsed.functionAssignments)
              ? parsed.functionAssignments
              : seedFunctionAssignments(catalog, organizationUnits),
            applicationAssignments: Array.isArray(parsed.applicationAssignments)
              ? parsed.applicationAssignments
              : [],
          };
          setMap(seeded);
        }
      }
    } catch {
      // A corrupt local draft should never block the workspace.
    }
    seededRef.current = seeded;
  }, []);

  // Reconcile with the server once the session settles, so create/edit decisions see the
  // real capability. Runs once; `hydrated` flips only after this settles, so saves never
  // fire against just-loaded server state. Offline keeps the local draft.
  useEffect(() => {
    if (!sessionReady || reconciledRef.current || seededRef.current === null) return;
    reconciledRef.current = true;
    const seeded = seededRef.current;
    let cancelled = false;
    (async () => {
      try {
        const list = await stackGraphClient.listBusinessMaps();
        const existing = list.maps.find((m) => m.map_key === MAP_KEY);
        if (existing) {
          const detail = await stackGraphClient.getBusinessMap(existing.id);
          if (cancelled) return;
          mapIdRef.current = detail.id;
          versionRef.current = detail.version;
          setMap(fromApiState(detail.state));
          setServerBacked(true);
        } else if (canEdit) {
          // No server map yet — only a user who can edit may create it.
          const detail = await stackGraphClient.createBusinessMap({ map_key: MAP_KEY, state: toApiState(seeded) });
          if (cancelled) return;
          mapIdRef.current = detail.id;
          versionRef.current = detail.version;
          setServerBacked(true);
        }
      } catch {
        // Offline / fixtures-without-backend: keep working from the local draft.
      } finally {
        if (!cancelled) setHydrated(true);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [sessionReady, canEdit]);

  // Persist: always cache the draft locally; when server-backed, debounce a whole-map save
  // guarded by the optimistic version, refetching once on a version conflict.
  useEffect(() => {
    if (!hydrated) return;
    if (skipFirstSave.current) {
      skipFirstSave.current = false;
      return;
    }
    const timer = window.setTimeout(() => {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(map));
      setSavedAt(Date.now());
      const mapId = mapIdRef.current;
      if (!mapId || !canEdit || savingRef.current) return;
      savingRef.current = true;
      (async () => {
        try {
          try {
            const saved = await stackGraphClient.saveBusinessMap(mapId, {
              expected_version: versionRef.current,
              state: toApiState(map),
            });
            versionRef.current = saved.version;
          } catch (error) {
            if (error instanceof ApiRequestError && error.status === 409) {
              const latest = await stackGraphClient.getBusinessMap(mapId);
              const retried = await stackGraphClient.saveBusinessMap(mapId, {
                expected_version: latest.version,
                state: toApiState(map),
              });
              versionRef.current = retried.version;
            }
            // Other errors: the local draft already holds the change; retry on next edit.
          }
        } finally {
          savingRef.current = false;
        }
      })();
    }, 350);
    return () => window.clearTimeout(timer);
  }, [hydrated, map]);

  const placementsByStage = useMemo(() => {
    const grouped = new Map<string | null, CapabilityPlacement[]>();
    for (const placement of map.placements) {
      const current = grouped.get(placement.stageId) ?? [];
      current.push(placement);
      grouped.set(placement.stageId, current);
    }
    return grouped;
  }, [map.placements]);

  const capabilityById = useMemo(
    () => new Map<string, Capability>(map.catalog.flatMap((fn) => fn.processes.flatMap((process) => process.capabilities)).map((capability) => [capability.id, capability])),
    [map.catalog],
  );

  const estateApplications = useMemo(
    () => (estateApplicationsQuery.data?.ranked_items ?? [])
      .filter((item) => item.domain === "ENTERPRISE" && item.kind === "Application")
      .map((item) => ({ id: item.id, name: item.name }))
      .sort((left, right) => left.name.localeCompare(right.name)),
    [estateApplicationsQuery.data?.ranked_items],
  );

  const applicationsByCapability = useMemo(() => {
    const grouped = new Map<string, CapabilityApplicationAssignment[]>();
    for (const assignment of map.applicationAssignments) {
      const current = grouped.get(assignment.capabilityId) ?? [];
      current.push(assignment);
      grouped.set(assignment.capabilityId, current);
    }
    for (const assignments of grouped.values()) {
      assignments.sort((left, right) => left.applicationName.localeCompare(right.applicationName));
    }
    return grouped;
  }, [map.applicationAssignments]);

  const selectCapability = useCallback((capabilityId: string | null) => {
    setSelectedCapabilityId(capabilityId);
    setPanel(capabilityId ? "capability" : null);
  }, []);

  const setTemplate = useCallback((templateId: string) => {
    setMap((current) => {
      if (templateId === "organization") return { ...current, viewMode: "organization" };
      const stages = cloneTemplate(templateId);
      const oldIndexes = new Map(current.stages.map((stage, index) => [stage.id, index]));
      const placements = current.placements.map((placement) => {
        if (!placement.stageId) return placement;
        const previousIndex = oldIndexes.get(placement.stageId) ?? 0;
        return { ...placement, stageId: stages[Math.min(previousIndex, stages.length - 1)]?.id ?? null };
      });
      const sharedGroups = current.sharedGroups.map((group) => {
        const startIndex = oldIndexes.get(group.startStageId) ?? 0;
        const endIndex = oldIndexes.get(group.endStageId) ?? startIndex;
        return {
          ...group,
          startStageId: stages[Math.min(startIndex, stages.length - 1)]?.id ?? "",
          endStageId: stages[Math.min(endIndex, stages.length - 1)]?.id ?? "",
        };
      });
      return { ...current, viewMode: "value-chain", templateId, stages, placements, sharedGroups };
    });
  }, []);

  const loadFunction = useCallback((functionId: string) => {
    setMap((current) => {
      const fn = current.catalog.find((candidate) => candidate.id === functionId);
      if (!fn || current.stages.length === 0) return current;
      const existing = new Set(current.placements.map((placement) => placement.capabilityId));
      const stageHints = FUNCTION_STAGE_HINTS[functionId] ?? [0];
      let offset = 0;
      const additions = fn.processes.flatMap((process) =>
        process.capabilities.flatMap((capability) => {
          if (existing.has(capability.id)) return [];
          const hintedIndex = stageHints[offset % stageHints.length] ?? 0;
          offset += 1;
          return [
            {
              capabilityId: capability.id,
              stageId: current.stages[Math.min(hintedIndex, current.stages.length - 1)]?.id ?? null,
              maturity: 2 as MaturityLevel,
              sourceFunctionId: functionId,
            },
          ];
        }),
      );
      return { ...current, placements: [...current.placements, ...additions] };
    });
  }, []);

  const addCapability = useCallback((capabilityId: string, stageId?: string | null) => {
    setMap((current) => {
      if (current.placements.some((placement) => placement.capabilityId === capabilityId)) return current;
      return {
        ...current,
        placements: [
          ...current.placements,
          {
            capabilityId,
            stageId: stageId ?? current.stages[0]?.id ?? null,
            maturity: 2,
            sourceFunctionId: sourceFunctionId(current.catalog, capabilityId),
          },
        ],
      };
    });
    selectCapability(capabilityId);
  }, [selectCapability]);

  const moveCapability = useCallback((capabilityId: string, stageId: string | null) => {
    setMap((current) => ({
      ...current,
      placements: current.placements.map((placement) =>
        placement.capabilityId === capabilityId ? { ...placement, stageId } : placement,
      ),
    }));
  }, []);

  const setMaturity = useCallback((capabilityId: string, maturity: MaturityLevel) => {
    setMap((current) => ({
      ...current,
      placements: current.placements.map((placement) =>
        placement.capabilityId === capabilityId ? { ...placement, maturity } : placement,
      ),
    }));
  }, []);

  const removeCapability = useCallback((capabilityId: string) => {
    setMap((current) => ({
      ...current,
      placements: current.placements.filter((placement) => placement.capabilityId !== capabilityId),
    }));
    setSelectedCapabilityId((selected) => (selected === capabilityId ? null : selected));
    setPanel((current) => (selectedCapabilityId === capabilityId ? null : current));
  }, [selectedCapabilityId]);

  const createFunction = useCallback((input: FunctionInput) => {
    const id = makeId("function");
    setMap((current) => ({
      ...current,
      catalog: [
        ...current.catalog,
        {
          id,
          name: input.name,
          description: input.description,
          color: "#D4A843",
          gradient: "",
          icon: "building",
          processes: [],
        },
      ],
      functionAssignments: [
        ...current.functionAssignments,
        { functionId: id, unitId: current.organizationUnits[0]?.id ?? "" },
      ],
    }));
    return id;
  }, []);

  const updateFunction = useCallback((functionId: string, input: FunctionInput) => {
    setMap((current) => ({
      ...current,
      catalog: current.catalog.map((fn) => (fn.id === functionId ? { ...fn, ...input } : fn)),
    }));
  }, []);

  const deleteFunction = useCallback((functionId: string) => {
    const target = map.catalog.find((fn) => fn.id === functionId);
    const deletedIds = new Set(target?.processes.flatMap((process) => process.capabilities.map((capability) => capability.id)) ?? []);
    setMap((current) => {
      return {
        ...current,
        catalog: current.catalog.filter((fn) => fn.id !== functionId),
        placements: current.placements.filter((placement) => !deletedIds.has(placement.capabilityId)),
        sharedGroups: current.sharedGroups
          .map((group) => ({ ...group, capabilityIds: group.capabilityIds.filter((capabilityId) => !deletedIds.has(capabilityId)) }))
          .filter((group) => group.capabilityIds.length > 0),
        functionAssignments: current.functionAssignments.filter((assignment) => assignment.functionId !== functionId),
        applicationAssignments: current.applicationAssignments.filter(
          (assignment) => !deletedIds.has(assignment.capabilityId),
        ),
      };
    });
    setSelectedCapabilityId((selected) => (selected && deletedIds.has(selected) ? null : selected));
    setPanel((current) => (selectedCapabilityId && deletedIds.has(selectedCapabilityId) ? null : current));
  }, [map.catalog, selectedCapabilityId]);

  const createProcess = useCallback((input: ProcessInput) => {
    const id = makeId("process");
    setMap((current) => ({
      ...current,
      catalog: current.catalog.map((fn) =>
        fn.id === input.functionId
          ? { ...fn, processes: [...fn.processes, { id, name: input.name, description: input.description, capabilities: [] }] }
          : fn,
      ),
    }));
    return id;
  }, []);

  const updateProcess = useCallback((processId: string, input: ProcessInput) => {
    setMap((current) => {
      let processToMove: Process | null = null;
      let previousFunctionId: string | null = null;
      const withoutProcess = current.catalog.map((fn) => {
        const existing = fn.processes.find((process) => process.id === processId);
        if (existing) {
          previousFunctionId = fn.id;
          processToMove = { ...existing, name: input.name, description: input.description };
        }
        return { ...fn, processes: fn.processes.filter((process) => process.id !== processId) };
      });
      if (!processToMove) return current;
      const catalog = withoutProcess.map((fn) =>
        fn.id === input.functionId ? { ...fn, processes: [...fn.processes, processToMove as Process] } : fn,
      );
      const movedCapabilityIds = new Set((processToMove as Process).capabilities.map((capability) => capability.id));
      return {
        ...current,
        catalog,
        placements: previousFunctionId === input.functionId
          ? current.placements
          : current.placements.map((placement) =>
              movedCapabilityIds.has(placement.capabilityId) ? { ...placement, sourceFunctionId: input.functionId } : placement,
            ),
      };
    });
  }, []);

  const deleteProcess = useCallback((processId: string) => {
    const process = map.catalog.flatMap((fn) => fn.processes).find((candidate) => candidate.id === processId);
    const deletedIds = new Set(process?.capabilities.map((capability) => capability.id) ?? []);
    setMap((current) => {
      return {
        ...current,
        catalog: current.catalog.map((fn) => ({ ...fn, processes: fn.processes.filter((candidate) => candidate.id !== processId) })),
        placements: current.placements.filter((placement) => !deletedIds.has(placement.capabilityId)),
        sharedGroups: current.sharedGroups
          .map((group) => ({ ...group, capabilityIds: group.capabilityIds.filter((capabilityId) => !deletedIds.has(capabilityId)) }))
          .filter((group) => group.capabilityIds.length > 0),
        applicationAssignments: current.applicationAssignments.filter(
          (assignment) => !deletedIds.has(assignment.capabilityId),
        ),
      };
    });
    setSelectedCapabilityId((selected) => (selected && deletedIds.has(selected) ? null : selected));
    setPanel((current) => (selectedCapabilityId && deletedIds.has(selectedCapabilityId) ? null : current));
  }, [map.catalog, selectedCapabilityId]);

  const createCatalogCapability = useCallback((input: CapabilityInput) => {
    const id = makeId("capability");
    setMap((current) => ({
      ...current,
      catalog: current.catalog.map((fn) => ({
        ...fn,
        processes: fn.processes.map((process) =>
          process.id === input.processId
            ? {
                ...process,
                capabilities: [
                  ...process.capabilities,
                  {
                    id,
                    name: input.name,
                    description: input.description,
                    tags: input.tags,
                    kpis: input.kpis,
                    owner: input.owner,
                  },
                ],
              }
            : process,
        ),
      })),
    }));
    return id;
  }, []);

  const updateCatalogCapability = useCallback((capabilityId: string, input: CapabilityInput) => {
    setMap((current) => {
      let capabilityToMove: Capability | null = null;
      const catalogWithoutCapability = current.catalog.map((fn) => ({
        ...fn,
        processes: fn.processes.map((process) => {
          const existing = process.capabilities.find((capability) => capability.id === capabilityId);
          if (existing) {
            capabilityToMove = {
              ...existing,
              name: input.name,
              description: input.description,
              tags: input.tags,
              kpis: input.kpis,
              owner: input.owner,
            };
          }
          return { ...process, capabilities: process.capabilities.filter((capability) => capability.id !== capabilityId) };
        }),
      }));
      if (!capabilityToMove) return current;
      return {
        ...current,
        catalog: catalogWithoutCapability.map((fn) => ({
          ...fn,
          processes: fn.processes.map((process) =>
            process.id === input.processId
              ? { ...process, capabilities: [...process.capabilities, capabilityToMove as Capability] }
              : process,
          ),
        })),
        placements: current.placements.map((placement) =>
          placement.capabilityId === capabilityId ? { ...placement, sourceFunctionId: input.functionId } : placement,
        ),
      };
    });
  }, []);

  const deleteCatalogCapability = useCallback((capabilityId: string) => {
    setMap((current) => ({
      ...current,
      catalog: current.catalog.map((fn) => ({
        ...fn,
        processes: fn.processes.map((process) => ({
          ...process,
          capabilities: process.capabilities.filter((capability) => capability.id !== capabilityId),
        })),
      })),
      placements: current.placements.filter((placement) => placement.capabilityId !== capabilityId),
      sharedGroups: current.sharedGroups
        .map((group) => ({ ...group, capabilityIds: group.capabilityIds.filter((id) => id !== capabilityId) }))
        .filter((group) => group.capabilityIds.length > 0),
      applicationAssignments: current.applicationAssignments.filter(
        (assignment) => assignment.capabilityId !== capabilityId,
      ),
    }));
    setSelectedCapabilityId((selected) => (selected === capabilityId ? null : selected));
    setPanel((current) => (selectedCapabilityId === capabilityId ? null : current));
  }, [selectedCapabilityId]);

  const createSharedGroup = useCallback((input: SharedGroupInput) => {
    const id = makeId("shared");
    setMap((current) => ({
      ...current,
      sharedGroups: [...current.sharedGroups, { id, ...input }],
    }));
    return id;
  }, []);

  const updateSharedGroup = useCallback((groupId: string, input: SharedGroupInput) => {
    setMap((current) => ({
      ...current,
      sharedGroups: current.sharedGroups.map((group) => (group.id === groupId ? { ...group, ...input } : group)),
    }));
  }, []);

  const deleteSharedGroup = useCallback((groupId: string) => {
    setMap((current) => ({ ...current, sharedGroups: current.sharedGroups.filter((group) => group.id !== groupId) }));
  }, []);

  const assignFunction = useCallback((functionId: string, unitId: string) => {
    setMap((current) => ({
      ...current,
      functionAssignments: current.functionAssignments.some((assignment) => assignment.functionId === functionId)
        ? current.functionAssignments.map((assignment) =>
            assignment.functionId === functionId ? { ...assignment, unitId } : assignment,
          )
        : [...current.functionAssignments, { functionId, unitId }],
    }));
  }, []);

  const assignApplication = useCallback((capabilityId: string, applicationId: string) => {
    setMap((current) => {
      if (current.applicationAssignments.some(
        (assignment) => assignment.capabilityId === capabilityId && assignment.applicationId === applicationId,
      )) return current;
      const application = estateApplications.find((candidate) => candidate.id === applicationId);
      if (!application) return current;
      return {
        ...current,
        applicationAssignments: [
          ...current.applicationAssignments,
          { capabilityId, applicationId, applicationName: application.name },
        ],
      };
    });
  }, [estateApplications]);

  const unassignApplication = useCallback((capabilityId: string, applicationId: string) => {
    setMap((current) => ({
      ...current,
      applicationAssignments: current.applicationAssignments.filter(
        (assignment) => assignment.capabilityId !== capabilityId || assignment.applicationId !== applicationId,
      ),
    }));
  }, []);

  const addOrganizationUnit = useCallback(() => {
    setMap((current) => ({
      ...current,
      organizationUnits: [
        ...current.organizationUnits,
        {
          id: makeId("org"),
          label: "New organization unit",
          sublabel: "Organizational unit",
          color: "43",
          gradient: "",
          icon: "building",
          order: current.organizationUnits.length,
        },
      ],
    }));
  }, []);

  const renameOrganizationUnit = useCallback((unitId: string, label: string) => {
    setMap((current) => ({
      ...current,
      organizationUnits: current.organizationUnits.map((unit) => (unit.id === unitId ? { ...unit, label } : unit)),
    }));
  }, []);

  const deleteOrganizationUnit = useCallback((unitId: string) => {
    setMap((current) => {
      if (current.organizationUnits.length <= 1) return current;
      const organizationUnits = current.organizationUnits.filter((unit) => unit.id !== unitId);
      const fallbackUnitId = organizationUnits[0]?.id ?? "";
      return {
        ...current,
        organizationUnits,
        functionAssignments: current.functionAssignments.map((assignment) =>
          assignment.unitId === unitId ? { ...assignment, unitId: fallbackUnitId } : assignment,
        ),
      };
    });
  }, []);

  const addStage = useCallback(() => {
    setMap((current) => ({
      ...current,
      templateId: "customized",
      stages: [
        ...current.stages,
        {
          id: `custom:${globalThis.crypto?.randomUUID?.() ?? Date.now()}`,
          label: "New stage",
          sublabel: "Describe this activity",
          color: "214",
          gradient: "",
          icon: "boxes",
          order: current.stages.length,
        },
      ],
    }));
  }, []);

  const renameStage = useCallback((stageId: string, label: string) => {
    setMap((current) => ({
      ...current,
      stages: current.stages.map((stage) => (stage.id === stageId ? { ...stage, label } : stage)),
    }));
  }, []);

  const clear = useCallback(() => {
    setMap((current) => ({ ...current, placements: [] }));
    setSelectedCapabilityId(null);
    setPanel(null);
  }, []);

  const reset = useCallback(() => {
    setMap((current) => {
      const initial = createInitialState();
      return {
        ...initial,
        catalog: current.catalog,
        functionAssignments: seedFunctionAssignments(current.catalog, initial.organizationUnits),
      };
    });
    setSelectedCapabilityId(null);
    setPanel(null);
  }, []);

  const setZoom = useCallback((next: number) => setZoomState(Math.max(0.7, Math.min(1.3, next))), []);

  return {
    map,
    setMap,
    selectedCapabilityId,
    panel,
    setPanel,
    libraryOpen,
    setLibraryOpen,
    showGrid,
    setShowGrid,
    zoom,
    setZoom,
    hydrated,
    savedAt,
    serverBacked,
    placementsByStage,
    capabilityById,
    estateApplications,
    estateApplicationsLoading: estateApplicationsQuery.isLoading,
    applicationsByCapability,
    selectCapability,
    setTemplate,
    loadFunction,
    addCapability,
    moveCapability,
    setMaturity,
    removeCapability,
    createFunction,
    updateFunction,
    deleteFunction,
    createProcess,
    updateProcess,
    deleteProcess,
    createCatalogCapability,
    updateCatalogCapability,
    deleteCatalogCapability,
    createSharedGroup,
    updateSharedGroup,
    deleteSharedGroup,
    assignFunction,
    assignApplication,
    unassignApplication,
    addOrganizationUnit,
    renameOrganizationUnit,
    deleteOrganizationUnit,
    addStage,
    renameStage,
    clear,
    reset,
  };
}
