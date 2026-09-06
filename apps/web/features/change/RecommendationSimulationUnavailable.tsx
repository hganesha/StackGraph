"use client";

import { useId } from "react";
import { IconPlayerPlay } from "@tabler/icons-react";
import styles from "./simulate-recommendation.module.css";

export function RecommendationSimulationUnavailable({ reason }: { reason: string }) {
  const reasonId = useId();
  return (
    <div className={styles.wrap}>
      <button type="button" className={`${styles.button} ${styles.compact}`} disabled aria-describedby={reasonId}>
        <IconPlayerPlay size={13} stroke={1.75} aria-hidden="true" />
        Simulate
      </button>
      <small id={reasonId} title={reason}>Not simulatable: {reason}</small>
    </div>
  );
}
