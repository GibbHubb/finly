// F46 — automated axe pass: 0 serious/critical violations on every screen,
// plus the dashboard with the split modal open.
//
// F46-fu — the first version of this file was written without a browser and
// had never been run. Its first real run failed on aria-hidden-focus (the pie
// SVG was a tab stop), color-contrast (--muted at 4.48:1) and
// link-in-text-block; it also could not reach the modal at all, because
// /test/reset leaves the user with no transactions and so no ✂ trigger. Each
// logged-in test now seeds one expense through the real Add form first, and
// the list covers all nine routes, not four. See plans/finly/F46.md §9 for the
// manual keyboard/screen-reader passes this spec cannot substitute for.
import AxeBuilder from "@axe-core/playwright";
import type { Page } from "@playwright/test";
import { test, expect } from "./fixtures";

const SERIOUS_OR_CRITICAL = ["serious", "critical"] as const;

function seriousOrCritical(violations: { impact?: string | null }[]) {
  return violations.filter((v) => v.impact && (SERIOUS_OR_CRITICAL as readonly string[]).includes(v.impact));
}

async function expectNoSeriousViolations(page: Page) {
  const results = await new AxeBuilder({ page }).analyze();
  expect(seriousOrCritical(results.violations), JSON.stringify(results.violations, null, 2)).toHaveLength(0);
}

/** Add one food expense via the dashboard form, so lists, the pie and the split trigger render. */
async function seedExpense(page: Page) {
  await page.goto("/dashboard");
  await page.getByLabel("Transaction type", { exact: true }).selectOption("expense");
  await page.getByLabel("Amount (€)", { exact: true }).fill("42.50");
  await page.getByLabel("Category", { exact: true }).selectOption("food");
  await page.getByLabel("Description (optional)", { exact: true }).fill("a11y groceries");
  await page.getByRole("button", { name: "Add", exact: true }).click();
  await expect(page.getByText("a11y groceries").first()).toBeVisible();
}

test.describe("accessibility (axe)", () => {
  for (const path of ["/login", "/register"]) {
    test(`${path} has 0 serious/critical violations`, async ({ page }) => {
      await page.goto(path);
      await expectNoSeriousViolations(page);
    });
  }

  for (const path of ["/dashboard", "/budgets", "/trends", "/import", "/rules", "/savings", "/category/food"]) {
    test(`${path} has 0 serious/critical violations`, async ({ loggedInPage: page }) => {
      await seedExpense(page);
      await page.goto(path);
      await page.waitForLoadState("networkidle");
      await expectNoSeriousViolations(page);
    });
  }

  test("Dashboard with the split modal open has 0 serious/critical violations", async ({ loggedInPage: page }) => {
    await seedExpense(page);
    const splitTrigger = page.locator('button[title="Split this transaction into multiple categories"]').first();
    await splitTrigger.click();
    await expect(page.getByRole("dialog")).toBeVisible();
    // The page behind the dialog is inert while it is open, and not after.
    await expect(page.locator("#root")).toHaveAttribute("inert", "");
    await expectNoSeriousViolations(page);

    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await expect(page.locator("#root")).not.toHaveAttribute("inert", "");
    await expect(splitTrigger).toBeFocused();
  });
});
