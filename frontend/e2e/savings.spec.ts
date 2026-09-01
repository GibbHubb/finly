import { test, expect } from "./fixtures";

test.describe("savings goals", () => {
  test("create a goal then add a contribution and see progress advance", async ({ loggedInPage: page }) => {
    await page.goto("/savings");
    await expect(page.getByRole("heading", { name: /savings goals/i })).toBeVisible();

    // F37 — every locator here names the field by its placeholder rather than
    // its position. The previous version used .first() / .last() on
    // `input[type=number]`, which worked only while the page had no goals: once
    // a goal row exists it renders ABOVE the new-goal form, so `.last()` was
    // the form's Target field. The contribution went into "target amount", the
    // row's + Add saw an empty box and added nothing, and the goal sat at
    // €0.00 — which reads as a broken feature and was a broken test.
    await page.locator('input[placeholder="Holiday fund"]').fill("Holiday fund");
    await page.locator('input[placeholder="1500.00"]').fill("500");
    await page.getByRole("button", { name: /create goal/i }).click();

    // The goal row renders with its target.
    await expect(page.locator("body")).toContainText("Holiday fund");
    await expect(page.locator("body")).toContainText(/500/);

    // Contribute, using the row's own Amount box.
    await page.locator('input[placeholder="Amount"]').first().fill("125");
    await page.getByRole("button", { name: /\+ Add/ }).first().click();

    // 125 of 500 = 25%.
    await expect(page.locator("body")).toContainText(/25\s*%|125/);
  });
});
