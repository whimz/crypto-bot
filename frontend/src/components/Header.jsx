import { useEffect, useRef, useState } from "react";
import { Play, Square, RefreshCw, UserCircle, Moon, Sun, LogOut, Settings as SettingsIcon } from "lucide-react";

function LogoMark() {
  return (
    <svg
      width="28"
      height="28"
      viewBox="0 0 28 28"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      aria-label="Crypto Bot"
      role="img"
    >
      <line x1="7" y1="4" x2="7" y2="11" />
      <rect x="4" y="11" width="6" height="9" rx="1" />
      <line x1="14" y1="2" x2="14" y2="9" />
      <rect x="11" y="9" width="6" height="14" rx="1" />
      <line x1="21" y1="6" x2="21" y2="13" />
      <rect x="18" y="13" width="6" height="7" rx="1" />
    </svg>
  );
}

export default function Header({
  status,
  busy,
  onStart,
  onStop,
  onRunCycle,
  theme,
  onToggleTheme,
  username,
  onLogout,
  inactive,
  onOpenSettings,
}) {
  const isRunning = status === "running";
  const label = status ? status : "unknown";
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef(null);

  useEffect(() => {
    if (!menuOpen) return;
    const handleClickOutside = (e) => {
      if (menuRef.current && !menuRef.current.contains(e.target)) setMenuOpen(false);
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [menuOpen]);

  return (
    <div className="header">
      <div className="header-title">
        <LogoMark />
        <span className={`status-pill ${isRunning ? "running" : "stopped"}`}>
          <span className="status-dot" />
          {label}
        </span>
        {inactive && (
          <span className="inactive-warning" title="Bot has not completed a cycle in over 20 minutes">
            ⚠️ Inactive
          </span>
        )}
      </div>
      <div className="header-actions">
        <button className="icon-button primary" onClick={onStart} disabled={busy || isRunning} title="Start Bot" aria-label="Start Bot">
          <Play size={18} />
        </button>
        <button className="icon-button danger" onClick={onStop} disabled={busy || !isRunning} title="Stop Bot" aria-label="Stop Bot">
          <Square size={18} />
        </button>
        {isRunning && (
          <button
            className="icon-button"
            onClick={onRunCycle}
            disabled={busy}
            title="Run cycle now"
            aria-label="Run cycle now"
          >
            <RefreshCw size={18} />
          </button>
        )}
        {username && (
          <div className="account-menu" ref={menuRef}>
            <button
              className="icon-button"
              onClick={() => setMenuOpen((open) => !open)}
              title={username}
              aria-label="Account menu"
            >
              <UserCircle size={20} />
            </button>
            {menuOpen && (
              <div className="account-dropdown">
                <div className="account-dropdown-username">{username}</div>
                <button onClick={onToggleTheme}>
                  {theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}
                  {theme === "dark" ? "Light theme" : "Dark theme"}
                </button>
                <button
                  onClick={() => {
                    setMenuOpen(false);
                    onOpenSettings();
                  }}
                >
                  <SettingsIcon size={16} />
                  Trade settings
                </button>
                <button onClick={onLogout}>
                  <LogOut size={16} />
                  Logout
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
