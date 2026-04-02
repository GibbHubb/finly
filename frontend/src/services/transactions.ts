import api from "./api";
import type { MonthlySummary, Transaction, TransactionCreate, TransactionFilters } from "@/types";

export const transactionService = {
  async list(filters: TransactionFilters = {}): Promise<Transaction[]> {
    const { data } = await api.get<Transaction[]>("/transactions/", { params: filters });
    return data;
  },

  async create(payload: TransactionCreate): Promise<Transaction> {
    const { data } = await api.post<Transaction>("/transactions/", payload);
    return data;
  },

  async remove(id: number): Promise<void> {
    await api.delete(`/transactions/${id}`);
  },

  async summary(month: number, year: number): Promise<MonthlySummary> {
    const { data } = await api.get<MonthlySummary>("/transactions/summary", {
      params: { month, year },
    });
    return data;
  },
};
