"use client";

import { useMemo } from "react";
import { CitationChip, ConfidenceChip, Skeleton, componentLabelParts } from "@stackgraph/design-system";
import { confidenceLabel } from "@stackgraph/design-system";
import type { RepositoryFingerprintSnapshot } from "@stackgraph/shared";
import { useRepositoryFingerprints } from "@/lib/changeQueries";
import { useEvidenceStore } from "@/lib/evidenceStore";
import styles from "./repository-fingerprint.module.css";

/**
 * How this repository is built, packaged, deployed and changed — in one reading.
 *
 * `scanner-improvements.md` sets out the fingerprint in full and then says, as an
 * aside, *"that's an extremely compelling 'repo page' too."* This is that page. It is
 * the highest-density screen in either plan and the natural home for classification,
 * components, frameworks, containers and deployment profiles at once.
 *
 * Two things the endpoint gives that nothing else in the product has. `fact_id` means
 * every snapshot links to evidence, which is what the plan asked for. And
 * `system_from`/`system_to` make it **bitemporal**, so this is the first surface that
 * can show a repository as it was at a point in time rather than only as it is —
 * the natural answer to "what changed about this repo since last quarter".
 *
 * `profile` is an untyped `object` on the contract, so only primitive and string-array
 * entries are rendered, and unknown keys are shown by name rather than dropped. A UI
 * that reaches blindly into an untyped payload is what `read-models.ts` exists to
 * prevent; a UI that silently hides fields the scanner produced is no better.
 */
type ProfileEntry = { key: string; label: string; values: string[] };

function readProfile(profile: unknown): ProfileEntry[] {
  if (!profile || typeof profile !== "object") return [];
  return Object.entries(profile as Record<string, unknown>)
    .map(([key, value]) => {
      const label = key.replaceAll("_", " ").replace(/^./, (c) => c.toUpperCase());
      if (Array.isArray(value)) {
        const values = value.filter((v): v is string => typeof v === "string");
        return values.length ? { key, label, values } : null;
      }
      if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
        return { key, label, values: [String(value)] };
      }
      return null;
    })
    .filter((entry): entry is ProfileEntry => entry !== null);
}

function SnapshotBlock({
  snapshot,
  repositoryName,
  current,
}: {
  snapshot: RepositoryFingerprintSnapshot;
  repositoryName?: string;
  current: boolean;
}) {
  const openEvidence = useEvidenceStore((state) => state.open);
  const entries = useMemo(() => readProfile(snapshot.profile), [snapshot.profile]);
  const components = entries.find((entry) => entry.key === "components");
  const rest = entries.filter((entry) => entry.key !== "components");

  return (
    <article className={`${styles.snapshot} ${current ? "" : styles.superseded}`}>
      <header className={styles.snapshotHead}>
        <div>
          <strong>
            {current ? "As it stands" : "Earlier"}
            {snapshot.observed_at ? (
              <span className={styles.when}>
                {" "}
                · read{" "}
                {new Date(snapshot.observed_at).toLocaleDateString(undefined, {
                  day: "numeric",
                  month: "short",
                  year: "numeric",
                })}
              </span>
            ) : null}
          </strong>
          {snapshot.source_revision ? (
            <span className={`${styles.revision} sg-mono`} title={snapshot.source_revision}>
              {snapshot.source_revision.slice(0, 12)}
            </span>
          ) : null}
        </div>
        {snapshot.confidence != null ? (
          <ConfidenceChip label={confidenceLabel(snapshot.confidence)} value={snapshot.confidence} />
        ) : null}
      </header>

      {components?.values.length ? (
        <div className={styles.components}>
          <span className={styles.entryLabel}>
            {components.values.length} component{components.values.length === 1 ? "" : "s"}
          </span>
          <ul className={styles.componentList}>
            {components.values.map((path) => {
              const parts = componentLabelParts(path, repositoryName, { repositoryIsImplied: true });
              return (
                <li key={path} className={`${styles.component} sg-mono`}>
                  {parts.path}
                </li>
              );
            })}
          </ul>
        </div>
      ) : null}

      <dl className={styles.entries}>
        {rest.map((entry) => (
          <div key={entry.key}>
            <dt>{entry.label}</dt>
            <dd>{entry.values.join(" · ")}</dd>
          </div>
        ))}
      </dl>

      {snapshot.fact_id ? (
        <div className={styles.evidence}>
          <CitationChip
            label="Evidence"
            onOpen={() => openEvidence(snapshot.fact_id, `${repositoryName ?? "Repository"} fingerprint`)}
          />
        </div>
      ) : null}
    </article>
  );
}

export function RepositoryFingerprint({
  repositoryId,
  repositoryName,
}: {
  repositoryId: string;
  repositoryName?: string;
}) {
  const query = useRepositoryFingerprints(repositoryId);
  const snapshots = query.data?.snapshots ?? [];

  if (query.isLoading) {
    return (
      <section className={styles.panel}>
        <Skeleton height={22} width="35%" />
        <Skeleton height={160} />
      </section>
    );
  }

  if (query.isError) {
    return (
      <section className={styles.panel}>
        <h2>Fingerprint</h2>
        <p className={styles.quiet} role="alert">The fingerprint is temporarily unavailable.</p>
      </section>
    );
  }

  if (!snapshots.length) {
    return (
      <section className={styles.panel} aria-labelledby={`fingerprint-${repositoryId}`}>
        <h2 id={`fingerprint-${repositoryId}`}>Fingerprint</h2>
        <p className={styles.quiet}>
          No fingerprint has been taken of this repository yet. One is produced by a scan,
          so this fills in after the next one.
        </p>
      </section>
    );
  }

  // Newest first; a snapshot with a `system_to` has been superseded.
  const ordered = [...snapshots].sort(
    (a, b) => new Date(b.observed_at ?? 0).getTime() - new Date(a.observed_at ?? 0).getTime(),
  );

  return (
    <section className={styles.panel} aria-labelledby={`fingerprint-${repositoryId}`}>
      <header className={styles.head}>
        <div>
          <h2 id={`fingerprint-${repositoryId}`}>Fingerprint</h2>
          <p>
            How this repository is built, packaged and deployed, as StackGraph read it.
            Every line comes from a scan and links to the fact behind it.
          </p>
        </div>
      </header>
      <div className={styles.snapshots}>
        {ordered.map((snapshot, index) => (
          <SnapshotBlock
            key={snapshot.fingerprint ?? `${snapshot.fact_id}-${index}`}
            snapshot={snapshot}
            repositoryName={repositoryName}
            current={index === 0 && !snapshot.system_to}
          />
        ))}
      </div>
      {ordered.length > 1 ? (
        <p className={styles.quiet}>
          {ordered.length} readings are kept, so a change in how this repository is built
          is visible rather than overwritten.
        </p>
      ) : null}
    </section>
  );
}
