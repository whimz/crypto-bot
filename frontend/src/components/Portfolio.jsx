import { useState } from "react";
import { initPortfolio } from "../api.js";
import { showToast } from "../toastBus.js";

function formatUsdt(value) {
  if (value === undefined || value === null) return "—";
  return `$${Number(value).toFixed(2)}`;
}

function SetDepositModal({ onClose, onSaved }) {
  const [amount, setAmount] = useState("");
  const [saving, setSaving] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    const value = Number(amount);
    if (!value || value <= 0) return;

    setSaving(true);
    try {
      await initPortfolio(value);
      showToast({ title: "Deposit updated", description: `Deposit set to $${value.toFixed(2)}.` });
      onSaved?.();
      onClose();
    } catch (err) {
      showToast({
        title: "Failed to set deposit",
        description: err.message,
        requestId: err.requestId,
      });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <form className="modal-card" onClick={(e) => e.stopPropagation()} onSubmit={handleSubmit}>
        <h3>Set Deposit</h3>
        <label className="modal-field">
          Amount (USDT)
          <input
            type="number"
            min="0"
            step="0.01"
            autoFocus
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
          />
        </label>
        <div className="modal-actions">
          <button type="button" onClick={onClose} disabled={saving}>
            Cancel
          </button>
          <button type="submit" className="primary" disabled={saving}>
            {saving ? "Saving..." : "Save"}
          </button>
        </div>
      </form>
    </div>
  );
}

export default function Portfolio({ portfolio, onDepositSaved }) {
  const drawdown = portfolio?.drawdown_pct ?? 0;
  const [modalOpen, setModalOpen] = useState(false);

  return (
    <div className="card">
      <div className="card-header-row">
        <h2>Portfolio</h2>
        <button onClick={() => setModalOpen(true)}>Set Deposit</button>
      </div>
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
      {modalOpen && (
        <SetDepositModal onClose={() => setModalOpen(false)} onSaved={onDepositSaved} />
      )}
    </div>
  );
}
