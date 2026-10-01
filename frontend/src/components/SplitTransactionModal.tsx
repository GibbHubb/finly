// F25 — split a transaction into >=2 child rows that sum exactly to the
// parent. v1: simple modal with N rows; live remainder + exact-sum gate.
// F46 — dialog semantics (role, focus trap, Escape, focus restore) and an
// integer-cent remainder so the client gate matches the server's exact-cent
// Decimal equality (services/transactions.py) instead of a float tolerance.
import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import type { Transaction, Category } from "@/types";
import { transactionService } from "@/services/transactions";
import { useTransactionStore } from "@/store/transactionStore";
import { apiErrorMessage } from "@/utils/errors";

const CATEGORIES: Category[] = [
  "housing", "food", "transport", "entertainment",
  "health", "shopping", "salary", "freelance", "other",
];

interface ChildRow {
  amount: string;
  category: Category;
  description: string;
}

interface Props {
  tx: Transaction;
  onClose: () => void;
  onSplit: () => void;  // parent refetches transactions
}

// F46 — round to whole cents the same way the value is actually submitted
// (`.toFixed(2)`), so the client-side gate cannot pass on a discrepancy the
// server then rejects. Summing floats first and rounding once at the end
// (the old `Math.round((parentAmount - childSum) * 100) / 100`) let a
// sub-cent-per-row drift slip through as "0.00" while the per-row values
// actually submitted did not sum to the parent.
const toCents = (v: string): number => Math.round((parseFloat(v) || 0) * 100);

const FOCUSABLE_SELECTOR =
  'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), ' +
  'textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

const MODAL_TITLE_ID = "split-modal-title";

export default function SplitTransactionModal({ tx, onClose, onSplit }: Props) {
  const parentAmount = parseFloat(tx.amount);
  const parentCents = Math.round(parentAmount * 100);
  const [rows, setRows] = useState<ChildRow[]>([
    { amount: "", category: tx.category, description: "" },
    { amount: "", category: tx.category, description: "" },
  ]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const modalRef = useRef<HTMLDivElement>(null);
  const firstInputRef = useRef<HTMLInputElement>(null);
  const triggerRef = useRef<Element | null>(null);
  // F46 — always-current ref so the mount-only effect below can call the
  // latest `onClose` without re-running (and re-yanking focus) on every
  // parent re-render.
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  const childCents = useMemo(
    () => rows.reduce((s, r) => s + toCents(r.amount), 0),
    [rows],
  );
  const remainderCents = parentCents - childCents;
  const remainder = remainderCents / 100;
  const canSubmit =
    rows.length >= 2 &&
    rows.every((r) => toCents(r.amount) > 0) &&
    remainderCents === 0;

  // F46 — focus management: remember the trigger, move focus into the
  // dialog on open, trap Tab within it, close on Escape, restore focus to
  // the trigger on close (mount/unmount only — deps intentionally empty).
  //
  // F46-fu — and make everything behind the dialog inert. The dialog is
  // portalled to <body> (below) so it is no longer inside #root; `inert` on
  // #root then takes the page out of the tab order, the pointer and the
  // accessibility tree in one attribute, which `aria-modal` alone only asks
  // screen readers to honour. Leave an already-inert root alone, and lift it
  // BEFORE restoring focus — an inert trigger cannot take focus.
  useEffect(() => {
    triggerRef.current = document.activeElement;
    firstInputRef.current?.focus();
    const appRoot = document.getElementById("root");
    const madeInert = !!appRoot && !appRoot.hasAttribute("inert");
    if (madeInert) appRoot.setAttribute("inert", "");

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onCloseRef.current();
        return;
      }
      if (e.key !== "Tab" || !modalRef.current) return;
      const focusable = Array.from(
        modalRef.current.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR),
      );
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      const active = document.activeElement;
      if (e.shiftKey) {
        if (active === first || !modalRef.current.contains(active)) {
          e.preventDefault();
          last.focus();
        }
      } else {
        if (active === last || !modalRef.current.contains(active)) {
          e.preventDefault();
          first.focus();
        }
      }
    };

    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      if (madeInert) appRoot.removeAttribute("inert");
      if (triggerRef.current instanceof HTMLElement) {
        triggerRef.current.focus();
      }
    };
  }, []);

  const update = (i: number, patch: Partial<ChildRow>) =>
    setRows((prev) => prev.map((r, idx) => (idx === i ? { ...r, ...patch } : r)));

  const addRow = () =>
    setRows((prev) => [...prev, { amount: "", category: tx.category, description: "" }]);

  const removeRow = (i: number) =>
    setRows((prev) => (prev.length <= 2 ? prev : prev.filter((_, idx) => idx !== i)));

  const submit = async () => {
    if (!canSubmit || busy) return;
    setBusy(true);
    setError(null);
    try {
      const updated = await transactionService.split(
        tx.id,
        // F46 — derive the submitted amount from the same cents value the
        // gate above checked, not a second independent `.toFixed(2)` that
        // could round differently and reintroduce the drift.
        rows.map((r) => ({
          amount: (toCents(r.amount) / 100).toFixed(2),
          category: r.category,
          description: r.description || undefined,
        })),
      );
      useTransactionStore.getState().pushBudgetAlerts(updated.budget_alerts); // F53
      onSplit();
      onClose();
    } catch (err: unknown) {
      setError(apiErrorMessage(err, "Failed to split"));
    } finally {
      setBusy(false);
    }
  };

  return createPortal(
    // F46 — the backdrop's click-to-close is a mouse convenience; Escape and
    // the Cancel button (both fully keyboard-reachable) are the equivalent,
    // so the two eslint-disables below are deliberate, not an oversight.
    // eslint-disable-next-line jsx-a11y/click-events-have-key-events, jsx-a11y/no-static-element-interactions
    <div style={overlay} onClick={onClose}>
      {/* eslint-disable-next-line jsx-a11y/click-events-have-key-events, jsx-a11y/no-noninteractive-element-interactions */}
      <div
        ref={modalRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={MODAL_TITLE_ID}
        style={modal}
        onClick={(e) => e.stopPropagation()}
      >
        <h3 id={MODAL_TITLE_ID} style={{ marginTop: 0 }}>Split transaction</h3>
        <p style={{ color: "var(--muted)", fontSize: "0.85rem", marginTop: 0 }}>
          {tx.description || "(no description)"} — {tx.category} —{" "}
          <strong>{parentAmount.toFixed(2)} {tx.currency}</strong>
        </p>

        {rows.map((r, i) => (
          <div key={i} style={rowStyle}>
            <input
              ref={i === 0 ? firstInputRef : undefined}
              aria-label={`Amount for row ${i + 1}`}
              type="number"
              step="0.01"
              min="0"
              placeholder="amount"
              value={r.amount}
              onChange={(e) => update(i, { amount: e.target.value })}
              style={{ ...inputStyle, width: "100px" }}
              disabled={busy}
            />
            <select
              aria-label={`Category for row ${i + 1}`}
              value={r.category}
              onChange={(e) => update(i, { category: e.target.value as Category })}
              style={inputStyle}
              disabled={busy}
            >
              {CATEGORIES.map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
            <input
              aria-label={`Description for row ${i + 1}`}
              type="text"
              placeholder="description (optional)"
              value={r.description}
              onChange={(e) => update(i, { description: e.target.value })}
              style={{ ...inputStyle, flex: 1 }}
              disabled={busy}
            />
            <button
              onClick={() => removeRow(i)}
              disabled={rows.length <= 2 || busy}
              title={rows.length <= 2 ? "Minimum 2 children" : "Remove this row"}
              aria-label={rows.length <= 2 ? "Minimum 2 children" : `Remove row ${i + 1}`}
              style={delBtn}
            >
              ✕
            </button>
          </div>
        ))}

        <button onClick={addRow} disabled={busy} style={{ ...btn, marginTop: "0.4rem" }}>
          + Add row
        </button>

        <div style={{ marginTop: "0.8rem", padding: "0.5rem", background: "rgba(15,23,42,0.4)", borderRadius: "0.4rem", fontSize: "0.85rem" }}>
          Children sum: <strong>{(childCents / 100).toFixed(2)}</strong> ·
          {" "}Parent: <strong>{parentAmount.toFixed(2)}</strong> ·
          {" "}Remainder: <strong style={{ color: remainderCents === 0 ? "#22c55e" : "#f59e0b" }}>
            {remainder.toFixed(2)}
          </strong>
        </div>

        {error && (
          <p role="alert" style={{ color: "#f87171", fontSize: "0.85rem", marginTop: "0.5rem" }}>{error}</p>
        )}

        <div style={{ marginTop: "1rem", display: "flex", gap: "0.5rem", justifyContent: "flex-end" }}>
          <button onClick={onClose} disabled={busy} style={btn}>Cancel</button>
          <button onClick={submit} disabled={!canSubmit || busy} style={{ ...btn, ...primaryBtn }}>
            {busy ? "Splitting…" : "Split"}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}

const overlay: React.CSSProperties = {
  position: "fixed", inset: 0, background: "rgba(0,0,0,0.55)",
  display: "flex", alignItems: "center", justifyContent: "center",
  zIndex: 100, padding: "1rem",
};
const modal: React.CSSProperties = {
  background: "var(--panel, #0f172a)", border: "1px solid rgba(148,163,184,0.25)",
  borderRadius: "0.6rem", padding: "1.2rem", width: "640px", maxWidth: "100%",
  color: "var(--text, #e2e8f0)",
};
const rowStyle: React.CSSProperties = {
  display: "flex", gap: "0.4rem", marginTop: "0.4rem", alignItems: "center",
};
const inputStyle: React.CSSProperties = {
  padding: "0.4rem 0.55rem",
  background: "rgba(15,23,42,0.6)", border: "1px solid rgba(148,163,184,0.25)",
  borderRadius: "0.4rem", color: "#e2e8f0", fontSize: "0.85rem",
};
const btn: React.CSSProperties = {
  padding: "0.45rem 0.85rem",
  background: "rgba(255,255,255,0.05)", border: "1px solid rgba(148,163,184,0.25)",
  borderRadius: "0.4rem", color: "inherit", cursor: "pointer", fontSize: "0.85rem",
};
const primaryBtn: React.CSSProperties = {
  // F46-fu — was #3b82f6 (white text 3.68:1); the shared fill token is 5.81:1.
  background: "var(--accent-fill)", borderColor: "var(--accent-fill)", color: "white",
};
const delBtn: React.CSSProperties = {
  ...btn, width: "32px", padding: "0.3rem", color: "#94a3b8",
};
