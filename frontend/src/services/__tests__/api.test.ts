import { describe, it, expect } from "vitest";
import { shouldRedirectOn401 } from "../api";

/**
 * F37 — the interceptor redirected on EVERY 401, including the one that means
 * "wrong password". Because `window.location.href` is a full page load, React
 * remounted and the "Invalid email or password" message was wiped before it
 * painted: the form silently blanked and said nothing.
 *
 * These pin the distinction that fix depends on.
 */
describe("shouldRedirectOn401", () => {
  it("bounces to /login when a session has expired mid-app", () => {
    expect(shouldRedirectOn401(401, "/transactions")).toBe(true);
    expect(shouldRedirectOn401(401, "/budgets?month=9")).toBe(true);
  });

  it("does NOT bounce when the sign-in attempt itself is rejected", () => {
    expect(shouldRedirectOn401(401, "/auth/login")).toBe(false);
    expect(shouldRedirectOn401(401, "/auth/register")).toBe(false);
    expect(shouldRedirectOn401(401, "/auth/demo-login")).toBe(false);
  });

  it("ignores every other status, including a missing one", () => {
    expect(shouldRedirectOn401(403, "/transactions")).toBe(false);
    expect(shouldRedirectOn401(500, "/transactions")).toBe(false);
    expect(shouldRedirectOn401(undefined, "/transactions")).toBe(false);
  });
});
