"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { IconSparkles } from "@tabler/icons-react";
import { Skeleton, Term } from "@stackgraph/design-system";
import type { SemanticSearchHit } from "@stackgraph/shared";
import { useSemanticSearch } from "@/lib/queries";
import { isUnavailable } from "@/lib/reviews";
import styles from "./SemanticMatches.module.css";

function hrefFor(hit: SemanticSearchHit): string {
  if (hit.entity.kind === "Repository") return `/repositories/${hit.entity.id}`;
  if (hit.entity.kind === "Application") return `/applications/${hit.entity.id}`;
  return `/technologies/${hit.entity.id}`;
}

/** Typing is continuous; retrieval should not be. */
function useDebounced(value: string, delayMs = 300): string {
  const [settled, setSettled] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setSettled(value), delayMs);
    return () => clearTimeout(timer);
  }, [value, delayMs]);
  return settled;
}

/**
 * Entities that read like the filter term but do not contain it.
 *
 * Deliberately a second group, below the exact matches and labelled as retrieval: a
 * semantic hit is a suggestion drawn from an embedding space, not a claim that the
 * entity matches. Where no evaluated space is active the API is fail-closed and says
 * so; that is a state this surface explains rather than an error it reports, and the
 * name filter above keeps working either way.
 */
export function SemanticMatches({ query }: { query: string }) {
  const settled = useDebounced(query);
  const search = useSemanticSearch(settled);

  if (settled.trim().length < 2) return null;

  return (
    <section className={styles.section} aria-labelledby="semantic-matches-heading">
      <div className={styles.head}>
        <IconSparkles size={15} stroke={1.75} aria-hidden="true" />
        <h2 id="semantic-matches-heading">Related by meaning</h2>
        <p>
          Found by <Term id="semanticSimilarity">semantic similarity</Term>, not by name. A
          suggestion to look at, never proof of a relationship.
        </p>
      </div>

      {search.isLoading ? (
        <Skeleton height={64} />
      ) : isUnavailable(search.error) ? (
        <p className={styles.unavailable}>
          Related matches need an evaluated <Term id="embeddingSpace">embedding space</Term>, and
          none is active yet. Filtering by name is unaffected.
        </p>
      ) : search.isError ? (
        <p className={styles.unavailable} role="alert">
          Related matches are temporarily unavailable. Filtering by name is unaffected.
        </p>
      ) : search.data?.hits.length ? (
        <>
          <ul className={styles.hits}>
            {search.data.hits.map((hit) => (
              <li key={hit.entity.id}>
                <Link href={hrefFor(hit)}>
                  <strong>{hit.entity.name}</strong>
                  <span>{hit.entity.kind}</span>
                  {hit.entity.summary ? <p>{hit.entity.summary}</p> : null}
                </Link>
                <span className={`${styles.score} sg-mono`}>{Math.round(hit.score * 100)}%</span>
              </li>
            ))}
          </ul>
          <p className={styles.provenance}>
            {search.data.model_or_algorithm} · {search.data.space_key}
            {search.data.limitations.map((limitation, index) => (
              <span key={`${String(limitation.code ?? "limitation")}:${index}`}>
                {" · "}
                {String(limitation.message ?? limitation.code ?? "This result has a limitation.")}
              </span>
            ))}
          </p>
        </>
      ) : (
        <p className={styles.unavailable}>
          Nothing in the evaluated space reads like “{settled.trim()}”.
        </p>
      )}
    </section>
  );
}
