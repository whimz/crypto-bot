import { useCallback, useEffect, useRef, useState } from "react";
import ActivityLog from "./components/ActivityLog.jsx";
import Chart from "./components/Chart.jsx";
import DepositChart from "./components/DepositChart.jsx";
import FadeInSection from "./components/FadeInSection.jsx";
import Header from "./components/Header.jsx";
import Login from "./components/Login.jsx";
import Portfolio from "./components/Portfolio.jsx";
import Positions from "./components/Positions.jsx";
import SettingsDrawer from "./components/SettingsDrawer.jsx";
import Toast from "./components/Toast.jsx";
import Trades from "./components/Trades.jsx";
import {
  getCurrentUser,
  getHealth,
  getPortfolio,
  getPositions,
  getToken,
  logout,
  runCycleNow,
  setUnauthorizedHandler,
  startBot,
  stopBot,
} from "./api.js";
import { showToast } from "./toastBus.js";

const POLL_INTERVAL_MS = 30_000;
const THEME_STORAGE_KEY = "theme";
const INACTIVITY_THRESHOLD_MS = 20 * 60 * 1000;

export default function App() {
  const [authChecked, setAuthChecked] = useState(false);
  const [username, setUsername] = useState(null);
  const [health, setHealth] = useState(null);
  const [portfolio, setPortfolio] = useState(null);
  const [positions, setPositions] = useState([]);
  const [busy, setBusy] = useState(false);
  const [theme, setTheme] = useState(() => localStorage.getItem(THEME_STORAGE_KEY) || "light");
  const [settingsOpen, setSettingsOpen] = useState(false);
  // Tracks whether we've already toasted the current inactivity episode, so polling every
  // 30s doesn't spam a new toast each time while the bot stays inactive.
  const inactivityToastedRef = useRef(false);

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

      const lastCycleAt = healthData?.last_cycle_at ? new Date(healthData.last_cycle_at).getTime() : null;
      const isInactive = lastCycleAt !== null && Date.now() - lastCycleAt > INACTIVITY_THRESHOLD_MS;
      if (isInactive && !inactivityToastedRef.current) {
        inactivityToastedRef.current = true;
        showToast({
          title: "Bot inactive",
          description: "The bot hasn't completed a trading cycle in over 20 minutes.",
        });
      } else if (!isInactive) {
        inactivityToastedRef.current = false;
      }
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

  const handleRunCycle = async () => {
    setBusy(true);
    try {
      await runCycleNow();
      await refresh();
      showToast({ title: "Cycle triggered", description: "Manual trading cycle completed." });
    } catch (err) {
      showToast({
        title: "Failed to run cycle",
        description: err.message,
        requestId: err.requestId,
        retry: handleRunCycle,
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

  const lastCycleAt = health?.last_cycle_at ? new Date(health.last_cycle_at).getTime() : null;
  const isInactive = lastCycleAt !== null && Date.now() - lastCycleAt > INACTIVITY_THRESHOLD_MS;

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
        onRunCycle={handleRunCycle}
        theme={theme}
        onToggleTheme={toggleTheme}
        username={username}
        onLogout={handleLogout}
        inactive={isInactive}
        onOpenSettings={() => setSettingsOpen(true)}
      />
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <FadeInSection>
          <Portfolio portfolio={portfolio} onDepositSaved={refresh} />
        </FadeInSection>
        <FadeInSection>
          <Positions positions={positions} />
        </FadeInSection>
        <FadeInSection>
          <Chart />
        </FadeInSection>
        <FadeInSection>
          <DepositChart />
        </FadeInSection>
        <FadeInSection>
          <Trades />
        </FadeInSection>
        <FadeInSection>
          <ActivityLog />
        </FadeInSection>
      </div>
      <SettingsDrawer open={settingsOpen} onClose={() => setSettingsOpen(false)} />
      <Toast />
    </>
  );
}
