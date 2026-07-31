# RASIM_FIN_2 — Implementation Overview

This document explains how the system is currently built: the strategy implementation, the
technology it runs on, the user interface it exposes today, and how data is stored. It reflects
the codebase as it exists right now, not a target design.

## 1. Implementation

### Strategy engine (`trading_agent.py`)
A deterministic, rule-based reversal strategy on BTC/USDT perpetual futures, 3-minute candles.
No ML — every decision is a fixed boolean chain.

- **Candle classification**: a candle is `RED` (open≈high, close≈low — bearish shape) or
  `GREEN` (open≈low, close≈high — bullish shape), based on configurable open/close-to-extreme
  tolerances. A candle that fits neither is unclassified and can't participate in a signal.
- **Entry pattern**: only the second candle of a `RED→GREEN` (bullish reversal) or `GREEN→RED`
  (bearish reversal) pair is considered.
- **Admin key levels** — two sources, either can drive the ladder for a trading day:
  - *Auto-projected*: each trading day starts at 05:30 IST; session high/low are tracked during
    a 12:30–18:30 IST window, but an extreme only counts once a same-direction candle-pair
    reversal (pivot confirmation) lands within a tolerance of it — this filters out isolated
    wick spikes. At 18:30 IST the range freezes into `fib0`/`fib1`/`fib0.5` and 6 levels are
    projected above and below the 05:30 open/close anchor, spaced at `range / 6`.
  - *Manual override* (`set_manual_swings`): an admin can hand-supply a swing high/low (and
    optionally a custom anchor) for a specific trading day, which takes priority over
    auto-detection for that day.
- **Signal trigger**: on a pattern-valid candle, inside the 18:30–21:30 IST trade window, with
  no open position, requires an EMA-7 break *and* a same-direction key-level break on the same
  candle to emit BUY/SELL; otherwise HOLD (with a reason).
- **Risk & sizing**: `quantity = (3% × capital) / $100`, 13× isolated leverage, $100 stop-loss /
  $450 target in leveraged USD PnL (~1:4.5 risk:reward).
- **Exit (backtest)**: intrabar check against the candle's high/low (not just its close), so a
  fast single-candle move can't blow past the nominal SL/target the way a close-only check would.
- The engine only **decides** — it never places orders itself.

### Execution layer
- `binance_testnet.py` — wraps `ccxt.binanceusdm` pointed at Binance's demo futures endpoint.
  Reads API credentials from environment variables only (`BINANCE_TESTNET_API_KEY`/`SECRET`);
  no secrets are stored in the repo. Places market entry + reduce-only STOP_MARKET/
  TAKE_PROFIT_MARKET orders from a decision payload; defaults to validate-only orders.
- `live_testnet_runner.py` — polls public 3-minute candles from Binance, computes EMA-7,
  feeds them into the strategy engine, and forwards each decision to the execution layer
  (currently hardcoded to validate-only — it never places a live-filled order as written).

### Data pipeline (`data_pipeline/`)
- Fetches paginated historical OHLCV from Binance Futures (`fetch_binance.py`), with retry/
  backoff and a pagination step derived from the configured timeframe.
- `main.py` is the CLI entry point: fetch → save CSV → compute EMA-7 → run a backtest → save
  a JSON summary, per symbol.

### Backtesting
`run_backtest` in `trading_agent.py` replays a candle sequence through the exact same
`DeterministicTradingAgent` used for live processing (no separate/simplified logic), producing
a trade list, equity curve, per-candle decision log, and day-level summary.

### Report generators (standalone scripts)
`diagnostic_report.py`, `generate_strategy_report.py`, `generate_live_results_report.py`,
`generate_extensive_reports.py` — each reads backtest/live JSON output and writes a markdown
(and sometimes PNG) report. These are one-off analysis scripts, not part of the live/backtest
decision path.

## 2. Supporting Technology

| Layer | Technology |
|---|---|
| Language / runtime | Python 3.13, `.venv` virtualenv |
| Exchange connectivity | `ccxt` (`binanceusdm`), against Binance USD-M Futures demo/testnet endpoints |
| Data handling | `pandas` (OHLCV frames, EMA calculation) |
| Testing | `pytest` (plain function-based tests, no framework classes) |
| CLI | `argparse`, invoked directly per script — no unified CLI entry point |
| Config | Plain Python module (`data_pipeline/config.py`) — no YAML/JSON config layer |
| Secrets | Environment variables only (`BINANCE_TESTNET_API_KEY`/`SECRET`); nothing hardcoded or committed |

There is no web framework, no task queue, no message broker, and no containerization in the
current codebase — everything runs as directly-invoked Python scripts/processes.

## 3. User Interface

**There is currently no graphical or web user interface.** All interaction happens through:
- CLI flags (`--symbol`, `--start-date`, `--key-levels`, `--manual-swings`, `--capital`, etc.)
  on individual scripts.
- Console/log output (`logging` to stdout) showing per-candle decisions during live/backtest runs.
- Generated markdown/JSON/CSV files as the only durable "view" of results — there is no live
  dashboard, chart rendering, or persistent UI process.

`decision.json` is a one-off sample payload (a hand-authored example decision), not a UI
artifact or a config file the system reads automatically.

## 4. Data Storage

Everything is flat-file based — **no database** (SQL or NoSQL) is used anywhere:

| Data | Format | Location |
|---|---|---|
| Historical OHLCV | CSV | `data_pipeline/data/<symbol>_<tf>_<start>_<end>.csv` |
| Backtest results (trades, PnL, equity curve, decisions) | JSON | `data_pipeline/data/..._backtest.json` |
| Diagnostic / strategy / live-results reports | Markdown (+ occasional PNG) | `data_pipeline/reports/` |
| Sample manual decision payload | JSON | `decision.json` (repo root) |
| Per-candle decision logs / equity curves (optional CLI output) | CSV | wherever `--output-decisions-csv` / `--output-equity-csv` point |

Nothing is persisted across runs automatically — each backtest/report run reads its inputs
fresh and writes new output files; there is no accumulating trade-history store, no live
position/state persistence across process restarts, and no automatic retention/rotation of
old output files.
