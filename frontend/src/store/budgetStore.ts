import { create } from "zustand";
import type { Budget, BudgetCreate } from "@/types";
import { budgetService } from "@/services/budgets";

interface BudgetState {
  budgets: Budget[];
  isLoading: boolean;
  fetch: (month?: number, year?: number) => Promise<void>;
  add: (payload: BudgetCreate) => Promise<void>;
  remove: (id: number) => Promise<void>;
}

export const useBudgetStore = create<BudgetState>((set, get) => ({
  budgets: [],
  isLoading: false,

  fetch: async (month, year) => {
    set({ isLoading: true });
    const budgets = await budgetService.list(month, year);
    set({ budgets, isLoading: false });
  },

  add: async (payload) => {
    const budget = await budgetService.create(payload);
    set({ budgets: [budget, ...get().budgets] });
  },

  remove: async (id) => {
    await budgetService.remove(id);
    set({ budgets: get().budgets.filter((b) => b.id !== id) });
  },
}));
