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

  async me(): Promise<User> {
    const { data } = await api.get<User>("/auth/me");
    return data;
  },
};
