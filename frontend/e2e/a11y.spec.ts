// F46 — automated axe pass over the screens named in the plan's acceptance
// criteria: Login, Dashboard, Budgets, and Dashboard with the split modal
// open. Asserts 0 serious/critical violations on each.
//
// NOT RUN in the session that wrote this file — no browser/axe tooling was
// available there (no `playwright install`, no live backend to drive the
// webServer this spec needs). This file is source only; running it and
// recording the before/after counts in plans/finly/F46.md §7 step 1/6 is
// still open. See that plan's §9 for the manual keyboard/screen-reader
// passes this spec cannot substitute for either.
import AxeBuilder from "@axe-core/playwright";
import { test, expect } from "./fixtures";

const SERIOUS_OR_CRITICAL = ["serious", "critical"] as const;

function seriousOrCritical(violations: { impact?: string | null }[]) {
  return violations.filter((v) => v.impact && (SERIOUS_OR_CRITICAL as readonly string[]).includes(v.impact));
}

test.describe("accessibility (axe)", () => {
  test("Login has 0 serious/critical violations", async ({ page }) => {
    await page.goto("/login");
    const results = await new AxeBuilder({ page }).analyze();
    expect(seriousOrCritical(results.violations), JSON.stringify(results.violations, null, 2)).toHaveLength(0);
  });

  test("Dashboard has 0 serious/critical violations", async ({ loggedInPage: page }) => {
    await page.goto("/dashboard");
    const results = await new AxeBuilder({ page }).analyze();
    expect(seriousOrCritical(results.violations), JSON.stringify(results.violations, null, 2)).toHaveLength(0);
  });

  test("Budgets has 0 serious/critical violations", async ({ loggedInPage: page }) => {
    await page.goto("/budgets");
    const results = await new AxeBuilder({ page }).analyze();
    expect(seriousOrCritical(results.violations), JSON.stringify(results.violations, null, 2)).toHaveLength(0);
  });

  test("Dashboard with the split modal open has 0 serious/critical violations", async ({ loggedInPage: page }) => {
    await page.goto("/dashboard");
    // Open the split modal on the first expense row that has one (skips
    // already-split children, which don't render the ✂ trigger).
    const splitTrigger = page.locator('button[title="Split this transaction into multiple categories"]').first();
    await splitTrigger.waitFor({ state: "visible" });
    await splitTrigger.click();
    await expect(page.getByRole("dialog")).toBeVisible();

    const results = await new AxeBuilder({ page }).analyze();
    expect(seriousOrCritical(results.violations), JSON.stringify(results.violations, null, 2)).toHaveLength(0);
  });
});
