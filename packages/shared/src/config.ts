/// <reference types="node" />

// Runtime data-source configuration. One flag flips the whole UI from fixtures to the live API
// with no component change (the Lane C promise). See docs/stackgraph-ux-architecture-and-plan.md §7.1.
//
// NOTE: these MUST be static `process.env.NEXT_PUBLIC_*` references. Next inlines only static
// member access on the client — a dynamic `process.env[key]` is NOT replaced and reads undefined
// in the browser.

export type DataSource = "fixtures" | "live";

export const config = {
  /** "live" (default) calls the API; set "fixtures" explicitly for an offline demo. */
  dataSource: (process.env.NEXT_PUBLIC_DATA_SOURCE as DataSource | undefined) ?? "live",
  /** Base URL of the live read API. Contract mounts read models under /api/v1. */
  apiBaseUrl: process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8080",
  /** Production login guard; API remains the source of truth for authorization. */
  authRequired: process.env.NEXT_PUBLIC_AUTH_REQUIRED === "true",
} as const;

export const isFixtureMode = () => config.dataSource === "fixtures";
