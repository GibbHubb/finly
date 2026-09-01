import { useEffect, useRef } from "react";
import { useTransactionStore } from "@/store/transactionStore";
import { useAuthStore } from "@/store/authStore";

/**
 * F34 — replaces `useTransactionSocket`.
 *
 * The socket could not survive the move to Vercel: serverless functions cannot
 * hold a connection open, so `/ws/transactions` would have been a WebSocket
 * that fails and retries on every page load, forever, with the UI still
 * implying live updates.
 *
 * It was already broken before that. `VITE_WS_URL` was never set on the
 * deployed environment, so the built SPA dialled `ws://localhost:8000` — the
 * *visitor's own machine*. Nobody noticed, because a WebSocket that never
 * connects looks exactly like one with nothing to say.
 *
 * Polling is honestly worse as an experience and honestly better as a claim:
 * a transaction added on another device shows up within POLL_MS instead of
 * instantly. That was the call in F34 §8 — the feature is a portfolio talking
 * point, and a dead socket is worse than a slow one.
 *
 * ⚠️ **Budget alerts are NOT delivered here.** The socket pushed a
 * `budget_alert` frame that this hook cannot reproduce: there is no "what
 * changed since you last asked" endpoint to poll, and inventing alerts on the
 * client would fire a toast for a budget that was already over before the page
 * loaded. The dashboard's own budget bars still show the state — see F35.
 */
const POLL_MS = 15_000;

export function useTransactionPolling() {
  const token = useAuthStore((s) => s.token);
  const fetchTransactions = useTransactionStore((s) => s.fetch);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  useEffect(() => {
    if (!token) return;
    let alive = true;

    async function tick() {
      try {
        await fetchTransactions();
      } catch {
        // A failed poll is not worth surfacing: the next one is 15s away and
        // the page still renders whatever it last had.
      } finally {
        // setTimeout rather than setInterval, so a slow response on a
        // cold-starting function cannot stack requests on top of each other.
        if (alive) timer.current = setTimeout(tick, POLL_MS);
      }
    }

    // Don't poll a tab nobody is looking at. This is a portfolio demo on a free
    // tier, and a background tab polling all night is how "free" quietly stops
    // being free.
    function onVisibility() {
      if (document.visibilityState === "hidden") {
        if (timer.current) clearTimeout(timer.current);
        timer.current = undefined;
      } else if (alive && timer.current === undefined) {
        void tick();
      }
    }
    document.addEventListener("visibilitychange", onVisibility);

    void tick();

    return () => {
      alive = false;
      if (timer.current) clearTimeout(timer.current);
      timer.current = undefined;
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [token, fetchTransactions]);
}
