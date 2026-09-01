import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuthStore } from "@/store/authStore";
import { useTransactions } from "@/hooks/useTransactions";
import { useTransactionStore } from "@/store/transactionStore";
import { useTransactionPolling } from "@/hooks/useTransactionPolling";
import type { TransactionCreate, Category, ImportResult, Transaction } from "@/types";
import { formatCurrency, formatDate } from "@/utils/format";
import { apiErrorMessage } from "@/utils/errors";
import SplitTransactionModal from "@/components/SplitTransactionModal";
import RecurringReview from "@/components/RecurringReview";
import { bankService, downloadYearReview, tagService, transactionService, type BankStatus, type TagBrief } from "@/services/transactions";
import TransactionFilter from "@/components/ui/TransactionFilter";

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
  const { add, remove, fetch: refetchTransactions, fetchForecast, forecast, forecastLoading, importCsv, fetchRecurring, recurring, recurringLoading } = useTransactionStore();
  const [splitTx, setSplitTx] = useState<Transaction | null>(null);  // F25
  const navigate = useNavigate();  // F26 — drill-down from pie slice
  const [banks, setBanks] = useState<BankStatus[]>([]);  // F27
  const [bankBusy, setBankBusy] = useState(false);  // F27
  const [bankMsg, setBankMsg] = useState<string | null>(null);  // F27

  // F27 — load bank-connection status on mount
  useEffect(() => {
    bankService.status().then(setBanks).catch(() => setBanks([]));
  }, []);

  const handleConnectBank = async () => {
    setBankBusy(true);
    setBankMsg(null);
    try {
      const r = await bankService.connect();
      // Open the GoCardless hosted consent screen; user returns to /bank/callback
      window.open(r.link, "_blank", "noopener");
      setBankMsg("Consent screen opened — complete it and return here.");
    } catch (err: unknown) {
      setBankMsg(apiErrorMessage(err, "Bank connect failed (check GOCARDLESS_* env vars)"));
    } finally {
      setBankBusy(false);
    }
  };

  const handleBankSync = async () => {
    setBankBusy(true);
    setBankMsg(null);
    try {
      const r = await bankService.syncNow();
      const totals = r.results.reduce(
        (acc, x) => ({ ins: acc.ins + x.inserted, skip: acc.skip + x.skipped }),
        { ins: 0, skip: 0 },
      );
      setBankMsg(`Synced ${r.connections} connection(s): +${totals.ins} new, ${totals.skip} skipped`);
      bankService.status().then(setBanks).catch(() => undefined);
      refetchTransactions();
    } catch (err: unknown) {
      setBankMsg(apiErrorMessage(err, "Sync failed"));
    } finally {
      setBankBusy(false);
    }
  };

  // F34 — the budget-alert toast stack was here, fed exclusively by the
  // WebSocket's `budget_alert` frame. With the socket gone there is no producer
  // for it, so the state, the callback and the toast markup are removed rather
  // than left as UI that can never appear. Restoring alerts needs a "what
  // changed since I last asked" endpoint to poll — filed as F35. The budget
  // bars below still show which categories are over.
  // F34 — polling replaces the WebSocket, which cannot exist on serverless and
  // had been dialling ws://localhost:8000 from the deployed SPA anyway.
  // ⚠️ It does NOT deliver budget alerts: the socket pushed those and polling
  // has nothing to poll for them (F35). `handleBudgetAlert` and the toast it
  // feeds are kept, unwired, because the budget bars below still render the
  // same state and the toast returns with F35.
  useTransactionPolling();

  const now = new Date();
  const [form, setForm] = useState<TransactionCreate>({
    amount: 0, type: "expense", category: "food", description: "", transaction_date: now.toISOString().slice(0, 10), currency: baseCurrency,
  });

  const [importToast, setImportToast] = useState<ImportResult | null>(null);
  const [importError, setImportError] = useState<string | null>(null);
  const [importing, setImporting] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // F8 — transaction filter state
  const [filterText, setFilterText] = useState("");
  const [filterCategory, setFilterCategory] = useState<Category | "all">("all");
  const [filterDateFrom, setFilterDateFrom] = useState("");
  const [filterDateTo, setFilterDateTo] = useState("");
  const [filterAmountMin, setFilterAmountMin] = useState("");
  const [filterAmountMax, setFilterAmountMax] = useState("");

  // F30 — tag filter state (kept here; TransactionFilter is purely presentational)
  const [availableTags, setAvailableTags] = useState<TagBrief[]>([]);
  const [selectedTags, setSelectedTags] = useState<string[]>([]);
  // Separate working list for tag-filtered results so chart source arrays are unaffected
  const [tagFilteredList, setTagFilteredList] = useState<Transaction[] | null>(null);

  const hasActiveFilters = !!(filterText || filterCategory !== "all" || filterDateFrom || filterDateTo || filterAmountMin || filterAmountMax || selectedTags.length > 0);

  const clearFilters = () => {
    setFilterText(""); setFilterCategory("all"); setFilterDateFrom(""); setFilterDateTo(""); setFilterAmountMin(""); setFilterAmountMax("");
    setSelectedTags([]);
    setTagFilteredList(null);
  };

  const handleToggleTag = (name: string) => {
    setSelectedTags((prev) =>
      prev.includes(name) ? prev.filter((t) => t !== name) : [...prev, name]
    );
  };

  // Fetch forecast + recurring on mount.
  // F-lint1 — `now` was a render-scoped `new Date()`, so listing it as a dep
  // would refire every render. Reading the date inside the effect drops it
  // from the dep set entirely; the two store actions are stable zustand
  // references, so this stays mount-only as intended.
  useEffect(() => {
    const d = new Date();
    fetchForecast(d.getMonth() + 1, d.getFullYear());
    fetchRecurring();
  }, [fetchForecast, fetchRecurring]);

  // F30 — load available tags on mount
  useEffect(() => {
    tagService.list().then(setAvailableTags).catch(() => setAvailableTags([]));
  }, []);

  // F30 — tag-filtered fetch: one request per selected tag, results merged & de-duped by id.
  // Stored in tagFilteredList (separate from transactions) so charts are unaffected.
  useEffect(() => {
    if (selectedTags.length === 0) {
      setTagFilteredList(null);
      return;
    }
    let cancelled = false;
    const fetchTagged = async () => {
      try {
        const results = await Promise.all(
          selectedTags.map((tag) => transactionService.list({ tag }))
        );
        if (cancelled) return;
        // Merge and de-dupe by id
        const seen = new Set<number>();
        const merged: Transaction[] = [];
        for (const batch of results) {
          for (const tx of batch) {
            if (!seen.has(tx.id)) {
              seen.add(tx.id);
              merged.push(tx);
            }
          }
        }
        // Sort by date descending to match normal list order
        merged.sort((a, b) => b.transaction_date.localeCompare(a.transaction_date));
        setTagFilteredList(merged);
      } catch {
        // On error, fall back to unfiltered list
        if (!cancelled) setTagFilteredList(null);
      }
    };
    fetchTagged();
    return () => { cancelled = true; };
  }, [selectedTags]);

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
        <nav style={{ display: "flex", gap: "1rem" }}>
          <Link to="/dashboard" className="btn-ghost" style={{ color: "var(--accent2)" }}>Dashboard</Link>
          <Link to="/trends" className="btn-ghost">Trends</Link>
          <Link to="/budgets" className="btn-ghost">Budgets</Link>
          <Link to="/rules" className="btn-ghost">Rules</Link>
          <Link to="/savings" className="btn-ghost">Savings</Link>
        </nav>
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
              <Pie
                data={expenseByCategory}
                dataKey="amount"
                nameKey="name"
                cx="50%" cy="50%"
                innerRadius={50}
                outerRadius={80}
                paddingAngle={2}
                cursor="pointer"
                onClick={(d: { name?: string }) => d?.name && navigate(`/category/${d.name}`)}
              >
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

      {/* F32-fu1 — confirm/reject the auto-applied 'recurring' tag.
          Self-hiding when there is nothing pending. */}
      <RecurringReview />

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
            <Link to="/import" className="import-hint" style={{ color: "var(--accent2)", textDecoration: "none" }}>
              Other bank? Custom import →
            </Link>
            {/* F28 — year-end PDF report */}
            <button
              type="button"
              className="btn-import"
              onClick={() => downloadYearReview(new Date().getFullYear()).catch(() => {})}
              title="Download a one-page PDF summary of this year"
              style={{ marginLeft: "auto" }}
            >
              📄 Year in review
            </button>
          </div>

          {/* F27 — Connect bank (GoCardless sandbox) */}
          <div className="import-section" style={{ marginTop: "0.5rem", flexDirection: "column", alignItems: "flex-start", gap: "0.4rem" }}>
            <div style={{ display: "flex", gap: "0.5rem", alignItems: "center", flexWrap: "wrap" }}>
              <button type="button" className="btn-import" onClick={handleConnectBank} disabled={bankBusy}>
                🏦 Connect bank
              </button>
              {banks.length > 0 && (
                <button type="button" className="btn-import" onClick={handleBankSync} disabled={bankBusy}>
                  ↻ Sync now
                </button>
              )}
              <span className="import-hint">GoCardless sandbox (NL banks)</span>
            </div>
            {banks.length > 0 && (
              <div style={{ fontSize: "0.8rem", color: "var(--muted)" }}>
                {banks.map((b) => (
                  <div key={b.id} style={{ display: "flex", alignItems: "center", gap: "0.5rem", flexWrap: "wrap" }}>
                    <span>
                      {b.institution_id} · <strong>{b.status}</strong>
                      {b.last_sync_at && ` · last sync ${new Date(b.last_sync_at).toLocaleString()}`}
                      {b.last_error && ` · ⚠ ${b.last_error}`}
                    </span>
                    {/* F31 — show Reconnect CTA when consent has expired */}
                    {b.needs_reconnect && (
                      <button
                        type="button"
                        className="btn-import"
                        onClick={handleConnectBank}
                        disabled={bankBusy}
                        style={{ fontSize: "0.75rem", padding: "0.15rem 0.5rem" }}
                      >
                        Reconnect
                      </button>
                    )}
                  </div>
                ))}
              </div>
            )}
            {bankMsg && (
              <div style={{ fontSize: "0.8rem", color: "var(--muted)" }}>{bankMsg}</div>
            )}
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

          {/* F8 + F30 — filter bar (extracted to TransactionFilter; state owned here) */}
          <TransactionFilter
            filterText={filterText} setFilterText={setFilterText}
            filterCategory={filterCategory} setFilterCategory={setFilterCategory}
            filterDateFrom={filterDateFrom} setFilterDateFrom={setFilterDateFrom}
            filterDateTo={filterDateTo} setFilterDateTo={setFilterDateTo}
            filterAmountMin={filterAmountMin} setFilterAmountMin={setFilterAmountMin}
            filterAmountMax={filterAmountMax} setFilterAmountMax={setFilterAmountMax}
            hasActiveFilters={hasActiveFilters}
            onClear={clearFilters}
            availableTags={availableTags}
            selectedTags={selectedTags}
            onToggleTag={handleToggleTag}
          />

          {isLoading && <p>Loading…</p>}
          {(() => {
            // F30: when tags are selected, start from the tag-filtered working list
            // (separate from `transactions` so charts are unaffected).
            // When no tags selected, fall back to the normal full list.
            const baseList = tagFilteredList !== null ? tagFilteredList : transactions;
            const searchLower = filterText.toLowerCase();
            const min = filterAmountMin ? parseFloat(filterAmountMin) : null;
            const max = filterAmountMax ? parseFloat(filterAmountMax) : null;
            const filtered = baseList.filter((tx) => {
              if (searchLower && !tx.description.toLowerCase().includes(searchLower) && !tx.category.toLowerCase().includes(searchLower)) return false;
              if (filterCategory !== "all" && tx.category !== filterCategory) return false;
              if (filterDateFrom && tx.transaction_date < filterDateFrom) return false;
              if (filterDateTo && tx.transaction_date > filterDateTo) return false;
              const amt = parseFloat(tx.amount);
              if (min !== null && amt < min) return false;
              if (max !== null && amt > max) return false;
              return true;
            });
            if (filtered.length === 0 && hasActiveFilters) {
              return <p style={{ color: "var(--muted)", fontSize: "0.85rem", padding: "0.5rem 0" }}>No transactions match the current filters.</p>;
            }
            return filtered.slice(0, 30).map((tx) => (
            <div key={tx.id} className={`tx-row ${tx.type}`}>
              <div>
                <span className="tx-cat">{tx.category}</span>
                <span className="tx-desc">{tx.description}</span>
                <span className="tx-date">{formatDate(tx.transaction_date)}</span>
                {/* F29 — tag chips (read-only); add via the # button on the right. */}
                {tx.tags && tx.tags.length > 0 && (
                  <span style={{ marginLeft: "0.4rem" }}>
                    {tx.tags.map((t) => (
                      <span
                        key={t.id}
                        title="Click ✕ to remove"
                        onClick={async () => {
                          await tagService.unassign(tx.id, t.id);
                          refetchTransactions();
                        }}
                        style={{
                          display: "inline-block",
                          marginRight: "0.25rem",
                          padding: "0.05rem 0.4rem",
                          fontSize: "0.7rem",
                          background: "rgba(99,102,241,0.18)",
                          border: "1px solid rgba(99,102,241,0.4)",
                          borderRadius: "0.7rem",
                          color: "#a5b4fc",
                          cursor: "pointer",
                        }}
                      >
                        #{t.name}
                      </span>
                    ))}
                  </span>
                )}
              </div>
              <div className="tx-right">
                <span className="tx-amount" title={tx.currency !== baseCurrency ? `${tx.currency} original` : undefined}>
                  {tx.type === "expense" ? "-" : "+"}{formatCurrency(parseFloat(tx.amount))}
                  {tx.currency && tx.currency !== baseCurrency && (
                    <span className="tx-currency">{tx.currency}</span>
                  )}
                </span>
                {/* F25 — split an expense into multiple categories */}
                {tx.type === "expense" && tx.parent_transaction_id == null && (
                  <button
                    onClick={() => setSplitTx(tx)}
                    className="btn-del"
                    title="Split this transaction into multiple categories"
                    style={{ fontSize: "0.85rem" }}
                  >
                    ✂︎
                  </button>
                )}
                {/* F29 — add a tag (prompt-based v1) */}
                <button
                  onClick={async () => {
                    const name = window.prompt("Tag name:");
                    if (!name || !name.trim()) return;
                    await tagService.assign(tx.id, name.trim());
                    refetchTransactions();
                  }}
                  className="btn-del"
                  title="Add a tag to this transaction"
                  style={{ fontSize: "0.85rem" }}
                >
                  #
                </button>
                <button onClick={() => remove(tx.id)} className="btn-del">✕</button>
              </div>
            </div>
            ));
          })()}
        </div>
      </div>

      {/* F25 — split modal */}
      {splitTx && (
        <SplitTransactionModal
          tx={splitTx}
          onClose={() => setSplitTx(null)}
          onSplit={() => refetchTransactions()}
        />
      )}
    </div>
  );
}
