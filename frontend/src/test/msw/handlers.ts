import { http, HttpResponse } from "msw";
import type { Budget, BudgetCreate } from "@/types";

/**
 * In-memory fake for `/budgets/*`. Reset between tests via `resetBudgets`.
 * Mirrors the real backend's uniqueness constraint (category+month+year).
 */
let budgets: Budget[] = [];
let nextId = 1;

export function resetBudgets(seed: Budget[] = []): void {
  budgets = [...seed];
  nextId = seed.reduce((m, b) => Math.max(m, b.id), 0) + 1;
}

export const handlers = [
  http.get("*/api/v1/budgets/", ({ request }) => {
    const url = new URL(request.url);
    const month = url.searchParams.get("month");
    const year = url.searchParams.get("year");

    let result = [...budgets];
    if (month) result = result.filter((b) => b.month === Number(month));
    if (year) result = result.filter((b) => b.year === Number(year));
    result.sort((a, b) => b.year - a.year || b.month - a.month);
    return HttpResponse.json(result);
  }),

  http.post("*/api/v1/budgets/", async ({ request }) => {
    const payload = (await request.json()) as BudgetCreate;
    const clash = budgets.find(
      (b) =>
        b.category === payload.category &&
        b.month === payload.month &&
        b.year === payload.year
    );
    if (clash) {
      return HttpResponse.json(
        { detail: "Budget for this category/month already exists" },
        { status: 409 }
      );
    }
    const budget: Budget = {
      id: nextId++,
      category: payload.category,
      limit_amount: payload.limit_amount.toFixed(2),
      month: payload.month,
      year: payload.year,
    };
    budgets = [budget, ...budgets];
    return HttpResponse.json(budget, { status: 201 });
  }),

  http.delete("*/api/v1/budgets/:id", ({ params }) => {
    const id = Number(params.id);
    const before = budgets.length;
    budgets = budgets.filter((b) => b.id !== id);
    if (budgets.length === before) {
      return HttpResponse.json({ detail: "Budget not found" }, { status: 404 });
    }
    return new HttpResponse(null, { status: 204 });
  }),
];
