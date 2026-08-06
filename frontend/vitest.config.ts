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
      exclude: ["**/*.d.ts", "src/test/**"],
      thresholds: {
        lines: 70,
        functions: 70,
        branches: 70,
        statements: 70,
      },
    },
  },
});
