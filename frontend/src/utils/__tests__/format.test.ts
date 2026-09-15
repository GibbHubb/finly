import { describe, expect, it } from "vitest";
import { formatCurrency, formatDate } from "@/utils/format";

// F36 — `src/utils` sat at 0% while every money figure and date on the
// dashboard goes through these two functions.
describe("formatCurrency", () => {
  it("renders euros with a symbol, grouping and two decimals", () => {
    // NBSP vs plain space differs by ICU build, so assert on the parts.
    const out = formatCurrency(1234.5);
    expect(out).toContain("€");
    expect(out).toContain("1,234.50");
  });

  it("renders zero rather than an empty string", () => {
    expect(formatCurrency(0)).toContain("0.00");
  });

  it("keeps the sign on a negative amount", () => {
    expect(formatCurrency(-42)).toMatch(/-|\(/);
  });

  it("honours a non-default currency", () => {
    const out = formatCurrency(10, "USD");
    expect(out).toMatch(/\$|USD/);
  });
});

describe("formatDate", () => {
  it("renders an ISO date as day / short-month / year", () => {
    const out = formatDate("2026-06-01");
    expect(out).toContain("2026");
    expect(out).toMatch(/Jun/i);
    expect(out).toContain("1");
  });

  it("accepts a full ISO timestamp", () => {
    expect(formatDate("2026-12-25T10:30:00")).toMatch(/Dec/i);
  });
});
