import { create } from "zustand";
import type { User } from "@/types";
import { authService } from "@/services/auth";

interface AuthState {
  user: User | null;
  token: string | null;
  isLoading: boolean;
  baseCurrency: string;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  fetchMe: () => Promise<void>;
  setBaseCurrency: (currency: string) => Promise<void>;
}

export const useAuthStore = create<AuthState>((set, get) => ({
  user: null,
  token: localStorage.getItem("token"),
  isLoading: false,
  baseCurrency: "EUR",

  login: async (email, password) => {
    set({ isLoading: true });
    const token = await authService.login(email, password);
    localStorage.setItem("token", token);
    const user = await authService.me();
    set({ token, user, isLoading: false, baseCurrency: user.base_currency ?? "EUR" });
  },

  logout: () => {
    localStorage.removeItem("token");
    set({ user: null, token: null, baseCurrency: "EUR" });
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
    set({ baseCurrency: currency });
    const u = get().user;
    if (u) set({ user: { ...u, base_currency: currency } });
    try {
      const updated = await authService.updateMe({ base_currency: currency });
      set({ user: updated, baseCurrency: updated.base_currency ?? currency });
      // Refresh transactions so the new server-recomputed base_amount surfaces
      const { useTransactionStore } = await import("@/store/transactionStore");
      useTransactionStore.getState().fetch();
    } catch {
      // Roll back local state on failure
      set({ baseCurrency: prev });
      const cur = get().user;
      if (cur) set({ user: { ...cur, base_currency: prev } });
    }
  },
}));
