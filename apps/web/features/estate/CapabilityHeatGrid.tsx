"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { IconAlertTriangle } from "@tabler/icons-react";
import { IconSpread, Skeleton, Term } from "@stackgraph/design-system";
import type { CapabilityFootprint } from "@stackgraph/shared";
import { useCapabilityFootprints } from "@/lib/queries";
import { squarify } from "./treemap";
import styles from "./heat-grid.module.css";

/**
 * Four ways to read the same grid. Each one is a field that already ships on
 * `/capabilities/footprints`, so nothing here is derived, weighted, or guessed.
 *
 * `higherIs` is the honest half of the legend: the ramp always runs light → dark as the
 * measure rises, so the legend has to say whether dark is the problem or the point.
 * Spread rising is a cost; reuse rising is a saving; the ramp cannot tell you which.
 */
type MeasureKey = "spread" | "reuse" | "technologies" | "none";

interface Measure {
  key: MeasureKey;
  label: string;
  hint: string;
  /** 0..1 for the ramp. `null` for the No colour mode. */
  scale: ((footprint: CapabilityFootprint, max: number) => number) | null;
  format: (footprint: CapabilityFootprint) => string;
  max: (footprints: CapabilityFootprint[]) => number;
  higherIs: string;
  term?: "spread" | "reuseSignal";
}

const MEASURES: Measure[] = [
  {
    key: "spread",
    label: "Spread",
    hint: "How many different ways do we do this one thing?",
    scale: (footprint) => footprint.technology_entropy,
    format: (footprint) => footprint.technology_entropy.toFixed(2),
    max: () => 1,
    higherIs: "Darker means the same job is being done more different ways.",
    term: "spread",
  },
  {
    key: "reuse",
    label: "Reuse",
    hint: "How much of this is shared versus rebuilt?",
    scale: (footprint) => footprint.reuse_signal,
    format: (footprint) => footprint.reuse_signal.toFixed(2),
    max: () => 1,
    higherIs: "Darker means more of this is built on things already used elsewhere.",
    term: "reuseSignal",
  },
  {
    key: "technologies",
    label: "Technologies",
    hint: "How many distinct technologies sit behind this capability?",
    scale: (footprint, max) => (max > 0 ? footprint.technology_count / max : 0),
    format: (footprint) => String(footprint.technology_count),
    max: (footprints) => Math.max(1, ...footprints.map((entry) => entry.technology_count)),
    higherIs: "Darker means more distinct technologies behind one capability.",
  },
  {
    key: "none",
    label: "Off",
    hint: "No colour — read the labels only.",
    scale: null,
    format: (footprint) => String(footprint.application_count),
    max: () => 1,
    higherIs: "",
  },
];

/** Six stops, so the ramp is readable as steps rather than as a gradient. */
const STOPS = 6;

function rampStop(value: number): number {
  if (!Number.isFinite(value)) return 0;
  return Math.min(STOPS - 1, Math.max(0, Math.round(value * (STOPS - 1))));
}

const GRID_WIDTH = 1000;
const GRID_HEIGHT = 560;

export function CapabilityHeatGrid() {
  const query = useCapabilityFootprints();
  const [measureKey, setMeasureKey] = useState<MeasureKey>("spread");
  const [focused, setFocused] = useState<string | null>(null);

  const measure = MEASURES.find((entry) => entry.key === measureKey) ?? MEASURES[0];
  const footprints = useMemo(() => query.data?.footprints ?? [], [query.data]);
  const max = useMemo(() => measure.max(footprints), [footprints, measure]);

  // Area is application count — the size of the bet, not the size of the problem.
  // A capability with no application behind it has no area, so it is listed beneath
  // the grid rather than dropped: an unmapped capability is a finding of its own.
  const tiles = useMemo(
    () =>
      squarify(
        footprints
          .filter((footprint) => footprint.application_count > 0)
          .map((footprint) => ({ item: footprint, value: footprint.application_count })),
        GRID_WIDTH,
        GRID_HEIGHT,
      ),
    [footprints],
  );
  const unmapped = useMemo(
    () => footprints.filter((footprint) => footprint.application_count === 0),
    [footprints],
  );

  const estateSpread = useMemo(() => {
    if (!footprints.length) return null;
    const weight = footprints.reduce((sum, entry) => sum + entry.application_count, 0);
    if (weight <= 0) return null;
    return (
      footprints.reduce((sum, entry) => sum + entry.technology_entropy * entry.application_count, 0) / weight
    );
  }, [footprints]);

  const focusedFootprint = useMemo(
    () => footprints.find((entry) => entry.capability.id === focused) ?? null,
    [focused, footprints],
  );

  if (query.isLoading) {
    return (
      <div className={styles.loading}>
        <Skeleton height={28} width="45%" />
        <Skeleton height={520} />
      </div>
    );
  }

  if (query.isError) {
    return (
      <div className={styles.notice} role="alert">
        <IconAlertTriangle size={18} stroke={1.5} aria-hidden="true" />
        <span>Couldn’t load capability footprints. The ranked list and canvas still work.</span>
      </div>
    );
  }

  if (!footprints.length) {
    return (
      <div className={styles.empty} role="status">
        <h2>No capabilities are mapped yet</h2>
        <p>
          This grid draws one cell per business capability, sized by how many applications
          sit behind it. Nothing has been mapped to a capability, so there is nothing to
          draw — which is itself the finding.
        </p>
        <Link href="/business-map">Open the Business Map</Link>
      </div>
    );
  }

  return (
    <section className={styles.wrap} aria-labelledby="heat-grid-heading">
      <header className={styles.head}>
        <div>
          <h2 id="heat-grid-heading">Where the estate is most scattered</h2>
          <p>
            One cell per business capability, sized by how many applications sit behind it.
            Every cell carries its number, so the grid reads the same in greyscale.
          </p>
        </div>
        {estateSpread != null ? (
          <div className={styles.headline}>
            {/* The 32px display step, reserved for "the numbers meant to be read from
                across a room" and until now spent on a repository count (§6.2). */}
            <strong className={`${styles.display} sg-mono`}>{estateSpread.toFixed(2)}</strong>
            <span>
              estate-wide <Term id="spread">spread</Term>
            </span>
            <small>weighted by applications</small>
          </div>
        ) : null}
      </header>

      <div className={styles.controls}>
        <fieldset className={styles.controlGroup}>
          <legend className={styles.controlLegend}>Colour by</legend>
          <div className={styles.segmented} role="radiogroup" aria-label="Colour capability cells by">
            {MEASURES.map((option) => (
              <button
                key={option.key}
                type="button"
                role="radio"
                aria-checked={measure.key === option.key}
                title={option.hint}
                className={`${styles.segment} ${measure.key === option.key ? styles.segmentActive : ""}`}
                onClick={() => setMeasureKey(option.key)}
              >
                {option.label}
              </button>
            ))}
          </div>
        </fieldset>
      </div>

      <div className={styles.body}>
        {/* Inline, permanent, left of the grid. Never a popover: a heat map without a
            legend on screen is a decoration. */}
        <aside className={styles.legend} aria-label={`${measure.label} legend`}>
          <span className={styles.legendTitle}>{measure.label}</span>
          <p className={styles.legendHint}>{measure.hint}</p>
          {measure.scale ? (
            <>
              <ol className={styles.ramp}>
                {Array.from({ length: STOPS }, (_, stop) => (
                  <li key={stop} className={styles.rampStop} data-stop={stop}>
                    <span className={styles.rampSwatch} aria-hidden="true" />
                    <span className={`${styles.rampValue} sg-mono`}>
                      {measure.key === "technologies"
                        ? Math.round((stop / (STOPS - 1)) * max)
                        : (stop / (STOPS - 1)).toFixed(1)}
                    </span>
                  </li>
                ))}
              </ol>
              <p className={styles.legendDirection}>{measure.higherIs}</p>
            </>
          ) : (
            <p className={styles.legendDirection}>
              No colour. Cells keep their size and their number — this is the mode to read
              the grid in when the ramp is getting in the way.
            </p>
          )}
          <p className={styles.legendArea}>Cell area is the number of applications behind the capability.</p>
        </aside>

        <div className={styles.gridWrap}>
          <svg
            className={styles.grid}
            viewBox={`0 0 ${GRID_WIDTH} ${GRID_HEIGHT}`}
            preserveAspectRatio="none"
            role="img"
            aria-label={`${tiles.length} business capabilities, sized by applications and coloured by ${measure.label.toLowerCase()}`}
          >
            {tiles.map(({ item, x, y, width, height }) => {
              const value = measure.scale ? measure.scale(item, max) : 0;
              const stop = measure.scale ? rampStop(value) : -1;
              // Below ~64px the numeral does not fit; below ~32px neither does the name.
              // Nothing is lost — the list beneath the grid carries every capability.
              const showName = width > 72 && height > 30;
              const showValue = showName && width > 96 && height > 48;
              return (
                <g
                  key={item.capability.id}
                  className={styles.tile}
                  data-stop={stop >= 0 ? stop : undefined}
                  onMouseEnter={() => setFocused(item.capability.id)}
                  onMouseLeave={() => setFocused(null)}
                >
                  <rect
                    x={x}
                    y={y}
                    width={Math.max(width - 1, 0)}
                    height={Math.max(height - 1, 0)}
                    className={styles.tileRect}
                  />
                  {showName ? (
                    <text x={x + 8} y={y + 18} className={styles.tileName}>
                      {item.capability.name}
                    </text>
                  ) : null}
                  {showValue ? (
                    <text
                      x={x + width - 9}
                      y={y + height - 9}
                      className={styles.tileValue}
                      textAnchor="end"
                    >
                      {measure.format(item)}
                    </text>
                  ) : null}
                </g>
              );
            })}
          </svg>

          {/* Every capability, in a table, focusable and readable. The grid is the
              shape; this is the record — and it is what a screen reader and a small
              viewport get instead of a picture. */}
          <table className={styles.table}>
            <caption>
              {footprints.length} mapped capabilit{footprints.length === 1 ? "y" : "ies"}, ranked by{" "}
              {measure.label.toLowerCase()}
            </caption>
            <thead>
              <tr>
                <th scope="col">Capability</th>
                <th scope="col">Applications</th>
                <th scope="col">Repositories</th>
                <th scope="col">Technologies</th>
                <th scope="col">Spread</th>
                <th scope="col">Reuse</th>
              </tr>
            </thead>
            <tbody>
              {[...footprints]
                .sort((left, right) => {
                  if (!measure.scale) return right.application_count - left.application_count;
                  return measure.scale(right, max) - measure.scale(left, max);
                })
                .map((footprint) => (
                  <tr
                    key={footprint.capability.id}
                    className={focused === footprint.capability.id ? styles.rowFocused : ""}
                    onMouseEnter={() => setFocused(footprint.capability.id)}
                    onMouseLeave={() => setFocused(null)}
                  >
                    <th scope="row">
                      <Link href="/business-map" onFocus={() => setFocused(footprint.capability.id)}>
                        {footprint.capability.name}
                      </Link>
                    </th>
                    <td className="sg-mono">{footprint.application_count}</td>
                    <td className="sg-mono">{footprint.repository_count}</td>
                    <td className="sg-mono">{footprint.technology_count}</td>
                    <td className="sg-mono">{footprint.technology_entropy.toFixed(2)}</td>
                    <td className="sg-mono">{footprint.reuse_signal.toFixed(2)}</td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      </div>

      {focusedFootprint ? (
        <p className={styles.focusReading} role="status">
          <IconSpread size={15} />
          <span>
            <strong>{focusedFootprint.capability.name}</strong> is implemented across{" "}
            {focusedFootprint.application_count} application
            {focusedFootprint.application_count === 1 ? "" : "s"} and{" "}
            {focusedFootprint.repository_count} repositor
            {focusedFootprint.repository_count === 1 ? "y" : "ies"}, using{" "}
            {focusedFootprint.technology_count} distinct technolog
            {focusedFootprint.technology_count === 1 ? "y" : "ies"}.
          </span>
        </p>
      ) : null}

      {unmapped.length ? (
        <p className={styles.unmapped}>
          {unmapped.length} mapped capabilit{unmapped.length === 1 ? "y has" : "ies have"} no
          application behind {unmapped.length === 1 ? "it" : "them"} and so no area in the grid:{" "}
          {unmapped.map((entry) => entry.capability.name).join(", ")}.
        </p>
      ) : null}
    </section>
  );
}
