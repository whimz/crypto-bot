"""FastAPI app exposing bot state to the frontend; owns the bot's lifecycle."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from dataclasses import asdict
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

import auth
import scheduler
from analysis.indicators import calculate_rsi_series
from config import ALLOWED_ORIGINS, SYMBOLS
from data.binance import BinanceClient, BinanceClientError
from db import storage


@asynccontextmanager
async def lifespan(app: FastAPI):
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
    return {"status": "running" if scheduler._running else "stopped"}


@app.get("/portfolio")
def portfolio() -> dict:
    data = storage.get_portfolio()
    initial = data["initial_deposit_usdt"]
    current = data["current_deposit_usdt"]
    drawdown_pct = ((initial - current) / initial * 100) if initial > 0 else 0.0
    return {
        "initial_deposit_usdt": initial,
        "current_deposit_usdt": current,
        "drawdown_pct": round(drawdown_pct, 2),
        "updated_at": data["updated_at"],
    }


@app.get("/positions")
def positions() -> list[dict]:
    open_positions = []
    for symbol in SYMBOLS:
        position = storage.get_position(symbol)
        if position is not None and position.total_invested > 0:
            open_positions.append(asdict(position))
    return open_positions


@app.get("/trades")
def trades(symbol: Optional[str] = Query(None), limit: int = Query(50, ge=1, le=500)) -> list[dict]:
    return storage.get_trades(symbol=symbol, limit=limit)


@app.get("/logs")
def logs(symbol: Optional[str] = Query(None), limit: int = Query(100, ge=1, le=1000)) -> list[dict]:
    entries = storage.get_logs(symbol=symbol, limit=limit)
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
