import { configDefaults, defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
  test: {
    // F-test1 — vitest's default include matches `e2e/*.spec.ts`, which are
    // Playwright specs it cannot transform. They surfaced as 4 failing test
    // FILES on every run, so a genuinely broken suite looked identical to a
    // healthy one. Playwright has its own runner with `testDir: "./e2e"`, so
    // excluding them here costs nothing.
    exclude: [...configDefaults.exclude, "e2e/**"],
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    css: false,
    coverage: {
      provider: "v8",
      reporter: ["text", "html", "lcov"],
      include: ["src/services/**", "src/store/**", "src/hooks/**", "src/utils/**"],
      // F36 — `**/__tests__/**` was missing, so the test files inside
      // src/store and src/services counted as covered source and flattered
      // every figure. Excluding them lowers the reported number and makes it
      // mean something.
      exclude: ["**/*.d.ts", "src/test/**", "**/__tests__/**"],
      // A RATCHET at where coverage actually is, not a target.
      //
      // F34 found these at 70 across the board — set in April, when these four
      // directories held a handful of files — while the real figures had fallen
      // to lines 22.2 / functions 47.4 / branches 67.6 after twenty-eight
      // commits of features landed on a branch CI never ran on. F34 lowered the
      // gate to those real numbers rather than delete it, on the grounds that a
      // ratchet can only be raised.
      //
      // F36 (2026-09-02) raised it back and then some: `auth.ts`,
      // `transactions.ts`, `rules.ts`, `savings.ts`, `authStore`,
      // `savingsStore`, `transactionStore`, both `utils` and all three hooks
      // went from 0% to covered, and the measured figures are now lines 99.2 /
      // functions 100 / branches 95.8 — past the original 70 bar, not back to
      // it. The thresholds below sit a few points under the measured numbers:
      // close enough that dropping a tested module trips the gate, loose enough
      // that an ordinary refactor does not.
      thresholds: {
        lines: 95,
        functions: 95,
        branches: 92,
        statements: 95,
      },
    },
  },
});
