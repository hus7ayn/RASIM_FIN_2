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


def _pos(side: str, entry: float, qty: float, stop: float, target: float) -> PositionState:
    """A position carrying explicit stop/target prices — the production path."""
    return PositionState(
        active=True, side=side, entry_price=entry, quantity=qty,
        entry_timestamp_ist="2026-01-24 19:21:00",
        stop_price=stop, target_price=target,
    )


def test_sl_caps_loss_even_when_close_overshoots():
    """A candle whose CLOSE implies a huge loss must exit at the SL price, not the close."""
    # qty 0.4625 with a $216 stop distance costs $100 at the stop.
    position = _pos(Action.BUY.value, 86_492.0, 0.46247, stop=86_275.77, target=87_465.04)
    # Low plunges far past the stop before recovering to close near the highs.
    candle = _c("2026-01-24 19:24:00", 86_490.0, 86_510.0, 85_800.0, 86_480.0)
    should_exit, pnl_usd, reason, exit_price = _evaluate_exit_intrabar(position, candle)
    assert should_exit is True
    assert reason == "SL_HIT_INTRABAR"
    assert pnl_usd == pytest.approx(-STOP_LOSS_USD, abs=0.05)
    assert exit_price == pytest.approx(86_275.77)
    assert candle.low <= exit_price <= candle.high


def test_target_hit_intrabar_caps_gain_at_target():
    position = _pos(Action.SELL.value, 86_492.0, 0.46247, stop=86_708.23, target=85_518.96)
    candle = _c("2026-01-24 19:24:00", 86_490.0, 86_495.0, 85_400.0, 85_600.0)
    should_exit, pnl_usd, reason, exit_price = _evaluate_exit_intrabar(position, candle)
    assert should_exit is True
    assert reason == "TARGET_HIT_INTRABAR"
    assert pnl_usd == pytest.approx(TARGET_USD, abs=0.05)
    assert exit_price == pytest.approx(85_518.96)


def test_entry_candle_itself_is_never_checked():
    """No exit check on the candle where the position was just filled at the close."""
    position = PositionState(
        active=True, side=Action.BUY.value, entry_price=100.0, quantity=1.0,
        entry_timestamp_ist="2026-01-24 19:24:00", stop_price=99.0, target_price=104.5,
    )
    candle = _c("2026-01-24 19:24:00", 100.0, 101.0, 50.0, 100.0)
    should_exit, pnl_usd, reason, exit_price = _evaluate_exit_intrabar(position, candle)
    assert should_exit is False
    assert pnl_usd is None and reason is None and exit_price is None


def test_no_exit_when_neither_threshold_reached():
    position = _pos(Action.BUY.value, 100.0, 1.0, stop=99.0, target=104.5)
    candle = _c("2026-01-24 19:24:00", 100.0, 100.5, 99.5, 100.1)
    should_exit, pnl_usd, reason, exit_price = _evaluate_exit_intrabar(position, candle)
    assert should_exit is False
    assert reason is None and exit_price is None
    assert pnl_usd is not None  # informational mark-to-close PnL is still returned


def test_both_thresholds_in_range_prefers_sl_conservatively():
    """A wide candle spanning both SL and target: SL wins (conservative tie-break)."""
    position = _pos(Action.BUY.value, 100.0, 1.0, stop=99.0, target=104.5)
    candle = _c("2026-01-24 19:24:00", 100.0, 140.0, 90.0, 120.0)
    should_exit, pnl_usd, reason, exit_price = _evaluate_exit_intrabar(position, candle)
    assert should_exit is True
    assert reason == "SL_HIT_INTRABAR"
    assert exit_price == pytest.approx(99.0)
    assert pnl_usd == pytest.approx(-1.0)  # 1 unit x $1 adverse move


def test_falls_back_to_usd_thresholds_when_prices_absent():
    """Positions built without explicit stop/target prices still exit.

    Derivation uses P&L = Δprice x quantity, with no leverage factor.
    """
    position = PositionState(
        active=True, side=Action.BUY.value, entry_price=1_000.0, quantity=2.0,
        entry_timestamp_ist="2026-01-24 19:21:00",
    )
    # No stop_price set, so SL derives to 1000 - 100/2 = 950.
    candle = _c("2026-01-24 19:24:00", 1_000.0, 1_001.0, 940.0, 990.0)
    should_exit, pnl_usd, reason, exit_price = _evaluate_exit_intrabar(position, candle)
    assert should_exit is True
    assert reason == "SL_HIT_INTRABAR"
    assert exit_price == pytest.approx(950.0)
    assert pnl_usd == pytest.approx(-STOP_LOSS_USD)
