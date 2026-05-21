import { test, expect } from "./fixtures";

test.describe("transactions", () => {
  test("add a transaction and see it in the list", async ({ loggedInPage: page }) => {
    // Fill the Add Transaction form (DashboardPage)
    await page.locator('input[placeholder*="Amount"]').fill("42.50");
    await page.locator('input[placeholder*="Description"]').fill("E2E lunch");

    // Set today's date — the date input is the only one with type=date
    const today = new Date().toISOString().slice(0, 10);
    await page.locator('input[type="date"]').first().fill(today);

    await page.getByRole("button", { name: /^add$/i }).click();

    // Row appears in the Recent Transactions list
    const row = page.locator(".tx-row", { hasText: "E2E lunch" });
    await expect(row).toBeVisible();
    await expect(row).toContainText(/42[.,]50/);
  });

  test("expense subtracts from balance", async ({ loggedInPage: page }) => {
    // Add an income first
    await page.locator('select').first().selectOption("income");
    await page.locator('input[placeholder*="Amount"]').fill("100.00");
    await page.locator('input[placeholder*="Description"]').fill("E2E income");
    await page.locator('input[type="date"]').first().fill(new Date().toISOString().slice(0, 10));
    await page.getByRole("button", { name: /^add$/i }).click();

    await expect(page.locator(".stat-card.income")).toContainText(/100/);

    // Add an expense
    await page.locator('select').first().selectOption("expense");
    await page.locator('input[placeholder*="Amount"]').fill("30.00");
    await page.locator('input[placeholder*="Description"]').fill("E2E coffee");
    await page.locator('input[type="date"]').first().fill(new Date().toISOString().slice(0, 10));
    await page.getByRole("button", { name: /^add$/i }).click();

    await expect(page.locator(".stat-card.expense")).toContainText(/30/);
    // Balance = income - expense = 70
    await expect(page.locator(".stat-card.positive, .stat-card.negative")).toContainText(/70/);
  });
});
