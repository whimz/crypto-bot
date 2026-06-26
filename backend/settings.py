"""Runtime-configurable strategy parameters, persisted in SQLite (settings table).

Defaults live here as a dataclass; persisted overrides are merged on top. Applying a
settings change means writing the value into the module-level globals that risk.py,
signals.py and scheduler.py read as plain constants - so trading logic itself stays
untouched and keeps passing its existing tests.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, fields

from db import storage

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Settings:
    rsi_oversold: float = 35.0
    rsi_overbought: float = 65.0
    confidence_threshold: float = 70.0
    trailing_stop_pct: float = 0.07
    max_allocation_pct: float = 0.40
    max_dca_count: int = 3
    global_stop_pct: float = 0.20
    cycle_minutes: int = 15
    notify_trades: bool = True
    notify_errors: bool = True
    notify_stops: bool = True
    notify_inactive: bool = True


_BOOL_FIELDS = {"notify_trades", "notify_errors", "notify_stops", "notify_inactive"}
_INT_FIELDS = {"max_dca_count", "cycle_minutes"}
_FIELD_NAMES = {f.name for f in fields(Settings)}


def _coerce(key: str, value) -> bool | int | float:
    if key in _BOOL_FIELDS:
        return value if isinstance(value, bool) else str(value).strip().lower() in ("1", "true", "yes", "on")
    if key in _INT_FIELDS:
        return int(value)
    return float(value)


def get_settings() -> Settings:
    overrides = storage.get_settings()
    values = asdict(Settings())
    for key, raw in overrides.items():
        if key in _FIELD_NAMES:
            values[key] = _coerce(key, raw)
    return Settings(**values)


def update_settings(updates: dict) -> Settings:
    unknown = set(updates) - _FIELD_NAMES
    if unknown:
        raise ValueError(f"Unknown settings: {sorted(unknown)}")
    coerced = {key: _coerce(key, value) for key, value in updates.items()}
    storage.save_settings({key: str(value) for key, value in coerced.items()})
    new_settings = get_settings()
    apply_settings(new_settings)
    return new_settings


def apply_settings(settings: Settings) -> None:
    """Push persisted settings into the modules that read them as plain globals."""
    import scheduler
    import trading.risk as risk
    import trading.signals as signals

    signals.RSI_OVERSOLD = settings.rsi_oversold
    signals.RSI_OVERBOUGHT = settings.rsi_overbought
    risk.TRAILING_STOP_LOSS_PCT = settings.trailing_stop_pct
    risk.MAX_SYMBOL_ALLOCATION_PCT = settings.max_allocation_pct
    risk.MAX_CONSECUTIVE_DCA = settings.max_dca_count
    risk.GLOBAL_DRAWDOWN_STOP_PCT = settings.global_stop_pct
    scheduler.CONFIDENCE_THRESHOLD = settings.confidence_threshold
    scheduler.set_cycle_minutes(settings.cycle_minutes)
    logger.info("Settings applied: %s", asdict(settings))
