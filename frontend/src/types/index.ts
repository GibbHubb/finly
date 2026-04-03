export interface User {
  id: number;
  email: string;
  full_name: string;
  is_active: boolean;
  created_at: string;
}

export interface Transaction {
  id: number;
  amount: string;
  type: "income" | "expense";
  category: Category;
  description: string;
  transaction_date: string;
  created_at: string;
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
}

export interface TransactionFilters {
  skip?: number;
  limit?: number;
  date_from?: string;
  date_to?: string;
  category?: Category;
  type?: "income" | "expense";
}

export interface CategorySummary {
  category: string;
  income: string;
  expenses: string;
  budget_limit?: string;
  budget_remaining?: string;
}

export interface MonthlySummary {
  month: number;
  year: number;
  total_income: string;
  total_expenses: string;
  net: string;
  categories: CategorySummary[];
}
