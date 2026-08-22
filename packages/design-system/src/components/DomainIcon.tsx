import {
  IconBrandOpenSource,
  IconBriefcase,
  IconBuildingSkyscraper,
  IconServer2,
  IconSparkles,
  IconStack2,
  type Icon,
} from "@tabler/icons-react";
import type { Namespace } from "@stackgraph/shared";

/**
 * One mono, flat, stroked glyph per namespace — the same Tabler family and stroke
 * weight the primary navigation uses, so a domain reads identically in the rail,
 * in a badge, on a card header, and on a graph node.
 *
 * TECHNOLOGY deliberately reuses the rail's Technologies glyph; the others are
 * distinct enough to stay separable at 13px.
 */
export const domainIcons: Record<Namespace, Icon> = {
  BUSINESS: IconBriefcase,
  ENTERPRISE: IconBuildingSkyscraper,
  TECHNOLOGY: IconStack2,
  OSS: IconBrandOpenSource,
  DEPLOYMENT: IconServer2,
  INTELLIGENCE: IconSparkles,
};

/**
 * Decorative by default: every place a domain icon appears also carries the
 * two-letter code or a text label, so the glyph is never the only signal.
 */
export function DomainIcon({
  namespace,
  size = 16,
  stroke = 1.5,
  className,
}: {
  namespace: Namespace;
  size?: number;
  stroke?: number;
  className?: string;
}) {
  const Glyph = domainIcons[namespace];
  return <Glyph size={size} stroke={stroke} className={className} aria-hidden="true" />;
}
