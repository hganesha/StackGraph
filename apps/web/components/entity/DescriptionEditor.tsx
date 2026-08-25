"use client";

import { useState } from "react";
import { useMutation, useQueryClient, type QueryKey } from "@tanstack/react-query";
import { stackGraphClient, type ApplicationDetail, type RepositoryDetail } from "@stackgraph/shared";
import styles from "./DescriptionEditor.module.css";

/**
 * The one human-curated field on an application/repository: a short description an
 * owner writes themselves. Distinct from discovery-derived text elsewhere on these
 * pages (e.g. a repository's evidence-backed "declared intent") — those stay read-only
 * so a rescan can never silently overwrite what a human corrected.
 */
export function DescriptionEditor({
  kind,
  entityId,
  description,
  queryKey,
}: {
  kind: "application" | "repository";
  entityId: string;
  description?: string;
  queryKey: QueryKey;
}) {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(description ?? "");

  const update = useMutation({
    mutationFn: (next: string) =>
      kind === "application"
        ? stackGraphClient.updateApplication(entityId, { description: next })
        : stackGraphClient.updateRepository(entityId, { description: next }),
    onSuccess: (result) => {
      queryClient.setQueryData<ApplicationDetail | RepositoryDetail>(queryKey, (current) => {
        if (!current) return current;
        return kind === "application"
          ? { ...current, application: { ...(current as ApplicationDetail).application, summary: result.summary } } as ApplicationDetail
          : { ...current, repository: { ...(current as RepositoryDetail).repository, summary: result.summary } } as RepositoryDetail;
      });
      setEditing(false);
    },
  });

  if (editing) {
    return (
      <form
        className={styles.form}
        onSubmit={(event) => {
          event.preventDefault();
          update.mutate(value.trim());
        }}
      >
        <textarea
          className={styles.textarea}
          value={value}
          onChange={(event) => setValue(event.target.value)}
          maxLength={2000}
          rows={3}
          autoFocus
          placeholder="Add a description a teammate would find useful…"
        />
        <div className={styles.actions}>
          <button
            type="button"
            className={styles.ghost}
            disabled={update.isPending}
            onClick={() => {
              setValue(description ?? "");
              setEditing(false);
            }}
          >
            Cancel
          </button>
          <button type="submit" className={styles.primary} disabled={update.isPending}>
            {update.isPending ? "Saving…" : "Save"}
          </button>
        </div>
        {update.isError ? <p className={styles.error}>Couldn’t save the description. Try again.</p> : null}
      </form>
    );
  }

  return (
    <div className={styles.display}>
      {description ? (
        <p className={styles.summary}>{description}</p>
      ) : (
        <p className={styles.placeholder}>No description yet.</p>
      )}
      <button type="button" className={styles.editButton} onClick={() => setEditing(true)}>
        {description ? "Edit" : "Add description"}
      </button>
    </div>
  );
}
