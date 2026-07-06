function fmtPnl(v) {
  const sign = v > 0 ? "+" : "";
  return `${sign}$${Number(v).toFixed(2)}`;
}

function pnlClass(v) {
  if (v > 0) return "positive";
  if (v < 0) return "negative";
  return "";
}

export default function PnLSummary({ data, positions }) {
  const unrealized = positions.reduce((sum, p) => sum + (p.pnl_usdt ?? 0), 0);

  if (data === null) {
    return (
      <div className="card">
        <h2>P&L Summary</h2>
        <div className="empty-state">Loading...</div>
      </div>
    );
  }

  const net = data.realized_pnl_usdt + unrealized;

  return (
    <div className="card">
      <h2>P&L Summary</h2>
      <div className="position-row">
        <span>Realized</span>
        <span className={pnlClass(data.realized_pnl_usdt)}>{fmtPnl(data.realized_pnl_usdt)}</span>
      </div>
      <div className="position-row">
        <span>Unrealized</span>
        <span className={pnlClass(unrealized)}>{fmtPnl(unrealized)}</span>
      </div>
      <div className="position-row pnl-net-row">
        <span>Net P&L</span>
        <span className={pnlClass(net)}>{fmtPnl(net)}</span>
      </div>
      <div className="pnl-divider" />
      <div className="position-row">
        <span>Win Rate</span>
        <span>{data.win_rate_pct !== null ? `${data.win_rate_pct}%` : "—"}</span>
      </div>
      <div className="position-row">
        <span>Wins / Losses</span>
        <span>
          <span className="positive">{data.winning_trades}</span>
          {" / "}
          <span className="negative">{data.losing_trades}</span>
        </span>
      </div>
    </div>
  );
}
