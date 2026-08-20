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

/** Connections — onboarding home (plan §11.2A). The UI orchestrates OAuth/App-install flows and
 *  stores only a credential_reference; it never accepts or displays a raw token. */
export function ConnectionsSection() {
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [repository, setRepository] = useState("");
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
  const disconnect = useMutation({
    mutationFn: (id: string) => stackGraphClient.removeConnector(id),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["admin"] });
    },
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    setConnectedRepository(null);
    connect.mutate();
  }

  return (
    <div className={styles.section}>
      <p className={styles.sectionNote}>
        Connect source and registry providers. StackGraph stores only a credential reference — never a raw token,
        PAT, or password. Read-only scopes are requested.
      </p>

      <button type="button" className={styles.primaryWide} onClick={() => setShowForm((open) => !open)}>
        {showForm ? "Cancel GitHub connection" : "+ Connect a GitHub repository"}
      </button>

      {showForm ? (
        <form className={styles.connectForm} onSubmit={submit}>
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
          <div className={styles.residency}>
            <span className={styles.residencyLabel}>Credential boundary</span>
            <span className={styles.residencyText}>
              Set <span className="sg-mono">GITHUB_TOKEN</span> in the pipeline environment before connecting.
              StackGraph saves only <span className="sg-mono">env://GITHUB_TOKEN</span>; the token never enters this form.
            </span>
          </div>
          <button type="submit" className={styles.primary} disabled={connect.isPending || !repository.trim()}>
            {connect.isPending ? "Connecting…" : "Connect and queue first scan"}
          </button>
          {connect.isError ? <p className={styles.error} role="alert">{errorMessage(connect.error)}</p> : null}
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
