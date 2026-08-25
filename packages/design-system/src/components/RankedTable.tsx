import type { ReactNode } from "react";
import { IconCornerDownRight } from "@tabler/icons-react";
import type { RankedItem } from "@stackgraph/shared";
import { DomainBadge } from "./DomainBadge";
import { ConfidenceChip } from "./ConfidenceChip";
import styles from "./RankedTable.module.css";

/**
 * Nests each Service row under its owning Application, in place, so the estate reads
 * as app -> service(s) instead of interleaving them at the same level by score. Rows
 * without a resolvable parent in the current list (filtered out, different page, or
 * no owner) stay at the top level in their original sort position.
 */
function withServiceHierarchy(items: RankedItem[]): { item: RankedItem; nested: boolean }[] {
  const ids = new Set(items.map((item) => item.id));
  const childrenByParent = new Map<string, RankedItem[]>();
  for (const item of items) {
    if (item.kind === "Service" && item.parent_application_id && ids.has(item.parent_application_id)) {
      const siblings = childrenByParent.get(item.parent_application_id) ?? [];
      siblings.push(item);
      childrenByParent.set(item.parent_application_id, siblings);
    }
  }
  if (childrenByParent.size === 0) return items.map((item) => ({ item, nested: false }));

  const nestedIds = new Set([...childrenByParent.values()].flat().map((child) => child.id));
  const rows: { item: RankedItem; nested: boolean }[] = [];
  for (const item of items) {
    if (nestedIds.has(item.id)) continue;
    rows.push({ item, nested: false });
    for (const child of childrenByParent.get(item.id) ?? []) {
      rows.push({ item: child, nested: true });
    }
  }
  return rows;
}

/**
 * The default reading surface (design language §table row): domain badge, mono name,
 * sans one-line status, confidence chip, right-aligned priority score.
 * Rows are keyboard-focusable and activate on Enter/click. Service rows nest under
 * their owning Application (see withServiceHierarchy) instead of sitting flat.
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
  const rows = withServiceHierarchy(items);

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
        {rows.map(({ item, nested }) => {
          const href = renderRowHref?.(item);
          const NameCell: ReactNode = (
            <>
              <span className={`${styles.name} sg-mono`}>
                {nested ? <IconCornerDownRight size={14} stroke={1.75} className={styles.nestGlyph} aria-hidden="true" /> : null}
                {item.name}
              </span>
              {item.summary ? <span className={styles.summary}>{item.summary}</span> : null}
            </>
          );
          return (
            <tr
              key={item.id}
              className={`${styles.row} ${nested ? styles.nestedRow : ""}`}
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
