/** Format a number as a currency string e.g. €1,234.56 */
export function formatCurrency(amount: number, currency = "EUR"): string {
  return new Intl.NumberFormat("en-IE", { style: "currency", currency }).format(amount);
}

/** Format ISO date string to readable form e.g. "Jun 1, 2024" */
export function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-IE", { day: "numeric", month: "short", year: "numeric" });
}
