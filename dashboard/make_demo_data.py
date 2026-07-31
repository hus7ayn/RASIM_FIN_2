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

DISCLAIMER = (
    "SYNTHETIC DEMO DATA - INVENTED FOR UI DEMONSTRATION ONLY. "
    "These trades never happened and do not represent strategy performance."
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

            # Deliberately modest edge: ~40% win rate at roughly 1:1.6 reward-to-risk,
            # which lands the demo year near +13% rather than an implausible headline.
            won = rng.random() < 0.36
            if won:
                pnl = round(rng.uniform(130.0, 185.0), 2)
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


if __name__ == "__main__":
    main()
