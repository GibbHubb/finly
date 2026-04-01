import { useEffect } from "react";
import { useTransactionStore } from "@/store/transactionStore";

/** Fetches transactions on mount, returns store state. */
export function useTransactions() {
  const store = useTransactionStore();
  const fetch = useTransactionStore((s) => s.fetch);

  useEffect(() => {
    fetch();
  }, [fetch]);

  const totalIncome = store.transactions
    .filter((t) => t.type === "income")
    .reduce((sum, t) => sum + parseFloat(t.amount), 0);

  const totalExpense = store.transactions
    .filter((t) => t.type === "expense")
    .reduce((sum, t) => sum + parseFloat(t.amount), 0);

  const balance = totalIncome - totalExpense;

  return { ...store, totalIncome, totalExpense, balance };
}
