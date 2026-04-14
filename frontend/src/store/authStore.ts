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
  setBaseCurrency: (currency: string) => void;
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

  setBaseCurrency: (currency) => {
    set({ baseCurrency: currency });
    const user = get().user;
    if (user) set({ user: { ...user, base_currency: currency } });
  },
}));
