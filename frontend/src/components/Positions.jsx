import { formatSymbol } from "../api.js";

function formatUsdt(value) {
  return `$${Number(value).toFixed(2)}`;
}

export default function Positions({ positions }) {
  return (
    <div className="card">
      <h2>Open Positions</h2>
      {positions.length === 0 ? (
        <div className="empty-state">No open positions</div>
      ) : (
        <div className="position-grid">
          {positions.map((position) => (
            <div className="position-card" key={position.symbol}>
              <div className="symbol">{formatSymbol(position.symbol)}</div>
              <div className="position-row">
                <span>Avg Price</span>
                <span>{formatUsdt(position.avg_price)}</span>
              </div>
              <div className="position-row">
                <span>Invested</span>
                <span>{formatUsdt(position.total_invested)}</span>
              </div>
              <div className="position-row">
                <span>DCA Count</span>
                <span>{position.dca_count}</span>
              </div>
              <div className="position-row">
                <span>Peak Price</span>
                <span>{formatUsdt(position.peak_price)}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
