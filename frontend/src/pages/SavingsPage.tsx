import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useSavingsStore } from "@/store/savingsStore";
import { formatCurrency } from "@/utils/format";
import type { SavingsGoalCreate } from "@/types";

export default function SavingsPage() {
  const { goals, isLoading, fetch, add, update, remove } = useSavingsStore();
  const [form, setForm] = useState<SavingsGoalCreate>({ name: "", target_amount: 0, deadline: "" });
  const [formError, setFormError] = useState("");
  const [addAmountInputs, setAddAmountInputs] = useState<Record<number, string>>({});

  useEffect(() => {
    fetch();
  }, [fetch]);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError("");
    if (!form.name.trim()) { setFormError("Name is required"); return; }
    if (form.target_amount <= 0) { setFormError("Target must be greater than 0"); return; }
    try {
      await add({ ...form, deadline: form.deadline || undefined });
      setForm({ name: "", target_amount: 0, deadline: "" });
    } catch {
      setFormError("Failed to create goal");
    }
  };

  const handleAddFunds = async (goalId: number, currentAmount: string, delta: number) => {
    const newAmount = Math.max(0, parseFloat(currentAmount) + delta);
    await update(goalId, { current_amount: newAmount });
    setAddAmountInputs((prev) => ({ ...prev, [goalId]: "" }));
  };

  const handleDelete = async (id: number, name: string) => {
    if (!confirm(`Delete savings goal "${name}"?`)) return;
    await remove(id);
  };

  return (
    <div className="dashboard">
      <header className="dash-header">
        <h1>💸 Finly</h1>
        <nav style={{ display: "flex", gap: "1rem" }}>
          <Link to="/dashboard" className="btn-ghost">Dashboard</Link>
          <Link to="/budgets" className="btn-ghost">Budgets</Link>
          <Link to="/savings" className="btn-ghost" style={{ color: "var(--accent2)" }}>Savings</Link>
        </nav>
      </header>

      <h2 style={{ fontFamily: "var(--font-head)", margin: "1.5rem 0 1rem" }}>Savings Goals</h2>

      {isLoading ? (
        <p style={{ color: "var(--muted)" }}>Loading…</p>
      ) : goals.length === 0 ? (
        <p style={{ color: "var(--muted)", marginBottom: "1.5rem" }}>
          No savings goals yet. Create one below to start tracking.
        </p>
      ) : (
        <div style={{ display: "grid", gap: "1rem", marginBottom: "2rem" }}>
          {goals.map((g) => {
            const current = parseFloat(g.current_amount);
            const target = parseFloat(g.target_amount);
            const isComplete = g.progress_pct >= 100;
            const bgColor = isComplete
              ? "linear-gradient(90deg, #22c55e, #16a34a)"
              : g.progress_pct > 60
              ? "linear-gradient(90deg, #6366f1, #818cf8)"
              : "var(--accent)";
            const deadlineDate = g.deadline ? new Date(g.deadline) : null;
            const isOverdue = deadlineDate && deadlineDate < new Date() && !isComplete;

            return (
              <div key={g.id} style={cardStyle}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: "0.5rem" }}>
                  <span style={{ fontWeight: 600, fontSize: "1.05rem" }}>
                    {g.name}
                    {isComplete && " 🎉"}
                  </span>
                  <span style={{ color: "var(--muted)", fontSize: "0.85rem" }}>
                    {formatCurrency(current)} / {formatCurrency(target)}
                  </span>
                </div>
                <div style={trackStyle}>
                  <div style={{ ...barStyle, width: `${g.progress_pct}%`, background: bgColor }} />
                </div>
                <div style={{ display: "flex", justifyContent: "space-between", marginTop: "0.4rem", fontSize: "0.8rem", color: "var(--muted)" }}>
                  <span>{Math.round(g.progress_pct)}% funded</span>
                  {g.deadline && (
                    <span style={{ color: isOverdue ? "var(--expense)" : "var(--muted)" }}>
                      {isOverdue ? "Overdue: " : "Deadline: "}{new Date(g.deadline).toLocaleDateString()}
                    </span>
                  )}
                </div>

                <div style={{ display: "flex", gap: "0.5rem", marginTop: "0.75rem", alignItems: "center" }}>
                  <input
                    type="number"
                    step="0.01"
                    placeholder="Amount"
                    value={addAmountInputs[g.id] ?? ""}
                    onChange={(e) => setAddAmountInputs((prev) => ({ ...prev, [g.id]: e.target.value }))}
                    style={{ ...inputStyle, width: "110px" }}
                  />
                  <button
                    onClick={() => {
                      const amt = parseFloat(addAmountInputs[g.id] ?? "");
                      if (isFinite(amt) && amt > 0) handleAddFunds(g.id, g.current_amount, amt);
                    }}
                    style={{ ...btnStyle, padding: "0.4rem 0.9rem", fontSize: "0.8rem" }}
                  >
                    + Add
                  </button>
                  <button
                    onClick={() => {
                      const amt = parseFloat(addAmountInputs[g.id] ?? "");
                      if (isFinite(amt) && amt > 0) handleAddFunds(g.id, g.current_amount, -amt);
                    }}
                    style={{ ...btnStyle, padding: "0.4rem 0.9rem", fontSize: "0.8rem", background: "var(--surface2)" }}
                  >
                    − Withdraw
                  </button>
                  <button
                    onClick={() => handleDelete(g.id, g.name)}
                    className="btn-del"
                    style={{ marginLeft: "auto", fontSize: "0.75rem" }}
                  >
                    Remove
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      <div style={cardStyle}>
        <h3 style={{ marginBottom: "1rem", fontFamily: "var(--font-head)" }}>New savings goal</h3>
        <form onSubmit={handleCreate} style={{ display: "flex", flexWrap: "wrap", gap: "0.75rem", alignItems: "flex-end" }}>
          <label style={labelStyle}>
            Name
            <input
              type="text"
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              style={{ ...inputStyle, width: "200px" }}
              placeholder="Holiday fund"
            />
          </label>
          <label style={labelStyle}>
            Target (€)
            <input
              type="number"
              min="0.01"
              step="0.01"
              value={form.target_amount || ""}
              onChange={(e) => setForm((f) => ({ ...f, target_amount: parseFloat(e.target.value) }))}
              style={inputStyle}
              placeholder="1500.00"
            />
          </label>
          <label style={labelStyle}>
            Deadline
            <input
              type="date"
              value={form.deadline || ""}
              onChange={(e) => setForm((f) => ({ ...f, deadline: e.target.value }))}
              style={inputStyle}
            />
          </label>
          <button type="submit" style={btnStyle}>Create goal</button>
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
  height: "10px",
  background: "var(--surface2)",
  borderRadius: "99px",
  overflow: "hidden",
};
const barStyle: React.CSSProperties = {
  height: "100%",
  borderRadius: "99px",
  transition: "width 0.4s ease",
};
const inputStyle: React.CSSProperties = {
  background: "var(--surface2)",
  border: "1px solid var(--border)",
  color: "var(--text)",
  borderRadius: "8px",
  padding: "0.4rem 0.6rem",
  fontSize: "0.9rem",
  width: "140px",
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
