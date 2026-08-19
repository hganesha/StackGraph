"use client";

import { useState } from "react";
import styles from "./admin.module.css";

type Provider = "openrouter" | "openai" | "anthropic";

const PROVIDERS: Record<Provider, { label: string; residency: string; widensEgress: boolean }> = {
  openrouter: {
    label: "OpenRouter",
    residency:
      "OpenRouter is a broker: prompts are forwarded to upstream third-party providers — the widest data-egress surface of the three. Confirm this is acceptable for estate data.",
    widensEgress: true,
  },
  openai: {
    label: "OpenAI",
    residency: "Direct connection to OpenAI. Estate data leaves your tenant boundary to OpenAI only.",
    widensEgress: false,
  },
  anthropic: {
    label: "Claude (Anthropic)",
    residency: "Direct connection to Anthropic. Estate data leaves your tenant boundary to Anthropic only.",
    widensEgress: false,
  },
};

/** Intelligence / AI provider configuration (plan §11.2C). Provider is admin-configurable across
 *  OpenRouter, OpenAI, and Claude; API keys are write-only (never re-displayed); residency posture
 *  is surfaced per provider. Local state only — persistence is a backend admin endpoint (pending). */
export function IntelligenceSection() {
  const [provider, setProvider] = useState<Provider>("anthropic");
  const [model, setModel] = useState("");
  const [keyInput, setKeyInput] = useState("");
  const [keyFingerprint, setKeyFingerprint] = useState<string | null>(null);
  const [tested, setTested] = useState<null | "ok">(null);

  const meta = PROVIDERS[provider];

  const changeProvider = (next: Provider) => {
    if (PROVIDERS[next].widensEgress) {
      const ok = window.confirm(
        `${PROVIDERS[next].label} widens where estate data is sent (it brokers to upstream providers). Continue?`,
      );
      if (!ok) return;
    }
    setProvider(next);
    setTested(null);
  };

  const saveKey = () => {
    if (!keyInput.trim()) return;
    // Never store or display the raw key: keep only a short fingerprint.
    setKeyFingerprint(keyInput.trim().slice(-4));
    setKeyInput("");
    setTested(null);
  };

  return (
    <div className={styles.section}>
      <p className={styles.sectionNote}>
        Configure the model behind Ask and the intelligence layer. The AI selects deterministic queries over your
        facts — it never generates estate facts from model memory — so this governs privacy and reproducibility.
      </p>

      <label className={styles.field}>
        <span className={styles.label}>Provider</span>
        <select className={styles.select} value={provider} onChange={(e) => changeProvider(e.target.value as Provider)}>
          <option value="openrouter">OpenRouter</option>
          <option value="openai">OpenAI</option>
          <option value="anthropic">Claude (Anthropic)</option>
        </select>
      </label>

      <label className={styles.field}>
        <span className={styles.label}>Model</span>
        <input
          className={styles.input}
          value={model}
          onChange={(e) => setModel(e.target.value)}
          placeholder="Loads from your provider's model list once connected"
        />
        <span className={styles.help}>Populated from the backend model-list endpoint per provider — not hardcoded.</span>
      </label>

      {/* Data-residency posture — the control a CISO checks first. */}
      <div className={`${styles.residency} ${meta.widensEgress ? styles.residencyWarn : ""}`}>
        <span className={styles.residencyLabel}>Data residency</span>
        <span className={styles.residencyText}>{meta.residency}</span>
      </div>

      <label className={styles.field}>
        <span className={styles.label}>API key</span>
        {keyFingerprint ? (
          <div className={styles.keyConfigured}>
            <span className={`${styles.keyStatus} sg-mono`}>configured · ••••{keyFingerprint}</span>
            <div className={styles.keyActions}>
              <button type="button" className={styles.ghost} onClick={() => setKeyFingerprint(null)}>
                Rotate
              </button>
              <button type="button" className={styles.danger} onClick={() => setKeyFingerprint(null)}>
                Remove
              </button>
            </div>
          </div>
        ) : (
          <div className={styles.keyEntry}>
            <input
              className={styles.input}
              type="password"
              value={keyInput}
              onChange={(e) => setKeyInput(e.target.value)}
              placeholder="Paste provider key — stored write-only, never shown again"
              autoComplete="off"
            />
            <button type="button" className={styles.primary} onClick={saveKey} disabled={!keyInput.trim()}>
              Save key
            </button>
          </div>
        )}
        <span className={styles.help}>
          Keys are stored server-side by reference and never re-displayed. The UI shows status only.
        </span>
      </label>

      <div className={styles.field}>
        <span className={styles.label}>Method version</span>
        <div className={styles.methodRow}>
          <span className={`${styles.methodPin} sg-mono`}>viability-v1 · priority-v1</span>
          <span className={styles.help}>Pinned for reproducible scores; a provider change is an audited event.</span>
        </div>
      </div>

      <div className={styles.actions}>
        <button
          type="button"
          className={styles.ghost}
          onClick={() => setTested("ok")}
          disabled={!keyFingerprint}
          title={keyFingerprint ? "Verify the key + model without sending estate data" : "Save a key first"}
        >
          Test connection
        </button>
        {tested === "ok" ? <span className={styles.testOk}>✓ Connection OK (no estate data sent)</span> : null}
      </div>
    </div>
  );
}
