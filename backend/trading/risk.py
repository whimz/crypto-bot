"""Position sizing and risk gating for trade signals."""

from __future__ import annotations

from dataclasses import dataclass

from backend.trading.signals import SignalResult

MAX_SYMBOL_ALLOCATION_PCT = 0.40
MAX_CONSECUTIVE_DCA = 3
TRAILING_STOP_LOSS_PCT = 0.07
GLOBAL_DRAWDOWN_STOP_PCT = 0.20

# RSI bands -> volatility-scaled order size, as a fraction of total deposit.
RSI_LOW_VOLATILITY_PCT = 0.15  # RSI 35-50
RSI_MEDIUM_VOLATILITY_PCT = 0.10  # RSI 20-35
RSI_HIGH_VOLATILITY_PCT = 0.05  # RSI < 20


@dataclass
class PositionState:
    symbol: str
    avg_price: float
    total_invested: float
    dca_count: int
    peak_price: float = 0.0  # highest price observed since entry; updated by the caller on each new candle


@dataclass(frozen=True)
class RiskResult:
    allowed: bool
    reason: str
    order_size_usdt: float


def _order_size_pct(avg_rsi: float) -> tuple[float, str]:
    if avg_rsi < 20:
        return RSI_HIGH_VOLATILITY_PCT, "high volatility (RSI<20)"
    if avg_rsi < 35:
        return RSI_MEDIUM_VOLATILITY_PCT, "medium volatility (RSI 20-35)"
    return RSI_LOW_VOLATILITY_PCT, "low volatility (RSI 35-50)"


def check_risk(
    symbol: str,
    current_price: float,
    signal: SignalResult,
    position: PositionState,
    deposit_usdt: float,
    initial_deposit_usdt: float,
) -> RiskResult:
    if signal.action == "HOLD":
        return RiskResult(allowed=False, reason=f"[{symbol}] HOLD signal: no action required", order_size_usdt=0.0)

    if signal.action == "SELL":
        # Exits are always allowed regardless of caps/DCA counters - closing risk takes priority.
        return RiskResult(
            allowed=True,
            reason=f"[{symbol}] SELL signal confirmed, closing position (invested={position.total_invested:.2f} USDT)",
            order_size_usdt=position.total_invested,
        )

    # From here on, signal.action == "BUY".

    if initial_deposit_usdt > 0:
        drawdown = (initial_deposit_usdt - deposit_usdt) / initial_deposit_usdt
        if drawdown >= GLOBAL_DRAWDOWN_STOP_PCT:
            return RiskResult(
                allowed=False,
                reason=f"[{symbol}] Global stop: deposit drawdown {drawdown * 100:.1f}% >= {GLOBAL_DRAWDOWN_STOP_PCT * 100:.0f}%",
                order_size_usdt=0.0,
            )

    if position.peak_price > 0:
        drop_from_peak = (position.peak_price - current_price) / position.peak_price
        if drop_from_peak >= TRAILING_STOP_LOSS_PCT:
            return RiskResult(
                allowed=False,
                reason=(
                    f"[{symbol}] Trailing stop-loss triggered: price {current_price:.2f} is "
                    f"{drop_from_peak * 100:.1f}% below peak {position.peak_price:.2f} - "
                    "blocking further DCA, position should be closed"
                ),
                order_size_usdt=0.0,
            )

    if position.dca_count >= MAX_CONSECUTIVE_DCA:
        return RiskResult(
            allowed=False,
            reason=f"[{symbol}] Max {MAX_CONSECUTIVE_DCA} consecutive DCA reached without a sell",
            order_size_usdt=0.0,
        )

    symbol_cap = MAX_SYMBOL_ALLOCATION_PCT * deposit_usdt
    remaining_allowance = symbol_cap - position.total_invested
    if remaining_allowance <= 0:
        return RiskResult(
            allowed=False,
            reason=(
                f"[{symbol}] Symbol allocation cap reached: {position.total_invested:.2f}/{symbol_cap:.2f} "
                f"USDT ({MAX_SYMBOL_ALLOCATION_PCT * 100:.0f}% of deposit)"
            ),
            order_size_usdt=0.0,
        )

    avg_rsi = (signal.rsi_15m + signal.rsi_1h) / 2
    pct, band = _order_size_pct(avg_rsi)
    order_size_usdt = min(pct * deposit_usdt, remaining_allowance)

    return RiskResult(
        allowed=True,
        reason=(
            f"[{symbol}] BUY approved: {band}, size={pct * 100:.0f}% of deposit "
            f"(capped to remaining allowance {remaining_allowance:.2f} USDT)"
        ),
        order_size_usdt=round(order_size_usdt, 2),
    )
