"use client";

import { useMemo } from "react";
import type { StratumLayer } from "@stackgraph/design-system";
import type { CapabilityFootprintList, EstateSummary } from "@stackgraph/shared";

/**
 * The five estate layers, derived from read models that already ship.
 *
 * Two layers have a real denominator today and are drawn as a ratio:
 *
 *   Business    capabilities that have an application behind them, out of the
 *               capabilities StackGraph has mapped (`/capabilities/footprints`)
 *   Enterprise  repositories scanned, out of repositories connected
 *               (`EstateSummary.coverage`)
 *
 * Three do not, and say so rather than inventing one. `EstateSummary` carries no
 * per-namespace population or evidence ratio, so Technology, OSS and Deployment have
 * no honest fraction to draw — the bands render hatched with their count beside them,
 * and the reason is stated in the expanded panel.
 *
 * That is deliberate and not a placeholder. A layer nobody measures and a layer that
 * is empty are different facts, and drawing the first as a zero-length band would make
 * the picture lie in exactly the direction that flatters us. When the summary grows a
 * per-namespace coverage reading, each of these becomes a one-line change here and
 * nothing else in the UI moves.
 */
export interface EstateStrata {
  layers: StratumLayer[];
  weakest: { label: string; reading: string } | null;
}

const NOT_MEASURED =
  "The estate summary reports no population or evidence ratio for this layer yet, so there is nothing honest to fill the band with.";

export function useEstateStrata(
  summary: EstateSummary | undefined,
  footprints: CapabilityFootprintList | undefined,
): EstateStrata {
  return useMemo<EstateStrata>(() => {
    if (!summary) return { layers: [], weakest: null };

    const { counts, coverage, distributions } = summary;

    const capabilities = footprints?.footprints ?? [];
    const mappedCapabilities = capabilities.filter((entry) => entry.application_count > 0);
    const businessRatio = capabilities.length ? mappedCapabilities.length / capabilities.length : null;

    const enterpriseRatio = coverage.repositories_total > 0
      ? coverage.repositories_scanned / coverage.repositories_total
      : null;

    // The technology distribution is a genuine per-layer breakdown and belongs in the
    // drill-down even though it cannot produce a coverage fraction.
    const technologyFacts = Object.entries(distributions)
      .filter(([key]) => key.startsWith("technology."))
      .sort(([, left], [, right]) => right - left)
      .slice(0, 4)
      .map(([key, value]) => ({
        label: key.slice("technology.".length).replaceAll("-", " "),
        value: String(Math.round(value)),
      }));

    const layers: StratumLayer[] = [
      {
        key: "BUSINESS",
        label: "Business",
        ratio: businessRatio,
        reading: capabilities.length
          ? `${mappedCapabilities.length} of ${capabilities.length} mapped capabilities have an application behind them`
          : "No business capabilities are mapped yet",
        unmeasuredReason: capabilities.length
          ? undefined
          : "Nothing has been mapped to a business capability, so there is no layer to measure. Start on the Business Map.",
        facts: capabilities.length
          ? [{ label: "Capabilities", value: String(capabilities.length) }]
          : undefined,
      },
      {
        key: "ENTERPRISE",
        label: "Enterprise",
        ratio: enterpriseRatio,
        reading: `${coverage.repositories_scanned} of ${coverage.repositories_total} repositories scanned`,
        unmeasuredReason: enterpriseRatio == null ? "No repositories are connected yet." : undefined,
        facts: [
          { label: "Applications", value: String(counts.applications) },
          { label: "Services", value: String(counts.services) },
        ],
      },
      {
        key: "TECHNOLOGY",
        label: "Technology",
        ratio: null,
        reading: `${counts.technologies} technologies observed`,
        unmeasuredReason: NOT_MEASURED,
        facts: technologyFacts.length ? technologyFacts : undefined,
      },
      {
        key: "OSS",
        label: "OSS",
        ratio: null,
        reading: "Linked open-source project intelligence",
        unmeasuredReason: NOT_MEASURED,
      },
      {
        key: "DEPLOYMENT",
        label: "Deployment",
        ratio: null,
        reading: "Deployment definitions found in your repositories",
        unmeasuredReason: NOT_MEASURED,
      },
    ];

    // The headline names the thinnest layer that actually has a measure. Naming an
    // unmeasured one would report a gap in our instrumentation as a gap in their estate.
    const weakest = layers
      .filter((layer): layer is StratumLayer & { ratio: number } => layer.ratio != null)
      .sort((left, right) => left.ratio - right.ratio)[0];

    return {
      layers,
      weakest: weakest ? { label: weakest.label, reading: weakest.reading } : null,
    };
  }, [footprints, summary]);
}
