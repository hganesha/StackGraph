"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { IconChecklist, IconLayoutGrid } from "@tabler/icons-react";
import type { ArchitectureProfileSummary, TenantCellPolicyModel } from "@stackgraph/shared";
import { APPLICABILITY_LABEL } from "@stackgraph/canvas-ui";
import {
  DEFAULT_REFERENCE_MODEL_KEY,
  cellPoliciesFromProjection,
  useArchitectureProfiles,
  useCanvasReferenceModel,
  useCanvasTargetProjection,
  useCreateArchitectureProfile,
  useProfileDetail,
  usePublishArchitectureProfile,
} from "@/lib/canvasQueries";
import styles from "./admin.module.css";

const shortFingerprint = (value: string) => value.replace(/^sha256:/, "").slice(0, 12);
const errorMessage = (error: unknown) =>
  error instanceof Error ? error.message : "Something went wrong.";

/**
 * Admin owns profile lifecycle, permissions, and audit history; the visual editing
 * happens on the Architecture workspace and is not duplicated here (spec §9.3).
 *
 * The list endpoint returns summaries without policy state, and the API publishes no
 * read-by-id, so per-revision policy detail is shown for the revision in force (read
 * back off the target projection) and for any revision this session created or edited.
 * Other revisions show their metadata and say plainly that their contents are not
 * retrievable, rather than rendering an empty table that reads as "no policies".
 */
export function ArchitectureProfilesSection() {
  const referenceModel = useCanvasReferenceModel();
  const profiles = useArchitectureProfiles();
  const target = useCanvasTargetProjection();
  const createDraft = useCreateArchitectureProfile();
  const publish = usePublishArchitectureProfile();
  const [confirmingPublish, setConfirmingPublish] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const all = profiles.data?.profiles ?? [];
  const active = all.find((entry) => entry.status === "ACTIVE") ?? null;
  const selected: ArchitectureProfileSummary | null =
    all.find((entry) => entry.id === selectedId) ?? active ?? all[0] ?? null;
  const selectedDetail = useProfileDetail(selected?.id ?? null);

  const activePolicies = useMemo(() => cellPoliciesFromProjection(target.data), [target.data]);
  const cellLabel = useMemo(() => {
    const lookup = new Map((referenceModel.data?.cells ?? []).map((cell) => [cell.key, cell.label]));
    return (key: string) => lookup.get(key) ?? key;
  }, [referenceModel.data]);

  // Which policies can we show for the selected revision, and can we vouch for them?
  const { policies, provenance } = useMemo((): {
    policies: TenantCellPolicyModel[] | null;
    provenance: string;
  } => {
    if (!selected) return { policies: null, provenance: "" };
    if (selectedDetail?.id === selected.id && selectedDetail.version === selected.version) {
      return { policies: selectedDetail.state.cell_policies ?? [], provenance: "as returned by the last write" };
    }
    if (selected.status === "ACTIVE") {
      return { policies: activePolicies, provenance: "resolved from the effective target projection" };
    }
    return { policies: null, provenance: "" };
  }, [activePolicies, selected, selectedDetail]);

  if (profiles.isLoading) return <p className={styles.empty}>Loading architecture profiles…</p>;
  if (profiles.isError) {
    return <p className={styles.error} role="alert">{errorMessage(profiles.error)}</p>;
  }

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
                <th scope="col">Updated</th>
                <th scope="col">Fingerprint</th>
                <th scope="col"><span className={styles.visuallyHidden}>Actions</span></th>
              </tr>
            </thead>
            <tbody>
              {all.map((profile) => (
                <tr key={profile.id} aria-selected={profile.id === selected?.id}>
                  <th scope="row">
                    {profile.name} <span className="sg-mono">v{profile.version}</span>
                  </th>
                  <td>{profile.status.toLowerCase()}</td>
                  <td>{new Date(profile.updated_at).toLocaleDateString()}</td>
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
                      Inspect<span className={styles.visuallyHidden}> revision {profile.version}</span>
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
            disabled={createDraft.isPending || !referenceModel.data}
            onClick={() =>
              createDraft.mutate({
                profileKey: `enterprise.target.v${(active?.version ?? 0) + 1}`,
                state: {
                  name: `${active?.name ?? "Enterprise architecture standard"} (draft)`,
                  reference_model_key: DEFAULT_REFERENCE_MODEL_KEY,
                  reference_model_version: referenceModel.data?.version ?? "1.0.0",
                  // Seeded from the effective target so a draft starts as a faithful copy.
                  cell_policies: activePolicies,
                  extension_cells: [],
                },
              })
            }
          >
            {createDraft.isPending ? "Creating…" : active ? "New draft from active" : "Create first draft"}
          </button>
          <Link className={styles.linkButton} href="/architecture">
            <IconLayoutGrid size={15} stroke={1.5} aria-hidden="true" /> Edit on the canvas
          </Link>
        </div>
        {createDraft.isError ? (
          <p className={styles.error} role="alert">{errorMessage(createDraft.error)}</p>
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

          {policies === null ? (
            <p className={styles.empty}>
              This revision&apos;s policy contents are not retrievable: the profile list carries
              metadata only, and the API publishes no read for a single revision&apos;s state. Its
              metadata above is accurate; its policies can be seen by making it active, or by
              editing it in this session.
            </p>
          ) : policies.length === 0 ? (
            <p className={styles.empty}>
              This revision overrides nothing, so every cell uses the reference model default.
            </p>
          ) : (
            <>
              <p className={styles.sectionNote}>{policies.length} governed cells, {provenance}.</p>
              <table className={styles.table}>
                <caption className={styles.visuallyHidden}>Cell policies in this revision</caption>
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
                  {policies.map((policy) => {
                    const counts = [
                      [(policy.preferred_technology_ids ?? []).length, "preferred"],
                      [(policy.allowed_technology_ids ?? []).length, "allowed"],
                      [(policy.discouraged_technology_ids ?? []).length, "discouraged"],
                      [(policy.prohibited_technology_ids ?? []).length, "prohibited"],
                    ] as const;
                    return (
                      <tr key={policy.cell_key}>
                        <th scope="row">{cellLabel(policy.cell_key)}</th>
                        <td>{APPLICABILITY_LABEL[policy.applicability ?? "OPTIONAL"]}</td>
                        <td>
                          {policy.minimum_implementations ?? "—"} to{" "}
                          {policy.maximum_implementations ?? "unbounded"}
                        </td>
                        <td>
                          {counts.filter(([n]) => n > 0).map(([n, label]) => `${n} ${label}`).join(", ") || "none"}
                          {(policy.exceptions ?? []).length
                            ? ` · ${(policy.exceptions ?? []).length} exception${(policy.exceptions ?? []).length === 1 ? "" : "s"}`
                            : ""}
                        </td>
                        <td>{policy.owner ?? "unassigned"}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </>
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
                      publish.mutate(
                        { id: selected.id, expectedVersion: selected.version },
                        { onSuccess: () => setConfirmingPublish(null) },
                      )
                    }
                  >
                    {publish.isPending ? "Publishing…" : "Publish revision"}
                  </button>
                  <button type="button" className={styles.ghost} onClick={() => setConfirmingPublish(null)}>
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
            <p className={styles.error} role="alert">{errorMessage(publish.error)}</p>
          ) : null}
        </section>
      ) : null}
    </div>
  );
}
