import api from "./api";
import type { ForecastResult, ImportResult, MonthlySummary, Transaction, TransactionCreate, TransactionFilters } from "@/types";

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

  async forecast(month: number, year: number): Promise<ForecastResult> {
    const { data } = await api.get<ForecastResult>("/transactions/forecast", {
      params: { month, year },
    });
    return data;
  },

  async importCsv(file: File): Promise<ImportResult> {
    const form = new FormData();
    form.append("file", file);
    const { data } = await api.post<ImportResult>("/transactions/import", form, {
      headers: { "Content-Type": "multipart/form-data" },
    });
    return data;
  },
};
