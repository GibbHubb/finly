import { beforeEach, describe, expect, it, vi } from "vitest";
import { http, HttpResponse } from "msw";
import { server } from "@/test/msw/server";
import { useAuthStore } from "@/store/authStore";
import { useTransactionStore } from "@/store/transactionStore";
import type { User } from "@/types";

const user = {
  id: 1,
  email: "demo@finly.app",
  full_name: "Demo User",
  is_active: true,
  base_currency: "EUR",
} as User;

function resetStore(): void {
  useAuthStore.setState({ user: null, token: null, refreshToken: null, isLoading: false, baseCurrency: "EUR" });
}

describe("authStore", () => {
  beforeEach(() => {
    localStorage.clear();
    resetStore();
    useTransactionStore.setState({ transactions: [], isLoading: false, error: null });
  });

  it("login stores the access+refresh tokens and the user, and adopts their base currency", async () => {
    server.use(
      http.post("*/api/v1/auth/login", () =>
        HttpResponse.json({ access_token: "jwt-1", refresh_token: "refresh-1" })
      ),
      http.get("*/api/v1/auth/me", () => HttpResponse.json({ ...user, base_currency: "USD" }))
    );

    await useAuthStore.getState().login("demo@finly.app", "pw");

    const s = useAuthStore.getState();
    expect(s.token).toBe("jwt-1");
    expect(s.refreshToken).toBe("refresh-1");
    expect(s.user?.email).toBe("demo@finly.app");
    expect(s.baseCurrency).toBe("USD");
    expect(s.isLoading).toBe(false);
    expect(localStorage.getItem("token")).toBe("jwt-1");
    expect(localStorage.getItem("refresh_token")).toBe("refresh-1");
  });

  it("defaults base currency to EUR when the user has none", async () => {
    server.use(
      http.post("*/api/v1/auth/login", () =>
        HttpResponse.json({ access_token: "jwt-1", refresh_token: "refresh-1" })
      ),
      http.get("*/api/v1/auth/me", () => HttpResponse.json({ ...user, base_currency: null }))
    );

    await useAuthStore.getState().login("demo@finly.app", "pw");
    expect(useAuthStore.getState().baseCurrency).toBe("EUR");
  });

  // F37 — a rejected sign-in used to leave isLoading true forever, so the
  // button stayed disabled reading "Signing in…" and you could not retry.
  it("clears isLoading when the sign-in is rejected, and rethrows", async () => {
    server.use(
      http.post("*/api/v1/auth/login", () =>
        HttpResponse.json({ detail: "Invalid email or password" }, { status: 401 })
      )
    );

    await expect(useAuthStore.getState().login("demo@finly.app", "wrong")).rejects.toBeTruthy();
    expect(useAuthStore.getState().isLoading).toBe(false);
    expect(useAuthStore.getState().token).toBeNull();
  });

  it("demoLogin signs in without credentials", async () => {
    server.use(
      http.post("*/api/v1/auth/demo-login", () =>
        HttpResponse.json({ access_token: "demo-jwt", refresh_token: "demo-refresh" })
      ),
      http.get("*/api/v1/auth/me", () => HttpResponse.json(user))
    );

    await useAuthStore.getState().demoLogin();
    expect(useAuthStore.getState().token).toBe("demo-jwt");
    expect(useAuthStore.getState().refreshToken).toBe("demo-refresh");
    expect(useAuthStore.getState().isLoading).toBe(false);
  });

  it("demoLogin clears isLoading and rethrows when DEMO_MODE is off", async () => {
    server.use(
      http.post("*/api/v1/auth/demo-login", () =>
        HttpResponse.json({ detail: "Not Found" }, { status: 404 })
      )
    );

    await expect(useAuthStore.getState().demoLogin()).rejects.toBeTruthy();
    expect(useAuthStore.getState().isLoading).toBe(false);
  });

  it("logout drops both tokens from the store and localStorage immediately, and revokes server-side", async () => {
    let revokedBody: unknown;
    server.use(
      http.post("*/api/v1/auth/logout", async ({ request }) => {
        revokedBody = await request.json();
        return new HttpResponse(null, { status: 204 });
      })
    );

    localStorage.setItem("token", "jwt-1");
    localStorage.setItem("refresh_token", "refresh-1");
    useAuthStore.setState({ token: "jwt-1", refreshToken: "refresh-1", user, baseCurrency: "USD" });

    useAuthStore.getState().logout();

    // Local state is cleared SYNCHRONOUSLY — the person clicking "Sign out"
    // does not wait on the network call.
    const s = useAuthStore.getState();
    expect(s.token).toBeNull();
    expect(s.refreshToken).toBeNull();
    expect(s.user).toBeNull();
    expect(s.baseCurrency).toBe("EUR");
    expect(localStorage.getItem("token")).toBeNull();
    expect(localStorage.getItem("refresh_token")).toBeNull();

    // The revoke call still goes out in the background.
    await vi.waitFor(() => expect(revokedBody).toEqual({ refresh_token: "refresh-1" }));
  });

  // F42 — code-review catch: api.ts's silent-refresh interceptor rotates the
  // pair straight into localStorage without touching this store, so a
  // session that survived one silent refresh has a STALE store.refreshToken.
  // logout() must send the CURRENT (localStorage) token, or it revokes an
  // already-dead row and leaves the real session live for up to 14 days.
  it("logout revokes the CURRENT refresh token, not a stale one left in the store", async () => {
    let revokedBody: unknown;
    server.use(
      http.post("*/api/v1/auth/logout", async ({ request }) => {
        revokedBody = await request.json();
        return new HttpResponse(null, { status: 204 });
      })
    );

    // Simulate: store still holds the token from the original login, but a
    // silent refresh has since rotated localStorage to a new pair (exactly
    // what api.ts's interceptor does, without going through this store).
    localStorage.setItem("token", "jwt-2-rotated");
    localStorage.setItem("refresh_token", "refresh-2-rotated");
    useAuthStore.setState({ token: "jwt-1-stale", refreshToken: "refresh-1-stale", user, baseCurrency: "USD" });

    useAuthStore.getState().logout();

    await vi.waitFor(() => expect(revokedBody).toEqual({ refresh_token: "refresh-2-rotated" }));
  });

  it("logout does not throw when the server-side revoke fails", async () => {
    server.use(http.post("*/api/v1/auth/logout", () => HttpResponse.json({ detail: "nope" }, { status: 500 })));

    localStorage.setItem("token", "jwt-1");
    localStorage.setItem("refresh_token", "refresh-1");
    useAuthStore.setState({ token: "jwt-1", refreshToken: "refresh-1", user, baseCurrency: "USD" });

    expect(() => useAuthStore.getState().logout()).not.toThrow();
    expect(useAuthStore.getState().token).toBeNull();
  });

  it("logout is a no-op network-wise when there was no refresh token", () => {
    // No handler registered for /auth/logout: if this called it, msw's
    // onUnhandledRequest ("error") would fail the test.
    useAuthStore.setState({ token: "jwt-1", refreshToken: null, user, baseCurrency: "USD" });
    expect(() => useAuthStore.getState().logout()).not.toThrow();
  });

  it("fetchMe is a no-op when there is no token", async () => {
    // No handler registered: if this made a request, msw's onUnhandledRequest
    // ("error") would fail the test — which is the assertion.
    await useAuthStore.getState().fetchMe();
    expect(useAuthStore.getState().user).toBeNull();
  });

  it("fetchMe loads the user when a token is present", async () => {
    localStorage.setItem("token", "jwt-1");
    server.use(http.get("*/api/v1/auth/me", () => HttpResponse.json(user)));

    await useAuthStore.getState().fetchMe();
    expect(useAuthStore.getState().user?.id).toBe(1);
  });

  it("setBaseCurrency updates optimistically, then keeps the server's answer", async () => {
    useAuthStore.setState({ user, baseCurrency: "EUR" });
    server.use(
      http.patch("*/api/v1/auth/me", () => HttpResponse.json({ ...user, base_currency: "USD" })),
      http.get("*/api/v1/transactions/", () => HttpResponse.json([]))
    );

    await useAuthStore.getState().setBaseCurrency("USD");

    expect(useAuthStore.getState().baseCurrency).toBe("USD");
    expect(useAuthStore.getState().user?.base_currency).toBe("USD");
  });

  it("setBaseCurrency rolls back when the server rejects it", async () => {
    useAuthStore.setState({ user, baseCurrency: "EUR" });
    server.use(
      http.patch("*/api/v1/auth/me", () => HttpResponse.json({ detail: "nope" }, { status: 400 }))
    );

    await useAuthStore.getState().setBaseCurrency("USD");

    expect(useAuthStore.getState().baseCurrency).toBe("EUR");
    expect(useAuthStore.getState().user?.base_currency).toBe("EUR");
  });

  it("F55: a refused change (FX outage) rolls back AND surfaces the server's message", async () => {
    const detail = "Exchange rates are unavailable right now, so your base currency was not changed. Try again later.";
    useAuthStore.setState({ user, baseCurrency: "EUR", baseCurrencyError: null });
    server.use(
      http.patch("*/api/v1/auth/me", () => HttpResponse.json({ detail }, { status: 503 }))
    );

    await useAuthStore.getState().setBaseCurrency("USD");

    expect(useAuthStore.getState().baseCurrency).toBe("EUR");
    expect(useAuthStore.getState().user?.base_currency).toBe("EUR");
    expect(useAuthStore.getState().baseCurrencyError).toBe(detail);
  });
});
