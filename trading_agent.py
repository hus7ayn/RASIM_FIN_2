from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from enum import Enum
import argparse
import csv
import json
import logging
from typing import Any, Dict, List, Optional, Sequence, Tuple

"""
Deterministic candle-close strategy (3m timeframe).

Admin workflow:
1) Admin provides key levels.
2) Machine evaluates entry triggers on each 3m candle close inside the IST window.

Entry triggers (all on the second candle of a two-candle pattern):
  - Break of admin key level
  - Valid pattern: RED→GREEN (upward/BUY) or GREEN→RED (downward/SELL)
  - EMA-7 break (same direction as level break)

Rules:
  - Trade window: 18:30–21:30 IST
  - Risk: 3% of capital per trade; quantity = (3% × capital) / $100
  - SL: $100 USD PnL; Target: $450 USD PnL; Leverage: 13×; Isolated margin
  - Entry always on candle close; one position at a time
"""

logger = logging.getLogger(__name__)

if not logger.handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


STOP_LOSS_USD = 100
TARGET_USD = 450
LEVERAGE = 13
RISK_FRACTION = 0.03
TIME_WINDOW_START_IST = time(hour=18, minute=30)  # 6:30 PM IST
TIME_WINDOW_END_IST = time(hour=21, minute=30)  # 9:30 PM IST
PRICE_TOLERANCE = 1e-9
# Open must equal high (RED) or low (GREEN) within this fraction of candle range.
OPEN_EXTREME_TOLERANCE = 0.02
# Close must be within this fraction of range from target extreme ("90% close" → 10% band).
CLOSE_EXTREME_TOLERANCE = 0.10


class Action(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class CandleType(str, Enum):
    RED = "RED"
    GREEN = "GREEN"


@dataclass(frozen=True)
class Candle:
    open: float
    high: float
    low: float
    close: float
    timestamp_ist: str


@dataclass
class PositionState:
    active: bool = False
    side: Optional[str] = None
    entry_price: Optional[float] = None
    quantity: Optional[float] = None
    entry_timestamp_ist: Optional[str] = None


@dataclass
class TradingState:
    current_open_position: PositionState = field(default_factory=PositionState)
    last_candle: Optional[Candle] = None
    previous_candle: Optional[Candle] = None
    last_signal_generated: Optional[Dict[str, Any]] = None
    active_admin_levels: List[float] = field(default_factory=list)
    inside_time_window: bool = False
    last_processed_candle_ts: Optional[str] = None
    admin_levels_state: Optional["AdminLevelsState"] = None


@dataclass(frozen=True)
class SessionWindow:
    start: time
    end: time


@dataclass(frozen=True)
class AdminLevel:
    label: str
    price: float
    direction: str
    index: int


@dataclass(frozen=True)
class ManualSwing:
    """Admin's hand-drawn swing extremes for a trading day.

    `anchor` is optional; when None the opening-candle (05:30 close) anchor is used.
    """
    swing_high: float
    swing_low: float
    anchor: Optional[float] = None


@dataclass(frozen=True)
class AdminLevelsConfig:
    trading_day_start: time = time(hour=5, minute=30)
    range_window_start: time = time(hour=12, minute=30)
    range_window_end: time = time(hour=18, minute=30)
    ny_session_start: time = time(hour=18, minute=30)
    ny_session_end: time = time(hour=21, minute=30)
    levels_per_side: int = 6
    step_divisor: int = 6
    pivot_lookback: int = 1
    pivot_tolerance_fraction: float = 0.10
    require_pivot_confirmation: bool = True
    interaction_tolerance_fraction: float = 0.05


@dataclass
class AdminLevelsState:
    trading_day_start: str
    trading_day_end: str
    range_window_start: str
    range_window_end: str
    session_high: Optional[float] = None
    session_low: Optional[float] = None
    fib0: Optional[float] = None
    fib0_5: Optional[float] = None
    fib1: Optional[float] = None
    session_open_close: Optional[float] = None
    admin_levels_up: List[AdminLevel] = field(default_factory=list)
    admin_levels_down: List[AdminLevel] = field(default_factory=list)
    ny_session_active: bool = False
    levels_finalized: bool = False


def _safe_float(value: Any) -> Optional[float]:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if parsed != parsed:  # NaN check
        return None
    return parsed


def _is_close(a: float, b: float, tol: float = PRICE_TOLERANCE) -> bool:
    return abs(a - b) <= tol


def _parse_ist_timestamp(timestamp_ist: str) -> Optional[datetime]:
    if not isinstance(timestamp_ist, str) or not timestamp_ist.strip():
        return None

    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%dT%H:%M",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(timestamp_ist, fmt)
        except ValueError:
            continue
    return None


def _in_window(ts: time, window: SessionWindow) -> bool:
    if window.start <= window.end:
        return window.start <= ts <= window.end
    return ts >= window.start or ts <= window.end


def _align_trading_day_start(ts: datetime, day_start: time) -> datetime:
    base = datetime.combine(ts.date(), day_start)
    if ts < base:
        base -= timedelta(days=1)
    return base


def _format_ts(ts: datetime) -> str:
    return ts.strftime("%Y-%m-%d %H:%M:%S")


def _is_valid_ohlc(candle: Candle) -> bool:
    values = [candle.open, candle.high, candle.low, candle.close]
    if any(_safe_float(v) is None for v in values):
        return False
    if candle.high < candle.low:
        return False
    if not (candle.low <= candle.open <= candle.high):
        return False
    if not (candle.low <= candle.close <= candle.high):
        return False
    return True


def _candle_range(candle: Candle) -> float:
    return candle.high - candle.low


def _near_extreme(price: float, extreme: float, candle_range: float, tol: float) -> bool:
    """Return True if `price` is within `tol` fraction of `candle_range` from `extreme`."""
    if candle_range <= PRICE_TOLERANCE:
        return _is_close(price, extreme)
    return abs(price - extreme) / candle_range <= tol


def is_red_candle(candle: Candle) -> bool:
    """
    RED: open equals high; close is ~90% toward low (within 10% of range from low).
    Bearish-shaped candle, used for downward level/EMA breaks (open above, close below).
    """
    if not _is_valid_ohlc(candle):
        return False
    r = _candle_range(candle)
    open_at_high = _near_extreme(candle.open, candle.high, r, OPEN_EXTREME_TOLERANCE)
    close_near_low = _near_extreme(candle.close, candle.low, r, CLOSE_EXTREME_TOLERANCE)
    return open_at_high and close_near_low


def is_green_candle(candle: Candle) -> bool:
    """
    GREEN: open equals low; close is ~90% toward high (within 10% of range from high).
    Bullish-shaped candle, used for upward level/EMA breaks (open below, close above).
    """
    if not _is_valid_ohlc(candle):
        return False
    r = _candle_range(candle)
    open_at_low = _near_extreme(candle.open, candle.low, r, OPEN_EXTREME_TOLERANCE)
    close_near_high = _near_extreme(candle.close, candle.high, r, CLOSE_EXTREME_TOLERANCE)
    return open_at_low and close_near_high


def classify_candle(candle: Candle) -> Optional[CandleType]:
    if is_red_candle(candle):
        return CandleType.RED
    if is_green_candle(candle):
        return CandleType.GREEN
    return None


def check_key_level_break(candle: Candle, key_level: float) -> Dict[str, Any]:
    if not _is_valid_ohlc(candle) or _safe_float(key_level) is None:
        return {"direction": None, "broken": False}

    ctype = classify_candle(candle)
    bullish = (
        candle.open < key_level
        and candle.close > key_level
        and ctype == CandleType.GREEN
    )
    bearish = (
        candle.open > key_level
        and candle.close < key_level
        and ctype == CandleType.RED
    )
    if bullish:
        return {"direction": "BULLISH", "broken": True}
    if bearish:
        return {"direction": "BEARISH", "broken": True}
    return {"direction": None, "broken": False}


def check_ema_break(candle: Candle, ema_7: float) -> Dict[str, Any]:
    if not _is_valid_ohlc(candle) or _safe_float(ema_7) is None:
        return {"direction": None, "broken": False}

    ctype = classify_candle(candle)
    bullish = candle.open < ema_7 and candle.close > ema_7 and ctype == CandleType.GREEN
    bearish = candle.open > ema_7 and candle.close < ema_7 and ctype == CandleType.RED
    if bullish:
        return {"direction": "BULLISH", "broken": True}
    if bearish:
        return {"direction": "BEARISH", "broken": True}
    return {"direction": None, "broken": False}


def validate_pattern(
    prev_candle_type: Optional[CandleType], current_candle_type: Optional[CandleType]
) -> bool:
    allowed = {
        (CandleType.RED, CandleType.GREEN),
        (CandleType.GREEN, CandleType.RED),
    }
    return (prev_candle_type, current_candle_type) in allowed


def _is_pivot_confirmed_near_extreme(
    prev_candle: Optional[Candle],
    current_candle: Candle,
    extreme_price: float,
    is_high_anchor: bool,
    config: AdminLevelsConfig,
) -> bool:
    if not config.require_pivot_confirmation:
        return True
    if prev_candle is None:
        return False
    prev_type = classify_candle(prev_candle)
    current_type = classify_candle(current_candle)
    reversal_ok = (
        prev_type == CandleType.RED and current_type == CandleType.GREEN
    ) or (
        prev_type == CandleType.GREEN and current_type == CandleType.RED
    )
    if not reversal_ok:
        return False
    candle_range = max(_candle_range(current_candle), PRICE_TOLERANCE)
    if is_high_anchor:
        return abs(current_candle.high - extreme_price) / candle_range <= config.pivot_tolerance_fraction
    return abs(current_candle.low - extreme_price) / candle_range <= config.pivot_tolerance_fraction


def _project_admin_levels(
    session_open_close: float,
    session_high: float,
    session_low: float,
    config: AdminLevelsConfig,
) -> Tuple[List[AdminLevel], List[AdminLevel]]:
    raw_range = max(session_high - session_low, PRICE_TOLERANCE)
    divisor = config.step_divisor if config.step_divisor > 0 else config.levels_per_side
    step = raw_range / max(divisor, 1)
    up_levels = [
        AdminLevel(
            label=f"UP_{i}",
            price=session_open_close + (i * step),
            direction="UP",
            index=i,
        )
        for i in range(1, config.levels_per_side + 1)
    ]
    down_levels = [
        AdminLevel(
            label=f"DOWN_{i}",
            price=session_open_close - (i * step),
            direction="DOWN",
            index=i,
        )
        for i in range(1, config.levels_per_side + 1)
    ]
    return up_levels, down_levels


def _strategy_state_to_dict(state: Optional[AdminLevelsState]) -> Optional[Dict[str, Any]]:
    if state is None:
        return None
    return {
        "tradingDayStart": state.trading_day_start,
        "tradingDayEnd": state.trading_day_end,
        "rangeWindowStart": state.range_window_start,
        "rangeWindowEnd": state.range_window_end,
        "sessionHigh": state.session_high,
        "sessionLow": state.session_low,
        "fib0": state.fib0,
        "fib0_5": state.fib0_5,
        "fib1": state.fib1,
        "sessionOpenClose": state.session_open_close,
        "adminLevelsUp": [lvl.__dict__ for lvl in state.admin_levels_up],
        "adminLevelsDown": [lvl.__dict__ for lvl in state.admin_levels_down],
        "nySessionActive": state.ny_session_active,
        "levelsFinalized": state.levels_finalized,
    }


def calculate_quantity(capital: float) -> float:
    parsed_capital = _safe_float(capital)
    if parsed_capital is None or parsed_capital <= 0:
        raise ValueError("Capital must be a positive number.")
    return (RISK_FRACTION * parsed_capital) / STOP_LOSS_USD


def within_time_window(timestamp_ist: str) -> bool:
    parsed = _parse_ist_timestamp(timestamp_ist)
    if parsed is None:
        return False
    return _in_window(parsed.time(), SessionWindow(TIME_WINDOW_START_IST, TIME_WINDOW_END_IST))


def _build_hold_decision(
    reason: str,
    timestamp_ist: str,
    ema_7: Optional[float] = None,
    candle_type_prev: Optional[CandleType] = None,
    candle_type_current: Optional[CandleType] = None,
    key_level: Optional[float] = None,
    level_break: bool = False,
    ema_break: bool = False,
    time_allowed: bool = False,
    position_active: bool = False,
    strategy_state: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    decision = {
        "action": Action.HOLD.value,
        "reason": reason,
        "output": "NO TRADE - CONDITIONS NOT MET",
        "entry_price": None,
        "key_level": key_level,
        "ema_7": ema_7,
        "stop_loss_usd": STOP_LOSS_USD,
        "target_usd": TARGET_USD,
        "quantity": None,
        "candle_type_prev": candle_type_prev.value if candle_type_prev else None,
        "candle_type_current": candle_type_current.value if candle_type_current else None,
        "level_break": level_break,
        "ema_break": ema_break,
        "time_allowed": time_allowed,
        "position_active": position_active,
        "timestamp_ist": timestamp_ist,
        "strategy_state": strategy_state,
    }
    logger.info("Decision=%s", decision)
    return decision


def generate_signal(
    prev_candle: Optional[Candle],
    current_candle: Candle,
    key_levels: Sequence[float],
    ema_7: Optional[float],
    capital: float,
    open_position: Optional[Dict[str, Any]],
    timestamp_ist: str,
    strategy_state: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Returns deterministic decision object for every 3-minute candle close.

    Decision pipeline:
    - Reject duplicate/invalid candles
    - Enforce IST time window
    - Enforce one-position-at-a-time
    - Validate EMA/key-level availability
    - Validate two-candle pattern
    - Require EMA break on current candle
    - Require aligned key-level break on current candle
    - Emit BUY/SELL with computed quantity, else HOLD with reason
    """
    logger.info("Processing candle close at IST timestamp=%s", timestamp_ist)

    position_active = bool((open_position or {}).get("active", False))
    last_processed_ts = (open_position or {}).get("last_processed_candle_ts")

    if timestamp_ist == last_processed_ts:
        return _build_hold_decision(
            reason="HOLD: Duplicate candle processing blocked.",
            timestamp_ist=timestamp_ist,
            ema_7=ema_7,
            position_active=position_active,
            strategy_state=strategy_state,
        )

    if not _is_valid_ohlc(current_candle):
        return _build_hold_decision(
            reason="HOLD: Invalid OHLC in current candle.",
            timestamp_ist=timestamp_ist,
            ema_7=ema_7,
            position_active=position_active,
            strategy_state=strategy_state,
        )
    if prev_candle is None or not _is_valid_ohlc(prev_candle):
        return _build_hold_decision(
            reason="HOLD: Previous candle missing or invalid for two-candle pattern.",
            timestamp_ist=timestamp_ist,
            ema_7=ema_7,
            position_active=position_active,
            strategy_state=strategy_state,
        )

    time_allowed = within_time_window(timestamp_ist)
    logger.info("Time window validation: allowed=%s", time_allowed)
    if not time_allowed:
        return _build_hold_decision(
            reason="HOLD: Outside allowed IST trading window.",
            timestamp_ist=timestamp_ist,
            ema_7=ema_7,
            time_allowed=False,
            position_active=position_active,
            strategy_state=strategy_state,
        )

    if position_active:
        return _build_hold_decision(
            reason="HOLD: Active position exists; only one trade allowed.",
            timestamp_ist=timestamp_ist,
            ema_7=ema_7,
            time_allowed=True,
            position_active=True,
            strategy_state=strategy_state,
        )

    parsed_ema = _safe_float(ema_7)
    if parsed_ema is None:
        return _build_hold_decision(
            reason="HOLD: EMA 7 missing or invalid.",
            timestamp_ist=timestamp_ist,
            ema_7=ema_7,
            time_allowed=True,
            position_active=False,
            strategy_state=strategy_state,
        )

    if not key_levels:
        return _build_hold_decision(
            reason="HOLD: No admin key levels provided.",
            timestamp_ist=timestamp_ist,
            ema_7=parsed_ema,
            time_allowed=True,
            position_active=False,
            strategy_state=strategy_state,
        )

    prev_type = classify_candle(prev_candle)
    current_type = classify_candle(current_candle)
    logger.info(
        "Candle classification: prev=%s current=%s", prev_type, current_type
    )

    if not validate_pattern(prev_type, current_type):
        return _build_hold_decision(
            reason="HOLD: Two-candle pattern not valid.",
            timestamp_ist=timestamp_ist,
            ema_7=parsed_ema,
            candle_type_prev=prev_type,
            candle_type_current=current_type,
            time_allowed=True,
            position_active=False,
            strategy_state=strategy_state,
        )

    ema_break_info = check_ema_break(current_candle, parsed_ema)
    logger.info("EMA break result: %s", ema_break_info)
    if not ema_break_info["broken"]:
        return _build_hold_decision(
            reason="HOLD: Current candle did not break EMA 7.",
            timestamp_ist=timestamp_ist,
            ema_7=parsed_ema,
            candle_type_prev=prev_type,
            candle_type_current=current_type,
            ema_break=False,
            time_allowed=True,
            position_active=False,
            strategy_state=strategy_state,
        )

    matched_key_level: Optional[float] = None
    matched_level_break: Optional[Dict[str, Any]] = None
    for level in key_levels:
        parsed_level = _safe_float(level)
        if parsed_level is None:
            continue
        level_break_info = check_key_level_break(current_candle, parsed_level)
        logger.info(
            "Key level break result for level=%s: %s", parsed_level, level_break_info
        )
        if (
            level_break_info["broken"]
            and level_break_info["direction"] == ema_break_info["direction"]
        ):
            matched_key_level = parsed_level
            matched_level_break = level_break_info
            break

    if matched_key_level is None or matched_level_break is None:
        return _build_hold_decision(
            reason="HOLD: No same-candle key-level break aligned with EMA break direction.",
            timestamp_ist=timestamp_ist,
            ema_7=parsed_ema,
            candle_type_prev=prev_type,
            candle_type_current=current_type,
            key_level=None,
            level_break=False,
            ema_break=True,
            time_allowed=True,
            position_active=False,
            strategy_state=strategy_state,
        )

    try:
        quantity = calculate_quantity(capital)
    except ValueError as exc:
        return _build_hold_decision(
            reason=f"HOLD: {exc}",
            timestamp_ist=timestamp_ist,
            ema_7=parsed_ema,
            candle_type_prev=prev_type,
            candle_type_current=current_type,
            key_level=matched_key_level,
            level_break=True,
            ema_break=True,
            time_allowed=True,
            position_active=False,
            strategy_state=strategy_state,
        )

    direction = matched_level_break["direction"]
    if direction == "BULLISH":
        action = Action.BUY.value
    elif direction == "BEARISH":
        action = Action.SELL.value
    else:
        return _build_hold_decision(
            reason="HOLD: Break direction undefined after validations.",
            timestamp_ist=timestamp_ist,
            ema_7=parsed_ema,
            candle_type_prev=prev_type,
            candle_type_current=current_type,
            key_level=matched_key_level,
            level_break=True,
            ema_break=True,
            time_allowed=True,
            position_active=False,
            strategy_state=strategy_state,
        )

    decision = {
        "action": action,
        "reason": (
            f"{action}: Valid two-candle pattern, same-candle key-level+EMA break "
            f"({direction}), within time window, no active position."
        ),
        "output": {
            "Direction": action,
            "Entry Price": current_candle.close,
            "Stop Loss": f"{STOP_LOSS_USD} USD equivalent",
            "Target": f"{TARGET_USD} USD equivalent",
            "Quantity": quantity,
            "Timestamp (IST)": timestamp_ist,
        },
        "entry_price": current_candle.close,
        "key_level": matched_key_level,
        "ema_7": parsed_ema,
        "stop_loss_usd": STOP_LOSS_USD,
        "target_usd": TARGET_USD,
        "quantity": quantity,
        "candle_type_prev": prev_type.value if prev_type else None,
        "candle_type_current": current_type.value if current_type else None,
        "level_break": True,
        "ema_break": True,
        "time_allowed": True,
        "position_active": False,
        "timestamp_ist": timestamp_ist,
        "strategy_state": strategy_state,
    }
    logger.info("Quantity calculation: capital=%s quantity=%s", capital, quantity)
    logger.info("Final signal decision=%s", decision)
    return decision


class DeterministicTradingAgent:
    """
    Stateful wrapper for live 3-minute candle processing.

    When admin supplies key_levels at init (or via update_key_levels), those levels
    are used for entry and are not replaced by auto-projected session levels.
    """

    def __init__(
        self,
        key_levels: Optional[Sequence[float]] = None,
        admin_levels_config: Optional[AdminLevelsConfig] = None,
    ) -> None:
        levels = [float(x) for x in (key_levels or [])]
        self.state = TradingState(active_admin_levels=levels)
        self.admin_levels_config = admin_levels_config or AdminLevelsConfig()
        self._admin_levels_locked = bool(levels)
        # Admin-drawn swings per trading day: {"YYYY-MM-DD": ManualSwing}.
        # When present for a day, the ladder is projected from these hand-picked
        # swing extremes instead of the auto-detected session high/low.
        self._manual_swings: Dict[str, ManualSwing] = {}

    def set_manual_swings(
        self,
        trading_day: str,
        swing_high: float,
        swing_low: float,
        anchor: Optional[float] = None,
    ) -> None:
        """Register the admin's hand-drawn swing high/low for one trading day.

        `trading_day` is the trading-day-start date as "YYYY-MM-DD" (the 05:30 IST
        anchor day). `anchor` overrides the opening-candle anchor if the admin also
        picks it by hand; otherwise the 05:30 candle close is used.
        """
        high = _safe_float(swing_high)
        low = _safe_float(swing_low)
        if high is None or low is None:
            raise ValueError("swing_high and swing_low must be numbers.")
        if high < low:
            high, low = low, high
        self._manual_swings[trading_day[:10]] = ManualSwing(
            swing_high=high, swing_low=low, anchor=_safe_float(anchor)
        )
        logger.info(
            "Manual swings set for %s: high=%s low=%s anchor=%s",
            trading_day[:10],
            high,
            low,
            anchor,
        )

    def update_key_levels(self, key_levels: Sequence[float]) -> None:
        self.state.active_admin_levels = [float(level) for level in key_levels]
        self._admin_levels_locked = bool(self.state.active_admin_levels)
        logger.info("Admin levels updated: %s", self.state.active_admin_levels)

    def _new_day_state(self, ts: datetime) -> AdminLevelsState:
        cfg = self.admin_levels_config
        day_start = _align_trading_day_start(ts, cfg.trading_day_start)
        day_end = day_start + timedelta(days=1)
        range_start = datetime.combine(day_start.date(), cfg.range_window_start)
        if range_start < day_start:
            range_start += timedelta(days=1)
        range_end = datetime.combine(day_start.date(), cfg.range_window_end)
        if range_end <= range_start:
            range_end += timedelta(days=1)
        return AdminLevelsState(
            trading_day_start=_format_ts(day_start),
            trading_day_end=_format_ts(day_end),
            range_window_start=_format_ts(range_start),
            range_window_end=_format_ts(range_end),
        )

    def _update_admin_levels(self, prev_candle: Optional[Candle], current_candle: Candle) -> None:
        ts = _parse_ist_timestamp(current_candle.timestamp_ist)
        if ts is None:
            return
        cfg = self.admin_levels_config
        current_day_start = _align_trading_day_start(ts, cfg.trading_day_start)
        state = self.state.admin_levels_state
        if state is None or _parse_ist_timestamp(state.trading_day_start) != current_day_start:
            self.state.admin_levels_state = self._new_day_state(ts)
            state = self.state.admin_levels_state
            logger.info("Started new trading day state: %s", state)

        assert state is not None
        range_start = _parse_ist_timestamp(state.range_window_start)
        range_end = _parse_ist_timestamp(state.range_window_end)
        if range_start is None or range_end is None:
            return

        if not state.levels_finalized and range_start <= ts <= range_end:
            high_candidate = current_candle.high
            low_candidate = current_candle.low
            if (
                state.session_high is None
                or high_candidate > state.session_high
            ) and _is_pivot_confirmed_near_extreme(prev_candle, current_candle, high_candidate, True, cfg):
                state.session_high = high_candidate
            if (
                state.session_low is None
                or low_candidate < state.session_low
            ) and _is_pivot_confirmed_near_extreme(prev_candle, current_candle, low_candidate, False, cfg):
                state.session_low = low_candidate
            logger.info(
                "Range update: high=%s low=%s ts=%s",
                state.session_high,
                state.session_low,
                current_candle.timestamp_ist,
            )

        day_start = _parse_ist_timestamp(state.trading_day_start)
        if (
            day_start is not None
            and ts.hour == day_start.hour
            and ts.minute == day_start.minute
        ):
            state.session_open_close = current_candle.close
            logger.info("Session 05:30 close anchor set: %s", state.session_open_close)

        # Admin's hand-drawn swings (if any) override auto-detected session extremes.
        # The swing high/low are subjective pivots the admin marks on the chart, so
        # they cannot be reproduced from a range-window formula — they are inputs.
        manual = self._manual_swings.get(state.trading_day_start[:10])
        finalize_high = manual.swing_high if manual is not None else state.session_high
        finalize_low = manual.swing_low if manual is not None else state.session_low
        finalize_anchor = state.session_open_close
        if manual is not None and manual.anchor is not None:
            finalize_anchor = manual.anchor

        if (
            not state.levels_finalized
            and ts > range_end
            and finalize_high is not None
            and finalize_low is not None
            and finalize_anchor is not None
        ):
            state.session_high = finalize_high
            state.session_low = finalize_low
            state.session_open_close = finalize_anchor
            state.fib0 = finalize_high
            state.fib1 = finalize_low
            state.fib0_5 = finalize_low + 0.5 * (finalize_high - finalize_low)
            ups, downs = _project_admin_levels(
                session_open_close=finalize_anchor,
                session_high=finalize_high,
                session_low=finalize_low,
                config=cfg,
            )
            state.admin_levels_up = ups
            state.admin_levels_down = downs
            state.levels_finalized = True
            logger.info("Finalized admin levels: %s", _strategy_state_to_dict(state))

        trade_window = SessionWindow(cfg.ny_session_start, cfg.ny_session_end)
        state.ny_session_active = _in_window(ts.time(), trade_window)
        if not self._admin_levels_locked and (state.admin_levels_up or state.admin_levels_down):
            self.state.active_admin_levels = [
                lvl.price for lvl in (state.admin_levels_up + state.admin_levels_down)
            ]

    def on_candle_close(
        self,
        candle: Candle,
        ema_7: Optional[float],
        capital: float,
        timestamp_ist: str,
    ) -> Dict[str, Any]:
        if self.state.last_processed_candle_ts == timestamp_ist:
            decision = _build_hold_decision(
                reason="HOLD: Duplicate candle processing blocked by agent state.",
                timestamp_ist=timestamp_ist,
                ema_7=ema_7,
                position_active=self.state.current_open_position.active,
                strategy_state=_strategy_state_to_dict(self.state.admin_levels_state),
            )
            self.state.last_signal_generated = decision
            return decision

        self._update_admin_levels(self.state.previous_candle, candle)
        strategy_state_dict = _strategy_state_to_dict(self.state.admin_levels_state)
        ny_active = bool((strategy_state_dict or {}).get("nySessionActive", False))

        open_position_dict = {
            "active": self.state.current_open_position.active,
            "side": self.state.current_open_position.side,
            "entry_price": self.state.current_open_position.entry_price,
            "last_processed_candle_ts": self.state.last_processed_candle_ts,
        }
        decision = generate_signal(
            prev_candle=self.state.previous_candle,
            current_candle=candle,
            key_levels=self.state.active_admin_levels,
            ema_7=ema_7,
            capital=capital,
            open_position=open_position_dict,
            timestamp_ist=timestamp_ist,
            strategy_state=strategy_state_dict,
        )
        if decision["action"] in (Action.BUY.value, Action.SELL.value) and not ny_active:
            decision = _build_hold_decision(
                reason="HOLD: Outside allowed trading window (18:30–21:30 IST).",
                timestamp_ist=timestamp_ist,
                ema_7=ema_7,
                time_allowed=False,
                position_active=self.state.current_open_position.active,
                strategy_state=strategy_state_dict,
            )

        self.state.previous_candle = candle
        self.state.last_candle = candle
        self.state.last_signal_generated = decision
        self.state.inside_time_window = decision["time_allowed"]
        self.state.last_processed_candle_ts = timestamp_ist

        if decision["action"] in (Action.BUY.value, Action.SELL.value):
            self.state.current_open_position = PositionState(
                active=True,
                side=decision["action"],
                entry_price=decision["entry_price"],
                quantity=decision["quantity"],
                entry_timestamp_ist=timestamp_ist,
            )
        return decision

    def close_position(self) -> None:
        self.state.current_open_position = PositionState(active=False)
        logger.info("Position manually closed.")


@dataclass
class BacktestTrade:
    side: str
    entry_timestamp_ist: str
    exit_timestamp_ist: str
    entry_price: float
    exit_price: float
    quantity: float
    pnl_usd: float
    exit_reason: str


@dataclass
class BacktestResult:
    initial_capital: float
    ending_capital: float
    total_trades: int
    wins: int
    losses: int
    total_pnl_usd: float
    trades: List[BacktestTrade]
    decisions: List[Dict[str, Any]]
    equity_curve: List[Dict[str, Any]]
    day_summary: List[Dict[str, Any]]


def _calculate_pnl_usd(
    side: str, entry_price: float, exit_price: float, quantity: float, leverage: int
) -> float:
    price_delta = exit_price - entry_price
    if side == Action.SELL.value:
        price_delta = -price_delta
    return price_delta * quantity * leverage


def _threshold_exit_price(
    side: str, entry_price: float, quantity: float, leverage: int, pnl_usd: float
) -> float:
    """Price at which closing would realize exactly `pnl_usd`, inverting _calculate_pnl_usd."""
    delta = pnl_usd / (quantity * leverage)
    return entry_price + delta if side == Action.BUY.value else entry_price - delta


def _evaluate_exit_intrabar(
    position: PositionState, candle: Candle
) -> Tuple[bool, Optional[float], Optional[str], Optional[float]]:
    """
    Deterministic backtest exit check using the candle's intrabar high/low, not just
    its close — a fixed-$100 SL / $450 target under leverage can be breached well
    within a single candle's range, so a close-only check lets losses run past the
    intended cap (see _calculate_pnl_usd; a small price move is amplified by LEVERAGE).

    The entry candle itself is never checked: the position is filled at that candle's
    close, so none of its high/low range was experienced while the position was open.

    If both the SL and target price are inside the same candle's range (a rare, wide
    candle), SL is assumed hit first — a conservative tie-break since OHLC data can't
    tell us the true intrabar order.
    """
    if not position.active:
        return False, None, None, None
    if (
        position.side is None
        or position.entry_price is None
        or position.quantity is None
        or position.quantity <= 0
    ):
        return False, None, None, None
    if position.entry_timestamp_ist == candle.timestamp_ist:
        return False, None, None, None

    sl_price = _threshold_exit_price(
        position.side, position.entry_price, position.quantity, LEVERAGE, -STOP_LOSS_USD
    )
    target_price = _threshold_exit_price(
        position.side, position.entry_price, position.quantity, LEVERAGE, TARGET_USD
    )
    if position.side == Action.BUY.value:
        sl_hit = candle.low <= sl_price
        target_hit = candle.high >= target_price
    else:
        sl_hit = candle.high >= sl_price
        target_hit = candle.low <= target_price

    if sl_hit:
        pnl_usd = _calculate_pnl_usd(
            position.side, position.entry_price, sl_price, position.quantity, LEVERAGE
        )
        return True, pnl_usd, "SL_HIT_INTRABAR", sl_price
    if target_hit:
        pnl_usd = _calculate_pnl_usd(
            position.side, position.entry_price, target_price, position.quantity, LEVERAGE
        )
        return True, pnl_usd, "TARGET_HIT_INTRABAR", target_price

    pnl_usd = _calculate_pnl_usd(
        position.side, position.entry_price, candle.close, position.quantity, LEVERAGE
    )
    return False, pnl_usd, None, None


def run_backtest(
    candles: Sequence[Candle],
    ema_values: Sequence[Optional[float]],
    key_levels: Sequence[float],
    initial_capital: float,
    manual_swings: Optional[Dict[str, Tuple[float, float, Optional[float]]]] = None,
) -> BacktestResult:
    """
    Runs deterministic backtest over a candle sequence.

    Notes:
    - Uses the same signal logic as live processing.
    - Records per-candle decisions and equity curve.
    - Closes positions only when close-based SL/target condition is met.
    - `manual_swings` maps a trading-day date ("YYYY-MM-DD") to the admin's
      hand-drawn (swing_high, swing_low, anchor|None); when given, that day's
      ladder is projected from those swings instead of auto-detected extremes.
    """
    if len(candles) != len(ema_values):
        raise ValueError("candles and ema_values length mismatch.")

    capital = float(initial_capital)
    if capital <= 0:
        raise ValueError("initial_capital must be positive.")

    agent = DeterministicTradingAgent(key_levels=key_levels)
    for day, swing in (manual_swings or {}).items():
        high, low = swing[0], swing[1]
        anchor = swing[2] if len(swing) > 2 else None
        agent.set_manual_swings(day, high, low, anchor)
    decisions: List[Dict[str, Any]] = []
    trades: List[BacktestTrade] = []
    equity_curve: List[Dict[str, Any]] = []

    for idx, candle in enumerate(candles):
        timestamp_ist = candle.timestamp_ist
        decision = agent.on_candle_close(
            candle=candle,
            ema_7=ema_values[idx],
            capital=capital,
            timestamp_ist=timestamp_ist,
        )
        decisions.append(decision)

        should_exit, pnl_usd, exit_reason, exit_price = _evaluate_exit_intrabar(
            agent.state.current_open_position, candle
        )
        if should_exit and pnl_usd is not None and exit_reason is not None:
            pos = agent.state.current_open_position
            capital += pnl_usd
            trade = BacktestTrade(
                side=pos.side or Action.HOLD.value,
                entry_timestamp_ist=pos.entry_timestamp_ist or timestamp_ist,
                exit_timestamp_ist=timestamp_ist,
                entry_price=pos.entry_price or candle.close,
                exit_price=exit_price if exit_price is not None else candle.close,
                quantity=pos.quantity or 0.0,
                pnl_usd=pnl_usd,
                exit_reason=exit_reason,
            )
            trades.append(trade)
            agent.close_position()

        equity_curve.append(
            {
                "timestamp_ist": timestamp_ist,
                "capital": capital,
                "position_active": agent.state.current_open_position.active,
            }
        )

    total_pnl = sum(t.pnl_usd for t in trades)
    wins = sum(1 for t in trades if t.pnl_usd > 0)
    losses = sum(1 for t in trades if t.pnl_usd < 0)
    day_summary = _build_day_summary(trades)

    return BacktestResult(
        initial_capital=initial_capital,
        ending_capital=capital,
        total_trades=len(trades),
        wins=wins,
        losses=losses,
        total_pnl_usd=total_pnl,
        trades=trades,
        decisions=decisions,
        equity_curve=equity_curve,
        day_summary=day_summary,
    )


def _extract_trading_day(timestamp_ist: str) -> str:
    parsed = _parse_ist_timestamp(timestamp_ist)
    if parsed is None:
        return "UNKNOWN_DATE"
    return parsed.date().isoformat()


def _build_day_summary(trades: Sequence[BacktestTrade]) -> List[Dict[str, Any]]:
    grouped: Dict[str, Dict[str, Any]] = {}
    for trade in trades:
        day = _extract_trading_day(trade.exit_timestamp_ist)
        if day not in grouped:
            grouped[day] = {
                "date_ist": day,
                "trades": 0,
                "wins": 0,
                "losses": 0,
                "pnl_usd": 0.0,
            }
        grouped[day]["trades"] += 1
        grouped[day]["pnl_usd"] += trade.pnl_usd
        if trade.pnl_usd > 0:
            grouped[day]["wins"] += 1
        elif trade.pnl_usd < 0:
            grouped[day]["losses"] += 1
    return [grouped[d] for d in sorted(grouped)]


def _load_candles_from_csv(path: str) -> Tuple[List[Candle], List[Optional[float]]]:
    candles: List[Candle] = []
    ema_values: List[Optional[float]] = []
    with open(path, mode="r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        required = {"timestamp_ist", "open", "high", "low", "close", "ema_7"}
        missing = required.difference(set(reader.fieldnames or []))
        if missing:
            raise ValueError(
                f"CSV missing required columns: {', '.join(sorted(missing))}"
            )
        for row in reader:
            candles.append(
                Candle(
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    timestamp_ist=row["timestamp_ist"],
                )
            )
            ema_raw = row.get("ema_7")
            ema_values.append(_safe_float(ema_raw) if ema_raw not in ("", None) else None)
    return candles, ema_values


def _result_to_dict(result: BacktestResult) -> Dict[str, Any]:
    return {
        "initial_capital": result.initial_capital,
        "ending_capital": result.ending_capital,
        "total_trades": result.total_trades,
        "wins": result.wins,
        "losses": result.losses,
        "total_pnl_usd": result.total_pnl_usd,
        "day_summary": result.day_summary,
        "trades": [
            {
                "side": t.side,
                "entry_timestamp_ist": t.entry_timestamp_ist,
                "exit_timestamp_ist": t.exit_timestamp_ist,
                "entry_price": t.entry_price,
                "exit_price": t.exit_price,
                "quantity": t.quantity,
                "pnl_usd": t.pnl_usd,
                "exit_reason": t.exit_reason,
            }
            for t in result.trades
        ],
        "equity_curve": result.equity_curve,
        "decisions": result.decisions,
    }


def _write_dict_rows_to_csv(path: str, rows: Sequence[Dict[str, Any]]) -> None:
    if not rows:
        with open(path, mode="w", newline="", encoding="utf-8") as f:
            f.write("")
        return
    fieldnames = list(rows[0].keys())
    with open(path, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _parse_manual_swings(
    spec: str,
) -> Dict[str, Tuple[float, float, Optional[float]]]:
    """Parse 'YYYY-MM-DD:high,low[,anchor];...' into a manual-swings mapping."""
    swings: Dict[str, Tuple[float, float, Optional[float]]] = {}
    for entry in spec.split(";"):
        entry = entry.strip()
        if not entry:
            continue
        day, _, values = entry.partition(":")
        parts = [p.strip() for p in values.split(",") if p.strip()]
        if not day.strip() or len(parts) < 2:
            raise ValueError(f"Invalid --manual-swings entry: {entry!r}")
        high, low = float(parts[0]), float(parts[1])
        anchor = float(parts[2]) if len(parts) > 2 else None
        swings[day.strip()[:10]] = (high, low, anchor)
    return swings


def main() -> None:
    parser = argparse.ArgumentParser(description="Deterministic trading strategy backtest")
    parser.add_argument("--csv", required=True, help="Path to input OHLC+EMA CSV")
    parser.add_argument(
        "--key-levels",
        required=True,
        help="Comma-separated admin key levels, e.g. 23500,23620.5",
    )
    parser.add_argument("--capital", required=True, type=float, help="Initial capital")
    parser.add_argument(
        "--output-json",
        required=False,
        help="Optional file path to save backtest summary JSON",
    )
    parser.add_argument(
        "--output-decisions-csv",
        required=False,
        help="Optional file path for per-candle decision log CSV",
    )
    parser.add_argument(
        "--output-equity-csv",
        required=False,
        help="Optional file path for equity curve CSV",
    )
    parser.add_argument(
        "--manual-swings",
        required=False,
        default="",
        help=(
            "Admin hand-drawn swings per trading day, ';'-separated: "
            "'YYYY-MM-DD:high,low[,anchor]'. Example: "
            "'2026-06-24:63826,61693,62760;2026-06-30:61674,58734,60206'"
        ),
    )
    args = parser.parse_args()

    key_levels = [float(x.strip()) for x in args.key_levels.split(",") if x.strip()]
    manual_swings = _parse_manual_swings(args.manual_swings)
    candles, ema_values = _load_candles_from_csv(args.csv)
    result = run_backtest(
        candles=candles,
        ema_values=ema_values,
        key_levels=key_levels,
        initial_capital=args.capital,
        manual_swings=manual_swings,
    )

    result_dict = _result_to_dict(result)
    print(json.dumps(result_dict, indent=2))
    if args.output_json:
        with open(args.output_json, mode="w", encoding="utf-8") as f:
            json.dump(result_dict, f, indent=2)
    if args.output_decisions_csv:
        _write_dict_rows_to_csv(args.output_decisions_csv, result.decisions)
    if args.output_equity_csv:
        _write_dict_rows_to_csv(args.output_equity_csv, result.equity_curve)


if __name__ == "__main__":
    main()