"""Shared pytest setup and helpers for backend tests."""

from __future__ import annotations

import sys
from pathlib import Path

# Make sure `import backend....` works no matter what directory pytest is invoked from.
ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.data.binance import Candle  # noqa: E402


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
