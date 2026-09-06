import type { ChangeScope, ValidTarget } from "@stackgraph/shared";
import styles from "./VersionSpreadComb.module.css";

export function VersionSpreadComb({ scope, targets }: { scope: ChangeScope; targets: ValidTarget[] }) {
  const maximum = Math.max(1, ...scope.version_distribution.map((item) => item.count));
  const suggested = new Set(targets.map((item) => item.version));

  return (
    <figure className={styles.figure} aria-labelledby={`spread-${scope.id}`}>
      <figcaption id={`spread-${scope.id}`}>
        <strong>Current version spread</strong>
        <span>{scope.affected_count} {scope.kind === "COMPONENT" ? "component dependencies" : "dependencies"} observed</span>
      </figcaption>
      <div className={styles.comb}>
        {scope.version_distribution.map((item) => (
          <div className={styles.tooth} key={item.version}>
            <span className={styles.count}>{item.count}</span>
            <span
              className={styles.bar}
              style={{ blockSize: `${Math.max(12, Math.round((item.count / maximum) * 72))}px` }}
              aria-hidden="true"
            />
            <span className={styles.version}>{item.version}</span>
            {suggested.has(item.version) ? <span className={styles.marker}>target</span> : null}
          </div>
        ))}
      </div>
      <p className={styles.textEquivalent}>
        {scope.version_distribution.map((item) => `${item.version}: ${item.count}`).join("; ")}.
      </p>
    </figure>
  );
}
