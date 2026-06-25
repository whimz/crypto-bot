function formatUsdt(value) {
  if (value === undefined || value === null) return "—";
  return `$${Number(value).toFixed(2)}`;
}

export default function Portfolio({ portfolio }) {
  const drawdown = portfolio?.drawdown_pct ?? 0;

  return (
    <div className="card">
      <h2>Portfolio</h2>
      <div className="stat-grid">
        <div>
          <div className="stat-label">Initial Deposit</div>
          <div className="stat-value">{formatUsdt(portfolio?.initial_deposit_usdt)}</div>
        </div>
        <div>
          <div className="stat-label">Current Deposit</div>
          <div className="stat-value">{formatUsdt(portfolio?.current_deposit_usdt)}</div>
        </div>
        <div>
          <div className="stat-label">Drawdown</div>
          <div className={`stat-value ${drawdown > 0 ? "negative" : ""}`}>
            {drawdown > 0 ? "-" : ""}{Math.abs(drawdown).toFixed(2)}%
          </div>
        </div>
      </div>
    </div>
  );
}
