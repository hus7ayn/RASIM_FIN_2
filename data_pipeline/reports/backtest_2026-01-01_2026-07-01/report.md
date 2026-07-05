# 6-Month Backtest Report (BTC/USDT:USDT)

Period: 2026-01-01 05:30:00 to 2026-07-01 05:27:00
Candles analyzed: 86,880 (1-minute bars)
Trades analyzed: 10

## Summary

| Metric | Value |
|---|---|
| Initial capital | $10,000.00 |
| Ending capital | $10,650.00 |
| Total PnL | $+650.00 |
| Return | +6.50% |
| Total trades | 10 |
| Wins / Losses | 3 / 7 |
| Win rate | 30.0% |
| Avg win | $+450.00 |
| Avg loss | $-100.00 |
| Stop loss / Target | $100 / $450 (intrabar-enforced) |
| Leverage | 13x |
| Risk per trade | 3.0% of capital |
| Key levels | Auto-projected admin ladder (12:30-18:30 IST session range / 6, pivot-confirmed) |

## Trade Log

| Entry Time (IST) | Side | Entry | Exit | Qty | PnL (USD) | Exit Reason |
|---|---|---|---|---|---|---|
| 2026-01-10 18:36:00 | BUY | 90704.5 | 90701.9 | 3.0000 | -100.00 | SL_HIT_INTRABAR |
| 2026-01-17 19:30:00 | SELL | 95311.5 | 95314.1 | 2.9700 | -100.00 | SL_HIT_INTRABAR |
| 2026-01-18 21:21:00 | BUY | 95043.2 | 95055.0 | 2.9400 | +450.00 | TARGET_HIT_INTRABAR |
| 2026-01-24 19:24:00 | BUY | 89500.0 | 89497.5 | 3.0750 | -100.00 | SL_HIT_INTRABAR |
| 2026-02-01 19:18:00 | SELL | 78426.6 | 78415.2 | 3.0450 | +450.00 | TARGET_HIT_INTRABAR |
| 2026-03-29 20:21:00 | SELL | 66511.0 | 66513.4 | 3.1800 | -100.00 | SL_HIT_INTRABAR |
| 2026-04-04 18:51:00 | SELL | 67063.3 | 67065.7 | 3.1500 | -100.00 | SL_HIT_INTRABAR |
| 2026-04-04 19:03:00 | BUY | 67073.9 | 67085.0 | 3.1200 | +450.00 | TARGET_HIT_INTRABAR |
| 2026-05-03 20:12:00 | BUY | 78672.3 | 78669.9 | 3.2550 | -100.00 | SL_HIT_INTRABAR |
| 2026-05-17 19:00:00 | SELL | 78212.3 | 78214.7 | 3.2250 | -100.00 | SL_HIT_INTRABAR |

## Notes

- Exit checks are **intrabar** (candle high/low vs. SL/target price), not close-only — this caps every
  loss at exactly -$100 and every win at exactly +$450.
- Admin levels are auto-projected each day from the 12:30-18:30 IST session high/low (pivot-confirmed
  reversal required), not hand-picked swings. Most days do not produce a confirmed session range, which
  is why only 10 trades fired across 86,880 1-minute candles.
- Data source: real Binance Futures (BTC/USDT:USDT) 1-minute OHLCV, `/Users/hussain/RASIM_FIN_2/data_pipeline/data/BTCUSDTUSDT_1m_2026-01-01_2026-07-01.csv`.
