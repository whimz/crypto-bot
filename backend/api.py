"""FastAPI app exposing bot state to the frontend; owns the bot's lifecycle."""

from __future__ import annotations

import csv
import io
import json
import logging
import sys
from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from typing import Optional

# Configured here, not in main.py: Railway's start command runs `uvicorn api:app` directly,
# which imports this module without ever executing main.py - a basicConfig() call there
# would never run, silently leaving every logger.info() call unhandled (Python's last-resort
# handler only emits WARNING+, which is why only errors were ever visible in Railway's logs).
logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

import auth
import scheduler
import settings as settings_module
from analysis.indicators import calculate_rsi_series
from config import ALLOWED_ORIGINS
from data.binance import BinanceClient, BinanceClientError
from db import storage
from trading.backtesting import SIMULATION_DAYS, TARGET_WEEKLY_RETURN_USDT, run_comparison
from trading.portfolio import calculate_equity

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings_module.apply_settings(settings_module.get_settings())
    scheduler.start_bot()
    yield
    scheduler.shutdown_bot()


app = FastAPI(title="Crypto Bot API", lifespan=lifespan)

app.include_router(auth.router)

# Added in this order so CORS ends up outermost (Starlette runs the most-recently-added
# middleware first) and can answer OPTIONS preflight requests before AuthMiddleware sees them.
app.add_middleware(auth.AuthMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {
        "status": "running" if scheduler._running else "stopped",
        "last_cycle_at": scheduler.get_last_cycle_at(),
    }


@app.get("/portfolio")
def portfolio() -> dict:
    snapshot = calculate_equity()
    initial = snapshot.initial_deposit_usdt
    current = snapshot.equity_usdt
    drawdown_pct = ((initial - current) / initial * 100) if initial > 0 else 0.0
    return {
        "initial_deposit_usdt": initial,
        "current_deposit_usdt": current,
        "drawdown_pct": round(drawdown_pct, 2),
        "updated_at": storage.get_portfolio()["updated_at"],
        "positions": [asdict(p) for p in snapshot.positions],
    }


class PortfolioInitRequest(BaseModel):
    amount: float


@app.post("/portfolio/init")
def portfolio_init(payload: PortfolioInitRequest) -> dict:
    if payload.amount <= 0:
        raise HTTPException(status_code=400, detail="amount must be positive")
    storage.update_portfolio(payload.amount)
    return portfolio()


@app.get("/portfolio/history")
def portfolio_history(days: int = Query(7, ge=1, le=365)) -> list[dict]:
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    return storage.get_portfolio_history(since)


@app.get("/positions")
def positions() -> list[dict]:
    """Kept for any standalone callers; the dashboard now gets positions from /portfolio's
    single combined response instead of fetching this separately."""
    return [asdict(p) for p in calculate_equity().positions]


@app.get("/trades")
def trades(symbol: Optional[str] = Query(None), limit: int = Query(50, ge=1, le=500)) -> list[dict]:
    return storage.get_trades(symbol=symbol, limit=limit)


@app.get("/trades/export")
def trades_export(
    symbol: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
) -> StreamingResponse:
    rows = storage.get_trades_filtered(symbol=symbol, date_from=date_from, date_to=date_to)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["date", "symbol", "action", "price", "amount_usdt", "reason", "confidence"])
    for row in rows:
        writer.writerow(
            [row["timestamp"], row["symbol"], row["action"], row["price"], row["amount_usdt"], row["reason"], row["confidence"]]
        )
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=trades.csv"},
    )


@app.get("/settings")
def get_settings_endpoint() -> dict:
    return asdict(settings_module.get_settings())


@app.post("/settings")
def update_settings_endpoint(updates: dict) -> dict:
    try:
        new_settings = settings_module.update_settings(updates)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return asdict(new_settings)


@app.get("/logs")
def logs(
    symbol: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
) -> list[dict]:
    entries = storage.get_logs(symbol=symbol, limit=limit, offset=offset, date_from=date_from, date_to=date_to)
    for entry in entries:
        entry["details"] = json.loads(entry["details"]) if entry["details"] else None
    return entries


@app.get("/chart")
def chart(
    symbol: str = Query(...),
    interval: str = Query("15m"),
    limit: int = Query(100, ge=1, le=1000),
) -> dict:
    try:
        candles = BinanceClient().get_klines(symbol=symbol, interval=interval, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except BinanceClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    candlesticks = [
        {"time": c.open_time // 1000, "open": c.open, "high": c.high, "low": c.low, "close": c.close}
        for c in candles
    ]

    rsi_period = 14
    rsi = []
    if len(candles) >= rsi_period + 1:
        rsi_values = calculate_rsi_series(candles, period=rsi_period)
        rsi = [
            {"time": c.open_time // 1000, "value": round(value, 2)}
            for c, value in zip(candles[rsi_period:], rsi_values)
        ]

    return {"candles": candlesticks, "rsi": rsi}


@app.post("/bot/start")
def bot_start() -> dict:
    scheduler.start_bot()
    return {"status": "running" if scheduler._running else "stopped"}


@app.post("/bot/stop")
def bot_stop() -> dict:
    scheduler.stop_bot(reason="Stopped via API")
    return {"status": "running" if scheduler._running else "stopped"}


@app.post("/bot/run-cycle")
def bot_run_cycle() -> dict:
    """One-off manual trading cycle, independent of the 15-minute APScheduler job."""
    if not scheduler._running:
        raise HTTPException(status_code=409, detail="Bot is not running")
    scheduler.run_cycle()
    return {"status": "ok", "last_cycle_at": scheduler.get_last_cycle_at()}


@app.post("/backtest")
def backtest() -> dict:
    """On-demand comparison of take-profit/EMA-filter combinations against real history.
    Takes noticeable time (fetches ~SIMULATION_DAYS of klines, then replays several
    configs) - the frontend shows a loading state while this is in flight."""
    try:
        rows = run_comparison()
    except BinanceClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {
        "simulation_days": SIMULATION_DAYS,
        "target_weekly_return_usdt": TARGET_WEEKLY_RETURN_USDT,
        "rows": [
            {
                "label": row.label,
                "take_profit_pct": row.config.take_profit_pct,
                "require_ema_trend": row.config.require_ema_trend,
                "trade_count": row.trade_count,
                "win_rate_pct": row.win_rate_pct,
                "avg_weekly_return_usdt": row.avg_weekly_return_usdt,
                "median_weekly_return_usdt": row.median_weekly_return_usdt,
                "worst_weekly_return_usdt": row.worst_weekly_return_usdt,
                "hint": row.hint,
            }
            for row in rows
        ],
    }
