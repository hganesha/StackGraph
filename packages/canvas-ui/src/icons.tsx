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
const REGISTRY: Record<string, TablerIcon> = {
  activity: IconActivityHeartbeat,
  alert: IconAlertTriangle,
  api: IconApi,
  archive: IconArchive,
  "arrow-out": IconArrowUpRight,
  bolt: IconBolt,
  box: IconBox,
  "building-warehouse": IconBuildingWarehouse,
  "clock-cog": IconClockCog,
  cloud: IconCloud,
  "cloud-cog": IconCloudCog,
  container: IconBrandDocker,
  contract: IconLink,
  cpu: IconCpu,
  database: IconDatabase,
  "database-cog": IconDatabaseCog,
  "database-share": IconDatabaseShare,
  devices: IconDevices,
  "file-code": IconFileCode,
  form: IconForms,
  framework: IconWindow,
  gateway: IconTopologyStar3,
  key: IconKey,
  logic: IconBinaryTree,
  network: IconNetwork,
  "network-share": IconShare,
  orchestration: IconHierarchy2,
  package: IconPackage,
  palette: IconPalette,
  pipeline: IconGitBranch,
  queue: IconStack2,
  rocket: IconRocket,
  route: IconRoute,
  search: IconSearch,
  server: IconServer2,
  sitemap: IconSitemap,
  state: IconLayoutGrid,
  stream: IconTransfer,
  terminal: IconTerminal2,
  test: IconTestPipe,
  transfer: IconTransfer,
  "ui-rendering": IconWindow,
  waveform: IconWaveSine,
};

const FALLBACK = IconBox;

export function isKnownIconKey(key: string): boolean {
  return key in REGISTRY;
}

export function unknownIconKeys(keys: string[]): string[] {
  return [...new Set(keys.filter((key) => !isKnownIconKey(key)))];
}

export function CellIcon({ name, size = 16 }: { name: string; size?: number }) {
  const Component = REGISTRY[name] ?? FALLBACK;
  // Decorative: the cell's accessible name comes from its heading, never the glyph.
  return <Component size={size} stroke={1.6} aria-hidden="true" />;
}
