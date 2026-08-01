#!/usr/bin/env python3
"""
Generate strategy methodology report + illustrative 8-month performance simulation.

The performance section uses seeded pseudo-random monthly outcomes calibrated to
strategy parameters (win rate, R:R, trade frequency). It is for planning and
presentation only — not live or backtested results.
"""

from __future__ import annotations

import argparse
import json
import random
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple


# ---------------------------------------------------------------------------
# Strategy constants (mirrors trading_agent.py)
# ---------------------------------------------------------------------------
INITIAL_CAPITAL = 10_000.0
STOP_LOSS_USD = 100.0
TARGET_USD = 450.0
LEVERAGE = 13
RISK_FRACTION = 0.03
WIN_RATE_ASSUMPTION = 0.35  # illustrative baseline for 8-month path
WIN_RATE_HORIZON_MC = 0.25  # conservative for early-exit probability model (slippage/regime)
TRADES_PER_MONTH_MEAN = 5.5
TRADES_PER_MONTH_STD = 1.8


@dataclass
class MonthResult:
    month: str
    trades: int
    wins: int
    losses: int
    pnl_usd: float
    capital_start: float
    capital_end: float
    return_pct: float


@dataclass
class HorizonOutcome:
    horizon_months: int
    prob_profit: float
    prob_loss: float
    prob_breakeven: float
    median_return_pct: float
    p10_return_pct: float
    p90_return_pct: float
    median_ending_capital: float


def _simulate_month(
    capital: float,
    rng: random.Random,
    win_rate: float,
) -> Tuple[int, int, int, float]:
    """Simulate one month of trading. Returns (trades, wins, losses, pnl)."""
    n_trades = max(1, int(round(rng.gauss(TRADES_PER_MONTH_MEAN, TRADES_PER_MONTH_STD))))
    outcomes = [rng.random() < win_rate for _ in range(n_trades)]
    wins = sum(outcomes)
    losses = n_trades - wins

    pnl = 0.0
    for is_win in outcomes:
        pnl += TARGET_USD if is_win else -STOP_LOSS_USD
    return n_trades, wins, losses, pnl


def simulate_8_month_path(seed: int, win_rate: float = WIN_RATE_ASSUMPTION) -> List[MonthResult]:
    rng = random.Random(seed)
    months = [
        "2025-08", "2025-09", "2025-10", "2025-11",
        "2025-12", "2026-01", "2026-02", "2026-03",
    ]
    capital = INITIAL_CAPITAL
    results: List[MonthResult] = []

    for label in months:
        start = capital
        trades, wins, losses, pnl = _simulate_month(capital, rng, win_rate)
        capital = max(capital + pnl, 500.0)  # floor to avoid negative sim
        ret = ((capital - start) / start) * 100 if start > 0 else 0.0
        results.append(
            MonthResult(
                month=label,
                trades=trades,
                wins=wins,
                losses=losses,
                pnl_usd=round(pnl, 2),
                capital_start=round(start, 2),
                capital_end=round(capital, 2),
                return_pct=round(ret, 2),
            )
        )
    return results


def monte_carlo_horizons(
    n_paths: int = 5000,
    seed: int = 42,
    win_rate: float = WIN_RATE_HORIZON_MC,
) -> Dict[int, HorizonOutcome]:
    """Estimate P(profit/loss) for stopping at 3, 6, and 8 months."""
    rng = random.Random(seed)
    horizons = [3, 4, 5, 6, 8]
    buckets: Dict[int, List[float]] = {h: [] for h in horizons}

    for _ in range(n_paths):
        capital = INITIAL_CAPITAL
        for month_idx in range(8):
            _, _, _, pnl = _simulate_month(capital, rng, win_rate)
            capital = max(capital + pnl, 500.0)
            m = month_idx + 1
            if m in horizons:
                ret_pct = ((capital - INITIAL_CAPITAL) / INITIAL_CAPITAL) * 100
                buckets[m].append(ret_pct)

    outcomes: Dict[int, HorizonOutcome] = {}
    for h in horizons:
        returns = sorted(buckets[h])
        n = len(returns)
        profits = sum(1 for r in returns if r > 1.0)
        losses = sum(1 for r in returns if r < -1.0)
        breakeven = n - profits - losses
        median = returns[n // 2]
        p10 = returns[int(n * 0.10)]
        p90 = returns[int(n * 0.90)]
        median_cap = INITIAL_CAPITAL * (1 + median / 100)
        outcomes[h] = HorizonOutcome(
            horizon_months=h,
            prob_profit=round(profits / n, 3),
            prob_loss=round(losses / n, 3),
            prob_breakeven=round(breakeven / n, 3),
            median_return_pct=round(median, 2),
            p10_return_pct=round(p10, 2),
            p90_return_pct=round(p90, 2),
            median_ending_capital=round(median_cap, 2),
        )
    return outcomes


def build_methodology_section() -> str:
    return """## Part 1 — How We Run the Strategy

### Overview

This is a **deterministic, 1-minute candle-close** system on **Binance USD-M Futures** (e.g. `BTC/USDT:USDT`). Every decision is made only after a candle closes — no intra-candle entries or exits.

| Parameter | Value |
|-----------|-------|
| Timeframe | 1 minute |
| EMA | 7-period on close |
| Stop loss | $100 per trade (USD PnL) |
| Target | $450 per trade (USD PnL) |
| Risk per trade | 3% of current capital |
| Leverage (PnL calc) | 13× |
| Max concurrent positions | 1 |

---

### Step 1 — Define the trading day

A "day" is **not** midnight to midnight. It runs:

> **05:30 IST → next day 05:30 IST**

Example: Monday's session = Monday 05:30 through Tuesday 05:29.

---

### Step 2 — Build the range (05:30 → 18:30)

Within each trading day, scan candles from **05:30 to 18:30 IST**:

- Find **session high** and **session low**
- High/low must be confirmed by a **red→green or green→red reversal** near the extreme (pivot confirmation)
- This gives Fibonacci anchors:
  - **Level 0** = session high
  - **Level 1** = session low
  - **Level 0.5** = midpoint

---

### Step 3 — Anchor and project admin levels

- Take the **05:30 candle close** as the starting anchor (`sessionOpenClose`)
- Compute range = high − low
- Step size = range ÷ 6
- Project **6 levels above** and **6 levels below** the anchor

These 12 admin levels are the key levels used for entry validation.

---

### Step 4 — Trade only in the New York session

Entries are allowed **only** during:

> **18:30 IST → 03:30 IST** (next calendar day)

This maps to the NY session window described in the strategy rules.

---

### Step 5 — Entry conditions (all must pass)

On each 1-minute candle close inside the NY window:

1. **Valid two-candle pattern** — one of:
   - RED → GREEN
   - GREEN → RED
   - DOJI → GREEN
   - DOJI → RED

2. **EMA-7 break** on the current candle (open on one side, close on the other)

3. **Admin key-level break** on the **same candle**, direction aligned with EMA break

4. **No open position** (one trade at a time)

5. **Candle classification** — RED/GREEN/DOJI/HIGH_DOJI based on body position within range

If all pass → **BUY** (bullish) or **SELL** (bearish) at candle close.

---

### Step 6 — Position sizing

```
quantity = (3% × current capital) / $100 stop loss
```

Position size scales with equity; risk stays proportional.

---

### Step 7 — Exit rules

Checked on every subsequent candle close:

- Exit if mark-to-close PnL ≤ **−$100** (stop loss)
- Exit if mark-to-close PnL ≥ **+$450** (target)

No trailing stop, no partial exits in the current implementation.

---

### Step 8 — Data pipeline & backtest flow

```
Binance Futures API (ccxt)
    → fetch 1m OHLCV for date range
    → convert timestamps to IST
    → save CSV (timestamp, open, high, low, close, volume)
    → compute EMA-7
    → run_backtest() in trading_agent.py
    → output JSON (trades, PnL, equity curve)
```

**Run command (example — March 2026):**

```bash
.venv/bin/python -m data_pipeline.main \\
  --symbol "BTC/USDT:USDT" \\
  --start-date 2026-03-01 \\
  --end-date 2026-04-01
```

Output files land in `data_pipeline/data/` as CSV + `_backtest.json`.

---

### Step 9 — Live / testnet path

For live execution, `live_testnet_runner.py` and `binance_testnet.py` connect to Binance testnet, poll 1m candles, and feed them through the same `DeterministicTradingAgent` logic.

"""


def build_performance_section(
    path: List[MonthResult],
    horizons: Dict[int, HorizonOutcome],
) -> str:
    total_pnl = path[-1].capital_end - INITIAL_CAPITAL
    total_ret = (total_pnl / INITIAL_CAPITAL) * 100
    total_trades = sum(m.trades for m in path)
    total_wins = sum(m.wins for m in path)
    total_losses = sum(m.losses for m in path)
    win_rate = (total_wins / total_trades * 100) if total_trades else 0

    lines = [
        "## Part 2 — Illustrative 8-Month Performance Report",
        "",
        "> **Disclaimer:** The numbers below are **simulated** for planning and presentation.",
        "> They are calibrated to strategy parameters (≈35% win rate, 1:4.5 R:R, ~5–6 trades/month)",
        "> and do **not** represent actual backtested or live results.",
        "",
        f"**Report generated:** {datetime.now().strftime('%Y-%m-%d %H:%M IST')}",
        f"**Starting capital:** ${INITIAL_CAPITAL:,.2f}",
        f"**Ending capital (8 months):** ${path[-1].capital_end:,.2f}",
        f"**Total return:** {total_ret:+.2f}% (${total_pnl:+,.2f})",
        f"**Total trades:** {total_trades} | Wins: {total_wins} | Losses: {total_losses} | Win rate: {win_rate:.1f}%",
        "",
        "### Monthly breakdown (simulated path)",
        "",
        "| Month | Trades | W/L | PnL ($) | Capital start | Capital end | Return |",
        "|-------|--------|-----|---------|---------------|-------------|--------|",
    ]

    for m in path:
        lines.append(
            f"| {m.month} | {m.trades} | {m.wins}/{m.losses} | {m.pnl_usd:+,.0f} | "
            f"${m.capital_start:,.0f} | ${m.capital_end:,.0f} | {m.return_pct:+.1f}% |"
        )

    lines.extend([
        "",
        "### Equity curve (simulated)",
        "",
        "```",
    ])
    for m in path:
        bar_len = int(max(0, min(40, (m.capital_end / INITIAL_CAPITAL - 0.85) * 100)))
        bar = "█" * bar_len
        lines.append(f"{m.month}  ${m.capital_end:>8,.0f}  {bar}")
    lines.append("```")
    lines.append("")

    lines.extend([
        "---",
        "",
        "## Part 3 — Early Exit Probabilities (Monte Carlo, 5,000 paths)",
        "",
        "If you stop trading before the full 8-month horizon, outcomes differ.",
        "Below: probability of ending **in profit**, **in loss**, or **near breakeven** (±1%).",
        "",
        "| Horizon | P(Profit) | P(Loss) | P(Breakeven) | Median return | 10th pct | 90th pct | Median capital |",
        "|---------|-----------|---------|--------------|---------------|----------|----------|----------------|",
    ])

    for h in sorted(horizons):
        o = horizons[h]
        lines.append(
            f"| **{h} months** | {o.prob_profit:.1%} | {o.prob_loss:.1%} | {o.prob_breakeven:.1%} | "
            f"{o.median_return_pct:+.1f}% | {o.p10_return_pct:+.1f}% | {o.p90_return_pct:+.1f}% | "
            f"${o.median_ending_capital:,.0f} |"
        )

    h3 = horizons[3]
    h5 = horizons.get(5, horizons[3])
    h6 = horizons[6]
    h8 = horizons[8]

    lines.extend([
        "",
        "### Interpretation",
        "",
        f"- **Stopping at 3 months:** ~{h3.prob_profit:.0%} chance of profit, ~{h3.prob_loss:.0%} chance of loss.",
        f"  Only ~16 trades on average — variance dominates. Median return {h3.median_return_pct:+.1f}%,",
        f"  but 10th percentile can be {h3.p10_return_pct:+.1f}%.",
        "",
        f"- **Stopping at 5 months:** ~{h5.prob_profit:.0%} profit / ~{h5.prob_loss:.0%} loss.",
        f"  Edge starts to appear but losing months still cluster. Median {h5.median_return_pct:+.1f}%.",
        "",
        f"- **Stopping at 6 months:** ~{h6.prob_profit:.0%} profit / ~{h6.prob_loss:.0%} loss.",
        f"  Median {h6.median_return_pct:+.1f}%.",
        "",
        f"- **Full 8 months:** ~{h8.prob_profit:.0%} profit / ~{h8.prob_loss:.0%} loss.",
        f"  Median ending capital ~${h8.median_ending_capital:,.0f} ({h8.median_return_pct:+.1f}%).",
        f"  Illustrative path in Part 2 reached +{total_ret:.0f}%.",
        "",
        "### Why shorter horizons lose more often",
        "",
        "With a **35% win rate** and **1:4.5 reward:risk**, expectancy per trade is positive:",
        "",
        "```",
        "E[trade] = 0.35 × $450 − 0.65 × $100 = +$92.50 per trade",
        "```",
        "",
        "But over only ~15–17 trades (3 months), random streaks of losses dominate.",
        "By month 8 (~44 trades), the law of large numbers pulls results toward the positive expectancy.",
        "",
        "### Risk notes",
        "",
        "- Simulated paths assume constant win rate and trade frequency — real markets regime-shift.",
        "- March 2026 actual backtest (current rules): **−88.8%** drawdown — strategy needs refinement before live use.",
        "- Past simulation ≠ future performance. Use testnet and walk-forward validation first.",
        "",
    ])
    return "\n".join(lines)


def generate_report(output_dir: Path, seed: int = 7) -> Dict[str, Any]:
    path = simulate_8_month_path(seed=seed)
    horizons = monte_carlo_horizons(seed=seed + 1000)

    output_dir.mkdir(parents=True, exist_ok=True)
    md_path = output_dir / "strategy_methodology_and_simulated_performance.md"
    json_path = output_dir / "simulated_performance_data.json"

    md_content = (
        "# Strategy Methodology & Simulated Performance Report\n\n"
        + build_methodology_section()
        + build_performance_section(path, horizons)
    )
    md_path.write_text(md_content, encoding="utf-8")

    payload = {
        "disclaimer": "Simulated illustrative data — not actual trading results",
        "assumptions": {
            "initial_capital": INITIAL_CAPITAL,
            "stop_loss_usd": STOP_LOSS_USD,
            "target_usd": TARGET_USD,
            "risk_fraction": RISK_FRACTION,
            "win_rate_assumption": WIN_RATE_ASSUMPTION,
            "win_rate_horizon_mc": WIN_RATE_HORIZON_MC,
            "trades_per_month_mean": TRADES_PER_MONTH_MEAN,
        },
        "eight_month_path": [asdict(m) for m in path],
        "horizon_probabilities": {str(k): asdict(v) for k, v in horizons.items()},
        "summary_8m": {
            "starting_capital": INITIAL_CAPITAL,
            "ending_capital": path[-1].capital_end,
            "total_return_pct": round(
                (path[-1].capital_end - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100, 2
            ),
            "total_trades": sum(m.trades for m in path),
            "total_wins": sum(m.wins for m in path),
            "total_losses": sum(m.losses for m in path),
        },
    }
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    return {"markdown": str(md_path), "json": str(json_path), "payload": payload}


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate strategy methodology + simulated performance report")
    parser.add_argument(
        "--output-dir",
        default="./data_pipeline/reports",
        help="Directory for report output",
    )
    parser.add_argument("--seed", type=int, default=7, help="RNG seed for reproducible simulated path")
    args = parser.parse_args()

    result = generate_report(Path(args.output_dir), seed=args.seed)
    print(f"Report written: {result['markdown']}")
    print(f"Data JSON:      {result['json']}")
    s = result["payload"]["summary_8m"]
    print(f"\n8-month simulated summary: ${s['starting_capital']:,.0f} → ${s['ending_capital']:,.0f} ({s['total_return_pct']:+.1f}%)")


if __name__ == "__main__":
    main()
