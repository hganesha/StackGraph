"use client";

import { useState } from "react";
import type { FormEvent } from "react";
import { ApiRequestError, stackGraphClient } from "@stackgraph/shared";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import styles from "./admin.module.css";

function errorMessage(error: unknown): string {
  if (error instanceof ApiRequestError && error.detail && typeof error.detail === "object") {
    const message = (error.detail as { message?: unknown }).message;
    if (typeof message === "string") return message;
  }
  return error instanceof Error ? error.message : "The connection could not be saved.";
}

const PROVIDER_LABELS = {
  GITHUB_APP: "GitHub",
  PACKAGE_REGISTRY: "Package registry",
  DEPS_DEV: "deps.dev",
  OSV: "OSV",
  OTHER: "Other",
} as const;

/** Connections — onboarding home (plan §11.2A). The UI registers authorized App installations
 *  and stores only a credential reference; it never accepts or displays a raw token. */
export function ConnectionsSection() {
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [repository, setRepository] = useState("");
  const [installationId, setInstallationId] = useState("");
  const [installationName, setInstallationName] = useState("");
  const [connectionMode, setConnectionMode] = useState<"installation" | "repository">("installation");
  const [connectedRepository, setConnectedRepository] = useState<string | null>(null);
  const connectors = useQuery({
    queryKey: ["admin", "connectors"],
    queryFn: () => stackGraphClient.listConnectors(),
  });
  const connect = useMutation({
    mutationFn: () => stackGraphClient.connectGitHubRepository({ repository: repository.trim() }),
    onSuccess: async (connector) => {
      setConnectedRepository(connector.display_name);
      setRepository("");
      setShowForm(false);
      await queryClient.invalidateQueries({ queryKey: ["admin"] });
    },
  });
  const connectInstallation = useMutation({
    mutationFn: () => stackGraphClient.connectGitHubInstallation({
      installation_id: installationId.trim(),
      ...(installationName.trim() ? { display_name: installationName.trim() } : {}),
    }),
    onSuccess: async (connector) => {
      setConnectedRepository(connector.display_name);
      setInstallationId("");
      setInstallationName("");
      setShowForm(false);
      await queryClient.invalidateQueries({ queryKey: ["admin"] });
    },
  });
  const disconnect = useMutation({
    mutationFn: (id: string) => stackGraphClient.removeConnector(id),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["admin"] });
    },
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    setConnectedRepository(null);
    if (connectionMode === "installation") connectInstallation.mutate();
    else connect.mutate();
  }

  const connectionPending = connect.isPending || connectInstallation.isPending;
  const connectionError = connect.error ?? connectInstallation.error;

  return (
    <div className={styles.section}>
      <p className={styles.sectionNote}>
        Connect source and registry providers. StackGraph stores only a credential reference — never a raw token,
        PAT, or password. Read-only scopes are requested.
      </p>

      <button type="button" className={styles.primaryWide} onClick={() => setShowForm((open) => !open)}>
        {showForm ? "Cancel GitHub connection" : "+ Connect GitHub"}
      </button>

      {showForm ? (
        <form className={styles.connectForm} onSubmit={submit}>
          <div className={styles.modeSwitch} role="group" aria-label="GitHub connection type">
            <button
              type="button"
              className={`${styles.modeButton} ${connectionMode === "installation" ? styles.modeButtonActive : ""}`}
              aria-pressed={connectionMode === "installation"}
              onClick={() => {
                connect.reset();
                connectInstallation.reset();
                setConnectionMode("installation");
              }}
            >
              GitHub App installation
            </button>
            <button
              type="button"
              className={`${styles.modeButton} ${connectionMode === "repository" ? styles.modeButtonActive : ""}`}
              aria-pressed={connectionMode === "repository"}
              onClick={() => {
                connect.reset();
                connectInstallation.reset();
                setConnectionMode("repository");
              }}
            >
              Development token
            </button>
          </div>
          {connectionMode === "installation" ? (
            <>
              <label className={styles.field}>
                <span className={styles.label}>Installation ID</span>
                <input
                  className={styles.input}
                  value={installationId}
                  onChange={(event) => setInstallationId(event.target.value)}
                  placeholder="12345678"
                  pattern="[1-9][0-9]*"
                  maxLength={20}
                  inputMode="numeric"
                  autoComplete="off"
                  required
                />
                <span className={styles.help}>Shown in the GitHub App installation URL after `/installations/`.</span>
              </label>
              <label className={styles.field}>
                <span className={styles.label}>Connection name <span className={styles.optional}>(optional)</span></span>
                <input
                  className={styles.input}
                  value={installationName}
                  onChange={(event) => setInstallationName(event.target.value)}
                  placeholder="Acme engineering"
                  maxLength={255}
                  autoComplete="off"
                />
              </label>
            </>
          ) : (
            <label className={styles.field}>
              <span className={styles.label}>Repository</span>
              <input
                className={styles.input}
                value={repository}
                onChange={(event) => setRepository(event.target.value)}
                placeholder="owner/repository"
                pattern="[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+"
                autoComplete="off"
                required
              />
            </label>
          )}
          <div className={styles.residency}>
            <span className={styles.residencyLabel}>Credential boundary</span>
            <span className={styles.residencyText}>
              {connectionMode === "installation" ? (
                <>The worker mints short-lived installation tokens from the deployment’s GitHub App key. Neither the key nor tokens enter this form or the database.</>
              ) : (
                <>Set <span className="sg-mono">GITHUB_TOKEN</span> in the pipeline environment. StackGraph saves only <span className="sg-mono">env://GITHUB_TOKEN</span>.</>
              )}
            </span>
          </div>
          <button
            type="submit"
            className={styles.primary}
            disabled={connectionPending || (connectionMode === "installation" ? !installationId.trim() : !repository.trim())}
          >
            {connectionPending ? "Connecting…" : "Connect and queue first scan"}
          </button>
          {connectionError ? <p className={styles.error} role="alert">{errorMessage(connectionError)}</p> : null}
        </form>
      ) : null}

      {connectedRepository ? (
        <p className={styles.success} role="status">
          {connectedRepository} is connected and its first scan is queued.
        </p>
      ) : null}

      <ul className={styles.connList}>
        {connectors.data?.connectors.map((connector) => {
          const broken = connector.status !== "CONNECTED";
          return (
            <li key={connector.id} className={styles.connItem}>
              <div className={styles.connMain}>
                <span className={styles.connName}>{connector.display_name}</span>
                <span className={styles.connMeta}>
                  {PROVIDER_LABELS[connector.provider]} · <span className="sg-mono">{connector.scopes.join(", ") || "no scopes reported"}</span>
                </span>
                <span className={styles.connMeta}>{connector.external_account_key}</span>
                {connector.last_synced_at ? (
                  <span className={styles.connMeta}>Last sync {new Date(connector.last_synced_at).toLocaleString()}</span>
                ) : null}
                {connector.last_error ? <span className={styles.connError}>{connector.last_error}</span> : null}
              </div>
              <div className={styles.connRight}>
                <span className={`${styles.connStatus} ${broken ? styles.connBroken : styles.connOk}`}>
                  {connector.status.toLowerCase().replaceAll("_", " ")}
                </span>
                <button
                  type="button"
                  className={styles.linkButton}
                  disabled={disconnect.isPending}
                  onClick={() => disconnect.mutate(connector.id)}
                >
                  Disconnect
                </button>
              </div>
            </li>
          );
        })}
      </ul>
      {connectors.isLoading ? <p className={styles.empty}>Loading connections…</p> : null}
      {connectors.isError ? <p className={styles.error} role="alert">{errorMessage(connectors.error)}</p> : null}
      {!connectors.isLoading && connectors.data?.connectors.length === 0 ? (
        <p className={styles.empty}>No providers are connected yet.</p>
      ) : null}
      {disconnect.isError ? <p className={styles.error} role="alert">{errorMessage(disconnect.error)}</p> : null}
    </div>
  );
}
