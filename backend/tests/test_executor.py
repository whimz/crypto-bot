"""Tests for execute_signal's order-fill bookkeeping.

storage/BinanceClient/telegram are monkeypatched so these stay pure unit tests - no real
network calls, no writes to the actual SQLite file, no Telegram messages sent.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from tests.conftest import make_candles
from trading import executor
from trading.risk import PositionState

SYMBOL = "BTCUSDT"


def _signal(action="BUY", rsi_15m=30.0, rsi_1h=30.0, confidence=80.0):
    from trading.signals import SignalResult

    return SignalResult(action=action, confidence=confidence, reason="test", rsi_15m=rsi_15m, rsi_1h=rsi_1h)


def _patch_dependencies(monkeypatch, position, order):
    monkeypatch.setattr(executor.storage, "get_position", lambda symbol: position)
    monkeypatch.setattr(executor.storage, "get_portfolio", lambda: {"current_deposit_usdt": 1000.0, "initial_deposit_usdt": 1000.0})
    monkeypatch.setattr(executor.storage, "update_position", MagicMock())
    monkeypatch.setattr(executor.storage, "save_trade", MagicMock())
    monkeypatch.setattr(executor.telegram, "notify_trade", MagicMock())
    monkeypatch.setattr(executor.telegram, "notify_error", MagicMock())

    fake_client = MagicMock()
    fake_client.place_market_order.return_value = order
    monkeypatch.setattr(executor, "BinanceClient", MagicMock(return_value=fake_client))


def test_buy_rounds_accumulated_total_invested_to_avoid_binance_precision_error(monkeypatch):
    # Existing position carries 0.1 USDT invested; this fill adds 0.2 more. 0.1 + 0.2 in
    # IEEE754 is 0.30000000000000004 - exactly the noise that later breaks a SELL's
    # quoteOrderQty with Binance's -1111 "too much precision" if it isn't rounded here.
    position = PositionState(symbol=SYMBOL, avg_price=0.1, total_invested=0.1, dca_count=0, peak_price=0.0)
    order = {"executedQty": "2", "cummulativeQuoteQty": "0.2"}  # fill_price=0.1, filled_quote=0.2
    _patch_dependencies(monkeypatch, position, order)

    executor.execute_signal(SYMBOL, _signal("BUY"), make_candles([0.1] * 60))

    updated_position = executor.storage.update_position.call_args[0][0]
    assert updated_position.total_invested == 0.3
    assert len(str(updated_position.total_invested).split(".")[-1]) <= 2
