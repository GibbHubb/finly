import { create } from "zustand";
import type { SavingsGoal, SavingsGoalCreate, SavingsGoalUpdate } from "@/types";
import { savingsService } from "@/services/savings";

interface SavingsState {
  goals: SavingsGoal[];
  isLoading: boolean;
  fetch: () => Promise<void>;
  add: (payload: SavingsGoalCreate) => Promise<void>;
  update: (id: number, payload: SavingsGoalUpdate) => Promise<void>;
  remove: (id: number) => Promise<void>;
}

export const useSavingsStore = create<SavingsState>((set, get) => ({
  goals: [],
  isLoading: false,

  fetch: async () => {
    set({ isLoading: true });
    try {
      const goals = await savingsService.list();
      set({ goals, isLoading: false });
    } catch {
      set({ isLoading: false });
    }
  },

  add: async (payload) => {
    const goal = await savingsService.create(payload);
    set({ goals: [goal, ...get().goals] });
  },

  update: async (id, payload) => {
    const goal = await savingsService.update(id, payload);
    set({ goals: get().goals.map((g) => (g.id === id ? goal : g)) });
  },

  remove: async (id) => {
    await savingsService.remove(id);
    set({ goals: get().goals.filter((g) => g.id !== id) });
  },
}));
