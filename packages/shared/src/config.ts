// Runtime data-source configuration. One flag flips the whole UI from fixtures to the live API
// with no component change (the Lane C promise). See docs/stackgraph-ux-architecture-and-plan.md §7.1.

export type DataSource = "fixtures" | "live";

function readEnv(key: string): string | undefined {
  // Works in both Next server (process.env) and injected NEXT_PUBLIC_* on the client.
  if (typeof process !== "undefined" && process.env) return process.env[key];
  return undefined;
}

export const config = {
  /** "fixtures" (default) serves contracts/v1 fixtures; "live" calls the real API. */
  dataSource: (readEnv("NEXT_PUBLIC_DATA_SOURCE") as DataSource) ?? "fixtures",
  /** Base URL of the live read API. Contract mounts read models under /api/v1. */
  apiBaseUrl: readEnv("NEXT_PUBLIC_API_BASE_URL") ?? "http://localhost:8080",
} as const;

export const isFixtureMode = () => config.dataSource === "fixtures";
