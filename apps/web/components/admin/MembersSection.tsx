"use client";

import styles from "./admin.module.css";

const MEMBERS = [
  { name: "You", email: "hariganesh@msn.com", role: "admin" },
  { name: "Dana Okafor", email: "dana@acme.example", role: "execute" },
  { name: "Priya Raman", email: "priya@acme.example", role: "review" },
  { name: "Sam Lee", email: "sam@acme.example", role: "view" },
];

/** Members & Roles (plan §11.2D, §8.3): the capability tiers view → review → execute → admin. */
export function MembersSection() {
  return (
    <div className={styles.section}>
      <p className={styles.sectionNote}>
        Roles gate what each member can do: <span className="sg-mono">view</span> →{" "}
        <span className="sg-mono">review</span> → <span className="sg-mono">execute</span> →{" "}
        <span className="sg-mono">admin</span>. Least-privilege by default. SSO/OIDC configured here.
      </p>

      <ul className={styles.memberList}>
        {MEMBERS.map((m) => (
          <li key={m.email} className={styles.memberItem}>
            <div className={styles.memberMain}>
              <span className={styles.memberName}>{m.name}</span>
              <span className={`${styles.memberEmail} sg-mono`}>{m.email}</span>
            </div>
            <span className={`${styles.roleBadge} ${styles[`role_${m.role}`]}`}>{m.role}</span>
          </li>
        ))}
      </ul>

      <button type="button" className={styles.ghost}>
        Configure SSO / OIDC
      </button>
    </div>
  );
}
