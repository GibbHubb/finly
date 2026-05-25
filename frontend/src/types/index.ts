export interface User {
  id: number;
  email: string;
  full_name: string;
  is_active: boolean;
  base_currency: string;
  created_at: string;
}

export interface Transaction {
  id: number;
  amount: string;
  type: "income" | "expense";
  category: Category;
  description: string;
  transaction_date: string;
  currency: string;
  base_amount: string | null;
  created_at: string;
  parent_transaction_id?: number | null;  // F25 — child rows of a split parent
  tags?: { id: number; name: string }[];  // F29
}

export type Category =
  | "housing" | "food" | "transport" | "entertainment"
  | "health" | "shopping" | "salary" | "freelance" | "other";

export interface TransactionCreate {
  amount: number;
  type: "income" | "expense";
  category: Category;
  description?: string;
  transaction_date: string;
  currency?: string;
}

export interface TransactionFilters {
  skip?: number;
  limit?: number;
  date_from?: string;
  date_to?: string;
  category?: Category;
  type?: "income" | "expense";
  tag?: string;  // F29
}

export interface CategorySummary {
  category: string;
  income: string;
  expenses: string;
  budget_limit?: string;
  budget_remaining?: string;
}

export interface Budget {
  id: number;
  category: Category;
  limit_amount: string;
  month: number;
  year: number;
}

export interface BudgetCreate {
  category: Category;
  limit_amount: number;
  month: number;
  year: number;
}

export interface ForecastResult {
  month: string;           // YYYY-MM
  projected_total: string | null;
  confidence: "low" | "medium" | "high";
  data_points_used: number;
  reason: string | null;
}

export interface ImportResult {
  imported: number;
  skipped_duplicates: number;
  errors: string[];
}

export interface MonthlySummary {
  month: number;
  year: number;
  total_income: string;
  total_expenses: string;
  net: string;
  categories: CategorySummary[];
}

export interface BudgetAlert {
  event: "budget_alert";
  category: string;
  spent: string;
  limit: string;
  overage: string;
}

export interface RecurringItem {
  merchant: string;
  monthly_amount: number;
  typical_day: number;
  months_detected: number;
  last_seen: string;
}

export interface MonthlyTrendEntry {
  month: string;                          // YYYY-MM
  categories: Record<string, string>;     // category -> amount as string (Decimal)
}

export type DateFormatKey =
  | "DD-MM-YYYY" | "YYYY-MM-DD" | "DD/MM/YYYY" | "MM/DD/YYYY" | "YYYYMMDD";

export type DecimalFormat = "comma" | "dot";

export interface ImportMappingPayload {
  date_col: string;
  amount_col: string;
  description_col: string;
  category_col?: string | null;
  delimiter?: string | null;
  date_format: DateFormatKey;
  decimal_format: DecimalFormat;
}

export interface ImportPreview {
  headers: string[];
  sample_rows: Record<string, string>[];
  delimiter: string;
  saved_mapping: ImportMappingPayload | null;
}

export type MatchType = "contains" | "equals" | "starts_with" | "regex";

export interface CategorisationRule {
  id: number;
  match_type: MatchType;
  match_value: string;
  category: Category;
  priority: number;
  enabled: boolean;
  created_at: string;
}

export interface CategorisationRuleCreate {
  match_type: MatchType;
  match_value: string;
  category: Category;
  priority?: number;
  enabled?: boolean;
}

export interface CategorisationRuleUpdate {
  match_type?: MatchType;
  match_value?: string;
  category?: Category;
  priority?: number;
  enabled?: boolean;
}

export interface SavingsGoal {
  id: number;
  name: string;
  target_amount: string;
  current_amount: string;
  deadline: string | null;
  progress_pct: number;
}

export interface SavingsGoalCreate {
  name: string;
  target_amount: number;
  deadline?: string;
}

export interface SavingsGoalUpdate {
  name?: string;
  target_amount?: number;
  current_amount?: number;
  deadline?: string | null;
}
