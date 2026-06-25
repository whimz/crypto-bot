import math

import pytest

from analysis.indicators import calculate_ema, calculate_macd, calculate_rsi, calculate_rsi_series
from tests.conftest import make_candles


def test_calculate_ema_known_values():
    # EMA seeded from the first value (pandas ewm(adjust=False) style), period=3, k=0.5:
    # 1 -> 1.5 -> 2.25 -> 3.125 -> 4.0625
    candles = make_candles([1, 2, 3, 4, 5])
    assert math.isclose(calculate_ema(candles, period=3), 4.0625, rel_tol=1e-9)


def test_calculate_ema_constant_price():
    candles = make_candles([100.0] * 10)
    assert calculate_ema(candles, period=5) == 100.0


def test_calculate_ema_single_candle():
    candles = make_candles([42.0])
    assert calculate_ema(candles, period=1) == 42.0


def test_calculate_ema_not_enough_candles_raises():
    candles = make_candles([1, 2, 3])
    with pytest.raises(ValueError):
        calculate_ema(candles, period=5)


def test_calculate_rsi_all_gains_is_100():
    candles = make_candles(list(range(1, 16)))  # 15 candles, period=14, every step is a gain
    assert calculate_rsi(candles, period=14) == 100.0


def test_calculate_rsi_all_losses_is_0():
    candles = make_candles(list(range(15, 0, -1)))
    assert calculate_rsi(candles, period=14) == 0.0


def test_calculate_rsi_constant_price_is_100():
    # No losses at all (avg_loss == 0) is treated as RSI=100 by this implementation.
    candles = make_candles([50.0] * 15)
    assert calculate_rsi(candles, period=14) == 100.0


def test_calculate_rsi_not_enough_candles_raises():
    candles = make_candles([1, 2, 3])
    with pytest.raises(ValueError):
        calculate_rsi(candles, period=14)


def test_calculate_macd_constant_price_is_zero():
    candles = make_candles([100.0] * 40)
    result = calculate_macd(candles, fast=12, slow=26, signal=9)
    assert result.macd_line == 0.0
    assert result.signal_line == 0.0
    assert result.histogram == 0.0


def test_calculate_macd_histogram_matches_macd_minus_signal():
    candles = make_candles([float(i) for i in range(1, 41)])
    result = calculate_macd(candles, fast=12, slow=26, signal=9)
    assert math.isclose(result.histogram, result.macd_line - result.signal_line, rel_tol=1e-9)


def test_calculate_macd_not_enough_candles_raises():
    candles = make_candles([float(i) for i in range(1, 20)])  # < slow(26) + signal(9)
    with pytest.raises(ValueError):
        calculate_macd(candles, fast=12, slow=26, signal=9)


def test_calculate_rsi_series_aligns_with_candles_and_matches_calculate_rsi():
    candles = make_candles([float(i) for i in range(1, 30)])
    series = calculate_rsi_series(candles, period=14)
    assert len(series) == len(candles) - 14
    assert series[-1] == calculate_rsi(candles, period=14)


def test_calculate_rsi_series_not_enough_candles_raises():
    candles = make_candles([1, 2, 3])
    with pytest.raises(ValueError):
        calculate_rsi_series(candles, period=14)
