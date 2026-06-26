import { useCallback, useEffect, useState } from "react";
import { exportTradesCsv, formatSymbol, getTrades } from "../api.js";
import { showToast } from "../toastBus.js";

const SYMBOLS = ["BTCUSDT", "ETHUSDT", "LTCUSDT"];
const POLL_INTERVAL_MS = 30_000;

function formatUsdt(value) {
  return `$${Number(value).toFixed(2)}`;
}

function formatTimestamp(value) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

export default function Trades() {
  const [symbol, setSymbol] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [trades, setTrades] = useState([]);
  const [exporting, setExporting] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const data = await getTrades(symbol || undefined, 50);
      setTrades(data);
    } catch (err) {
      showToast({
        title: "Failed to load trade history",
        description: err.message,
        requestId: err.requestId,
        retry: refresh,
      });
    }
  }, [symbol]);

  useEffect(() => {
    refresh();
    const interval = setInterval(refresh, POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [refresh]);

  const filteredTrades = trades.filter((trade) => {
    if (dateFrom && new Date(trade.timestamp).getTime() < new Date(`${dateFrom}T00:00:00`).getTime()) return false;
    if (dateTo && new Date(trade.timestamp).getTime() > new Date(`${dateTo}T23:59:59.999`).getTime()) return false;
    return true;
  });

  const handleExport = async () => {
    setExporting(true);
    try {
      await exportTradesCsv(symbol || undefined, dateFrom || undefined, dateTo || undefined);
    } catch (err) {
      showToast({
        title: "Failed to export trades",
        description: err.message,
        requestId: err.requestId,
        retry: handleExport,
      });
    } finally {
      setExporting(false);
    }
  };

  return (
    <div className="card">
      <div className="card-header-row">
        <h2>Trade History</h2>
        <button onClick={handleExport} disabled={exporting}>
          {exporting ? "Exporting..." : "Export CSV"}
        </button>
      </div>
      <div className="trades-filter">
        <select value={symbol} onChange={(e) => setSymbol(e.target.value)}>
          <option value="">All symbols</option>
          {SYMBOLS.map((s) => (
            <option key={s} value={s}>
              {formatSymbol(s)}
            </option>
          ))}
        </select>
        <label className="date-filter">
          From
          <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
        </label>
        <label className="date-filter">
          To
          <input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
        </label>
      </div>
      {filteredTrades.length === 0 ? (
        <div className="empty-state">No trades yet</div>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Time</th>
              <th>Symbol</th>
              <th>Action</th>
              <th>Price</th>
              <th>Amount</th>
              <th>Confidence</th>
              <th>Reason</th>
            </tr>
          </thead>
          <tbody>
            {filteredTrades.map((trade) => (
              <tr key={trade.id}>
                <td>{formatTimestamp(trade.timestamp)}</td>
                <td>{formatSymbol(trade.symbol)}</td>
                <td>
                  <span className={`action-tag ${trade.action.toLowerCase()}`}>{trade.action}</span>
                </td>
                <td>{formatUsdt(trade.price)}</td>
                <td>{formatUsdt(trade.amount_usdt)}</td>
                <td>{Number(trade.confidence).toFixed(1)}%</td>
                <td>{trade.reason}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
