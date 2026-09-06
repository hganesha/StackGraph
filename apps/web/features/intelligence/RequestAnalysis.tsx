"use client";

import { useState } from "react";
import { SIMULATION_STATUS_LABEL } from "@stackgraph/design-system";
import { useRequestGraphAnalysis } from "@/lib/changeQueries";
import styles from "./request-analysis.module.css";

/**
 * Ask for a fresh analysis run when the projection has fallen behind.
 *
 * `POST /graph-intelligence/analysis-requests` shipped with no client method and no
 * control, so an operator watching the projection lag on Scan health could see the
 * problem and had no way to act on it from the product.
 *
 * The response carries `requested_change_watermark`, which is the useful part: it says
 * which point in the estate the run was asked to catch up to, so a second press while
 * one is already queued reads as the same request rather than as a new one.
 */
const STATUS_COPY: Record<string, string> = {
  PENDING: "Queued",
  WAITING_FOR_PROJECTION: "Waiting for the projection to catch up",
};

export function RequestAnalysis({ lag }: { lag: number }) {
  const request = useRequestGraphAnalysis();
  const [result, setResult] = useState<{ status: string; watermark: number } | null>(null);

  // Nothing to catch up to. A control that does nothing is worse than no control.
  if (lag <= 0 && !result) return null;

  return (
    <span className={styles.wrap}>
      <button
        type="button"
        className={styles.button}
        disabled={request.isPending}
        onClick={async () => {
          const created = await request.mutateAsync({
            policy_key: "runtime-dependency",
            reason: "Requested from Scan health because the projection is behind.",
          });
          setResult({
            status: created.status,
            watermark: created.requested_change_watermark,
          });
        }}
      >
        {request.isPending ? "Requesting…" : "Request a fresh analysis"}
      </button>
      {result ? (
        <span className={styles.result}>
          {STATUS_COPY[result.status] ?? SIMULATION_STATUS_LABEL.QUEUED} · catching up to
          change {result.watermark.toLocaleString()}
        </span>
      ) : null}
      {request.isError ? (
        <span className={styles.result} role="alert">
          The request was not accepted. Nothing was queued, so it is safe to try again.
        </span>
      ) : null}
    </span>
  );
}
