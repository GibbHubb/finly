import { create } from "zustand";
import type { Transaction, TransactionCreate } from "@/types";
import { transactionService } from "@/services/transactions";

interface TransactionState {
  transactions: Transaction[];
  isLoading: boolean;
  fetch: () => Promise<void>;
  add: (payload: TransactionCreate) => Promise<void>;
  remove: (id: number) => Promise<void>;
}

export const useTransactionStore = create<TransactionState>((set, get) => ({
  transactions: [],
  isLoading: false,

  fetch: async () => {
    set({ isLoading: true });
    const transactions = await transactionService.list();
    set({ transactions, isLoading: false });
  },

  add: async (payload) => {
    const tx = await transactionService.create(payload);
    set({ transactions: [tx, ...get().transactions] });
  },

  remove: async (id) => {
    await transactionService.remove(id);
    set({ transactions: get().transactions.filter((t) => t.id !== id) });
  },
}));
