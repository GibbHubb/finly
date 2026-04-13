import { beforeEach, describe, expect, it } from "vitest";
import { useBudgetStore } from "@/store/budgetStore";
import { resetBudgets } from "@/test/msw/handlers";
import type { Budget } from "@/types";

const sample: Budget = {
  id: 1,
  category: "food",
  limit_amount: "300.00",
  month: 6,
  year: 2024,
};

function resetStore(): void {
  useBudgetStore.setState({ budgets: [], isLoading: false });
}

describe("budgetStore", () => {
  beforeEach(() => {
    resetStore();
    resetBudgets();
    localStorage.setItem("token", "test-token");
  });

  it("fetch populates budgets and toggles loading", async () => {
    resetBudgets([sample]);

    const promise = useBudgetStore.getState().fetch();
    expect(useBudgetStore.getState().isLoading).toBe(true);

    await promise;

    expect(useBudgetStore.getState().isLoading).toBe(false);
    expect(useBudgetStore.getState().budgets).toEqual([sample]);
  });

  it("fetch forwards month/year filters", async () => {
    resetBudgets([
      { ...sample, id: 1, month: 6, year: 2024 },
      { ...sample, id: 2, month: 7, year: 2024 },
    ]);

    await useBudgetStore.getState().fetch(6, 2024);

    expect(useBudgetStore.getState().budgets).toHaveLength(1);
    expect(useBudgetStore.getState().budgets[0].month).toBe(6);
  });

  it("add prepends the new budget (newest-first UX)", async () => {
    resetBudgets([{ ...sample, id: 1, month: 5, year: 2024 }]);
    await useBudgetStore.getState().fetch();

    await useBudgetStore.getState().add({
      category: "transport",
      limit_amount: 150,
      month: 6,
      year: 2024,
    });

    const { budgets } = useBudgetStore.getState();
    expect(budgets).toHaveLength(2);
    expect(budgets[0].category).toBe("transport");
  });

  it("add surfaces 409 on duplicate and does not mutate state", async () => {
    resetBudgets([sample]);
    await useBudgetStore.getState().fetch();

    await expect(
      useBudgetStore.getState().add({
        category: "food",
        limit_amount: 999,
        month: 6,
        year: 2024,
      })
    ).rejects.toMatchObject({ response: { status: 409 } });

    expect(useBudgetStore.getState().budgets).toEqual([sample]);
  });

  it("remove drops the budget locally after server 204", async () => {
    resetBudgets([sample]);
    await useBudgetStore.getState().fetch();

    await useBudgetStore.getState().remove(sample.id);

    expect(useBudgetStore.getState().budgets).toEqual([]);
  });
});
