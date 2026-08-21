"use client";

import { useDeferredValue, useMemo, useState, type CSSProperties, type FormEvent, type KeyboardEvent } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import {
  DndContext,
  KeyboardSensor,
  PointerSensor,
  useDraggable,
  useDroppable,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import {
  IconAdjustmentsHorizontal,
  IconArrowLeft,
  IconArrowRight,
  IconArrowsHorizontal,
  IconBuilding,
  IconCheck,
  IconChevronDown,
  IconEdit,
  IconEye,
  IconGridDots,
  IconGripVertical,
  IconLayoutSidebarLeftCollapse,
  IconLayoutSidebarLeftExpand,
  IconMessageQuestion,
  IconMinus,
  IconPlus,
  IconRefresh,
  IconSearch,
  IconTrash,
  IconX,
} from "@tabler/icons-react";
import { VALUE_CHAIN_TEMPLATES, type Capability, type MaturityLevel } from "./catalog";
import {
  useBusinessMap,
  type CapabilityInput,
  type CapabilityPlacement,
  type FunctionInput,
  type ProcessInput,
  type SharedGroupInput,
} from "./useBusinessMap";
import styles from "./BusinessMapWorkspace.module.css";

const MATURITY = [
  { value: 1, label: "Initial", detail: "Ad hoc and reactive" },
  { value: 2, label: "Developing", detail: "Repeatable but inconsistent" },
  { value: 3, label: "Defined", detail: "Documented and standardised" },
  { value: 4, label: "Advanced", detail: "Measured and controlled" },
  { value: 5, label: "Optimising", detail: "Continuously improving" },
] as const;

type BusinessMapController = ReturnType<typeof useBusinessMap>;

type CatalogEditorTarget =
  | { kind: "function"; mode: "create" | "edit"; functionId?: string }
  | { kind: "process"; mode: "create" | "edit"; functionId: string; processId?: string }
  | { kind: "capability"; mode: "create" | "edit"; functionId: string; processId: string; capabilityId?: string };

type SharedGroupEditorTarget = { mode: "create" | "edit"; groupId?: string };

const SHARED_BAND_TOP = 76;
const SHARED_BAND_STRIDE = 64;
const SHARED_BAND_BODY_GAP = 8;

function IconButton({
  label,
  pressed,
  onClick,
  children,
}: {
  label: string;
  pressed?: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      className={`${styles.iconButton} ${pressed ? styles.iconButtonActive : ""}`}
      aria-label={label}
      aria-pressed={pressed}
      title={label}
      onClick={onClick}
    >
      {children}
    </button>
  );
}

function Toolbar({
  controller,
  onNewSharedGroup,
  editing,
  onEditingChange,
}: {
  controller: BusinessMapController;
  onNewSharedGroup: () => void;
  editing: boolean;
  onEditingChange: (editing: boolean) => void;
}) {
  const { map } = controller;
  const router = useRouter();
  const average = map.placements.length
    ? map.placements.reduce((sum, placement) => sum + placement.maturity, 0) / map.placements.length
    : null;

  return (
    <header className={styles.toolbar}>
      <div className={styles.toolbarIdentity}>
        <span className={styles.bizMark} aria-hidden="true">BIZ</span>
        {editing ? (
          <input
            className={styles.mapTitle}
            aria-label="Business map title"
            value={map.title}
            onChange={(event) => controller.setMap((current) => ({ ...current, title: event.target.value }))}
          />
        ) : <strong className={`${styles.mapTitle} ${styles.mapTitleView}`}>{map.title}</strong>}
      </div>

      {editing ? <label className={styles.templateControl}>
        <span>Template</span>
        <select value={map.viewMode === "organization" ? "organization" : map.templateId} onChange={(event) => controller.setTemplate(event.target.value)}>
          {Object.keys(VALUE_CHAIN_TEMPLATES).map((templateId) => (
            <option key={templateId} value={templateId}>
              {templateId === "porter" ? "Porter value chain" : templateId.replace(/^./, (letter) => letter.toUpperCase())}
            </option>
          ))}
          {map.templateId === "customized" ? <option value="customized">Customized</option> : null}
          <option value="organization">Organization map</option>
        </select>
        <IconChevronDown size={14} stroke={1.5} aria-hidden="true" />
      </label> : (
        <div className={`${styles.templateControl} ${styles.templateViewLabel}`}>
          <span>Template</span>
          <strong>{map.viewMode === "organization" ? "Organization map" : map.templateId === "porter" ? "Porter value chain" : map.templateId.replace(/^./, (letter) => letter.toUpperCase())}</strong>
        </div>
      )}

      {editing && map.viewMode === "value-chain" ? <details className={styles.loadMenu}>
        <summary>Load function <IconChevronDown size={14} stroke={1.5} /></summary>
        <div className={styles.loadPopover}>
          <p>Suggested capability placements</p>
          {map.catalog.map((fn, index) => {
            const total = fn.processes.flatMap((process) => process.capabilities).length;
            return (
              <button key={fn.id} type="button" onClick={() => controller.loadFunction(fn.id)}>
                <span className="sg-mono">{String(index + 1).padStart(2, "0")}</span>
                <span>{fn.name}</span>
                <span className="sg-mono">+{total}</span>
              </button>
            );
          })}
        </div>
      </details> : editing && map.viewMode === "organization" ? <span className={styles.orgModeHint}><IconBuilding size={14} /> Functions by organization</span> : null}

      <div className={styles.toolbarSpacer} />

      <button type="button" className={styles.metrics} aria-label="Map metrics">
        {map.viewMode === "organization" ? (
          <>
            <span><strong className="sg-mono">{String(map.catalog.length).padStart(2, "0")}</strong>Functions</span>
            <span><strong className="sg-mono">{String(map.organizationUnits.length).padStart(2, "0")}</strong>Units</span>
            <span><strong className="sg-mono">{String(map.functionAssignments.length).padStart(2, "0")}</strong>Mapped</span>
          </>
        ) : (
          <>
            <span><strong className="sg-mono">{String(map.placements.length).padStart(2, "0")}</strong>Capabilities</span>
            <span><strong className="sg-mono">{String(map.stages.length).padStart(2, "0")}</strong>Stages</span>
            <span><strong className="sg-mono">{average ? average.toFixed(1) : "—"}</strong>Average</span>
          </>
        )}
      </button>

      <div className={styles.toolbarControls}>
        {editing ? (
          <IconButton
            label={controller.libraryOpen ? "Hide capability library" : "Show capability library"}
            pressed={controller.libraryOpen}
            onClick={() => controller.setLibraryOpen((open) => !open)}
          >
            {controller.libraryOpen ? <IconLayoutSidebarLeftCollapse size={17} /> : <IconLayoutSidebarLeftExpand size={17} />}
          </IconButton>
        ) : null}
        <IconButton label="Toggle canvas grid" pressed={controller.showGrid} onClick={() => controller.setShowGrid((show) => !show)}>
          <IconGridDots size={17} />
        </IconButton>
        <div className={styles.zoomControl}>
          <IconButton label="Zoom out" onClick={() => controller.setZoom(controller.zoom - 0.1)}><IconMinus size={15} /></IconButton>
          <span className="sg-mono">{Math.round(controller.zoom * 100)}%</span>
          <IconButton label="Zoom in" onClick={() => controller.setZoom(controller.zoom + 0.1)}><IconPlus size={15} /></IconButton>
        </div>
        {editing ? <IconButton label="Reset business map" onClick={controller.reset}><IconRefresh size={16} /></IconButton> : null}
        {editing && map.viewMode === "value-chain" ? (
          <button type="button" className={styles.sharedButton} onClick={onNewSharedGroup}>
            <IconPlus size={16} stroke={1.5} /> <span>Shared group</span>
          </button>
        ) : null}
        <div className={styles.modeSwitch} role="group" aria-label="Map mode">
          <button type="button" aria-pressed={!editing} onClick={() => onEditingChange(false)}><IconEye size={15} /> View</button>
          <button type="button" aria-pressed={editing} onClick={() => onEditingChange(true)}><IconEdit size={15} /> Edit</button>
        </div>
        <button
          type="button"
          className={styles.askMapButton}
          onClick={() => {
            const context = {
              title: map.title,
              template: map.templateId,
              viewMode: map.viewMode,
              stages: map.stages.map((stage) => ({
                name: stage.label,
                capabilities: (controller.placementsByStage.get(stage.id) ?? []).map((placement) => ({
                  name: controller.capabilityById.get(placement.capabilityId)?.name ?? placement.capabilityId,
                  maturity: placement.maturity,
                  applications: (controller.applicationsByCapability.get(placement.capabilityId) ?? [])
                    .map((application) => application.applicationName),
                })),
              })),
              organizationUnits: map.organizationUnits.map((unit) => ({
                name: unit.label,
                functions: map.functionAssignments
                  .filter((assignment) => assignment.unitId === unit.id)
                  .map((assignment) => controller.map.catalog.find((fn) => fn.id === assignment.functionId)?.name)
                  .filter(Boolean),
              })),
            };
            window.sessionStorage.setItem("stackgraph.ask.business-map-context", JSON.stringify(context));
            router.push("/ask?source=business-map");
          }}
        >
          <IconMessageQuestion size={16} stroke={1.5} /> <span>Ask about map</span>
        </button>
      </div>
    </header>
  );
}

function CapabilityLibrary({
  controller,
  onEdit,
}: {
  controller: BusinessMapController;
  onEdit: (target: CatalogEditorTarget) => void;
}) {
  const [query, setQuery] = useState("");
  const deferredQuery = useDeferredValue(query.trim().toLowerCase());
  const placedIds = useMemo(() => new Set(controller.map.placements.map((placement) => placement.capabilityId)), [controller.map.placements]);
  const capabilityCount = controller.map.catalog.reduce(
    (total, fn) => total + fn.processes.reduce((processTotal, process) => processTotal + process.capabilities.length, 0),
    0,
  );

  return (
    <aside className={styles.library} aria-label="Capability library">
      <div className={styles.libraryHeader}>
        <div>
          <h2>Capability library</h2>
          <p className="sg-mono">{capabilityCount} capabilities · {controller.map.catalog.length} functions</p>
        </div>
        <div className={styles.libraryHeaderActions}>
          <button type="button" onClick={() => onEdit({ kind: "function", mode: "create" })}><IconPlus size={14} /> Function</button>
          {controller.map.placements.length ? <button type="button" onClick={controller.clear}>Clear</button> : null}
        </div>
      </div>
      <label className={styles.searchBox}>
        <IconSearch size={15} aria-hidden="true" />
        <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search capabilities" />
        {query ? <button type="button" aria-label="Clear search" onClick={() => setQuery("")}><IconX size={14} /></button> : null}
      </label>

      <div className={styles.functionList}>
        {controller.map.catalog.map((fn, functionIndex) => {
          const matchingProcesses = fn.processes
            .map((process) => ({
              ...process,
              capabilities: process.capabilities.filter((capability) =>
                !deferredQuery ||
                capability.name.toLowerCase().includes(deferredQuery) ||
                capability.description.toLowerCase().includes(deferredQuery) ||
                capability.tags?.some((tag) => tag.toLowerCase().includes(deferredQuery)),
              ),
            }))
            .filter((process) => !deferredQuery || process.capabilities.length > 0);
          if (deferredQuery && matchingProcesses.length === 0) return null;
          const allCapabilities = fn.processes.flatMap((process) => process.capabilities);
          const completed = allCapabilities.filter((capability) => placedIds.has(capability.id)).length;
          return (
            <details key={fn.id} className={styles.functionGroup} open={Boolean(deferredQuery) || fn.id === "technology"}>
              <summary>
                <span className="sg-mono">{String(functionIndex + 1).padStart(2, "0")}</span>
                <span><strong>{fn.name}</strong><i><b style={{ width: `${allCapabilities.length ? (completed / allCapabilities.length) * 100 : 0}%` }} /></i></span>
                <span className="sg-mono">{completed}/{allCapabilities.length}</span>
                <IconChevronDown size={14} aria-hidden="true" />
              </summary>
              <div className={styles.processList}>
                <div className={styles.functionActions} role="group" aria-label={`${fn.name} actions`}>
                  <button
                    type="button"
                    aria-label={`Add process to ${fn.name}`}
                    title="Add process"
                    onClick={() => onEdit({ kind: "process", mode: "create", functionId: fn.id })}
                  >
                    <IconPlus size={13} /> <span>Process</span>
                  </button>
                  <button
                    type="button"
                    aria-label={`Edit ${fn.name}`}
                    title="Edit function"
                    onClick={() => onEdit({ kind: "function", mode: "edit", functionId: fn.id })}
                  >
                    <IconEdit size={13} />
                  </button>
                </div>
                <button type="button" className={styles.loadFunctionButton} onClick={() => controller.loadFunction(fn.id)}>
                  Load suggested placements <span>+{allCapabilities.length - completed}</span>
                </button>
                {matchingProcesses.map((process, processIndex) => (
                  <section key={process.id} className={styles.processGroup}>
                    <div className={styles.processHeading}>
                      <h3><span className="sg-mono">{String(processIndex + 1).padStart(2, "0")}</span>{process.name}</h3>
                      <span>
                        <button type="button" aria-label={`Add capability to ${process.name}`} title="Add capability" onClick={() => onEdit({ kind: "capability", mode: "create", functionId: fn.id, processId: process.id })}><IconPlus size={13} /></button>
                        <button type="button" aria-label={`Edit ${process.name}`} title="Edit process" onClick={() => onEdit({ kind: "process", mode: "edit", functionId: fn.id, processId: process.id })}><IconEdit size={13} /></button>
                      </span>
                    </div>
                    {process.capabilities.map((capability) => {
                      const placed = placedIds.has(capability.id);
                      return (
                        <div key={capability.id} className={styles.capabilityLibraryRow}>
                          <button
                            type="button"
                            className={styles.libraryCapability}
                            disabled={placed}
                            onClick={() => controller.addCapability(capability.id)}
                          >
                            <span>{capability.name}</span>
                            {placed ? <IconCheck size={14} aria-label="On map" /> : <IconPlus size={14} aria-hidden="true" />}
                          </button>
                          <button
                            type="button"
                            className={styles.editCatalogButton}
                            aria-label={`Edit ${capability.name}`}
                            title="Edit capability"
                            onClick={() => onEdit({ kind: "capability", mode: "edit", functionId: fn.id, processId: process.id, capabilityId: capability.id })}
                          >
                            <IconEdit size={13} />
                          </button>
                        </div>
                      );
                    })}
                  </section>
                ))}
                {fn.processes.length === 0 ? (
                  <button type="button" className={styles.emptyCatalogAction} onClick={() => onEdit({ kind: "process", mode: "create", functionId: fn.id })}>
                    <IconPlus size={14} /> Add the first process
                  </button>
                ) : null}
              </div>
            </details>
          );
        })}
      </div>
    </aside>
  );
}

function CapabilityCard({
  capability,
  placement,
  selected,
  stageIndex,
  stageCount,
  editing,
  onSelect,
  onMove,
  applications,
}: {
  capability: Capability;
  placement: CapabilityPlacement;
  selected: boolean;
  stageIndex: number;
  stageCount: number;
  editing: boolean;
  onSelect: () => void;
  onMove: (index: number) => void;
  applications: Array<{ applicationId: string; applicationName: string }>;
}) {
  const draggable = useDraggable({ id: placement.capabilityId, disabled: !editing });
  const transform = draggable.transform
    ? `translate3d(${draggable.transform.x}px, ${draggable.transform.y}px, 0)`
    : undefined;
  const maturityLabel = MATURITY.find((item) => item.value === placement.maturity)?.label ?? "Unknown";

  const onKeyDown = (event: KeyboardEvent<HTMLButtonElement>) => {
    if (!editing) return;
    if (!event.altKey) return;
    if (event.key === "ArrowLeft" && stageIndex > 0) {
      event.preventDefault();
      onMove(stageIndex - 1);
    }
    if (event.key === "ArrowRight" && stageIndex < stageCount - 1) {
      event.preventDefault();
      onMove(stageIndex + 1);
    }
  };

  return (
    <article
      ref={draggable.setNodeRef}
      className={`${styles.capabilityCard} ${!editing ? styles.capabilityCardView : ""} ${selected ? styles.capabilityCardSelected : ""} ${draggable.isDragging ? styles.capabilityCardDragging : ""}`}
      style={{ transform } as CSSProperties}
    >
      <button
        type="button"
        className={styles.capabilityCardHeader}
        {...(editing ? draggable.listeners : {})}
        {...(editing ? draggable.attributes : {})}
        aria-label={editing ? `${capability.name}. Maturity ${maturityLabel}. Alt plus left or right arrow moves between stages.` : `${capability.name}. Maturity ${maturityLabel}.`}
        aria-pressed={selected}
        onClick={onSelect}
        onKeyDown={onKeyDown}
      >
        <span className={styles.maturityTicks} aria-hidden="true">
          {MATURITY.map((item) => <i key={item.value} data-filled={item.value <= placement.maturity} />)}
        </span>
        <span>{capability.name}</span>
        {applications.length > 0 ? <span className="sg-mono">{applications.length}</span> : null}
      </button>
      {applications.length > 0 ? (
        <div className={styles.applicationStack} aria-label={`${capability.name} applications`}>
          {applications.slice(0, 3).map((application) => (
            <Link key={application.applicationId} href={`/applications/${application.applicationId}`}>
              <span aria-hidden="true">ENT</span>
              <span>{application.applicationName}</span>
              <span aria-hidden="true">→</span>
            </Link>
          ))}
          {applications.length > 3 ? <button type="button" onClick={onSelect}>+{applications.length - 3} more</button> : null}
        </div>
      ) : null}
    </article>
  );
}

function ValueChainStage({
  controller,
  stageId,
  stageIndex,
  sharedGroupCount,
  editing,
}: {
  controller: BusinessMapController;
  stageId: string;
  stageIndex: number;
  sharedGroupCount: number;
  editing: boolean;
}) {
  const stage = controller.map.stages[stageIndex];
  const droppable = useDroppable({ id: stageId, disabled: !editing });
  const placements = controller.placementsByStage.get(stageId) ?? [];

  return (
    <section
      ref={droppable.setNodeRef}
      className={`${styles.stage} ${droppable.isOver ? styles.stageDropTarget : ""}`}
      style={{ gridColumn: stageIndex + 1, gridRow: 1 }}
    >
      <div className={styles.stageHeader}>
        <span className="sg-mono">{String(stageIndex + 1).padStart(2, "0")}</span>
        {editing ? <label>
          <span className={styles.visuallyHidden}>Stage {stageIndex + 1} name</span>
          <input value={stage.label} onChange={(event) => controller.renameStage(stage.id, event.target.value)} />
          <small>{stage.sublabel}</small>
        </label> : <div className={styles.stageLabel}><strong>{stage.label}</strong><small>{stage.sublabel}</small></div>}
        <span className="sg-mono">{String(placements.length).padStart(2, "0")}</span>
      </div>
      <div
        className={styles.stageBody}
        style={{ paddingTop: sharedGroupCount ? SHARED_BAND_BODY_GAP + sharedGroupCount * SHARED_BAND_STRIDE : undefined }}
      >
        {placements.map((placement) => {
          const capability = controller.capabilityById.get(placement.capabilityId);
          if (!capability) return null;
          return (
            <CapabilityCard
              key={placement.capabilityId}
              capability={capability}
              placement={placement}
              selected={controller.selectedCapabilityId === placement.capabilityId}
              stageIndex={stageIndex}
              stageCount={controller.map.stages.length}
              editing={editing}
              applications={controller.applicationsByCapability.get(placement.capabilityId) ?? []}
              onSelect={() => controller.selectCapability(placement.capabilityId)}
              onMove={(index) => controller.moveCapability(placement.capabilityId, controller.map.stages[index]?.id ?? null)}
            />
          );
        })}
        {placements.length === 0 ? <p>{editing ? "Drop or add capabilities here" : "No capabilities mapped"}</p> : null}
      </div>
    </section>
  );
}

function ValueChainCanvas({
  controller,
  onEditSharedGroup,
  editing,
}: {
  controller: BusinessMapController;
  onEditSharedGroup: (groupId: string) => void;
  editing: boolean;
}) {
  return (
    <main className={`${styles.canvas} ${controller.showGrid ? styles.canvasGrid : ""}`} aria-label="Value chain canvas">
      <div className={styles.canvasScroll} tabIndex={0} role="group" aria-label="Scrollable map region">
        <div
          className={styles.stageGrid}
          style={{
            gridTemplateColumns: `repeat(${controller.map.stages.length}, minmax(164px, 1fr)) 92px`,
            transform: `scale(${controller.zoom})`,
            transformOrigin: "top left",
          }}
        >
          {controller.map.stages.map((stage, index) => (
            <ValueChainStage
              key={stage.id}
              controller={controller}
              stageId={stage.id}
              stageIndex={index}
              sharedGroupCount={controller.map.sharedGroups.length}
              editing={editing}
            />
          ))}
          {controller.map.sharedGroups.map((group, bandIndex) => {
            const startIndex = controller.map.stages.findIndex((stage) => stage.id === group.startStageId);
            const endIndex = controller.map.stages.findIndex((stage) => stage.id === group.endStageId);
            const first = Math.max(0, Math.min(startIndex, endIndex));
            const last = Math.max(first, Math.max(startIndex, endIndex));
            const bandContent = (
              <>
                <IconArrowsHorizontal size={14} />
                <span><strong>{group.name}</strong><small>{group.capabilityIds.length} shared capabilities</small></span>
                {editing ? <IconEdit size={13} /> : null}
              </>
            );
            const bandStyle = {
              gridColumn: `${first + 1} / ${Math.min(last + 2, controller.map.stages.length + 1)}`,
              gridRow: 1,
              marginTop: SHARED_BAND_TOP + bandIndex * SHARED_BAND_STRIDE,
            };
            return editing ? (
              <button
                key={group.id}
                type="button"
                className={styles.sharedBand}
                style={bandStyle}
                onClick={() => onEditSharedGroup(group.id)}
              >
                {bandContent}
              </button>
            ) : <div key={group.id} className={`${styles.sharedBand} ${styles.sharedBandView}`} style={bandStyle}>{bandContent}</div>;
          })}
          {editing ? <button
            type="button"
            className={styles.addStage}
            style={{ gridColumn: controller.map.stages.length + 1, gridRow: 1 }}
            onClick={controller.addStage}
            aria-label="Add value chain stage"
          >
            <IconPlus size={18} /> <span>Add stage</span>
          </button> : null}
        </div>
      </div>
      {controller.map.placements.length === 0 ? (
        <div className={styles.emptyState}>
          <IconAdjustmentsHorizontal size={22} stroke={1.3} />
          <strong>{editing ? "Build the business view" : "No capabilities mapped"}</strong>
          <p>{editing ? "Load a function for suggested placements, or add individual capabilities from the library." : "Enter Edit mode to build this value chain."}</p>
        </div>
      ) : null}
      <div className={styles.canvasFooter}>
        <span>{controller.map.sharedGroups.length ? `${controller.map.sharedGroups.length} shared ·` : ""} Maturity</span>
        {MATURITY.map((item) => <span key={item.value}><i data-level={item.value} />{item.label}</span>)}
        <span className={styles.saveStatus}>{editing ? controller.savedAt ? "Draft saved locally" : "Draft ready" : "View mode"}</span>
      </div>
    </main>
  );
}

function OrganizationFunctionCard({
  controller,
  functionId,
  onEdit,
  editing,
}: {
  controller: BusinessMapController;
  functionId: string;
  onEdit: (target: CatalogEditorTarget) => void;
  editing: boolean;
}) {
  const fn = controller.map.catalog.find((candidate) => candidate.id === functionId);
  const draggable = useDraggable({ id: `function:${functionId}`, disabled: !editing });
  if (!fn) return null;
  const capabilityCount = fn.processes.reduce((total, process) => total + process.capabilities.length, 0);
  const transform = draggable.transform
    ? `translate3d(${draggable.transform.x}px, ${draggable.transform.y}px, 0)`
    : undefined;

  const cardContent = (
    <>
      {editing ? <IconGripVertical size={14} aria-hidden="true" /> : null}
      <span><strong>{fn.name}</strong><small>{fn.processes.length} processes · {capabilityCount} capabilities</small></span>
      {editing ? <IconEdit size={13} aria-hidden="true" /> : null}
    </>
  );

  return editing ? (
    <button
      ref={draggable.setNodeRef}
      type="button"
      className={`${styles.organizationFunctionCard} ${draggable.isDragging ? styles.capabilityCardDragging : ""}`}
      style={{ transform } as CSSProperties}
      {...draggable.listeners}
      {...draggable.attributes}
      onClick={() => onEdit({ kind: "function", mode: "edit", functionId })}
    >
      {cardContent}
    </button>
  ) : <article ref={draggable.setNodeRef} className={`${styles.organizationFunctionCard} ${styles.organizationFunctionCardView}`}>{cardContent}</article>;
}

function OrganizationCanvas({
  controller,
  onEditFunction,
  editing,
}: {
  controller: BusinessMapController;
  onEditFunction: (target: CatalogEditorTarget) => void;
  editing: boolean;
}) {
  return (
    <main className={`${styles.canvas} ${controller.showGrid ? styles.canvasGrid : ""}`} aria-label="Organization to function map">
      <div className={styles.canvasScroll} tabIndex={0} role="group" aria-label="Scrollable map region">
        <div
          className={`${styles.stageGrid} ${styles.organizationGrid}`}
          style={{
            gridTemplateColumns: `repeat(${controller.map.organizationUnits.length}, minmax(180px, 1fr)) 92px`,
            transform: `scale(${controller.zoom})`,
            transformOrigin: "top left",
          }}
        >
          {controller.map.organizationUnits.map((unit, index) => {
            const droppableId = `org-unit:${unit.id}`;
            const assignments = controller.map.functionAssignments.filter((assignment) => assignment.unitId === unit.id);
            return (
              <OrganizationUnit
                key={unit.id}
                controller={controller}
                unitId={unit.id}
                droppableId={droppableId}
                unitIndex={index}
                functionIds={assignments.map((assignment) => assignment.functionId)}
                onEditFunction={onEditFunction}
                editing={editing}
              />
            );
          })}
          {editing ? <button
            type="button"
            className={styles.addStage}
            style={{ gridColumn: controller.map.organizationUnits.length + 1, gridRow: 1 }}
            onClick={controller.addOrganizationUnit}
            aria-label="Add organization unit"
          >
            <IconPlus size={18} /> <span>Add unit</span>
          </button> : null}
        </div>
      </div>
      {editing ? <div className={styles.organizationEmptyHint}>
        <IconBuilding size={18} /> Drag business functions between organization units
      </div> : null}
      <div className={styles.canvasFooter}>
        <span>Organization map</span>
        <span><i data-level="2" />Functions are durable business responsibilities</span>
        <span><i data-level="4" />Units represent the current operating structure</span>
        <span className={styles.saveStatus}>{editing ? controller.savedAt ? "Draft saved locally" : "Draft ready" : "View mode"}</span>
      </div>
    </main>
  );
}

function OrganizationUnit({
  controller,
  unitId,
  droppableId,
  unitIndex,
  functionIds,
  onEditFunction,
  editing,
}: {
  controller: BusinessMapController;
  unitId: string;
  droppableId: string;
  unitIndex: number;
  functionIds: string[];
  onEditFunction: (target: CatalogEditorTarget) => void;
  editing: boolean;
}) {
  const unit = controller.map.organizationUnits.find((candidate) => candidate.id === unitId);
  const droppable = useDroppable({ id: droppableId, disabled: !editing });
  if (!unit) return null;

  return (
    <section
      ref={droppable.setNodeRef}
      className={`${styles.stage} ${styles.organizationUnit} ${droppable.isOver ? styles.stageDropTarget : ""}`}
      style={{ gridColumn: unitIndex + 1, gridRow: 1 }}
    >
      <div className={styles.stageHeader}>
        <span className="sg-mono">{String(unitIndex + 1).padStart(2, "0")}</span>
        {editing ? <label>
          <span className={styles.visuallyHidden}>Organization unit {unitIndex + 1} name</span>
          <input value={unit.label} onChange={(event) => controller.renameOrganizationUnit(unit.id, event.target.value)} />
          <small>{unit.sublabel}</small>
        </label> : <div className={styles.stageLabel}><strong>{unit.label}</strong><small>{unit.sublabel}</small></div>}
        {editing ? <button
          type="button"
          className={styles.deleteUnitButton}
          disabled={controller.map.organizationUnits.length <= 1}
          aria-label={`Delete ${unit.label}`}
          title="Delete organization unit"
          onClick={() => controller.deleteOrganizationUnit(unit.id)}
        >
          <IconTrash size={13} />
        </button> : <span className="sg-mono">{String(functionIds.length).padStart(2, "0")}</span>}
      </div>
      <div className={styles.stageBody}>
        {functionIds.map((functionId) => (
          <OrganizationFunctionCard key={functionId} controller={controller} functionId={functionId} onEdit={onEditFunction} editing={editing} />
        ))}
        {functionIds.length === 0 ? <p>{editing ? "Drop business functions here" : "No functions mapped"}</p> : null}
      </div>
    </section>
  );
}

function CapabilityPanel({
  controller,
  onEdit,
  editing,
}: {
  controller: BusinessMapController;
  onEdit: (target: CatalogEditorTarget) => void;
  editing: boolean;
}) {
  const [applicationId, setApplicationId] = useState("");
  const placement = controller.map.placements.find((item) => item.capabilityId === controller.selectedCapabilityId);
  const capability = placement ? controller.capabilityById.get(placement.capabilityId) : null;
  const owner = placement ? controller.map.catalog.find((fn) => fn.id === placement.sourceFunctionId) : null;
  const process = capability
    ? owner?.processes.find((candidate) => candidate.capabilities.some((item) => item.id === capability.id))
    : null;
  if (!placement || !capability) return null;
  const stageIndex = controller.map.stages.findIndex((stage) => stage.id === placement.stageId);
  const assignedApplications = controller.applicationsByCapability.get(capability.id) ?? [];
  const assignedApplicationIds = new Set(assignedApplications.map((application) => application.applicationId));
  const availableApplications = controller.estateApplications.filter(
    (application) => !assignedApplicationIds.has(application.id),
  );

  return (
    <aside className={styles.detailPanel} aria-label="Capability detail">
      <div className={styles.panelHeader}><span>Capability</span><IconButton label="Close capability detail" onClick={() => controller.selectCapability(null)}><IconX size={16} /></IconButton></div>
      <div className={styles.panelScroll}>
        <div className={styles.capabilityIdentity}>
          <span className={styles.domainLabel}>BIZ · {owner?.name ?? "Business"}</span>
          <h2>{capability.name}</h2>
          <p>{capability.description}</p>
        </div>
        <section className={styles.panelSection}>
          <h3>Maturity assessment</h3>
          {editing ? <div className={styles.maturityOptions}>
            {MATURITY.map((item) => (
              <button
                key={item.value}
                type="button"
                aria-pressed={placement.maturity === item.value}
                onClick={() => controller.setMaturity(capability.id, item.value as MaturityLevel)}
              >
                <span className="sg-mono">{String(item.value).padStart(2, "0")}</span>
                <span><strong>{item.label}</strong><small>{item.detail}</small></span>
                {placement.maturity === item.value ? <IconCheck size={16} /> : null}
              </button>
            ))}
          </div> : (() => {
            const maturity = MATURITY.find((item) => item.value === placement.maturity);
            return <div className={styles.maturityReadOnly}><span className="sg-mono">{String(placement.maturity).padStart(2, "0")}</span><span><strong>{maturity?.label}</strong><small>{maturity?.detail}</small></span></div>;
          })()}
        </section>
        <section className={styles.panelSection}>
          <h3>Value-chain stage</h3>
          {editing ? <><select value={placement.stageId ?? ""} onChange={(event) => controller.moveCapability(capability.id, event.target.value || null)}>
            <option value="">Unassigned</option>
            {controller.map.stages.map((stage) => <option key={stage.id} value={stage.id}>{stage.label}</option>)}
          </select>
          <div className={styles.stageMoveButtons}>
            <button type="button" disabled={stageIndex <= 0} onClick={() => controller.moveCapability(capability.id, controller.map.stages[stageIndex - 1]?.id ?? null)}><IconArrowLeft size={15} /> Previous</button>
            <button type="button" disabled={stageIndex < 0 || stageIndex >= controller.map.stages.length - 1} onClick={() => controller.moveCapability(capability.id, controller.map.stages[stageIndex + 1]?.id ?? null)}>Next <IconArrowRight size={15} /></button>
          </div></> : <p className={styles.stageReadOnly}>{controller.map.stages.find((stage) => stage.id === placement.stageId)?.label ?? "Unassigned"}</p>}
        </section>
        <section className={styles.panelSection}>
          <h3>Business structure</h3>
          <dl className={styles.structureList}>
            <div><dt>Function</dt><dd>{owner?.name ?? "—"}</dd></div>
            <div><dt>Process</dt><dd>{process?.name ?? "—"}</dd></div>
            <div><dt>Source</dt><dd>Starter catalog · CURATED</dd></div>
          </dl>
        </section>
        <section className={styles.panelSection}>
          <div className={styles.panelSectionHeading}>
            <h3>Applications</h3>
            <span className="sg-mono">{String(assignedApplications.length).padStart(2, "0")}</span>
          </div>
          {assignedApplications.length > 0 ? (
            <ul className={styles.capabilityApplications}>
              {assignedApplications.map((application) => (
                <li key={application.applicationId}>
                  <Link href={`/applications/${application.applicationId}`}>
                    <span aria-hidden="true">ENT</span>
                    <strong>{application.applicationName}</strong>
                    <span aria-hidden="true">→</span>
                  </Link>
                  {editing ? (
                    <button
                      type="button"
                      aria-label={`Unlink ${application.applicationName}`}
                      title="Unlink application"
                      onClick={() => controller.unassignApplication(capability.id, application.applicationId)}
                    >
                      <IconX size={14} />
                    </button>
                  ) : null}
                </li>
              ))}
            </ul>
          ) : <p className={styles.noCapabilityApplications}>No applications linked to this capability.</p>}
          {editing ? (
            <div className={styles.applicationAssignmentControl}>
              <select
                aria-label="Application to link"
                value={applicationId}
                disabled={controller.estateApplicationsLoading || availableApplications.length === 0}
                onChange={(event) => setApplicationId(event.target.value)}
              >
                <option value="">
                  {controller.estateApplicationsLoading
                    ? "Loading estate applications…"
                    : availableApplications.length === 0
                      ? "No more applications"
                      : "Select estate application"}
                </option>
                {availableApplications.map((application) => (
                  <option key={application.id} value={application.id}>{application.name}</option>
                ))}
              </select>
              <button
                type="button"
                disabled={!applicationId}
                onClick={() => {
                  controller.assignApplication(capability.id, applicationId);
                  setApplicationId("");
                }}
              >
                <IconPlus size={14} /> Link
              </button>
            </div>
          ) : null}
        </section>
        {capability.kpis?.length ? (
          <section className={styles.panelSection}>
            <h3>Suggested measures</h3>
            <ol className={styles.kpiList}>{capability.kpis.map((kpi) => <li key={kpi}>{kpi}</li>)}</ol>
          </section>
        ) : null}
      </div>
      {editing ? <div className={styles.panelFooterActions}>
        <button type="button" onClick={() => onEdit({ kind: "capability", mode: "edit", functionId: owner?.id ?? placement.sourceFunctionId, processId: process?.id ?? "", capabilityId: capability.id })}><IconEdit size={15} /> Edit definition</button>
        <button type="button" onClick={() => controller.removeCapability(capability.id)}><IconTrash size={15} /> Remove from map</button>
      </div> : null}
    </aside>
  );
}

function SharedGroupEditorPanel({
  controller,
  target,
  onClose,
}: {
  controller: BusinessMapController;
  target: SharedGroupEditorTarget;
  onClose: () => void;
}) {
  const existing = target.groupId ? controller.map.sharedGroups.find((group) => group.id === target.groupId) : null;
  const firstCapabilityId = existing?.capabilityIds[0];
  const existingFunction = firstCapabilityId
    ? controller.map.catalog.find((fn) => fn.processes.some((process) => process.capabilities.some((capability) => capability.id === firstCapabilityId)))
    : null;
  const initialFunction = existingFunction ?? controller.map.catalog[0];
  const [functionId, setFunctionId] = useState(initialFunction?.id ?? "");
  const [name, setName] = useState(existing?.name ?? (initialFunction ? `${initialFunction.name} · Shared` : "Shared capability group"));
  const [description, setDescription] = useState(existing?.description ?? "Cross-cutting capabilities shared across multiple value-chain stages.");
  const [capabilityIds, setCapabilityIds] = useState<string[]>(existing?.capabilityIds ?? initialFunction?.processes.flatMap((process) => process.capabilities.map((capability) => capability.id)) ?? []);
  const [startStageId, setStartStageId] = useState(existing?.startStageId ?? controller.map.stages[0]?.id ?? "");
  const [endStageId, setEndStageId] = useState(existing?.endStageId ?? controller.map.stages.at(-1)?.id ?? "");
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [error, setError] = useState("");
  const selectedFunction = controller.map.catalog.find((fn) => fn.id === functionId);
  const availableCapabilities = selectedFunction?.processes.flatMap((process) => process.capabilities) ?? [];

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!name.trim() || capabilityIds.length === 0) {
      setError("Add a name and at least one capability.");
      return;
    }
    const startIndex = controller.map.stages.findIndex((stage) => stage.id === startStageId);
    const endIndex = controller.map.stages.findIndex((stage) => stage.id === endStageId);
    const firstIndex = Math.max(0, Math.min(startIndex, endIndex));
    const lastIndex = Math.max(firstIndex, Math.max(startIndex, endIndex));
    const input: SharedGroupInput = {
      name: name.trim(),
      description: description.trim(),
      capabilityIds,
      startStageId: controller.map.stages[firstIndex]?.id ?? "",
      endStageId: controller.map.stages[lastIndex]?.id ?? "",
    };
    if (existing) controller.updateSharedGroup(existing.id, input);
    else controller.createSharedGroup(input);
    onClose();
  };

  return (
    <aside className={styles.detailPanel} aria-label={`${existing ? "Edit" : "Create"} shared capability group`}>
      <div className={styles.panelHeader}>
        <span><IconArrowsHorizontal size={15} /> {existing ? "Edit" : "New"} shared group</span>
        <IconButton label="Close shared group editor" onClick={onClose}><IconX size={16} /></IconButton>
      </div>
      <form className={styles.catalogForm} onSubmit={submit}>
        <div className={styles.catalogFormScroll}>
          <div className={styles.editorIntro}>
            <span className={styles.domainLabel}>HORIZONTAL · SHARED</span>
            <p>Use a shared group when a function or capability set enables several contiguous value-chain stages.</p>
          </div>
          <label className={styles.formField}>
            <span>Start from function</span>
            <select
              value={functionId}
              onChange={(event) => {
                const nextFunctionId = event.target.value;
                const nextFunction = controller.map.catalog.find((fn) => fn.id === nextFunctionId);
                setFunctionId(nextFunctionId);
                setCapabilityIds(nextFunction?.processes.flatMap((process) => process.capabilities.map((capability) => capability.id)) ?? []);
                if (!existing && nextFunction) setName(`${nextFunction.name} · Shared`);
              }}
            >
              {controller.map.catalog.map((fn) => <option key={fn.id} value={fn.id}>{fn.name}</option>)}
            </select>
          </label>
          <label className={styles.formField}>
            <span>Group name</span>
            <input value={name} onChange={(event) => setName(event.target.value)} autoFocus placeholder="Shared capability group" />
          </label>
          <label className={styles.formField}>
            <span>Description</span>
            <textarea value={description} onChange={(event) => setDescription(event.target.value)} rows={3} />
          </label>
          <div className={styles.rangeFields}>
            <label className={styles.formField}>
              <span>From stage</span>
              <select value={startStageId} onChange={(event) => setStartStageId(event.target.value)}>
                {controller.map.stages.map((stage) => <option key={stage.id} value={stage.id}>{stage.label}</option>)}
              </select>
            </label>
            <label className={styles.formField}>
              <span>Through stage</span>
              <select value={endStageId} onChange={(event) => setEndStageId(event.target.value)}>
                {controller.map.stages.map((stage) => <option key={stage.id} value={stage.id}>{stage.label}</option>)}
              </select>
            </label>
          </div>
          <fieldset className={styles.groupCapabilityFieldset}>
            <legend>Capabilities in group · {capabilityIds.length} selected</legend>
            <div className={styles.groupCapabilityList}>
              {availableCapabilities.map((capability) => (
                <label key={capability.id}>
                  <input
                    type="checkbox"
                    checked={capabilityIds.includes(capability.id)}
                    onChange={(event) => setCapabilityIds((current) =>
                      event.target.checked
                        ? [...current, capability.id]
                        : current.filter((capabilityId) => capabilityId !== capability.id),
                    )}
                  />
                  <span>{capability.name}</span>
                </label>
              ))}
            </div>
          </fieldset>
          {error ? <p className={styles.formError} role="alert">{error}</p> : null}
          {existing ? (
            <section className={styles.dangerZone}>
              <h3>Danger zone</h3>
              {confirmDelete ? (
                <div>
                  <p>Delete this shared group? Its underlying capabilities remain in the catalog and on the canvas.</p>
                  <span><button type="button" onClick={() => setConfirmDelete(false)}>Cancel</button><button type="button" onClick={() => { controller.deleteSharedGroup(existing.id); onClose(); }}>Delete permanently</button></span>
                </div>
              ) : (
                <button type="button" onClick={() => setConfirmDelete(true)}><IconTrash size={14} /> Delete shared group</button>
              )}
            </section>
          ) : null}
        </div>
        <div className={styles.catalogFormFooter}>
          <button type="button" onClick={onClose}>Cancel</button>
          <button type="submit">{existing ? "Save changes" : "Create shared group"}</button>
        </div>
      </form>
    </aside>
  );
}

function CatalogEditorPanel({
  controller,
  target,
  onClose,
}: {
  controller: BusinessMapController;
  target: CatalogEditorTarget;
  onClose: () => void;
}) {
  const existingFunction = target.functionId ? controller.map.catalog.find((fn) => fn.id === target.functionId) : null;
  const existingProcess = target.kind !== "function"
    ? controller.map.catalog.flatMap((fn) => fn.processes).find((process) => process.id === target.processId)
    : null;
  const existingCapability = target.kind === "capability" && target.capabilityId
    ? controller.capabilityById.get(target.capabilityId)
    : null;
  const [name, setName] = useState(existingCapability?.name ?? existingProcess?.name ?? existingFunction?.name ?? "");
  const [description, setDescription] = useState(existingCapability?.description ?? existingProcess?.description ?? existingFunction?.description ?? "");
  const [functionId, setFunctionId] = useState(target.functionId ?? controller.map.catalog[0]?.id ?? "");
  const [processId, setProcessId] = useState(target.kind === "capability" ? target.processId : "");
  const [organizationUnitId, setOrganizationUnitId] = useState(
    (target.functionId
      ? controller.map.functionAssignments.find((assignment) => assignment.functionId === target.functionId)?.unitId
      : undefined) ?? controller.map.organizationUnits[0]?.id ?? "",
  );
  const [owner, setOwner] = useState(existingCapability?.owner ?? "");
  const [tags, setTags] = useState(existingCapability?.tags?.join(", ") ?? "");
  const [kpis, setKpis] = useState(existingCapability?.kpis?.join("\n") ?? "");
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [error, setError] = useState("");
  const availableProcesses = controller.map.catalog.find((fn) => fn.id === functionId)?.processes ?? [];
  const entityLabel = target.kind === "function" ? "Business function" : target.kind === "process" ? "Business process" : "Capability";
  const destructiveCount = target.kind === "function"
    ? existingFunction?.processes.reduce((total, process) => total + process.capabilities.length, 0) ?? 0
    : target.kind === "process"
      ? existingProcess?.capabilities.length ?? 0
      : existingCapability ? 1 : 0;

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!name.trim()) {
      setError("Name is required.");
      return;
    }
    if (target.kind === "function") {
      const input: FunctionInput = { name: name.trim(), description: description.trim() };
      const savedFunctionId = target.mode === "edit" && target.functionId
        ? (controller.updateFunction(target.functionId, input), target.functionId)
        : controller.createFunction(input);
      if (organizationUnitId) controller.assignFunction(savedFunctionId, organizationUnitId);
    } else if (target.kind === "process") {
      if (!functionId) {
        setError("Choose a parent function.");
        return;
      }
      const input: ProcessInput = { functionId, name: name.trim(), description: description.trim() };
      if (target.mode === "edit" && target.processId) controller.updateProcess(target.processId, input);
      else controller.createProcess(input);
    } else {
      const resolvedProcessId = processId || availableProcesses[0]?.id || "";
      if (!functionId || !resolvedProcessId) {
        setError("Choose a function with at least one process.");
        return;
      }
      const input: CapabilityInput = {
        functionId,
        processId: resolvedProcessId,
        name: name.trim(),
        description: description.trim(),
        owner: owner.trim() || undefined,
        tags: tags.split(",").map((tag) => tag.trim()).filter(Boolean),
        kpis: kpis.split("\n").map((kpi) => kpi.trim()).filter(Boolean),
      };
      if (target.mode === "edit" && target.capabilityId) controller.updateCatalogCapability(target.capabilityId, input);
      else controller.createCatalogCapability(input);
    }
    onClose();
  };

  const deleteEntity = () => {
    if (target.kind === "function" && target.functionId) controller.deleteFunction(target.functionId);
    if (target.kind === "process" && target.processId) controller.deleteProcess(target.processId);
    if (target.kind === "capability" && target.capabilityId) controller.deleteCatalogCapability(target.capabilityId);
    onClose();
  };

  return (
    <aside className={styles.detailPanel} aria-label={`${target.mode === "create" ? "Create" : "Edit"} ${entityLabel.toLowerCase()}`}>
      <div className={styles.panelHeader}>
        <span>{target.mode === "create" ? "New" : "Edit"} {entityLabel}</span>
        <IconButton label="Close catalog editor" onClick={onClose}><IconX size={16} /></IconButton>
      </div>
      <form className={styles.catalogForm} onSubmit={submit}>
        <div className={styles.catalogFormScroll}>
          <div className={styles.editorIntro}>
            <span className={styles.domainLabel}>CATALOG · {target.mode === "create" ? "NEW" : "MANAGED"}</span>
            <p>{target.kind === "function" ? "Functions group the work the enterprise must perform." : target.kind === "process" ? "Processes organise related capabilities within a function." : "Capabilities describe durable business abilities, independent of systems or teams."}</p>
          </div>
          {target.kind !== "function" ? (
            <label className={styles.formField}>
              <span>Business function</span>
              <select
                value={functionId}
                onChange={(event) => {
                  const nextFunctionId = event.target.value;
                  setFunctionId(nextFunctionId);
                  if (target.kind === "capability") setProcessId(controller.map.catalog.find((fn) => fn.id === nextFunctionId)?.processes[0]?.id ?? "");
                }}
              >
                {controller.map.catalog.map((fn) => <option key={fn.id} value={fn.id}>{fn.name}</option>)}
              </select>
            </label>
          ) : null}
          {target.kind === "function" ? (
            <label className={styles.formField}>
              <span>Organization unit</span>
              <select value={organizationUnitId} onChange={(event) => setOrganizationUnitId(event.target.value)}>
                {controller.map.organizationUnits.map((unit) => <option key={unit.id} value={unit.id}>{unit.label}</option>)}
              </select>
              <small>This function can also be moved between units directly on the organization map.</small>
            </label>
          ) : null}
          {target.kind === "capability" ? (
            <label className={styles.formField}>
              <span>Business process</span>
              <select value={processId || availableProcesses[0]?.id || ""} onChange={(event) => setProcessId(event.target.value)}>
                {availableProcesses.map((process) => <option key={process.id} value={process.id}>{process.name}</option>)}
              </select>
              {availableProcesses.length === 0 ? <small>Create a process in this function before adding capabilities.</small> : null}
            </label>
          ) : null}
          <label className={styles.formField}>
            <span>Name</span>
            <input value={name} onChange={(event) => setName(event.target.value)} autoFocus placeholder={`${entityLabel} name`} />
          </label>
          <label className={styles.formField}>
            <span>Description</span>
            <textarea value={description} onChange={(event) => setDescription(event.target.value)} rows={4} placeholder="Describe the business outcome and scope" />
          </label>
          {target.kind === "capability" ? (
            <>
              <label className={styles.formField}>
                <span>Accountable owner</span>
                <input value={owner} onChange={(event) => setOwner(event.target.value)} placeholder="Role or business unit" />
              </label>
              <label className={styles.formField}>
                <span>Tags</span>
                <input value={tags} onChange={(event) => setTags(event.target.value)} placeholder="strategy, risk, customer" />
                <small>Separate tags with commas.</small>
              </label>
              <label className={styles.formField}>
                <span>Suggested measures</span>
                <textarea value={kpis} onChange={(event) => setKpis(event.target.value)} rows={4} placeholder={"One KPI per line\nCycle time\nOutcome quality"} />
              </label>
            </>
          ) : null}
          {error ? <p className={styles.formError} role="alert">{error}</p> : null}
          {target.mode === "edit" ? (
            <section className={styles.dangerZone}>
              <h3>Danger zone</h3>
              {confirmDelete ? (
                <div>
                  <p>Delete this {target.kind}{destructiveCount ? ` and ${destructiveCount} ${destructiveCount === 1 ? "capability" : "capabilities"}` : ""}? Canvas placements are removed too.</p>
                  <span><button type="button" onClick={() => setConfirmDelete(false)}>Cancel</button><button type="button" onClick={deleteEntity}>Delete permanently</button></span>
                </div>
              ) : (
                <button type="button" onClick={() => setConfirmDelete(true)}><IconTrash size={14} /> Delete {target.kind}</button>
              )}
            </section>
          ) : null}
        </div>
        <div className={styles.catalogFormFooter}>
          <button type="button" onClick={onClose}>Cancel</button>
          <button type="submit">{target.mode === "create" ? `Create ${target.kind}` : "Save changes"}</button>
        </div>
      </form>
    </aside>
  );
}

export function BusinessMapWorkspace() {
  const controller = useBusinessMap();
  const [editing, setEditing] = useState(false);
  const [catalogEditor, setCatalogEditor] = useState<CatalogEditorTarget | null>(null);
  const [sharedGroupEditor, setSharedGroupEditor] = useState<SharedGroupEditorTarget | null>(null);
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor),
  );

  const handleDragEnd = (event: DragEndEvent) => {
    if (!editing) return;
    if (!event.over) return;
    const activeId = String(event.active.id);
    const overId = String(event.over.id);
    if (activeId.startsWith("function:") && overId.startsWith("org-unit:")) {
      controller.assignFunction(activeId.slice("function:".length), overId.slice("org-unit:".length));
      return;
    }
    if (controller.map.viewMode === "value-chain") controller.moveCapability(activeId, overId);
  };

  const openCatalogEditor = (target: CatalogEditorTarget) => {
    setSharedGroupEditor(null);
    setCatalogEditor(target);
  };

  const openSharedGroupEditor = (target: SharedGroupEditorTarget) => {
    setCatalogEditor(null);
    setSharedGroupEditor(target);
  };

  const changeEditing = (nextEditing: boolean) => {
    setEditing(nextEditing);
    if (!nextEditing) {
      setCatalogEditor(null);
      setSharedGroupEditor(null);
      controller.selectCapability(null);
    }
  };

  return (
    <div className={styles.workspace}>
      <Toolbar controller={controller} onNewSharedGroup={() => openSharedGroupEditor({ mode: "create" })} editing={editing} onEditingChange={changeEditing} />
      <DndContext sensors={sensors} onDragEnd={handleDragEnd}>
        <div className={styles.workspaceBody}>
          {editing && controller.libraryOpen ? <CapabilityLibrary controller={controller} onEdit={openCatalogEditor} /> : null}
          {controller.map.viewMode === "organization" ? (
            <OrganizationCanvas controller={controller} onEditFunction={openCatalogEditor} editing={editing} />
          ) : (
            <ValueChainCanvas controller={controller} onEditSharedGroup={(groupId) => openSharedGroupEditor({ mode: "edit", groupId })} editing={editing} />
          )}
          {editing && sharedGroupEditor ? (
            <SharedGroupEditorPanel
              key={`${sharedGroupEditor.mode}:${sharedGroupEditor.groupId ?? ""}`}
              controller={controller}
              target={sharedGroupEditor}
              onClose={() => setSharedGroupEditor(null)}
            />
          ) : editing && catalogEditor ? (
            <CatalogEditorPanel
              key={`${catalogEditor.kind}:${catalogEditor.mode}:${catalogEditor.functionId ?? ""}:${"processId" in catalogEditor ? catalogEditor.processId ?? "" : ""}:${"capabilityId" in catalogEditor ? catalogEditor.capabilityId ?? "" : ""}`}
              controller={controller}
              target={catalogEditor}
              onClose={() => setCatalogEditor(null)}
            />
          ) : controller.panel === "capability" ? (
            <CapabilityPanel controller={controller} onEdit={openCatalogEditor} editing={editing} />
          ) : null}
        </div>
      </DndContext>
    </div>
  );
}
