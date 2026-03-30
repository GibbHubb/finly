import { create } from "zustand";
import type { User } from "@/types";
import { authService } from "@/services/auth";

interface AuthState {
  user: User | null;
  token: string | null;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  fetchMe: () => Promise<void>;
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  token: localStorage.getItem("token"),
  isLoading: false,

  login: async (email, password) => {
    set({ isLoading: true });
    const token = await authService.login(email, password);
    localStorage.setItem("token", token);
    const user = await authService.me();
    set({ token, user, isLoading: false });
  },

  logout: () => {
    localStorage.removeItem("token");
    set({ user: null, token: null });
  },

  fetchMe: async () => {
    const token = localStorage.getItem("token");
    if (!token) return;
    const user = await authService.me();
    set({ user });
  },
}));
