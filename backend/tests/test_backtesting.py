"""Tests for trading/backtesting.py's simulation bookkeeping.

get_signal is monkeypatched to a small scripted sequence (driven by a synthetic price at
each step) so these stay deterministic, fast unit tests - no real Binance calls, no
dependency on actual RSI/EMA/MACD math (that's signals.py's own test suite's job).
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

import trading.risk as risk
import trading.signals as signals
from data.binance import Candle
from trading import backtesting as bt
from trading.signals import SignalResult

SYMBOL = "BTCUSDT"
STEP_MS = 15 * 60 * 1000
BASE_MS = int(datetime(2024, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)  # a Monday 00:00 UTC
FILLER_PRICE = 90.0
BUY_PRICE = 100.0
SELL_PRICE = 110.0
BUY_IDX = bt.LOOKBACK_CANDLES  # first index with a full lookback is LOOKBACK_CANDLES - 1
SELL_IDX = BUY_IDX + 1


def _candle(open_time_ms: int, close: float) -> Candle:
    return Candle(
        open_time=open_time_ms, open=close, high=close, low=close, close=close,
        volume=1.0, close_time=open_time_ms + 1, quote_volume=1.0, trades=1,
    )


def _build_history() -> dict[str, bt._SymbolHistory]:
    candles_15m = []
    for i in range(SELL_IDX + 1):
        price = FILLER_PRICE
        if i == BUY_IDX:
            price = BUY_PRICE
        elif i == SELL_IDX:
            price = SELL_PRICE
        candles_15m.append(_candle(BASE_MS + i * STEP_MS, price))

    # 1h candles only need to satisfy the LOOKBACK_CANDLES-length gate in _aligned_1h_window;
    # their content is irrelevant since get_signal is mocked.
    candles_1h = [_candle(i, 100.0) for i in range(bt.LOOKBACK_CANDLES)]

    return {
        SYMBOL: bt._SymbolHistory(
            candles_15m=candles_15m,
            open_times_15m=[c.open_time for c in candles_15m],
            candles_1h=candles_1h,
            close_times_1h=[c.close_time for c in candles_1h],
        )
    }


def _fake_get_signal(window_15m, _window_1h) -> SignalResult:
    close = window_15m[-1].close
    if close == BUY_PRICE:
        return SignalResult(action="BUY", confidence=80.0, reason="test buy", rsi_15m=30.0, rsi_1h=30.0)
    if close == SELL_PRICE:
        return SignalResult(action="SELL", confidence=80.0, reason="test sell", rsi_15m=70.0, rsi_1h=70.0)
    return SignalResult(action="HOLD", confidence=0.0, reason="test hold", rsi_15m=50.0, rsi_1h=50.0)


@pytest.fixture(autouse=True)
def _reset_globals(monkeypatch):
    monkeypatch.setattr(bt, "get_signal", _fake_get_signal)


def test_simulate_records_a_buy_then_sell_and_tracks_equity():
    config = bt.SimulationConfig(take_profit_pct=0.0, require_ema_trend=True, label="test")
    history = _build_history()
    cutoff_ms = BASE_MS  # include every synthetic candle

    result = bt._simulate(config, history, cutoff_ms)

    assert [t.action for t in result.trades] == ["BUY", "SELL"]
    buy, sell = result.trades
    assert buy.price == BUY_PRICE
    assert buy.amount_usdt == 10.0  # medium-volatility band (avg RSI 30) -> 10% of $100 deposit
    assert sell.price == SELL_PRICE
    assert sell.realized_pnl_usdt == 1.0  # qty 0.1 * (110 - 100)
    assert result.final_equity_usdt == 101.0


def test_simulate_aggregates_into_a_single_week_when_span_is_short():
    config = bt.SimulationConfig(take_profit_pct=0.0, require_ema_trend=True, label="test")
    history = _build_history()

    result = bt._simulate(config, history, cutoff_ms=BASE_MS)

    assert len(result.weekly_returns) == 1
    assert result.weekly_returns[0].return_usdt == 1.0


def test_summarize_computes_win_rate_and_hint_from_trades():
    config = bt.SimulationConfig(take_profit_pct=0.0, require_ema_trend=True, label="test")
    history = _build_history()
    result = bt._simulate(config, history, cutoff_ms=BASE_MS)

    row = bt.summarize(result)

    assert row.trade_count == 1  # one completed round trip (one SELL)
    assert row.win_rate_pct == 100.0
    assert row.avg_weekly_return_usdt == 1.0
    assert "цел" in row.hint or "Достиг" in row.hint or row.hint  # some non-empty hint either way


def test_summarize_reports_no_trades_hint_when_nothing_happened():
    config = bt.SimulationConfig(take_profit_pct=0.0, require_ema_trend=True, label="test")
    result = bt.SimulationResult(config=config, initial_deposit_usdt=100.0, final_equity_usdt=100.0)

    row = bt.summarize(result)

    assert row.trade_count == 0
    assert row.win_rate_pct is None
    assert "строг" in row.hint  # "условия слишком строгие"


def test_run_comparison_restores_globals_after_each_config(monkeypatch):
    original_ema = signals.REQUIRE_EMA_TREND
    original_tp = risk.TAKE_PROFIT_PCT
    history = _build_history()
    configs = [
        bt.SimulationConfig(take_profit_pct=0.03, require_ema_trend=False, label="a"),
        bt.SimulationConfig(take_profit_pct=0.05, require_ema_trend=True, label="b"),
    ]

    rows = bt.run_comparison(configs=configs, history=history)

    assert len(rows) == 2
    assert signals.REQUIRE_EMA_TREND == original_ema
    assert risk.TAKE_PROFIT_PCT == original_tp


def test_run_comparison_restores_globals_even_if_simulation_raises(monkeypatch):
    original_ema = signals.REQUIRE_EMA_TREND
    original_tp = risk.TAKE_PROFIT_PCT
    monkeypatch.setattr(bt, "_simulate", MagicMock(side_effect=RuntimeError("boom")))

    with pytest.raises(RuntimeError):
        bt.run_comparison(configs=[bt.SimulationConfig(0.03, False, "a")], history=_build_history())

    assert signals.REQUIRE_EMA_TREND == original_ema
    assert risk.TAKE_PROFIT_PCT == original_tp
