import axios from "axios";

// F33 — base URL is env-driven so the deployed static site can reach the
// backend on its own origin. Empty/unset keeps the relative path, which is
// what the Vite dev proxy expects, so local development is unchanged.
const API_ROOT = import.meta.env.VITE_API_URL ?? "";
const api = axios.create({ baseURL: `${API_ROOT}/api/v1` });

api.interceptors.request.use((config) => {
  const token = localStorage.getItem("token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// F37 — a 401 from a SIGN-IN ATTEMPT is not an expired session.
//
// This redirected on every 401, including the one that says "wrong password".
// `window.location.href` is a full page load, so React remounted and the
// `Invalid email or password` message the login page had just set was wiped
// before it painted: you typed a bad password and the form silently blanked,
// with nothing saying why. The e2e spec had been asserting that message for
// months, and had never run in CI to say so.
//
// Session expiry still bounces you to /login. An authentication ATTEMPT is
// allowed to fail and be reported where it happened.
const AUTH_ATTEMPT = ["/auth/login", "/auth/register", "/auth/demo-login"];

/**
 * Should a 401 bounce the browser to /login?
 *
 * Exported so the rule can be tested without standing up axios and a fake
 * `window.location` — the decision is the part worth pinning, and it is the
 * part that was wrong.
 */
export function shouldRedirectOn401(status: number | undefined, url: string): boolean {
  if (status !== 401) return false;
  return !AUTH_ATTEMPT.some((p) => url.includes(p));
}

api.interceptors.response.use(
  (r) => r,
  (err) => {
    if (shouldRedirectOn401(err.response?.status, err.config?.url ?? "")) {
      localStorage.removeItem("token");
      window.location.href = "/login";
    }
    return Promise.reject(err);
  }
);

export default api;
