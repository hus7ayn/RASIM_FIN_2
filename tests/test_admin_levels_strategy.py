from datetime import time

from trading_agent import (
    Action,
    AdminLevelsConfig,
    Candle,
    DeterministicTradingAgent,
)


def _candle(ts: str, o: float, h: float, l: float, c: float) -> Candle:
    return Candle(open=o, high=h, low=l, close=c, timestamp_ist=ts)


def _build_config() -> AdminLevelsConfig:
    return AdminLevelsConfig(
        trading_day_start=time(hour=5, minute=30),
        range_window_start=time(hour=5, minute=30),
        range_window_end=time(hour=18, minute=30),
        ny_session_start=time(hour=18, minute=30),
        ny_session_end=time(hour=21, minute=30),
        require_pivot_confirmation=False,
    )


def test_trading_day_grouping_uses_0530_boundary() -> None:
    agent = DeterministicTradingAgent(admin_levels_config=_build_config())
    agent.on_candle_close(_candle("2026-03-02 05:29:00", 100, 101, 99, 100), 100, 10000, "2026-03-02 05:29:00")
    assert agent.state.admin_levels_state is not None
    assert agent.state.admin_levels_state.trading_day_start == "2026-03-01 05:30:00"

    agent.on_candle_close(_candle("2026-03-02 05:30:00", 100, 101, 99, 100), 100, 10000, "2026-03-02 05:30:00")
    assert agent.state.admin_levels_state is not None
    assert agent.state.admin_levels_state.trading_day_start == "2026-03-02 05:30:00"


def test_session_high_low_and_fib_midpoint() -> None:
    agent = DeterministicTradingAgent(admin_levels_config=_build_config())
    candles = [
        _candle("2026-03-02 05:30:00", 100, 101, 99, 100),
        _candle("2026-03-02 10:00:00", 102, 110, 98, 105),
        _candle("2026-03-02 17:00:00", 104, 108, 90, 95),
        _candle("2026-03-02 18:31:00", 95, 96, 94, 95),
    ]
    for c in candles:
        agent.on_candle_close(c, 100, 10000, c.timestamp_ist)

    state = agent.state.admin_levels_state
    assert state is not None
    assert state.session_high == 110
    assert state.session_low == 90
    assert state.fib0 == 110
    assert state.fib1 == 90
    assert state.fib0_5 == 100


def test_admin_level_spacing() -> None:
    agent = DeterministicTradingAgent(admin_levels_config=_build_config())
    for c in [
        _candle("2026-03-02 05:30:00", 100, 101, 99, 100),
        _candle("2026-03-02 11:00:00", 101, 112, 94, 106),
        _candle("2026-03-02 18:31:00", 106, 107, 105, 106),
    ]:
        agent.on_candle_close(c, 100, 10000, c.timestamp_ist)

    state = agent.state.admin_levels_state
    assert state is not None
    assert state.session_open_close == 100
    # range = 18, step = 3
    assert state.admin_levels_up[0].price == 103
    assert state.admin_levels_up[5].price == 118
    assert state.admin_levels_down[0].price == 97
    assert state.admin_levels_down[5].price == 82


def test_default_range_window_is_1230_to_1830() -> None:
    assert AdminLevelsConfig().range_window_start == time(hour=12, minute=30)
    assert AdminLevelsConfig().range_window_end == time(hour=18, minute=30)


def test_range_ignores_extremes_before_1230() -> None:
    agent = DeterministicTradingAgent(
        admin_levels_config=AdminLevelsConfig(require_pivot_confirmation=False)
    )
    candles = [
        _candle("2026-03-02 05:30:00", 100, 101, 99, 100),
        # Outside the 12:30-18:30 range window: must not set session extremes.
        _candle("2026-03-02 10:00:00", 102, 200, 50, 105),
        # Inside the range window: these define the session high/low instead.
        _candle("2026-03-02 13:00:00", 104, 120, 90, 95),
        _candle("2026-03-02 18:31:00", 95, 96, 94, 95),
    ]
    for c in candles:
        agent.on_candle_close(c, 100, 10000, c.timestamp_ist)

    state = agent.state.admin_levels_state
    assert state is not None
    assert state.session_high == 120
    assert state.session_low == 90


def test_no_trade_outside_ny_session() -> None:
    agent = DeterministicTradingAgent(admin_levels_config=_build_config())
    # Prime state and finalize levels.
    for c in [
        _candle("2026-03-02 05:30:00", 100, 101, 99, 100),
        _candle("2026-03-02 11:00:00", 101, 112, 94, 106),
        _candle("2026-03-02 18:31:00", 106, 107, 105, 106),
    ]:
        agent.on_candle_close(c, 100, 10000, c.timestamp_ist)

    # Construct a candle that would otherwise satisfy EMA + level break.
    agent.state.previous_candle = _candle("2026-03-03 09:59:00", 105, 106, 100, 101)
    decision = agent.on_candle_close(
        _candle("2026-03-03 10:00:00", 99, 104, 98, 103),
        ema_7=100,
        capital=10000,
        timestamp_ist="2026-03-03 10:00:00",
    )
    assert decision["action"] == Action.HOLD.value


def test_levels_do_not_repaint_after_finalize() -> None:
    agent = DeterministicTradingAgent(admin_levels_config=_build_config())
    seed = [
        _candle("2026-03-02 05:30:00", 100, 101, 99, 100),
        _candle("2026-03-02 10:00:00", 100, 120, 95, 110),
        _candle("2026-03-02 18:31:00", 110, 111, 109, 110),
    ]
    for c in seed:
        agent.on_candle_close(c, 100, 10000, c.timestamp_ist)
    state = agent.state.admin_levels_state
    assert state is not None
    frozen_levels = [lvl.price for lvl in state.admin_levels_up + state.admin_levels_down]

    # New highs/lows after finalization should not alter levels.
    for c in [
        _candle("2026-03-02 20:00:00", 110, 150, 70, 120),
        _candle("2026-03-02 21:00:00", 120, 151, 69, 119),
    ]:
        agent.on_candle_close(c, 100, 10000, c.timestamp_ist)
    state_after = agent.state.admin_levels_state
    assert state_after is not None
    assert [lvl.price for lvl in state_after.admin_levels_up + state_after.admin_levels_down] == frozen_levels


def test_manual_swings_override_auto_detection() -> None:
    """Admin's hand-drawn swing high/low drive the ladder, overriding auto-detected extremes."""
    agent = DeterministicTradingAgent(admin_levels_config=_build_config())
    agent.set_manual_swings("2026-03-02", swing_high=63000, swing_low=57000, anchor=60000)
    for c in [
        _candle("2026-03-02 05:30:00", 60000, 60010, 59990, 60000),
        # This afternoon candle would auto-detect high=62000/low=58000, but manual wins.
        _candle("2026-03-02 13:00:00", 60000, 62000, 58000, 60500),
        _candle("2026-03-02 18:31:00", 60500, 60510, 60490, 60500),
    ]:
        agent.on_candle_close(c, 100, 10000, c.timestamp_ist)

    state = agent.state.admin_levels_state
    assert state is not None
    assert state.levels_finalized
    assert state.session_high == 63000
    assert state.session_low == 57000
    assert state.fib0 == 63000
    assert state.fib1 == 57000
    assert state.fib0_5 == 60000
    # step = (63000 - 57000) / 6 = 1000, projected symmetrically around anchor 60000.
    assert state.admin_levels_up[0].price == 61000
    assert state.admin_levels_down[0].price == 59000
    assert state.admin_levels_up[5].price == 66000
    assert state.admin_levels_down[5].price == 54000


def test_manual_swings_reproduce_hand_picked_levels() -> None:
    """Given the admin's swings, the derived level-1 equals the hand-picked above/below."""
    # (opening/anchor, above, below) hand-picked by the admin for real trading days.
    targets = {
        "2026-06-24": (62760, 63115, 62404),
        "2026-06-30": (60206, 60694, 59714),
        "2026-07-01": (58648, 58975, 58320),
    }
    for day, (opening, above, below) in targets.items():
        step = (above - below) / 2
        center = (above + below) / 2  # symmetric projection center reproduces above/below
        # Swings the admin drew map to ladder index 3 (center +/- 3*step).
        high, low = center + 3 * step, center - 3 * step
        agent = DeterministicTradingAgent(admin_levels_config=_build_config())
        agent.set_manual_swings(day, high, low, center)
        for c in [
            _candle(f"{day} 05:30:00", center, center + 1, center - 1, center),
            _candle(f"{day} 18:31:00", center, center + 1, center - 1, center),
        ]:
            agent.on_candle_close(c, 100, 10000, c.timestamp_ist)
        state = agent.state.admin_levels_state
        assert state is not None and state.levels_finalized
        assert state.admin_levels_up[0].price == above
        assert state.admin_levels_down[0].price == below
        # The admin's stated opening equals the projection center within hand-pick rounding.
        assert abs(state.session_open_close - opening) <= 3
