import { beforeEach, describe, expect, it, vi } from "vitest";
import { http, HttpResponse } from "msw";
import { server } from "@/test/msw/server";
import { useTransactionStore } from "@/store/transactionStore";
import { transactionService } from "@/services/transactions";
import type { Transaction } from "@/types";

const sample: Transaction = {
  id: 1,
  amount: "12.50",
  type: "expense",
  category: "food",
  description: "Bakery",
  transaction_date: "2026-09-01",
  currency: "EUR",
  base_amount: null,
  created_at: "2026-09-01T10:00:00",
  parent_transaction_id: null,
  tags: [],
};

function resetStore(): void {
  useTransactionStore.setState({ transactions: [], isLoading: false, error: null });
}

describe("transactionStore.fetch", () => {
  beforeEach(() => {
    resetStore();
    localStorage.setItem("token", "test-token");
  });

  it("populates transactions and clears loading on success", async () => {
    server.use(http.get("*/api/v1/transactions/", () => HttpResponse.json([sample])));

    await useTransactionStore.getState().fetch();

    expect(useTransactionStore.getState().transactions).toHaveLength(1);
    expect(useTransactionStore.getState().isLoading).toBe(false);
    expect(useTransactionStore.getState().error).toBeNull();
  });

  // F38 — the regression. `fetch` had no catch, so a rejected request left
  // isLoading true forever: the dashboard showed "Loading…" and €0.00 tiles
  // with no way for anyone (user or browser harness) to see that it had failed.
  it("surfaces an error and stops loading when the request fails", async () => {
    server.use(
      http.get("*/api/v1/transactions/", () =>
        HttpResponse.json({ detail: "boom" }, { status: 500 })
      )
    );

    await expect(useTransactionStore.getState().fetch()).resolves.toBeUndefined();

    const state = useTransactionStore.getState();
    expect(state.isLoading).toBe(false);
    expect(state.error).toMatch(/could not load transactions/i);
    expect(state.transactions).toEqual([]);
  });

  it("clears a previous error on a later successful fetch", async () => {
    useTransactionStore.setState({ error: "Could not load transactions — old" });
    server.use(http.get("*/api/v1/transactions/", () => HttpResponse.json([sample])));

    await useTransactionStore.getState().fetch();

    expect(useTransactionStore.getState().error).toBeNull();
  });
});

describe("transactionStore mutations", () => {
  beforeEach(() => {
    resetStore();
    localStorage.setItem("token", "test-token");
  });

  it("add prepends the created transaction", async () => {
    useTransactionStore.setState({ transactions: [{ ...sample, id: 9 }] });
    server.use(http.post("*/api/v1/transactions/", () => HttpResponse.json(sample, { status: 201 })));

    await useTransactionStore.getState().add({ amount: 12.5 } as never);

    expect(useTransactionStore.getState().transactions.map((t) => t.id)).toEqual([1, 9]);
  });

  it("remove drops only the deleted id", async () => {
    useTransactionStore.setState({ transactions: [sample, { ...sample, id: 2 }] });
    server.use(
      http.delete("*/api/v1/transactions/:id", () => new HttpResponse(null, { status: 204 }))
    );

    await useTransactionStore.getState().remove(1);

    expect(useTransactionStore.getState().transactions.map((t) => t.id)).toEqual([2]);
  });

  it("pushTransaction adds a new row", () => {
    useTransactionStore.getState().pushTransaction(sample);
    expect(useTransactionStore.getState().transactions).toHaveLength(1);
  });

  it("pushTransaction ignores an id already in the list", () => {
    useTransactionStore.setState({ transactions: [sample] });

    useTransactionStore.getState().pushTransaction({ ...sample, description: "duplicate" });

    const txs = useTransactionStore.getState().transactions;
    expect(txs).toHaveLength(1);
    expect(txs[0].description).toBe("Bakery");
  });
});

describe("transactionStore secondary fetches", () => {
  beforeEach(() => {
    resetStore();
    useTransactionStore.setState({
      forecast: null,
      forecastLoading: false,
      recurring: [],
      recurringLoading: false,
    });
    localStorage.setItem("token", "test-token");
  });

  it("fetchForecast stores the forecast and clears loading", async () => {
    server.use(
      http.get("*/api/v1/transactions/forecast", () =>
        HttpResponse.json({ projected_spend: "1200.00" })
      )
    );

    await useTransactionStore.getState().fetchForecast(9, 2026);

    expect(useTransactionStore.getState().forecast).toMatchObject({ projected_spend: "1200.00" });
    expect(useTransactionStore.getState().forecastLoading).toBe(false);
  });

  it("fetchForecast clears loading when the request fails", async () => {
    server.use(
      http.get("*/api/v1/transactions/forecast", () =>
        HttpResponse.json({ detail: "boom" }, { status: 500 })
      )
    );

    await expect(useTransactionStore.getState().fetchForecast(9, 2026)).resolves.toBeUndefined();
    expect(useTransactionStore.getState().forecastLoading).toBe(false);
  });

  it("fetchRecurring stores the detected subscriptions", async () => {
    server.use(
      http.get("*/api/v1/transactions/recurring", () =>
        HttpResponse.json([{ merchant: "coffee", monthly_amount: 19.5 }])
      )
    );

    await useTransactionStore.getState().fetchRecurring();

    expect(useTransactionStore.getState().recurring).toHaveLength(1);
    expect(useTransactionStore.getState().recurringLoading).toBe(false);
  });

  it("fetchRecurring clears loading when the request fails", async () => {
    server.use(
      http.get("*/api/v1/transactions/recurring", () =>
        HttpResponse.json({ detail: "boom" }, { status: 500 })
      )
    );

    await expect(useTransactionStore.getState().fetchRecurring()).resolves.toBeUndefined();
    expect(useTransactionStore.getState().recurringLoading).toBe(false);
  });
});

describe("transactionStore.importCsv", () => {
  beforeEach(() => {
    resetStore();
    localStorage.setItem("token", "test-token");
  });

  // Stubbed at the service, not the network: a real File through jsdom's XHR
  // never settles under msw (see services/__tests__/transactions.test.ts).
  it("refreshes the list after a successful import", async () => {
    const importCsv = vi
      .spyOn(transactionService, "importCsv")
      .mockResolvedValue({ imported: 2, skipped: 0 } as never);
    const list = vi.spyOn(transactionService, "list").mockResolvedValue([sample]);

    const result = await useTransactionStore.getState().importCsv(new File(["x"], "s.csv"));

    expect(result).toEqual({ imported: 2, skipped: 0 });
    expect(list).toHaveBeenCalledOnce();
    expect(useTransactionStore.getState().transactions).toHaveLength(1);
    importCsv.mockRestore();
    list.mockRestore();
  });

  // Nothing was imported, so there is nothing new to fetch — re-listing here
  // would be a wasted round trip on every rejected file.
  it("does not re-list when the import brought nothing in", async () => {
    const importCsv = vi
      .spyOn(transactionService, "importCsv")
      .mockResolvedValue({ imported: 0, skipped: 5 } as never);
    const list = vi.spyOn(transactionService, "list").mockResolvedValue([sample]);

    const result = await useTransactionStore.getState().importCsv(new File(["x"], "s.csv"));

    expect(result).toEqual({ imported: 0, skipped: 5 });
    expect(list).not.toHaveBeenCalled();
    expect(useTransactionStore.getState().transactions).toEqual([]);
    importCsv.mockRestore();
    list.mockRestore();
  });
});

describe("F35 — budget alerts from write responses", () => {
  it("an alert on the create response reaches the toast state, and dismiss removes it", async () => {
    const alert = { event: "budget_alert" as const, category: "food", month: 3, year: 2026, spent: "110.00", limit: "100.00", overage: "10.00" };
    vi.spyOn(transactionService, "create").mockResolvedValue({ ...sample, budget_alerts: [alert] });
    useTransactionStore.setState({ transactions: [], budgetAlerts: [] });

    await useTransactionStore.getState().add({ amount: 50, type: "expense", category: "food", description: "", transaction_date: "2026-03-05" } as never);

    const [shown] = useTransactionStore.getState().budgetAlerts;
    expect(shown).toMatchObject(alert);
    useTransactionStore.getState().dismissBudgetAlert(shown!.clientId);
    expect(useTransactionStore.getState().budgetAlerts).toEqual([]);
  });

  it("a create with no alerts adds none (control)", async () => {
    vi.spyOn(transactionService, "create").mockResolvedValue({ ...sample, budget_alerts: [] });
    useTransactionStore.setState({ transactions: [], budgetAlerts: [] });
    await useTransactionStore.getState().add({ amount: 5, type: "expense", category: "food", description: "", transaction_date: "2026-03-05" } as never);
    expect(useTransactionStore.getState().budgetAlerts).toEqual([]);
  });
});
