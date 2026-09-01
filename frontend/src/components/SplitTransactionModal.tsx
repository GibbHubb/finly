// F25 — split a transaction into >=2 child rows that sum exactly to the
// parent. v1: simple modal with N rows; live remainder + exact-sum gate.
import { useMemo, useState } from "react";
import type { Transaction, Category } from "@/types";
import { transactionService } from "@/services/transactions";
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

export default function SplitTransactionModal({ tx, onClose, onSplit }: Props) {
  const parentAmount = parseFloat(tx.amount);
  const [rows, setRows] = useState<ChildRow[]>([
    { amount: "", category: tx.category, description: "" },
    { amount: "", category: tx.category, description: "" },
  ]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const childSum = useMemo(
    () => rows.reduce((s, r) => s + (parseFloat(r.amount) || 0), 0),
    [rows],
  );
  const remainder = Math.round((parentAmount - childSum) * 100) / 100;
  const canSubmit =
    rows.length >= 2 &&
    rows.every((r) => parseFloat(r.amount) > 0) &&
    Math.abs(remainder) < 0.005;

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
      await transactionService.split(
        tx.id,
        rows.map((r) => ({
          amount: parseFloat(r.amount).toFixed(2),
          category: r.category,
          description: r.description || undefined,
        })),
      );
      onSplit();
      onClose();
    } catch (err: unknown) {
      setError(apiErrorMessage(err, "Failed to split"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={overlay} onClick={onClose}>
      <div style={modal} onClick={(e) => e.stopPropagation()}>
        <h3 style={{ marginTop: 0 }}>Split transaction</h3>
        <p style={{ color: "var(--muted)", fontSize: "0.85rem", marginTop: 0 }}>
          {tx.description || "(no description)"} — {tx.category} —{" "}
          <strong>{parentAmount.toFixed(2)} {tx.currency}</strong>
        </p>

        {rows.map((r, i) => (
          <div key={i} style={rowStyle}>
            <input
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
          Children sum: <strong>{childSum.toFixed(2)}</strong> ·
          {" "}Parent: <strong>{parentAmount.toFixed(2)}</strong> ·
          {" "}Remainder: <strong style={{ color: Math.abs(remainder) < 0.005 ? "#22c55e" : "#f59e0b" }}>
            {remainder.toFixed(2)}
          </strong>
        </div>

        {error && (
          <p style={{ color: "#f87171", fontSize: "0.85rem", marginTop: "0.5rem" }}>{error}</p>
        )}

        <div style={{ marginTop: "1rem", display: "flex", gap: "0.5rem", justifyContent: "flex-end" }}>
          <button onClick={onClose} disabled={busy} style={btn}>Cancel</button>
          <button onClick={submit} disabled={!canSubmit || busy} style={{ ...btn, ...primaryBtn }}>
            {busy ? "Splitting…" : "Split"}
          </button>
        </div>
      </div>
    </div>
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
  background: "#3b82f6", borderColor: "#3b82f6", color: "white",
};
const delBtn: React.CSSProperties = {
  ...btn, width: "32px", padding: "0.3rem", color: "#94a3b8",
};
