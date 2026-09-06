"use client";

import { useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import {
  IconAlertTriangle,
  IconApps,
  IconChevronDown,
  IconChevronRight,
  IconGitBranch,
  IconInbox,
  IconServer2,
  IconStack2,
} from "@tabler/icons-react";
import { DomainIcon, RankedTable, StatTile, Skeleton } from "@stackgraph/design-system";
import { namespaceLabel, type Namespace, type RankedItem } from "@stackgraph/shared";
import { useEstateSummary, useInfiniteEstateSummary } from "@/lib/queries";
import { useEstateQuery } from "@/lib/useEstateQuery";
import { SemanticMatches } from "@/components/estate/SemanticMatches";
import { applyEstateQuery } from "@/lib/estateFilters";
import { FilterBar } from "@/components/estate/FilterBar";
import { ArchitectureWorkspace } from "@/features/architecture/ArchitectureWorkspace";
import { CapabilityHeatGrid } from "@/features/estate/CapabilityHeatGrid";
import { Archetypes } from "@/features/intelligence/Archetypes";
import styles from "./estate.module.css";

const DOMAIN_ORDER: Namespace[] = [
  "BUSINESS",
  "ENTERPRISE",
  "TECHNOLOGY",
  "OSS",
  "DEPLOYMENT",
];
const PAGED_DOMAINS = DOMAIN_ORDER;

const hrefFor = (item: RankedItem) => {
  if (item.domain === "BUSINESS") return "/business-map";
  if (item.kind === "Service") {
    return item.parent_application_id
      ? `/applications/${item.parent_application_id}?tab=overview#services`
      : "/applications?view=services";
  }
  if (item.domain === "TECHNOLOGY" || item.domain === "OSS") return `/technologies/${item.id}`;
  return `/applications/${item.id}`;
};

function EstateDomainSection({
  domain,
  items,
  loadedCount,
  sort,
  hasMore,
  isLoadingMore,
  onLoadMore,
  onOpen,
}: {
  domain: Namespace;
  items: RankedItem[];
  loadedCount: number;
  sort: string;
  hasMore: boolean;
  isLoadingMore: boolean;
  onLoadMore: () => void;
  onOpen: (item: RankedItem) => void;
}) {
  const [open, setOpen] = useState(true);
  const contentId = `estate-domain-${domain.toLowerCase()}`;

  return (
    <section className={styles.domainGroup} aria-labelledby={`${contentId}-heading`}>
      <button
        type="button"
        id={`${contentId}-heading`}
        className={styles.domainDisclosure}
        aria-expanded={open}
        aria-controls={contentId}
        onClick={() => setOpen((value) => !value)}
      >
        {open ? (
          <IconChevronDown size={18} stroke={1.75} aria-hidden="true" />
        ) : (
          <IconChevronRight size={18} stroke={1.75} aria-hidden="true" />
        )}
        <span className={styles.domainGlyph}>
          <DomainIcon namespace={domain} size={16} />
        </span>
        <strong>{namespaceLabel(domain)}</strong>
        {/* One denominator per row. "3 of 50 match" beside "50 loaded" made a reader
            work out which 50 was which (defect §7.5). */}
        <span className={styles.domainCount}>
          {items.length === loadedCount
            ? `${loadedCount} loaded`
            : `${loadedCount} loaded · ${items.length} match your filters`}
        </span>
      </button>
      {open ? (
        <div id={contentId} className={styles.domainTable}>
          {items.length ? (
            <RankedTable
              caption={`${loadedCount} loaded · ${items.length} match your filters · sorted by ${sort}`}
              items={items}
              renderRowHref={hrefFor}
              onOpen={onOpen}
            />
          ) : (
            <p className={styles.domainEmpty}>
              <IconInbox size={20} stroke={1.5} aria-hidden="true" />
              {loadedCount === 0
                ? domain === "OSS"
                  ? "No linked OSS projects are represented yet. Open-source packages discovered in repositories appear under Technology; this section shows external project intelligence such as source repositories, releases, licenses, maintainers, and ecosystem health once linked."
                  : `No ${namespaceLabel(domain).toLowerCase()} items are currently represented in the estate.`
                : "No loaded items in this domain match the active lens or filters."}
            </p>
          )}
          {hasMore ? (
            <div className={styles.domainLoadMore}>
              <button
                type="button"
                className={styles.loadMore}
                disabled={isLoadingMore}
                onClick={onLoadMore}
              >
                {isLoadingMore ? "Loading…" : `Load 50 more ${namespaceLabel(domain)} items`}
              </button>
            </div>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

export function EstateView() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { query, setQuery, applyLens, reset } = useEstateQuery();
  const showAllDomains = query.domain === "ALL";
  const selectedDomain = query.domain as Namespace;
  const selectedOtherDomains = useMemo(
    () => !showAllDomains && !PAGED_DOMAINS.includes(selectedDomain) ? [selectedDomain] : [],
    [selectedDomain, showAllDomains],
  );
  const overview = useEstateSummary();
  const businessEstate = useInfiniteEstateSummary(["BUSINESS"], {
    enabled: showAllDomains || selectedDomain === "BUSINESS",
  });
  const enterpriseEstate = useInfiniteEstateSummary(["ENTERPRISE"], {
    enabled: showAllDomains || selectedDomain === "ENTERPRISE",
  });
  const technologyEstate = useInfiniteEstateSummary(["TECHNOLOGY"], {
    enabled: showAllDomains || selectedDomain === "TECHNOLOGY",
  });
  const ossEstate = useInfiniteEstateSummary(["OSS"], {
    enabled: showAllDomains || selectedDomain === "OSS",
  });
  const deploymentEstate = useInfiniteEstateSummary(["DEPLOYMENT"], {
    enabled: showAllDomains || selectedDomain === "DEPLOYMENT",
  });
  const otherEstate = useInfiniteEstateSummary(selectedOtherDomains, {
    enabled: selectedOtherDomains.length > 0,
  });
  const activeEstate = selectedDomain === "BUSINESS"
    ? businessEstate
    : selectedDomain === "ENTERPRISE"
      ? enterpriseEstate
      : selectedDomain === "TECHNOLOGY"
        ? technologyEstate
        : selectedDomain === "OSS"
          ? ossEstate
          : selectedDomain === "DEPLOYMENT"
            ? deploymentEstate
            : otherEstate;
  const activeDomainEstates = showAllDomains
    ? [businessEstate, enterpriseEstate, technologyEstate, ossEstate, deploymentEstate]
    : [activeEstate];
  const counts = overview.data?.counts;
  const isLoading = overview.isLoading || activeDomainEstates.some((estate) => estate.isLoading);
  const isError = overview.isError || activeDomainEstates.some((estate) => estate.isError);
  const loadedItems = useMemo(
    () => {
      const dataSets = showAllDomains
        ? [
            businessEstate.data,
            enterpriseEstate.data,
            technologyEstate.data,
            ossEstate.data,
            deploymentEstate.data,
          ]
        : [activeEstate.data];
      return dataSets.flatMap(
        (data) => data?.pages.flatMap((page) => page.ranked_items) ?? [],
      );
    },
    [
      activeEstate.data,
      businessEstate.data,
      deploymentEstate.data,
      enterpriseEstate.data,
      ossEstate.data,
      showAllDomains,
      technologyEstate.data,
    ],
  );
  const items = useMemo(() => applyEstateQuery(loadedItems, query), [loadedItems, query]);
  const domainGroups = useMemo(() => {
    const grouped = new Map<Namespace, RankedItem[]>();
    for (const item of loadedItems) {
      const group = grouped.get(item.domain) ?? [];
      group.push(item);
      grouped.set(item.domain, group);
    }
    return DOMAIN_ORDER.flatMap((domain) => {
      const group = grouped.get(domain) ?? [];
      return [{
        domain,
        loadedCount: group.length,
        items: applyEstateQuery(group, { ...query, domain: "ALL" }),
      }];
    });
  }, [loadedItems, query]);
  const estateForDomain = (domain: Namespace) => {
    if (domain === "BUSINESS") return businessEstate;
    if (domain === "ENTERPRISE") return enterpriseEstate;
    if (domain === "TECHNOLOGY") return technologyEstate;
    if (domain === "OSS") return ossEstate;
    if (domain === "DEPLOYMENT") return deploymentEstate;
    return otherEstate;
  };
  const hasMore = activeDomainEstates.some((estate) => estate.hasNextPage);
  // The canvas is a peer view of the same estate, not a filter on the ranked list, so
  // it reads its own URL param and leaves the filter query untouched.
  const viewParam = searchParams?.get("view");
  const estateView =
    viewParam === "canvas"
      ? "canvas"
      : viewParam === "heat"
        ? "heat"
        : viewParam === "archetypes"
          ? "archetypes"
          : "ranked";

  return (
    <div className={styles.page}>
      <header className={styles.head}>
        <h1 className={styles.title}>Your estate</h1>
        <p className={styles.subtitle}>
          Everything StackGraph found across your repositories — and what it means.
        </p>
        <nav className={styles.viewSwitch} aria-label="Estate view">
          {([
            ["ranked", "Ranked list", "/estate"],
            ["heat", "Heat grid", "/estate?view=heat"],
            ["archetypes", "Archetypes", "/estate?view=archetypes"],
            ["canvas", "Architecture canvas", "/estate?view=canvas"],
          ] as const).map(([id, label, href]) =>
            estateView === id ? (
              <span key={id} aria-current="page" className={styles.activeView}>
                {label}
              </span>
            ) : (
              <Link key={id} href={href}>
                {label}
              </Link>
            ),
          )}
        </nav>
      </header>

      {estateView === "canvas" ? (
        <ArchitectureWorkspace scope="ESTATE" variant="embedded" initialDensity="compact" />
      ) : estateView === "heat" ? (
        <CapabilityHeatGrid />
      ) : estateView === "archetypes" ? (
        <Archetypes />
      ) : (
        <>

      {isError ? (
        <div className={styles.notice} role="alert">
          <IconAlertTriangle size={18} stroke={1.5} aria-hidden="true" />
          <span>Couldn’t load the estate. Try again, or check the API connection.</span>
        </div>
      ) : null}

      <section className={styles.tiles} aria-label="Estate counts">
        {isLoading || !counts ? (
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
            <StatTile label="Applications" value={counts.applications} icon={IconApps} />
            <StatTile label="Repositories" value={counts.repositories} icon={IconGitBranch} />
            <StatTile label="Services" value={counts.services} icon={IconServer2} />
            <StatTile label="Technologies" value={counts.technologies} icon={IconStack2} />
          </>
        )}
      </section>

      {overview.data ? (
        <FilterBar
          query={query}
          setQuery={setQuery}
          applyLens={applyLens}
          reset={reset}
          resultCount={items.length}
          total={loadedItems.length}
          hasMore={hasMore}
          incremental
        />
      ) : null}

      {/* Exact matches stay above; retrieval is offered beside them, never instead. */}
      <SemanticMatches query={query.q} />

      <section className={styles.tableWrap} aria-label="Everything found">
        {isLoading || !overview.data ? (
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
        ) : showAllDomains ? (
          <div className={styles.domainGroups}>
            {domainGroups.map((group) => {
              const estate = estateForDomain(group.domain);
              return (
                <EstateDomainSection
                  key={group.domain}
                  domain={group.domain}
                  items={group.items}
                  loadedCount={group.loadedCount}
                  sort={query.sort}
                  hasMore={Boolean(estate.hasNextPage)}
                  isLoadingMore={estate.isFetchingNextPage}
                  onLoadMore={() => estate.fetchNextPage()}
                  onOpen={(item) => router.push(hrefFor(item))}
                />
              );
            })}
          </div>
        ) : (
          <EstateDomainSection
            domain={selectedDomain}
            items={items}
            loadedCount={loadedItems.length}
            sort={query.sort}
            hasMore={Boolean(activeEstate.hasNextPage)}
            isLoadingMore={activeEstate.isFetchingNextPage}
            onLoadMore={() => activeEstate.fetchNextPage()}
            onOpen={(item) => router.push(hrefFor(item))}
          />
        )}
      </section>
        </>
      )}
    </div>
  );
}
