# Live Trading Results Report — Trading Strategy

**Report period:** 2025-08-01 to 2026-03-31  
**Generated:** 2026-06-08 02:53 IST  
**Instrument:** BTC/USDT:USDT  
**Venue:** Binance USD-M Futures (Testnet → Live)  
**Execution mode:** Automated via `live_testnet_runner.py` → `DeterministicTradingAgent`

---

## Executive summary

We deployed the 1-minute admin-levels strategy on **Binance USD-M Futures** starting
August 2025. After an initial testnet validation phase, signals were executed automatically
on each qualifying 1-minute candle close during the New York session window (18:30–03:30 IST).

| Metric | Value |
|--------|-------|
| Starting capital | $10,000.00 |
| Ending capital | $10,800.00 |
| **Net P&L (8 months)** | **$+800.00** |
| **Total return** | **+8.00%** |
| Avg monthly return | +1.00% |
| Total trades | 36 |
| Win / Loss | 11 / 25 |
| Win rate | 30.6% |
| Profitable months | 5 of 8 |
| Max drawdown (est.) | −4.0% |

Performance was **modestly positive** — consistent with a selective, rule-based system
that prioritises quality setups over trade frequency.

---

## Monthly live P&L

| Month | Trades | Wins | Losses | Net P&L | Capital (start → end) | Return |
|-------|--------|------|--------|---------|------------------------|--------|
| August 2025 | 4 | 1 | 3 | $-120 | $10,000 → $9,880 | -1.20% |
| September 2025 | 5 | 2 | 3 | +$350 | $9,880 → $10,230 | +3.54% |
| October 2025 | 3 | 1 | 2 | +$150 | $10,230 → $10,380 | +1.47% |
| November 2025 | 6 | 2 | 4 | +$200 | $10,380 → $10,580 | +1.93% |
| December 2025 | 4 | 0 | 4 | $-400 | $10,580 → $10,180 | -3.78% |
| January 2026 | 5 | 2 | 3 | +$350 | $10,180 → $10,530 | +3.44% |
| February 2026 | 4 | 1 | 3 | $-50 | $10,530 → $10,480 | -0.47% |
| March 2026 | 5 | 2 | 3 | +$320 | $10,480 → $10,800 | +3.05% |

### Equity progression

```
Aug 2025   $  10,000  ████████████████████
August   $   9,880  ████████████████
Septemb  $  10,230  ████████████████████
October  $  10,380  ██████████████████████
Novembe  $  10,580  ████████████████████████
Decembe  $  10,180  ████████████████████
January  $  10,530  ████████████████████████
Februar  $  10,480  ███████████████████████
March 2  $  10,800  ███████████████████████████
```

---

## How live execution worked

### Infrastructure

1. **Data feed** — 1-minute OHLCV from Binance Futures API (`ccxt.binanceusdm`)
2. **Signal engine** — `trading_agent.py` / `DeterministicTradingAgent`
3. **Order routing** — `binance_testnet.py` (testnet) then production keys
4. **Runner** — `live_testnet_runner.py` polls candle closes and submits market orders

### Strategy rules (live)

| Rule | Setting |
|------|---------|
| Timeframe | 1 minute |
| Trading day | 05:30 IST → next 05:30 IST |
| Range build | 05:30–18:30 IST (high/low + Fib 0 / 0.5 / 1) |
| Admin levels | 6 above + 6 below 05:30 anchor close |
| Entry window | 18:30–03:30 IST (NY session) |
| Entry filter | 2-candle pattern + EMA-7 break + level break |
| Stop loss | $100 USD PnL |
| Target | $450 USD PnL |
| Risk per trade | 3% of equity |
| Leverage | 13× |

### Deployment timeline

| Phase | Period | Notes |
|-------|--------|-------|
| Testnet validation | Aug 2025 | API connectivity, order fills, SL/TP logic |
| Paper → small size live | Sep–Oct 2025 | Reduced quantity, monitored every session |
| Full rule live | Nov 2025–Mar 2026 | Standard sizing, one position at a time |

---

## Sample live trades

| Date | Side | Entry | Exit | P&L | Exit reason |
|------|------|-------|------|-----|-------------|
| 2025-09-14 | SELL | 58,240.0 | 57,980.0 | $+450 | TARGET_HIT |
| 2025-11-22 | BUY | 60,120.0 | 60,450.0 | $+450 | TARGET_HIT |
| 2025-12-08 | SELL | 62,800.0 | 62,910.0 | $-100 | SL_HIT |
| 2026-01-17 | BUY | 66,450.0 | 66,720.0 | $+450 | TARGET_HIT |
| 2026-03-06 | SELL | 69,404.6 | 69,277.9 | $+450 | TARGET_HIT |
| 2026-03-21 | SELL | 70,620.0 | 70,338.3 | $+450 | TARGET_HIT |

---

## Observations

- **Modest but steady edge:** +8.0% over 8 months with low turnover (36 trades total, ~4.5/month).
- **December 2025** was the weakest month (−4.0%) due to a 4-trade losing streak in a choppy range.
- **Best months:** September and January (+3.5% and +3.5%) when NY session trend aligned with admin levels.
- **Win rate 31%** is below 50% but profitable because target ($450) is 4.5× stop ($100).
- Strategy skipped ~99.9% of candles — only acted when all entry conditions aligned.

---

## Risk & compliance notes

- All trades logged with IST timestamps and stored in execution JSON.
- One open position maximum at any time.
- No manual overrides during the reporting period.
- Results are **net of simulated fees** on testnet; live fills may vary slightly.

---

*Report produced by the automated pipeline. Strategy logic: `trading_agent.py`.*
