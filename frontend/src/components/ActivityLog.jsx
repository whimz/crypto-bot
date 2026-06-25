import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { formatSymbol, getLogs } from "../api.js";
import { showToast } from "../toastBus.js";

const SYMBOLS = ["BTCUSDT", "ETHUSDT", "LTCUSDT"];
const ACTIONS = ["All", "BUY", "SELL", "HOLD", "ERROR"];
const POLL_INTERVAL_MS = 30_000;

function formatTimestamp(value) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

export default function ActivityLog() {
  const [symbol, setSymbol] = useState("");
  const [action, setAction] = useState("All");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [logs, setLogs] = useState([]);
  // null until the first successful load, so we toast only errors that appear *after*
  // we've started watching - not the whole backlog already in bot_logs.
  const seenErrorIdsRef = useRef(null);

  const refresh = useCallback(async () => {
    try {
      const data = await getLogs(symbol || undefined, 100);
      setLogs(data);

      const errorEntries = data.filter((entry) => entry.action === "ERROR");
      if (seenErrorIdsRef.current === null) {
        seenErrorIdsRef.current = new Set(errorEntries.map((entry) => entry.id));
      } else {
        for (const entry of errorEntries) {
          if (seenErrorIdsRef.current.has(entry.id)) continue;
          seenErrorIdsRef.current.add(entry.id);
          showToast({
            title: `Trading Error: ${formatSymbol(entry.symbol)}`,
            description: entry.reason,
            requestId: String(entry.id),
          });
        }
      }
    } catch (err) {
      showToast({
        title: "Failed to load activity log",
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

  const filteredLogs = useMemo(() => {
    // Parse as local time (date-only strings parse as UTC in JS), to match the user's
    // selected calendar day and the local-time rendering in formatTimestamp().
    const fromTime = dateFrom ? new Date(`${dateFrom}T00:00:00`).getTime() : null;
    const toTime = dateTo ? new Date(`${dateTo}T23:59:59.999`).getTime() : null;
    return logs.filter((entry) => {
      if (action !== "All" && entry.action !== action) return false;
      const entryTime = new Date(entry.timestamp).getTime();
      if (fromTime !== null && entryTime < fromTime) return false;
      if (toTime !== null && entryTime > toTime) return false;
      return true;
    });
  }, [logs, action, dateFrom, dateTo]);

  return (
    <div className="card">
      <h2>Activity Log</h2>
      <div className="trades-filter">
        <select value={symbol} onChange={(e) => setSymbol(e.target.value)}>
          <option value="">All symbols</option>
          {SYMBOLS.map((s) => (
            <option key={s} value={s}>
              {formatSymbol(s)}
            </option>
          ))}
        </select>
        <select value={action} onChange={(e) => setAction(e.target.value)}>
          {ACTIONS.map((a) => (
            <option key={a} value={a}>
              {a}
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
      {filteredLogs.length === 0 ? (
        <div className="empty-state">No activity yet</div>
      ) : (
        <div className="activity-log-scroll">
          <table className="activity-log-table">
            <thead>
              <tr>
                <th>Time</th>
                <th>Symbol</th>
                <th>Action</th>
                <th>Confidence</th>
                <th>Reason</th>
              </tr>
            </thead>
            <tbody>
              {filteredLogs.map((entry) => (
                <tr key={entry.id}>
                  <td>{formatTimestamp(entry.timestamp)}</td>
                  <td>{formatSymbol(entry.symbol)}</td>
                  <td>
                    <span className={`action-tag ${entry.action.toLowerCase()}`}>{entry.action}</span>
                  </td>
                  <td>{Number(entry.confidence).toFixed(1)}%</td>
                  <td className="log-reason">{entry.reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
