from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from trading_agent import LEVERAGE, STOP_LOSS_USD, TARGET_USD, _threshold_exit_price

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_LOG_PATH = os.path.join(REPO_ROOT, "data_pipeline", "data", "live_trade_log.json")

# Status values a trade can hold. "Partially Closed" is distinct from "Open" so the UI
# can show that size was booked while the remainder still carries risk.
STATUS_OPEN = "Open"
STATUS_PARTIAL = "Partially Closed"
STATUS_TARGET = "Target Hit"
STATUS_STOP = "Stop Loss Hit"
STATUS_MANUAL = "Manual Exit"
STATUS_CLOSED = "Closed"

OPEN_STATUSES = (STATUS_OPEN, STATUS_PARTIAL)


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


def _normalize(row: Dict[str, Any]) -> Dict[str, Any]:
    """Fill in fields added after a record was first written.

    Older log entries predate partial booking and TP/SL editing, so readers would
    otherwise KeyError on them. Normalising on read keeps existing logs usable
    without a migration step.
    """
    row.setdefault("symbol", "BTC/USDT:USDT")
    row.setdefault("original_quantity", row.get("quantity"))
    row.setdefault("partial_exits", [])
    row.setdefault("tp_sl_modifications", [])
    booked = sum(float(p.get("quantity", 0.0)) for p in row["partial_exits"])
    row.setdefault(
        "remaining_quantity",
        max(float(row.get("original_quantity") or 0.0) - booked, 0.0)
        if row.get("status") in OPEN_STATUSES
        else 0.0,
    )
    row.setdefault("realized_pnl_usd", sum(float(p.get("pnl_usd", 0.0)) for p in row["partial_exits"]))
    return row


def _find_open(rows: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    for row in reversed(rows):
        if row.get("status") in OPEN_STATUSES:
            return row
    return None


def append_open_trade(
    decision: Dict[str, Any], symbol: str = "BTC/USDT:USDT", path: str = DEFAULT_LOG_PATH
) -> int:
    """Record a newly opened position. Returns the assigned trade number."""
    rows = [_normalize(r) for r in _load(path)]
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
            "symbol": symbol,
            "date": ts[:10],
            "entry_time": ts,
            "exit_time": None,
            "side": side,
            "entry_price": entry_price,
            "quantity": quantity,
            "original_quantity": quantity,
            "remaining_quantity": quantity,
            "stop_loss_price": stop_loss_price,
            "target_price": target_price,
            "risk_reward_ratio": TARGET_USD / STOP_LOSS_USD,
            "exit_price": None,
            "pnl_usd": None,
            "pnl_pct": None,
            "realized_pnl_usd": 0.0,
            "exit_reason": None,
            "status": STATUS_OPEN,
            "partial_exits": [],
            "tp_sl_modifications": [],
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
    """Close out the most recent open trade with its realized result.

    Any P&L already booked through partial exits is added to this final leg, so
    `pnl_usd` on the record is the trade's total result rather than just the last leg.
    """
    rows = [_normalize(r) for r in _load(path)]
    row = _find_open(rows)
    if row is None:
        return

    total_pnl = float(row.get("realized_pnl_usd") or 0.0) + float(pnl_usd)
    row["exit_time"] = timestamp_ist
    row["exit_price"] = exit_price
    row["pnl_usd"] = total_pnl
    row["pnl_pct"] = (total_pnl / capital_at_entry * 100.0) if capital_at_entry else None
    row["realized_pnl_usd"] = total_pnl
    row["remaining_quantity"] = 0.0
    row["exit_reason"] = exit_reason
    if "TARGET" in exit_reason:
        row["status"] = STATUS_TARGET
    elif "SL" in exit_reason:
        row["status"] = STATUS_STOP
    else:
        row["status"] = STATUS_CLOSED
    _save(path, rows)


def record_partial_exit(
    quantity: float,
    exit_price: float,
    timestamp_ist: str,
    reason: str = "PARTIAL_BOOK",
    path: str = DEFAULT_LOG_PATH,
) -> Dict[str, Any]:
    """Book part of the open position, leaving the remainder active.

    Returns the updated trade record. Raises ValueError if there is no open trade or
    the requested quantity exceeds what is still open — booking more than you hold
    would silently flip the position, so it is rejected rather than clamped.
    """
    rows = [_normalize(r) for r in _load(path)]
    row = _find_open(rows)
    if row is None:
        raise ValueError("No open trade to book against.")

    remaining = float(row.get("remaining_quantity") or 0.0)
    quantity = float(quantity)
    if quantity <= 0:
        raise ValueError("Partial quantity must be positive.")
    if quantity > remaining + 1e-12:
        raise ValueError(
            f"Requested {quantity:.6f} exceeds remaining {remaining:.6f}."
        )

    entry_price = float(row["entry_price"])
    delta = exit_price - entry_price
    if row["side"] == "SELL":
        delta = -delta
    leg_pnl = delta * quantity * LEVERAGE

    row["partial_exits"].append(
        {
            "timestamp_ist": timestamp_ist,
            "quantity": quantity,
            "exit_price": exit_price,
            "pnl_usd": leg_pnl,
            "reason": reason,
        }
    )
    row["realized_pnl_usd"] = float(row.get("realized_pnl_usd") or 0.0) + leg_pnl
    row["remaining_quantity"] = remaining - quantity
    row["quantity"] = row["remaining_quantity"]

    if row["remaining_quantity"] <= 1e-12:
        # Fully booked out through partials — treat as a closed manual exit.
        row["remaining_quantity"] = 0.0
        row["quantity"] = 0.0
        row["exit_time"] = timestamp_ist
        row["exit_price"] = exit_price
        row["pnl_usd"] = row["realized_pnl_usd"]
        row["exit_reason"] = "FULLY_BOOKED_PARTIALS"
        row["status"] = STATUS_MANUAL
    else:
        row["status"] = STATUS_PARTIAL

    _save(path, rows)
    return row


def record_tp_sl_change(
    timestamp_ist: str,
    new_target: Optional[float] = None,
    new_stop: Optional[float] = None,
    path: str = DEFAULT_LOG_PATH,
) -> Dict[str, Any]:
    """Amend TP and/or SL on the open trade, keeping an audit trail of every change."""
    rows = [_normalize(r) for r in _load(path)]
    row = _find_open(rows)
    if row is None:
        raise ValueError("No open trade to modify.")

    changed = False
    for field, key, new_value in (
        ("target_price", "target_price", new_target),
        ("stop_loss_price", "stop_loss_price", new_stop),
    ):
        if new_value is None:
            continue
        old_value = row.get(key)
        if old_value is not None and abs(float(old_value) - float(new_value)) < 1e-9:
            continue
        row["tp_sl_modifications"].append(
            {
                "timestamp_ist": timestamp_ist,
                "field": "target" if key == "target_price" else "stop_loss",
                "old_value": old_value,
                "new_value": float(new_value),
            }
        )
        row[key] = float(new_value)
        changed = True

    if changed:
        _save(path, rows)
    return row


def close_open_trade_manually(
    timestamp_ist: str, exit_price: Optional[float] = None, path: str = DEFAULT_LOG_PATH
) -> None:
    rows = [_normalize(r) for r in _load(path)]
    row = _find_open(rows)
    if row is None:
        return
    if exit_price is not None:
        entry_price = float(row["entry_price"])
        delta = exit_price - entry_price
        if row["side"] == "SELL":
            delta = -delta
        leg_pnl = delta * float(row.get("remaining_quantity") or 0.0) * LEVERAGE
        row["realized_pnl_usd"] = float(row.get("realized_pnl_usd") or 0.0) + leg_pnl
        row["pnl_usd"] = row["realized_pnl_usd"]
        row["exit_price"] = exit_price
    row["exit_time"] = timestamp_ist
    row["remaining_quantity"] = 0.0
    row["quantity"] = 0.0
    row["exit_reason"] = row.get("exit_reason") or "MANUAL_EXIT"
    row["status"] = STATUS_MANUAL
    _save(path, rows)


def load_trade_log(path: str = DEFAULT_LOG_PATH) -> List[Dict[str, Any]]:
    return [_normalize(r) for r in _load(path)]


def current_open_trade(path: str = DEFAULT_LOG_PATH) -> Optional[Dict[str, Any]]:
    return _find_open([_normalize(r) for r in _load(path)])
