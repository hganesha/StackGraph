"use client";

// Mock session/capability model (plan §8.3 RBAC). Real capabilities come from the
// authenticated session; in fixture mode we assume an admin so the surfaces are demoable.
// The backend enforces the same graded ladder in apps/api/app/auth.py: holding a tier
// implies every tier before it (view → review → execute → admin).
export type Capability = "view" | "review" | "execute" | "admin";

const CAPABILITY_LADDER: Capability[] = ["view", "review", "execute", "admin"];

export interface Session {
  tenant: string;
  capabilities: Capability[];
}

const MOCK_SESSION: Session = {
  tenant: "StackGraph",
  capabilities: ["admin"],
};

export function useSession(): Session {
  return MOCK_SESSION;
}

export function useCan(capability: Capability): boolean {
  const highest = Math.max(
    -1,
    ...MOCK_SESSION.capabilities.map((held) => CAPABILITY_LADDER.indexOf(held)),
  );
  return highest >= CAPABILITY_LADDER.indexOf(capability);
}
