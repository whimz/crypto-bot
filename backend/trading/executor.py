"""Trade execution: turns an approved signal into a real (testnet/production) order."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from data.binance import BinanceClient, BinanceClientError, Candle
from db import storage
from notifications import telegram
from trading.risk import PositionState, check_risk
from trading.signals import SignalResult

logger = logging.getLogger(__name__)


def _empty_position(symbol: str) -> PositionState:
    return PositionState(symbol=symbol, avg_price=0.0, total_invested=0.0, dca_count=0, peak_price=0.0)


def _extract_fill(order: dict, fallback_price: float, fallback_quote: float) -> tuple[float, float]:
    """Use the exchange's actual fill price/amount when present, else fall back to the nominal values."""
    executed_qty = float(order.get("executedQty") or 0)
    cumulative_quote_qty = float(order.get("cummulativeQuoteQty") or 0)
    if executed_qty > 0 and cumulative_quote_qty > 0:
        return cumulative_quote_qty / executed_qty, cumulative_quote_qty
    return fallback_price, fallback_quote


def execute_signal(symbol: str, signal: SignalResult, candles_15m: list[Candle]) -> None:
    current_price = candles_15m[-1].close

    position = storage.get_position(symbol) or _empty_position(symbol)

    if signal.action == "SELL" and (not position or position.total_invested <= 0):
        logger.info("[%s] No position to sell, skipping", symbol)
        return

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
        logger.info("Trade blocked for %s %s: %s", signal.action, symbol, risk_result.reason)
        return

    client = BinanceClient()
    try:
        order = client.place_market_order(
            symbol=symbol,
            side=signal.action,
            quote_order_qty=risk_result.order_size_usdt,
        )
    except BinanceClientError as exc:
        logger.error("Order failed for %s %s: %s", signal.action, symbol, exc)
        telegram.notify_error(f"Order failed for {signal.action} {symbol}: {exc}")
        return

    fill_price, filled_quote = _extract_fill(order, current_price, risk_result.order_size_usdt)

    if signal.action == "BUY":
        prior_qty = position.total_invested / position.avg_price if position.avg_price > 0 else 0.0
        filled_qty = filled_quote / fill_price if fill_price > 0 else 0.0
        new_total_invested = position.total_invested + filled_quote
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
