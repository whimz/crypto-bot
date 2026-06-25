"""SQLite persistence for trades, positions and portfolio state."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional

from config import DB_PATH
from trading.risk import PositionState

_DB_PATH = Path(DB_PATH)


@dataclass(frozen=True)
class Trade:
    symbol: str
    action: str
    price: float
    amount_usdt: float
    timestamp: str
    reason: str
    confidence: float
    id: Optional[int] = None


@dataclass(frozen=True)
class LogEntry:
    symbol: str
    action: str
    confidence: float
    reason: str
    timestamp: str
    details: str = ""  # JSON-encoded indicator breakdown (RSI/EMA/MACD per timeframe)
    id: Optional[int] = None


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    """Connection-per-call: `sqlite3.Connection.__exit__` only commits/rolls back, it
    never closes the connection - without an explicit close() the file handle leaks,
    which on Windows leaves the .db file locked even after the caller is done with it."""
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def init_db() -> None:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                action TEXT NOT NULL,
                price REAL NOT NULL,
                amount_usdt REAL NOT NULL,
                timestamp TEXT NOT NULL,
                reason TEXT NOT NULL,
                confidence REAL NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS bot_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                symbol TEXT NOT NULL,
                action TEXT NOT NULL,
                confidence REAL NOT NULL,
                reason TEXT NOT NULL,
                details TEXT NOT NULL DEFAULT ''
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS positions (
                symbol TEXT PRIMARY KEY,
                avg_price REAL NOT NULL,
                total_invested REAL NOT NULL,
                dca_count INTEGER NOT NULL,
                peak_price REAL NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS portfolio (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                initial_deposit_usdt REAL NOT NULL,
                current_deposit_usdt REAL NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        # Seed the singleton portfolio row so get_portfolio() never has to handle "missing".
        conn.execute(
            """
            INSERT OR IGNORE INTO portfolio (id, initial_deposit_usdt, current_deposit_usdt, updated_at)
            VALUES (1, 0, 0, ?)
            """,
            (datetime.now(timezone.utc).isoformat(),),
        )


def save_trade(trade: Trade) -> int:
    with _connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO trades (symbol, action, price, amount_usdt, timestamp, reason, confidence)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (trade.symbol, trade.action, trade.price, trade.amount_usdt, trade.timestamp, trade.reason, trade.confidence),
        )
        return cursor.lastrowid


def save_log(entry: LogEntry) -> int:
    with _connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO bot_logs (timestamp, symbol, action, confidence, reason, details)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (entry.timestamp, entry.symbol, entry.action, entry.confidence, entry.reason, entry.details),
        )
        return cursor.lastrowid


def get_logs(symbol: Optional[str] = None, limit: int = 100) -> list[dict]:
    query = "SELECT id, timestamp, symbol, action, confidence, reason, details FROM bot_logs"
    params: tuple = ()
    if symbol:
        query += " WHERE symbol = ?"
        params = (symbol,)
    query += " ORDER BY id DESC LIMIT ?"
    params = params + (limit,)
    with _connect() as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def get_position(symbol: str) -> Optional[PositionState]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT symbol, avg_price, total_invested, dca_count, peak_price FROM positions WHERE symbol = ?",
            (symbol,),
        ).fetchone()
    if row is None:
        return None
    return PositionState(
        symbol=row["symbol"],
        avg_price=row["avg_price"],
        total_invested=row["total_invested"],
        dca_count=row["dca_count"],
        peak_price=row["peak_price"],
    )


def update_position(position: PositionState) -> None:
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO positions (symbol, avg_price, total_invested, dca_count, peak_price)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(symbol) DO UPDATE SET
                avg_price = excluded.avg_price,
                total_invested = excluded.total_invested,
                dca_count = excluded.dca_count,
                peak_price = excluded.peak_price
            """,
            (position.symbol, position.avg_price, position.total_invested, position.dca_count, position.peak_price),
        )


def get_trades(symbol: Optional[str] = None, limit: int = 50) -> list[dict]:
    query = "SELECT id, symbol, action, price, amount_usdt, timestamp, reason, confidence FROM trades"
    params: tuple = ()
    if symbol:
        query += " WHERE symbol = ?"
        params = (symbol,)
    query += " ORDER BY id DESC LIMIT ?"
    params = params + (limit,)
    with _connect() as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def get_portfolio() -> dict:
    with _connect() as conn:
        row = conn.execute(
            "SELECT initial_deposit_usdt, current_deposit_usdt, updated_at FROM portfolio WHERE id = 1"
        ).fetchone()
    return dict(row)


def update_portfolio(current_deposit: float) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        # First update after the singleton row's seed value (0) also establishes the initial deposit baseline.
        conn.execute(
            """
            UPDATE portfolio
            SET current_deposit_usdt = ?,
                initial_deposit_usdt = CASE WHEN initial_deposit_usdt = 0 THEN ? ELSE initial_deposit_usdt END,
                updated_at = ?
            WHERE id = 1
            """,
            (current_deposit, current_deposit, now),
        )


init_db()
