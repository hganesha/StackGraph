// Presentation-only derivations. Components consume these, never raw read models directly,
// so contract changes touch this seam, not 40 components (plan §7.2).

import type { ConfidenceLabel, Namespace } from "../contracts/read-models";

const NS_LABEL: Record<Namespace, string> = {
  BUSINESS: "Business",
  ENTERPRISE: "Enterprise",
  TECHNOLOGY: "Technology",
  OSS: "OSS",
  DEPLOYMENT: "Deployment",
  INTELLIGENCE: "Intelligence",
};

export const namespaceLabel = (ns: Namespace) => NS_LABEL[ns];

/** Locale-aware date (plan §8.2 i18n). Defaults to the runtime locale. */
export function formatDate(iso: string, locale?: string): string {
  return new Intl.DateTimeFormat(locale, { dateStyle: "medium" }).format(new Date(iso));
}

/** "3 days ago" style relative time from an ISO timestamp. */
export function formatRelative(iso: string, locale?: string, now = Date.now()): string {
  const diffMs = new Date(iso).getTime() - now;
  const rtf = new Intl.RelativeTimeFormat(locale, { numeric: "auto" });
  const abs = Math.abs(diffMs);
  const units: Array<[Intl.RelativeTimeFormatUnit, number]> = [
    ["year", 31536000000],
    ["month", 2592000000],
    ["day", 86400000],
    ["hour", 3600000],
    ["minute", 60000],
  ];
  for (const [unit, ms] of units) {
    if (abs >= ms) return rtf.format(Math.round(diffMs / ms), unit);
  }
  return rtf.format(0, "minute");
}

/** Confidence decimal formatted to the runtime locale, e.g. 0.71 or 0,71. */
export function formatConfidence(value: number, locale?: string): string {
  return new Intl.NumberFormat(locale, { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value);
}

export const segmentsFor = (label: ConfidenceLabel): 1 | 2 | 3 =>
  label === "HIGH" ? 3 : label === "MEDIUM" ? 2 : 1;

/**
 * Defense-in-depth: never render a credential-bearing origin (plan §8.3).
 * Strips any userinfo (user:pass@) and query/hash, returning host + path only.
 * Read models are contractually credential-free, but the UI refuses to echo one anyway.
 */
export function sanitizeOrigin(raw: string): string {
  try {
    const u = new URL(raw);
    u.username = "";
    u.password = "";
    u.search = "";
    u.hash = "";
    return u.host + (u.pathname === "/" ? "" : u.pathname);
  } catch {
    // Not a URL — strip anything resembling userinfo and query strings.
    return raw.replace(/\/\/[^/@]*@/, "//").replace(/[?#].*$/, "");
  }
}
