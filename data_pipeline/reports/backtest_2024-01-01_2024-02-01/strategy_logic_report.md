# Strategy Summary and Full Logic

## 1) Backtest run summarized

- Instrument: `BTC/USDT:USDT` (Binance futures symbol format)
- Timeframe: `1m`
- Period: `2024-01-01 05:30:00` to `2024-02-01 05:29:00` (IST timestamps in dataset)
- Candles processed: `44,640`
- Initial capital: `$10,000.00`
- Ending capital: `$9,657.23`
- Net PnL: `$-342.77`
- Total closed trades: `4`
- Wins/Losses: `1 / 3` (Win rate: `25.00%`)

## 2) Parameters used

From `trading_agent.py`:

- `STOP_LOSS_USD = 100`
- `TARGET_USD = 450`
- `LEVERAGE = 13`
- `RISK_FRACTION = 0.03`
- Trading window (IST): `18:30` to `21:30`
- Doji tolerance:
  - `DOJI_NEARNESS_MIN = 0.10`
  - `DOJI_NEARNESS_MAX = 0.20`

Key levels used in this backtest report:

- Count: `25`
- Range: `38,000` to `50,000`
- Step: `500`
- Note: these were auto-generated for this run so that the strategy could produce trade signals; with empty key levels, the strategy returns HOLD.

## 3) Signal logic (entry rules)

The strategy is deterministic and evaluates at each candle close.

### Step-by-step decision pipeline

1. **Duplicate protection**
   - If candle timestamp was already processed, return `HOLD`.

2. **Data validity checks**
   - Current candle must be valid OHLC.
   - Previous candle must exist and be valid.
   - Else return `HOLD`.

3. **Time filter**
   - Current candle timestamp must be inside IST window `18:30` to `21:30`.
   - Else return `HOLD`.

4. **Single-position rule**
   - If there is already an active position, return `HOLD`.

5. **EMA availability**
   - EMA-7 must be present and numeric.
   - Else return `HOLD`.

6. **Key levels availability**
   - At least one key level must be provided.
   - Else return `HOLD`.

7. **Two-candle pattern validation**
   - Candle types are classified (`RED`, `GREEN`, `DOJI`, `HIGH_DOJI`).
   - Allowed transitions:
     - `RED -> GREEN`
     - `GREEN -> RED`
     - `DOJI -> GREEN`
     - `DOJI -> RED`
   - If pair is not allowed, return `HOLD`.

8. **EMA break confirmation**
   - Bullish EMA break: `open < ema_7` and `close > ema_7`
   - Bearish EMA break: `open > ema_7` and `close < ema_7`
   - If no EMA break, return `HOLD`.

9. **Key-level break in same direction**
   - For any admin key level:
     - Bullish key break: `open < level` and `close > level`
     - Bearish key break: `open > level` and `close < level`
   - A valid entry requires key-level break direction == EMA break direction.
   - If no aligned level found, return `HOLD`.

10. **Position sizing and action**
   - Quantity formula:
     - `quantity = (RISK_FRACTION * capital) / STOP_LOSS_USD`
   - If aligned break direction is bullish -> `BUY`
   - If aligned break direction is bearish -> `SELL`

## 4) Candle classification rules

### RED candle

- `open` is near `low` (using tiny tolerance)
- `close >= high * 0.90`

### GREEN candle

- `open` is near `high`
- `close <= low * 1.10`

### DOJI candle

- Open-close are near each other (exactly near OR within 10% to 20% of full candle range)
- Open is near midpoint: `(high + low) / 2`

### HIGH_DOJI candle

- Open-close near each other (same tolerance as doji)
- Open near first-half point: `(high + low) / 4`
- Open is in first half (`open <= midpoint`)

## 5) Exit and PnL logic

After entry, on each candle close:

- Compute mark-to-close PnL:
  - For BUY: `(exit_price - entry_price) * quantity * leverage`
  - For SELL: `(entry_price - exit_price) * quantity * leverage`
- Exit rules:
  - If `pnl <= -100` -> exit reason `SL_HIT_ON_CLOSE`
  - If `pnl >= 450` -> exit reason `TARGET_HIT_ON_CLOSE`
  - Otherwise keep position open
- On exit:
  - Capital is updated: `capital += pnl`
  - Trade is recorded with side, timestamps, prices, quantity, pnl, exit reason
- Only one active position is allowed at a time.

## 6) Trades produced in this run

1. BUY at `2024-01-08 19:57:00` -> SL hit, `-362.70`
2. SELL at `2024-01-19 20:31:00` -> SL hit, `-481.09`
3. BUY at `2024-01-24 18:36:00` -> SL hit, `-210.68`
4. BUY at `2024-01-29 20:46:00` -> Target hit, `+711.71`

Net result = `-342.77` USD.

## 7) Why trades are few

- Strict time window (`3 hours/day`)
- Multiple sequential filters (pattern + EMA break + key-level break alignment)
- One-position-only constraint
- Relatively high TP/SL thresholds in USD

## 8) Files generated for this run

- `summary.json` (headline metrics)
- `trades.csv` (trade-by-trade ledger)
- `equity_curve.csv` (capital over time)
- `equity_curve.png` (equity visualization)
- `trade_pnl.png` (trade PnL bars)
- `trades_on_price.png` (entries/exits on price)

