"use client";

import { useMemo } from "react";
import { useRouter } from "next/navigation";
import { RankedTable, StatTile, Skeleton } from "@stackgraph/design-system";
import { useEstateSummary } from "@/lib/queries";
import { useEstateQuery } from "@/lib/useEstateQuery";
import { applyEstateQuery } from "@/lib/estateFilters";
import { FilterBar } from "@/components/estate/FilterBar";
import styles from "./estate.module.css";

export function EstateView() {
  const router = useRouter();
  const { data, isLoading, isError } = useEstateSummary();
  const { query, setQuery, applyLens, reset } = useEstateQuery();

  // Route to the explorer that matches the item's domain (plan §5.1).
  const hrefFor = (domain: string, id: string) =>
    domain === "TECHNOLOGY" || domain === "OSS" ? `/technologies/${id}` : `/applications/${id}`;

  const items = useMemo(() => (data ? applyEstateQuery(data.ranked_items, query) : []), [data, query]);

  return (
    <div className={styles.page}>
      <header className={styles.head}>
        <h1 className={styles.title}>Software Estate</h1>
        <p className={styles.subtitle}>
          Your portfolio, ranked by priority. Scan first — evidence is one click beneath every number.
        </p>
      </header>

      {isError ? (
        <div className={styles.notice} role="alert">
          Couldn’t load the estate summary. Retry, or check the API connection.
        </div>
      ) : null}

      <section className={styles.tiles} aria-label="Estate counts">
        {isLoading || !data ? (
          <>
            {[0, 1, 2, 3].map((i) => (
              <div key={i} className={styles.tileSkeleton}>
                <Skeleton height={12} width="40%" />
                <Skeleton height={24} width="55%" />
              </div>
            ))}
          </>
        ) : (
          <>
            <StatTile label="Applications" value={data.counts.applications} />
            <StatTile label="Repositories" value={data.counts.repositories} />
            <StatTile label="Services" value={data.counts.services} />
            <StatTile label="Technologies" value={data.counts.technologies} />
          </>
        )}
      </section>

      {data ? (
        <FilterBar
          query={query}
          setQuery={setQuery}
          applyLens={applyLens}
          reset={reset}
          resultCount={items.length}
          total={data.ranked_items.length}
        />
      ) : null}

      <section className={styles.tableWrap} aria-label="Ranked items">
        {isLoading || !data ? (
          <div className={styles.tableSkeleton}>
            {[0, 1, 2, 3, 4].map((i) => (
              <div key={i} className={styles.rowSkeleton}>
                <Skeleton height={20} width={44} radius="999px" />
                <Skeleton height={16} width="45%" />
                <Skeleton height={16} width={120} />
                <Skeleton height={20} width={32} />
              </div>
            ))}
          </div>
        ) : data.ranked_items.length === 0 ? (
          <div className={styles.empty}>
            <p className={styles.emptyTitle}>No applications scanned yet.</p>
            <p className={styles.emptyBody}>Connect a GitHub org to begin. Results appear as coverage grows.</p>
          </div>
        ) : items.length === 0 ? (
          <div className={styles.empty}>
            <p className={styles.emptyTitle}>No items match these filters.</p>
            <button type="button" className={styles.emptyBody} onClick={reset}>
              Clear filters to see all {data.ranked_items.length} items.
            </button>
          </div>
        ) : (
          <RankedTable
            caption={`${items.length} items · sorted by ${query.sort}`}
            items={items}
            renderRowHref={(item) => hrefFor(item.domain, item.id)}
            onOpen={(item) => router.push(hrefFor(item.domain, item.id))}
          />
        )}
      </section>
    </div>
  );
}
