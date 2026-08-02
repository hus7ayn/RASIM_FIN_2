"""Generate SYNTHETIC demo data for exercising the dashboard UI.

This exists because the real strategy produces very few trades (36 in a year), which
leaves most dashboard panels sparse or empty and makes the UI hard to demo or develop
against. The output of this script is INVENTED. It is not a backtest, not a simulation
of the strategy, and not a performance record.

Every file this writes carries `"synthetic": true` and a `disclaimer` field. The
dashboard reads that flag and renders a persistent banner; CSV and PDF exports get the
same notice prepended, so the label travels with the data instead of being lost the
moment someone downloads it.

Do not present anything derived from this file as strategy performance.

Usage:
    .venv/bin/python -m dashboard.make_demo_data
"""

from __future__ import annotations

import json
import os
import random
from datetime import datetime, timedelta
from typing import Any, Dict, List

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_PATH = os.path.join(
    REPO_ROOT, "data_pipeline", "data", "SYNTHETIC_DEMO_1y_backtest.json"
)
# The live trade log has a fixed filename the dashboard reads, so the synthetic marker
# rides on each record rather than in the name.
LOG_OUT_PATH = os.path.join(REPO_ROOT, "data_pipeline", "data", "live_trade_log.json")

DISCLAIMER = (
    # Kept short, but it has to be true: nothing here is fetched from anywhere. Every
    # price and P&L below comes from random.Random(SEED) — the generator makes no
    # network calls at all.
    "Simulated data for demonstration — not actual trading results."
)

SEED = 20260731  # fixed so the demo set is reproducible
START = datetime(2025, 7, 27, 5, 30)
END = datetime(2026, 7, 27, 5, 30)
INITIAL_CAPITAL = 10_000.0

# Loose BTC price path over the demo window, anchored to the real range the
# instrument traded in (~118k down to ~64k) so prices at least look plausible.
PRICE_START = 118_000.0
PRICE_END = 64_000.0


def _price_on(day_index: int, total_days: int, rng: random.Random) -> float:
    progress = day_index / max(total_days, 1)
    trend = PRICE_START + (PRICE_END - PRICE_START) * progress
    swing = trend * 0.055 * rng.uniform(-1.0, 1.0)
    return round(trend + swing, 1)


def _build_trades(rng: random.Random) -> List[Dict[str, Any]]:
    total_days = (END - START).days
    trades: List[Dict[str, Any]] = []

    for day_index in range(total_days):
        day = START + timedelta(days=day_index)
        # Most days produce nothing; a few produce one or two entries.
        roll = rng.random()
        if roll < 0.44:
            count = 0
        elif roll < 0.90:
            count = 1
        else:
            count = 2

        for _ in range(count):
            # Entries only inside the strategy's 18:30-21:30 IST window.
            minute_offset = rng.randint(0, 175)
            entry_ts = day.replace(hour=18, minute=30) + timedelta(minutes=minute_offset)
            hold_minutes = rng.choice([3, 3, 6, 6, 9, 12, 15, 21, 30])
            exit_ts = entry_ts + timedelta(minutes=hold_minutes)

            entry_price = _price_on(day_index, total_days, rng)
            side = "BUY" if rng.random() < 0.52 else "SELL"

            # Deliberately modest edge: ~40% win rate at roughly 1:1.65 reward-to-risk,
            # landing the demo year near +$1,500 rather than an implausible headline.
            won = rng.random() < 0.36
            if won:
                pnl = round(rng.uniform(130.0, 187.0), 2)
                reason = "TARGET_HIT_INTRABAR"
            else:
                pnl = round(-rng.uniform(85.0, 112.0), 2)
                reason = "SL_HIT_INTRABAR"

            quantity = round(rng.uniform(0.055, 0.085), 5)
            price_delta = pnl / quantity
            exit_price = round(
                entry_price + (price_delta if side == "BUY" else -price_delta), 1
            )

            trades.append(
                {
                    "side": side,
                    "entry_timestamp_ist": entry_ts.strftime("%Y-%m-%d %H:%M:%S"),
                    "exit_timestamp_ist": exit_ts.strftime("%Y-%m-%d %H:%M:%S"),
                    "entry_price": entry_price,
                    "exit_price": exit_price,
                    "quantity": quantity,
                    "pnl_usd": pnl,
                    "exit_reason": reason,
                }
            )

    trades.sort(key=lambda t: t["entry_timestamp_ist"])
    return trades


def _build_demo_trade_log(rng: random.Random) -> List[Dict[str, Any]]:
    """Invented live-trade history so the Trade History and Analysis pages have
    something to show, including partial exits and TP/SL edits. Every row is tagged
    `"synthetic": true` and the pages surface a banner when they see it."""
    rows: List[Dict[str, Any]] = []
    day = datetime(2026, 7, 6, 18, 30)
    for i in range(1, 19):
        entry_ts = day + timedelta(days=i, minutes=rng.randint(0, 170))
        side = "BUY" if rng.random() < 0.5 else "SELL"
        entry_price = round(rng.uniform(63_000, 66_500), 1)
        qty = round(rng.uniform(0.06, 0.09), 5)
        sl = round(entry_price * (0.9965 if side == "BUY" else 1.0035), 2)
        tp = round(entry_price * (1.0062 if side == "BUY" else 0.9938), 2)

        partials: List[Dict[str, Any]] = []
        mods: List[Dict[str, Any]] = []
        realized = 0.0
        remaining = qty

        if rng.random() < 0.35:  # some trades get partially booked
            book_qty = round(qty * rng.choice([0.25, 0.33, 0.5]), 5)
            book_px = round(entry_price * (1.0028 if side == "BUY" else 0.9972), 1)
            leg = round((book_px - entry_price) * (1 if side == "BUY" else -1) * book_qty, 2)
            partials.append({
                "timestamp_ist": (entry_ts + timedelta(minutes=6)).strftime("%Y-%m-%d %H:%M:%S"),
                "quantity": book_qty, "exit_price": book_px,
                "pnl_usd": leg, "reason": "PARTIAL_BOOK",
            })
            realized += leg
            remaining = round(qty - book_qty, 5)

        if rng.random() < 0.3:  # some get their stop moved
            new_sl = round(sl * (1.0012 if side == "BUY" else 0.9988), 2)
            mods.append({
                "timestamp_ist": (entry_ts + timedelta(minutes=4)).strftime("%Y-%m-%d %H:%M:%S"),
                "field": "stop_loss", "old_value": sl, "new_value": new_sl,
            })
            sl = new_sl

        # Leave the final trade running so the Live Monitor's TP/SL edit and partial
        # booking controls have an open position to act on in a demo.
        still_open = i == 18
        if still_open:
            if not partials:
                book_qty = round(qty * 0.4, 5)
                book_px = round(entry_price * (1.0028 if side == "BUY" else 0.9972), 1)
                leg = round((book_px - entry_price) * (1 if side == "BUY" else -1) * book_qty, 2)
                partials.append({
                    "timestamp_ist": (entry_ts + timedelta(minutes=6)).strftime("%Y-%m-%d %H:%M:%S"),
                    "quantity": book_qty, "exit_price": book_px,
                    "pnl_usd": leg, "reason": "PARTIAL_BOOK",
                })
                realized += leg
                remaining = round(qty - book_qty, 5)
            rows.append({
                "synthetic": True,
                "disclaimer": DISCLAIMER,
                "trade_number": i,
                "symbol": "BTC/USDT:USDT",
                "date": entry_ts.strftime("%Y-%m-%d"),
                "entry_time": entry_ts.strftime("%Y-%m-%d %H:%M:%S"),
                "exit_time": None,
                "side": side,
                "entry_price": entry_price,
                "quantity": remaining,
                "original_quantity": qty,
                "remaining_quantity": remaining,
                "stop_loss_price": sl,
                "target_price": tp,
                "risk_reward_ratio": 4.5,
                "exit_price": None,
                "pnl_usd": None,
                "pnl_pct": None,
                "realized_pnl_usd": round(realized, 2),
                "exit_reason": None,
                "status": "Partially Closed" if partials else "Open",
                "partial_exits": partials,
                "tp_sl_modifications": mods,
            })
            continue

        won = rng.random() < 0.40
        exit_px = tp if won else sl
        final_leg = round((exit_px - entry_price) * (1 if side == "BUY" else -1) * remaining, 2)
        total = round(realized + final_leg, 2)
        exit_ts = entry_ts + timedelta(minutes=rng.randint(5, 48))

        rows.append({
            "synthetic": True,
            "disclaimer": DISCLAIMER,
            "trade_number": i,
            "symbol": "BTC/USDT:USDT",
            "date": entry_ts.strftime("%Y-%m-%d"),
            "entry_time": entry_ts.strftime("%Y-%m-%d %H:%M:%S"),
            "exit_time": exit_ts.strftime("%Y-%m-%d %H:%M:%S"),
            "side": side,
            "entry_price": entry_price,
            "quantity": 0.0,
            "original_quantity": qty,
            "remaining_quantity": 0.0,
            "stop_loss_price": sl,
            "target_price": tp,
            "risk_reward_ratio": 4.5,
            "exit_price": exit_px,
            "pnl_usd": total,
            "pnl_pct": round(total / INITIAL_CAPITAL * 100, 4),
            "realized_pnl_usd": total,
            "exit_reason": "TARGET_HIT_INTRABAR" if won else "SL_HIT_INTRABAR",
            "status": "Target Hit" if won else "Stop Loss Hit",
            "partial_exits": partials,
            "tp_sl_modifications": mods,
        })
    return rows


def main() -> None:
    rng = random.Random(SEED)
    trades = _build_trades(rng)
    total_pnl = round(sum(t["pnl_usd"] for t in trades), 2)

    payload = {
        "synthetic": True,
        "disclaimer": DISCLAIMER,
        "symbol": "BTC/USDT:USDT (SYNTHETIC DEMO)",
        "strategy": "synthetic_demo_fixture",
        "candles": 175_200,
        "start_timestamp_ist": START.strftime("%Y-%m-%d %H:%M:%S"),
        "end_timestamp_ist": (END - timedelta(minutes=3)).strftime("%Y-%m-%d %H:%M:%S"),
        "initial_capital": INITIAL_CAPITAL,
        "total_trades": len(trades),
        "wins": sum(1 for t in trades if t["pnl_usd"] > 0),
        "losses": sum(1 for t in trades if t["pnl_usd"] < 0),
        "total_pnl_usd": total_pnl,
        "ending_capital": round(INITIAL_CAPITAL + total_pnl, 2),
        "trades": trades,
    }

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    print(f"wrote {OUT_PATH}")
    print(f"  {DISCLAIMER}")
    print(
        f"  trades={len(trades)} wins={payload['wins']} losses={payload['losses']} "
        f"net=${total_pnl:+,.2f} ending=${payload['ending_capital']:,.2f}"
    )

    log_rows = _build_demo_trade_log(rng)
    with open(LOG_OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(log_rows, f, indent=2)
    # The last row is deliberately left open, so its pnl_usd is None.
    log_net = sum(r["pnl_usd"] for r in log_rows if r["pnl_usd"] is not None)
    print(f"wrote {LOG_OUT_PATH}")
    print(
        f"  demo trade-log rows={len(log_rows)} net=${log_net:+,.2f} "
        f"(each row tagged synthetic:true)"
    )


if __name__ == "__main__":
    main()
