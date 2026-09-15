import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { http, HttpResponse } from "msw";
import { server } from "@/test/msw/server";
import { useTransactions } from "@/hooks/useTransactions";
import { useBudgets } from "@/hooks/useBudgets";
import { useTransactionPolling } from "@/hooks/useTransactionPolling";
import { useTransactionStore } from "@/store/transactionStore";
import { useAuthStore } from "@/store/authStore";
import { useBudgetStore } from "@/store/budgetStore";
import type { Transaction } from "@/types";

const base = {
  id: 1,
  type: "expense",
  category: "food",
  description: "Bakery",
  transaction_date: "2026-09-01",
  currency: "EUR",
  created_at: "2026-09-01T10:00:00",
  parent_transaction_id: null,
  tags: [],
};

const expense = { ...base, id: 1, amount: "10.00", base_amount: null } as Transaction;
const income = { ...base, id: 2, type: "income", amount: "30.00", base_amount: null } as Transaction;
// F12 — a foreign-currency row: base_amount is what the totals must use.
const converted = { ...base, id: 3, amount: "100.00", currency: "USD", base_amount: "90.00" } as Transaction;

describe("useTransactions", () => {
  beforeEach(() => {
    useTransactionStore.setState({ transactions: [], isLoading: false, error: null });
    localStorage.setItem("token", "test-token");
  });

  it("fetches on mount and totals income, expenses and balance", async () => {
    server.use(
      http.get("*/api/v1/transactions/", () => HttpResponse.json([expense, income]))
    );

    const { result } = renderHook(() => useTransactions());

    await waitFor(() => expect(result.current.transactions).toHaveLength(2));
    expect(result.current.totalIncome).toBe(30);
    expect(result.current.totalExpense).toBe(10);
    expect(result.current.balance).toBe(20);
  });

  it("totals on base_amount when a row was converted, not the original amount", async () => {
    server.use(http.get("*/api/v1/transactions/", () => HttpResponse.json([converted])));

    const { result } = renderHook(() => useTransactions());

    await waitFor(() => expect(result.current.transactions).toHaveLength(1));
    expect(result.current.totalExpense).toBe(90);
  });

  it("totals to zero with no rows", async () => {
    server.use(http.get("*/api/v1/transactions/", () => HttpResponse.json([])));

    const { result } = renderHook(() => useTransactions());

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.balance).toBe(0);
  });
});

describe("useBudgets", () => {
  beforeEach(() => {
    useBudgetStore.setState({ budgets: [], isLoading: false });
    localStorage.setItem("token", "test-token");
  });

  it("fetches the given month and year on mount", async () => {
    let url = "";
    server.use(
      http.get("*/api/v1/budgets/", ({ request }) => {
        url = request.url;
        return HttpResponse.json([]);
      })
    );

    const { result } = renderHook(() => useBudgets(9, 2026));

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(url).toContain("month=9");
    expect(url).toContain("year=2026");
  });
});

describe("useTransactionPolling", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    useTransactionStore.setState({ transactions: [], isLoading: false, error: null });
    useAuthStore.setState({ token: null, user: null, isLoading: false, baseCurrency: "EUR" });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("does not poll at all when there is no token", () => {
    const fetchSpy = vi.fn().mockResolvedValue(undefined);
    useTransactionStore.setState({ fetch: fetchSpy });

    renderHook(() => useTransactionPolling());

    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("fetches immediately and then every 15s while signed in", async () => {
    const fetchSpy = vi.fn().mockResolvedValue(undefined);
    useTransactionStore.setState({ fetch: fetchSpy });
    useAuthStore.setState({ token: "jwt-1" });

    renderHook(() => useTransactionPolling());

    await act(async () => {});
    expect(fetchSpy).toHaveBeenCalledTimes(1);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(15_000);
    });
    expect(fetchSpy).toHaveBeenCalledTimes(2);
  });

  // A failed poll must not stop the loop — the next one is 15s away and the
  // page still renders what it last had.
  it("keeps polling after a failed request", async () => {
    const fetchSpy = vi.fn().mockRejectedValue(new Error("offline"));
    useTransactionStore.setState({ fetch: fetchSpy });
    useAuthStore.setState({ token: "jwt-1" });

    renderHook(() => useTransactionPolling());

    await act(async () => {});
    await act(async () => {
      await vi.advanceTimersByTimeAsync(15_000);
    });
    expect(fetchSpy).toHaveBeenCalledTimes(2);
  });

  it("stops polling once unmounted", async () => {
    const fetchSpy = vi.fn().mockResolvedValue(undefined);
    useTransactionStore.setState({ fetch: fetchSpy });
    useAuthStore.setState({ token: "jwt-1" });

    const { unmount } = renderHook(() => useTransactionPolling());
    await act(async () => {});
    const callsAtUnmount = fetchSpy.mock.calls.length;

    unmount();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(60_000);
    });

    expect(fetchSpy).toHaveBeenCalledTimes(callsAtUnmount);
  });

  // A background tab polling all night is how a free tier stops being free.
  it("pauses while the tab is hidden and resumes when it comes back", async () => {
    const fetchSpy = vi.fn().mockResolvedValue(undefined);
    useTransactionStore.setState({ fetch: fetchSpy });
    useAuthStore.setState({ token: "jwt-1" });

    renderHook(() => useTransactionPolling());
    await act(async () => {});
    const before = fetchSpy.mock.calls.length;

    const visibility = vi.spyOn(document, "visibilityState", "get").mockReturnValue("hidden");
    await act(async () => {
      document.dispatchEvent(new Event("visibilitychange"));
      await vi.advanceTimersByTimeAsync(60_000);
    });
    expect(fetchSpy).toHaveBeenCalledTimes(before);

    visibility.mockReturnValue("visible");
    await act(async () => {
      document.dispatchEvent(new Event("visibilitychange"));
    });
    expect(fetchSpy.mock.calls.length).toBeGreaterThan(before);

    visibility.mockRestore();
  });
});
