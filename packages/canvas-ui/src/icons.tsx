"use client";

import type { Icon as TablerIcon } from "@tabler/icons-react";
import {
  IconActivityHeartbeat, IconAlertTriangle, IconApi, IconArchive, IconArrowUpRight,
  IconBinaryTree, IconBolt, IconBox, IconBrandDocker, IconBuildingWarehouse, IconClockCog,
  IconCloud, IconCloudCog, IconCpu, IconDatabase, IconDatabaseCog, IconDatabaseShare,
  IconDevices, IconFileCode, IconForms, IconGitBranch, IconHierarchy2, IconKey,
  IconLayoutGrid, IconLink, IconNetwork, IconPackage, IconPalette, IconRocket, IconRoute,
  IconSearch, IconServer2, IconShare, IconSitemap, IconStack2, IconTerminal2,
  IconTestPipe, IconTopologyStar3, IconTransfer, IconWaveSine, IconWindow,
} from "@tabler/icons-react";

/**
 * Semantic icon registry (spec §5.2: "Icons are semantic registry keys validated by
 * the UI package"). Reference models ship keys, never component names or colours.
 * An unknown key resolves to the neutral fallback and is reported by
 * `unknownIconKeys` so a template can be corrected rather than silently degraded.
 */
/**
 * Keyed by concern leaf (the last segment of a concern key), because that is the
 * stable semantic handle the reference model publishes. Cells carry no icon on the
 * wire: presentation choices do not cross the API boundary (spec §5.2).
 *
 * Several leaves repeat across domains — `runtime` and `orchestration` each appear
 * twice — so keys are qualified where the domain changes the meaning.
 */
const REGISTRY: Record<string, TablerIcon> = {
  // experience
  ui: IconWindow,
  web: IconWindow,
  state: IconLayoutGrid,
  input: IconForms,
  design: IconPalette,
  channels: IconDevices,
  // application
  service: IconApi,
  logic: IconBinaryTree,
  persistence: IconDatabaseCog,
  outbound: IconArrowUpRight,
  background: IconClockCog,
  workflow: IconHierarchy2,
  "application.runtime": IconBox,
  // integration
  edge: IconTopologyStar3,
  contract: IconLink,
  connectivity: IconNetwork,
  messaging: IconStack2,
  events: IconTransfer,
  "stream-processing": IconWaveSine,
  "integration.orchestration": IconSitemap,
  "identity-access": IconKey,
  // data
  database: IconDatabase,
  "cache-session": IconBolt,
  search: IconSearch,
  "object-storage": IconArchive,
  analytics: IconBuildingWarehouse,
  processing: IconCpu,
  movement: IconTransfer,
  // platform
  "platform.runtime": IconTerminal2,
  artifact: IconBrandDocker,
  compute: IconServer2,
  "platform.orchestration": IconHierarchy2,
  serverless: IconCloudCog,
  network: IconShare,
  provider: IconCloud,
  // delivery
  build: IconPackage,
  test: IconTestPipe,
  cicd: IconGitBranch,
  iac: IconFileCode,
  configuration: IconKey,
  release: IconRocket,
  observability: IconActivityHeartbeat,
  reliability: IconAlertTriangle,
};

const FALLBACK = IconBox;

/**
 * Resolution tries the domain-qualified key first, so `runtime` under platform and
 * under application can differ, then falls back to the bare leaf.
 */
function resolve(key: string, domainKey?: string): TablerIcon | undefined {
  if (domainKey && REGISTRY[`${domainKey}.${key}`]) return REGISTRY[`${domainKey}.${key}`];
  return REGISTRY[key];
}

export function isKnownIconKey(key: string, domainKey?: string): boolean {
  return Boolean(resolve(key, domainKey));
}

export function unknownIconKeys(keys: string[]): string[] {
  return [...new Set(keys.filter((key) => !isKnownIconKey(key)))];
}

export function CellIcon({
  name,
  domainKey,
  size = 16,
}: {
  name: string;
  domainKey?: string;
  size?: number;
}) {
  const Component = resolve(name, domainKey) ?? FALLBACK;
  // Decorative: the cell's accessible name comes from its heading, never the glyph.
  return <Component size={size} stroke={1.6} aria-hidden="true" />;
}
