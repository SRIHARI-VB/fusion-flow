import { create } from "zustand";
import { confirmStepUpPassword } from "./endpoints";

/**
 * In-memory-only doctor step-up session (clinic-queue module) - same
 * non-persisted security posture as `auth-store.ts`'s main access token,
 * and for the same reason: a value that disappears on reload is a much
 * smaller blast radius than one sitting in localStorage/sessionStorage.
 * A hard reload always re-prompts a doctor for their password, by design.
 */
interface StepUpAuthState {
  token: string | null;
  expiresAt: string | null;
  isConfirming: boolean;
  error: string | null;
  isValid: () => boolean;
  confirmPassword: (password: string) => Promise<void>;
  clear: () => void;
}

export const useStepUpAuth = create<StepUpAuthState>((set, get) => ({
  token: null,
  expiresAt: null,
  isConfirming: false,
  error: null,
  isValid: () => {
    const { token, expiresAt } = get();
    if (!token || !expiresAt) return false;
    return new Date(expiresAt).getTime() > Date.now();
  },
  confirmPassword: async (password: string) => {
    set({ isConfirming: true, error: null });
    try {
      const result = await confirmStepUpPassword(password);
      set({ token: result.step_up_token, expiresAt: result.expires_at, isConfirming: false });
    } catch {
      // Deliberately generic - the backend's 401 body isn't surfaced verbatim
      // here (avoids leaking whether the account/password guess was "close"),
      // matching the same caution the main Login page's error handling uses.
      set({ isConfirming: false, error: "Incorrect password. Please try again." });
      throw new Error("step-up confirmation failed");
    }
  },
  clear: () => set({ token: null, expiresAt: null, error: null }),
}));

/** Non-hook accessor for use outside React (e.g. the axios interceptor
 * that attaches `X-Step-Up-Token` - see `api-client.ts`). */
export function getStepUpAuthState() {
  return useStepUpAuth.getState();
}
