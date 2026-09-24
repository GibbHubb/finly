/**
 * F46 — SplitTransactionModal accessibility + remainder-math tests.
 *
 * Covers what a unit test *can* verify without a real browser:
 *   1. Dialog semantics (role, aria-modal, aria-labelledby → a real heading).
 *   2. Initial focus lands inside the dialog on mount.
 *   3. Escape calls onClose.
 *   4. The Tab-trap wraps at the boundaries (jsdom has no native tab order,
 *      so only the wrap-around edges the component's own keydown handler
 *      implements are testable here — the interior order is a browser's
 *      job and is covered by the manual keyboard pass in the plan's §9).
 *   5. Focus is restored to the trigger element on close/unmount.
 *   6. The integer-cent remainder gate: a sub-cent-per-row discrepancy that
 *      the OLD `Math.abs(remainder) < 0.005` tolerance let through as
 *      "0.00" is rejected (Split stays disabled) under the new cents math.
 */
import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import SplitTransactionModal from "@/components/SplitTransactionModal";
import type { Transaction } from "@/types";

afterEach(() => cleanup());

function makeTx(overrides: Partial<Transaction> = {}): Transaction {
  return {
    id: 1,
    amount: "10.00",
    type: "expense",
    category: "food",
    description: "Groceries",
    transaction_date: "2026-01-01",
    currency: "EUR",
    base_amount: null,
    created_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

describe("SplitTransactionModal — dialog semantics", () => {
  it("has role=dialog, aria-modal=true and aria-labelledby pointing at the heading", () => {
    render(<SplitTransactionModal tx={makeTx()} onClose={vi.fn()} onSplit={vi.fn()} />);
    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveAttribute("aria-modal", "true");
    const labelledBy = dialog.getAttribute("aria-labelledby");
    expect(labelledBy).toBeTruthy();
    const heading = document.getElementById(labelledBy!);
    expect(heading).not.toBeNull();
    expect(heading).toHaveTextContent("Split transaction");
  });

  it("moves focus into the dialog (first amount field) on open", () => {
    render(<SplitTransactionModal tx={makeTx()} onClose={vi.fn()} onSplit={vi.fn()} />);
    expect(document.activeElement).toHaveAccessibleName("Amount for row 1");
  });

  it("calls onClose on Escape", () => {
    const onClose = vi.fn();
    render(<SplitTransactionModal tx={makeTx()} onClose={onClose} onSplit={vi.fn()} />);
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("Tab on the last focusable element wraps to the first", () => {
    render(<SplitTransactionModal tx={makeTx()} onClose={vi.fn()} onSplit={vi.fn()} />);
    // Disabled controls (Split starts disabled — nothing entered yet) are
    // correctly excluded from the trap, so the last *focusable* element in
    // the default state is Cancel, not Split.
    const cancelButton = screen.getByRole("button", { name: "Cancel" });
    cancelButton.focus();
    expect(document.activeElement).toBe(cancelButton);
    fireEvent.keyDown(document, { key: "Tab" });
    expect(document.activeElement).toHaveAccessibleName("Amount for row 1");
  });

  it("Shift+Tab on the first focusable element wraps to the last", () => {
    render(<SplitTransactionModal tx={makeTx()} onClose={vi.fn()} onSplit={vi.fn()} />);
    const firstInput = screen.getByRole("spinbutton", { name: "Amount for row 1" });
    firstInput.focus();
    expect(document.activeElement).toBe(firstInput);
    fireEvent.keyDown(document, { key: "Tab", shiftKey: true });
    // Same reasoning as above: Cancel, not the still-disabled Split, is the
    // last focusable element until the rows balance.
    const cancelButton = screen.getByRole("button", { name: "Cancel" });
    expect(document.activeElement).toBe(cancelButton);
  });

  it("restores focus to the trigger element on unmount", () => {
    const trigger = document.createElement("button");
    trigger.textContent = "Split";
    document.body.appendChild(trigger);
    trigger.focus();
    expect(document.activeElement).toBe(trigger);

    const { unmount } = render(
      <SplitTransactionModal tx={makeTx()} onClose={vi.fn()} onSplit={vi.fn()} />,
    );
    // Focus moved into the dialog on open.
    expect(document.activeElement).not.toBe(trigger);

    unmount();
    expect(document.activeElement).toBe(trigger);
    trigger.remove();
  });
});

describe("SplitTransactionModal — integer-cent remainder gate (F46)", () => {
  it("rejects a 0.004 discrepancy client-side instead of letting it through as 0.00", () => {
    // Parent = 10.00. Two rows entered as 5.002 and 4.994 (bypassing the
    // step="0.01" UI constraint, exactly like a value the browser's number
    // input still accepts via paste or scripting). Their raw float sum is
    // 9.996 — a 0.004 discrepancy that the OLD
    // `Math.round((parentAmount - childSum) * 100) / 100` rounded straight
    // to 0.00, passing `Math.abs(remainder) < 0.005`. But the values
    // actually POSTED (`.toFixed(2)`) round to 5.00 and 4.99 — 9.99, not
    // 10.00 — which is exactly the split the server 422'd.
    render(<SplitTransactionModal tx={makeTx({ amount: "10.00" })} onClose={vi.fn()} onSplit={vi.fn()} />);

    const row1 = screen.getByRole("spinbutton", { name: "Amount for row 1" });
    const row2 = screen.getByRole("spinbutton", { name: "Amount for row 2" });
    fireEvent.change(row1, { target: { value: "5.002" } });
    fireEvent.change(row2, { target: { value: "4.994" } });

    const splitButton = screen.getByRole("button", { name: "Split" });
    expect(splitButton).toBeDisabled();
  });

  it("enables Split once the rows sum to the exact same cents as the parent", () => {
    render(<SplitTransactionModal tx={makeTx({ amount: "10.00" })} onClose={vi.fn()} onSplit={vi.fn()} />);

    const row1 = screen.getByRole("spinbutton", { name: "Amount for row 1" });
    const row2 = screen.getByRole("spinbutton", { name: "Amount for row 2" });
    fireEvent.change(row1, { target: { value: "6.00" } });
    fireEvent.change(row2, { target: { value: "4.00" } });

    const splitButton = screen.getByRole("button", { name: "Split" });
    expect(splitButton).not.toBeDisabled();
  });
});
