import { useEffect } from "react";
import { useBudgetStore } from "@/store/budgetStore";

/** Fetches budgets for the given month/year on mount, returns store state. */
export function useBudgets(month: number, year: number) {
  const store = useBudgetStore();
  const fetch = useBudgetStore((s) => s.fetch);

  useEffect(() => {
    fetch(month, year);
  }, [fetch, month, year]);

  return store;
}
