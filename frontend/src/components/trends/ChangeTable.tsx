import type { MonthlyTrendEntry } from "@/types";
import { formatCurrency } from "@/utils/format";

const EXPENSE_CATEGORIES = [
  "housing", "food", "transport", "entertainment",
  "health", "shopping", "other",
] as const;

interface Row {
  category: string;
  current: number;
  previous: number;
  pct: number | null;   // null = new spending (prev was 0)
}

export function ChangeTable({ data }: { data: MonthlyTrendEntry[] }) {
  if (data.length < 2) {
    return <p className="change-table-empty">Need at least 2 months of data for comparison.</p>;
  }

  const current = data[data.length - 1];
  const previous = data[data.length - 2];

  const rows: Row[] = EXPENSE_CATEGORIES.map((cat) => {
    const cur = parseFloat(current.categories[cat] ?? "0");
    const prev = parseFloat(previous.categories[cat] ?? "0");
    const pct = prev > 0 ? ((cur - prev) / prev) * 100 : null;
    return { category: cat, current: cur, previous: prev, pct };
  }).filter((r) => r.current > 0 || r.previous > 0);

  if (rows.length === 0) {
    return <p className="change-table-empty">No expense activity in the last two months.</p>;
  }

  return (
    <table className="change-table">
      <thead>
        <tr>
          <th>Category</th>
          <th style={{ textAlign: "right" }}>This month</th>
          <th style={{ textAlign: "right" }}>Last month</th>
          <th style={{ textAlign: "right" }}>Change</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => {
          let arrow = "→";
          let color = "#94a3b8";
          let label: string;
          if (r.pct === null) {
            label = r.current > 0 ? "new" : "—";
          } else if (r.pct > 5) {
            arrow = "↑";
            color = "#ef4444";
            label = `+${r.pct.toFixed(0)}%`;
          } else if (r.pct < -5) {
            arrow = "↓";
            color = "#22c55e";
            label = `${r.pct.toFixed(0)}%`;
          } else {
            label = `${r.pct >= 0 ? "+" : ""}${r.pct.toFixed(0)}%`;
          }
          return (
            <tr key={r.category}>
              <td style={{ textTransform: "capitalize" }}>{r.category}</td>
              <td style={{ textAlign: "right" }}>{formatCurrency(r.current)}</td>
              <td style={{ textAlign: "right" }}>{formatCurrency(r.previous)}</td>
              <td style={{ textAlign: "right", color }}>{arrow} {label}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
