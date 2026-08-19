import type { Namespace } from "@stackgraph/shared";
import styles from "./DomainBadge.module.css";

const META: Record<Namespace, { code: string; family: string; label: string }> = {
  BUSINESS: { code: "BIZ", family: "business", label: "Business" },
  ENTERPRISE: { code: "ENT", family: "enterprise", label: "Enterprise" },
  TECHNOLOGY: { code: "TEC", family: "enterprise", label: "Technology" },
  OSS: { code: "OSS", family: "oss", label: "OSS" },
  DEPLOYMENT: { code: "DEP", family: "enterprise", label: "Deployment" },
  INTELLIGENCE: { code: "INT", family: "intelligence", label: "Intelligence" },
};

/**
 * Domain badge — mono two-letter code on a 100-tint fill with 800-tint text.
 * Text label is ALWAYS present: color is never the only signal (accessibility + B/W print).
 */
export function DomainBadge({ namespace }: { namespace: Namespace }) {
  const m = META[namespace];
  return (
    <span
      className={`${styles.badge} sg-mono`}
      style={{
        // eslint-disable-next-line
        ["--fill" as string]: `var(--sg-color-domain-${m.family}-100)`,
        ["--ink" as string]: `var(--sg-color-domain-${m.family}-800)`,
      }}
      aria-label={m.label}
      title={m.label}
    >
      {m.code}
    </span>
  );
}
