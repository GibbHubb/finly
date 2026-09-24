import { create } from "zustand";
import type { User } from "@/types";
import { authService } from "@/services/auth";
import { getAccessToken, getRefreshToken, setTokens, clearTokens } from "@/services/api";
import { apiErrorMessage } from "@/utils/errors";

interface AuthState {
  user: User | null;
  token: string | null;
  /** F42 — the refresh token. api.ts's interceptor reads/writes localStorage
   *  directly for the silent-refresh path; this copy is for the store's own
   *  consumers (logout) and so `token`'s origin has a visible counterpart. */
  refreshToken: string | null;
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
  token: getAccessToken(),
  refreshToken: getRefreshToken(),
  isLoading: false,
  baseCurrency: "EUR",
  baseCurrencyError: null,

  login: async (email, password) => {
    // F37 — isLoading is reset on FAILURE too. It was only cleared on the happy
    // path, so a rejected sign-in left the store loading forever and the Sign
    // in button disabled, reading "Signing in…" — you could not even retry.
    set({ isLoading: true });
    try {
      const { accessToken, refreshToken } = await authService.login(email, password);
      setTokens(accessToken, refreshToken);
      const user = await authService.me();
      set({ token: accessToken, refreshToken, user, isLoading: false, baseCurrency: user.base_currency ?? "EUR" });
    } catch (err) {
      set({ isLoading: false });
      throw err;
    }
  },

  demoLogin: async () => {
    set({ isLoading: true });
    try {
      const { accessToken, refreshToken } = await authService.demoLogin();
      setTokens(accessToken, refreshToken);
      const user = await authService.me();
      set({ token: accessToken, refreshToken, user, isLoading: false, baseCurrency: user.base_currency ?? "EUR" });
    } catch (err) {
      set({ isLoading: false });
      throw err;
    }
  },

  logout: () => {
    // F42 — read the refresh token from localStorage, NOT from `get().refreshToken`.
    // api.ts's silent-refresh interceptor rotates the pair on a 401 and writes the
    // new one straight to localStorage without touching this store (nothing in the
    // app needs the store's copy live-updated for that). Any session that survived
    // one silent refresh would otherwise have a STALE store value here — already
    // revoked server-side — so this call would silently no-op and leave the real,
    // still-live refresh token valid for up to REFRESH_TOKEN_EXPIRE_DAYS even
    // though the UI shows the user signed out.
    const refreshToken = getRefreshToken();
    clearTokens();
    set({ user: null, token: null, refreshToken: null, baseCurrency: "EUR", baseCurrencyError: null });
    if (refreshToken) {
      authService.logout(refreshToken).catch(() => {
        // Best effort — the token is already gone from THIS client either
        // way; a failed revoke just means it stays valid server-side until
        // it expires on its own.
      });
    }
  },

  fetchMe: async () => {
    const token = getAccessToken();
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
