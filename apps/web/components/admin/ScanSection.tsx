"use client";

import { useState } from "react";
import styles from "./admin.module.css";

/** Scan & Refresh — tenant policy (plan §11.2B): cadence, manual rescan, reconciliation. */
export function ScanSection() {
  const [cadence, setCadence] = useState("daily");
  const [rescanning, setRescanning] = useState(false);

  return (
    <div className={styles.section}>
      <p className={styles.sectionNote}>
        Control how often connected sources are rescanned. The scheduler creates the work; workers never invent
        their own loops.
      </p>

      <label className={styles.field}>
        <span className={styles.label}>Refresh cadence</span>
        <select className={styles.select} value={cadence} onChange={(e) => setCadence(e.target.value)}>
          <option value="hourly">Hourly</option>
          <option value="daily">Daily</option>
          <option value="weekly">Weekly</option>
          <option value="manual">Manual only</option>
        </select>
      </label>

      <div className={styles.field}>
        <span className={styles.label}>Manual rescan</span>
        <button
          type="button"
          className={styles.primary}
          disabled={rescanning}
          onClick={() => {
            setRescanning(true);
            setTimeout(() => setRescanning(false), 1200);
          }}
        >
          {rescanning ? "Queued…" : "Rescan now"}
        </button>
        <span className={styles.help}>Reconciles missed webhook deliveries and re-checks changed repositories.</span>
      </div>

      <div className={styles.field}>
        <span className={styles.label}>Quota &amp; freshness</span>
        <span className={`${styles.methodPin} sg-mono`}>github: 4200/5000 · npm: OK · deps.dev: OK</span>
        <span className={styles.help}>Per-provider quota and backoff state, so throttling reads as intentional, not failure.</span>
      </div>
    </div>
  );
}
