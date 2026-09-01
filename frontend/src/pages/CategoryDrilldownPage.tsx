// F26 — category drill-down: every transaction in a category, sorted by
// amount desc, with a text/date filter on top. Reached from the Dashboard
// pie slice (and later from the Trends stacked chart — followup).
//
// Note: the plan §6 also called for extracting DashboardPage's inline
// filter into a shared TransactionFilter component. That refactor is
// flagged risky in §8 (subtle Dashboard regression) and is deferred —
// this page ships with its own minimal filter UI for v1. When F29 lands,
// the extraction can be done deliberately with a regression check.

import { useEffect, useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { transactionService } from "@/services/transactions";
import type { Category, Transaction } from "@/types";
import { formatCurrency, formatDate } from "@/utils/format";

// F-lint1 — the route param is an arbitrary string; validate it against the
// real union instead of casting through `any`, so an unknown /category/<x>
// URL cannot reach the API as a bogus filter.
const CATEGORIES: readonly Category[] = [
  "housing", "food", "transport", "entertainment",
  "health", "shopping", "salary", "freelance", "other",
];

function asCategory(value: string | undefined): Category | undefined {
  return CATEGORIES.find((c) => c === value);
}

export default function CategoryDrilldownPage() {
  const { name } = useParams<{ name: string }>();
  const [searchParams] = useSearchParams();
  const dateFrom = searchParams.get("from") || undefined;
  const dateTo = searchParams.get("to") || undefined;

  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchText, setSearchText] = useState("");
  const [localFrom, setLocalFrom] = useState(dateFrom || "");
  const [localTo, setLocalTo] = useState(dateTo || "");

  useEffect(() => {
    if (!name) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    transactionService
      .list({
        category: asCategory(name),
        date_from: localFrom || undefined,
        date_to: localTo || undefined,
        limit: 500,
      })
      .then((rows) => {
        if (!cancelled) setTransactions(rows);
      })
      .catch((err) => {
        if (!cancelled) setError(err?.message || "Failed to load transactions");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [name, localFrom, localTo]);

  // Sorted by amount desc; client-side text filter for in-page narrowing.
  const filtered = useMemo(() => {
    const needle = searchText.trim().toLowerCase();
    const list = needle
      ? transactions.filter((t) => t.description.toLowerCase().includes(needle))
      : transactions;
    return [...list].sort((a, b) => parseFloat(b.amount) - parseFloat(a.amount));
  }, [transactions, searchText]);

  const total = filtered.reduce((s, t) => s + parseFloat(t.amount), 0);

  return (
    <div className="container" style={{ maxWidth: "900px", margin: "0 auto", padding: "1.5rem" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "0.6rem" }}>
        <h2 style={{ margin: 0 }}>
          {name?.charAt(0).toUpperCase()}{name?.slice(1)} — transactions
        </h2>
        <Link to="/dashboard" style={{ fontSize: "0.85rem", color: "var(--muted)" }}>← Back to Dashboard</Link>
      </div>

      <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", marginBottom: "1rem" }}>
        <input
          type="text"
          placeholder="Search description…"
          value={searchText}
          onChange={(e) => setSearchText(e.target.value)}
          style={inputStyle}
        />
        <input
          type="date"
          value={localFrom}
          onChange={(e) => setLocalFrom(e.target.value)}
          style={inputStyle}
          aria-label="From date"
        />
        <input
          type="date"
          value={localTo}
          onChange={(e) => setLocalTo(e.target.value)}
          style={inputStyle}
          aria-label="To date"
        />
        <span style={{ marginLeft: "auto", color: "var(--muted)", alignSelf: "center", fontSize: "0.9rem" }}>
          {filtered.length} txs · {formatCurrency(total)}
        </span>
      </div>

      {loading && <p style={{ color: "var(--muted)" }}>Loading…</p>}
      {error && <p style={{ color: "#f87171" }}>{error}</p>}
      {!loading && !error && filtered.length === 0 && (
        <p style={{ color: "var(--muted)" }}>
          No transactions in <strong>{name}</strong>
          {(localFrom || localTo) ? " for this date range" : ""}.
        </p>
      )}

      <div>
        {filtered.map((tx) => (
          <div key={tx.id} className={`tx-row ${tx.type}`}>
            <div>
              <span className="tx-desc">{tx.description || "(no description)"}</span>
              <span className="tx-date">{formatDate(tx.transaction_date)}</span>
            </div>
            <div className="tx-right">
              <span className="tx-amount">
                {tx.type === "expense" ? "-" : "+"}{formatCurrency(parseFloat(tx.amount))}
                {tx.currency && <span className="tx-currency"> {tx.currency}</span>}
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

const inputStyle: React.CSSProperties = {
  padding: "0.4rem 0.6rem",
  background: "rgba(15,23,42,0.6)",
  border: "1px solid rgba(148,163,184,0.25)",
  borderRadius: "0.4rem",
  color: "#e2e8f0",
  fontSize: "0.85rem",
};
