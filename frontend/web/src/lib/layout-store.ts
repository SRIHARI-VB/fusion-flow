import { create } from "zustand";

/**
 * App-shell layout preferences — separate from `auth-store.ts` (which is
 * deliberately in-memory-only for security reasons that don't apply here).
 * Two independent concerns:
 *
 * - `sidebarCollapsed`: a durable user preference (persisted to
 *   localStorage, restored on every load) — the global nav rail stays
 *   collapsed/expanded exactly how the user last left it.
 * - `fullView`: a per-editing-session concern (NOT persisted — always
 *   starts `false` on a fresh page load, and `WorkflowEditorPage.tsx`
 *   resets it to `false` on unmount too) so leaving the workflow editor
 *   while in full view never strands another page chrome-less.
 */

const SIDEBAR_COLLAPSED_KEY = "fusionflow.sidebarCollapsed";

function readPersistedSidebarCollapsed(): boolean {
  try {
    return localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === "true";
  } catch {
    // Storage can throw in a locked-down/private-browsing context - a
    // missing preference just falls back to "expanded," never a crash.
    return false;
  }
}

interface LayoutState {
  sidebarCollapsed: boolean;
  toggleSidebarCollapsed: () => void;
  fullView: boolean;
  setFullView: (fullView: boolean) => void;
}

export const useLayoutStore = create<LayoutState>((set, get) => ({
  sidebarCollapsed: readPersistedSidebarCollapsed(),
  toggleSidebarCollapsed: () => {
    const next = !get().sidebarCollapsed;
    try {
      localStorage.setItem(SIDEBAR_COLLAPSED_KEY, String(next));
    } catch {
      // Best-effort persistence only - the in-memory toggle itself must
      // still work even if storage is unavailable.
    }
    set({ sidebarCollapsed: next });
  },
  fullView: false,
  setFullView: (fullView) => set({ fullView }),
}));
