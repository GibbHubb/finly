import api from "./api";
import type { Transaction, TransactionCreate } from "@/types";

export const transactionService = {
  async list(skip = 0, limit = 200): Promise<Transaction[]> {
    const { data } = await api.get<Transaction[]>("/transactions/", { params: { skip, limit } });
    return data;
  },

  async create(payload: TransactionCreate): Promise<Transaction> {
    const { data } = await api.post<Transaction>("/transactions/", payload);
    return data;
  },

  async remove(id: number): Promise<void> {
    await api.delete(`/transactions/${id}`);
  },
};
