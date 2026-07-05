# End-to-End Trade Logic Report (Admin Levels + Deterministic Execution)

## 1) Scope and design intent

This report documents the implemented end-to-end strategy pipeline in `trading_agent.py` after integrating Admin Levels logic.

The strategy is:

- strictly `1-minute` candle based
- deterministic (same input candles => same outputs)
- non-repainting for finalized daily levels
- configurable for all critical session/time boundaries

## 2) Data and timeframe constraints

- Input data granularity: `1m` candles only
- Required per-candle fields: `open`, `high`, `low`, `close`, `timestamp_ist`
- Optional indicator input for entry filter: `ema_7` (already computed upstream in pipeline)
- No higher-timeframe aggregation is used in core decision logic

## 3) Trading day model

Trading day is custom, not midnight based:

- `tradingDayStart`: `05:30` IST (configurable)
- `tradingDayEnd`: next day `05:30` IST

Candles are grouped by this boundary using internal alignment logic.  
Example:

- candle at `05:29` belongs to previous trading day
- candle at `05:30` starts the next trading day

## 4) Range construction window (for admin levels)

Within each custom trading day, the strategy scans a configurable range window:

- default `rangeWindowStart`: `05:30`
- default `rangeWindowEnd`: `18:30`

From this window:

- `sessionHigh = max(high)`
- `sessionLow = min(low)`

Both anchors can be optionally gated by pivot confirmation (configurable helper).

## 5) Pivot confirmation near extremes

To avoid fragile inline logic, anchor confirmation is isolated in helper:

- `_is_pivot_confirmed_near_extreme(...)`

Behavior:

- can be enabled/disabled via config (`require_pivot_confirmation`)
- uses a simple local red/green reversal check
- uses tolerance near high/low (`pivot_tolerance_fraction`)

This keeps discretionary visual interpretation configurable and auditable.

## 6) Fib anchors

After range capture:

- `fib0 = sessionHigh`
- `fib1 = sessionLow`
- `fib0_5 = sessionLow + 0.5 * (sessionHigh - sessionLow)`

These are stored in daily strategy state and exposed in per-candle output.

## 7) 05:30 anchor close

The strategy captures the close of the day-start candle:

- `sessionOpenClose = close of 05:30 candle`

This value is the projection base for admin levels.

## 8) Admin level projection

Once range is available and day anchor exists, levels are projected from `sessionOpenClose`.

Defaults:

- levels per side: `6`
- step divisor: `6`
- step: `(sessionHigh - sessionLow) / 6`

Projection:

- `upLevels[i] = sessionOpenClose + i * step`
- `downLevels[i] = sessionOpenClose - i * step`
- `i = 1..6`

Stored as structured objects:

- `label` (`UP_1..UP_6`, `DOWN_1..DOWN_6`)
- `price`
- `direction`
- `index`

## 9) Level finalization and non-repainting

Daily levels are finalized once range window has ended and required values exist:

- `sessionHigh`, `sessionLow`, `sessionOpenClose`

After finalization:

- `levelsFinalized = true`
- projected level prices are frozen for that trading day
- later candles do not repaint those levels

At next trading day boundary, a fresh state is created.

## 10) Session filter for trade permission

Trade entries are NY-session gated (configurable, supports overnight window):

- default `nySessionStart`: `18:30` IST
- default `nySessionEnd`: `03:30` IST

Outside this session:

- levels are still computed and maintained
- entry actions are blocked (`HOLD`)

## 11) Signal generation pipeline (per candle close)

For each 1-minute candle close:

1. duplicate-candle guard  
2. current/previous OHLC validation  
3. trading-session permission check  
4. single-position-only guard  
5. EMA availability check  
6. key levels availability check (now sourced from computed admin levels when available)  
7. two-candle pattern validation  
8. EMA break check on current candle  
9. same-candle admin-level break aligned with EMA direction  
10. quantity calculation and action emission (`BUY` or `SELL`)  

If any condition fails => `HOLD` with explicit reason.

## 12) Entry confirmation rules

Conservative entry requires:

- valid 2-candle pattern:
  - `RED -> GREEN`
  - `GREEN -> RED`
  - `DOJI -> GREEN`
  - `DOJI -> RED`
- EMA break and admin-level break on same candle
- break direction alignment
- NY session active
- no active position

## 13) Position sizing and risk

Constants:

- `STOP_LOSS_USD = 100`
- `TARGET_USD = 450`
- `LEVERAGE = 13`
- `RISK_FRACTION = 0.03`

Size:

- `quantity = (RISK_FRACTION * capital) / STOP_LOSS_USD`

## 14) Exit logic

Exit is evaluated on every candle close (deterministic close-based model):

- BUY pnl: `(exit - entry) * quantity * leverage`
- SELL pnl: `(entry - exit) * quantity * leverage`

Exit criteria:

- `pnl <= -STOP_LOSS_USD` => `SL_HIT_ON_CLOSE`
- `pnl >= TARGET_USD` => `TARGET_HIT_ON_CLOSE`

Only one active position is allowed at any time.

## 15) Output model for auditing/debugging

Each decision now includes `strategy_state` with:

- `tradingDayStart`, `tradingDayEnd`
- `rangeWindowStart`, `rangeWindowEnd`
- `sessionHigh`, `sessionLow`
- `fib0`, `fib0_5`, `fib1`
- `sessionOpenClose`
- `adminLevelsUp[]`, `adminLevelsDown[]`
- `nySessionActive`
- `levelsFinalized`

This makes replay and screenshot reconciliation easier.

## 16) Test coverage added

Added in `tests/test_admin_levels_strategy.py`:

- 05:30 trading-day grouping behavior
- session high/low extraction
- fib midpoint correctness
- admin level spacing correctness
- no trade entries outside NY session
- non-repainting of levels after finalization

## 17) Configurability summary

All key boundaries and behaviors are configurable via `AdminLevelsConfig`:

- trading day start
- range window start/end
- NY session start/end
- number of levels per side
- step divisor
- pivot confirmation on/off
- pivot and interaction tolerances

This supports future tuning without architecture rewrites.

