"use client";

import { useCallback, useMemo } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { DEFAULT_QUERY, LENSES, type EstateQuery } from "./estateFilters";

/** Reads/writes the estate filter state as URL query params — shareable and back-button-safe (plan §3.4). */
export function useEstateQuery(): {
  query: EstateQuery;
  setQuery: (patch: Partial<EstateQuery>) => void;
  applyLens: (lensKey: string) => void;
  reset: () => void;
} {
  const router = useRouter();
  const pathname = usePathname() ?? "/estate";
  const params = useSearchParams();

  const query = useMemo<EstateQuery>(
    () => ({
      domain: (params?.get("domain") as EstateQuery["domain"]) ?? DEFAULT_QUERY.domain,
      confidence: (params?.get("confidence") as EstateQuery["confidence"]) ?? DEFAULT_QUERY.confidence,
      freshness: (params?.get("freshness") as EstateQuery["freshness"]) ?? DEFAULT_QUERY.freshness,
      sort: (params?.get("sort") as EstateQuery["sort"]) ?? DEFAULT_QUERY.sort,
      dir: (params?.get("dir") as EstateQuery["dir"]) ?? DEFAULT_QUERY.dir,
      q: params?.get("q") ?? DEFAULT_QUERY.q,
      lens: params?.get("lens") ?? DEFAULT_QUERY.lens,
    }),
    [params],
  );

  const write = useCallback(
    (next: EstateQuery) => {
      const sp = new URLSearchParams();
      // Only serialize non-default values to keep URLs clean.
      if (next.domain !== DEFAULT_QUERY.domain) sp.set("domain", next.domain);
      if (next.confidence !== DEFAULT_QUERY.confidence) sp.set("confidence", next.confidence);
      if (next.freshness !== DEFAULT_QUERY.freshness) sp.set("freshness", next.freshness);
      if (next.sort !== DEFAULT_QUERY.sort) sp.set("sort", next.sort);
      if (next.dir !== DEFAULT_QUERY.dir) sp.set("dir", next.dir);
      if (next.q.trim()) sp.set("q", next.q);
      if (next.lens !== DEFAULT_QUERY.lens) sp.set("lens", next.lens);
      const qs = sp.toString();
      router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    },
    [router, pathname],
  );

  const setQuery = useCallback(
    (patch: Partial<EstateQuery>) => {
      const next = { ...query, ...patch };
      // A manual filter change diverges from any named lens.
      if (!("lens" in patch)) next.lens = "custom";
      write(next);
    },
    [query, write],
  );

  const applyLens = useCallback(
    (lensKey: string) => {
      const lens = LENSES[lensKey];
      if (!lens) return;
      write({ ...DEFAULT_QUERY, ...lens.apply, lens: lensKey });
    },
    [write],
  );

  const reset = useCallback(() => write(DEFAULT_QUERY), [write]);

  return { query, setQuery, applyLens, reset };
}
