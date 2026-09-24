import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { authService } from "@/services/auth";
import { useAuthStore } from "@/store/authStore";

export default function RegisterPage() {
  const [form, setForm] = useState({ email: "", password: "", full_name: "" });
  const [error, setError] = useState("");
  const { login } = useAuthStore();
  const navigate = useNavigate();

  const update = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm((f) => ({ ...f, [k]: e.target.value }));

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    try {
      await authService.register(form.email, form.password, form.full_name);
      await login(form.email, form.password);
      navigate("/dashboard");
    } catch {
      setError("Registration failed. Email may already be in use.");
    }
  };

  return (
    <div className="auth-page">
      <main className="auth-card">
        <h1>💸 Finly</h1>
        <h2>Create account</h2>
        {error && <p className="error" role="alert">{error}</p>}
        <form onSubmit={handleSubmit}>
          <label htmlFor="register-name">Name<input id="register-name" value={form.full_name} onChange={update("full_name")} required /></label>
          <label htmlFor="register-email">Email<input id="register-email" type="email" value={form.email} onChange={update("email")} required /></label>
          <label htmlFor="register-password">Password<input id="register-password" type="password" value={form.password} onChange={update("password")} required minLength={8} /></label>
          <button type="submit">Create account</button>
        </form>
        <p>Already registered? <Link to="/login">Sign in</Link></p>
      </main>
    </div>
  );
}
