import os
import tempfile
from pathlib import Path

import pytest

from db import storage
from trading.risk import PositionState


@pytest.fixture
def db(monkeypatch):
    """Point storage at a fresh temp file for the duration of the test, then delete it."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db_path = Path(path)
    monkeypatch.setattr(storage, "_DB_PATH", db_path)
    storage.init_db()
    try:
        yield storage
    finally:
        db_path.unlink(missing_ok=True)


def test_init_db_seeds_empty_portfolio(db):
    portfolio = db.get_portfolio()
    assert portfolio["initial_deposit_usdt"] == 0.0
    assert portfolio["current_deposit_usdt"] == 0.0
    assert portfolio["updated_at"]


def test_save_and_read_trade(db):
    trade = db.Trade(
        symbol="BTCUSDT", action="BUY", price=50000.0, amount_usdt=100.0,
        timestamp="2026-01-01T00:00:00Z", reason="test buy", confidence=80.0,
    )
    trade_id = db.save_trade(trade)
    assert trade_id == 1

    trades = db.get_trades(symbol="BTCUSDT")
    assert len(trades) == 1
    assert trades[0]["symbol"] == "BTCUSDT"
    assert trades[0]["price"] == 50000.0
    assert trades[0]["confidence"] == 80.0


def test_get_trades_filters_by_symbol_and_orders_newest_first(db):
    for i in range(5):
        db.save_trade(
            db.Trade(symbol="BTCUSDT", action="BUY", price=100.0 + i, amount_usdt=10.0, timestamp=f"t{i}", reason="r", confidence=50.0)
        )
    db.save_trade(db.Trade(symbol="ETHUSDT", action="BUY", price=2000.0, amount_usdt=10.0, timestamp="t", reason="r", confidence=50.0))

    btc_trades = db.get_trades(symbol="BTCUSDT", limit=3)
    assert len(btc_trades) == 3
    assert all(t["symbol"] == "BTCUSDT" for t in btc_trades)
    assert btc_trades[0]["price"] == 104.0  # most recently inserted comes first

    all_trades = db.get_trades(limit=100)
    assert len(all_trades) == 6


def test_get_position_returns_none_when_missing(db):
    assert db.get_position("BTCUSDT") is None


def test_update_and_get_position_round_trip(db):
    position = PositionState(symbol="BTCUSDT", avg_price=50000.0, total_invested=100.0, dca_count=1, peak_price=51000.0)
    db.update_position(position)
    assert db.get_position("BTCUSDT") == position


def test_update_position_upserts_instead_of_duplicating(db):
    db.update_position(PositionState(symbol="BTCUSDT", avg_price=100.0, total_invested=10.0, dca_count=1, peak_price=100.0))
    updated = PositionState(symbol="BTCUSDT", avg_price=110.0, total_invested=20.0, dca_count=2, peak_price=120.0)
    db.update_position(updated)
    assert db.get_position("BTCUSDT") == updated


def test_update_portfolio_sets_initial_deposit_only_on_first_call(db):
    db.update_portfolio(1000.0)
    portfolio = db.get_portfolio()
    assert portfolio["initial_deposit_usdt"] == 1000.0
    assert portfolio["current_deposit_usdt"] == 1000.0

    db.update_portfolio(900.0)
    portfolio = db.get_portfolio()
    assert portfolio["initial_deposit_usdt"] == 1000.0  # baseline stays fixed
    assert portfolio["current_deposit_usdt"] == 900.0


def _log(timestamp: str) -> "storage.LogEntry":
    return storage.LogEntry(symbol="BTCUSDT", action="HOLD", confidence=0.0, reason="r", timestamp=timestamp)


def test_get_logs_filters_by_date_range_across_full_history_not_just_loaded_page(db):
    # "Yesterday" and "today" relative to a fixed now, far apart so paging order is unambiguous.
    db.save_log(_log("2026-01-01T10:00:00+00:00"))  # yesterday
    db.save_log(_log("2026-01-02T05:00:00+00:00"))  # today, before noon
    db.save_log(_log("2026-01-02T18:00:00+00:00"))  # today, after noon

    yesterday = db.get_logs(date_from="2026-01-01T00:00:00+00:00", date_to="2026-01-01T23:59:59.999+00:00")
    assert len(yesterday) == 1
    assert yesterday[0]["timestamp"] == "2026-01-01T10:00:00+00:00"

    today = db.get_logs(date_from="2026-01-02T00:00:00+00:00", date_to="2026-01-02T23:59:59.999+00:00")
    assert len(today) == 2
    assert {row["timestamp"] for row in today} == {"2026-01-02T05:00:00+00:00", "2026-01-02T18:00:00+00:00"}


def test_get_logs_date_filter_accepts_js_z_suffixed_iso_strings(db):
    db.save_log(_log("2026-01-01T10:00:00+00:00"))
    db.save_log(_log("2026-01-02T05:00:00+00:00"))

    # JS's Date.prototype.toISOString() always emits a "Z" suffix, not "+00:00".
    result = db.get_logs(date_from="2026-01-02T00:00:00.000Z", date_to="2026-01-02T23:59:59.999Z")
    assert len(result) == 1
    assert result[0]["timestamp"] == "2026-01-02T05:00:00+00:00"


def test_get_logs_date_filter_combines_with_pagination(db):
    for hour in range(5):
        db.save_log(_log(f"2026-01-02T{hour:02d}:00:00+00:00"))

    page1 = db.get_logs(limit=2, offset=0, date_from="2026-01-02T00:00:00+00:00", date_to="2026-01-02T23:59:59.999+00:00")
    page2 = db.get_logs(limit=2, offset=2, date_from="2026-01-02T00:00:00+00:00", date_to="2026-01-02T23:59:59.999+00:00")
    assert len(page1) == 2
    assert len(page2) == 2
    assert {row["id"] for row in page1}.isdisjoint({row["id"] for row in page2})
