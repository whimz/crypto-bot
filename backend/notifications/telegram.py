"""Telegram notifications and incoming command polling (/stop, /closeall)."""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Optional

import requests

from config import TELEGRAM_CHAT_ID, TELEGRAM_TOKEN

logger = logging.getLogger(__name__)

API_URL = "https://api.telegram.org/bot{token}/{method}"
SUPPORTED_COMMANDS = ("/stop", "/closeall")

CommandHandler = Callable[[], None]
_command_handlers: dict[str, CommandHandler] = {}

_polling_thread: Optional[threading.Thread] = None
_stop_event = threading.Event()


def _is_configured() -> bool:
    return bool(TELEGRAM_TOKEN and TELEGRAM_CHAT_ID)


def _api_url(method: str) -> str:
    return API_URL.format(token=TELEGRAM_TOKEN, method=method)


def send_message(text: str) -> bool:
    if not _is_configured():
        logger.warning("Telegram is not configured (missing TELEGRAM_TOKEN/TELEGRAM_CHAT_ID); message not sent: %s", text)
        return False
    try:
        response = requests.post(
            _api_url("sendMessage"),
            data={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"},
            timeout=10,
        )
        response.raise_for_status()
        return True
    except requests.RequestException as exc:
        logger.error("Failed to send Telegram message: %s", exc)
        return False


def notify_trade(action: str, symbol: str, price: float, amount_usdt: float, reason: str, confidence: float) -> None:
    emoji = {"BUY": "\U0001F7E2", "SELL": "\U0001F534"}.get(action.upper(), "⚪")
    text = (
        f"{emoji} <b>{action.upper()}</b> {symbol}\n"
        f"Price: {price:.2f}\n"
        f"Amount: {amount_usdt:.2f} USDT\n"
        f"Confidence: {confidence:.1f}%\n"
        f"Reason: {reason}"
    )
    send_message(text)


def notify_error(error_text: str) -> None:
    send_message(f"⚠️ <b>ERROR</b>\n{error_text}")


def notify_stop(reason: str) -> None:
    send_message(f"\U0001F6D1 <b>BOT STOPPED</b>\n{reason}")


def register_command_handler(command: str, handler: CommandHandler) -> None:
    """Register the action to run when `command` (e.g. "/stop") arrives via Telegram."""
    if command not in SUPPORTED_COMMANDS:
        raise ValueError(f"Unsupported command: {command!r}. Supported: {SUPPORTED_COMMANDS}")
    _command_handlers[command] = handler


def _handle_update(update: dict) -> None:
    message = update.get("message", {})
    chat_id = str(message.get("chat", {}).get("id", ""))
    if chat_id != str(TELEGRAM_CHAT_ID):
        return

    text = (message.get("text") or "").strip()
    command = text.split()[0] if text else ""
    handler = _command_handlers.get(command)
    if handler is None:
        if command in SUPPORTED_COMMANDS:
            logger.warning("Received %s but no handler is registered", command)
        return

    try:
        handler()
    except Exception:
        logger.exception("Handler for command %s raised an exception", command)


def _poll_loop(poll_timeout: int = 30) -> None:
    offset = 0
    while not _stop_event.is_set():
        try:
            response = requests.get(
                _api_url("getUpdates"),
                params={"offset": offset, "timeout": poll_timeout},
                timeout=poll_timeout + 5,
            )
            response.raise_for_status()
            for update in response.json().get("result", []):
                offset = update["update_id"] + 1
                _handle_update(update)
        except requests.RequestException as exc:
            logger.error("Telegram polling error: %s", exc)
            time.sleep(5)


def start_polling() -> None:
    """Start listening for /stop and /closeall commands in a background thread."""
    global _polling_thread
    if not _is_configured():
        logger.warning("Telegram is not configured; command polling disabled")
        return
    if _polling_thread is not None and _polling_thread.is_alive():
        return

    _stop_event.clear()
    _polling_thread = threading.Thread(target=_poll_loop, daemon=True, name="telegram-polling")
    _polling_thread.start()


def stop_polling() -> None:
    _stop_event.set()
    if _polling_thread is not None:
        _polling_thread.join(timeout=5)
