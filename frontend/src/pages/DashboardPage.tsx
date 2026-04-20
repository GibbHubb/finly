import { useCallback, useEffect, useRef, useState } from "react";
import { useAuthStore } from "@/store/authStore";
import { useTransactions } from "@/hooks/useTransactions";
import { useTransactionStore } from "@/store/transactionStore";
import { useTransactionSocket } from "@/hooks/useTransactionSocket";
import type { TransactionCreate, Category, ImportResult, BudgetAlert } from "@/types";
import { formatCurrency, formatDate } from "@/utils/format";

const CURRENCIES = ["EUR", "USD", "GBP", "SEK", "NOK", "DKK"];
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, PieChart, Pie, Cell, Legend,
} from "recharts";

const CATEGORIES: Category[] = ["housing","food","transport","entertainment","health","shopping","salary","freelance","other"];
const COLORS = ["#6366f1","#22c55e","#f59e0b","#ec4899","#14b8a6","#8b5cf6","#f97316","#06b6d4","#84cc16"];

const CONFIDENCE_COLOR: Record<string, string> = {
  high: "#22c55e",
  medium: "#f59e0b",
  low: "#94a3b8",
};

export default function DashboardPage() {
  const { user, logout, baseCurrency, setBaseCurrency } = useAuthStore();
  const { transactions, totalIncome, totalExpense, balance, isLoading } = useTransactions();
  const { add, remove, fetchForecast, forecast, forecastLoading, importCsv, fetchRecurring, recurring, recurringLoading } = useTransactionStore();

  // Budget alert toasts
  const [budgetAlerts, setBudgetAlerts] = useState<BudgetAlert[]>([]);
  const handleBudgetAlert = useCallback((alert: BudgetAlert) => {
    setBudgetAlerts((prev) => [...prev, alert]);
    setTimeout(() => {
      setBudgetAlerts((prev) => prev.filter((a) => a !== alert));
    }, 5000);
  }, []);
  useTransactionSocket(handleBudgetAlert);

  const now = new Date();
  const [form, setForm] = useState<TransactionCreate>({
    amount: 0, type: "expense", category: "food", description: "", transaction_date: now.toISOString().slice(0, 10), currency: baseCurrency,
  });

  const [importToast, setImportToast] = useState<ImportResult | null>(null);
  const [importError, setImportError] = useState<string | null>(null);
  const [importing, setImporting] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Fetch forecast + recurring on mount
  useEffect(() => {
    fetchForecast(now.getMonth() + 1, now.getFullYear());
    fetchRecurring();
  }, []);

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault();
    await add(form);
    setForm((f) => ({ ...f, amount: 0, description: "" }));
    // Refresh forecast after adding a transaction
    fetchForecast(now.getMonth() + 1, now.getFullYear());
  };

  const handleImport = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setImporting(true);
    setImportToast(null);
    setImportError(null);
    try {
      const result = await importCsv(file);
      setImportToast(result);
      if (result.imported > 0) {
        fetchForecast(now.getMonth() + 1, now.getFullYear());
      }
    } catch {
      setImportError("Import failed — check the file format (ING or ABN AMRO CSV).");
    } finally {
      setImporting(false);
      // Reset so the same file can be re-selected
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  // Chart data
  const expenseByCategory = CATEGORIES.map((cat, i) => ({
    name: cat,
    amount: transactions.filter((t) => t.type === "expense" && t.category === cat).reduce((s, t) => s + parseFloat(t.amount), 0),
    fill: COLORS[i],
  })).filter((d) => d.amount > 0);

  const monthlyData = Array.from({ length: 6 }, (_, i) => {
    const d = new Date();
    d.setMonth(d.getMonth() - (5 - i));
    const m = d.toISOString().slice(0, 7);
    const monthTx = transactions.filter((t) => t.transaction_date.startsWith(m));
    return {
      month: d.toLocaleString("default", { month: "short" }),
      income: monthTx.filter((t) => t.type === "income").reduce((s, t) => s + parseFloat(t.amount), 0),
      expense: monthTx.filter((t) => t.type === "expense").reduce((s, t) => s + parseFloat(t.amount), 0),
    };
  });

  return (
    <div className="dashboard">
      <header className="dash-header">
        <h1>💸 Finly</h1>
        <span>Hello, {user?.full_name}</span>
        <select
          className="currency-select"
          value={baseCurrency}
          onChange={(e) => setBaseCurrency(e.target.value)}
          title="Display currency"
        >
          {CURRENCIES.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
        <button onClick={logout} className="btn-ghost">Sign out</button>
      </header>

      <div className="stats">
        <div className="stat-card income">
          <p>Income</p>
          <h2>{formatCurrency(totalIncome)}</h2>
        </div>
        <div className="stat-card expense">
          <p>Expenses</p>
          <h2>{formatCurrency(totalExpense)}</h2>
        </div>
        <div className={`stat-card ${balance >= 0 ? "positive" : "negative"}`}>
          <p>Balance</p>
          <h2>{formatCurrency(balance)}</h2>
        </div>

        {/* Forecast card */}
        <div className="stat-card forecast">
          <p>Projected spend</p>
          {forecastLoading ? (
            <h2 className="forecast-loading">…</h2>
          ) : forecast?.projected_total ? (
            <>
              <h2>{formatCurrency(parseFloat(forecast.projected_total))}</h2>
              <span
                className="forecast-confidence"
                style={{ color: CONFIDENCE_COLOR[forecast.confidence] }}
              >
                {forecast.confidence} confidence · {forecast.data_points_used} data points
              </span>
            </>
          ) : (
            <span className="forecast-na">Not enough data yet</span>
          )}
        </div>
      </div>

      <div className="charts">
        <div className="chart-card">
          <h3>6-Month Overview</h3>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={monthlyData}>
              <XAxis dataKey="month" />
              <YAxis tickFormatter={(v: number) => formatCurrency(v)} />
              <Tooltip formatter={(v: number) => formatCurrency(v)} />
              <Bar dataKey="income" fill="#22c55e" radius={[4,4,0,0]} />
              <Bar dataKey="expense" fill="#f43f5e" radius={[4,4,0,0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="chart-card">
          <h3>Spending by Category</h3>
          <ResponsiveContainer width="100%" height={220}>
            <PieChart>
              <Pie data={expenseByCategory} dataKey="amount" nameKey="name" cx="50%" cy="50%" innerRadius={50} outerRadius={80} paddingAngle={2}>
                {expenseByCategory.map((e, i) => <Cell key={i} fill={e.fill} />)}
              </Pie>
              <Tooltip formatter={(v: number) => formatCurrency(v)} />
              <Legend />
            </PieChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Subscriptions / recurring spend */}
      <div className="subscriptions-card">
        <h3>Subscriptions</h3>
        {recurringLoading ? (
          <p className="sub-empty">Loading…</p>
        ) : recurring.length === 0 ? (
          <p className="sub-empty">No subscriptions detected</p>
        ) : (
          <>
            <p className="sub-total">~{formatCurrency(recurring.reduce((s, r) => s + r.monthly_amount, 0))}/mo</p>
            <div className="sub-list">
              {recurring.map((r) => (
                <div key={r.merchant} className="sub-row">
                  <span className="sub-merchant">{r.merchant}</span>
                  <span className="sub-amount">{formatCurrency(r.monthly_amount)}/mo</span>
                  <span className="sub-meta">{r.months_detected} months · day ~{r.typical_day}</span>
                </div>
              ))}
            </div>
          </>
        )}
      </div>

      <div className="main-grid">
        <form className="add-form" onSubmit={handleAdd}>
          <h3>Add Transaction</h3>
          <select value={form.type} onChange={(e) => setForm((f) => ({ ...f, type: e.target.value as "income" | "expense" }))}>
            <option value="expense">Expense</option>
            <option value="income">Income</option>
          </select>
          <input type="number" min="0.01" step="0.01" placeholder="Amount (€)" value={form.amount || ""} onChange={(e) => setForm((f) => ({ ...f, amount: parseFloat(e.target.value) }))} required />
          <select value={form.category} onChange={(e) => setForm((f) => ({ ...f, category: e.target.value as Category }))}>
            {CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
          <input placeholder="Description (optional)" value={form.description} onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))} />
          <input type="date" value={form.transaction_date} onChange={(e) => setForm((f) => ({ ...f, transaction_date: e.target.value }))} required />
          <button type="submit">Add</button>

          {/* Import CSV */}
          <div className="import-section">
            <input
              ref={fileInputRef}
              type="file"
              accept=".csv"
              style={{ display: "none" }}
              onChange={handleImport}
            />
            <button
              type="button"
              className="btn-import"
              disabled={importing}
              onClick={() => fileInputRef.current?.click()}
            >
              {importing ? "Importing…" : "Import CSV"}
            </button>
            <span className="import-hint">ING or ABN AMRO export</span>
          </div>

          {importToast && (
            <div className={`import-toast ${importToast.imported > 0 ? "success" : "neutral"}`}>
              ✓ {importToast.imported} imported · {importToast.skipped_duplicates} duplicates skipped
              {importToast.errors.length > 0 && (
                <span className="import-errors"> · {importToast.errors.length} row error(s)</span>
              )}
            </div>
          )}
          {importError && <div className="import-toast error">{importError}</div>}
        </form>

        <div className="tx-list">
          <h3>Recent Transactions</h3>
          {isLoading && <p>Loading…</p>}
          {transactions.slice(0, 30).map((tx) => (
            <div key={tx.id} className={`tx-row ${tx.type}`}>
              <div>
                <span className="tx-cat">{tx.category}</span>
                <span className="tx-desc">{tx.description}</span>
                <span className="tx-date">{formatDate(tx.transaction_date)}</span>
              </div>
              <div className="tx-right">
                <span className="tx-amount" title={tx.currency !== baseCurrency ? `${tx.currency} original` : undefined}>
                  {tx.type === "expense" ? "-" : "+"}{formatCurrency(parseFloat(tx.amount))}
                  {tx.currency && tx.currency !== baseCurrency && (
                    <span className="tx-currency">{tx.currency}</span>
                  )}
                </span>
                <button onClick={() => remove(tx.id)} className="btn-del">✕</button>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Budget alert toasts */}
      {budgetAlerts.length > 0 && (
        <div className="budget-toast-stack">
          {budgetAlerts.map((a, i) => (
            <div key={i} className="budget-toast">
              <span>{a.category} over budget — {formatCurrency(parseFloat(a.spent))} of {formatCurrency(parseFloat(a.limit))} limit</span>
              <button onClick={() => setBudgetAlerts((prev) => prev.filter((_, j) => j !== i))}>✕</button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
