import type { Namespace } from "@stackgraph/shared";
import { DomainIcon } from "./DomainIcon";
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
 * Domain badge — mono glyph + two-letter code on a 100-tint fill with 800-tint text.
 * Text code is ALWAYS present: neither color nor icon is ever the only signal
 * (accessibility + B/W print). Pass `showIcon={false}` to drop the glyph in dense rows.
 */
export function DomainBadge({
  namespace,
  showIcon = true,
}: {
  namespace: Namespace;
  showIcon?: boolean;
}) {
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
      {showIcon ? <DomainIcon namespace={namespace} size={13} stroke={1.75} className={styles.glyph} /> : null}
      {m.code}
    </span>
  );
}
