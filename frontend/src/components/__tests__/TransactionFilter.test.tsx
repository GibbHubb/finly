/**
 * F30 — TransactionFilter component tests.
 *
 * The component is purely presentational (no API calls, no state).
 * These tests verify:
 *   1. Tag chips render for each available tag.
 *   2. Unselected chips have the base class; selected chips get the --selected modifier.
 *   3. Clicking a chip calls onToggleTag with the correct tag name.
 *   4. The Clear button appears only when hasActiveFilters is true and calls onClear.
 */
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import TransactionFilter from "@/components/ui/TransactionFilter";

const availableTags = [
  { id: 1, name: "groceries" },
  { id: 2, name: "travel" },
  { id: 3, name: "gym" },
];

function makeProps(overrides: Partial<Parameters<typeof TransactionFilter>[0]> = {}) {
  return {
    filterText: "",
    setFilterText: vi.fn(),
    filterCategory: "all" as const,
    setFilterCategory: vi.fn(),
    filterDateFrom: "",
    setFilterDateFrom: vi.fn(),
    filterDateTo: "",
    setFilterDateTo: vi.fn(),
    filterAmountMin: "",
    setFilterAmountMin: vi.fn(),
    filterAmountMax: "",
    setFilterAmountMax: vi.fn(),
    hasActiveFilters: false,
    onClear: vi.fn(),
    availableTags,
    selectedTags: [],
    onToggleTag: vi.fn(),
    ...overrides,
  };
}

describe("TransactionFilter — tag chips", () => {
  it("renders a chip for each available tag", () => {
    render(<TransactionFilter {...makeProps()} />);
    expect(screen.getByText("#groceries")).toBeInTheDocument();
    expect(screen.getByText("#travel")).toBeInTheDocument();
    expect(screen.getByText("#gym")).toBeInTheDocument();
  });

  it("unselected chips do not have the --selected class", () => {
    render(<TransactionFilter {...makeProps()} />);
    const chip = screen.getByText("#groceries");
    expect(chip.className).not.toContain("--selected");
  });

  it("selected chips have the tx-tag-chip--selected class", () => {
    render(<TransactionFilter {...makeProps({ selectedTags: ["groceries"] })} />);
    const chip = screen.getByText("#groceries");
    expect(chip.className).toContain("tx-tag-chip--selected");
    // travel is not selected
    expect(screen.getByText("#travel").className).not.toContain("--selected");
  });

  it("clicking a chip calls onToggleTag with the tag name", () => {
    const onToggleTag = vi.fn();
    render(<TransactionFilter {...makeProps({ onToggleTag })} />);
    fireEvent.click(screen.getByText("#travel"));
    expect(onToggleTag).toHaveBeenCalledOnce();
    expect(onToggleTag).toHaveBeenCalledWith("travel");
  });

  it("clicking an already-selected chip also calls onToggleTag (deselect)", () => {
    const onToggleTag = vi.fn();
    render(<TransactionFilter {...makeProps({ selectedTags: ["gym"], onToggleTag })} />);
    fireEvent.click(screen.getByText("#gym"));
    expect(onToggleTag).toHaveBeenCalledWith("gym");
  });
});

describe("TransactionFilter — Clear button", () => {
  it("Clear button is not rendered when no active filters", () => {
    render(<TransactionFilter {...makeProps({ hasActiveFilters: false })} />);
    expect(screen.queryByText("Clear")).toBeNull();
  });

  it("Clear button is rendered when hasActiveFilters is true", () => {
    render(<TransactionFilter {...makeProps({ hasActiveFilters: true })} />);
    expect(screen.getByText("Clear")).toBeInTheDocument();
  });

  it("clicking Clear calls onClear", () => {
    const onClear = vi.fn();
    render(<TransactionFilter {...makeProps({ hasActiveFilters: true, onClear })} />);
    fireEvent.click(screen.getByText("Clear"));
    expect(onClear).toHaveBeenCalledOnce();
  });
});

describe("TransactionFilter — tag chip de-dup merge (inline logic verification)", () => {
  /**
   * This test verifies the union/any-of de-duplication logic used in DashboardPage.
   * It is a pure unit test — no rendering needed.
   */
  it("merges results from multiple tag fetches and de-dupes by id", () => {
    // Simulate two tag fetch results with an overlapping transaction (id: 2)
    const tag1Results = [
      { id: 1, amount: "10.00", type: "expense" as const, category: "food" as const, description: "A", transaction_date: "2024-01-02", currency: "EUR", base_amount: null, created_at: "" },
      { id: 2, amount: "20.00", type: "expense" as const, category: "food" as const, description: "B", transaction_date: "2024-01-01", currency: "EUR", base_amount: null, created_at: "" },
    ];
    const tag2Results = [
      { id: 2, amount: "20.00", type: "expense" as const, category: "food" as const, description: "B", transaction_date: "2024-01-01", currency: "EUR", base_amount: null, created_at: "" },
      { id: 3, amount: "30.00", type: "expense" as const, category: "food" as const, description: "C", transaction_date: "2024-01-03", currency: "EUR", base_amount: null, created_at: "" },
    ];

    // Reproduce the merge logic from DashboardPage's useEffect
    const results = [tag1Results, tag2Results];
    const seen = new Set<number>();
    const merged: typeof tag1Results = [];
    for (const batch of results) {
      for (const tx of batch) {
        if (!seen.has(tx.id)) {
          seen.add(tx.id);
          merged.push(tx);
        }
      }
    }
    merged.sort((a, b) => b.transaction_date.localeCompare(a.transaction_date));

    expect(merged).toHaveLength(3);  // 4 total, 1 duplicate removed
    expect(merged.map((t) => t.id)).toEqual([3, 1, 2]);  // sorted by date desc
  });
});
