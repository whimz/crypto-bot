"""Tests for get_signal's BUY/SELL/HOLD decision logic.

The indicator functions are monkeypatched so each test can dial in exact RSI/EMA/MACD
values without having to engineer candle series that happen to produce them. The two
timeframe candle lists are made distinguishable by length, since that's the only thing
the fakes can key off of.
"""

from __future__ import annotations

import trading.signals as signals
from analysis.indicators import MACDResult
from tests.conftest import make_candles

CANDLES_15M = make_candles([100.0])  # len == 1
CANDLES_1H = make_candles([100.0, 100.0])  # len == 2


def _patch_indicators(monkeypatch, rsi_by_len, ema_by_len, macd_by_len):
    def fake_rsi(candles, period=14):
        return rsi_by_len[len(candles)]

    def fake_ema(candles, period=50):
        return ema_by_len[len(candles)]

    def fake_macd(candles, fast=12, slow=26, signal=9):
        return macd_by_len[len(candles)]

    monkeypatch.setattr(signals, "calculate_rsi", fake_rsi)
    monkeypatch.setattr(signals, "calculate_ema", fake_ema)
    monkeypatch.setattr(signals, "calculate_macd", fake_macd)


def test_buy_when_both_timeframes_oversold_and_price_above_ema(monkeypatch):
    _patch_indicators(
        monkeypatch,
        rsi_by_len={1: 30.0, 2: 32.0},
        ema_by_len={1: 90.0, 2: 95.0},
        macd_by_len={1: MACDResult(1.0, 0.5, 0.5), 2: MACDResult(1.0, 0.5, 0.5)},
    )
    result = signals.get_signal(CANDLES_15M, CANDLES_1H)
    assert result.action == "BUY"
    assert 60.0 <= result.confidence <= 100.0
    assert result.rsi_15m == 30.0
    assert result.rsi_1h == 32.0


def test_sell_when_both_timeframes_overbought_and_price_below_ema(monkeypatch):
    _patch_indicators(
        monkeypatch,
        rsi_by_len={1: 70.0, 2: 72.0},
        ema_by_len={1: 110.0, 2: 115.0},
        macd_by_len={1: MACDResult(-1.0, -0.5, -0.5), 2: MACDResult(-1.0, -0.5, -0.5)},
    )
    result = signals.get_signal(CANDLES_15M, CANDLES_1H)
    assert result.action == "SELL"
    assert 60.0 <= result.confidence <= 100.0


def test_hold_when_only_one_timeframe_is_oversold(monkeypatch):
    _patch_indicators(
        monkeypatch,
        rsi_by_len={1: 30.0, 2: 50.0},  # 1h RSI not oversold
        ema_by_len={1: 90.0, 2: 90.0},
        macd_by_len={1: MACDResult(0.0, 0.0, 0.0), 2: MACDResult(0.0, 0.0, 0.0)},
    )
    result = signals.get_signal(CANDLES_15M, CANDLES_1H)
    assert result.action == "HOLD"
    assert result.confidence == 0.0


def test_hold_when_oversold_but_price_below_ema(monkeypatch):
    _patch_indicators(
        monkeypatch,
        rsi_by_len={1: 20.0, 2: 25.0},  # both oversold...
        ema_by_len={1: 200.0, 2: 200.0},  # ...but price (100) is below EMA50
        macd_by_len={1: MACDResult(0.0, 0.0, 0.0), 2: MACDResult(0.0, 0.0, 0.0)},
    )
    result = signals.get_signal(CANDLES_15M, CANDLES_1H)
    assert result.action == "HOLD"


def test_hold_when_only_one_timeframe_is_overbought(monkeypatch):
    _patch_indicators(
        monkeypatch,
        rsi_by_len={1: 70.0, 2: 50.0},  # 1h RSI not overbought
        ema_by_len={1: 110.0, 2: 110.0},
        macd_by_len={1: MACDResult(0.0, 0.0, 0.0), 2: MACDResult(0.0, 0.0, 0.0)},
    )
    result = signals.get_signal(CANDLES_15M, CANDLES_1H)
    assert result.action == "HOLD"


def test_buy_ignores_ema_when_trend_filter_disabled(monkeypatch):
    monkeypatch.setattr(signals, "REQUIRE_EMA_TREND", False)
    _patch_indicators(
        monkeypatch,
        rsi_by_len={1: 20.0, 2: 25.0},  # both oversold...
        ema_by_len={1: 200.0, 2: 200.0},  # ...but price (100) is below EMA50
        macd_by_len={1: MACDResult(0.0, 0.0, 0.0), 2: MACDResult(0.0, 0.0, 0.0)},
    )
    result = signals.get_signal(CANDLES_15M, CANDLES_1H)
    assert result.action == "BUY"
    assert "EMA trend filter disabled" in result.reason


def test_sell_ignores_ema_when_trend_filter_disabled(monkeypatch):
    monkeypatch.setattr(signals, "REQUIRE_EMA_TREND", False)
    _patch_indicators(
        monkeypatch,
        rsi_by_len={1: 70.0, 2: 75.0},  # both overbought...
        ema_by_len={1: 50.0, 2: 50.0},  # ...but price (100) is above EMA50
        macd_by_len={1: MACDResult(0.0, 0.0, 0.0), 2: MACDResult(0.0, 0.0, 0.0)},
    )
    result = signals.get_signal(CANDLES_15M, CANDLES_1H)
    assert result.action == "SELL"
    assert "EMA trend filter disabled" in result.reason


def test_hold_when_trend_filter_disabled_but_rsi_not_aligned(monkeypatch):
    monkeypatch.setattr(signals, "REQUIRE_EMA_TREND", False)
    _patch_indicators(
        monkeypatch,
        rsi_by_len={1: 50.0, 2: 50.0},
        ema_by_len={1: 200.0, 2: 200.0},
        macd_by_len={1: MACDResult(0.0, 0.0, 0.0), 2: MACDResult(0.0, 0.0, 0.0)},
    )
    result = signals.get_signal(CANDLES_15M, CANDLES_1H)
    assert result.action == "HOLD"


def test_hold_on_neutral_rsi(monkeypatch):
    _patch_indicators(
        monkeypatch,
        rsi_by_len={1: 50.0, 2: 50.0},
        ema_by_len={1: 100.0, 2: 100.0},
        macd_by_len={1: MACDResult(0.0, 0.0, 0.0), 2: MACDResult(0.0, 0.0, 0.0)},
    )
    result = signals.get_signal(CANDLES_15M, CANDLES_1H)
    assert result.action == "HOLD"
    assert result.confidence == 0.0
    assert "No aligned signal" in result.reason
