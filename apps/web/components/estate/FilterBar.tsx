"use client";

import { useState } from "react";
import {
  IconArrowDown,
  IconArrowUp,
  IconBookmark,
  IconChevronDown,
  IconSearch,
  IconX,
} from "@tabler/icons-react";
import { LENSES, activeFilterCount, type EstateQuery } from "@/lib/estateFilters";
import { useSavedViews } from "@/lib/useSavedViews";
import styles from "./FilterBar.module.css";

interface Props {
  query: EstateQuery;
  setQuery: (patch: Partial<EstateQuery>) => void;
  applyLens: (lensKey: string) => void;
  reset: () => void;
  resultCount: number;
  total: number;
  hasMore?: boolean;
  incremental?: boolean;
  /** Hide the domain control when the surface is already domain-scoped (list pages). */
  showDomain?: boolean;
}

export function FilterBar({ query, setQuery, applyLens, reset, resultCount, total, hasMore = false, incremental = false, showDomain = true }: Props) {
  const active = activeFilterCount(query);
  const savedViews = useSavedViews();
  const [naming, setNaming] = useState(false);
  const [draftName, setDraftName] = useState("");

  return (
    <div className={styles.bar}>
      <div className={styles.scroller}>
        <label className={styles.searchField}>
          <span className={styles.srOnly}>Filter by name</span>
          <IconSearch className={styles.searchIcon} size={16} stroke={1.75} aria-hidden="true" />
          <input
            className={styles.input}
            type="search"
            value={query.q}
            placeholder="Filter by name…"
            onChange={(e) => setQuery({ q: e.target.value })}
          />
        </label>

        <label className={`${styles.control} ${styles.lensControl}`}>
          <span className={styles.label}>Lens</span>
          <span className={styles.selectWrap}>
            <select
              className={styles.select}
              value={query.lens in LENSES ? query.lens : "custom"}
              onChange={(e) => applyLens(e.target.value)}
            >
              {Object.entries(LENSES).map(([key, l]) => (
                <option key={key} value={key}>
                  {l.label}
                </option>
              ))}
              <option value="custom" disabled>
                Custom
              </option>
            </select>
            <IconChevronDown className={styles.chevron} size={14} stroke={1.75} aria-hidden="true" />
          </span>
        </label>

        {showDomain ? (
          <label className={`${styles.control} ${styles.domainControl}`}>
            <span className={styles.label}>Domain</span>
            <span className={styles.selectWrap}>
              <select className={styles.select} value={query.domain} onChange={(e) => setQuery({ domain: e.target.value as EstateQuery["domain"] })}>
                <option value="ALL">All domains</option>
                <option value="BUSINESS">Business</option>
                <option value="ENTERPRISE">Enterprise</option>
                <option value="TECHNOLOGY">Technology</option>
                <option value="OSS">OSS</option>
                <option value="DEPLOYMENT">Deployment</option>
              </select>
              <IconChevronDown className={styles.chevron} size={14} stroke={1.75} aria-hidden="true" />
            </span>
          </label>
        ) : null}

        <label className={`${styles.control} ${styles.confidenceControl}`}>
          <span className={styles.label}>Confidence</span>
          <span className={styles.selectWrap}>
            <select className={styles.select} value={query.confidence} onChange={(e) => setQuery({ confidence: e.target.value as EstateQuery["confidence"] })}>
              <option value="ALL">Any</option>
              <option value="HIGH">High</option>
              <option value="MEDIUM">Medium</option>
              <option value="LOW">Low</option>
            </select>
            <IconChevronDown className={styles.chevron} size={14} stroke={1.75} aria-hidden="true" />
          </span>
        </label>

        <label className={`${styles.control} ${styles.freshnessControl}`}>
          <span className={styles.label}>Freshness</span>
          <span className={styles.selectWrap}>
            <select className={styles.select} value={query.freshness} onChange={(e) => setQuery({ freshness: e.target.value as EstateQuery["freshness"] })}>
              <option value="ALL">Any</option>
              <option value="FRESH">Fresh</option>
              <option value="STALE">Stale</option>
              <option value="UNKNOWN">Unknown</option>
            </select>
            <IconChevronDown className={styles.chevron} size={14} stroke={1.75} aria-hidden="true" />
          </span>
        </label>

        <div className={styles.sortGroup}>
          <label className={`${styles.control} ${styles.sortControl}`}>
            <span className={styles.label}>Sort</span>
            <span className={styles.selectWrap}>
              <select className={styles.select} value={query.sort} onChange={(e) => setQuery({ sort: e.target.value as EstateQuery["sort"] })}>
                <option value="priority">Priority</option>
                <option value="viability">Viability</option>
                <option value="name">Name</option>
              </select>
              <IconChevronDown className={styles.chevron} size={14} stroke={1.75} aria-hidden="true" />
            </span>
          </label>
          <button
            type="button"
            className={styles.dir}
            onClick={() => setQuery({ dir: query.dir === "desc" ? "asc" : "desc" })}
            aria-label={`Sort ${query.dir === "desc" ? "descending" : "ascending"}`}
            title={`Sort ${query.dir === "desc" ? "descending" : "ascending"}`}
          >
            {query.dir === "desc" ? (
              <IconArrowDown size={16} stroke={1.75} aria-hidden="true" />
            ) : (
              <IconArrowUp size={16} stroke={1.75} aria-hidden="true" />
            )}
          </button>
        </div>

        <div className={styles.summary}>
          <span className={`${styles.count} sg-mono`}>
            {incremental
              ? `${total} loaded${resultCount === total ? "" : ` · ${resultCount} match your filters`}${hasMore ? " · more available" : ""}`
              : `${total} loaded · ${resultCount} match your filters`}
          </span>
          {active > 0 ? (
            <button type="button" className={styles.clear} onClick={reset}>
              Clear {active} filter{active > 1 ? "s" : ""}
            </button>
          ) : null}
        </div>
      </div>

      {/* Saved views (R10d). The query already serialises itself to the URL, so this is
          a name and a query object — kept in this browser, never on the server. */}
      <div className={styles.savedViews}>
        {savedViews.views.map((view) => (
          <span key={view.id} className={styles.savedView}>
            <button
              type="button"
              className={styles.savedViewApply}
              onClick={() => setQuery(view.query)}
              title={`Apply ${view.name}`}
            >
              <IconBookmark size={13} stroke={1.75} aria-hidden="true" />
              {view.name}
            </button>
            <button
              type="button"
              className={styles.savedViewRemove}
              onClick={() => savedViews.remove(view.id)}
              aria-label={`Forget the saved view ${view.name}`}
              title={`Forget ${view.name}`}
            >
              <IconX size={12} stroke={1.75} aria-hidden="true" />
            </button>
          </span>
        ))}

        {naming ? (
          <form
            className={styles.saveForm}
            onSubmit={(event) => {
              event.preventDefault();
              savedViews.save(draftName, query);
              setDraftName("");
              setNaming(false);
            }}
          >
            <label className={styles.srOnly} htmlFor="saved-view-name">
              Name this view
            </label>
            <input
              id="saved-view-name"
              className={styles.saveInput}
              value={draftName}
              autoFocus
              placeholder="Name this view…"
              onChange={(event) => setDraftName(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Escape") setNaming(false);
              }}
            />
            <button type="submit" className={styles.saveConfirm} disabled={!draftName.trim()}>
              Save
            </button>
            <button type="button" className={styles.saveCancel} onClick={() => setNaming(false)}>
              Cancel
            </button>
          </form>
        ) : (
          <button type="button" className={styles.saveTrigger} onClick={() => setNaming(true)}>
            <IconBookmark size={13} stroke={1.75} aria-hidden="true" />
            Save this view
          </button>
        )}
        {savedViews.views.length ? (
          <span className={styles.savedViewNote}>Saved in this browser only</span>
        ) : null}
      </div>
    </div>
  );
}
