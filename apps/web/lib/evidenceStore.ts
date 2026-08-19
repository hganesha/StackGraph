import { create } from "zustand";

/**
 * Linked-selection store for the Evidence Drawer (plan §7.3).
 * Any surface can open evidence for a fact; the globally-mounted drawer reacts.
 */
interface EvidenceState {
  factId: string | null;
  label: string | null;
  open: (factId: string, label?: string) => void;
  close: () => void;
}

export const useEvidenceStore = create<EvidenceState>((set) => ({
  factId: null,
  label: null,
  open: (factId, label) => set({ factId, label: label ?? null }),
  close: () => set({ factId: null, label: null }),
}));
