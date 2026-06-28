"""Bot state machine: scheduled trading loop over SYMBOLS, driven by APScheduler."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from analysis.indicators import calculate_ema, calculate_macd, calculate_rsi
from config import SYMBOLS
from data.binance import BinanceClient, BinanceClientError, Candle
from db import backup, storage
from notifications import telegram
from settings import get_settings
from trading.executor import execute_signal, update_peak_prices
from trading.portfolio import calculate_equity
from trading.risk import PositionState
from trading.signals import SignalResult, get_signal

logger = logging.getLogger(__name__)

CYCLE_MINUTES = 15
CONFIDENCE_THRESHOLD = 70
INACTIVITY_THRESHOLD_MINUTES = 20
INACTIVITY_ALERT_COOLDOWN_MINUTES = 60
DB_BACKUP_CRON = "0 3 * * *"  # 03:00 UTC daily

_scheduler: Optional[BackgroundScheduler] = None
_running = False
_last_cycle_at: Optional[datetime] = None
_last_inactivity_alert_at: Optional[datetime] = None


def _build_log_details(candles_15m: list[Candle], candles_1h: list[Candle]) -> str:
    """Full indicator breakdown (RSI/EMA/MACD per timeframe) for the activity log, independent
    of SignalResult's narrower public contract used by signals.py/risk.py."""
    details = {}
    for label, candles in (("15m", candles_15m), ("1h", candles_1h)):
        macd = calculate_macd(candles)
        details[label] = {
            "price": candles[-1].close,
            "rsi": round(calculate_rsi(candles), 2),
            "ema50": round(calculate_ema(candles, period=50), 2),
            "macd": {
                "line": round(macd.macd_line, 4),
                "signal": round(macd.signal_line, 4),
                "histogram": round(macd.histogram, 4),
            },
        }
    return json.dumps(details)


def _log_cycle(symbol: str, trade_signal: SignalResult, candles_15m: list[Candle], candles_1h: list[Candle]) -> None:
    try:
        details = _build_log_details(candles_15m, candles_1h)
    except ValueError:
        details = ""  # not enough candles for the full breakdown - still log the decision itself
    try:
        storage.save_log(
            storage.LogEntry(
                symbol=symbol,
                action=trade_signal.action,
                confidence=trade_signal.confidence,
                reason=trade_signal.reason,
                timestamp=datetime.now(timezone.utc).isoformat(),
                details=details,
            )
        )
    except Exception:
        logger.exception("[%s] Failed to write activity log entry", symbol)


def _log_error(symbol: str, reason: str) -> None:
    try:
        storage.save_log(
            storage.LogEntry(
                symbol=symbol,
                action="ERROR",
                confidence=0.0,
                reason=reason,
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
        )
    except Exception:
        logger.exception("[%s] Failed to write error log entry", symbol)


def get_last_cycle_at() -> Optional[str]:
    return _last_cycle_at.isoformat() if _last_cycle_at else None


def set_cycle_minutes(minutes: int) -> None:
    """Update the cycle interval and, if the bot is already running, reschedule the live job."""
    global CYCLE_MINUTES
    CYCLE_MINUTES = minutes
    if _scheduler is not None:
        _scheduler.reschedule_job("run_cycle", trigger="interval", minutes=minutes)


def _recover_stalled_run_cycle_job() -> None:
    """_check_inactivity (this function's caller) only gets to run at all because the
    scheduler thread itself is alive - so if we're here, run_cycle's specific interval
    trigger is the thing that stopped firing (seen in production after certain pause/resume
    sequences). Re-adding it with an immediate next_run_time is safe and idempotent: it only
    resets the schedule entry, it can't disrupt an execution already in flight."""
    if _scheduler is None:
        return
    try:
        _scheduler.add_job(
            run_cycle,
            "interval",
            minutes=CYCLE_MINUTES,
            next_run_time=datetime.now(),
            id="run_cycle",
            replace_existing=True,
        )
        logger.warning("run_cycle had stalled - rescheduled it")
        telegram.notify_error("Trading cycle had stalled and was rescheduled automatically")
    except Exception:
        logger.exception("Failed to reschedule stalled run_cycle job")


def _check_inactivity() -> None:
    global _last_inactivity_alert_at

    if _last_cycle_at is None:
        return
    inactive_minutes = (datetime.now(timezone.utc) - _last_cycle_at).total_seconds() / 60
    if inactive_minutes <= INACTIVITY_THRESHOLD_MINUTES:
        return

    now = datetime.now(timezone.utc)
    if _last_inactivity_alert_at is not None:
        since_last_alert = (now - _last_inactivity_alert_at).total_seconds() / 60
        if since_last_alert < INACTIVITY_ALERT_COOLDOWN_MINUTES:
            return

    _last_inactivity_alert_at = now
    logger.warning("Bot inactive for %.0f minutes", inactive_minutes)
    telegram.notify_inactive(inactive_minutes)
    _recover_stalled_run_cycle_job()


def run_cycle() -> None:
    global _last_cycle_at

    if not _running:
        return

    debug_logging = get_settings().debug_logging
    client = BinanceClient()
    for symbol in SYMBOLS:
        try:
            candles_15m = client.get_klines(symbol=symbol, interval="15m", limit=100)
            candles_1h = client.get_klines(symbol=symbol, interval="1h", limit=100)

            update_peak_prices(symbol, candles_15m[-1].close)

            trade_signal = get_signal(candles_15m, candles_1h)
            logger.info(
                "[%s] action=%s confidence=%.1f reason=%s",
                symbol, trade_signal.action, trade_signal.confidence, trade_signal.reason,
            )
            # HOLD is the vast majority of cycles - only log it when debug_logging is on, to
            # keep the Activity Log free of noise by default. BUY/SELL/errors always log.
            if trade_signal.action != "HOLD" or debug_logging:
                _log_cycle(symbol, trade_signal, candles_15m, candles_1h)

            if trade_signal.confidence > CONFIDENCE_THRESHOLD:
                execute_signal(symbol, trade_signal, candles_15m)
        except BinanceClientError as exc:
            logger.error("[%s] Binance error: %s", symbol, exc)
            telegram.notify_error(f"[{symbol}] Binance error: {exc}")
            _log_error(symbol, f"Binance error: {exc}")
        except Exception as exc:
            logger.exception("[%s] Unexpected error in trading cycle", symbol)
            telegram.notify_error(f"[{symbol}] Unexpected error in trading cycle, see logs")
            _log_error(symbol, f"Unexpected error in trading cycle: {exc}")

    _last_cycle_at = datetime.now(timezone.utc)
    try:
        storage.save_portfolio_snapshot(calculate_equity(client).equity_usdt)
    except Exception:
        logger.exception("Failed to save portfolio history snapshot")

    logger.info("Cycle complete for %s", ", ".join(SYMBOLS))


def _close_all_positions() -> None:
    client = BinanceClient()
    closed = []
    for symbol in SYMBOLS:
        position = storage.get_position(symbol)
        if position is None or position.total_invested <= 0:
            continue
        try:
            client.place_market_order(symbol=symbol, side="SELL", quote_order_qty=position.total_invested)
        except BinanceClientError as exc:
            logger.error("Failed to close position for %s: %s", symbol, exc)
            telegram.notify_error(f"Failed to close {symbol} position: {exc}")
            continue
        storage.update_position(PositionState(symbol=symbol, avg_price=0.0, total_invested=0.0, dca_count=0, peak_price=0.0))
        closed.append(symbol)

    if closed:
        telegram.send_message(f"✅ Closed all positions: {', '.join(closed)}")
    else:
        telegram.send_message("✅ /closeall: no open positions to close")


def _handle_stop_command() -> None:
    stop_bot(reason="Stopped via /stop command")


def _handle_closeall_command() -> None:
    logger.info("Closing all positions via /closeall command")
    _close_all_positions()


def start_bot() -> None:
    """Idempotent: safe to call again (e.g. from POST /bot/start) while already running."""
    global _scheduler, _running

    if _running:
        logger.info("start_bot called but the bot is already running")
        return

    storage.init_db()
    telegram.register_command_handler("/stop", _handle_stop_command)
    telegram.register_command_handler("/closeall", _handle_closeall_command)
    telegram.start_polling()

    if _scheduler is None:
        _scheduler = BackgroundScheduler()
        _scheduler.add_job(run_cycle, "interval", minutes=CYCLE_MINUTES, next_run_time=datetime.now(), id="run_cycle")
        _scheduler.add_job(_check_inactivity, "interval", minutes=5, id="check_inactivity")
        _scheduler.add_job(
            backup.run_backup,
            CronTrigger.from_crontab(DB_BACKUP_CRON, timezone="UTC"),
            id="db_backup",
        )
        _scheduler.start()
    else:
        _scheduler.resume()

    _running = True
    logger.info("Bot started, symbols=%s, cycle=%dm", SYMBOLS, CYCLE_MINUTES)
    telegram.send_message("\U0001F680 Бот запущен")


def stop_bot(reason: str = "Stopped via API") -> None:
    """Pause the trading loop without tearing down the scheduler/telegram polling."""
    global _running

    if not _running:
        logger.info("stop_bot called but the bot is not running")
        return

    _running = False
    if _scheduler is not None:
        _scheduler.pause()
    logger.info("Bot stopped: %s", reason)
    telegram.notify_stop(reason)


def shutdown_bot() -> None:
    """Full teardown for process exit (Ctrl+C / server stopping)."""
    global _scheduler, _running

    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
    telegram.stop_polling()
    if _running:
        telegram.notify_stop("Bot shut down")
    _running = False
