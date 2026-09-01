import api from "./api";
import type { ForecastResult, ImportMappingPayload, ImportPreview, ImportResult, MonthlySummary, MonthlyTrendEntry, RecurringItem, RecurringReviewAction, RecurringReviewGroup, RecurringReviewResult, Transaction, TransactionCreate, TransactionFilters } from "@/types";

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

  // F25 — split a transaction into >=2 children that sum exactly to the parent.
  async split(
    id: number,
    children: { amount: number | string; category: string; description?: string }[],
  ): Promise<Transaction> {
    const { data } = await api.post<Transaction>(`/transactions/${id}/split`, { children });
    return data;
  },

  async unsplit(id: number): Promise<Transaction> {
    const { data } = await api.delete<Transaction>(`/transactions/${id}/split`);
    return data;
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

  async recurring(): Promise<RecurringItem[]> {
    const { data } = await api.get<RecurringItem[]>("/transactions/recurring");
    return data;
  },

  // F32-fu1 — review surface for the auto-applied 'recurring' tag.
  async recurringReview(): Promise<RecurringReviewGroup[]> {
    const { data } = await api.get<RecurringReviewGroup[]>(
      "/transactions/recurring-review",
    );
    return data;
  },

  async resolveRecurringReview(
    merchant: string,
    action: RecurringReviewAction,
  ): Promise<RecurringReviewResult> {
    const { data } = await api.post<RecurringReviewResult>(
      "/transactions/recurring-review",
      { merchant, action },
    );
    return data;
  },

  async trends(months: number = 6): Promise<MonthlyTrendEntry[]> {
    const { data } = await api.get<MonthlyTrendEntry[]>("/transactions/trends", {
      params: { months },
    });
    return data;
  },

  async importPreview(file: File): Promise<ImportPreview> {
    const form = new FormData();
    form.append("file", file);
    const { data } = await api.post<ImportPreview>("/transactions/import/preview", form, {
      headers: { "Content-Type": "multipart/form-data" },
    });
    return data;
  },

  async importCommit(file: File, mapping: ImportMappingPayload): Promise<ImportResult> {
    const form = new FormData();
    form.append("file", file);
    form.append("mapping", JSON.stringify(mapping));
    const { data } = await api.post<ImportResult>("/transactions/import/commit", form, {
      headers: { "Content-Type": "multipart/form-data" },
    });
    return data;
  },
};


// F27 — GoCardless bank connection helpers.
export interface BankStatus {
  id: number;
  institution_id: string;
  institution_name: string | null;
  status: string;
  last_sync_at: string | null;
  last_error: string | null;
  /** F31 — true when status is "expired" and the user must re-consent. */
  needs_reconnect?: boolean;
}

export const bankService = {
  async connect(): Promise<{ requisition_id: string; link: string; connection_id: number }> {
    const { data } = await api.post("/bank/connect");
    return data;
  },

  async status(): Promise<BankStatus[]> {
    const { data } = await api.get<BankStatus[]>("/bank/status");
    return data;
  },

  async syncNow(): Promise<{ connections: number; results: Array<{ connection_id: number; inserted: number; skipped: number; error: string | null }> }> {
    const { data } = await api.post("/bank/sync");
    return data;
  },
};


// F29 — tag CRUD + per-transaction assign/unassign helpers.
export interface TagBrief {
  id: number;
  name: string;
}

export const tagService = {
  async list(): Promise<TagBrief[]> {
    const { data } = await api.get<TagBrief[]>("/tags");
    return data;
  },
  async create(name: string): Promise<TagBrief> {
    const { data } = await api.post<TagBrief>("/tags", { name });
    return data;
  },
  async remove(id: number): Promise<void> {
    await api.delete(`/tags/${id}`);
  },
  async assign(txId: number, name: string): Promise<TagBrief[]> {
    const { data } = await api.post<TagBrief[]>(`/tags/assign/${txId}`, { name });
    return data;
  },
  async unassign(txId: number, tagId: number): Promise<TagBrief[]> {
    const { data } = await api.delete<TagBrief[]>(`/tags/assign/${txId}/${tagId}`);
    return data;
  },
};


// F28 — year-end PDF download helper. Uses the api axios instance so the
// JWT auth header travels with the request; converts the binary response
// to a blob and triggers a browser download.
export async function downloadYearReview(year: number): Promise<void> {
  const res = await api.get(`/reports/year/${year}.pdf`, { responseType: "blob" });
  const blob = new Blob([res.data], { type: "application/pdf" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `finly-${year}-review.pdf`;
  a.click();
  URL.revokeObjectURL(url);
}
