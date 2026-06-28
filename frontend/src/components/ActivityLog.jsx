import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { formatSymbol, getLogs } from "../api.js";
import { showToast } from "../toastBus.js";

const SYMBOLS = ["BTCUSDT", "ETHUSDT", "LTCUSDT"];
const ACTIONS = ["All", "BUY", "SELL", "HOLD", "ERROR"];
const POLL_INTERVAL_MS = 30_000;
const PAGE_SIZE = 25;
const SCROLL_LOAD_THRESHOLD_PX = 48;

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
  const [hasMore, setHasMore] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  // null until the first successful load, so we toast only errors that appear *after*
  // we've started watching - not the whole backlog already in bot_logs.
  const seenErrorIdsRef = useRef(null);
  const scrollRef = useRef(null);

  // Resolved once per dateFrom/dateTo change into absolute UTC instants for the *browser's*
  // local calendar day - the date-only input value has no "T" time portion, so appending
  // T00:00:00/T23:59:59.999 (no zone suffix) makes JS parse it as local time, matching what
  // the user actually meant by "today"/"yesterday".
  const dateFromIso = useMemo(
    () => (dateFrom ? new Date(`${dateFrom}T00:00:00`).toISOString() : undefined),
    [dateFrom]
  );
  const dateToIso = useMemo(
    () => (dateTo ? new Date(`${dateTo}T23:59:59.999`).toISOString() : undefined),
    [dateTo]
  );

  const refresh = useCallback(async () => {
    try {
      const data = await getLogs(symbol || undefined, PAGE_SIZE, 0, dateFromIso, dateToIso);
      setLogs(data);
      setHasMore(data.length === PAGE_SIZE);

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
  }, [symbol, dateFromIso, dateToIso]);

  const loadMore = useCallback(async () => {
    if (loadingMore || !hasMore) return;
    setLoadingMore(true);
    try {
      const data = await getLogs(symbol || undefined, PAGE_SIZE, logs.length, dateFromIso, dateToIso);
      setLogs((current) => [...current, ...data]);
      setHasMore(data.length === PAGE_SIZE);
    } catch (err) {
      showToast({
        title: "Failed to load more activity",
        description: err.message,
        requestId: err.requestId,
        retry: loadMore,
      });
    } finally {
      setLoadingMore(false);
    }
  }, [symbol, dateFromIso, dateToIso, logs.length, loadingMore, hasMore]);

  useEffect(() => {
    refresh();
    const interval = setInterval(refresh, POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [refresh]);

  const handleScroll = () => {
    const el = scrollRef.current;
    if (!el) return;
    if (el.scrollHeight - el.scrollTop - el.clientHeight < SCROLL_LOAD_THRESHOLD_PX) {
      loadMore();
    }
  };

  // Date range is now filtered on the backend (across the full bot_logs history, not just
  // the loaded page); only the action filter still applies client-side to what's loaded.
  const filteredLogs = useMemo(() => {
    if (action === "All") return logs;
    return logs.filter((entry) => entry.action === action);
  }, [logs, action]);

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
        <div className="activity-log-scroll" ref={scrollRef} onScroll={handleScroll}>
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
          {loadingMore && <div className="empty-state">Loading...</div>}
        </div>
      )}
    </div>
  );
}
