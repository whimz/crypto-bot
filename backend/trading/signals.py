"""Multi-timeframe trading signal generation (15m + 1h confirmation)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from backend.analysis.indicators import MACDResult, calculate_ema, calculate_macd, calculate_rsi
from backend.data.binance import Candle

RSI_OVERSOLD = 35
RSI_OVERBOUGHT = 65
EMA_PERIOD = 50


@dataclass(frozen=True)
class SignalResult:
    action: Literal["BUY", "SELL", "HOLD"]
    confidence: float
    reason: str
    rsi_15m: float
    rsi_1h: float


@dataclass(frozen=True)
class _TimeframeAnalysis:
    rsi: float
    ema50: float
    macd: MACDResult
    price: float


def _analyze(candles: list[Candle]) -> _TimeframeAnalysis:
    return _TimeframeAnalysis(
        rsi=calculate_rsi(candles),
        ema50=calculate_ema(candles, period=EMA_PERIOD),
        macd=calculate_macd(candles),
        price=candles[-1].close,
    )


def _rsi_strength(rsi: float, threshold: float, lower_is_stronger: bool) -> float:
    """0..1: how far RSI sits past the threshold, in the direction that strengthens the signal."""
    if lower_is_stronger:
        return max(0.0, min(1.0, (threshold - rsi) / threshold))
    return max(0.0, min(1.0, (rsi - threshold) / (100 - threshold)))


def get_signal(candles_15m: list[Candle], candles_1h: list[Candle]) -> SignalResult:
    tf15 = _analyze(candles_15m)
    tf1h = _analyze(candles_1h)

    oversold = tf15.rsi < RSI_OVERSOLD and tf1h.rsi < RSI_OVERSOLD
    overbought = tf15.rsi > RSI_OVERBOUGHT and tf1h.rsi > RSI_OVERBOUGHT
    above_ema = tf15.price > tf15.ema50 and tf1h.price > tf1h.ema50
    below_ema = tf15.price < tf15.ema50 and tf1h.price < tf1h.ema50

    if oversold and above_ema:
        strength = (
            _rsi_strength(tf15.rsi, RSI_OVERSOLD, lower_is_stronger=True)
            + _rsi_strength(tf1h.rsi, RSI_OVERSOLD, lower_is_stronger=True)
        ) / 2
        macd_bonus = 10 if tf15.macd.histogram > 0 and tf1h.macd.histogram > 0 else 0
        confidence = min(100.0, 60 + strength * 30 + macd_bonus)
        return SignalResult(
            action="BUY",
            confidence=round(confidence, 2),
            reason=(
                f"RSI oversold on both timeframes (15m={tf15.rsi:.1f}, 1h={tf1h.rsi:.1f}) "
                f"with price above EMA50 (15m={tf15.price:.2f}>{tf15.ema50:.2f}, "
                f"1h={tf1h.price:.2f}>{tf1h.ema50:.2f})"
            ),
            rsi_15m=tf15.rsi,
            rsi_1h=tf1h.rsi,
        )

    if overbought and below_ema:
        strength = (
            _rsi_strength(tf15.rsi, RSI_OVERBOUGHT, lower_is_stronger=False)
            + _rsi_strength(tf1h.rsi, RSI_OVERBOUGHT, lower_is_stronger=False)
        ) / 2
        macd_bonus = 10 if tf15.macd.histogram < 0 and tf1h.macd.histogram < 0 else 0
        confidence = min(100.0, 60 + strength * 30 + macd_bonus)
        return SignalResult(
            action="SELL",
            confidence=round(confidence, 2),
            reason=(
                f"RSI overbought on both timeframes (15m={tf15.rsi:.1f}, 1h={tf1h.rsi:.1f}) "
                f"with price below EMA50 (15m={tf15.price:.2f}<{tf15.ema50:.2f}, "
                f"1h={tf1h.price:.2f}<{tf1h.ema50:.2f})"
            ),
            rsi_15m=tf15.rsi,
            rsi_1h=tf1h.rsi,
        )

    return SignalResult(
        action="HOLD",
        confidence=0.0,
        reason=(
            f"No aligned signal: RSI 15m={tf15.rsi:.1f}, 1h={tf1h.rsi:.1f}; "
            f"price vs EMA50 15m={tf15.price:.2f}/{tf15.ema50:.2f}, "
            f"1h={tf1h.price:.2f}/{tf1h.ema50:.2f}"
        ),
        rsi_15m=tf15.rsi,
        rsi_1h=tf1h.rsi,
    )
