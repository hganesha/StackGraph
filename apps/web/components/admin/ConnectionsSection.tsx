"use client";

import styles from "./admin.module.css";

const CONNECTIONS = [
  { name: "acme-corp (GitHub org)", kind: "GitHub App", status: "Connected", scopes: "repo:read, metadata:read", when: "synced 2h ago" },
  { name: "npm-public", kind: "Registry", status: "Connected", scopes: "PUBLIC", when: "synced 1h ago" },
  { name: "artifactory-internal", kind: "Registry (private)", status: "Needs re-auth", scopes: "PRIVATE · tenant-scoped", when: "failed 30m ago" },
];

/** Connections — onboarding home (plan §11.2A). The UI orchestrates OAuth/App-install flows and
 *  stores only a credential_reference; it never accepts or displays a raw token. */
export function ConnectionsSection() {
  return (
    <div className={styles.section}>
      <p className={styles.sectionNote}>
        Connect source and registry providers. StackGraph stores only a credential reference — never a raw token,
        PAT, or password. Read-only scopes are requested.
      </p>

      <button type="button" className={styles.primaryWide}>
        + Install the GitHub App
      </button>

      <ul className={styles.connList}>
        {CONNECTIONS.map((c) => {
          const broken = c.status !== "Connected";
          return (
            <li key={c.name} className={styles.connItem}>
              <div className={styles.connMain}>
                <span className={styles.connName}>{c.name}</span>
                <span className={styles.connMeta}>
                  {c.kind} · <span className="sg-mono">{c.scopes}</span>
                </span>
              </div>
              <div className={styles.connRight}>
                <span className={`${styles.connStatus} ${broken ? styles.connBroken : styles.connOk}`}>{c.status}</span>
                <span className={styles.connWhen}>{c.when}</span>
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
