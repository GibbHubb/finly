import { beforeEach, describe, expect, it } from "vitest";
import { http, HttpResponse } from "msw";
import { server } from "@/test/msw/server";
import { rulesService } from "@/services/rules";
import type { CategorisationRule } from "@/types";

const rule: CategorisationRule = {
  id: 1,
  match_type: "contains",
  match_value: "albert heijn",
  category: "food",
  priority: 1,
  enabled: true,
  created_at: "2026-09-01T10:00:00",
} as CategorisationRule;

describe("rulesService", () => {
  beforeEach(() => localStorage.setItem("token", "test-token"));

  it("list returns the rules", async () => {
    server.use(http.get("*/api/v1/categorisation-rules/", () => HttpResponse.json([rule])));
    await expect(rulesService.list()).resolves.toHaveLength(1);
  });

  it("create posts the payload", async () => {
    let body: unknown;
    server.use(
      http.post("*/api/v1/categorisation-rules/", async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(rule, { status: 201 });
      })
    );

    await rulesService.create({ match_type: "contains", match_value: "albert heijn", category: "food" } as never);
    expect(body).toEqual({ match_type: "contains", match_value: "albert heijn", category: "food" });
  });

  it("update patches the rule by id", async () => {
    let id = 0;
    server.use(
      http.patch("*/api/v1/categorisation-rules/:id", ({ params }) => {
        id = Number(params.id);
        return HttpResponse.json({ ...rule, category: "shopping" });
      })
    );

    await expect(rulesService.update(1, { category: "shopping" } as never)).resolves.toMatchObject({
      category: "shopping",
    });
    expect(id).toBe(1);
  });

  it("remove deletes the rule", async () => {
    server.use(
      http.delete("*/api/v1/categorisation-rules/:id", () => new HttpResponse(null, { status: 204 }))
    );
    await expect(rulesService.remove(1)).resolves.toBeUndefined();
  });

  // The apply route is a POST to a bare /apply path — easy to break into a
  // 405 by "tidying" it to a trailing slash, and nothing else would notice.
  it("applyNow posts to /apply and reports how many rows changed", async () => {
    server.use(
      http.post("*/api/v1/categorisation-rules/apply", () => HttpResponse.json({ updated: 17 }))
    );
    await expect(rulesService.applyNow()).resolves.toEqual({ updated: 17 });
  });
});
