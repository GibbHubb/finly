import api from "./api";
import type { User } from "@/types";

export const authService = {
  async register(email: string, password: string, full_name: string): Promise<User> {
    const { data } = await api.post<User>("/auth/register", { email, password, full_name });
    return data;
  },

  async login(email: string, password: string): Promise<string> {
    const form = new FormData();
    form.append("username", email);
    form.append("password", password);
    const { data } = await api.post<{ access_token: string }>("/auth/login", form);
    return data.access_token;
  },

  /** F33 — one-click login to the shared demo account. Takes no credentials
   *  by design; the backend returns 404 unless DEMO_MODE is on. */
  async demoLogin(): Promise<string> {
    const { data } = await api.post<{ access_token: string }>("/auth/demo-login");
    return data.access_token;
  },

  async me(): Promise<User> {
    const { data } = await api.get<User>("/auth/me");
    return data;
  },

  async updateMe(payload: { full_name?: string; base_currency?: string }): Promise<User> {
    const { data } = await api.patch<User>("/auth/me", payload);
    return data;
  },
};
