"""Tests aligned with the official Modified Trading Agent Strategy spec."""

from trading_agent import (
    Candle,
    CandleType,
    DeterministicTradingAgent,
    classify_candle,
    within_time_window,
)


def _c(ts: str, o: float, h: float, l: float, c: float) -> Candle:
    return Candle(open=o, high=h, low=l, close=c, timestamp_ist=ts)


def test_green_candle_open_low_close_near_high() -> None:
    # open=low, close within 10% of range from high (bullish shape)
    candle = _c("2026-03-01 19:00:00", 100.0, 110.0, 100.0, 109.0)
    assert classify_candle(candle) == CandleType.GREEN


def test_red_candle_open_high_close_near_low() -> None:
    # open=high, close within 10% of range from low (bearish shape)
    candle = _c("2026-03-01 19:00:00", 110.0, 110.0, 100.0, 101.0)
    assert classify_candle(candle) == CandleType.RED


def test_trade_window_630pm_to_930pm_ist() -> None:
    assert within_time_window("2026-03-01 18:30:00") is True
    assert within_time_window("2026-03-01 21:30:00") is True
    assert within_time_window("2026-03-01 21:31:00") is False
    assert within_time_window("2026-03-01 10:00:00") is False
    assert within_time_window("2026-03-01 03:00:00") is False


def test_admin_provided_levels_are_not_overwritten() -> None:
    admin_levels = [50000.0, 51000.0, 52000.0]
    agent = DeterministicTradingAgent(key_levels=admin_levels)
    for c in [
        _c("2026-03-02 05:30:00", 100, 120, 90, 100),
        _c("2026-03-02 11:00:00", 101, 112, 94, 106),
        _c("2026-03-02 18:31:00", 106, 107, 105, 106),
    ]:
        agent.on_candle_close(c, 100, 10000, c.timestamp_ist)
    assert agent.state.active_admin_levels == admin_levels
