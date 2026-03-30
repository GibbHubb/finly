import { useState } from "react";
import { useAuthStore } from "@/store/authStore";
import { useTransactions } from "@/hooks/useTransactions";
import { useTransactionStore } from "@/store/transactionStore";
import type { TransactionCreate, Category } from "@/types";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, PieChart, Pie, Cell, Legend,
} from "recharts";

const CATEGORIES: Category[] = ["housing","food","transport","entertainment","health","shopping","salary","freelance","other"];
const COLORS = ["#6366f1","#22c55e","#f59e0b","#ec4899","#14b8a6","#8b5cf6","#f97316","#06b6d4","#84cc16"];

export default function DashboardPage() {
  const { user, logout } = useAuthStore();
  const { transactions, totalIncome, totalExpense, balance, isLoading } = useTransactions();
  const { add, remove } = useTransactionStore();

  const [form, setForm] = useState<TransactionCreate>({
    amount: 0, type: "expense", category: "food", description: "", transaction_date: new Date().toISOString().slice(0, 10),
  });

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault();
    await add(form);
    setForm((f) => ({ ...f, amount: 0, description: "" }));
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
        <button onClick={logout} className="btn-ghost">Sign out</button>
      </header>

      <div className="stats">
        <div className="stat-card income">
          <p>Income</p>
          <h2>€{totalIncome.toFixed(2)}</h2>
        </div>
        <div className="stat-card expense">
          <p>Expenses</p>
          <h2>€{totalExpense.toFixed(2)}</h2>
        </div>
        <div className={`stat-card ${balance >= 0 ? "positive" : "negative"}`}>
          <p>Balance</p>
          <h2>€{balance.toFixed(2)}</h2>
        </div>
      </div>

      <div className="charts">
        <div className="chart-card">
          <h3>6-Month Overview</h3>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={monthlyData}>
              <XAxis dataKey="month" />
              <YAxis />
              <Tooltip formatter={(v: number) => `€${v.toFixed(2)}`} />
              <Bar dataKey="income" fill="#22c55e" radius={[4,4,0,0]} />
              <Bar dataKey="expense" fill="#f43f5e" radius={[4,4,0,0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="chart-card">
          <h3>Spending by Category</h3>
          <ResponsiveContainer width="100%" height={220}>
            <PieChart>
              <Pie data={expenseByCategory} dataKey="amount" nameKey="name" cx="50%" cy="50%" outerRadius={80}>
                {expenseByCategory.map((e, i) => <Cell key={i} fill={e.fill} />)}
              </Pie>
              <Tooltip formatter={(v: number) => `€${v.toFixed(2)}`} />
              <Legend />
            </PieChart>
          </ResponsiveContainer>
        </div>
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
        </form>

        <div className="tx-list">
          <h3>Recent Transactions</h3>
          {isLoading && <p>Loading…</p>}
          {transactions.slice(0, 30).map((tx) => (
            <div key={tx.id} className={`tx-row ${tx.type}`}>
              <div>
                <span className="tx-cat">{tx.category}</span>
                <span className="tx-desc">{tx.description}</span>
                <span className="tx-date">{tx.transaction_date}</span>
              </div>
              <div className="tx-right">
                <span className="tx-amount">{tx.type === "expense" ? "-" : "+"}€{parseFloat(tx.amount).toFixed(2)}</span>
                <button onClick={() => remove(tx.id)} className="btn-del">✕</button>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
