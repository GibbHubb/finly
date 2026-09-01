import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useAuthStore } from "@/store/authStore";
import { transactionService } from "@/services/transactions";
import { StackedCategoryChart } from "@/components/charts/StackedCategoryChart";
import { ChangeTable } from "@/components/trends/ChangeTable";
import type { MonthlyTrendEntry } from "@/types";

export default function TrendsPage() {
  const { user, logout } = useAuthStore();
  const [data, setData] = useState<MonthlyTrendEntry[]>([]);
  const [months, setMonths] = useState<number>(6);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    transactionService
      .trends(months)
      .then((d) => {
        if (!cancelled) setData(d);
      })
      .catch(() => {
        if (!cancelled) setError("Could not load trends — please try again.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [months]);

  return (
    <div className="dashboard">
      <header className="dash-header">
        <h1>💸 Finly</h1>
        <nav className="nav-links">
          <Link to="/dashboard" className="btn-ghost">Dashboard</Link>
          <Link to="/trends" className="btn-ghost" style={{ color: "var(--accent2)" }}>Trends</Link>
          <Link to="/budgets" className="btn-ghost">Budgets</Link>
          <Link to="/rules" className="btn-ghost">Rules</Link>
          <Link to="/savings" className="btn-ghost">Savings</Link>
        </nav>
        <span>Hello, {user?.full_name}</span>
        <button onClick={logout} className="btn-ghost">Sign out</button>
      </header>

      <div className="trends-controls">
        <label>
          Window:{" "}
          <select value={months} onChange={(e) => setMonths(parseInt(e.target.value))}>
            <option value={3}>3 months</option>
            <option value={6}>6 months</option>
            <option value={12}>12 months</option>
          </select>
        </label>
      </div>

      {error && <div className="import-toast error">{error}</div>}

      <div className="chart-card">
        <h3>Expense trends — last {months} months</h3>
        {loading ? (
          <p>Loading…</p>
        ) : data.every((d) => Object.keys(d.categories).length === 0) ? (
          <p style={{ color: "var(--muted)" }}>No expense transactions in this window yet.</p>
        ) : (
          <StackedCategoryChart data={data} />
        )}
      </div>

      <div className="chart-card">
        <h3>Month-over-month change</h3>
        {loading ? <p>Loading…</p> : <ChangeTable data={data} />}
      </div>
    </div>
  );
}
