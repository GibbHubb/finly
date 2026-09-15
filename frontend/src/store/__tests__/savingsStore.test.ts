import { beforeEach, describe, expect, it } from "vitest";
import { http, HttpResponse } from "msw";
import { server } from "@/test/msw/server";
import { useSavingsStore } from "@/store/savingsStore";
import { savingsService } from "@/services/savings";
import type { SavingsGoal } from "@/types";

const goal = {
  id: 1,
  name: "New bike",
  target_amount: "800.00",
  current_amount: "200.00",
} as SavingsGoal;

function resetStore(): void {
  useSavingsStore.setState({ goals: [], isLoading: false });
}

describe("savingsService", () => {
  beforeEach(() => localStorage.setItem("token", "test-token"));

  it("list, create, update and remove hit the savings-goals endpoints", async () => {
    server.use(
      http.get("*/api/v1/savings-goals/", () => HttpResponse.json([goal])),
      http.post("*/api/v1/savings-goals/", () => HttpResponse.json(goal, { status: 201 })),
      http.patch("*/api/v1/savings-goals/:id", () =>
        HttpResponse.json({ ...goal, current_amount: "300.00" })
      ),
      http.delete("*/api/v1/savings-goals/:id", () => new HttpResponse(null, { status: 204 }))
    );

    await expect(savingsService.list()).resolves.toHaveLength(1);
    await expect(savingsService.create({ name: "New bike" } as never)).resolves.toEqual(goal);
    await expect(savingsService.update(1, { current_amount: 300 } as never)).resolves.toMatchObject({
      current_amount: "300.00",
    });
    await expect(savingsService.remove(1)).resolves.toBeUndefined();
  });
});

describe("savingsStore", () => {
  beforeEach(() => {
    resetStore();
    localStorage.setItem("token", "test-token");
  });

  it("fetch populates goals and clears loading", async () => {
    server.use(http.get("*/api/v1/savings-goals/", () => HttpResponse.json([goal])));

    await useSavingsStore.getState().fetch();

    expect(useSavingsStore.getState().goals).toHaveLength(1);
    expect(useSavingsStore.getState().isLoading).toBe(false);
  });

  it("fetch swallows a failure but still clears loading", async () => {
    server.use(
      http.get("*/api/v1/savings-goals/", () =>
        HttpResponse.json({ detail: "boom" }, { status: 500 })
      )
    );

    await expect(useSavingsStore.getState().fetch()).resolves.toBeUndefined();
    expect(useSavingsStore.getState().isLoading).toBe(false);
    expect(useSavingsStore.getState().goals).toEqual([]);
  });

  it("add prepends the new goal", async () => {
    useSavingsStore.setState({ goals: [{ ...goal, id: 9 }] });
    server.use(
      http.post("*/api/v1/savings-goals/", () => HttpResponse.json(goal, { status: 201 }))
    );

    await useSavingsStore.getState().add({ name: "New bike" } as never);

    expect(useSavingsStore.getState().goals.map((g) => g.id)).toEqual([1, 9]);
  });

  it("update replaces only the matching goal", async () => {
    useSavingsStore.setState({ goals: [goal, { ...goal, id: 2, name: "Holiday" }] });
    server.use(
      http.patch("*/api/v1/savings-goals/:id", () =>
        HttpResponse.json({ ...goal, current_amount: "500.00" })
      )
    );

    await useSavingsStore.getState().update(1, { current_amount: 500 } as never);

    const goals = useSavingsStore.getState().goals;
    expect(goals[0].current_amount).toBe("500.00");
    expect(goals[1].name).toBe("Holiday");
  });

  it("remove drops the goal from the list", async () => {
    useSavingsStore.setState({ goals: [goal, { ...goal, id: 2 }] });
    server.use(http.delete("*/api/v1/savings-goals/:id", () => new HttpResponse(null, { status: 204 })));

    await useSavingsStore.getState().remove(1);

    expect(useSavingsStore.getState().goals.map((g) => g.id)).toEqual([2]);
  });
});
