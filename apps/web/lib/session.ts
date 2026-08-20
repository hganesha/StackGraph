"use client";

// Session/capability model backed by the API's GET /session. Capabilities follow a graded
// ladder view → review → execute → admin (each tier implies the earlier ones), enforced
// server-side in apps/api/app/auth.py. In fixture mode the client returns a full-capability
// admin so every surface stays demoable.
import { useQuery } from "@tanstack/react-query";
import { stackGraphClient, type Capability } from "@stackgraph/shared";

export type { Capability };

const CAPABILITY_LADDER: Capability[] = ["view", "review", "execute", "admin"];

export interface Session {
  tenant: string | null;
  actorKey: string | null;
  capabilities: Capability[];
  /** True once the session fetch has settled (success or failure). */
  ready: boolean;
}

function useSessionQuery() {
  return useQuery({
    queryKey: ["session"],
    queryFn: () => stackGraphClient.getSession(),
    staleTime: 5 * 60_000,
  });
}

export function useSession(): Session {
  const { data, isSuccess, isError } = useSessionQuery();
  return {
    tenant: data?.tenant_id ?? null,
    actorKey: data?.actor_key ?? null,
    capabilities: data?.capabilities ?? [],
    ready: isSuccess || isError,
  };
}

export function useCan(capability: Capability): boolean {
  const { capabilities } = useSession();
  const highest = Math.max(
    -1,
    ...capabilities.map((held) => CAPABILITY_LADDER.indexOf(held)),
  );
  return highest >= CAPABILITY_LADDER.indexOf(capability);
}
