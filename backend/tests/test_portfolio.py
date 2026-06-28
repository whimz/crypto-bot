import os
import tempfile
from pathlib import Path

import pytest

from data.binance import BinanceClientError
from db import storage
from trading import portfolio
from trading.risk import PositionState


class FakeClient:
    """Returns a fixed price per symbol, or raises if the configured value is an exception."""

    def __init__(self, prices: dict):
        self.prices = prices

    def get_ticker_price(self, symbol: str) -> float:
        price = self.prices[symbol]
        if isinstance(price, Exception):
            raise price
        return price


@pytest.fixture
def db(monkeypatch):
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db_path = Path(path)
    monkeypatch.setattr(storage, "_DB_PATH", db_path)
    storage.init_db()
    try:
        yield storage
    finally:
        db_path.unlink(missing_ok=True)


def test_equity_equals_initial_deposit_with_no_open_positions(db, monkeypatch):
    monkeypatch.setattr(portfolio, "SYMBOLS", ["BTCUSDT"])
    db.update_portfolio(1000.0)

    snapshot = portfolio.calculate_equity(FakeClient({}))

    assert snapshot.initial_deposit_usdt == 1000.0
    assert snapshot.free_cash_usdt == 1000.0
    assert snapshot.equity_usdt == 1000.0
    assert snapshot.positions == []


def test_equity_reflects_unrealized_gain_on_open_position(db, monkeypatch):
    monkeypatch.setattr(portfolio, "SYMBOLS", ["BTCUSDT"])
    db.update_portfolio(1000.0)
    db.update_position(PositionState(symbol="BTCUSDT", avg_price=100.0, total_invested=200.0, dca_count=1, peak_price=100.0))

    snapshot = portfolio.calculate_equity(FakeClient({"BTCUSDT": 110.0}))  # price up 10%

    assert snapshot.free_cash_usdt == 800.0  # 1000 initial - 200 invested
    assert snapshot.equity_usdt == 1020.0  # 800 free cash + 220 market value
    assert len(snapshot.positions) == 1
    position_view = snapshot.positions[0]
    assert position_view.current_price == 110.0
    assert position_view.pnl_usdt == 20.0
    assert position_view.pnl_pct == 10.0


def test_equity_falls_back_to_invested_amount_when_price_fetch_fails(db, monkeypatch):
    monkeypatch.setattr(portfolio, "SYMBOLS", ["BTCUSDT"])
    db.update_portfolio(1000.0)
    db.update_position(PositionState(symbol="BTCUSDT", avg_price=100.0, total_invested=200.0, dca_count=1, peak_price=100.0))

    snapshot = portfolio.calculate_equity(FakeClient({"BTCUSDT": BinanceClientError("boom")}))

    assert snapshot.equity_usdt == 1000.0  # degrades to 0 PnL instead of crashing
    position_view = snapshot.positions[0]
    assert position_view.current_price is None
    assert position_view.pnl_usdt is None
    assert position_view.pnl_pct is None


def test_equity_sums_multiple_open_positions_and_skips_closed_ones(db, monkeypatch):
    monkeypatch.setattr(portfolio, "SYMBOLS", ["BTCUSDT", "ETHUSDT", "LTCUSDT"])
    db.update_portfolio(1000.0)
    db.update_position(PositionState(symbol="BTCUSDT", avg_price=100.0, total_invested=100.0, dca_count=1, peak_price=100.0))
    db.update_position(PositionState(symbol="ETHUSDT", avg_price=50.0, total_invested=50.0, dca_count=1, peak_price=50.0))
    db.update_position(PositionState(symbol="LTCUSDT", avg_price=0.0, total_invested=0.0, dca_count=0, peak_price=0.0))  # closed

    snapshot = portfolio.calculate_equity(FakeClient({"BTCUSDT": 100.0, "ETHUSDT": 50.0}))

    assert {p.symbol for p in snapshot.positions} == {"BTCUSDT", "ETHUSDT"}
    assert snapshot.free_cash_usdt == 850.0  # 1000 - 100 - 50
    assert snapshot.equity_usdt == 1000.0  # no price change
