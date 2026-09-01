import { useEffect } from "react";
import { useTransactionStore } from "@/store/transactionStore";

/** Fetches transactions on mount, returns store state. */
export function useTransactions() {
  const store = useTransactionStore();
  const fetch = useTransactionStore((s) => s.fetch);

  useEffect(() => {
    fetch();
  }, [fetch]);

  // Prefer base_amount (already converted to user's base currency); fall back
  // to amount for legacy rows that pre-date F12 and were never backfilled.
  const valueOf = (t: { amount: string; base_amount: string | null }): number =>
    parseFloat(t.base_amount ?? t.amount);

  const totalIncome = store.transactions
    .filter((t) => t.type === "income")
    .reduce((sum, t) => sum + valueOf(t), 0);

  const totalExpense = store.transactions
    .filter((t) => t.type === "expense")
    .reduce((sum, t) => sum + valueOf(t), 0);

  const balance = totalIncome - totalExpense;

  return { ...store, totalIncome, totalExpense, balance };
}
