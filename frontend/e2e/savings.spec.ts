import { test, expect } from "./fixtures";

test.describe("savings goals", () => {
  test("create a goal then add a contribution and see progress advance", async ({ loggedInPage: page }) => {
    await page.goto("/savings");
    await expect(page.getByRole("heading", { name: /savings goals/i })).toBeVisible();

    // Fill the new-goal form. Selectors are tolerant — the SavingsPage form has
    // name, target_amount, deadline.
    const nameInput = page.locator('input[type="text"]').first();
    await nameInput.fill("Holiday fund");

    const targetInput = page.locator('input[type="number"]').first();
    await targetInput.fill("500");

    await page.getByRole("button", { name: /create|add|save/i }).first().click();

    // Goal row renders
    const goal = page.locator("body", { hasText: "Holiday fund" });
    await expect(goal).toBeVisible();

    // Make a contribution. Find the row's "Add" / "+" button or amount input.
    // Strategy: the row should have at least one number input + an Add button.
    const contributionInput = page.locator('input[type="number"]').last();
    await contributionInput.fill("125");
    await page.getByRole("button", { name: /add|deposit|contribute|\+/i }).first().click();

    // Progress should reflect 125/500 = 25%
    await expect(page.locator("body")).toContainText(/25\s*%|125/);
  });
});
