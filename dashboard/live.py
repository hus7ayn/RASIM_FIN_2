from __future__ import annotations

import time as time_module
from typing import Any, Dict, List, Optional

import ccxt

from strategies import get_strategy
from trading_agent import Action, Candle

CANDLE_LIMIT = 500  # 500 x 3m ~= 25h, enough to span the current trading day from 05:30 IST


def build_market_data_exchange() -> ccxt.binanceusdm:
    """Public market data stream — no API keys required (same endpoint as live_testnet_runner.py)."""
    return ccxt.binanceusdm(
        {
            "enableRateLimit": True,
            "options": {"defaultType": "future"},
            "timeout": 30000,
            "urls": {"api": {"fapiPublic": "https://demo-fapi.binance.com/fapi/v1"}},
        }
    )


def _to_candle(row: list) -> Candle:
    ts_ms = int(row[0])
    ts_ist = time_module.strftime("%Y-%m-%d %H:%M:%S", time_module.gmtime(ts_ms / 1000 + 19800))
    return Candle(open=float(row[1]), high=float(row[2]), low=float(row[3]), close=float(row[4]), timestamp_ist=ts_ist)


def fetch_recent_candles(symbol: str, timeframe: str = "3m", limit: int = CANDLE_LIMIT) -> List[Candle]:
    mdx = build_market_data_exchange()
    rows = mdx.fetch_ohlcv(symbol=symbol, timeframe=timeframe, limit=limit)
    return [_to_candle(r) for r in rows]


def compute_ema7(closes: List[float]) -> List[float]:
    ema_values: List[float] = []
    ema = closes[0] if closes else 0.0
    alpha = 2.0 / (7 + 1)
    for i, c in enumerate(closes):
        ema = c if i == 0 else (c * alpha) + (ema * (1 - alpha))
        ema_values.append(ema)
    return ema_values


def _session_status(state, ny_active: bool) -> str:
    if state is None:
        return "Waiting"
    if state.levels_finalized:
        return "Finalized"
    if state.session_high is not None or state.session_low is not None:
        return "Tracking"
    return "Waiting"


def _bias(current_price: float, ema_7: Optional[float]) -> str:
    if ema_7 is None:
        return "Neutral"
    if current_price > ema_7:
        return "Bullish"
    if current_price < ema_7:
        return "Bearish"
    return "Neutral"


def _trend(closes: List[float], lookback: int = 10) -> str:
    if len(closes) < lookback + 1:
        return "Unknown"
    delta = closes[-1] - closes[-1 - lookback]
    if delta > 0:
        return "Up"
    if delta < 0:
        return "Down"
    return "Sideways"


def get_live_snapshot(
    symbol: str,
    key_levels: Optional[List[float]],
    capital: float,
    strategy_name: str = "admin_levels_reversal",
) -> Dict[str, Any]:
    """Fetch recent candles, replay them through the real strategy engine, and return
    a flat snapshot dict for dashboard rendering. Looks up the strategy via the
    strategies/ registry — the same registry backtest.py and live_testnet_runner.py
    can use — instead of importing one hardcoded strategy class."""
    candles = fetch_recent_candles(symbol=symbol)
    if len(candles) < 2:
        return {"error": "Not enough candle data returned from the exchange."}

    closes = [c.close for c in candles]
    emas = compute_ema7(closes)

    agent = get_strategy(strategy_name, key_levels=key_levels or None)
    decision = None
    for idx, c in enumerate(candles):
        decision = agent.on_candle_close(c, ema_7=emas[idx], capital=capital, timestamp_ist=c.timestamp_ist)

    state = agent.state.admin_levels_state
    last_candle = candles[-1]
    current_price = last_candle.close
    current_ema = emas[-1]
    ny_active = bool(decision.get("strategy_state", {}).get("nySessionActive", False)) if decision else False

    session_high = state.session_high if state else None
    session_low = state.session_low if state else None
    anchor = state.session_open_close if state else None
    fib0_5 = state.fib0_5 if state else None

    def _distance(target: Optional[float]) -> Optional[Dict[str, float]]:
        if target is None:
            return None
        diff = current_price - target
        pct = (diff / target * 100.0) if target else 0.0
        return {"price_diff": diff, "pct_diff": pct}

    levels_up = [lvl.__dict__ for lvl in state.admin_levels_up] if state else []
    levels_down = [lvl.__dict__ for lvl in state.admin_levels_down] if state else []
    all_levels = sorted(levels_up + levels_down, key=lambda l: l["price"]) if (levels_up or levels_down) else []
    nearest_level = None
    if all_levels:
        nearest_level = min(all_levels, key=lambda l: abs(l["price"] - current_price))

    position_active = bool(decision.get("position_active")) if decision else False
    waiting_for_confirmation = bool(
        decision and ny_active and decision["action"] == Action.HOLD.value and not position_active
    )

    return {
        "symbol": symbol,
        "current_price": current_price,
        "current_ema_7": current_ema,
        "last_candle_ts_ist": last_candle.timestamp_ist,
        "session_status": _session_status(state, ny_active),
        "ny_session_active": ny_active,
        "session_high": session_high,
        "session_low": session_low,
        "session_range": (session_high - session_low) if (session_high is not None and session_low is not None) else None,
        "fib0": state.fib0 if state else None,
        "fib0_5": fib0_5,
        "fib1": state.fib1 if state else None,
        "anchor_opening_level": anchor,
        "levels_up": levels_up,
        "levels_down": levels_down,
        "nearest_level": nearest_level,
        "used_unconfirmed_fallback": state.used_unconfirmed_fallback if state else False,
        "levels_finalized": state.levels_finalized if state else False,
        "distance_from_high": _distance(session_high),
        "distance_from_low": _distance(session_low),
        "distance_from_mid": _distance(fib0_5),
        "distance_from_opening": _distance(anchor),
        "bias": _bias(current_price, current_ema),
        "trend": _trend(closes),
        "active_signal": decision["action"] if decision else "HOLD",
        "signal_reason": decision["reason"] if decision else None,
        "waiting_for_confirmation": waiting_for_confirmation,
        "position_active": position_active,
    }
