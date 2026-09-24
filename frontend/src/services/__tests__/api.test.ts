import { afterEach, beforeEach, describe, it, expect } from "vitest";
import { http, HttpResponse, delay } from "msw";
import { server } from "@/test/msw/server";
import api, { shouldRedirectOn401, setTokens, getAccessToken, getRefreshToken } from "../api";

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

  // F42 — a failed /auth/refresh must not itself be treated as "session
  // expired, go refresh" (that is the infinite loop the single-flight logic
  // below has to avoid). It IS the refresh attempt.
  it("does NOT bounce on a 401 FROM /auth/refresh itself", () => {
    expect(shouldRedirectOn401(401, "/auth/refresh")).toBe(false);
  });
});

// F42 — silent refresh, single-flight.
describe("silent refresh", () => {
  let originalLocation: Location;

  beforeEach(() => {
    localStorage.clear();
    // Replace `window.location` with a plain writable stub so the
    // interceptor's `window.location.href = "/login"` is a harmless property
    // set in jsdom instead of an unimplemented real navigation.
    originalLocation = window.location;
    // @ts-expect-error — intentionally replacing with a minimal stub for the test
    delete window.location;
    // @ts-expect-error — same
    window.location = { href: "http://localhost/dashboard" };
  });

  afterEach(() => {
    // @ts-expect-error — restoring the real Location object
    window.location = originalLocation;
  });

  it("shares ONE refresh call across concurrent 401s, then retries both requests", async () => {
    setTokens("expired-access", "valid-refresh");
    let refreshCalls = 0;

    server.use(
      http.get("*/api/v1/thing-a", ({ request }) => {
        if (request.headers.get("authorization") === "Bearer expired-access") {
          return HttpResponse.json({ detail: "expired" }, { status: 401 });
        }
        return HttpResponse.json({ ok: "a" });
      }),
      http.get("*/api/v1/thing-b", ({ request }) => {
        if (request.headers.get("authorization") === "Bearer expired-access") {
          return HttpResponse.json({ detail: "expired" }, { status: 401 });
        }
        return HttpResponse.json({ ok: "b" });
      }),
      http.post("*/api/v1/auth/refresh", async ({ request }) => {
        refreshCalls += 1;
        const body = (await request.json()) as { refresh_token: string };
        expect(body.refresh_token).toBe("valid-refresh");
        await delay(20); // widen the race window so both 401s land first
        return HttpResponse.json({ access_token: "new-access", refresh_token: "new-refresh" });
      })
    );

    const [a, b] = await Promise.all([api.get("/thing-a"), api.get("/thing-b")]);

    expect(refreshCalls).toBe(1);
    expect(a.data).toEqual({ ok: "a" });
    expect(b.data).toEqual({ ok: "b" });
    expect(getAccessToken()).toBe("new-access");
    expect(getRefreshToken()).toBe("new-refresh");
  });

  it("redirects to /login and clears tokens when the refresh itself fails", async () => {
    setTokens("expired-access", "dead-refresh");

    server.use(
      http.get("*/api/v1/thing-c", () => HttpResponse.json({ detail: "expired" }, { status: 401 })),
      http.post("*/api/v1/auth/refresh", () => HttpResponse.json({ detail: "invalid" }, { status: 401 }))
    );

    await expect(api.get("/thing-c")).rejects.toBeTruthy();

    expect(window.location.href).toBe("/login");
    expect(getAccessToken()).toBeNull();
    expect(getRefreshToken()).toBeNull();
  });

  it("does not loop when the RETRIED request 401s again", async () => {
    setTokens("expired-access", "valid-refresh");
    let thingCalls = 0;

    server.use(
      http.get("*/api/v1/thing-d", () => {
        thingCalls += 1;
        return HttpResponse.json({ detail: "still no" }, { status: 401 });
      }),
      http.post("*/api/v1/auth/refresh", () =>
        HttpResponse.json({ access_token: "new-access", refresh_token: "new-refresh" })
      )
    );

    await expect(api.get("/thing-d")).rejects.toBeTruthy();

    // One try, one retry after refresh — never a second refresh-and-retry.
    expect(thingCalls).toBe(2);
    expect(window.location.href).toBe("/login");
  });

  // F42 code-review catch: a network/5xx failure talking to /auth/refresh is
  // NOT the same as the server saying the token is invalid. It used to log
  // out a session with a perfectly good, unexpired refresh token on a blip.
  it("does NOT clear tokens or redirect when /auth/refresh fails transiently (5xx)", async () => {
    setTokens("expired-access", "still-valid-refresh");

    server.use(
      http.get("*/api/v1/thing-e", () => HttpResponse.json({ detail: "expired" }, { status: 401 })),
      http.post("*/api/v1/auth/refresh", () => HttpResponse.json({ detail: "db down" }, { status: 503 }))
    );

    await expect(api.get("/thing-e")).rejects.toBeTruthy();

    expect(window.location.href).toBe("http://localhost/dashboard"); // unchanged, no redirect
    expect(getAccessToken()).toBe("expired-access"); // untouched — still there for the next attempt
    expect(getRefreshToken()).toBe("still-valid-refresh");
  });
});
