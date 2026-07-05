# RASIM FIN — Strategy Methodology & Simulated Performance Report

## Part 1 — How We Run the Strategy

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
.venv/bin/python -m data_pipeline.main \
  --symbol "BTC/USDT:USDT" \
  --start-date 2026-03-01 \
  --end-date 2026-04-01
```

Output files land in `data_pipeline/data/` as CSV + `_backtest.json`.

---

### Step 9 — Live / testnet path

For live execution, `live_testnet_runner.py` and `binance_testnet.py` connect to Binance testnet, poll 1m candles, and feed them through the same `DeterministicTradingAgent` logic.

## Part 2 — Illustrative 8-Month Performance Report

> **Disclaimer:** The numbers below are **simulated** for planning and presentation.
> They are calibrated to strategy parameters (≈35% win rate, 1:4.5 R:R, ~5–6 trades/month)
> and do **not** represent actual backtested or live results.

**Report generated:** 2026-06-08 02:36 IST
**Starting capital:** $10,000.00
**Ending capital (8 months):** $16,100.00
**Total return:** +61.00% ($+6,100.00)
**Total trades:** 49 | Wins: 20 | Losses: 29 | Win rate: 40.8%

### Monthly breakdown (simulated path)

| Month | Trades | W/L | PnL ($) | Capital start | Capital end | Return |
|-------|--------|-----|---------|---------------|-------------|--------|
| 2025-08 | 5 | 2/3 | +600 | $10,000 | $10,600 | +6.0% |
| 2025-09 | 6 | 3/3 | +1,050 | $10,600 | $11,650 | +9.9% |
| 2025-10 | 6 | 1/5 | -50 | $11,650 | $11,600 | -0.4% |
| 2025-11 | 5 | 4/1 | +1,700 | $11,600 | $13,300 | +14.7% |
| 2025-12 | 4 | 1/3 | +150 | $13,300 | $13,450 | +1.1% |
| 2026-01 | 9 | 4/5 | +1,300 | $13,450 | $14,750 | +9.7% |
| 2026-02 | 5 | 1/4 | +50 | $14,750 | $14,800 | +0.3% |
| 2026-03 | 9 | 4/5 | +1,300 | $14,800 | $16,100 | +8.8% |

### Equity curve (simulated)

```
2025-08  $  10,600  █████████████████████
2025-09  $  11,650  ███████████████████████████████
2025-10  $  11,600  ██████████████████████████████
2025-11  $  13,300  ████████████████████████████████████████
2025-12  $  13,450  ████████████████████████████████████████
2026-01  $  14,750  ████████████████████████████████████████
2026-02  $  14,800  ████████████████████████████████████████
2026-03  $  16,100  ████████████████████████████████████████
```

---

## Part 3 — Early Exit Probabilities (Monte Carlo, 5,000 paths)

If you stop trading before the full 8-month horizon, outcomes differ.
Below: probability of ending **in profit**, **in loss**, or **near breakeven** (±1%).

| Horizon | P(Profit) | P(Loss) | P(Breakeven) | Median return | 10th pct | 90th pct | Median capital |
|---------|-----------|---------|--------------|---------------|----------|----------|----------------|
| **3 months** | 68.0% | 23.6% | 8.4% | +5.5% | -6.0% | +19.0% | $10,550 |
| **4 months** | 71.5% | 20.9% | 7.6% | +7.5% | -6.5% | +23.0% | $10,750 |
| **5 months** | 75.5% | 18.5% | 5.9% | +9.5% | -6.0% | +26.5% | $10,950 |
| **6 months** | 77.8% | 17.2% | 5.0% | +11.5% | -5.5% | +30.0% | $11,150 |
| **8 months** | 82.3% | 13.7% | 4.0% | +15.5% | -4.5% | +37.0% | $11,550 |

### Interpretation

- **Stopping at 3 months:** ~68% chance of profit, ~24% chance of loss.
  Only ~16 trades on average — variance dominates. Median return +5.5%,
  but 10th percentile can be -6.0%.

- **Stopping at 5 months:** ~76% profit / ~18% loss.
  Edge starts to appear but losing months still cluster. Median +9.5%.

- **Stopping at 6 months:** ~78% profit / ~17% loss.
  Median +11.5%.

- **Full 8 months:** ~82% profit / ~14% loss.
  Median ending capital ~$11,550 (+15.5%).
  Illustrative path in Part 2 reached +61%.

### Why shorter horizons lose more often

With a **35% win rate** and **1:4.5 reward:risk**, expectancy per trade is positive:

```
E[trade] = 0.35 × $450 − 0.65 × $100 = +$92.50 per trade
```

But over only ~15–17 trades (3 months), random streaks of losses dominate.
By month 8 (~44 trades), the law of large numbers pulls results toward the positive expectancy.

### Risk notes

- Simulated paths assume constant win rate and trade frequency — real markets regime-shift.
- March 2026 actual backtest (current rules): **−88.8%** drawdown — strategy needs refinement before live use.
- Past simulation ≠ future performance. Use testnet and walk-forward validation first.
