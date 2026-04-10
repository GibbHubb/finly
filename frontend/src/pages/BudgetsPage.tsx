import { useState } from "react";
import { Link } from "react-router-dom";
import { useBudgets } from "@/hooks/useBudgets";
import { useTransactions } from "@/hooks/useTransactions";
import { formatCurrency } from "@/utils/format";
import type { BudgetCreate, Category } from "@/types";
import { useBudgetStore } from "@/store/budgetStore";

const EXPENSE_CATEGORIES: Category[] = [
  "housing", "food", "transport", "entertainment", "health", "shopping", "other",
];

export default function BudgetsPage() {
  const now = new Date();
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [year, setYear] = useState(now.getFullYear());

  const { budgets, isLoading } = useBudgets(month, year);
  const { add, remove } = useBudgetStore();
  const { transactions } = useTransactions();

  const [form, setForm] = useState<BudgetCreate>({
    category: "food",
    limit_amount: 0,
    month,
    year,
  });
  const [formError, setFormError] = useState("");

  // Compute spending per category for the selected month/year
  const spendByCategory = (cat: Category): number =>
    transactions
      .filter((t) =>
        t.type === "expense" &&
        t.category === cat &&
        t.transaction_date.startsWith(`${year}-${String(month).padStart(2, "0")}`)
      )
      .reduce((sum, t) => sum + parseFloat(t.amount), 0);

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError("");
    if (form.limit_amount <= 0) { setFormError("Amount must be greater than 0"); return; }
    try {
      await add({ ...form, month, year });
      setForm((f) => ({ ...f, limit_amount: 0 }));
    } catch {
      setFormError("Budget for this category/month already exists.");
    }
  };

  const categoriesWithBudget = budgets.map((b) => {
    const spent = spendByCategory(b.category as Category);
    const limit = parseFloat(b.limit_amount);
    const pct = limit > 0 ? Math.min((spent / limit) * 100, 100) : 0;
    const over = spent > limit;
    return { ...b, spent, limit, pct, over };
  });

  const MONTH_NAMES = [
    "January","February","March","April","May","June",
    "July","August","September","October","November","December",
  ];

  return (
    <div className="dashboard">
      <header className="dash-header">
        <h1>💸 Finly</h1>
        <nav style={{ display: "flex", gap: "1rem" }}>
          <Link to="/dashboard" className="btn-ghost">Dashboard</Link>
          <Link to="/budgets" className="btn-ghost" style={{ color: "var(--accent2)" }}>Budgets</Link>
        </nav>
      </header>

      <h2 style={{ fontFamily: "var(--font-head)", margin: "1.5rem 0 1rem" }}>Budgets</h2>

      {/* Month/year selector */}
      <div style={{ display: "flex", gap: "0.75rem", marginBottom: "1.5rem", alignItems: "center" }}>
        <select
          value={month}
          onChange={(e) => setMonth(Number(e.target.value))}
          style={selectStyle}
        >
          {MONTH_NAMES.map((m, i) => (
            <option key={m} value={i + 1}>{m}</option>
          ))}
        </select>
        <select
          value={year}
          onChange={(e) => setYear(Number(e.target.value))}
          style={selectStyle}
        >
          {[2024, 2025, 2026, 2027].map((y) => (
            <option key={y} value={y}>{y}</option>
          ))}
        </select>
      </div>

      {/* Budget progress cards */}
      {isLoading ? (
        <p style={{ color: "var(--muted)" }}>Loading…</p>
      ) : categoriesWithBudget.length === 0 ? (
        <p style={{ color: "var(--muted)", marginBottom: "1.5rem" }}>
          No budgets set for {MONTH_NAMES[month - 1]} {year}. Add one below.
        </p>
      ) : (
        <div style={{ display: "grid", gap: "1rem", marginBottom: "2rem" }}>
          {categoriesWithBudget.map((b) => (
            <div key={b.id} style={cardStyle}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: "0.5rem" }}>
                <span style={{ textTransform: "capitalize", fontWeight: 600 }}>{b.category}</span>
                <span style={{ color: b.over ? "var(--expense)" : "var(--muted)", fontSize: "0.85rem" }}>
                  {formatCurrency(b.spent)} / {formatCurrency(b.limit)}
                  {b.over && " ⚠ over budget"}
                </span>
              </div>
              <div style={trackStyle}>
                <div
                  style={{
                    ...barStyle,
                    width: `${b.pct}%`,
                    background: b.over
                      ? "var(--expense)"
                      : b.pct > 80
                      ? "#f59e0b"
                      : "var(--accent)",
                  }}
                />
              </div>
              <div style={{ display: "flex", justifyContent: "space-between", marginTop: "0.4rem", fontSize: "0.8rem", color: "var(--muted)" }}>
                <span>{Math.round(b.pct)}% used</span>
                <span>
                  {b.over
                    ? `${formatCurrency(b.spent - b.limit)} over`
                    : `${formatCurrency(b.limit - b.spent)} left`}
                </span>
              </div>
              <button
                onClick={() => remove(b.id)}
                className="btn-del"
                style={{ marginTop: "0.6rem", fontSize: "0.75rem" }}
              >
                Remove
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Add budget form */}
      <div style={cardStyle}>
        <h3 style={{ marginBottom: "1rem", fontFamily: "var(--font-head)" }}>Set a budget</h3>
        <form onSubmit={handleAdd} style={{ display: "flex", flexWrap: "wrap", gap: "0.75rem", alignItems: "flex-end" }}>
          <label style={labelStyle}>
            Category
            <select
              value={form.category}
              onChange={(e) => setForm((f) => ({ ...f, category: e.target.value as Category }))}
              style={selectStyle}
            >
              {EXPENSE_CATEGORIES.map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
          </label>
          <label style={labelStyle}>
            Limit (€)
            <input
              type="number"
              min="0.01"
              step="0.01"
              value={form.limit_amount || ""}
              onChange={(e) => setForm((f) => ({ ...f, limit_amount: parseFloat(e.target.value) }))}
              style={inputStyle}
              placeholder="0.00"
            />
          </label>
          <button type="submit" style={btnStyle}>Add budget</button>
        </form>
        {formError && <p style={{ color: "var(--expense)", marginTop: "0.5rem", fontSize: "0.85rem" }}>{formError}</p>}
      </div>
    </div>
  );
}

const cardStyle: React.CSSProperties = {
  background: "var(--surface)",
  border: "1px solid var(--border)",
  borderRadius: "var(--radius)",
  padding: "1.25rem 1.5rem",
};

const trackStyle: React.CSSProperties = {
  height: "8px",
  background: "var(--surface2)",
  borderRadius: "99px",
  overflow: "hidden",
};

const barStyle: React.CSSProperties = {
  height: "100%",
  borderRadius: "99px",
  transition: "width 0.4s ease",
};

const selectStyle: React.CSSProperties = {
  background: "var(--surface2)",
  border: "1px solid var(--border)",
  color: "var(--text)",
  borderRadius: "8px",
  padding: "0.4rem 0.6rem",
  fontSize: "0.9rem",
  cursor: "pointer",
};

const inputStyle: React.CSSProperties = {
  background: "var(--surface2)",
  border: "1px solid var(--border)",
  color: "var(--text)",
  borderRadius: "8px",
  padding: "0.4rem 0.6rem",
  fontSize: "0.9rem",
  width: "120px",
};

const labelStyle: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: "0.3rem",
  fontSize: "0.8rem",
  color: "var(--muted)",
  textTransform: "capitalize",
};

const btnStyle: React.CSSProperties = {
  background: "var(--accent)",
  color: "#fff",
  border: "none",
  borderRadius: "8px",
  padding: "0.5rem 1.2rem",
  cursor: "pointer",
  fontWeight: 600,
  fontSize: "0.9rem",
};
