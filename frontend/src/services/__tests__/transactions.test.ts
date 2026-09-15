import { beforeEach, describe, expect, it, vi } from "vitest";
import { http, HttpResponse } from "msw";
import { server } from "@/test/msw/server";
import api from "@/services/api";
import {
  bankService,
  downloadYearReview,
  tagService,
  transactionService,
} from "@/services/transactions";
import type { Transaction } from "@/types";

const tx: Transaction = {
  id: 1,
  amount: "12.50",
  type: "expense",
  category: "food",
  description: "Bakery",
  transaction_date: "2026-09-01",
  currency: "EUR",
  base_amount: null,
  created_at: "2026-09-01T10:00:00",
  parent_transaction_id: null,
  tags: [],
};

describe("transactionService", () => {
  beforeEach(() => {
    localStorage.setItem("token", "test-token");
  });

  it("list forwards filters as query params", async () => {
    let url = "";
    server.use(
      http.get("*/api/v1/transactions/", ({ request }) => {
        url = request.url;
        return HttpResponse.json([tx]);
      })
    );

    await expect(transactionService.list({ category: "food" })).resolves.toHaveLength(1);
    expect(url).toContain("category=food");
  });

  it("list with no filters sends no query string", async () => {
    let url = "";
    server.use(
      http.get("*/api/v1/transactions/", ({ request }) => {
        url = request.url;
        return HttpResponse.json([]);
      })
    );

    await transactionService.list();
    expect(url).not.toContain("?");
  });

  it("create posts the payload and returns the saved row", async () => {
    server.use(http.post("*/api/v1/transactions/", () => HttpResponse.json(tx, { status: 201 })));
    await expect(transactionService.create({ amount: 12.5 } as never)).resolves.toEqual(tx);
  });

  it("remove issues a DELETE for the id", async () => {
    let seen = 0;
    server.use(
      http.delete("*/api/v1/transactions/:id", ({ params }) => {
        seen = Number(params.id);
        return new HttpResponse(null, { status: 204 });
      })
    );

    await transactionService.remove(7);
    expect(seen).toBe(7);
  });

  // F25 — children must reach the API under a `children` key, or the split
  // silently posts an empty body and the server rejects it.
  it("split posts the children under a children key", async () => {
    let body: { children?: unknown } = {};
    server.use(
      http.post("*/api/v1/transactions/:id/split", async ({ request }) => {
        body = (await request.json()) as { children?: unknown };
        return HttpResponse.json(tx);
      })
    );

    await transactionService.split(1, [{ amount: 5, category: "food" }]);
    expect(body.children).toHaveLength(1);
  });

  it("unsplit deletes the split and returns the restored parent", async () => {
    server.use(http.delete("*/api/v1/transactions/:id/split", () => HttpResponse.json(tx)));
    await expect(transactionService.unsplit(1)).resolves.toEqual(tx);
  });

  it("summary passes month and year", async () => {
    let url = "";
    server.use(
      http.get("*/api/v1/transactions/summary", ({ request }) => {
        url = request.url;
        return HttpResponse.json({ month: 9, year: 2026, categories: [] });
      })
    );

    await transactionService.summary(9, 2026);
    expect(url).toContain("month=9");
    expect(url).toContain("year=2026");
  });

  it("forecast passes month and year", async () => {
    let url = "";
    server.use(
      http.get("*/api/v1/transactions/forecast", ({ request }) => {
        url = request.url;
        return HttpResponse.json({ projected: null });
      })
    );

    await transactionService.forecast(9, 2026);
    expect(url).toContain("month=9");
  });

  it("trends defaults to a 6-month window", async () => {
    let url = "";
    server.use(
      http.get("*/api/v1/transactions/trends", ({ request }) => {
        url = request.url;
        return HttpResponse.json([]);
      })
    );

    await transactionService.trends();
    expect(url).toContain("months=6");
  });

  it("trends honours an explicit window", async () => {
    let url = "";
    server.use(
      http.get("*/api/v1/transactions/trends", ({ request }) => {
        url = request.url;
        return HttpResponse.json([]);
      })
    );

    await transactionService.trends(12);
    expect(url).toContain("months=12");
  });

  it("recurring and recurringReview read their endpoints", async () => {
    server.use(
      http.get("*/api/v1/transactions/recurring", () => HttpResponse.json([{ merchant: "coffee" }])),
      http.get("*/api/v1/transactions/recurring-review", () => HttpResponse.json([]))
    );

    await expect(transactionService.recurring()).resolves.toHaveLength(1);
    await expect(transactionService.recurringReview()).resolves.toEqual([]);
  });

  it("resolveRecurringReview posts the merchant and the action", async () => {
    let body: unknown;
    server.use(
      http.post("*/api/v1/transactions/recurring-review", async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({ merchant: "coffee", updated: 3 });
      })
    );

    await transactionService.resolveRecurringReview("coffee", "confirm" as never);
    expect(body).toEqual({ merchant: "coffee", action: "confirm" });
  });

  // The three upload helpers are asserted at the axios call, not over the
  // network: a real File posted through jsdom's XHR never settles under msw,
  // so routing them through the server would only ever test jsdom. What
  // matters here is our code — the field names, the JSON-encoded mapping and
  // the multipart content type — and that is all visible on the call itself.
  it("importCsv posts the file under a 'file' field as multipart", async () => {
    const post = vi.spyOn(api, "post").mockResolvedValue({ data: { imported: 2, skipped: 0 } });

    const file = new File(["date,amount\n"], "statement.csv", { type: "text/csv" });
    await expect(transactionService.importCsv(file)).resolves.toEqual({ imported: 2, skipped: 0 });

    const [url, form, config] = post.mock.calls[0] as [string, FormData, { headers: Record<string, string> }];
    expect(url).toBe("/transactions/import");
    expect((form.get("file") as File).name).toBe("statement.csv");
    expect(config.headers["Content-Type"]).toBe("multipart/form-data");
    post.mockRestore();
  });

  it("importCommit sends the file and a JSON-encoded mapping together", async () => {
    const post = vi.spyOn(api, "post").mockResolvedValue({ data: { imported: 1, skipped: 0 } });

    await transactionService.importCommit(new File(["x"], "s.csv"), { amount: "Bedrag" } as never);

    const [url, form] = post.mock.calls[0] as [string, FormData];
    expect(url).toBe("/transactions/import/commit");
    expect((form.get("file") as File).name).toBe("s.csv");
    expect(JSON.parse(form.get("mapping") as string)).toEqual({ amount: "Bedrag" });
    post.mockRestore();
  });

  it("importPreview posts to the preview endpoint and returns the preview", async () => {
    const post = vi.spyOn(api, "post").mockResolvedValue({ data: { headers: ["date"], rows: [] } });

    await expect(transactionService.importPreview(new File(["x"], "s.csv"))).resolves.toEqual({
      headers: ["date"],
      rows: [],
    });
    expect(post.mock.calls[0][0]).toBe("/transactions/import/preview");
    post.mockRestore();
  });
});

describe("bankService", () => {
  beforeEach(() => localStorage.setItem("token", "test-token"));

  it("connect returns the hosted consent link", async () => {
    server.use(
      http.post("*/api/v1/bank/connect", () =>
        HttpResponse.json({ requisition_id: "r1", link: "https://consent", connection_id: 1 })
      )
    );

    await expect(bankService.connect()).resolves.toMatchObject({ link: "https://consent" });
  });

  it("status returns the connection list", async () => {
    server.use(http.get("*/api/v1/bank/status", () => HttpResponse.json([])));
    await expect(bankService.status()).resolves.toEqual([]);
  });

  it("syncNow reports what each connection did", async () => {
    server.use(
      http.post("*/api/v1/bank/sync", () => HttpResponse.json({ connections: 0, results: [] }))
    );
    await expect(bankService.syncNow()).resolves.toEqual({ connections: 0, results: [] });
  });
});

describe("tagService", () => {
  beforeEach(() => localStorage.setItem("token", "test-token"));

  it("lists, creates, assigns, unassigns and removes tags", async () => {
    server.use(
      http.get("*/api/v1/tags", () => HttpResponse.json([{ id: 1, name: "recurring" }])),
      http.post("*/api/v1/tags", () => HttpResponse.json({ id: 2, name: "holiday" }, { status: 201 })),
      http.delete("*/api/v1/tags/:id", () => new HttpResponse(null, { status: 204 })),
      http.post("*/api/v1/tags/assign/:txId", () => HttpResponse.json([{ id: 2, name: "holiday" }])),
      http.delete("*/api/v1/tags/assign/:txId/:tagId", () => HttpResponse.json([]))
    );

    await expect(tagService.list()).resolves.toHaveLength(1);
    await expect(tagService.create("holiday")).resolves.toMatchObject({ name: "holiday" });
    await expect(tagService.assign(1, "holiday")).resolves.toHaveLength(1);
    await expect(tagService.unassign(1, 2)).resolves.toEqual([]);
    await expect(tagService.remove(2)).resolves.toBeUndefined();
  });
});

describe("downloadYearReview", () => {
  beforeEach(() => localStorage.setItem("token", "test-token"));

  // F28 — the PDF must travel through the axios instance so the JWT goes with
  // it; a plain <a href> would 401. jsdom has no object-URL support, so both
  // sides of the create/revoke pair are stubbed and asserted.
  it("requests the PDF and hands the browser a blob download", async () => {
    let url = "";
    server.use(
      http.get("*/api/v1/reports/year/:year.pdf", ({ request }) => {
        url = request.url;
        return HttpResponse.arrayBuffer(new Uint8Array([37, 80, 68, 70]).buffer, {
          headers: { "Content-Type": "application/pdf" },
        });
      })
    );

    // Patch the two methods, never the URL constructor itself — axios calls
    // `new URL(...)` internally, so stubbing the global breaks the request.
    const createURL = vi.fn(() => "blob:fake");
    const revokeURL = vi.fn();
    const realCreate = URL.createObjectURL;
    const realRevoke = URL.revokeObjectURL;
    URL.createObjectURL = createURL as unknown as typeof URL.createObjectURL;
    URL.revokeObjectURL = revokeURL as unknown as typeof URL.revokeObjectURL;
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});

    await downloadYearReview(2026);

    expect(url).toContain("/reports/year/2026.pdf");
    expect(createURL).toHaveBeenCalledOnce();
    expect(click).toHaveBeenCalledOnce();
    expect(revokeURL).toHaveBeenCalledWith("blob:fake");

    click.mockRestore();
    URL.createObjectURL = realCreate;
    URL.revokeObjectURL = realRevoke;
  });
});
