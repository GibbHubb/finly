import api from "./api";
import type { User } from "@/types";

// F42 — access + refresh pair, camelCased for the store's convenience. The
// wire shape (`access_token`/`refresh_token`) stays an implementation
// detail of this file.
export interface TokenPair {
  accessToken: string;
  refreshToken: string;
}

export const authService = {
  async register(email: string, password: string, full_name: string): Promise<User> {
    const { data } = await api.post<User>("/auth/register", { email, password, full_name });
    return data;
  },

  async login(email: string, password: string): Promise<TokenPair> {
    const form = new FormData();
    form.append("username", email);
    form.append("password", password);
    const { data } = await api.post<{ access_token: string; refresh_token: string }>("/auth/login", form);
    return { accessToken: data.access_token, refreshToken: data.refresh_token };
  },

  /** F33 — one-click login to the shared demo account. Takes no credentials
   *  by design; the backend returns 404 unless DEMO_MODE is on. */
  async demoLogin(): Promise<TokenPair> {
    const { data } = await api.post<{ access_token: string; refresh_token: string }>("/auth/demo-login");
    return { accessToken: data.access_token, refreshToken: data.refresh_token };
  },

  /** F42 — best-effort server-side revoke. Callers should not let this
   *  block or fail the local sign-out. */
  async logout(refreshToken: string): Promise<void> {
    await api.post("/auth/logout", { refresh_token: refreshToken });
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
