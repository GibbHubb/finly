import api from "./api";
import type { Budget, BudgetCreate } from "@/types";

export const budgetService = {
  async list(month?: number, year?: number): Promise<Budget[]> {
    const { data } = await api.get<Budget[]>("/budgets/", { params: { month, year } });
    return data;
  },

  async create(payload: BudgetCreate): Promise<Budget> {
    const { data } = await api.post<Budget>("/budgets/", payload);
    return data;
  },

  async remove(id: number): Promise<void> {
    await api.delete(`/budgets/${id}`);
  },
};
