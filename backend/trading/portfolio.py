"""Live portfolio equity: free cash + current market value of open positions.

Kept separate from risk.py on purpose - risk.py's check_risk() still reads the stored,
manually-set portfolio.current_deposit_usdt for trade-sizing/drawdown decisions, unchanged.
This module only computes a *display* figure (API responses, deposit history snapshots),
so it can't accidentally affect entry/exit logic.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from config import SYMBOLS
from data.binance import BinanceClient, BinanceClientError
from db import storage

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PositionView:
    symbol: str
    avg_price: float
    total_invested: float
    dca_count: int
    peak_price: float
    current_price: Optional[float]
    pnl_usdt: Optional[float]
    pnl_pct: Optional[float]


@dataclass(frozen=True)
class EquitySnapshot:
    initial_deposit_usdt: float
    free_cash_usdt: float
    equity_usdt: float
    positions: list[PositionView]


def calculate_equity(client: Optional[BinanceClient] = None) -> EquitySnapshot:
    """One ticker-price fetch per open symbol, shared between the equity total and each
    position's own PnL - replacing what used to be two separate fetches (one in /portfolio's
    caller, one in /positions). If a price fetch fails for a symbol, that position's PnL
    fields degrade to None (same as before) and its contribution to equity falls back to its
    invested amount (assumes 0 PnL) rather than failing the whole calculation."""
    client = client or BinanceClient()
    initial_deposit = storage.get_portfolio()["initial_deposit_usdt"]

    positions: list[PositionView] = []
    invested_total = 0.0
    market_value_total = 0.0

    for symbol in SYMBOLS:
        position = storage.get_position(symbol)
        if position is None or position.total_invested <= 0:
            continue

        invested_total += position.total_invested
        market_value = position.total_invested  # degrade-gracefully default if price fetch fails
        current_price = None
        pnl_usdt = None
        pnl_pct = None

        try:
            current_price = client.get_ticker_price(symbol)
        except BinanceClientError as exc:
            logger.error("Failed to fetch ticker price for %s: %s", symbol, exc)
        else:
            if position.avg_price > 0:
                quantity = position.total_invested / position.avg_price
                market_value = current_price * quantity
                pnl_usdt = round(market_value - position.total_invested, 2)
                pnl_pct = round((current_price - position.avg_price) / position.avg_price * 100, 2)

        market_value_total += market_value
        positions.append(
            PositionView(
                symbol=position.symbol,
                avg_price=position.avg_price,
                total_invested=position.total_invested,
                dca_count=position.dca_count,
                peak_price=position.peak_price,
                current_price=current_price,
                pnl_usdt=pnl_usdt,
                pnl_pct=pnl_pct,
            )
        )

    free_cash = initial_deposit - invested_total
    return EquitySnapshot(
        initial_deposit_usdt=initial_deposit,
        free_cash_usdt=free_cash,
        equity_usdt=free_cash + market_value_total,
        positions=positions,
    )
