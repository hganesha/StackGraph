export { confidencePolicy, confidenceLabel, confidenceSegments, domainMeta, NAMESPACES } from "./tokens/tokens";
export { ThemeProvider, useTheme, themeInitScript } from "./theme/ThemeProvider";
export type { ThemeChoice } from "./theme/ThemeProvider";
export { DomainBadge } from "./components/DomainBadge";
export { DomainIcon, domainIcons } from "./components/DomainIcon";
export { ConfidenceChip } from "./components/ConfidenceChip";
export { StatTile } from "./components/StatTile";
export { StatusStrip } from "./components/StatusStrip";
export type { StatusStripProps } from "./components/StatusStrip";
export {
  RunProvenance,
  graphSnapshotProvenance,
  simulationRunProvenance,
} from "./components/RunProvenance";
export type { RunProvenanceFacts } from "./components/RunProvenance";
export { StratumBar } from "./components/StratumBar";
export type { StratumLayer, StratumLayerFact } from "./components/StratumBar";
export { AttenuationBar } from "./components/AttenuationBar";
export type { AttenuationStage, AttenuationBarProps } from "./components/AttenuationBar";
export { Sparkline } from "./components/Sparkline";
export type { SparklineProps } from "./components/Sparkline";
export { CorroborationMark } from "./components/CorroborationMark";
export type { CorroborationMarkProps } from "./components/CorroborationMark";
export { GateNotice } from "./components/GateNotice";
export type { GateNoticeProps } from "./components/GateNotice";
export { ResolutionLabel } from "./components/ResolutionLabel";
export type { ResolutionLabelProps } from "./components/ResolutionLabel";
export {
  IconAttenuation,
  IconBlast,
  IconSpread,
  IconStrata,
  IconDrift,
} from "./components/SignalGlyphs";
export type { SignalGlyphProps } from "./components/SignalGlyphs";

/* The blocking and identity axes. Kept out of the tonal vocabulary on purpose: a gate
   is not a louder tone, and resolution is not confidence. */
export {
  GATE_LABEL,
  GATE_DESCRIPTION,
  GATE_RENDERS,
} from "./vocabulary/gates";
export type { GateVerdict } from "./vocabulary/gates";
export {
  SIMULATION_STATUS_LABEL,
  SIMULATION_STATUS_IS_TERMINAL,
  INTERPRETATION_STATUS_LABEL,
  INTERPRETATION_STATUS_DESCRIPTION,
  CLASSIFICATION_LABEL,
  CLASSIFICATION_DESCRIPTION,
  PREDICATE_LABEL,
  COMMAND_STATE_LABEL,
  MUTATION_LIFECYCLE_LABEL,
  TARGET_SUPPORT_LABEL,
  TARGET_FRESHNESS_LABEL,
} from "./vocabulary/change";
export type {
  SimulationRunStatus,
  InterpretationStatus,
  ImpactClassification,
  ChangePredicate,
  CommandState,
  MutationLifecycle,
  TargetSupport,
  TargetFreshness,
} from "./vocabulary/change";
export {
  ESTATE_LEVEL_LABEL,
  ESTATE_LEVEL_DESCRIPTION,
  ESTATE_LEVEL_UNIT,
  formatScopeCount,
  formatComponentImpact,
  componentLabelParts,
  componentLabelText,
} from "./vocabulary/estate-level";
export type { EstateLevel, ComponentLabelParts } from "./vocabulary/estate-level";
export {
  RESOLUTION_LABEL,
  RESOLUTION_DESCRIPTION,
  RESOLUTION_TONE,
  RESOLUTION_BLOCKS,
} from "./vocabulary/resolution";
export type { ResolutionState } from "./vocabulary/resolution";
export { RankedTable } from "./components/RankedTable";
export { Skeleton } from "./components/Skeleton";
export { AssertionTag } from "./components/AssertionTag";
export { EvidenceRow } from "./components/EvidenceRow";
export { CitationChip } from "./components/CitationChip";
export { Drawer } from "./components/Drawer";
export { Term } from "./components/Term";
export { GLOSSARY } from "./glossary/terms";
export type { GlossaryKey, GlossaryEntry } from "./glossary/terms";
