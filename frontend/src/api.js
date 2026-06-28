// In dev, BASE_URL stays "/api" so requests go through vite's proxy (vite.config.js),
// which strips the "/api" prefix before forwarding to the backend. In production there's
// no dev server/proxy, so BASE_URL must point directly at the deployed backend.
const BASE_URL = import.meta.env.VITE_API_URL || "/api";
const TOKEN_STORAGE_KEY = "auth_token";

let unauthorizedHandler = () => {};

export function setUnauthorizedHandler(handler) {
  unauthorizedHandler = handler;
}

export function getToken() {
  return localStorage.getItem(TOKEN_STORAGE_KEY);
}

export function setToken(token) {
  localStorage.setItem(TOKEN_STORAGE_KEY, token);
}

export function clearToken() {
  localStorage.removeItem(TOKEN_STORAGE_KEY);
}

function generateRequestId() {
  return Math.random().toString(36).slice(2, 10);
}

// Every thrown error carries a requestId so the UI's Toast component can show it for
// support/debugging purposes, even though the backend doesn't issue one itself.
function requestError(message, requestId) {
  const err = new Error(message);
  err.requestId = requestId;
  return err;
}

async function request(path, options = {}, { auth = true } = {}) {
  const requestId = generateRequestId();
  const headers = { ...(options.headers || {}) };
  if (auth) {
    const token = getToken();
    if (token) headers.Authorization = `Bearer ${token}`;
  }

  let response;
  try {
    response = await fetch(`${BASE_URL}${path}`, { ...options, headers });
  } catch (err) {
    throw requestError(`Network error calling ${path}: ${err.message}`, requestId);
  }

  if (response.status === 401) {
    clearToken();
    unauthorizedHandler();
    throw requestError("Not authenticated", requestId);
  }
  if (!response.ok) {
    const detail = await response.json().catch(() => null);
    const message = detail?.detail || `${path} failed: ${response.status} ${response.statusText}`;
    throw requestError(message, requestId);
  }
  return response.json();
}

export async function login(username, password) {
  const data = await request(
    "/auth/login",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    },
    { auth: false }
  );
  setToken(data.access_token);
  return data;
}

export function getCurrentUser() {
  return request("/auth/me");
}

export function logout() {
  clearToken();
}

export function getHealth() {
  return request("/health");
}

export function getPortfolio() {
  return request("/portfolio");
}

export function getTrades(symbol, limit = 50) {
  const params = new URLSearchParams({ limit: String(limit) });
  if (symbol) params.set("symbol", symbol);
  return request(`/trades?${params.toString()}`);
}

export function getLogs(symbol, limit = 100, offset = 0, dateFrom, dateTo) {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  if (symbol) params.set("symbol", symbol);
  if (dateFrom) params.set("date_from", dateFrom);
  if (dateTo) params.set("date_to", dateTo);
  return request(`/logs?${params.toString()}`);
}

export function getChart(symbol, interval = "15m", limit = 100) {
  const params = new URLSearchParams({ symbol, interval, limit: String(limit) });
  return request(`/chart?${params.toString()}`);
}

export function startBot() {
  return request("/bot/start", { method: "POST" });
}

export function stopBot() {
  return request("/bot/stop", { method: "POST" });
}

export function runCycleNow() {
  return request("/bot/run-cycle", { method: "POST" });
}

export function getSettings() {
  return request("/settings");
}

export function updateSettings(updates) {
  return request("/settings", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(updates),
  });
}

export function initPortfolio(amount) {
  return request("/portfolio/init", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ amount }),
  });
}

export function getPortfolioHistory(days = 7) {
  return request(`/portfolio/history?days=${days}`);
}

export async function exportTradesCsv(symbol, dateFrom, dateTo) {
  const params = new URLSearchParams();
  if (symbol) params.set("symbol", symbol);
  if (dateFrom) params.set("date_from", dateFrom);
  if (dateTo) params.set("date_to", dateTo);

  const token = getToken();
  const headers = token ? { Authorization: `Bearer ${token}` } : {};
  const response = await fetch(`${BASE_URL}/trades/export?${params.toString()}`, { headers });
  if (!response.ok) {
    throw requestError(`Export failed: ${response.status} ${response.statusText}`, generateRequestId());
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "trades.csv";
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

const QUOTE_ASSETS = ["USDT", "BUSD", "USDC"];

export function formatSymbol(symbol) {
  if (!symbol) return "";
  const quote = QUOTE_ASSETS.find((q) => symbol.endsWith(q) && symbol.length > q.length);
  if (!quote) return symbol;
  return `${symbol.slice(0, -quote.length)} / ${quote}`;
}
