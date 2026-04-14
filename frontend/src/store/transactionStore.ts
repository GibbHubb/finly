import { create } from "zustand";
import type { ForecastResult, ImportResult, Transaction, TransactionCreate } from "@/types";
import { transactionService } from "@/services/transactions";

interface TransactionState {
  transactions: Transaction[];
  isLoading: boolean;
  forecast: ForecastResult | null;
  forecastLoading: boolean;
  fetch: () => Promise<void>;
  add: (payload: TransactionCreate) => Promise<void>;
  remove: (id: number) => Promise<void>;
  pushTransaction: (tx: Transaction) => void;
  fetchForecast: (month: number, year: number) => Promise<void>;
  importCsv: (file: File) => Promise<ImportResult>;
}

export const useTransactionStore = create<TransactionState>((set, get) => ({
  transactions: [],
  isLoading: false,
  forecast: null,
  forecastLoading: false,

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

  pushTransaction: (tx) => {
    // Ignore if already present (e.g. added by the same tab via REST)
    if (get().transactions.some((t) => t.id === tx.id)) return;
    set({ transactions: [tx, ...get().transactions] });
  },

  fetchForecast: async (month, year) => {
    set({ forecastLoading: true });
    try {
      const forecast = await transactionService.forecast(month, year);
      set({ forecast, forecastLoading: false });
    } catch {
      set({ forecastLoading: false });
    }
  },

  importCsv: async (file) => {
    const result = await transactionService.importCsv(file);
    if (result.imported > 0) {
      // Refresh transaction list after a successful import
      const transactions = await transactionService.list();
      set({ transactions });
    }
    return result;
  },
}));
