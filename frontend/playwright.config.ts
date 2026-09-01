import { defineConfig, devices } from "@playwright/test";

const FRONTEND_PORT = 5173;
const BACKEND_PORT = 8000;
const FRONTEND_URL = process.env.E2E_BASE_URL ?? `http://127.0.0.1:${FRONTEND_PORT}`;

export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  expect: { timeout: 5_000 },
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,                // sequential — tests share the same DB user
  reporter: process.env.CI ? [["github"], ["list"]] : "list",
  use: {
    baseURL: FRONTEND_URL,
    trace: "retain-on-failure",
    video: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
  ],
  // Spin up backend (with E2E_MODE) and frontend automatically.
  webServer: process.env.E2E_BASE_URL
    ? undefined
    : [
        {
          command:
            "cd ../backend && E2E_MODE=1 DATABASE_URL=sqlite:///./e2e.db " +
            "python -m uvicorn app.main:app --host 127.0.0.1 --port " + BACKEND_PORT,
          url: `http://127.0.0.1:${BACKEND_PORT}/health`,
          reuseExistingServer: !process.env.CI,
          timeout: 60_000,
        },
        {
          command: `npm run dev -- --host 127.0.0.1 --port ${FRONTEND_PORT}`,
          url: FRONTEND_URL,
          reuseExistingServer: !process.env.CI,
          timeout: 60_000,
        },
      ],
});
