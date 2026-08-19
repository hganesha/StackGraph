"use client";

// Mock session/capability model (plan §8.3 RBAC). Real capabilities come from the
// authenticated session; in fixture mode we assume an admin so the surfaces are demoable.
export type Capability = "view" | "review" | "execute" | "admin";

export interface Session {
  tenant: string;
  capabilities: Capability[];
}

const MOCK_SESSION: Session = {
  tenant: "StackGraph",
  capabilities: ["view", "review", "execute", "admin"],
};

export function useSession(): Session {
  return MOCK_SESSION;
}

export function useCan(capability: Capability): boolean {
  return MOCK_SESSION.capabilities.includes(capability);
}
