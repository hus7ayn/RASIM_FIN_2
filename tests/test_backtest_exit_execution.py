"""Tests for intrabar SL/target enforcement in the backtest exit check."""

import pytest

from trading_agent import (
    Action,
    Candle,
    PositionState,
    STOP_LOSS_USD,
    TARGET_USD,
    _evaluate_exit_intrabar,
)


def _c(ts: str, o: float, h: float, l: float, c: float) -> Candle:
    return Candle(open=o, high=h, low=l, close=c, timestamp_ist=ts)


def test_sl_caps_loss_even_when_close_overshoots():
    """A candle whose CLOSE implies a huge loss must still exit at the SL price, not the close."""
    # BUY qty=2.5628 lev=13: SL price = entry - 100/(2.5628*13) = entry - 3.0036...
    position = PositionState(
        active=True, side=Action.BUY.value, entry_price=89500.0, quantity=2.5628,
        entry_timestamp_ist="2026-01-24 19:21:00",
    )
    # Candle low plunges to 89321.7 (the real close that produced a -$5940 loss pre-fix),
    # well past the SL price, before recovering to close near the highs.
    candle = _c("2026-01-24 19:24:00", 89490.0, 89510.0, 89321.7, 89480.0)
    should_exit, pnl_usd, reason, exit_price = _evaluate_exit_intrabar(position, candle)
    assert should_exit is True
    assert reason == "SL_HIT_INTRABAR"
    assert pnl_usd == pytest.approx(-STOP_LOSS_USD)
    assert exit_price is not None and candle.low <= exit_price <= candle.high


def test_target_hit_intrabar_caps_gain_at_target():
    position = PositionState(
        active=True, side=Action.SELL.value, entry_price=60000.0, quantity=1.0,
        entry_timestamp_ist="2026-01-24 19:21:00",
    )
    # SL price = 60000 + 100/13 ~= 60007.7 ; target price = 60000 - 450/13 ~= 59965.4
    candle = _c("2026-01-24 19:24:00", 60000.0, 60003.0, 59900.0, 59950.0)
    should_exit, pnl_usd, reason, exit_price = _evaluate_exit_intrabar(position, candle)
    assert should_exit is True
    assert reason == "TARGET_HIT_INTRABAR"
    assert pnl_usd == pytest.approx(TARGET_USD)
    assert exit_price is not None and candle.low <= exit_price <= candle.high


def test_entry_candle_itself_is_never_checked():
    """No exit check on the candle where the position was just filled at the close."""
    position = PositionState(
        active=True, side=Action.BUY.value, entry_price=100.0, quantity=1.0,
        entry_timestamp_ist="2026-01-24 19:24:00",
    )
    # This candle's own low would otherwise trigger an SL — but it's the entry candle.
    candle = _c("2026-01-24 19:24:00", 100.0, 101.0, 50.0, 100.0)
    should_exit, pnl_usd, reason, exit_price = _evaluate_exit_intrabar(position, candle)
    assert should_exit is False
    assert pnl_usd is None and reason is None and exit_price is None


def test_no_exit_when_neither_threshold_reached():
    position = PositionState(
        active=True, side=Action.BUY.value, entry_price=100.0, quantity=1.0,
        entry_timestamp_ist="2026-01-24 19:21:00",
    )
    candle = _c("2026-01-24 19:24:00", 100.0, 100.5, 99.5, 100.1)
    should_exit, pnl_usd, reason, exit_price = _evaluate_exit_intrabar(position, candle)
    assert should_exit is False
    assert reason is None and exit_price is None
    assert pnl_usd is not None  # informational mark-to-close PnL is still returned


def test_both_thresholds_in_range_prefers_sl_conservatively():
    """A wide candle spanning both SL and target: SL wins (conservative tie-break)."""
    position = PositionState(
        active=True, side=Action.BUY.value, entry_price=100.0, quantity=1.0,
        entry_timestamp_ist="2026-01-24 19:21:00",
    )
    # SL price = 100 - 100/13 ~= 92.3 ; target price = 100 + 450/13 ~= 134.6
    candle = _c("2026-01-24 19:24:00", 100.0, 140.0, 90.0, 120.0)
    should_exit, pnl_usd, reason, exit_price = _evaluate_exit_intrabar(position, candle)
    assert should_exit is True
    assert reason == "SL_HIT_INTRABAR"
    assert pnl_usd == pytest.approx(-STOP_LOSS_USD)
