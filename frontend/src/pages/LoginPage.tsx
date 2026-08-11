import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { useAuthStore } from "@/store/authStore";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const { login, demoLogin, isLoading } = useAuthStore();
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    try {
      await login(email, password);
      navigate("/dashboard");
    } catch {
      setError("Invalid email or password");
    }
  };

  // F33 — one click into a pre-seeded, auto-resetting demo account. The
  // endpoint 404s when DEMO_MODE is off, so on a non-demo deployment this
  // button reports that rather than hanging.
  const handleDemo = async () => {
    setError("");
    try {
      await demoLogin();
      navigate("/dashboard");
    } catch {
      setError("The demo isn't available on this deployment.");
    }
  };

  return (
    <div className="auth-page">
      <div className="auth-card">
        <h1>💸 Finly</h1>
        <h2>Sign in</h2>
        {error && <p className="error">{error}</p>}
        <form onSubmit={handleSubmit}>
          <label>Email<input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required /></label>
          <label>Password<input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required /></label>
          <button type="submit" disabled={isLoading}>{isLoading ? "Signing in…" : "Sign in"}</button>
        </form>

        <div className="auth-divider"><span>or</span></div>

        <button
          type="button"
          className="demo-button"
          onClick={handleDemo}
          disabled={isLoading}
        >
          Try the demo
        </button>
        <p className="demo-hint">
          No sign-up. Explore a pre-filled account with four months of data —
          it resets itself, so feel free to change anything.
        </p>

        <p>No account? <Link to="/register">Register</Link></p>
      </div>
    </div>
  );
}
