import pytest

from trading.risk import (
    GLOBAL_DRAWDOWN_STOP_PCT,
    MAX_CONSECUTIVE_DCA,
    MAX_SYMBOL_ALLOCATION_PCT,
    PositionState,
    check_risk,
    check_take_profit,
)
from trading.signals import SignalResult

SYMBOL = "BTCUSDT"


def _signal(action, rsi_15m=30.0, rsi_1h=30.0, confidence=80.0):
    return SignalResult(action=action, confidence=confidence, reason="test", rsi_15m=rsi_15m, rsi_1h=rsi_1h)


def _fresh_position():
    return PositionState(symbol=SYMBOL, avg_price=0.0, total_invested=0.0, dca_count=0, peak_price=0.0)


def test_hold_signal_is_never_allowed():
    result = check_risk(SYMBOL, 100.0, _signal("HOLD"), _fresh_position(), deposit_usdt=1000.0, initial_deposit_usdt=1000.0)
    assert result.allowed is False
    assert result.order_size_usdt == 0.0


def test_sell_signal_is_always_allowed_and_sized_to_invested_amount():
    position = PositionState(symbol=SYMBOL, avg_price=100.0, total_invested=250.0, dca_count=1, peak_price=120.0)
    result = check_risk(SYMBOL, 100.0, _signal("SELL"), position, deposit_usdt=1000.0, initial_deposit_usdt=1000.0)
    assert result.allowed is True
    assert result.order_size_usdt == 250.0


def test_sell_order_size_is_rounded_to_avoid_binance_precision_error():
    # 0.1 + 0.2 != 0.3 in IEEE754 - exactly the kind of noise repeated DCA fills accumulate
    # into total_invested. Binance rejects unrounded quoteOrderQty with -1111.
    position = PositionState(symbol=SYMBOL, avg_price=100.0, total_invested=0.1 + 0.2, dca_count=1, peak_price=120.0)
    result = check_risk(SYMBOL, 100.0, _signal("SELL"), position, deposit_usdt=1000.0, initial_deposit_usdt=1000.0)
    assert result.order_size_usdt == 0.3
    assert len(str(result.order_size_usdt).split(".")[-1]) <= 2


def test_sell_bypasses_every_block():
    # Even with a maxed-out DCA count, a triggered trailing stop and a breached global
    # drawdown, closing a position must still be allowed - exits take priority.
    position = PositionState(symbol=SYMBOL, avg_price=100.0, total_invested=300.0, dca_count=10, peak_price=200.0)
    result = check_risk(SYMBOL, 50.0, _signal("SELL"), position, deposit_usdt=500.0, initial_deposit_usdt=1000.0)
    assert result.allowed is True
    assert result.order_size_usdt == 300.0


@pytest.mark.parametrize("deposit_usdt", [799.9, 800.0])
def test_global_stop_blocks_buy_at_or_above_threshold(deposit_usdt):
    result = check_risk(
        SYMBOL, 100.0, _signal("BUY"), _fresh_position(), deposit_usdt=deposit_usdt, initial_deposit_usdt=1000.0
    )
    drawdown = (1000.0 - deposit_usdt) / 1000.0
    assert drawdown >= GLOBAL_DRAWDOWN_STOP_PCT
    assert result.allowed is False
    assert "Global stop" in result.reason


def test_global_stop_does_not_block_buy_below_threshold():
    result = check_risk(SYMBOL, 100.0, _signal("BUY"), _fresh_position(), deposit_usdt=810.0, initial_deposit_usdt=1000.0)
    assert result.allowed is True


def test_trailing_stop_blocks_buy_when_price_drops_7_percent_from_peak():
    position = PositionState(symbol=SYMBOL, avg_price=90.0, total_invested=50.0, dca_count=0, peak_price=100.0)
    result = check_risk(SYMBOL, 92.0, _signal("BUY"), position, deposit_usdt=1000.0, initial_deposit_usdt=1000.0)
    assert result.allowed is False
    assert "Trailing stop-loss" in result.reason


def test_trailing_stop_does_not_block_buy_under_threshold():
    position = PositionState(symbol=SYMBOL, avg_price=90.0, total_invested=50.0, dca_count=0, peak_price=100.0)
    result = check_risk(SYMBOL, 94.0, _signal("BUY"), position, deposit_usdt=1000.0, initial_deposit_usdt=1000.0)
    assert result.allowed is True


def test_trailing_stop_is_ignored_when_no_peak_recorded_yet():
    # peak_price == 0.0 means "no position/no peak yet" - must not be mistaken for a 100% drop.
    result = check_risk(SYMBOL, 1.0, _signal("BUY"), _fresh_position(), deposit_usdt=1000.0, initial_deposit_usdt=1000.0)
    assert result.allowed is True


def test_max_dca_blocks_further_buys():
    position = PositionState(symbol=SYMBOL, avg_price=100.0, total_invested=50.0, dca_count=MAX_CONSECUTIVE_DCA, peak_price=0.0)
    result = check_risk(SYMBOL, 100.0, _signal("BUY"), position, deposit_usdt=1000.0, initial_deposit_usdt=1000.0)
    assert result.allowed is False
    assert "DCA" in result.reason


def test_below_max_dca_does_not_block():
    position = PositionState(
        symbol=SYMBOL, avg_price=100.0, total_invested=50.0, dca_count=MAX_CONSECUTIVE_DCA - 1, peak_price=0.0
    )
    result = check_risk(SYMBOL, 100.0, _signal("BUY"), position, deposit_usdt=1000.0, initial_deposit_usdt=1000.0)
    assert result.allowed is True


def test_allocation_cap_blocks_buy_when_fully_allocated():
    cap = MAX_SYMBOL_ALLOCATION_PCT * 1000.0
    position = PositionState(symbol=SYMBOL, avg_price=100.0, total_invested=cap, dca_count=0, peak_price=0.0)
    result = check_risk(SYMBOL, 100.0, _signal("BUY"), position, deposit_usdt=1000.0, initial_deposit_usdt=1000.0)
    assert result.allowed is False
    assert "allocation cap" in result.reason


def test_allocation_cap_limits_order_size_to_remaining_allowance():
    cap = MAX_SYMBOL_ALLOCATION_PCT * 1000.0  # 400
    position = PositionState(symbol=SYMBOL, avg_price=100.0, total_invested=cap - 10.0, dca_count=0, peak_price=0.0)
    result = check_risk(SYMBOL, 100.0, _signal("BUY", rsi_15m=40.0, rsi_1h=40.0), position, deposit_usdt=1000.0, initial_deposit_usdt=1000.0)
    assert result.allowed is True
    assert result.order_size_usdt == 10.0


def test_take_profit_disabled_by_default_never_triggers():
    position = PositionState(symbol=SYMBOL, avg_price=100.0, total_invested=100.0, dca_count=1, peak_price=100.0)
    assert check_take_profit(position, current_price=1000.0) is False


def test_take_profit_triggers_once_price_reaches_target(monkeypatch):
    import trading.risk as risk

    monkeypatch.setattr(risk, "TAKE_PROFIT_PCT", 0.05)
    position = PositionState(symbol=SYMBOL, avg_price=100.0, total_invested=100.0, dca_count=1, peak_price=100.0)

    assert check_take_profit(position, current_price=104.99) is False
    assert check_take_profit(position, current_price=105.0) is True
    assert check_take_profit(position, current_price=110.0) is True


def test_take_profit_ignores_a_closed_or_missing_position(monkeypatch):
    import trading.risk as risk

    monkeypatch.setattr(risk, "TAKE_PROFIT_PCT", 0.05)
    closed_position = PositionState(symbol=SYMBOL, avg_price=0.0, total_invested=0.0, dca_count=0, peak_price=0.0)
    assert check_take_profit(closed_position, current_price=1000.0) is False


@pytest.mark.parametrize(
    "rsi_15m,rsi_1h,expected_pct",
    [
        (10.0, 10.0, 0.05),  # high volatility: RSI < 20
        (25.0, 25.0, 0.10),  # medium volatility: RSI 20-35
        (40.0, 40.0, 0.15),  # low volatility: RSI 35-50
    ],
)
def test_order_size_scales_with_rsi_volatility_band(rsi_15m, rsi_1h, expected_pct):
    result = check_risk(
        SYMBOL, 100.0, _signal("BUY", rsi_15m=rsi_15m, rsi_1h=rsi_1h), _fresh_position(), deposit_usdt=1000.0, initial_deposit_usdt=1000.0
    )
    assert result.allowed is True
    assert result.order_size_usdt == expected_pct * 1000.0
