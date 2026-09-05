"use client";

import { useCallback, useEffect, useState } from "react";
import type { EstateQuery } from "./estateFilters";

const STORAGE_KEY = "stackgraph.savedEstateViews.v1";
const MAX_VIEWS = 12;

export interface SavedView {
  id: string;
  name: string;
  query: EstateQuery;
  savedAt: string;
}

/**
 * Named filter stacks, kept in this browser.
 *
 * The estate query already serialises its whole state to the URL, so a saved view is a
 * name and a query string — nothing more. Analysts who live in the tool for hours
 * rebuild the same filter stack every morning, and the machinery to stop that has been
 * there the whole time (recommendations R10d).
 *
 * `localStorage` rather than the server, deliberately: a saved view is a per-person
 * convenience, not estate state, and it should not need a round trip, a migration, or
 * a contract. It is also the honest limit — this does not sync between devices, and
 * the panel says so rather than implying otherwise.
 */
function read(): SavedView[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(
      (entry): entry is SavedView =>
        typeof entry === "object" &&
        entry !== null &&
        typeof (entry as SavedView).id === "string" &&
        typeof (entry as SavedView).name === "string" &&
        typeof (entry as SavedView).query === "object",
    );
  } catch {
    // A private window, cleared site data, or a browser set to block storage. A saved
    // view is a convenience; losing it must never break the page it sits on.
    return [];
  }
}

function write(views: SavedView[]) {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(views));
  } catch {
    /* Storage is unavailable or full. The view stays in memory for this session. */
  }
}

export function useSavedViews() {
  const [views, setViews] = useState<SavedView[]>([]);

  // Read after mount: the server render has no localStorage, and rendering saved views
  // during hydration would mismatch.
  useEffect(() => setViews(read()), []);

  const save = useCallback((name: string, query: EstateQuery) => {
    const trimmed = name.trim();
    if (!trimmed) return;
    setViews((current) => {
      const next = [
        { id: `${Date.now()}-${trimmed}`, name: trimmed, query, savedAt: new Date().toISOString() },
        ...current.filter((view) => view.name !== trimmed),
      ].slice(0, MAX_VIEWS);
      write(next);
      return next;
    });
  }, []);

  const remove = useCallback((id: string) => {
    setViews((current) => {
      const next = current.filter((view) => view.id !== id);
      write(next);
      return next;
    });
  }, []);

  return { views, save, remove };
}
