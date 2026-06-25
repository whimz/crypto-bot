"""Shared pytest setup and helpers for backend tests."""

from __future__ import annotations

import sys
from pathlib import Path

# Backend modules import each other root-relative (e.g. `from data.binance import Candle`),
# matching Railway's deploy where root directory = backend/. Put backend/ itself on sys.path
# no matter what directory pytest is invoked from.
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from data.binance import Candle  # noqa: E402


def make_candles(prices: list[float]) -> list[Candle]:
    """Build a minimal Candle series from close prices; only `.close` matters to the code under test."""
    return [
        Candle(
            open_time=i,
            open=price,
            high=price,
            low=price,
            close=price,
            volume=1.0,
            close_time=i,
            quote_volume=1.0,
            trades=1,
        )
        for i, price in enumerate(prices)
    ]
