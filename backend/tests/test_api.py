"""Direct unit tests for api.py route functions (no TestClient/httpx dependency in this
project yet - calling the handler functions directly is consistent with how the rest of
the backend is tested here)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

import api
from data.binance import BinanceClientError
from trading.backtesting import ComparisonRow, SimulationConfig


def _row(label="TP=3%, EMA filter=on") -> ComparisonRow:
    return ComparisonRow(
        label=label,
        config=SimulationConfig(take_profit_pct=0.03, require_ema_trend=True, label=label),
        trade_count=5,
        win_rate_pct=60.0,
        avg_weekly_return_usdt=2.5,
        median_weekly_return_usdt=2.0,
        worst_weekly_return_usdt=-1.0,
        hint="В среднем прибыльно, но ниже цели",
    )


def test_backtest_endpoint_shapes_comparison_rows_into_json(monkeypatch):
    monkeypatch.setattr(api, "run_comparison", MagicMock(return_value=[_row()]))

    response = api.backtest()

    assert response["simulation_days"] == api.SIMULATION_DAYS
    assert response["target_weekly_return_usdt"] == api.TARGET_WEEKLY_RETURN_USDT
    assert len(response["rows"]) == 1
    row = response["rows"][0]
    assert row["label"] == "TP=3%, EMA filter=on"
    assert row["take_profit_pct"] == 0.03
    assert row["require_ema_trend"] is True
    assert row["trade_count"] == 5
    assert row["win_rate_pct"] == 60.0


def test_backtest_endpoint_returns_502_on_binance_error(monkeypatch):
    monkeypatch.setattr(api, "run_comparison", MagicMock(side_effect=BinanceClientError("rate limited")))

    with pytest.raises(HTTPException) as exc_info:
        api.backtest()

    assert exc_info.value.status_code == 502
