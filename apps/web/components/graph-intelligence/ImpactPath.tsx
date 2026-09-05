"use client";

import { ConfidenceChip, DomainBadge, confidenceLabel } from "@stackgraph/design-system";
import type { Namespace } from "@stackgraph/shared";
import styles from "./impact-path.module.css";

export interface ImpactHop {
  id: string;
  /** `null` when the hop is not in the neighbourhood we fetched. */
  name: string | null;
  domain?: Namespace;
  kind?: string;
}

/**
 * One traversal result, read as a sentence.
 *
 * This replaces `impact.entity_ids.join(" → ")` — a chain of raw UUIDs shown to an
 * executive, which was unreadable to every persona in the spec (defect §7.1). The
 * answer StackGraph exists to give is "this package, three hops out, touches Claims
 * Settlement, and here is the evidence for every hop", and it was one string-join away
 * from being invisible.
 *
 * Names come from the neighbourhood already fetched for the graph view. A hop outside
 * that neighbourhood renders as an unnamed step rather than as its id: a UUID on screen
 * is not information, and the id stays on the `title` for anyone who needs it.
 *
 * The terminus is the destination, drawn heavier than the path that reaches it — a
 * blast radius of 73 repositories means much less than "Payment Authorization, a
 * business capability, is affected."
 */
export function ImpactPath({
  hops,
  distance,
  minimumConfidence,
  targetName,
  targetDomain,
}: {
  hops: ImpactHop[];
  distance: number;
  minimumConfidence: number;
  targetName: string;
  targetDomain?: Namespace;
}) {
  const named = hops.filter((hop) => hop.name);
  const unnamed = hops.length - named.length;

  return (
    <div className={styles.path}>
      <ol
        className={styles.trail}
        aria-label={`Impact path, ${distance} hop${distance === 1 ? "" : "s"}: ${
          hops.map((hop) => hop.name ?? "an unnamed step").join(", then ")
        }`}
      >
        {hops.map((hop, index) => {
          const last = index === hops.length - 1;
          return (
            <li key={`${hop.id}:${index}`} className={styles.step}>
              <span
                className={`${styles.hop} ${last ? styles.terminus : ""} ${hop.name ? "" : styles.unnamed}`}
                title={hop.name ? `${hop.kind ?? "Entity"} · ${hop.id}` : `Not in the loaded neighbourhood · ${hop.id}`}
              >
                {hop.domain ? <DomainBadge namespace={hop.domain} /> : null}
                <span className={styles.hopName}>{hop.name ?? "Unnamed step"}</span>
              </span>
              {last ? null : (
                <span className={styles.arrow} aria-hidden="true">
                  →
                </span>
              )}
            </li>
          );
        })}
      </ol>
      <div className={styles.meta}>
        <span className={styles.terminusReading}>
          Reaches{" "}
          <strong>
            {targetDomain ? <DomainBadge namespace={targetDomain} /> : null} {targetName}
          </strong>{" "}
          in {distance} hop{distance === 1 ? "" : "s"}
        </span>
        {/* The weakest link in the chain, on the same three-segment control the rest of
            the product uses. Opacity alone would have made this a second confidence
            encoding, and there is only meant to be one. */}
        <span className={styles.confidence}>
          Weakest hop <ConfidenceChip label={confidenceLabel(minimumConfidence)} value={minimumConfidence} />
        </span>
        {unnamed ? (
          <span className={styles.unnamedNote}>
            {unnamed} step{unnamed === 1 ? "" : "s"} on this path {unnamed === 1 ? "is" : "are"} outside
            the loaded neighbourhood
          </span>
        ) : null}
      </div>
    </div>
  );
}
