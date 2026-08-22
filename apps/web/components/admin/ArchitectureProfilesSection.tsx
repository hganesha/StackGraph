"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { IconChecklist, IconLayoutGrid } from "@tabler/icons-react";
import { stackGraphClient, type TenantArchitectureProfile } from "@stackgraph/shared";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { APPLICABILITY_LABEL } from "@stackgraph/canvas-ui";
import {
  DEFAULT_REFERENCE_MODEL_KEY,
  useCanvasReferenceModel,
  usePublishArchitectureProfile,
} from "@/lib/canvasQueries";
import styles from "./admin.module.css";

const shortFingerprint = (value: string) => value.replace(/^sha256:/, "").slice(0, 12);

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : "Something went wrong.";
}

/**
 * Admin owns profile lifecycle, permissions, and audit history; the visual editing
 * happens on the Architecture workspace and is not duplicated here (spec §9.3).
 *
 * What this surface has to make legible is what a canvas cell cannot: which revision
 * is in force, what a draft would change if published, and which migrated policies
 * are still unplaced. Publishing changes what every team may ship, so it is
 * deliberately a two-step confirmation rather than a single button.
 */
export function ArchitectureProfilesSection() {
  const queryClient = useQueryClient();
  const referenceModel = useCanvasReferenceModel();
  const publish = usePublishArchitectureProfile();
  const [confirmingPublish, setConfirmingPublish] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const profiles = useQuery({
    queryKey: ["canvas", "architecture-profiles"],
    queryFn: () => stackGraphClient.listArchitectureProfiles(),
  });

  const createDraft = useMutation({
    mutationFn: (copyFrom: string | undefined) =>
      stackGraphClient.createArchitectureProfile({
        name: "Enterprise architecture standard (draft)",
        reference_model_key: DEFAULT_REFERENCE_MODEL_KEY,
        reference_model_version: referenceModel.data?.version ?? "1.0.0",
        copy_from_profile_id: copyFrom,
      }),
    onSuccess: (created: TenantArchitectureProfile) => {
      setSelectedId(created.id);
      queryClient.invalidateQueries({ queryKey: ["canvas"] });
    },
  });

  const cellLabel = useMemo(() => {
    const lookup = new Map((referenceModel.data?.cells ?? []).map((cell) => [cell.key, cell.label]));
    return (key: string) => lookup.get(key) ?? key;
  }, [referenceModel.data]);

  if (profiles.isLoading) return <p className={styles.empty}>Loading architecture profiles…</p>;
  if (profiles.isError) {
    return (
      <p className={styles.error} role="alert">
        {errorMessage(profiles.error)}
      </p>
    );
  }
  if (!profiles.data) return <p className={styles.empty}>Architecture profile state is unavailable.</p>;

  const all = profiles.data.profiles;
  const active = all.find((entry) => entry.status === "ACTIVE") ?? null;
  const selected = all.find((entry) => entry.id === selectedId) ?? active ?? all[0] ?? null;

  return (
    <div className={styles.section}>
      <p className={styles.sectionNote}>
        The tenant architecture profile overlays canonical reference-model defaults with this
        workspace&apos;s applicability, expectations, and technology decisions. Canonical cell
        meanings are owned by StackGraph and cannot be rebound here — only tailored.
      </p>

      <section className={styles.governanceCard} aria-labelledby="architecture-profile-heading">
        <div className={styles.governanceCardHead}>
          <div>
            <span className={styles.eyebrow}>Tenant profile</span>
            <h2 id="architecture-profile-heading" className={styles.cardTitle}>
              Architecture profile revisions
            </h2>
          </div>
          <span className={styles.statusMuted}>
            {active ? `v${active.version} active` : "no active revision"}
          </span>
        </div>

        {all.length === 0 ? (
          <p className={styles.empty}>
            No profile exists yet. Until one is published every cell falls back to the reference
            model&apos;s defaults and reports as ungoverned, which is a valid starting state.
          </p>
        ) : (
          <table className={styles.table}>
            <caption className={styles.visuallyHidden}>Architecture profile revisions</caption>
            <thead>
              <tr>
                <th scope="col">Revision</th>
                <th scope="col">Status</th>
                <th scope="col">Overrides</th>
                <th scope="col">Updated</th>
                <th scope="col">Fingerprint</th>
                <th scope="col">
                  <span className={styles.visuallyHidden}>Actions</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {all.map((profile) => (
                <tr key={profile.id} aria-selected={profile.id === selected?.id}>
                  <th scope="row">
                    {profile.name} <span className="sg-mono">v{profile.version}</span>
                  </th>
                  <td>{profile.status.toLowerCase()}</td>
                  <td>
                    {profile.cell_overrides.length} cell
                    {profile.cell_overrides.length === 1 ? "" : "s"}
                    {profile.extension_cells.length
                      ? ` · ${profile.extension_cells.length} extension`
                      : ""}
                  </td>
                  <td>
                    {new Date(profile.updated_at).toLocaleDateString()} · {profile.updated_by}
                  </td>
                  <td>
                    <span className="sg-mono" title={profile.fingerprint}>
                      {shortFingerprint(profile.fingerprint)}
                    </span>
                  </td>
                  <td>
                    <button
                      type="button"
                      className={styles.linkButton}
                      onClick={() => setSelectedId(profile.id)}
                    >
                      Inspect
                      <span className={styles.visuallyHidden}> revision {profile.version}</span>
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        <div className={styles.actions}>
          <button
            type="button"
            className={styles.ghost}
            disabled={createDraft.isPending}
            onClick={() => createDraft.mutate(active?.id)}
          >
            {createDraft.isPending ? "Creating…" : active ? "New draft from active" : "Create first draft"}
          </button>
          <Link className={styles.linkButton} href="/architecture">
            <IconLayoutGrid size={15} stroke={1.5} aria-hidden="true" /> Edit on the canvas
          </Link>
        </div>
        {createDraft.isError ? (
          <p className={styles.error} role="alert">
            {errorMessage(createDraft.error)}
          </p>
        ) : null}
      </section>

      {selected ? (
        <section className={styles.governanceCard} aria-labelledby="architecture-profile-detail-heading">
          <div className={styles.governanceCardHead}>
            <div>
              <span className={styles.eyebrow}>Revision {selected.version}</span>
              <h2 id="architecture-profile-detail-heading" className={styles.cardTitle}>
                {selected.name}
              </h2>
            </div>
            <span className={styles.statusMuted}>{selected.status.toLowerCase()}</span>
          </div>

          <p className={styles.sectionNote}>
            Bound to reference model{" "}
            <span className="sg-mono">
              {selected.reference_model_key}@{selected.reference_model_version}
            </span>
            . A revision can only be compared with another built on the same model major version.
          </p>

          {selected.cell_overrides.length === 0 ? (
            <p className={styles.empty}>
              This revision overrides nothing yet, so every cell uses the reference model default.
            </p>
          ) : (
            <table className={styles.table}>
              <caption className={styles.visuallyHidden}>Cell overrides in this revision</caption>
              <thead>
                <tr>
                  <th scope="col">Cell</th>
                  <th scope="col">Applicability</th>
                  <th scope="col">Implementations</th>
                  <th scope="col">Decisions</th>
                  <th scope="col">Owner</th>
                </tr>
              </thead>
              <tbody>
                {selected.cell_overrides.map((override) => {
                  const decisions = [
                    [override.preferred_technology_ids.length, "preferred"],
                    [override.allowed_technology_ids.length, "allowed"],
                    [override.discouraged_technology_ids.length, "discouraged"],
                    [override.prohibited_technology_ids.length, "prohibited"],
                  ] as const;
                  return (
                    <tr key={override.cell_key}>
                      <th scope="row">{cellLabel(override.cell_key)}</th>
                      <td>{APPLICABILITY_LABEL[override.applicability]}</td>
                      <td>
                        {override.minimum_implementations ?? "—"} to{" "}
                        {override.maximum_implementations ?? "unbounded"}
                      </td>
                      <td>
                        {decisions
                          .filter(([count]) => count > 0)
                          .map(([count, label]) => `${count} ${label}`)
                          .join(", ") || "none"}
                        {override.exceptions.length
                          ? ` · ${override.exceptions.length} exception${override.exceptions.length === 1 ? "" : "s"}`
                          : ""}
                      </td>
                      <td>{override.owner ?? "unassigned"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}

          {selected.status === "DRAFT" ? (
            <div className={styles.actions}>
              {confirmingPublish === selected.id ? (
                <>
                  <p className={styles.residencyWarn} role="alert">
                    <IconChecklist size={15} stroke={1.5} aria-hidden="true" /> Publishing makes this
                    revision effective for every scope immediately. Drift and conformance across the
                    estate are recomputed against it.
                  </p>
                  <button
                    type="button"
                    className={styles.primary}
                    disabled={publish.isPending}
                    onClick={() =>
                      publish.mutate(selected.id, { onSuccess: () => setConfirmingPublish(null) })
                    }
                  >
                    {publish.isPending ? "Publishing…" : "Publish revision"}
                  </button>
                  <button
                    type="button"
                    className={styles.ghost}
                    onClick={() => setConfirmingPublish(null)}
                  >
                    Cancel
                  </button>
                </>
              ) : (
                <button
                  type="button"
                  className={styles.primary}
                  onClick={() => setConfirmingPublish(selected.id)}
                >
                  Publish this revision…
                </button>
              )}
            </div>
          ) : null}
          {publish.isError ? (
            <p className={styles.error} role="alert">
              {errorMessage(publish.error)}
            </p>
          ) : null}
        </section>
      ) : null}
    </div>
  );
}
