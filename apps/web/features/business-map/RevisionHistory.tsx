"use client";

import { useQuery } from "@tanstack/react-query";
import { Skeleton } from "@stackgraph/design-system";
import { stackGraphClient } from "@stackgraph/shared";
import styles from "./revision-history.module.css";

/**
 * The saved history of a business map, which was being kept and never shown.
 *
 * `getBusinessMapRevisions` has had a client method and no call site since it shipped
 * (defect §7.12). The map has persisted server-side all along — the P3 claiming
 * otherwise was stale — so what was actually missing was the history, not the
 * persistence.
 *
 * It matters more now than it did: Phase 2 §22 raises capability mapping to a
 * simulation input, and a business map that decides what a change touches needs to be
 * able to answer "who changed this, and when".
 */
export function BusinessMapRevisionHistory({ mapId }: { mapId: string | null }) {
  const query = useQuery({
    queryKey: ["business-map", "revisions", mapId],
    queryFn: () => stackGraphClient.getBusinessMapRevisions(mapId as string),
    enabled: Boolean(mapId),
    staleTime: 60_000,
  });

  if (!mapId) {
    return (
      <p className={styles.quiet}>
        This map has not been saved to the workspace yet, so it has no history.
      </p>
    );
  }

  if (query.isLoading) return <Skeleton height={96} />;

  if (query.isError) {
    return (
      <p className={styles.quiet} role="alert">
        Revision history is temporarily unavailable. The map itself is unaffected.
      </p>
    );
  }

  const revisions = query.data?.revisions ?? [];
  if (!revisions.length) {
    return <p className={styles.quiet}>No revisions have been recorded yet.</p>;
  }

  return (
    <div className={styles.wrap}>
      <h3 className={styles.heading}>Saved revisions</h3>
      <ol className={styles.list}>
        {[...revisions]
          .sort((a, b) => b.version - a.version)
          .map((revision, index) => (
            <li key={revision.version}>
              <span className={`${styles.version} sg-mono`}>v{revision.version}</span>
              <span className={styles.actor}>{revision.actor_key}</span>
              <span className={styles.when}>
                {new Date(revision.created_at).toLocaleString(undefined, {
                  day: "numeric",
                  month: "short",
                  hour: "2-digit",
                  minute: "2-digit",
                })}
              </span>
              {index === 0 ? <span className={styles.current}>Current</span> : null}
            </li>
          ))}
      </ol>
    </div>
  );
}
