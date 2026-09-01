import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuthStore } from "@/store/authStore";
import { transactionService } from "@/services/transactions";
import type { DateFormatKey, DecimalFormat, ImportMappingPayload, ImportPreview, ImportResult } from "@/types";

type Step = "upload" | "map" | "done";

const DATE_FORMATS: DateFormatKey[] = ["DD-MM-YYYY", "YYYY-MM-DD", "DD/MM/YYYY", "MM/DD/YYYY", "YYYYMMDD"];

const labelStyle: React.CSSProperties = {
  display: "flex", flexDirection: "column", gap: "0.25rem",
  fontSize: "0.85rem", color: "var(--muted)",
};
const reqStyle: React.CSSProperties = { color: "var(--accent, #ef4444)", marginLeft: "0.25rem" };

export default function ImportPage() {
  const { user, logout } = useAuthStore();
  const navigate = useNavigate();

  const [step, setStep] = useState<Step>("upload");
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [mapping, setMapping] = useState<Partial<ImportMappingPayload>>({
    date_format: "DD-MM-YYYY",
    decimal_format: "comma",
  });
  const [result, setResult] = useState<ImportResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const handleFile = async (f: File) => {
    setFile(f);
    setError(null);
    setBusy(true);
    try {
      const pv = await transactionService.importPreview(f);
      setPreview(pv);
      // Pre-fill mapping from saved preference if every referenced column is present in this file
      if (pv.saved_mapping) {
        const cols = new Set(pv.headers);
        const ok =
          cols.has(pv.saved_mapping.date_col) &&
          cols.has(pv.saved_mapping.amount_col) &&
          cols.has(pv.saved_mapping.description_col) &&
          (!pv.saved_mapping.category_col || cols.has(pv.saved_mapping.category_col));
        if (ok) setMapping(pv.saved_mapping);
      }
      setStep("map");
    } catch {
      setError("Could not read that file — is it a CSV?");
    } finally {
      setBusy(false);
    }
  };

  const canSubmit =
    !!file &&
    !!mapping.date_col &&
    !!mapping.amount_col &&
    !!mapping.description_col &&
    !!mapping.date_format &&
    !!mapping.decimal_format;

  const runImport = async () => {
    if (!file || !canSubmit) return;
    setError(null);
    setBusy(true);
    try {
      const res = await transactionService.importCommit(file, mapping as ImportMappingPayload);
      setResult(res);
      setStep("done");
    } catch {
      setError("Import failed — check the mapping and try again.");
    } finally {
      setBusy(false);
    }
  };

  const reset = () => {
    setStep("upload");
    setFile(null);
    setPreview(null);
    setResult(null);
    setError(null);
  };

  const picker = (label: keyof ImportMappingPayload, optional = false) => (
    <select
      value={(mapping[label] as string) ?? ""}
      onChange={(e) => setMapping((m) => ({ ...m, [label]: e.target.value || (optional ? null : "") }))}
      className="tx-filter-input"
    >
      <option value="">{optional ? "— none —" : "— pick column —"}</option>
      {preview?.headers.map((h) => <option key={h} value={h}>{h}</option>)}
    </select>
  );

  return (
    <div className="dashboard">
      <header className="dash-header">
        <h1>💸 Finly</h1>
        <nav className="nav-links">
          <Link to="/dashboard" className="btn-ghost">Dashboard</Link>
          <Link to="/trends" className="btn-ghost">Trends</Link>
          <Link to="/budgets" className="btn-ghost">Budgets</Link>
          <Link to="/rules" className="btn-ghost">Rules</Link>
          <Link to="/savings" className="btn-ghost">Savings</Link>
        </nav>
        <span>Hello, {user?.full_name}</span>
        <button onClick={logout} className="btn-ghost">Sign out</button>
      </header>

      <h2 style={{ fontFamily: "var(--font-head)", margin: "1.5rem 0 0.5rem" }}>Custom CSV import</h2>
      <p style={{ color: "var(--muted)", marginBottom: "1.5rem", fontSize: "0.9rem" }}>
        Upload any bank CSV, map the columns once, and we'll remember the mapping next time.
        For ING or ABN AMRO exports, the <Link to="/dashboard" style={{ color: "var(--accent2)" }}>Dashboard</Link> quick-import is faster.
      </p>

      <ol style={{
        display: "flex", gap: "1rem", listStyle: "none", padding: 0, marginBottom: "1rem",
        fontSize: "0.85rem", color: "var(--muted)",
      }}>
        {(["upload", "map", "done"] as const).map((s, i) => {
          const activeIdx = step === "upload" ? 0 : step === "map" ? 1 : 2;
          const isActive = s === step;
          const isDone = i < activeIdx;
          return (
            <li key={s} style={{
              color: isActive ? "var(--accent2)" : isDone ? "var(--fg, inherit)" : undefined,
              fontWeight: isActive ? 600 : 400,
            }}>
              {i + 1}. {s === "upload" ? "Upload" : s === "map" ? "Map columns" : "Result"}
            </li>
          );
        })}
      </ol>

      {error && <div className="import-toast error">{error}</div>}

      {step === "upload" && (
        <div className="chart-card">
          <h3>Pick a CSV file</h3>
          <input
            type="file"
            accept=".csv,text/csv"
            disabled={busy}
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) handleFile(f);
            }}
          />
          {busy && <p style={{ marginTop: "0.5rem" }}>Reading…</p>}
        </div>
      )}

      {step === "map" && preview && (
        <>
          <div className="chart-card">
            <h3>Map your columns</h3>
            <p style={{ color: "var(--muted)", fontSize: "0.85rem" }}>
              Detected delimiter: <code>{preview.delimiter === "\t" ? "\\t" : preview.delimiter}</code>
              {preview.saved_mapping && " · pre-filled from your previous import"}
            </p>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: "0.75rem" }}>
              <label style={labelStyle}>Date <span style={reqStyle}>*</span>{picker("date_col")}</label>
              <label style={labelStyle}>Amount <span style={reqStyle}>*</span>{picker("amount_col")}</label>
              <label style={labelStyle}>Description <span style={reqStyle}>*</span>{picker("description_col")}</label>
              <label style={labelStyle}>Category (optional){picker("category_col", true)}</label>
              <label style={labelStyle}>
                Date format <span style={reqStyle}>*</span>
                <select
                  value={mapping.date_format}
                  onChange={(e) => setMapping((m) => ({ ...m, date_format: e.target.value as DateFormatKey }))}
                  className="tx-filter-input"
                >
                  {DATE_FORMATS.map((f) => <option key={f} value={f}>{f}</option>)}
                </select>
              </label>
              <label style={labelStyle}>
                Decimal format <span style={reqStyle}>*</span>
                <select
                  value={mapping.decimal_format}
                  onChange={(e) => setMapping((m) => ({ ...m, decimal_format: e.target.value as DecimalFormat }))}
                  className="tx-filter-input"
                >
                  <option value="comma">Comma (1.234,56)</option>
                  <option value="dot">Dot (1,234.56)</option>
                </select>
              </label>
            </div>
            <p style={{ color: "var(--muted)", fontSize: "0.8rem", marginTop: "0.75rem" }}>
              Amounts starting with <code>-</code> become expenses; positive amounts become income.
            </p>
          </div>

          <div className="chart-card">
            <h3>Sample rows</h3>
            <div style={{ overflowX: "auto" }}>
              <table className="change-table">
                <thead>
                  <tr>{preview.headers.map((h) => <th key={h}>{h}</th>)}</tr>
                </thead>
                <tbody>
                  {preview.sample_rows.map((row, i) => (
                    <tr key={i}>
                      {preview.headers.map((h) => <td key={h}>{row[h] ?? ""}</td>)}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div style={{ display: "flex", gap: "0.75rem", marginTop: "1rem" }}>
            <button onClick={reset} className="btn-ghost">Back</button>
            <button onClick={runImport} disabled={!canSubmit || busy}>
              {busy ? "Importing…" : "Import transactions"}
            </button>
          </div>
        </>
      )}

      {step === "done" && result && (
        <div className="chart-card">
          <h3>Done</h3>
          <p>
            <strong>{result.imported}</strong> imported · <strong>{result.skipped_duplicates}</strong> duplicates skipped
            {result.errors.length > 0 && <> · <strong>{result.errors.length}</strong> row error(s)</>}
          </p>
          {result.errors.length > 0 && (
            <details style={{ marginTop: "0.5rem" }}>
              <summary>Errors ({result.errors.length})</summary>
              <ul style={{ fontSize: "0.8rem", color: "var(--muted)" }}>
                {result.errors.slice(0, 20).map((e, i) => <li key={i}>{e}</li>)}
                {result.errors.length > 20 && <li>…and {result.errors.length - 20} more</li>}
              </ul>
            </details>
          )}
          <div style={{ display: "flex", gap: "0.75rem", marginTop: "1rem" }}>
            <button onClick={reset} className="btn-ghost">Import another</button>
            <button onClick={() => navigate("/dashboard")}>Back to dashboard</button>
          </div>
        </div>
      )}
    </div>
  );
}
