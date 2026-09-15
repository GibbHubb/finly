import { create } from "zustand";
import type { Budget, BudgetCreate } from "@/types";
import { budgetService } from "@/services/budgets";

interface BudgetState {
  budgets: Budget[];
  isLoading: boolean;
  /** F38 — set when the list fetch fails, so the page can say so instead of
   *  spinning. Null while loading and after a successful fetch. */
  error: string | null;
  fetch: (month?: number, year?: number) => Promise<void>;
  add: (payload: BudgetCreate) => Promise<void>;
  remove: (id: number) => Promise<void>;
}

export const useBudgetStore = create<BudgetState>((set, get) => ({
  budgets: [],
  isLoading: false,
  error: null,

  // F38 — the same missing failure path that was fixed in transactionStore:
  // a rejected request left isLoading true forever, so BudgetsPage showed
  // "Loading…" with nothing to say why, and the rejection never reached
  // `pageerror` so a browser run still called the page clean.
  fetch: async (month, year) => {
    set({ isLoading: true, error: null });
    try {
      const budgets = await budgetService.list(month, year);
      set({ budgets, isLoading: false, error: null });
    } catch (err) {
      set({
        isLoading: false,
        error:
          err instanceof Error
            ? `Could not load budgets — ${err.message}`
            : "Could not load budgets — please try again.",
      });
    }
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
