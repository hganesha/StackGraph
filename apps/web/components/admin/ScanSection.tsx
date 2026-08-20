"use client";

import { useState } from "react";
import { ApiRequestError, stackGraphClient } from "@stackgraph/shared";
import type { ScanCadence } from "@stackgraph/shared";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import styles from "./admin.module.css";

function errorMessage(error: unknown): string {
  if (error instanceof ApiRequestError && error.detail && typeof error.detail === "object") {
    const message = (error.detail as { message?: unknown }).message;
    if (typeof message === "string") return message;
  }
  return error instanceof Error ? error.message : "The scan request failed.";
}

/** Scan & Refresh — tenant policy (plan §11.2B): cadence, manual rescan, reconciliation. */
export function ScanSection() {
  const queryClient = useQueryClient();
  const [pendingCadence, setPendingCadence] = useState<ScanCadence | null>(null);
  const status = useQuery({
    queryKey: ["admin", "scan-status"],
    queryFn: () => stackGraphClient.getScanStatus(),
  });
  const cadence = pendingCadence ?? status.data?.policy.cadence ?? "DAILY";
  const savePolicy = useMutation({
    mutationFn: (next: ScanCadence) => stackGraphClient.updateScanPolicy({
      cadence: next,
      enabled: true,
    }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["admin", "scan-status"] });
      setPendingCadence(null);
    },
    onError: () => setPendingCadence(null),
  });
  const rescan = useMutation({
    mutationFn: () => stackGraphClient.requestRescan({
      idempotency_key: globalThis.crypto.randomUUID(),
      reason: "Manual rescan from Admin",
    }),
    onSuccess: async () => queryClient.invalidateQueries({ queryKey: ["admin", "scan-status"] }),
  });

  function changeCadence(next: ScanCadence) {
    setPendingCadence(next);
    savePolicy.mutate(next);
  }

  return (
    <div className={styles.section}>
      <p className={styles.sectionNote}>
        Control how often connected sources are rescanned. The scheduler creates the work; workers never invent
        their own loops.
      </p>

      <label className={styles.field}>
        <span className={styles.label}>Refresh cadence</span>
        <select
          className={styles.select}
          value={cadence}
          disabled={savePolicy.isPending || status.isLoading}
          onChange={(event) => changeCadence(event.target.value as ScanCadence)}
        >
          <option value="HOURLY">Hourly</option>
          <option value="DAILY">Daily</option>
          <option value="WEEKLY">Weekly</option>
          <option value="MANUAL">Manual only</option>
        </select>
        {savePolicy.isPending ? <span className={styles.help}>Saving policy…</span> : null}
      </label>

      <div className={styles.field}>
        <span className={styles.label}>Manual rescan</span>
        <button
          type="button"
          className={styles.primary}
          disabled={rescan.isPending}
          onClick={() => rescan.mutate()}
        >
          {rescan.isPending ? "Queuing…" : "Rescan now"}
        </button>
        <span className={styles.help}>Reconciles missed webhook deliveries and re-checks changed repositories.</span>
        {rescan.isSuccess ? <span className={styles.success}>Rescan queued.</span> : null}
      </div>

      <div className={styles.field}>
        <span className={styles.label}>Quota &amp; freshness</span>
        <span className={`${styles.methodPin} sg-mono`}>
          {status.data?.quotas.length
            ? status.data.quotas.map((quota) => `${quota.provider.toLowerCase()}: ${quota.used}/${quota.limit ?? "∞"} ${quota.status}`).join(" · ")
            : "No provider quota observations yet"}
        </span>
        <span className={styles.help}>Per-provider quota and backoff state, so throttling reads as intentional, not failure.</span>
      </div>
      {status.data?.recent_jobs[0] ? (
        <div className={styles.field}>
          <span className={styles.label}>Latest rescan</span>
          <span className={`${styles.methodPin} sg-mono`}>
            {status.data.recent_jobs[0].status.toLowerCase()} · {status.data.recent_jobs[0].reason || "manual request"}
          </span>
        </div>
      ) : null}
      {status.isError || savePolicy.isError || rescan.isError ? (
        <p className={styles.error} role="alert">
          {errorMessage(status.error ?? savePolicy.error ?? rescan.error)}
        </p>
      ) : null}
    </div>
  );
}
