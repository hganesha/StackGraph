import type { ReactNode } from "react";
import type { RankedItem } from "@stackgraph/shared";
import { DomainBadge } from "./DomainBadge";
import { ConfidenceChip } from "./ConfidenceChip";
import styles from "./RankedTable.module.css";

/**
 * The default reading surface (design language §table row): domain badge, mono name,
 * sans one-line status, confidence chip, right-aligned priority score.
 * Rows are keyboard-focusable and activate on Enter/click.
 */
export function RankedTable({
  items,
  caption,
  onOpen,
  renderRowHref,
}: {
  items: RankedItem[];
  caption: string;
  onOpen?: (item: RankedItem) => void;
  renderRowHref?: (item: RankedItem) => string;
}) {
  const showDependencyTier = items.some((item) => item.dependency_tier !== undefined);

  return (
    <table className={`${styles.table} ${showDependencyTier ? styles.withTier : ""}`}>
      <caption className={styles.caption}>{caption}</caption>
      <thead>
        <tr>
          <th scope="col" className={styles.hDomain}>
            Domain
          </th>
          <th scope="col">Name</th>
          {showDependencyTier ? (
            <th scope="col" className={styles.hTier}>
              Dependency tier
            </th>
          ) : null}
          <th scope="col" className={styles.hConf}>
            Confidence
          </th>
          <th scope="col" className={styles.hNum}>
            Priority
          </th>
        </tr>
      </thead>
      <tbody>
        {items.map((item) => {
          const href = renderRowHref?.(item);
          const NameCell: ReactNode = (
            <>
              <span className={`${styles.name} sg-mono`}>{item.name}</span>
              {item.summary ? <span className={styles.summary}>{item.summary}</span> : null}
            </>
          );
          return (
            <tr
              key={item.id}
              className={styles.row}
              tabIndex={0}
              onClick={() => onOpen?.(item)}
              onKeyDown={(e) => {
                if (e.key === "Enter") onOpen?.(item);
              }}
            >
              <td className={styles.cDomain}>
                <DomainBadge namespace={item.domain} />
              </td>
              <td className={styles.cName}>
                {href ? (
                  <a href={href} className={styles.link} onClick={(e) => e.stopPropagation()}>
                    {NameCell}
                  </a>
                ) : (
                  <span className={styles.link}>{NameCell}</span>
                )}
              </td>
              {showDependencyTier ? (
                <td className={styles.cTier}>
                  {item.dependency_tier ? (
                    <span className={styles.tierBadge}>
                      Tier {item.dependency_tier}
                      <span>{item.dependency_tier === 1 ? "Direct" : "Transitive"}</span>
                    </span>
                  ) : (
                    <span className={styles.notApplicable}>—</span>
                  )}
                </td>
              ) : null}
              <td className={styles.cConf}>
                <ConfidenceChip label={item.priority.confidence_label} value={item.priority.confidence} />
              </td>
              <td className={`${styles.cNum} sg-mono`}>{Math.round(item.priority.value)}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
