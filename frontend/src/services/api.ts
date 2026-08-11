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

api.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem("token");
      window.location.href = "/login";
    }
    return Promise.reject(err);
  }
);

export default api;
