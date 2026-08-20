"use client";

import { useRouter } from "next/navigation";
import { RankedTable, StatTile, Skeleton } from "@stackgraph/design-system";
import { useModernization } from "@/lib/queries";
import styles from "./modernization.module.css";

export default function ModernizationPage() {
  const router = useRouter();
  const { data, isLoading } = useModernization();

  return (
    <div className={styles.page}>
      <header className={styles.head}>
        <h1 className={styles.title}>Modernization</h1>
        <p className={styles.subtitle}>What to do, in what order — ranked by opportunity, not by noise.</p>
      </header>

      <aside className={styles.investigative} aria-label="Pilot recommendation status">
        <strong>Investigative during the pilot.</strong> Rankings support review and discovery; they do not
        become governed recommendations until tenant policy and calibration are approved.
      </aside>

      <section className={styles.hero} aria-label="Portfolio metrics">
        {isLoading || !data ? (
          <div className={styles.heroSkeleton}>
            <Skeleton height={12} width={140} />
            <Skeleton height={40} width={80} />
          </div>
        ) : (
          <StatTile label="Open opportunities" value={data.opportunities.length} hero sub="ranked by priority" />
        )}
      </section>

      <section aria-label="Opportunities">
        {isLoading || !data ? (
          <div className={styles.tableSkeleton}>
            {[0, 1, 2].map((i) => (
              <Skeleton key={i} height={40} />
            ))}
          </div>
        ) : data.opportunities.length === 0 ? (
          <div className={styles.empty}>
            <p className={styles.emptyTitle}>No modernization opportunities surfaced yet.</p>
            <p className={styles.emptyBody}>
              Opportunities appear as assessments run across the estate — unsupported runtimes, deprecated
              packages, and consolidation candidates rank here first.
            </p>
          </div>
        ) : (
          <RankedTable
            caption="Ranked modernization opportunities"
            items={data.opportunities}
            renderRowHref={(item) => `/technologies/${item.id}`}
            onOpen={(item) => router.push(`/technologies/${item.id}`)}
          />
        )}
      </section>
    </div>
  );
}
