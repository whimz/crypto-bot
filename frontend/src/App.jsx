import { useCallback, useEffect, useState } from "react";
import ActivityLog from "./components/ActivityLog.jsx";
import Chart from "./components/Chart.jsx";
import Header from "./components/Header.jsx";
import Login from "./components/Login.jsx";
import Portfolio from "./components/Portfolio.jsx";
import Positions from "./components/Positions.jsx";
import Toast from "./components/Toast.jsx";
import Trades from "./components/Trades.jsx";
import {
  getCurrentUser,
  getHealth,
  getPortfolio,
  getPositions,
  getToken,
  logout,
  setUnauthorizedHandler,
  startBot,
  stopBot,
} from "./api.js";
import { showToast } from "./toastBus.js";

const POLL_INTERVAL_MS = 30_000;
const THEME_STORAGE_KEY = "theme";

export default function App() {
  const [authChecked, setAuthChecked] = useState(false);
  const [username, setUsername] = useState(null);
  const [health, setHealth] = useState(null);
  const [portfolio, setPortfolio] = useState(null);
  const [positions, setPositions] = useState([]);
  const [busy, setBusy] = useState(false);
  const [theme, setTheme] = useState(() => localStorage.getItem(THEME_STORAGE_KEY) || "light");

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem(THEME_STORAGE_KEY, theme);
  }, [theme]);

  const toggleTheme = () => setTheme((t) => (t === "dark" ? "light" : "dark"));

  const handleUnauthenticated = useCallback(() => {
    setUsername(null);
  }, []);

  useEffect(() => {
    setUnauthorizedHandler(handleUnauthenticated);
  }, [handleUnauthenticated]);

  useEffect(() => {
    if (!getToken()) {
      setAuthChecked(true);
      return;
    }
    getCurrentUser()
      .then((data) => setUsername(data.username))
      .catch(() => {})
      .finally(() => setAuthChecked(true));
  }, []);

  const refresh = useCallback(async () => {
    try {
      const [healthData, portfolioData, positionsData] = await Promise.all([
        getHealth(),
        getPortfolio(),
        getPositions(),
      ]);
      setHealth(healthData);
      setPortfolio(portfolioData);
      setPositions(positionsData);
    } catch (err) {
      showToast({
        title: "Failed to load dashboard data",
        description: err.message,
        requestId: err.requestId,
        retry: refresh,
      });
    }
  }, []);

  useEffect(() => {
    if (!username) return;
    refresh();
    const interval = setInterval(refresh, POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [username, refresh]);

  const handleStart = async () => {
    setBusy(true);
    try {
      await startBot();
      await refresh();
    } catch (err) {
      showToast({
        title: "Failed to start the bot",
        description: err.message,
        requestId: err.requestId,
        retry: handleStart,
      });
    } finally {
      setBusy(false);
    }
  };

  const handleStop = async () => {
    setBusy(true);
    try {
      await stopBot();
      await refresh();
    } catch (err) {
      showToast({
        title: "Failed to stop the bot",
        description: err.message,
        requestId: err.requestId,
        retry: handleStop,
      });
    } finally {
      setBusy(false);
    }
  };

  const handleLogout = () => {
    logout();
    setUsername(null);
  };

  const handleLoginSuccess = async () => {
    try {
      const data = await getCurrentUser();
      setUsername(data.username);
    } catch (err) {
      showToast({ title: "Failed to load user", description: err.message, requestId: err.requestId });
    }
  };

  if (!authChecked) {
    return null;
  }

  if (!username) {
    return (
      <>
        <Login onLoginSuccess={handleLoginSuccess} />
        <Toast />
      </>
    );
  }

  return (
    <>
      <Header
        status={health?.status}
        busy={busy}
        onStart={handleStart}
        onStop={handleStop}
        theme={theme}
        onToggleTheme={toggleTheme}
        username={username}
        onLogout={handleLogout}
      />
      <Portfolio portfolio={portfolio} />
      <Positions positions={positions} />
      <Chart />
      <Trades />
      <ActivityLog />
      <Toast />
    </>
  );
}
