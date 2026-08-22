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
 *  and stores encrypted credentials through write-only controls; it never displays a raw token. */
export function ConnectionsSection() {
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [repository, setRepository] = useState("");
  const [githubToken, setGitHubToken] = useState("");
  const [installationId, setInstallationId] = useState("");
  const [installationName, setInstallationName] = useState("");
  const [manualBindingAcknowledged, setManualBindingAcknowledged] = useState(false);
  const [connectionMode, setConnectionMode] = useState<"installation" | "repository">("installation");
  const [connectedRepository, setConnectedRepository] = useState<string | null>(null);
  const connectors = useQuery({
    queryKey: ["admin", "connectors"],
    queryFn: () => stackGraphClient.listConnectors(),
  });
  const availableRepositories = useQuery({
    queryKey: ["admin", "github", "repositories", "available"],
    queryFn: () => stackGraphClient.listAvailableGitHubRepositories(),
    enabled: showForm && connectionMode === "repository",
    staleTime: 30_000,
  });
  const tokenConfiguration = useQuery({
    queryKey: ["admin", "github", "token"],
    queryFn: () => stackGraphClient.getGitHubTokenConfiguration(),
    enabled: showForm && connectionMode === "repository",
  });
  const saveToken = useMutation({
    mutationFn: () => stackGraphClient.updateGitHubToken({ token: githubToken }),
    onSuccess: async () => {
      setGitHubToken("");
      await queryClient.invalidateQueries({ queryKey: ["admin", "github"] });
    },
  });
  const removeToken = useMutation({
    mutationFn: () => stackGraphClient.removeGitHubToken(),
    onSuccess: async () => {
      setRepository("");
      await queryClient.invalidateQueries({ queryKey: ["admin", "github"] });
    },
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
      pilot_manual_binding_acknowledged: true,
      ...(installationName.trim() ? { display_name: installationName.trim() } : {}),
    }),
    onSuccess: async (connector) => {
      setConnectedRepository(connector.display_name);
      setInstallationId("");
      setInstallationName("");
      setManualBindingAcknowledged(false);
      setShowForm(false);
      await queryClient.invalidateQueries({ queryKey: ["admin"] });
    },
  });
  const hostedSetup = useMutation({
    mutationFn: () => stackGraphClient.startGitHubInstallationSetup({
      return_to: `${window.location.pathname}${window.location.search}`,
    }),
    onSuccess: ({ setup_url }) => window.location.assign(setup_url),
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
  const repositoryAvailable = availableRepositories.data?.repositories.some(
    (option) => option.full_name === repository,
  ) ?? false;

  return (
    <div className={styles.section}>
      <p className={styles.sectionNote}>
        Connect source and registry providers. Tokens are accepted only through write-only controls, encrypted at
        rest, and never displayed. Read-only scopes are requested.
      </p>

      <button type="button" className={styles.primaryWide} onClick={() => setShowForm((open) => !open)}>
        {showForm ? "Cancel GitHub connection" : "+ Connect GitHub"}
      </button>

      {showForm ? (
        <form className={styles.connectForm} onSubmit={submit}>
          <div className={styles.residency}>
            <span className={styles.residencyLabel}>Recommended</span>
            <span className={styles.residencyText}>
              Install through GitHub so StackGraph can verify your GitHub identity, App ownership, permissions,
              and workspace binding before the first scan.
            </span>
            <button
              type="button"
              className={styles.primary}
              disabled={hostedSetup.isPending}
              onClick={() => hostedSetup.mutate()}
            >
              {hostedSetup.isPending ? "Opening GitHub…" : "Install and verify with GitHub"}
            </button>
            {hostedSetup.isError ? <span className={styles.error} role="alert">{errorMessage(hostedSetup.error)}</span> : null}
          </div>
          <p className={styles.sectionNote}>
            Pilot recovery options remain below. Manual installation binding can be disabled by the deployment.
          </p>
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
              Manual pilot binding
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
              <label className={styles.field}>
                <span className={styles.label}>Pilot verification</span>
                <span className={styles.help}>
                  <input
                    type="checkbox"
                    checked={manualBindingAcknowledged}
                    onChange={(event) => setManualBindingAcknowledged(event.target.checked)}
                    required
                  />{" "}
                  I verified that this installation belongs to the current pilot workspace. Hosted GitHub setup remains required for general availability.
                </span>
              </label>
            </>
          ) : (
            <>
            <label className={styles.field}>
              <span className={styles.label}>GitHub token</span>
              <input
                className={styles.input}
                type="password"
                value={githubToken}
                onChange={(event) => setGitHubToken(event.target.value)}
                placeholder={tokenConfiguration.data?.configured ? "Enter a replacement token" : "github_pat_…"}
                minLength={8}
                maxLength={8192}
                autoComplete="new-password"
              />
              <span className={styles.help}>
                {tokenConfiguration.isLoading
                  ? "Checking token configuration…"
                  : tokenConfiguration.data?.configured
                    ? `A ${tokenConfiguration.data.source === "TENANT_SECRET" ? "workspace" : "deployment"} token ending in ${tokenConfiguration.data.fingerprint ?? "••••"} is configured.`
                    : "No GitHub token is configured. Use a fine-grained, read-only token."}
              </span>
              <span className={styles.repositoryPickerActions}>
                <button
                  type="button"
                  className={styles.primary}
                  disabled={saveToken.isPending || githubToken.trim().length < 8}
                  onClick={() => saveToken.mutate()}
                >
                  {saveToken.isPending ? "Saving token…" : tokenConfiguration.data?.configured ? "Replace token" : "Save token"}
                </button>
                {tokenConfiguration.data?.source === "TENANT_SECRET" ? (
                  <button
                    type="button"
                    className={styles.linkButton}
                    disabled={removeToken.isPending}
                    onClick={() => removeToken.mutate()}
                  >
                    {removeToken.isPending ? "Removing…" : "Remove token"}
                  </button>
                ) : null}
              </span>
              {saveToken.isError ? <span className={styles.error} role="alert">{errorMessage(saveToken.error)}</span> : null}
              {removeToken.isError ? <span className={styles.error} role="alert">{errorMessage(removeToken.error)}</span> : null}
            </label>
            <label className={styles.field}>
              <span className={styles.label}>Repository</span>
              <select
                className={styles.select}
                value={repository}
                onChange={(event) => setRepository(event.target.value)}
                disabled={
                  availableRepositories.isLoading
                  || availableRepositories.isFetching
                  || !availableRepositories.data
                  || availableRepositories.data?.token_configured === false
                  || availableRepositories.data?.repositories.length === 0
                }
                required
              >
                <option value="">
                  {availableRepositories.isLoading || availableRepositories.isFetching
                    ? "Loading repositories…"
                    : availableRepositories.data?.token_configured === false
                      ? "Save a GitHub token above"
                      : availableRepositories.data?.repositories.length === 0
                        ? "No unconnected repositories available"
                        : "Select a repository…"}
                </option>
                {availableRepositories.data?.repositories.map((option) => (
                  <option value={option.full_name} key={option.full_name}>
                    {option.full_name}
                    {option.visibility === "public" ? "" : ` · ${option.visibility}`}
                    {option.archived ? " · archived" : ""}
                  </option>
                ))}
              </select>
              <span className={styles.help}>
                {availableRepositories.data?.token_configured === false
                  ? "Save a read-only GitHub token above, then choose a repository."
                  : "Only repositories visible to GITHUB_TOKEN and not already in StackGraph are shown."}
              </span>
              <span className={styles.repositoryPickerActions}>
                <button
                  type="button"
                  className={styles.linkButton}
                  disabled={availableRepositories.isFetching}
                  onClick={() => void availableRepositories.refetch()}
                >
                  Refresh repositories
                </button>
                {availableRepositories.data?.truncated ? "Showing the first 10,000 repositories." : null}
              </span>
              {availableRepositories.isError ? (
                <span className={styles.error} role="alert">{errorMessage(availableRepositories.error)}</span>
              ) : null}
            </label>
            </>
          )}
          <div className={styles.residency}>
            <span className={styles.residencyLabel}>Credential boundary</span>
            <span className={styles.residencyText}>
              {connectionMode === "installation" ? (
                <>The worker mints short-lived installation tokens from the deployment’s GitHub App key. Neither the key nor tokens enter this form or the database.</>
              ) : (
                <>Tokens entered here are encrypted at rest, accepted write-only, and resolved by the scan worker through an opaque workspace secret reference.</>
              )}
            </span>
          </div>
          <button
            type="submit"
            className={styles.primary}
            disabled={connectionPending || (
              connectionMode === "installation"
                ? !installationId.trim() || !manualBindingAcknowledged
                : !repositoryAvailable
            )}
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
