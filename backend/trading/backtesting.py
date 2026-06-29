"""Reusable backtest simulation: replays the real signals.get_signal()/risk.check_risk()/
risk.check_take_profit() functions against historical Binance candles, with a simulated
shared deposit across all of config.SYMBOLS - the same way scheduler.run_cycle() drives them
live, just against the past instead of in real time.

Used by both backend/scripts/backtest.py (CLI, prints to stdout) and api.py's /backtest route
(returns structured data) - the simulation/aggregation logic itself lives only here, so
neither consumer duplicates it.
"""

from __future__ import annotations

import statistics
import threading
from bisect import bisect_left, bisect_right
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

import trading.risk as risk
import trading.signals as signals
from config import SYMBOLS
from data.binance import BinanceClient, Candle
from trading.risk import PositionState, check_risk, check_take_profit
from trading.signals import SignalResult, get_signal

SIMULATION_DAYS = 30  # shorter than the diagnostic script's 90d - x8 configs adds up fast,
# and a long synchronous HTTP request risks a proxy timeout when triggered from the UI
WARMUP_BUFFER_DAYS = 5  # extra history fetched so the first evaluations have a full lookback
LOOKBACK_CANDLES = 100  # mirrors run_cycle()'s client.get_klines(..., limit=100)
FETCH_BATCH_LIMIT = 1000  # Binance's max klines per request
INTERVAL_MS = {"15m": 15 * 60 * 1000, "1h": 60 * 60 * 1000}

SIMULATED_DEPOSIT_USDT = 100.0  # matches the project's real Testnet deposit size
TARGET_WEEKLY_RETURN_USDT = 10.0  # context's stated goal: ~$10/week on a $100 deposit

TAKE_PROFIT_CANDIDATES_PCT = [0.0, 0.02, 0.03, 0.05]  # 0.0 = disabled (today's baseline)
REQUIRE_EMA_TREND_CANDIDATES = [True, False]

# signals.REQUIRE_EMA_TREND/risk.TAKE_PROFIT_PCT are mutated for the duration of a comparison
# run (see run_comparison) so the simulation can reuse the real decision functions unchanged.
# This lock keeps two concurrent comparison requests from stepping on each other's overrides;
# it does not protect against the live scheduler thread reading these globals mid-run_cycle(),
# which is an accepted, narrow race for a manually-triggered diagnostic feature.
_CONFIG_OVERRIDE_LOCK = threading.Lock()


@dataclass(frozen=True)
class SimulationConfig:
    take_profit_pct: float
    require_ema_trend: bool
    label: str


@dataclass(frozen=True)
class SimulatedTrade:
    symbol: str
    action: str  # "BUY" or "SELL"
    timestamp: datetime
    price: float
    amount_usdt: float
    realized_pnl_usdt: Optional[float] = None  # set on SELL only


@dataclass(frozen=True)
class WeeklyReturn:
    week_start: datetime
    return_usdt: float


@dataclass(frozen=True)
class SimulationResult:
    config: SimulationConfig
    initial_deposit_usdt: float
    final_equity_usdt: float
    trades: list[SimulatedTrade] = field(default_factory=list)
    weekly_returns: list[WeeklyReturn] = field(default_factory=list)


@dataclass(frozen=True)
class ComparisonRow:
    label: str
    config: SimulationConfig
    trade_count: int
    win_rate_pct: Optional[float]
    avg_weekly_return_usdt: float
    median_weekly_return_usdt: float
    worst_weekly_return_usdt: float
    hint: str


def build_default_configs() -> list[SimulationConfig]:
    """The comparison grid: every take-profit candidate crossed with the EMA filter toggle."""
    configs = []
    for require_ema in REQUIRE_EMA_TREND_CANDIDATES:
        for take_profit_pct in TAKE_PROFIT_CANDIDATES_PCT:
            label = (
                f"TP={take_profit_pct * 100:.0f}%, EMA filter={'on' if require_ema else 'off'}"
            )
            configs.append(
                SimulationConfig(take_profit_pct=take_profit_pct, require_ema_trend=require_ema, label=label)
            )
    return configs


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


@dataclass(frozen=True)
class _SymbolHistory:
    candles_15m: list[Candle]
    open_times_15m: list[int]
    candles_1h: list[Candle]
    close_times_1h: list[int]


def fetch_comparison_history(client: Optional[BinanceClient] = None) -> dict[str, _SymbolHistory]:
    """Fetched once and replayed across every SimulationConfig - the expensive network part
    of a comparison run, shared so 8 combos don't mean 8x the Binance requests."""
    client = client or BinanceClient()
    since_ms = int((datetime.now(timezone.utc) - timedelta(days=SIMULATION_DAYS + WARMUP_BUFFER_DAYS)).timestamp() * 1000)

    history: dict[str, _SymbolHistory] = {}
    for symbol in SYMBOLS:
        candles_15m = _fetch_history(client, symbol, "15m", since_ms)
        candles_1h = _fetch_history(client, symbol, "1h", since_ms)
        history[symbol] = _SymbolHistory(
            candles_15m=candles_15m,
            open_times_15m=[c.open_time for c in candles_15m],
            candles_1h=candles_1h,
            close_times_1h=[c.close_time for c in candles_1h],
        )
    return history


def _empty_position(symbol: str) -> PositionState:
    return PositionState(symbol=symbol, avg_price=0.0, total_invested=0.0, dca_count=0, peak_price=0.0)


def _update_peak_price(position: PositionState, current_price: float) -> PositionState:
    """Mirrors executor.update_peak_prices() exactly, including that it runs even on a flat
    position (peak_price drifting while no position is open is the live bot's real behavior,
    not something this backtest should "fix")."""
    if current_price <= position.peak_price:
        return position
    return PositionState(
        symbol=position.symbol,
        avg_price=position.avg_price,
        total_invested=position.total_invested,
        dca_count=position.dca_count,
        peak_price=current_price,
    )


def _weekly_returns(equity_curve: list[tuple[datetime, float]], initial_deposit: float) -> list[WeeklyReturn]:
    if not equity_curve:
        return []
    last_equity_by_week: dict[datetime, float] = {}
    for timestamp, equity in equity_curve:
        week_start = timestamp - timedelta(days=timestamp.weekday(), hours=timestamp.hour, minutes=timestamp.minute)
        last_equity_by_week[week_start] = equity  # overwritten chronologically -> ends up last-of-week

    returns: list[WeeklyReturn] = []
    previous_equity = initial_deposit
    for week_start in sorted(last_equity_by_week):
        equity = last_equity_by_week[week_start]
        returns.append(WeeklyReturn(week_start=week_start, return_usdt=round(equity - previous_equity, 2)))
        previous_equity = equity
    return returns


def _simulate(config: SimulationConfig, history: dict[str, _SymbolHistory], cutoff_ms: int) -> SimulationResult:
    """Walks every symbol's 15m timestamps in chronological order, exactly mirroring
    run_cycle()'s per-cycle, per-symbol loop, but against historical candles with a
    simulated shared cash balance instead of placing real orders."""
    cash = SIMULATED_DEPOSIT_USDT
    positions: dict[str, PositionState] = {symbol: _empty_position(symbol) for symbol in history}
    last_known_price: dict[str, float] = {}
    trades: list[SimulatedTrade] = []
    equity_curve: list[tuple[datetime, float]] = []

    timestamps = sorted(
        {
            open_time
            for h in history.values()
            for open_time in h.open_times_15m
            if open_time >= cutoff_ms
        }
    )

    for ts in timestamps:
        for symbol, h in history.items():
            idx = bisect_left(h.open_times_15m, ts)
            if idx >= len(h.open_times_15m) or h.open_times_15m[idx] != ts:
                continue  # this symbol has no candle at exactly this timestamp

            candle = h.candles_15m[idx]
            last_known_price[symbol] = candle.close
            position = _update_peak_price(positions[symbol], candle.close)
            positions[symbol] = position

            if idx < LOOKBACK_CANDLES - 1:
                continue
            window_15m = h.candles_15m[idx - LOOKBACK_CANDLES + 1 : idx + 1]
            window_1h = _aligned_1h_window(h.candles_1h, h.close_times_1h, candle.close_time)
            if len(window_1h) < LOOKBACK_CANDLES:
                continue

            try:
                trade_signal = get_signal(window_15m, window_1h)
            except ValueError:
                continue

            if check_take_profit(position, candle.close):
                trade_signal = SignalResult(
                    action="SELL", confidence=100.0, reason="take-profit",
                    rsi_15m=trade_signal.rsi_15m, rsi_1h=trade_signal.rsi_1h,
                )

            if trade_signal.action == "HOLD":
                continue

            # deposit_usdt is the fixed initial deposit, not a live-equity figure: that's
            # exactly what the real bot's risk.check_risk() is fed today (current_deposit_usdt
            # is only ever set manually via "Set Deposit" and never updated by trading) - the
            # backtest must replay that same behavior to predict the real bot accurately.
            risk_result = check_risk(
                symbol=symbol, current_price=candle.close, signal=trade_signal, position=position,
                deposit_usdt=SIMULATED_DEPOSIT_USDT, initial_deposit_usdt=SIMULATED_DEPOSIT_USDT,
            )
            if not risk_result.allowed:
                continue

            timestamp = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
            if trade_signal.action == "BUY":
                order_size = min(risk_result.order_size_usdt, round(cash, 2))
                if order_size <= 0:
                    continue
                prior_qty = position.total_invested / position.avg_price if position.avg_price > 0 else 0.0
                filled_qty = order_size / candle.close
                new_total_invested = round(position.total_invested + order_size, 2)
                new_qty = prior_qty + filled_qty
                positions[symbol] = PositionState(
                    symbol=symbol,
                    avg_price=new_total_invested / new_qty if new_qty > 0 else candle.close,
                    total_invested=new_total_invested,
                    dca_count=position.dca_count + 1,
                    peak_price=max(position.peak_price, candle.close),
                )
                cash = round(cash - order_size, 2)
                trades.append(SimulatedTrade(symbol=symbol, action="BUY", timestamp=timestamp, price=candle.close, amount_usdt=order_size))
            else:  # SELL closes the whole position
                qty = position.total_invested / position.avg_price if position.avg_price > 0 else 0.0
                proceeds = round(qty * candle.close, 2)
                realized_pnl = round(proceeds - position.total_invested, 2)
                cash = round(cash + proceeds, 2)
                positions[symbol] = _empty_position(symbol)
                trades.append(
                    SimulatedTrade(
                        symbol=symbol, action="SELL", timestamp=timestamp, price=candle.close,
                        amount_usdt=proceeds, realized_pnl_usdt=realized_pnl,
                    )
                )

        market_value = sum(
            (p.total_invested / p.avg_price) * last_known_price.get(symbol, p.avg_price)
            for symbol, p in positions.items()
            if p.total_invested > 0
        )
        equity_curve.append((datetime.fromtimestamp(ts / 1000, tz=timezone.utc), round(cash + market_value, 2)))

    final_equity = equity_curve[-1][1] if equity_curve else SIMULATED_DEPOSIT_USDT
    return SimulationResult(
        config=config,
        initial_deposit_usdt=SIMULATED_DEPOSIT_USDT,
        final_equity_usdt=final_equity,
        trades=trades,
        weekly_returns=_weekly_returns(equity_curve, SIMULATED_DEPOSIT_USDT),
    )


def _build_hint(trade_count: int, avg_weekly_return_usdt: float) -> str:
    if trade_count == 0:
        return "Нет сделок за период - условия слишком строгие, статистика недостоверна"
    if avg_weekly_return_usdt >= TARGET_WEEKLY_RETURN_USDT:
        return f"В среднем достигает цели ~${TARGET_WEEKLY_RETURN_USDT:.0f}/неделю"
    if avg_weekly_return_usdt > 0:
        return f"В среднем прибыльно, но ниже цели ~${TARGET_WEEKLY_RETURN_USDT:.0f}/неделю"
    return "В среднем убыточно за период - не рекомендуется для реальной торговли"


def summarize(result: SimulationResult) -> ComparisonRow:
    sells = [t for t in result.trades if t.action == "SELL"]
    wins = [t for t in sells if (t.realized_pnl_usdt or 0.0) > 0]
    win_rate_pct = round(len(wins) / len(sells) * 100, 1) if sells else None

    weekly_values = [w.return_usdt for w in result.weekly_returns]
    avg_weekly = round(statistics.mean(weekly_values), 2) if weekly_values else 0.0
    median_weekly = round(statistics.median(weekly_values), 2) if weekly_values else 0.0
    worst_weekly = round(min(weekly_values), 2) if weekly_values else 0.0

    return ComparisonRow(
        label=result.config.label,
        config=result.config,
        trade_count=len(sells),
        win_rate_pct=win_rate_pct,
        avg_weekly_return_usdt=avg_weekly,
        median_weekly_return_usdt=median_weekly,
        worst_weekly_return_usdt=worst_weekly,
        hint=_build_hint(len(sells), avg_weekly),
    )


def run_comparison(
    client: Optional[BinanceClient] = None,
    configs: Optional[list[SimulationConfig]] = None,
    history: Optional[dict[str, _SymbolHistory]] = None,
) -> list[ComparisonRow]:
    """Fetches history once (unless `history` is already supplied, e.g. by a caller that
    wants to reuse it) and replays every config against it, restoring the real
    signals.REQUIRE_EMA_TREND/risk.TAKE_PROFIT_PCT globals afterwards either way."""
    configs = configs if configs is not None else build_default_configs()
    history = history if history is not None else fetch_comparison_history(client)
    cutoff_ms = int((datetime.now(timezone.utc) - timedelta(days=SIMULATION_DAYS)).timestamp() * 1000)

    rows: list[ComparisonRow] = []
    with _CONFIG_OVERRIDE_LOCK:
        original_require_ema = signals.REQUIRE_EMA_TREND
        original_take_profit = risk.TAKE_PROFIT_PCT
        try:
            for config in configs:
                signals.REQUIRE_EMA_TREND = config.require_ema_trend
                risk.TAKE_PROFIT_PCT = config.take_profit_pct
                result = _simulate(config, history, cutoff_ms)
                rows.append(summarize(result))
        finally:
            signals.REQUIRE_EMA_TREND = original_require_ema
            risk.TAKE_PROFIT_PCT = original_take_profit
    return rows
