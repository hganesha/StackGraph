"use client";

import { LENSES, activeFilterCount, type EstateQuery } from "@/lib/estateFilters";
import styles from "./FilterBar.module.css";

interface Props {
  query: EstateQuery;
  setQuery: (patch: Partial<EstateQuery>) => void;
  applyLens: (lensKey: string) => void;
  reset: () => void;
  resultCount: number;
  total: number;
  /** Hide the domain control when the surface is already domain-scoped (list pages). */
  showDomain?: boolean;
}

export function FilterBar({ query, setQuery, applyLens, reset, resultCount, total, showDomain = true }: Props) {
  const active = activeFilterCount(query);

  return (
    <div className={styles.bar}>
      <div className={styles.row}>
        <label className={styles.field}>
          <span className={styles.label}>Lens</span>
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
        </label>

        <label className={`${styles.field} ${styles.grow}`}>
          <span className={styles.label}>Search</span>
          <input
            className={styles.input}
            type="search"
            value={query.q}
            placeholder="Filter by name…"
            onChange={(e) => setQuery({ q: e.target.value })}
          />
        </label>

        <label className={styles.field}>
          <span className={styles.label}>Sort</span>
          <select className={styles.select} value={query.sort} onChange={(e) => setQuery({ sort: e.target.value as EstateQuery["sort"] })}>
            <option value="priority">Priority</option>
            <option value="viability">Viability</option>
            <option value="name">Name</option>
          </select>
        </label>
        <button
          type="button"
          className={styles.dir}
          onClick={() => setQuery({ dir: query.dir === "desc" ? "asc" : "desc" })}
          aria-label={`Sort ${query.dir === "desc" ? "descending" : "ascending"}`}
          title={`Sort ${query.dir === "desc" ? "descending" : "ascending"}`}
        >
          {query.dir === "desc" ? "↓" : "↑"}
        </button>
      </div>

      <div className={styles.row}>
        {showDomain ? (
          <label className={styles.field}>
            <span className={styles.label}>Domain</span>
            <select className={styles.select} value={query.domain} onChange={(e) => setQuery({ domain: e.target.value as EstateQuery["domain"] })}>
              <option value="ALL">All domains</option>
              <option value="BUSINESS">Business</option>
              <option value="ENTERPRISE">Enterprise</option>
              <option value="TECHNOLOGY">Technology</option>
              <option value="OSS">OSS</option>
              <option value="DEPLOYMENT">Deployment</option>
            </select>
          </label>
        ) : null}

        <label className={styles.field}>
          <span className={styles.label}>Confidence</span>
          <select className={styles.select} value={query.confidence} onChange={(e) => setQuery({ confidence: e.target.value as EstateQuery["confidence"] })}>
            <option value="ALL">Any</option>
            <option value="HIGH">High</option>
            <option value="MEDIUM">Medium</option>
            <option value="LOW">Low</option>
          </select>
        </label>

        <label className={styles.field}>
          <span className={styles.label}>Freshness</span>
          <select className={styles.select} value={query.freshness} onChange={(e) => setQuery({ freshness: e.target.value as EstateQuery["freshness"] })}>
            <option value="ALL">Any</option>
            <option value="FRESH">Fresh</option>
            <option value="STALE">Stale</option>
            <option value="UNKNOWN">Unknown</option>
          </select>
        </label>

        <div className={styles.summary}>
          <span className={`${styles.count} sg-mono`}>
            {resultCount} of {total}
          </span>
          {active > 0 ? (
            <button type="button" className={styles.clear} onClick={reset}>
              Clear {active} filter{active > 1 ? "s" : ""}
            </button>
          ) : null}
        </div>
      </div>
    </div>
  );
}
