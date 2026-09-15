import { beforeEach, describe, expect, it } from "vitest";
import { http, HttpResponse } from "msw";
import { server } from "@/test/msw/server";
import { authService } from "@/services/auth";
import type { User } from "@/types";

const user: User = {
  id: 1,
  email: "demo@finly.app",
  full_name: "Demo User",
  is_active: true,
  base_currency: "EUR",
} as User;

describe("authService", () => {
  beforeEach(() => {
    localStorage.setItem("token", "test-token");
  });

  it("register posts the credentials and returns the created user", async () => {
    let body: unknown;
    server.use(
      http.post("*/api/v1/auth/register", async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(user, { status: 201 });
      })
    );

    await expect(authService.register("demo@finly.app", "pw", "Demo User")).resolves.toEqual(user);
    expect(body).toEqual({ email: "demo@finly.app", password: "pw", full_name: "Demo User" });
  });

  // The backend's token route is OAuth2 form-encoded, not JSON — a change to
  // that would be silent until a real sign-in failed.
  it("login sends form fields named username/password and returns the token", async () => {
    let username: string | null = null;
    server.use(
      http.post("*/api/v1/auth/login", async ({ request }) => {
        const form = await request.formData();
        username = form.get("username") as string;
        return HttpResponse.json({ access_token: "jwt-abc" });
      })
    );

    await expect(authService.login("demo@finly.app", "pw")).resolves.toBe("jwt-abc");
    expect(username).toBe("demo@finly.app");
  });

  it("demoLogin posts no credentials at all", async () => {
    let hadBody = true;
    server.use(
      http.post("*/api/v1/auth/demo-login", async ({ request }) => {
        hadBody = Boolean(await request.text());
        return HttpResponse.json({ access_token: "demo-jwt" });
      })
    );

    await expect(authService.demoLogin()).resolves.toBe("demo-jwt");
    expect(hadBody).toBe(false);
  });

  it("demoLogin rejects when the deployment has DEMO_MODE off (404)", async () => {
    server.use(
      http.post("*/api/v1/auth/demo-login", () =>
        HttpResponse.json({ detail: "Not Found" }, { status: 404 })
      )
    );

    await expect(authService.demoLogin()).rejects.toBeTruthy();
  });

  it("me returns the current user", async () => {
    server.use(http.get("*/api/v1/auth/me", () => HttpResponse.json(user)));
    await expect(authService.me()).resolves.toEqual(user);
  });

  it("updateMe patches only the fields given", async () => {
    let body: unknown;
    server.use(
      http.patch("*/api/v1/auth/me", async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({ ...user, base_currency: "USD" });
      })
    );

    const updated = await authService.updateMe({ base_currency: "USD" });
    expect(body).toEqual({ base_currency: "USD" });
    expect(updated.base_currency).toBe("USD");
  });
});
