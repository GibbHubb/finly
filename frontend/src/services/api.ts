import axios from "axios";

// F33 — base URL is env-driven so the deployed static site can reach the
// backend on its own origin. Empty/unset keeps the relative path, which is
// what the Vite dev proxy expects, so local development is unchanged.
const API_ROOT = import.meta.env.VITE_API_URL ?? "";
const api = axios.create({ baseURL: `${API_ROOT}/api/v1` });

// F42 — token storage helpers, one place for both keys so login/refresh/
// logout can't drift out of sync with each other.
export function getAccessToken(): string | null {
  return localStorage.getItem("token");
}
export function getRefreshToken(): string | null {
  return localStorage.getItem("refresh_token");
}
export function setTokens(accessToken: string, refreshToken: string): void {
  localStorage.setItem("token", accessToken);
  localStorage.setItem("refresh_token", refreshToken);
}
export function clearTokens(): void {
  localStorage.removeItem("token");
  localStorage.removeItem("refresh_token");
}

api.interceptors.request.use((config) => {
  const token = getAccessToken();
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
//
// F42 — /auth/refresh joined this list. A refresh call itself returning 401
// (the refresh token is expired/revoked) is not "an expired session to try
// refreshing" — it IS the refresh attempt, and trying to refresh a failed
// refresh is exactly the infinite loop the single-flight logic below has to
// not fall into.
const AUTH_ATTEMPT = ["/auth/login", "/auth/register", "/auth/demo-login", "/auth/refresh"];

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

function redirectToLogin(): void {
  clearTokens();
  window.location.href = "/login";
}

// F42 — silent refresh, single-flight.
//
// Several requests can 401 at once (a dashboard fires off transactions +
// budgets + summary in parallel). Without this, EACH one would call
// /auth/refresh independently: N refresh calls, and — because refresh
// ROTATES the token — all but the first would be replaying an
// already-consumed refresh token and fail. `inFlightRefresh` is shared by
// every concurrent 401: the first caller starts the request, everyone else
// just awaits the same promise, and exactly one new pair gets minted.
let inFlightRefresh: Promise<string | null> | null = null;

/**
 * Resolves to the new access token, or `null` if the session is genuinely
 * over (no refresh token to try, or the server rejected it outright).
 *
 * F42 code-review catch: a network error or a 5xx from /auth/refresh is NOT
 * the same as the server saying "this token is invalid" — it means the
 * request never got a verdict. Treating it the same as a 401 used to log a
 * user with a perfectly good, unexpired refresh token straight out on a
 * transient blip. Only a definitive 401/403 clears tokens and gives up; any
 * other failure REJECTS so the caller lets this one request fail without
 * touching the (still possibly valid) stored tokens — the next request gets
 * its own fresh attempt.
 */
function refreshAccessToken(): Promise<string | null> {
  if (inFlightRefresh) return inFlightRefresh;

  const refreshToken = getRefreshToken();
  if (!refreshToken) {
    return Promise.resolve(null);
  }

  inFlightRefresh = api
    .post<{ access_token: string; refresh_token: string }>("/auth/refresh", {
      refresh_token: refreshToken,
    })
    .then(({ data }) => {
      setTokens(data.access_token, data.refresh_token);
      return data.access_token;
    })
    .catch((err) => {
      const refreshStatus = err.response?.status;
      if (refreshStatus === 401 || refreshStatus === 403) {
        return null;
      }
      throw err;
    })
    .finally(() => {
      inFlightRefresh = null;
    });

  return inFlightRefresh;
}

api.interceptors.response.use(
  (r) => r,
  async (err) => {
    const status = err.response?.status;
    const url: string = err.config?.url ?? "";

    if (!shouldRedirectOn401(status, url)) {
      return Promise.reject(err);
    }

    const originalRequest = err.config ?? {};
    if (originalRequest._retriedAfterRefresh) {
      // F42 — already retried once after a fresh token; a second 401 is a
      // real expired/revoked session, not a race to lose. Refuse to loop.
      redirectToLogin();
      return Promise.reject(err);
    }

    let newAccessToken: string | null;
    try {
      newAccessToken = await refreshAccessToken();
    } catch {
      // Transient failure (network/5xx) talking to /auth/refresh — the
      // session itself may still be fine. Don't clear tokens or redirect;
      // just let THIS request fail, and the next one gets its own attempt.
      return Promise.reject(err);
    }
    if (!newAccessToken) {
      redirectToLogin();
      return Promise.reject(err);
    }

    originalRequest._retriedAfterRefresh = true;
    originalRequest.headers = { ...originalRequest.headers, Authorization: `Bearer ${newAccessToken}` };
    return api(originalRequest);
  }
);

export default api;
