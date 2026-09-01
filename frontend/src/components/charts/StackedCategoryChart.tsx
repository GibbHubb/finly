import { BarChart, Bar, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer } from "recharts";
import type { TooltipProps } from "recharts";
import type { MonthlyTrendEntry } from "@/types";
import { formatCurrency } from "@/utils/format";

const EXPENSE_CATEGORIES = [
  "housing", "food", "transport", "entertainment",
  "health", "shopping", "other",
] as const;

const COLORS: Record<string, string> = {
  housing: "#6366f1",
  food: "#22c55e",
  transport: "#f59e0b",
  entertainment: "#ec4899",
  health: "#14b8a6",
  shopping: "#8b5cf6",
  other: "#84cc16",
};

function formatMonth(key: string): string {
  const [y, m] = key.split("-");
  const d = new Date(parseInt(y), parseInt(m) - 1, 1);
  return d.toLocaleString("default", { month: "short", year: "2-digit" });
}

function TrendsTooltip({ active, payload, label }: TooltipProps<number, string>) {
  if (!active || !payload || payload.length === 0) return null;
  const total = payload.reduce((sum, p) => sum + (typeof p.value === "number" ? p.value : 0), 0);
  if (total === 0) return null;
  return (
    <div style={{
      background: "var(--card, #1f2937)", color: "var(--fg, #f8fafc)",
      padding: "0.5rem 0.75rem", borderRadius: 6, fontSize: "0.85rem",
      boxShadow: "0 2px 8px rgba(0,0,0,0.3)",
    }}>
      <div style={{ fontWeight: 600, marginBottom: 4 }}>{label}</div>
      {payload
        .slice()
        .reverse()
        .filter((p) => typeof p.value === "number" && p.value > 0)
        .map((p) => {
          const v = p.value as number;
          const pct = (v / total) * 100;
          return (
            <div key={p.dataKey as string} style={{ display: "flex", justifyContent: "space-between", gap: "0.75rem" }}>
              <span style={{ color: p.color, textTransform: "capitalize" }}>{p.dataKey}</span>
              <span>{formatCurrency(v)} · {pct.toFixed(0)}%</span>
            </div>
          );
        })}
      <div style={{ borderTop: "1px solid rgba(255,255,255,0.1)", marginTop: 4, paddingTop: 4, display: "flex", justifyContent: "space-between" }}>
        <span>Total</span>
        <span>{formatCurrency(total)}</span>
      </div>
    </div>
  );
}

export function StackedCategoryChart({ data }: { data: MonthlyTrendEntry[] }) {
  const chartData = data.map((entry) => {
    const row: Record<string, string | number> = { month: formatMonth(entry.month) };
    for (const cat of EXPENSE_CATEGORIES) {
      row[cat] = parseFloat(entry.categories[cat] ?? "0");
    }
    return row;
  });

  return (
    <ResponsiveContainer width="100%" height={320}>
      <BarChart data={chartData} margin={{ top: 12, right: 12, left: 0, bottom: 4 }}>
        <XAxis dataKey="month" />
        <YAxis tickFormatter={(v: number) => formatCurrency(v)} width={80} />
        <Tooltip content={<TrendsTooltip />} />
        <Legend />
        {EXPENSE_CATEGORIES.map((cat) => (
          <Bar key={cat} dataKey={cat} stackId="expenses" fill={COLORS[cat]} />
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}
