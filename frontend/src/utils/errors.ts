// F-lint1 — shared extraction of an API error message.
//
// The `err?.response?.data?.detail || "fallback"` shape was repeated at four
// call sites, three of them typed `catch (err: any)` purely to reach through
// it. This narrows an unknown once, so the call sites stay `unknown` and the
// no-explicit-any rule holds.

interface ApiErrorShape {
  response?: { data?: { detail?: unknown } };
  message?: unknown;
}

/**
 * Best-effort human message from a caught value.
 *
 * Prefers FastAPI's `response.data.detail`, falls back to `Error.message`,
 * then to `fallback`. Never throws — it is called from catch blocks, where a
 * second failure would mask the original.
 */
export function apiErrorMessage(err: unknown, fallback: string): string {
  if (typeof err === 'object' && err !== null) {
    const e = err as ApiErrorShape;
    const detail = e.response?.data?.detail;
    if (typeof detail === 'string' && detail.trim()) return detail;
    // F40 — a 422 from FastAPI puts a LIST of {loc, msg} in detail. Show the messages rather
    // than falling through to a generic fallback that hides why the input was refused.
    if (Array.isArray(detail)) {
      const msgs = detail
        .map((d) => (typeof d === 'object' && d !== null ? (d as { msg?: unknown }).msg : undefined))
        .filter((m): m is string => typeof m === 'string' && m.trim() !== '')
        .map((m) => m.replace(/^Value error, /, ''));
      if (msgs.length) return msgs.join('; ');
    }
    if (typeof e.message === 'string' && e.message.trim()) return e.message;
  }
  return fallback;
}
