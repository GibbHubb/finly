import { create } from "zustand";
import type { User } from "@/types";
import { authService } from "@/services/auth";
import { apiErrorMessage } from "@/utils/errors";

interface AuthState {
  user: User | null;
  token: string | null;
  isLoading: boolean;
  baseCurrency: string;
  /** F55 — why the last base-currency change was refused; null once one succeeds. */
  baseCurrencyError: string | null;
  login: (email: string, password: string) => Promise<void>;
  demoLogin: () => Promise<void>;
  logout: () => void;
  fetchMe: () => Promise<void>;
  setBaseCurrency: (currency: string) => Promise<void>;
}

export const useAuthStore = create<AuthState>((set, get) => ({
  user: null,
  token: localStorage.getItem("token"),
  isLoading: false,
  baseCurrency: "EUR",
  baseCurrencyError: null,

  login: async (email, password) => {
    // F37 — isLoading is reset on FAILURE too. It was only cleared on the happy
    // path, so a rejected sign-in left the store loading forever and the Sign
    // in button disabled, reading "Signing in…" — you could not even retry.
    set({ isLoading: true });
    try {
      const token = await authService.login(email, password);
      localStorage.setItem("token", token);
      const user = await authService.me();
      set({ token, user, isLoading: false, baseCurrency: user.base_currency ?? "EUR" });
    } catch (err) {
      set({ isLoading: false });
      throw err;
    }
  },

  demoLogin: async () => {
    set({ isLoading: true });
    try {
      const token = await authService.demoLogin();
      localStorage.setItem("token", token);
      const user = await authService.me();
      set({ token, user, isLoading: false, baseCurrency: user.base_currency ?? "EUR" });
    } catch (err) {
      set({ isLoading: false });
      throw err;
    }
  },

  logout: () => {
    localStorage.removeItem("token");
    set({ user: null, token: null, baseCurrency: "EUR", baseCurrencyError: null });
  },

  fetchMe: async () => {
    const token = localStorage.getItem("token");
    if (!token) return;
    const user = await authService.me();
    set({ user, baseCurrency: user.base_currency ?? "EUR" });
  },

  setBaseCurrency: async (currency) => {
    // Optimistic local update
    const prev = get().baseCurrency;
    set({ baseCurrency: currency, baseCurrencyError: null });
    const u = get().user;
    if (u) set({ user: { ...u, base_currency: currency } });
    try {
      const updated = await authService.updateMe({ base_currency: currency });
      set({ user: updated, baseCurrency: updated.base_currency ?? currency });
      // Refresh transactions so the new server-recomputed base_amount surfaces
      const { useTransactionStore } = await import("@/store/transactionStore");
      useTransactionStore.getState().fetch();
    } catch (err) {
      // Roll back local state on failure. F55 — and say why: the server refuses the change
      // (503) when exchange rates are unavailable, and a silent snap-back looked like a glitch.
      set({
        baseCurrency: prev,
        baseCurrencyError: apiErrorMessage(err, "Could not change your base currency — please try again."),
      });
      const cur = get().user;
      if (cur) set({ user: { ...cur, base_currency: prev } });
    }
  },
}));
