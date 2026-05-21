import { test as base, expect, Page } from "@playwright/test";

export const E2E_USER = {
  email: "e2e@finly.dev",
  password: "e2e-pass-123",
  name: "E2E User",
};

const BACKEND_URL = process.env.E2E_BACKEND_URL ?? "http://127.0.0.1:8000";

/** Wipe + reseed the backend's test user. Run before every spec for isolation. */
async function resetBackend(page: Page) {
  const res = await page.request.post(`${BACKEND_URL}/api/v1/test/reset`);
  if (!res.ok()) {
    throw new Error(`Backend /test/reset failed (${res.status()}). Is E2E_MODE=1 set?`);
  }
}

/** Sign the standard E2E user in via the UI. */
async function signIn(page: Page) {
  await page.goto("/login");
  await page.getByLabel("Email").fill(E2E_USER.email);
  await page.getByLabel("Password").fill(E2E_USER.password);
  await page.getByRole("button", { name: /sign in/i }).click();
  await expect(page).toHaveURL(/\/dashboard/);
}

type Fixtures = {
  loggedInPage: Page;
};

export const test = base.extend<Fixtures>({
  loggedInPage: async ({ page }, use) => {
    await resetBackend(page);
    await signIn(page);
    await use(page);
  },
});

export { expect };
export { resetBackend, signIn };
