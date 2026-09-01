import api from "./api";
import type { SavingsGoal, SavingsGoalCreate, SavingsGoalUpdate } from "@/types";

export const savingsService = {
  async list(): Promise<SavingsGoal[]> {
    const { data } = await api.get<SavingsGoal[]>("/savings-goals/");
    return data;
  },

  async create(payload: SavingsGoalCreate): Promise<SavingsGoal> {
    const { data } = await api.post<SavingsGoal>("/savings-goals/", payload);
    return data;
  },

  async update(id: number, payload: SavingsGoalUpdate): Promise<SavingsGoal> {
    const { data } = await api.patch<SavingsGoal>(`/savings-goals/${id}`, payload);
    return data;
  },

  async remove(id: number): Promise<void> {
    await api.delete(`/savings-goals/${id}`);
  },
};
