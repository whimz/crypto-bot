"""Technical indicators computed over Candle series from data.binance."""

from __future__ import annotations

from dataclasses import dataclass

from data.binance import Candle


@dataclass(frozen=True)
class MACDResult:
    macd_line: float
    signal_line: float
    histogram: float


def _closes(candles: list[Candle]) -> list[float]:
    if not candles:
        raise ValueError("candles must not be empty")
    return [c.close for c in candles]


def _ema_series(values: list[float], period: int) -> list[float]:
    """EMA over the full series, seeded from the first value (pandas ewm(adjust=False) style)."""
    if period < 1:
        raise ValueError("period must be >= 1")
    k = 2 / (period + 1)
    ema = [values[0]]
    for price in values[1:]:
        ema.append(price * k + ema[-1] * (1 - k))
    return ema


def calculate_ema(candles: list[Candle], period: int = 50) -> float:
    """Latest EMA value of the close price over `period`."""
    closes = _closes(candles)
    if len(closes) < period:
        raise ValueError(f"need at least {period} candles, got {len(closes)}")
    return _ema_series(closes, period)[-1]


def _rsi_from_averages(avg_gain: float, avg_loss: float) -> float:
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def _rsi_series_from_closes(closes: list[float], period: int) -> list[float]:
    """RSI (Wilder's smoothing) at every point once enough history exists; result[i] lines
    up with closes[period + i]."""
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [max(d, 0.0) for d in deltas]
    losses = [max(-d, 0.0) for d in deltas]

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    rsi_values = [_rsi_from_averages(avg_gain, avg_loss)]

    for gain, loss in zip(gains[period:], losses[period:]):
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
        rsi_values.append(_rsi_from_averages(avg_gain, avg_loss))

    return rsi_values


def calculate_rsi(candles: list[Candle], period: int = 14) -> float:
    """Latest RSI value (Wilder's smoothing) of the close price over `period`."""
    closes = _closes(candles)
    if len(closes) < period + 1:
        raise ValueError(f"need at least {period + 1} candles, got {len(closes)}")
    return _rsi_series_from_closes(closes, period)[-1]


def calculate_rsi_series(candles: list[Candle], period: int = 14) -> list[float]:
    """RSI at every candle once enough history exists; result[i] lines up with candles[period + i]."""
    closes = _closes(candles)
    if len(closes) < period + 1:
        raise ValueError(f"need at least {period + 1} candles, got {len(closes)}")
    return _rsi_series_from_closes(closes, period)


def calculate_macd(
    candles: list[Candle],
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> MACDResult:
    """MACD line, signal line and histogram of the close price."""
    closes = _closes(candles)
    if len(closes) < slow + signal:
        raise ValueError(f"need at least {slow + signal} candles, got {len(closes)}")

    ema_fast = _ema_series(closes, fast)
    ema_slow = _ema_series(closes, slow)
    macd_series = [f - s for f, s in zip(ema_fast, ema_slow)]
    signal_series = _ema_series(macd_series, signal)

    macd_value = macd_series[-1]
    signal_value = signal_series[-1]
    return MACDResult(
        macd_line=macd_value,
        signal_line=signal_value,
        histogram=macd_value - signal_value,
    )
