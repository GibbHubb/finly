import { test, expect } from "./fixtures";

test.describe("budgets", () => {
  test("set a budget then trigger an over-limit alert via a transaction", async ({ loggedInPage: page }) => {
    // Navigate to Budgets via the in-page nav
    await page.goto("/budgets");
    await expect(page.getByRole("heading", { name: /budgets/i })).toBeVisible();

    // Find the food category dropdown / amount input. The exact form structure
    // varies — this test asserts the broad shape (a category, an amount, a save action).
    const categoryDropdown = page.locator("select").first();
    await categoryDropdown.selectOption("food");

    // Enter a tight limit
    const limitInput = page.locator('input[type="number"]').first();
    await limitInput.fill("10");

    await page.getByRole("button", { name: /add|save|set/i }).first().click();

    // Budget row visible with "food" + the limit
    await expect(page.locator("body")).toContainText(/food/i);
    await expect(page.locator("body")).toContainText(/10/);

    // Now go back to dashboard and add an expense over the limit
    await page.goto("/dashboard");
    await page.locator('input[placeholder*="Amount"]').fill("25.00");
    await page.locator('input[placeholder*="Description"]').fill("over-budget lunch");
    await page.locator('input[type="date"]').first().fill(new Date().toISOString().slice(0, 10));
    await page.getByRole("button", { name: /^add$/i }).click();

    // Toast appears with the over-budget message
    const toast = page.locator(".budget-toast");
    await expect(toast).toBeVisible({ timeout: 10_000 });
    await expect(toast).toContainText(/over budget/i);
  });
});
