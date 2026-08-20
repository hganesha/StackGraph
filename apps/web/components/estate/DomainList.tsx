"use client";

import { useMemo } from "react";
import { useRouter } from "next/navigation";
import { RankedTable, Skeleton } from "@stackgraph/design-system";
import type { Namespace } from "@stackgraph/shared";
import { useEstateDomainSummary } from "@/lib/queries";
import { useEstateQuery } from "@/lib/useEstateQuery";
import { applyEstateQuery } from "@/lib/estateFilters";
import { FilterBar } from "./FilterBar";
import styles from "./DomainList.module.css";

/** Domain-scoped list surface (Applications, Technologies). Reuses the estate ranked items,
 *  pre-filtered to the given namespaces, then the shared filter/sort/lens system on top. */
export function DomainList({
  title,
  subtitle,
  domains,
  hrefBase,
  emptyTitle = "No matching items.",
  emptyBody,
}: {
  title: string;
  subtitle: string;
  domains: Namespace[];
  hrefBase: string;
  emptyTitle?: string;
  emptyBody?: string;
}) {
  const router = useRouter();
  const { data, isLoading } = useEstateDomainSummary(domains);
  const { query, setQuery, applyLens, reset } = useEstateQuery();

  const scoped = useMemo(
    () => (data ? data.ranked_items.filter((i) => domains.includes(i.domain)) : []),
    [data, domains],
  );
  const items = useMemo(
    () => applyEstateQuery(scoped, { ...query, domain: "ALL" }),
    [scoped, query],
  );

  return (
    <div className={styles.page}>
      <header className={styles.head}>
        <h1 className={styles.title}>{title}</h1>
        <p className={styles.subtitle}>{subtitle}</p>
      </header>

      {data ? (
        <FilterBar
          query={query}
          setQuery={setQuery}
          applyLens={applyLens}
          reset={reset}
          resultCount={items.length}
          total={scoped.length}
          showDomain={false}
        />
      ) : null}

      {isLoading || !data ? (
        <div className={styles.skeleton}>
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} height={44} />
          ))}
        </div>
      ) : items.length === 0 ? (
        <div className={styles.empty}>
          <p className={styles.emptyTitle}>{scoped.length === 0 ? emptyTitle : "No matching items."}</p>
          {scoped.length === 0 && emptyBody ? (
            <p className={styles.emptyNote}>{emptyBody}</p>
          ) : (
            <button type="button" className={styles.emptyBody} onClick={reset}>Clear filters.</button>
          )}
        </div>
      ) : (
        <RankedTable
          caption={`${items.length} items · sorted by ${query.sort}`}
          items={items}
          renderRowHref={(item) => `${hrefBase}/${item.id}`}
          onOpen={(item) => router.push(`${hrefBase}/${item.id}`)}
        />
      )}
    </div>
  );
}
