from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from trading_agent import LEVERAGE, STOP_LOSS_USD, TARGET_USD, _threshold_exit_price

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_LOG_PATH = os.path.join(REPO_ROOT, "data_pipeline", "data", "live_trade_log.json")


def _load(path: str) -> List[Dict[str, Any]]:
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        content = f.read().strip()
    return json.loads(content) if content else []


def _save(path: str, rows: List[Dict[str, Any]]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2)


def append_open_trade(decision: Dict[str, Any], path: str = DEFAULT_LOG_PATH) -> int:
    """Record a newly opened position. Returns the assigned trade number."""
    rows = _load(path)
    trade_number = len(rows) + 1
    entry_price = decision["entry_price"]
    quantity = decision["quantity"]
    side = decision["action"]
    stop_loss_price = _threshold_exit_price(side, entry_price, quantity, LEVERAGE, -STOP_LOSS_USD)
    target_price = _threshold_exit_price(side, entry_price, quantity, LEVERAGE, TARGET_USD)
    ts = decision["timestamp_ist"]
    rows.append(
        {
            "trade_number": trade_number,
            "date": ts[:10],
            "entry_time": ts,
            "exit_time": None,
            "side": side,
            "entry_price": entry_price,
            "quantity": quantity,
            "stop_loss_price": stop_loss_price,
            "target_price": target_price,
            "risk_reward_ratio": TARGET_USD / STOP_LOSS_USD,
            "exit_price": None,
            "pnl_usd": None,
            "pnl_pct": None,
            "exit_reason": None,
            "status": "Open",
        }
    )
    _save(path, rows)
    return trade_number


def append_close_trade(
    pnl_usd: float,
    exit_price: float,
    exit_reason: str,
    timestamp_ist: str,
    capital_at_entry: Optional[float] = None,
    path: str = DEFAULT_LOG_PATH,
) -> None:
    """Close out the most recent open trade record with its realized result."""
    rows = _load(path)
    for row in reversed(rows):
        if row["status"] == "Open":
            row["exit_time"] = timestamp_ist
            row["exit_price"] = exit_price
            row["pnl_usd"] = pnl_usd
            row["pnl_pct"] = (pnl_usd / capital_at_entry * 100.0) if capital_at_entry else None
            row["exit_reason"] = exit_reason
            if "TARGET" in exit_reason:
                row["status"] = "Target Hit"
            elif "SL" in exit_reason:
                row["status"] = "Stop Loss Hit"
            else:
                row["status"] = "Closed"
            break
    _save(path, rows)


def close_open_trade_manually(timestamp_ist: str, path: str = DEFAULT_LOG_PATH) -> None:
    rows = _load(path)
    for row in reversed(rows):
        if row["status"] == "Open":
            row["exit_time"] = timestamp_ist
            row["status"] = "Manual Exit"
            break
    _save(path, rows)


def load_trade_log(path: str = DEFAULT_LOG_PATH) -> List[Dict[str, Any]]:
    return _load(path)


def current_open_trade(path: str = DEFAULT_LOG_PATH) -> Optional[Dict[str, Any]]:
    rows = _load(path)
    for row in reversed(rows):
        if row["status"] == "Open":
            return row
    return None
