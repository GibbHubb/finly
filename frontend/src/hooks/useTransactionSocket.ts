import { useEffect, useRef } from "react";
import { useTransactionStore } from "@/store/transactionStore";
import { useAuthStore } from "@/store/authStore";

const WS_BASE = import.meta.env.VITE_WS_URL ?? "ws://localhost:8000";
const MAX_RETRIES = 5;

export function useTransactionSocket() {
  const token = useAuthStore((s) => s.token);
  const pushTransaction = useTransactionStore((s) => s.pushTransaction);
  const retries = useRef(0);
  const ws = useRef<WebSocket | null>(null);
  const unmounted = useRef(false);

  useEffect(() => {
    if (!token) return;
    unmounted.current = false;

    function connect() {
      if (unmounted.current) return;
      const socket = new WebSocket(`${WS_BASE}/ws/transactions?token=${token}`);
      ws.current = socket;

      socket.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data);
          if (msg.event === "transaction_created") {
            pushTransaction(msg.transaction);
          }
        } catch {
          // ignore malformed frames
        }
      };

      socket.onclose = () => {
        if (unmounted.current) return;
        if (retries.current < MAX_RETRIES) {
          const delay = Math.min(1000 * 2 ** retries.current, 30_000);
          retries.current += 1;
          setTimeout(connect, delay);
        }
      };

      socket.onopen = () => {
        retries.current = 0;
      };
    }

    connect();

    return () => {
      unmounted.current = true;
      ws.current?.close();
    };
  }, [token]);
}
