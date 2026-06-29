from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

import scheduler
from data.binance import Candle
from trading.risk import PositionState
from trading.signals import SignalResult


def _fake_candle(close: float = 100.0) -> Candle:
    return Candle(
        open_time=0, open=close, high=close, low=close, close=close,
        volume=1.0, close_time=1, quote_volume=1.0, trades=1,
    )


@pytest.fixture(autouse=True)
def reset_scheduler_state(monkeypatch):
    """Each test gets a clean slate for the module-level state _check_inactivity reads/writes."""
    monkeypatch.setattr(scheduler, "_last_cycle_at", None)
    monkeypatch.setattr(scheduler, "_last_inactivity_alert_at", None)
    monkeypatch.setattr(scheduler, "_scheduler", None)
    monkeypatch.setattr(scheduler.telegram, "notify_inactive", MagicMock())
    monkeypatch.setattr(scheduler.telegram, "notify_error", MagicMock())


def test_check_inactivity_does_nothing_when_cycle_is_fresh():
    scheduler._last_cycle_at = datetime.now(timezone.utc)
    scheduler._check_inactivity()
    scheduler.telegram.notify_inactive.assert_not_called()
    scheduler.telegram.notify_error.assert_not_called()


def test_check_inactivity_does_nothing_without_a_baseline_cycle():
    scheduler._check_inactivity()  # _last_cycle_at is None
    scheduler.telegram.notify_inactive.assert_not_called()


def test_check_inactivity_recovers_stalled_run_cycle_job():
    scheduler._last_cycle_at = datetime.now(timezone.utc) - timedelta(minutes=scheduler.INACTIVITY_THRESHOLD_MINUTES + 1)
    mock_scheduler = MagicMock()
    scheduler._scheduler = mock_scheduler

    scheduler._check_inactivity()

    scheduler.telegram.notify_inactive.assert_called_once()
    mock_scheduler.add_job.assert_called_once()
    args, kwargs = mock_scheduler.add_job.call_args
    assert args[0] is scheduler.run_cycle
    assert kwargs["id"] == "run_cycle"
    assert kwargs["replace_existing"] is True
    scheduler.telegram.notify_error.assert_called_once()


def test_check_inactivity_recovery_is_a_noop_without_a_scheduler_instance():
    scheduler._last_cycle_at = datetime.now(timezone.utc) - timedelta(minutes=scheduler.INACTIVITY_THRESHOLD_MINUTES + 1)
    scheduler._scheduler = None

    scheduler._check_inactivity()  # must not raise

    scheduler.telegram.notify_inactive.assert_called_once()
    scheduler.telegram.notify_error.assert_not_called()


def test_check_inactivity_respects_cooldown_between_recovery_attempts():
    scheduler._last_cycle_at = datetime.now(timezone.utc) - timedelta(minutes=scheduler.INACTIVITY_THRESHOLD_MINUTES + 1)
    mock_scheduler = MagicMock()
    scheduler._scheduler = mock_scheduler

    scheduler._check_inactivity()
    scheduler._check_inactivity()  # still within INACTIVITY_ALERT_COOLDOWN_MINUTES

    scheduler.telegram.notify_inactive.assert_called_once()
    mock_scheduler.add_job.assert_called_once()


def test_run_cycle_snapshots_live_equity_not_a_stale_stored_value(monkeypatch):
    """Regression guard for the equity work: the deposit-history snapshot must come from
    calculate_equity() (free cash + live position value), not the old stale
    portfolio.current_deposit_usdt column that "Set Deposit" never updates after a trade."""
    monkeypatch.setattr(scheduler, "_running", True)
    monkeypatch.setattr(scheduler, "SYMBOLS", ["BTCUSDT"])
    monkeypatch.setattr(scheduler, "get_settings", lambda: MagicMock(debug_logging=False))

    fake_client = MagicMock()
    fake_client.get_klines.return_value = [_fake_candle()]
    monkeypatch.setattr(scheduler, "BinanceClient", MagicMock(return_value=fake_client))
    monkeypatch.setattr(
        scheduler,
        "get_signal",
        lambda *_args: SignalResult(action="HOLD", confidence=0.0, reason="r", rsi_15m=50.0, rsi_1h=50.0),
    )
    monkeypatch.setattr(scheduler.storage, "get_position", lambda symbol: None)

    fake_equity = MagicMock(equity_usdt=1234.56)
    mock_calculate_equity = MagicMock(return_value=fake_equity)
    monkeypatch.setattr(scheduler, "calculate_equity", mock_calculate_equity)
    mock_save_snapshot = MagicMock()
    monkeypatch.setattr(scheduler.storage, "save_portfolio_snapshot", mock_save_snapshot)

    scheduler.run_cycle()

    mock_calculate_equity.assert_called_once_with(fake_client)
    mock_save_snapshot.assert_called_once_with(1234.56)


def test_close_all_positions_rounds_quote_order_qty(monkeypatch):
    """/closeall sends total_invested straight to Binance, bypassing risk.py's SELL
    rounding - it needs its own guard against the same -1111 "too much precision" error."""
    monkeypatch.setattr(scheduler, "SYMBOLS", ["BTCUSDT"])
    position = PositionState(symbol="BTCUSDT", avg_price=100.0, total_invested=0.1 + 0.2, dca_count=1, peak_price=100.0)
    monkeypatch.setattr(scheduler.storage, "get_position", lambda symbol: position)
    monkeypatch.setattr(scheduler.storage, "update_position", MagicMock())
    monkeypatch.setattr(scheduler.telegram, "send_message", MagicMock())

    fake_client = MagicMock()
    monkeypatch.setattr(scheduler, "BinanceClient", MagicMock(return_value=fake_client))

    scheduler._close_all_positions()

    fake_client.place_market_order.assert_called_once_with(symbol="BTCUSDT", side="SELL", quote_order_qty=0.3)
