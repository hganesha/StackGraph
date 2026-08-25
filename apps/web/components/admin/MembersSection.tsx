"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiRequestError, stackGraphClient, type MemberRole, type MemberStatus } from "@stackgraph/shared";
import { Skeleton } from "@stackgraph/design-system";
import styles from "./admin.module.css";

const ROLES: MemberRole[] = ["view", "review", "execute", "admin"];

function errorMessage(error: unknown): string {
  if (error instanceof ApiRequestError && error.detail && typeof error.detail === "object") {
    const message = (error.detail as { message?: unknown }).message;
    if (typeof message === "string") return message;
  }
  return error instanceof Error ? error.message : "The request failed.";
}

/** Members & Roles (plan §11.2D, §8.3): the capability tiers view → review → execute → admin. */
export function MembersSection() {
  const queryClient = useQueryClient();
  const members = useQuery({
    queryKey: ["admin", "members"],
    queryFn: () => stackGraphClient.listMembers(),
  });

  const [email, setEmail] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [role, setRole] = useState<MemberRole>("view");
  const [pendingRemoveId, setPendingRemoveId] = useState<string | null>(null);

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["admin", "members"] });

  const invite = useMutation({
    mutationFn: () => stackGraphClient.inviteMember({
      actor_key: email.trim().toLowerCase(),
      display_name: displayName.trim() || undefined,
      email: email.trim(),
      role,
    }),
    onSuccess: () => {
      setEmail("");
      setDisplayName("");
      setRole("view");
      return invalidate();
    },
  });

  const updateRole = useMutation({
    mutationFn: ({ id, role: nextRole }: { id: string; role: MemberRole }) =>
      stackGraphClient.updateMember(id, { role: nextRole }),
    onSuccess: invalidate,
  });

  const updateStatus = useMutation({
    mutationFn: ({ id, status }: { id: string; status: MemberStatus }) =>
      stackGraphClient.updateMember(id, { status }),
    onSuccess: invalidate,
  });

  const removeMember = useMutation({
    mutationFn: (id: string) => stackGraphClient.removeMember(id),
    onSuccess: () => {
      setPendingRemoveId(null);
      return invalidate();
    },
  });

  return (
    <div className={styles.section}>
      <p className={styles.sectionNote}>
        Roles gate what each member can do: <span className="sg-mono">view</span> →{" "}
        <span className="sg-mono">review</span> → <span className="sg-mono">execute</span> →{" "}
        <span className="sg-mono">admin</span>. Least-privilege by default. SSO/OIDC configured here.
      </p>

      <form
        className={styles.connectForm}
        onSubmit={(event) => {
          event.preventDefault();
          if (!email.trim() || invite.isPending) return;
          invite.mutate();
        }}
      >
        <div className={styles.inviteRow}>
          <label className={styles.field}>
            <span className={styles.label}>Email</span>
            <input
              className={styles.input}
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder="name@company.com"
              required
            />
          </label>
          <label className={styles.field}>
            <span className={styles.label}>
              Name <span className={styles.optional}>(optional)</span>
            </span>
            <input
              className={styles.input}
              value={displayName}
              onChange={(event) => setDisplayName(event.target.value)}
              placeholder="Full name"
            />
          </label>
          <label className={styles.field}>
            <span className={styles.label}>Role</span>
            <select
              className={styles.select}
              value={role}
              onChange={(event) => setRole(event.target.value as MemberRole)}
            >
              {ROLES.map((option) => <option key={option} value={option}>{option}</option>)}
            </select>
          </label>
          <button type="submit" className={styles.primary} disabled={!email.trim() || invite.isPending}>
            {invite.isPending ? "Inviting…" : "Invite member"}
          </button>
        </div>
        {invite.isError ? <p className={styles.error} role="alert">{errorMessage(invite.error)}</p> : null}
      </form>

      {members.isLoading ? (
        <div className={styles.memberList}>
          <Skeleton height={52} />
          <Skeleton height={52} />
        </div>
      ) : members.isError ? (
        <p className={styles.error} role="alert">{errorMessage(members.error)}</p>
      ) : !members.data || members.data.members.length === 0 ? (
        <p className={styles.empty}>No members yet. Invite one above.</p>
      ) : (
        <ul className={styles.memberList}>
          {members.data.members.map((m) => (
            <li key={m.id} className={styles.memberItem}>
              <div className={styles.memberMain}>
                <span className={styles.memberName}>{m.display_name || m.email || m.actor_key}</span>
                {m.email ? <span className={`${styles.memberEmail} sg-mono`}>{m.email}</span> : null}
              </div>
              <div className={styles.memberRight}>
                <span className={`${styles.memberStatus} ${styles[`memberStatus${m.status}`]}`}>
                  {m.status.toLowerCase()}
                </span>
                <select
                  className={`${styles.select} ${styles.memberRoleSelect}`}
                  value={m.role}
                  disabled={updateRole.isPending && updateRole.variables?.id === m.id}
                  onChange={(event) => updateRole.mutate({ id: m.id, role: event.target.value as MemberRole })}
                >
                  {ROLES.map((option) => <option key={option} value={option}>{option}</option>)}
                </select>
                {m.status === "SUSPENDED" ? (
                  <button
                    type="button"
                    className={styles.ghost}
                    disabled={updateStatus.isPending && updateStatus.variables?.id === m.id}
                    onClick={() => updateStatus.mutate({ id: m.id, status: "ACTIVE" })}
                  >
                    Reactivate
                  </button>
                ) : (
                  <button
                    type="button"
                    className={styles.ghost}
                    disabled={updateStatus.isPending && updateStatus.variables?.id === m.id}
                    onClick={() => updateStatus.mutate({ id: m.id, status: "SUSPENDED" })}
                  >
                    Suspend
                  </button>
                )}
                {pendingRemoveId === m.id ? (
                  <>
                    <span className={styles.help}>Remove?</span>
                    <button
                      type="button"
                      className={styles.danger}
                      disabled={removeMember.isPending}
                      onClick={() => removeMember.mutate(m.id)}
                    >
                      {removeMember.isPending ? "Removing…" : "Confirm"}
                    </button>
                    <button type="button" className={styles.ghost} onClick={() => setPendingRemoveId(null)}>
                      Cancel
                    </button>
                  </>
                ) : (
                  <button type="button" className={styles.danger} onClick={() => setPendingRemoveId(m.id)}>
                    Remove
                  </button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
      {updateRole.isError || updateStatus.isError || removeMember.isError ? (
        <p className={styles.error} role="alert">
          {errorMessage(updateRole.error ?? updateStatus.error ?? removeMember.error)}
        </p>
      ) : null}

      <button type="button" className={styles.ghost}>
        Configure SSO / OIDC
      </button>
    </div>
  );
}
