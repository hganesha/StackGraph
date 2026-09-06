"use client";

import { IconCommand, IconRoute, IconShieldCheck } from "@tabler/icons-react";
import { config } from "@stackgraph/shared";
import styles from "./simulate.module.css";

export default function SimulatePage() {
  const openCommand = () => window.dispatchEvent(new Event("stackgraph:open-change-command"));

  return (
    <div className={styles.page}>
      <header className={styles.hero}>
        <span className={styles.eyebrow}>Change simulator</span>
        <h1>Know the impact before the estate changes.</h1>
        <p>
          Build a bounded mutation from entities StackGraph has actually observed, then inspect deterministic findings separately from AI interpretation.
        </p>
        <button type="button" onClick={openCommand} disabled={!config.phase2ChangesEnabled}>
          Plan a change <kbd>⌘K</kbd>
        </button>
        {!config.phase2ChangesEnabled ? <small>Change simulation is not enabled for this tenant.</small> : null}
      </header>

      <section className={styles.principles} aria-label="How simulation works">
        <article>
          <IconCommand size={20} stroke={1.5} aria-hidden="true" />
          <h2>Compile</h2>
          <p>Actions, subjects, targets, and scopes come from the estate—not generated suggestions.</p>
        </article>
        <article>
          <IconRoute size={20} stroke={1.5} aria-hidden="true" />
          <h2>Simulate</h2>
          <p>A pinned policy follows evidence-backed paths and records where traversal deliberately stops.</p>
        </article>
        <article>
          <IconShieldCheck size={20} stroke={1.5} aria-hidden="true" />
          <h2>Decide</h2>
          <p>Deterministic findings remain available when interpretation is absent, unavailable, or quarantined.</p>
        </article>
      </section>

      <aside className={styles.note}>
        <strong>Simulation does not execute changes.</strong>
        <span>Phase 2A–2E surfaces are read and review controls only.</span>
      </aside>
    </div>
  );
}
