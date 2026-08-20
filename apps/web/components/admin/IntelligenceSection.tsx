"use client";

import { useEffect, useState } from "react";
import { ApiRequestError, stackGraphClient, type AIProvider } from "@stackgraph/shared";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import styles from "./admin.module.css";

const PROVIDERS: Record<AIProvider, { label: string; residency: string; widensEgress: boolean }> = {
  openrouter: {
    label: "OpenRouter",
    residency: "OpenRouter is a broker: prompts are forwarded to upstream third-party providers — the widest data-egress surface of the three. Confirm this is acceptable for estate data.",
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

function errorMessage(error: unknown): string {
  if (error instanceof ApiRequestError && error.detail && typeof error.detail === "object") {
    const message = (error.detail as { message?: unknown }).message;
    if (typeof message === "string") return message;
  }
  return error instanceof Error ? error.message : "The AI configuration could not be saved.";
}

/** Tenant-scoped, write-only AI provider administration. Raw keys exist only in this input until
 * the save request completes; the server returns a fingerprint and never re-displays the key. */
export function IntelligenceSection() {
  const queryClient = useQueryClient();
  const configuration = useQuery({
    queryKey: ["admin", "ai-configuration"],
    queryFn: () => stackGraphClient.getAIProviderConfiguration(),
  });
  const [provider, setProvider] = useState<AIProvider>("anthropic");
  const [model, setModel] = useState("");
  const [keyInput, setKeyInput] = useState("");
  const [rotating, setRotating] = useState(false);
  const [availableModels, setAvailableModels] = useState<string[]>([]);

  useEffect(() => {
    if (!configuration.data) return;
    setProvider(configuration.data.provider);
    setModel(configuration.data.model);
    setRotating(false);
    setKeyInput("");
  }, [configuration.data]);

  const save = useMutation({
    mutationFn: () => stackGraphClient.updateAIProviderConfiguration({
      provider,
      model: model.trim(),
      ...(keyInput.trim() ? { api_key: keyInput.trim() } : {}),
      enabled: true,
    }),
    onSuccess: async (next) => {
      setKeyInput("");
      setRotating(false);
      queryClient.setQueryData(["admin", "ai-configuration"], next);
      await queryClient.invalidateQueries({ queryKey: ["admin", "ai-configuration"] });
    },
  });
  const removeKey = useMutation({
    mutationFn: () => stackGraphClient.removeAIProviderKey(),
    onSuccess: async (next) => {
      setKeyInput("");
      setRotating(false);
      setAvailableModels([]);
      queryClient.setQueryData(["admin", "ai-configuration"], next);
      await queryClient.invalidateQueries({ queryKey: ["admin", "ai-configuration"] });
    },
  });
  const testConnection = useMutation({
    mutationFn: () => stackGraphClient.testAIProviderConnection(),
    onSuccess: async (result) => {
      setAvailableModels(result.models);
      await queryClient.invalidateQueries({ queryKey: ["admin", "ai-configuration"] });
    },
    onError: async () => {
      await queryClient.invalidateQueries({ queryKey: ["admin", "ai-configuration"] });
    },
  });

  const persisted = configuration.data;
  const providerChanged = Boolean(persisted?.key_configured && persisted.provider !== provider);
  const keyEntryVisible = !persisted?.key_configured || rotating || providerChanged;
  const hasDraftChanges = Boolean(
    !persisted || persisted.provider !== provider || persisted.model !== model.trim() || keyInput.trim(),
  );
  const meta = PROVIDERS[provider];

  const changeProvider = (next: AIProvider) => {
    if (next === provider) return;
    if (PROVIDERS[next].widensEgress) {
      const ok = window.confirm(
        `${PROVIDERS[next].label} widens where estate data is sent because it brokers to upstream providers. Continue?`,
      );
      if (!ok) return;
    }
    setProvider(next);
    if (persisted?.key_configured) setRotating(true);
  };

  if (configuration.isLoading) return <p className={styles.empty}>Loading AI configuration…</p>;
  if (configuration.isError) {
    return <p className={styles.error} role="alert">{errorMessage(configuration.error)}</p>;
  }

  return (
    <div className={styles.section}>
      <p className={styles.sectionNote}>
        Configure the model behind Ask and the intelligence layer. The AI selects deterministic queries over your
        facts — it never generates estate facts from model memory — so this governs privacy and reproducibility.
      </p>

      <label className={styles.field}>
        <span className={styles.label}>Provider</span>
        <select className={styles.select} value={provider} onChange={(event) => changeProvider(event.target.value as AIProvider)}>
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
          onChange={(event) => setModel(event.target.value)}
          placeholder="For example: anthropic/claude-sonnet-4"
          list="ai-provider-models"
        />
        <datalist id="ai-provider-models">
          {availableModels.map((id) => <option value={id} key={id} />)}
        </datalist>
        <span className={styles.help}>Test the connection to load model IDs. Ask remains deterministic until a model is selected.</span>
      </label>

      <div className={`${styles.residency} ${meta.widensEgress ? styles.residencyWarn : ""}`}>
        <span className={styles.residencyLabel}>Data residency</span>
        <span className={styles.residencyText}>{meta.residency}</span>
      </div>

      <div className={styles.field}>
        <span className={styles.label}>API key</span>
        {persisted?.key_configured && !keyEntryVisible ? (
          <div className={styles.keyConfigured}>
            <span className={`${styles.keyStatus} sg-mono`}>configured · ••••{persisted.key_fingerprint}</span>
            <div className={styles.keyActions}>
              <button type="button" className={styles.ghost} onClick={() => setRotating(true)}>Rotate</button>
              <button
                type="button"
                className={styles.danger}
                disabled={removeKey.isPending}
                onClick={() => {
                  if (window.confirm("Remove this provider key? Ask will use deterministic mode until another key is saved.")) {
                    removeKey.mutate();
                  }
                }}
              >
                {removeKey.isPending ? "Removing…" : "Remove"}
              </button>
            </div>
          </div>
        ) : (
          <div className={styles.keyEntry}>
            <input
              className={styles.input}
              type="password"
              value={keyInput}
              onChange={(event) => setKeyInput(event.target.value)}
              placeholder={persisted?.key_configured ? "Paste replacement provider key" : "Paste provider key"}
              autoComplete="new-password"
            />
            {persisted?.key_configured && !providerChanged ? (
              <button type="button" className={styles.ghost} onClick={() => { setRotating(false); setKeyInput(""); }}>Cancel</button>
            ) : null}
          </div>
        )}
        <span className={styles.help}>Encrypted server-side and write-only. Only the last four characters are returned as a fingerprint.</span>
        {providerChanged ? <span className={styles.help}>A new key is required when changing providers.</span> : null}
      </div>

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
          className={styles.primary}
          onClick={() => save.mutate()}
          disabled={save.isPending || !hasDraftChanges || (providerChanged && !keyInput.trim())}
        >
          {save.isPending ? "Saving…" : "Save configuration"}
        </button>
        <button
          type="button"
          className={styles.ghost}
          onClick={() => testConnection.mutate()}
          disabled={testConnection.isPending || !persisted?.key_configured || hasDraftChanges}
          title={hasDraftChanges ? "Save changes before testing" : "Verify the key without sending estate data"}
        >
          {testConnection.isPending ? "Testing…" : "Test connection"}
        </button>
        {persisted?.test_status === "SUCCEEDED" ? <span className={styles.testOk}>✓ Connection OK (no estate data sent)</span> : null}
      </div>

      {save.isSuccess ? <p className={styles.success} role="status">AI configuration saved.</p> : null}
      {save.isError ? <p className={styles.error} role="alert">{errorMessage(save.error)}</p> : null}
      {removeKey.isError ? <p className={styles.error} role="alert">{errorMessage(removeKey.error)}</p> : null}
      {testConnection.isError ? <p className={styles.error} role="alert">{errorMessage(testConnection.error)}</p> : null}
      {persisted?.test_status === "FAILED" && persisted.last_error ? <p className={styles.error} role="alert">{persisted.last_error}</p> : null}
    </div>
  );
}
