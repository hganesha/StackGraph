import type { RankedItem } from "@stackgraph/shared";

export type DomainFilter = "ALL" | "BUSINESS" | "ENTERPRISE" | "TECHNOLOGY" | "OSS" | "DEPLOYMENT" | "INTELLIGENCE";
export type ConfidenceFilter = "ALL" | "HIGH" | "MEDIUM" | "LOW";
export type FreshnessFilter = "ALL" | "FRESH" | "STALE" | "UNKNOWN";
export type SortKey = "priority" | "viability" | "name";
export type SortDir = "desc" | "asc";

export interface EstateQuery {
  domain: DomainFilter;
  confidence: ConfidenceFilter;
  freshness: FreshnessFilter;
  sort: SortKey;
  dir: SortDir;
  q: string;
  lens: string;
}

export const DEFAULT_QUERY: EstateQuery = {
  domain: "ALL",
  confidence: "ALL",
  freshness: "ALL",
  sort: "priority",
  dir: "desc",
  q: "",
  lens: "all",
};

/** Persona lenses: named bundles of filter + sort (plan §4.4). */
export const LENSES: Record<string, { label: string; apply: Partial<EstateQuery> }> = {
  all: { label: "All items", apply: { domain: "ALL", confidence: "ALL", freshness: "ALL", sort: "priority", dir: "desc" } },
  cto: { label: "CTO overview", apply: { domain: "ENTERPRISE", confidence: "ALL", freshness: "ALL", sort: "priority", dir: "desc" } },
  ea: { label: "EA standardization", apply: { domain: "TECHNOLOGY", confidence: "ALL", freshness: "ALL", sort: "viability", dir: "asc" } },
  risk: { label: "CISO risk", apply: { domain: "ALL", confidence: "ALL", freshness: "STALE", sort: "priority", dir: "desc" } },
  platform: { label: "Platform drift", apply: { domain: "ENTERPRISE", confidence: "ALL", freshness: "STALE", sort: "viability", dir: "asc" } },
};

function matchesConfidence(item: RankedItem, f: ConfidenceFilter): boolean {
  return f === "ALL" || item.priority.confidence_label === f;
}

export function applyEstateQuery(items: RankedItem[], q: EstateQuery): RankedItem[] {
  const needle = q.q.trim().toLowerCase();
  const filtered = items.filter((item) => {
    if (q.domain !== "ALL" && item.domain !== q.domain) return false;
    if (!matchesConfidence(item, q.confidence)) return false;
    if (q.freshness !== "ALL" && item.freshness.status !== q.freshness) return false;
    if (needle && !item.name.toLowerCase().includes(needle) && !(item.summary ?? "").toLowerCase().includes(needle))
      return false;
    return true;
  });

  const sorted = [...filtered].sort((a, b) => {
    let cmp = 0;
    if (q.sort === "name") cmp = a.name.localeCompare(b.name);
    else if (q.sort === "viability") {
      if (!a.viability && !b.viability) cmp = 0;
      else if (!a.viability) return 1;
      else if (!b.viability) return -1;
      else cmp = a.viability.value - b.viability.value;
    }
    else cmp = a.priority.value - b.priority.value;
    return q.dir === "asc" ? cmp : -cmp;
  });
  return sorted;
}

/** How many filters are active (for the "clear" affordance). */
export function activeFilterCount(q: EstateQuery): number {
  let n = 0;
  if (q.domain !== "ALL") n++;
  if (q.confidence !== "ALL") n++;
  if (q.freshness !== "ALL") n++;
  if (q.q.trim()) n++;
  return n;
}
