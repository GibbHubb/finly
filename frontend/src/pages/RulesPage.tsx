import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useAuthStore } from "@/store/authStore";
import { rulesService } from "@/services/rules";
import type { CategorisationRule, CategorisationRuleCreate, Category, MatchType } from "@/types";

const MATCH_TYPES: MatchType[] = ["contains", "equals", "starts_with", "regex"];
const CATEGORIES: Category[] = [
  "housing", "food", "transport", "entertainment",
  "health", "shopping", "salary", "freelance", "other",
];

const EMPTY: CategorisationRuleCreate = {
  match_type: "contains",
  match_value: "",
  category: "other",
  priority: 100,
  enabled: true,
};

export default function RulesPage() {
  const { user, logout } = useAuthStore();
  const [rules, setRules] = useState<CategorisationRule[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState<CategorisationRuleCreate>(EMPTY);
  const [creating, setCreating] = useState(false);
  const [applyResult, setApplyResult] = useState<number | null>(null);

  const load = async () => {
    setLoading(true);
    try {
      setRules(await rulesService.list());
    } catch {
      setError("Could not load rules.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.match_value.trim()) return;
    setCreating(true);
    setError(null);
    try {
      await rulesService.create(form);
      setForm(EMPTY);
      await load();
    } catch (err: unknown) {
      const msg =
        typeof err === "object" && err !== null && "response" in err
          ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
          : null;
      setError(msg ?? "Could not create rule.");
    } finally {
      setCreating(false);
    }
  };

  const toggle = async (r: CategorisationRule) => {
    await rulesService.update(r.id, { enabled: !r.enabled });
    load();
  };

  const setPriority = async (r: CategorisationRule, delta: number) => {
    const next = Math.max(1, r.priority + delta);
    if (next === r.priority) return;
    await rulesService.update(r.id, { priority: next });
    load();
  };

  const remove = async (r: CategorisationRule) => {
    await rulesService.remove(r.id);
    load();
  };

  const applyNow = async () => {
    const res = await rulesService.applyNow();
    setApplyResult(res.updated);
    setTimeout(() => setApplyResult(null), 4000);
  };

  return (
    <div className="dashboard">
      <header className="dash-header">
        <h1>💸 Finly</h1>
        <nav className="nav-links">
          <Link to="/dashboard" className="btn-ghost">Dashboard</Link>
          <Link to="/trends" className="btn-ghost">Trends</Link>
          <Link to="/budgets" className="btn-ghost">Budgets</Link>
          <Link to="/rules" className="btn-ghost" style={{ color: "var(--accent2)" }}>Rules</Link>
          <Link to="/savings" className="btn-ghost">Savings</Link>
        </nav>
        <span>Hello, {user?.full_name}</span>
        <button onClick={logout} className="btn-ghost">Sign out</button>
      </header>

      <h2 style={{ fontFamily: "var(--font-head)", margin: "1.5rem 0 0.5rem" }}>Auto-assign rules</h2>
      <p style={{ color: "var(--muted)", marginBottom: "1rem", fontSize: "0.9rem" }}>
        When a transaction description matches a rule, its category is auto-assigned on import.
        Lower priority number wins. Use the "Apply now" button to run rules against existing
        uncategorised transactions.
      </p>

      {error && <div className="import-toast error">{error}</div>}
      {applyResult !== null && (
        <div className={`import-toast ${applyResult > 0 ? "success" : "neutral"}`}>
          ✓ {applyResult} transaction{applyResult === 1 ? "" : "s"} re-categorised
        </div>
      )}

      <form className="chart-card" onSubmit={handleCreate}>
        <h3>New rule</h3>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: "0.75rem" }}>
          <label style={{ display: "flex", flexDirection: "column", gap: "0.25rem", fontSize: "0.85rem" }}>
            Match type
            <select
              value={form.match_type}
              onChange={(e) => setForm((f) => ({ ...f, match_type: e.target.value as MatchType }))}
              className="tx-filter-input"
            >
              {MATCH_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </label>
          <label style={{ display: "flex", flexDirection: "column", gap: "0.25rem", fontSize: "0.85rem" }}>
            Match value
            <input
              placeholder="e.g. Albert Heijn"
              value={form.match_value}
              onChange={(e) => setForm((f) => ({ ...f, match_value: e.target.value }))}
              className="tx-filter-input"
              required
            />
          </label>
          <label style={{ display: "flex", flexDirection: "column", gap: "0.25rem", fontSize: "0.85rem" }}>
            Category
            <select
              value={form.category}
              onChange={(e) => setForm((f) => ({ ...f, category: e.target.value as Category }))}
              className="tx-filter-input"
            >
              {CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          </label>
          <label style={{ display: "flex", flexDirection: "column", gap: "0.25rem", fontSize: "0.85rem" }}>
            Priority
            <input
              type="number"
              min={1}
              value={form.priority ?? 100}
              onChange={(e) => setForm((f) => ({ ...f, priority: parseInt(e.target.value) || 100 }))}
              className="tx-filter-input"
            />
          </label>
        </div>
        <div style={{ marginTop: "0.75rem", display: "flex", gap: "0.5rem" }}>
          <button type="submit" disabled={creating || !form.match_value.trim()}>
            {creating ? "Saving…" : "Add rule"}
          </button>
          <button type="button" onClick={applyNow} className="btn-ghost">Apply rules to existing</button>
        </div>
      </form>

      <div className="chart-card" style={{ marginTop: "1rem" }}>
        <h3>Rules ({rules.length})</h3>
        {loading ? (
          <p>Loading…</p>
        ) : rules.length === 0 ? (
          <p style={{ color: "var(--muted)" }}>No rules yet — add one above.</p>
        ) : (
          <table className="change-table">
            <thead>
              <tr>
                <th>#</th>
                <th>Type</th>
                <th>Match</th>
                <th>→ Category</th>
                <th>Enabled</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {rules.map((r) => (
                <tr key={r.id} style={{ opacity: r.enabled ? 1 : 0.5 }}>
                  <td style={{ whiteSpace: "nowrap" }}>
                    <button onClick={() => setPriority(r, -1)} className="btn-ghost" title="Higher priority">↑</button>
                    <span style={{ margin: "0 0.25rem" }}>{r.priority}</span>
                    <button onClick={() => setPriority(r, +1)} className="btn-ghost" title="Lower priority">↓</button>
                  </td>
                  <td>{r.match_type}</td>
                  <td style={{ fontFamily: "monospace" }}>{r.match_value}</td>
                  <td style={{ textTransform: "capitalize" }}>{r.category}</td>
                  <td>
                    <button onClick={() => toggle(r)} className="btn-ghost">
                      {r.enabled ? "on" : "off"}
                    </button>
                  </td>
                  <td>
                    <button onClick={() => remove(r)} className="btn-del" title="Delete">✕</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
