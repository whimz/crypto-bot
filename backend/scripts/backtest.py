"""Backtest trading/signals.get_signal() against real Binance history.

Standalone diagnostic script - NOT part of the production scheduler loop and does not
change signals.py/risk.py thresholds. Run from anywhere with:

    python backend/scripts/backtest.py

Fetches ~90 days of 15m/1h klines per symbol in config.SYMBOLS, replays get_signal() at
every 15m close using the same rolling 100-candle lookback window run_cycle() uses live,
and reports how often each action would have fired - including "near miss" BUY/SELL
signals whose confidence didn't clear the execution threshold.
"""

from __future__ import annotations

import sys
from bisect import bisect_right
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from config import SYMBOLS  # noqa: E402
from data.binance import BinanceClient, BinanceClientError, Candle  # noqa: E402
from trading.signals import get_signal  # noqa: E402

BACKTEST_DAYS = 90
WARMUP_BUFFER_DAYS = 5  # extra history fetched so the first evaluations have a full lookback
LOOKBACK_CANDLES = 100  # mirrors run_cycle()'s client.get_klines(..., limit=100)
FETCH_BATCH_LIMIT = 1000  # Binance's max klines per request
EXECUTION_CONFIDENCE_THRESHOLD = 70  # scheduler.CONFIDENCE_THRESHOLD's Moderate-preset default
NEAR_MISS_CONFIDENCE_FLOOR = 60.0  # signals.py never returns a BUY/SELL confidence below this
MAX_PRINTED_EVENTS = 20  # cap detail lines per bucket so the summary stays readable

INTERVAL_MS = {"15m": 15 * 60 * 1000, "1h": 60 * 60 * 1000}


@dataclass
class Evaluation:
    timestamp: datetime
    action: str
    confidence: float
    reason: str


def _fetch_history(client: BinanceClient, symbol: str, interval: str, since_ms: int) -> list[Candle]:
    """Page through Binance klines from `since_ms` to now (max FETCH_BATCH_LIMIT per request)."""
    candles: list[Candle] = []
    cursor = since_ms
    while True:
        batch = client.get_klines(symbol=symbol, interval=interval, limit=FETCH_BATCH_LIMIT, start_time=cursor)
        if not batch:
            break
        candles.extend(batch)
        cursor = batch[-1].close_time + 1
        if len(batch) < FETCH_BATCH_LIMIT:
            break
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    return [c for c in candles if c.close_time <= now_ms]  # drop a still-forming final candle


def _aligned_1h_window(candles_1h: list[Candle], close_times_1h: list[int], as_of_close_time: int) -> list[Candle]:
    """The last LOOKBACK_CANDLES 1h candles that had already closed by `as_of_close_time`."""
    end_idx = bisect_right(close_times_1h, as_of_close_time)
    start_idx = max(0, end_idx - LOOKBACK_CANDLES)
    return candles_1h[start_idx:end_idx]


def _evaluate_symbol(client: BinanceClient, symbol: str) -> list[Evaluation]:
    since_ms = int((datetime.now(timezone.utc) - timedelta(days=BACKTEST_DAYS + WARMUP_BUFFER_DAYS)).timestamp() * 1000)
    cutoff_ms = int((datetime.now(timezone.utc) - timedelta(days=BACKTEST_DAYS)).timestamp() * 1000)

    print(f"[{symbol}] fetching {BACKTEST_DAYS}+{WARMUP_BUFFER_DAYS}d of 15m/1h history...")
    candles_15m = _fetch_history(client, symbol, "15m", since_ms)
    candles_1h = _fetch_history(client, symbol, "1h", since_ms)
    close_times_1h = [c.close_time for c in candles_1h]

    evaluations: list[Evaluation] = []
    for i in range(LOOKBACK_CANDLES - 1, len(candles_15m)):
        candle = candles_15m[i]
        if candle.open_time < cutoff_ms:
            continue
        window_15m = candles_15m[i - LOOKBACK_CANDLES + 1 : i + 1]
        window_1h = _aligned_1h_window(candles_1h, close_times_1h, candle.close_time)
        if len(window_1h) < LOOKBACK_CANDLES:
            continue
        try:
            result = get_signal(window_15m, window_1h)
        except ValueError:
            continue
        evaluations.append(
            Evaluation(
                timestamp=datetime.fromtimestamp(candle.open_time / 1000, tz=timezone.utc),
                action=result.action,
                confidence=result.confidence,
                reason=result.reason,
            )
        )
    return evaluations


def _print_bucket(title: str, events: list[Evaluation]) -> None:
    print(f"  {title}: {len(events)}")
    for ev in events[:MAX_PRINTED_EVENTS]:
        print(f"    {ev.timestamp.isoformat()}  {ev.action} confidence={ev.confidence:.1f}  {ev.reason}")
    if len(events) > MAX_PRINTED_EVENTS:
        print(f"    ... and {len(events) - MAX_PRINTED_EVENTS} more")


def _print_summary(symbol: str, evaluations: list[Evaluation]) -> None:
    print(f"\n=== {symbol}: {len(evaluations)} evaluations over the last {BACKTEST_DAYS} days ===")
    if not evaluations:
        print("  (no evaluations - insufficient history)")
        return

    holds = [ev for ev in evaluations if ev.action == "HOLD"]
    signals = [ev for ev in evaluations if ev.action != "HOLD"]
    would_execute = [ev for ev in signals if ev.confidence > EXECUTION_CONFIDENCE_THRESHOLD]
    near_misses = [
        ev for ev in signals if NEAR_MISS_CONFIDENCE_FLOOR <= ev.confidence <= EXECUTION_CONFIDENCE_THRESHOLD
    ]

    print(f"  HOLD (no aligned RSI+EMA pattern): {len(holds)}")
    _print_bucket(f"Would have executed (confidence > {EXECUTION_CONFIDENCE_THRESHOLD})", would_execute)
    _print_bucket(
        f"Near misses (pattern matched, confidence {NEAR_MISS_CONFIDENCE_FLOOR:.0f}-{EXECUTION_CONFIDENCE_THRESHOLD})",
        near_misses,
    )


def main() -> None:
    client = BinanceClient()
    for symbol in SYMBOLS:
        try:
            evaluations = _evaluate_symbol(client, symbol)
        except BinanceClientError as exc:
            print(f"[{symbol}] failed to fetch history: {exc}")
            continue
        _print_summary(symbol, evaluations)


if __name__ == "__main__":
    main()
