"""Trade execution: turns an approved signal into a real (testnet/production) order."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from data.binance import BinanceClient, BinanceClientError, Candle
from db import storage
from notifications import telegram
from trading.risk import PositionState, check_risk
from trading.signals import SignalResult

logger = logging.getLogger(__name__)

# Activity Log row categories - the single source of truth for these strings. Defined here
# (not duplicated in scheduler.py) even though TAKE_PROFIT/HOLD are never returned by
# execute_signal itself - scheduler.py imports them from here too, so every category string
# used anywhere in the backend lives in exactly one place.
CATEGORY_TRADE_EXECUTED = "TRADE_EXECUTED"
CATEGORY_TAKE_PROFIT = "TAKE_PROFIT"
CATEGORY_RISK_BLOCKED = "RISK_BLOCKED"
CATEGORY_SIGNAL_IGNORED_NO_POSITION = "SIGNAL_IGNORED_NO_POSITION"
CATEGORY_ERROR = "ERROR"
CATEGORY_HOLD = "HOLD"


@dataclass(frozen=True)
class ExecutionOutcome:
    """What actually happened when execute_signal() was called - distinct from the signal's
    own action/reason, since a BUY/SELL signal can still result in nothing happening."""

    category: str
    reason: str


def _empty_position(symbol: str) -> PositionState:
    return PositionState(symbol=symbol, avg_price=0.0, total_invested=0.0, dca_count=0, peak_price=0.0)


def _extract_fill(order: dict, fallback_price: float, fallback_quote: float) -> tuple[float, float]:
    """Use the exchange's actual fill price/amount when present, else fall back to the nominal values."""
    executed_qty = float(order.get("executedQty") or 0)
    cumulative_quote_qty = float(order.get("cummulativeQuoteQty") or 0)
    if executed_qty > 0 and cumulative_quote_qty > 0:
        return cumulative_quote_qty / executed_qty, cumulative_quote_qty
    return fallback_price, fallback_quote


def execute_signal(symbol: str, signal: SignalResult, candles_15m: list[Candle]) -> ExecutionOutcome:
    current_price = candles_15m[-1].close

    position = storage.get_position(symbol) or _empty_position(symbol)

    if signal.action == "SELL" and (not position or position.total_invested <= 0):
        reason = f"[{symbol}] No position to sell, skipping"
        logger.info(reason)
        return ExecutionOutcome(category=CATEGORY_SIGNAL_IGNORED_NO_POSITION, reason=reason)

    portfolio = storage.get_portfolio()

    risk_result = check_risk(
        symbol=symbol,
        current_price=current_price,
        signal=signal,
        position=position,
        deposit_usdt=portfolio["current_deposit_usdt"],
        initial_deposit_usdt=portfolio["initial_deposit_usdt"],
    )

    if not risk_result.allowed:
        reason = f"Trade blocked for {signal.action} {symbol}: {risk_result.reason}"
        logger.info(reason)
        return ExecutionOutcome(category=CATEGORY_RISK_BLOCKED, reason=reason)

    client = BinanceClient()
    try:
        order = client.place_market_order(
            symbol=symbol,
            side=signal.action,
            quote_order_qty=risk_result.order_size_usdt,
        )
    except BinanceClientError as exc:
        reason = f"Order failed for {signal.action} {symbol}: {exc}"
        logger.error(reason)
        telegram.notify_error(reason)
        return ExecutionOutcome(category=CATEGORY_ERROR, reason=reason)

    fill_price, filled_quote = _extract_fill(order, current_price, risk_result.order_size_usdt)

    if signal.action == "BUY":
        prior_qty = position.total_invested / position.avg_price if position.avg_price > 0 else 0.0
        filled_qty = filled_quote / fill_price if fill_price > 0 else 0.0
        # Rounded so float noise from repeated DCA fills doesn't accumulate in the stored
        # position - otherwise it would surface later as Binance's -1111 "too much precision"
        # when this total is sent back as a SELL order's quoteOrderQty.
        new_total_invested = round(position.total_invested + filled_quote, 2)
        new_qty = prior_qty + filled_qty
        updated_position = PositionState(
            symbol=symbol,
            avg_price=new_total_invested / new_qty if new_qty > 0 else fill_price,
            total_invested=new_total_invested,
            dca_count=position.dca_count + 1,
            peak_price=max(position.peak_price, current_price),
        )
    else:  # SELL closes the whole position
        updated_position = _empty_position(symbol)

    try:
        storage.update_position(updated_position)
        storage.save_trade(
            storage.Trade(
                symbol=symbol,
                action=signal.action,
                price=fill_price,
                amount_usdt=filled_quote,
                timestamp=datetime.now(timezone.utc).isoformat(),
                reason=risk_result.reason,
                confidence=signal.confidence,
            )
        )
    except Exception:
        logger.exception("Order for %s %s executed but failed to persist", signal.action, symbol)

    telegram.notify_trade(
        action=signal.action,
        symbol=symbol,
        price=fill_price,
        amount_usdt=filled_quote,
        reason=risk_result.reason,
        confidence=signal.confidence,
    )

    return ExecutionOutcome(category=CATEGORY_TRADE_EXECUTED, reason=risk_result.reason)


def update_peak_prices(symbol: str, current_price: float) -> None:
    """Bump the stored peak_price after each new candle so the trailing stop has a reference."""
    position = storage.get_position(symbol)
    if position is None or current_price <= position.peak_price:
        return
    storage.update_position(
        PositionState(
            symbol=position.symbol,
            avg_price=position.avg_price,
            total_invested=position.total_invested,
            dca_count=position.dca_count,
            peak_price=current_price,
        )
    )
