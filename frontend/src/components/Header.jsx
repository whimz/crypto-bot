export default function Header({ status, busy, onStart, onStop, theme, onToggleTheme, username, onLogout }) {
  const isRunning = status === "running";
  const label = status ? status : "unknown";

  return (
    <div className="header">
      <div className="header-title">
        <h1>Crypto Bot</h1>
        <span className={`status-pill ${isRunning ? "running" : "stopped"}`}>
          <span className="status-dot" />
          {label}
        </span>
      </div>
      <div className="header-actions">
        <button className="primary" onClick={onStart} disabled={busy || isRunning}>
          Start Bot
        </button>
        <button className="danger" onClick={onStop} disabled={busy || !isRunning}>
          Stop Bot
        </button>
        <button
          className="theme-toggle"
          onClick={onToggleTheme}
          aria-label={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
          title={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
        >
          {theme === "dark" ? "🌙" : "☀️"}
        </button>
        {username && (
          <>
            <span className="username">{username}</span>
            <button onClick={onLogout}>Logout</button>
          </>
        )}
      </div>
    </div>
  );
}
