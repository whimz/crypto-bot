import { useState } from "react";
import { login } from "../api.js";
import { showToast } from "../toastBus.js";

export default function Login({ onLoginSuccess }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      await login(username, password);
      onLoginSuccess();
    } catch (err) {
      showToast({
        title: "Sign in failed",
        description: "Invalid username or password",
        requestId: err.requestId,
      });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="login-page">
      <form className="login-card" onSubmit={handleSubmit}>
        <h1>Crypto Bot</h1>
        <p className="login-subtitle">Sign in to continue</p>
        <label className="login-field">
          <span>Username</span>
          <input
            type="text"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoFocus
            required
          />
        </label>
        <label className="login-field">
          <span>Password</span>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </label>
        <button type="submit" className="primary login-submit" disabled={busy}>
          {busy ? "Signing in..." : "Sign In"}
        </button>
      </form>
    </div>
  );
}
