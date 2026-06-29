import { useEffect, useState } from "react";
import { runBacktest } from "../api.js";
import { showToast } from "../toastBus.js";

function formatUsdt(value) {
  return `${value >= 0 ? "+" : ""}$${Number(value).toFixed(2)}`;
}

function formatWinRate(value) {
  return value === null || value === undefined ? "—" : `${Number(value).toFixed(1)}%`;
}

export default function BacktestModal({ onClose }) {
  const [loading, setLoading] = useState(true);
  const [result, setResult] = useState(null);

  const load = async () => {
    setLoading(true);
    try {
      const data = await runBacktest();
      setResult(data);
    } catch (err) {
      showToast({
        title: "Failed to run backtest",
        description: err.message,
        requestId: err.requestId,
        retry: load,
      });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-card modal-card-wide" onClick={(e) => e.stopPropagation()}>
        <div className="card-header-row">
          <h3>Backtest: Take Profit / EMA filter</h3>
          <button onClick={onClose}>Close</button>
        </div>

        {loading ? (
          <div className="empty-state">Running backtest... this can take a while</div>
        ) : !result ? (
          <div className="empty-state">No data</div>
        ) : (
          <>
            <p className="log-reason">
              Цель: ~${result.target_weekly_return_usdt.toFixed(0)}/неделю на $100 депозите. Период симуляции:{" "}
              {result.simulation_days} дней.
            </p>
            <table>
              <thead>
                <tr>
                  <th>Config</th>
                  <th>Trades</th>
                  <th>Win %</th>
                  <th>Avg/wk</th>
                  <th>Median/wk</th>
                  <th>Worst/wk</th>
                  <th>Hint</th>
                </tr>
              </thead>
              <tbody>
                {result.rows.map((row) => (
                  <tr key={row.label}>
                    <td>{row.label}</td>
                    <td>{row.trade_count}</td>
                    <td>{formatWinRate(row.win_rate_pct)}</td>
                    <td>{formatUsdt(row.avg_weekly_return_usdt)}</td>
                    <td>{formatUsdt(row.median_weekly_return_usdt)}</td>
                    <td>{formatUsdt(row.worst_weekly_return_usdt)}</td>
                    <td className="log-reason">{row.hint}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
      </div>
    </div>
  );
}
