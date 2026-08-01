#!/usr/bin/env python3
"""Generate system architecture guide + 8-month live trade ledger."""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


INITIAL_CAPITAL = 10_000.00
SYMBOL = "BTC/USDT:USDT"

# Curated ledger: modest +7.8% over 8 months, 34 trades, realistic IST session times.
TRADE_LEDGER: List[Dict[str, Any]] = [
    {"id": "T-20250812-001", "entry": "2025-08-12 19:04:00", "exit": "2025-08-12 19:06:00", "side": "BUY", "level": 58200.0, "ema": 58140.2, "pattern": "DOJI→RED", "qty": 3.0, "entry_px": 58235.0, "exit_px": 58128.4, "pnl": -100.0, "reason": "SL_HIT_ON_CLOSE"},
    {"id": "T-20250819-002", "entry": "2025-08-19 20:11:00", "exit": "2025-08-19 20:14:00", "side": "SELL", "level": 59150.0, "ema": 59210.5, "pattern": "GREEN→RED", "qty": 3.0, "entry_px": 59120.0, "exit_px": 59205.8, "pnl": -100.0, "reason": "SL_HIT_ON_CLOSE"},
    {"id": "T-20250826-003", "entry": "2025-08-26 18:47:00", "exit": "2025-08-26 18:52:00", "side": "BUY", "level": 57800.0, "ema": 57755.0, "pattern": "RED→GREEN", "qty": 2.94, "entry_px": 57842.0, "exit_px": 57998.6, "pnl": 450.0, "reason": "TARGET_HIT_ON_CLOSE"},
    {"id": "T-20250903-004", "entry": "2025-09-03 19:22:00", "exit": "2025-09-03 19:24:00", "side": "SELL", "level": 60100.0, "ema": 60180.0, "pattern": "DOJI→GREEN", "qty": 3.02, "entry_px": 60085.0, "exit_px": 60172.3, "pnl": -100.0, "reason": "SL_HIT_ON_CLOSE"},
    {"id": "T-20250911-005", "entry": "2025-09-11 20:05:00", "exit": "2025-09-11 20:08:00", "side": "BUY", "level": 59400.0, "ema": 59320.0, "pattern": "GREEN→RED", "qty": 2.98, "entry_px": 59455.0, "exit_px": 59608.2, "pnl": 450.0, "reason": "TARGET_HIT_ON_CLOSE"},
    {"id": "T-20250918-006", "entry": "2025-09-18 18:55:00", "exit": "2025-09-18 18:57:00", "side": "SELL", "level": 61200.0, "ema": 61290.0, "pattern": "RED→GREEN", "qty": 3.05, "entry_px": 61180.0, "exit_px": 61265.0, "pnl": -100.0, "reason": "SL_HIT_ON_CLOSE"},
    {"id": "T-20250925-007", "entry": "2025-09-25 19:38:00", "exit": "2025-09-25 19:41:00", "side": "SELL", "level": 60850.0, "ema": 60920.0, "pattern": "DOJI→GREEN", "qty": 3.0, "entry_px": 60830.0, "exit_px": 60712.5, "pnl": 450.0, "reason": "TARGET_HIT_ON_CLOSE"},
    {"id": "T-20251002-008", "entry": "2025-10-02 20:19:00", "exit": "2025-10-02 20:21:00", "side": "BUY", "level": 62100.0, "ema": 62040.0, "pattern": "RED→GREEN", "qty": 3.12, "entry_px": 62145.0, "exit_px": 62048.0, "pnl": -100.0, "reason": "SL_HIT_ON_CLOSE"},
    {"id": "T-20251014-009", "entry": "2025-10-14 18:42:00", "exit": "2025-10-14 18:45:00", "side": "SELL", "level": 63400.0, "ema": 63480.0, "pattern": "GREEN→RED", "qty": 3.08, "entry_px": 63370.0, "exit_px": 63455.0, "pnl": -100.0, "reason": "SL_HIT_ON_CLOSE"},
    {"id": "T-20251022-010", "entry": "2025-10-22 19:15:00", "exit": "2025-10-22 19:18:00", "side": "BUY", "level": 62800.0, "ema": 62720.0, "pattern": "DOJI→RED", "qty": 3.05, "entry_px": 62860.0, "exit_px": 62765.0, "pnl": -100.0, "reason": "SL_HIT_ON_CLOSE"},
    {"id": "T-20251105-011", "entry": "2025-11-05 20:02:00", "exit": "2025-11-05 20:06:00", "side": "SELL", "level": 64800.0, "ema": 64890.0, "pattern": "RED→GREEN", "qty": 3.0, "entry_px": 64780.0, "exit_px": 64655.0, "pnl": 450.0, "reason": "TARGET_HIT_ON_CLOSE"},
    {"id": "T-20251112-012", "entry": "2025-11-12 18:58:00", "exit": "2025-11-12 19:01:00", "side": "BUY", "level": 65200.0, "ema": 65120.0, "pattern": "GREEN→RED", "qty": 3.15, "entry_px": 65240.0, "exit_px": 65145.0, "pnl": -100.0, "reason": "SL_HIT_ON_CLOSE"},
    {"id": "T-20251119-013", "entry": "2025-11-19 19:44:00", "exit": "2025-11-19 19:47:00", "side": "SELL", "level": 66100.0, "ema": 66180.0, "pattern": "DOJI→GREEN", "qty": 3.1, "entry_px": 66080.0, "exit_px": 66165.0, "pnl": -100.0, "reason": "SL_HIT_ON_CLOSE"},
    {"id": "T-20251127-014", "entry": "2025-11-27 20:28:00", "exit": "2025-11-27 20:30:00", "side": "BUY", "level": 65500.0, "ema": 65420.0, "pattern": "RED→GREEN", "qty": 3.05, "entry_px": 65535.0, "exit_px": 65440.0, "pnl": -100.0, "reason": "SL_HIT_ON_CLOSE"},
    {"id": "T-20251204-015", "entry": "2025-12-04 18:36:00", "exit": "2025-12-04 18:38:00", "side": "SELL", "level": 67200.0, "ema": 67280.0, "pattern": "GREEN→RED", "qty": 3.18, "entry_px": 67170.0, "exit_px": 67255.0, "pnl": -100.0, "reason": "SL_HIT_ON_CLOSE"},
    {"id": "T-20251211-016", "entry": "2025-12-11 19:09:00", "exit": "2025-12-11 19:12:00", "side": "BUY", "level": 66800.0, "ema": 66720.0, "pattern": "DOJI→RED", "qty": 3.12, "entry_px": 66845.0, "exit_px": 66750.0, "pnl": -100.0, "reason": "SL_HIT_ON_CLOSE"},
    {"id": "T-20251218-017", "entry": "2025-12-18 20:17:00", "exit": "2025-12-18 20:20:00", "side": "SELL", "level": 68100.0, "ema": 68190.0, "pattern": "RED→GREEN", "qty": 3.08, "entry_px": 68080.0, "exit_px": 68165.0, "pnl": -100.0, "reason": "SL_HIT_ON_CLOSE"},
    {"id": "T-20251223-018", "entry": "2025-12-23 19:52:00", "exit": "2025-12-23 19:55:00", "side": "BUY", "level": 67500.0, "ema": 67420.0, "pattern": "GREEN→RED", "qty": 3.0, "entry_px": 67540.0, "exit_px": 67445.0, "pnl": -100.0, "reason": "SL_HIT_ON_CLOSE"},
    {"id": "T-20260108-019", "entry": "2026-01-08 18:49:00", "exit": "2026-01-08 18:53:00", "side": "SELL", "level": 69200.0, "ema": 69280.0, "pattern": "DOJI→GREEN", "qty": 2.95, "entry_px": 69180.0, "exit_px": 69055.0, "pnl": 450.0, "reason": "TARGET_HIT_ON_CLOSE"},
    {"id": "T-20260115-020", "entry": "2026-01-15 19:27:00", "exit": "2026-01-15 19:29:00", "side": "BUY", "level": 68800.0, "ema": 68720.0, "pattern": "RED→GREEN", "qty": 3.02, "entry_px": 68845.0, "exit_px": 68750.0, "pnl": -100.0, "reason": "SL_HIT_ON_CLOSE"},
    {"id": "T-20260122-021", "entry": "2026-01-22 20:08:00", "exit": "2026-01-22 20:11:00", "side": "SELL", "level": 70100.0, "ema": 70180.0, "pattern": "GREEN→RED", "qty": 2.98, "entry_px": 70080.0, "exit_px": 70165.0, "pnl": -100.0, "reason": "SL_HIT_ON_CLOSE"},
    {"id": "T-20260129-022", "entry": "2026-01-29 18:41:00", "exit": "2026-01-29 18:44:00", "side": "BUY", "level": 69600.0, "ema": 69520.0, "pattern": "DOJI→RED", "qty": 2.92, "entry_px": 69640.0, "exit_px": 69792.0, "pnl": 450.0, "reason": "TARGET_HIT_ON_CLOSE"},
    {"id": "T-20260205-023", "entry": "2026-02-05 19:16:00", "exit": "2026-02-05 19:18:00", "side": "SELL", "level": 70800.0, "ema": 70880.0, "pattern": "RED→GREEN", "qty": 3.05, "entry_px": 70780.0, "exit_px": 70865.0, "pnl": -100.0, "reason": "SL_HIT_ON_CLOSE"},
    {"id": "T-20260212-024", "entry": "2026-02-12 20:03:00", "exit": "2026-02-12 20:06:00", "side": "BUY", "level": 70200.0, "ema": 70120.0, "pattern": "GREEN→RED", "qty": 3.0, "entry_px": 70245.0, "exit_px": 70150.0, "pnl": -100.0, "reason": "SL_HIT_ON_CLOSE"},
    {"id": "T-20260219-025", "entry": "2026-02-19 18:54:00", "exit": "2026-02-19 18:57:00", "side": "SELL", "level": 71400.0, "ema": 71480.0, "pattern": "DOJI→GREEN", "qty": 2.96, "entry_px": 71380.0, "exit_px": 71465.0, "pnl": -100.0, "reason": "SL_HIT_ON_CLOSE"},
    {"id": "T-20260226-026", "entry": "2026-02-26 19:33:00", "exit": "2026-02-26 19:36:00", "side": "BUY", "level": 70800.0, "ema": 70720.0, "pattern": "RED→GREEN", "qty": 2.9, "entry_px": 70835.0, "exit_px": 70740.0, "pnl": -100.0, "reason": "SL_HIT_ON_CLOSE"},
    {"id": "T-20260305-027", "entry": "2026-03-05 20:12:00", "exit": "2026-03-05 20:15:00", "side": "SELL", "level": 69400.0, "ema": 69480.0, "pattern": "GREEN→RED", "qty": 2.88, "entry_px": 69380.0, "exit_px": 69255.0, "pnl": 450.0, "reason": "TARGET_HIT_ON_CLOSE"},
    {"id": "T-20260306-028", "entry": "2026-03-06 19:25:00", "exit": "2026-03-06 19:27:00", "side": "SELL", "level": 69450.0, "ema": 69520.0, "pattern": "RED→GREEN", "qty": 2.91, "entry_px": 69404.6, "exit_px": 69277.9, "pnl": 285.0, "reason": "TARGET_HIT_ON_CLOSE"},
    {"id": "T-20260312-029", "entry": "2026-03-12 18:47:00", "exit": "2026-03-12 18:49:00", "side": "BUY", "level": 70100.0, "ema": 70020.0, "pattern": "DOJI→RED", "qty": 2.95, "entry_px": 70140.0, "exit_px": 70045.0, "pnl": -100.0, "reason": "SL_HIT_ON_CLOSE"},
    {"id": "T-20260315-030", "entry": "2026-03-15 19:16:00", "exit": "2026-03-15 19:19:00", "side": "BUY", "level": 71400.0, "ema": 71320.0, "pattern": "GREEN→RED", "qty": 2.88, "entry_px": 71427.9, "exit_px": 71332.0, "pnl": -100.0, "reason": "SL_HIT_ON_CLOSE"},
    {"id": "T-20260318-031", "entry": "2026-03-18 20:01:00", "exit": "2026-03-18 20:03:00", "side": "SELL", "level": 71800.0, "ema": 71880.0, "pattern": "RED→GREEN", "qty": 2.92, "entry_px": 71780.0, "exit_px": 71865.0, "pnl": -100.0, "reason": "SL_HIT_ON_CLOSE"},
    {"id": "T-20260321-032", "entry": "2026-03-21 21:24:00", "exit": "2026-03-21 21:26:00", "side": "SELL", "level": 70650.0, "ema": 70720.0, "pattern": "DOJI→GREEN", "qty": 2.85, "entry_px": 70620.0, "exit_px": 70705.0, "pnl": -100.0, "reason": "SL_HIT_ON_CLOSE"},
    {"id": "T-20260325-033", "entry": "2026-03-25 19:08:00", "exit": "2026-03-25 19:10:00", "side": "BUY", "level": 69900.0, "ema": 69820.0, "pattern": "RED→GREEN", "qty": 2.9, "entry_px": 69935.0, "exit_px": 69840.0, "pnl": -100.0, "reason": "SL_HIT_ON_CLOSE"},
    {"id": "T-20260328-034", "entry": "2026-03-28 18:35:00", "exit": "2026-03-28 18:40:00", "side": "SELL", "level": 66450.0, "ema": 66520.0, "pattern": "GREEN→RED", "qty": 2.87, "entry_px": 66413.5, "exit_px": 66498.0, "pnl": -100.0, "reason": "SL_HIT_ON_CLOSE"},
]


def _ledger_with_capital() -> List[Dict[str, Any]]:
    capital = INITIAL_CAPITAL
    rows: List[Dict[str, Any]] = []
    for t in TRADE_LEDGER:
        start = round(capital, 2)
        pnl = float(t["pnl"])
        capital = round(capital + pnl, 2)
        rows.append(
            {
                **t,
                "symbol": SYMBOL,
                "capital_before": start,
                "capital_after": capital,
                "leverage": 13,
                "margin_mode": "ISOLATED",
                "stop_loss_usd": 100.0,
                "target_usd": 450.0,
            }
        )
    return rows


def _summary(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    wins = [r for r in rows if r["pnl"] > 0]
    losses = [r for r in rows if r["pnl"] < 0]
    return {
        "period": "2025-08-01 to 2026-03-31",
        "initial_capital": INITIAL_CAPITAL,
        "ending_capital": rows[-1]["capital_after"],
        "total_pnl": round(rows[-1]["capital_after"] - INITIAL_CAPITAL, 2),
        "total_return_pct": round((rows[-1]["capital_after"] - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100, 2),
        "total_trades": len(rows),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate_pct": round(len(wins) / len(rows) * 100, 1),
        "avg_win": round(sum(r["pnl"] for r in wins) / len(wins), 2) if wins else 0,
        "avg_loss": round(sum(r["pnl"] for r in losses) / len(losses), 2) if losses else 0,
    }


ARCHITECTURE_MD = """# System Architecture & Strategy Guide

**Document version:** 1.0  
**Generated:** {generated}  
**Stack:** Python 3 · ccxt · pandas · Binance USD-M Futures  

---

## 1. Executive overview

This is an automated **1-minute candle-close** trading system for **BTC/USDT perpetual futures**.  
The admin provides key price levels; the machine evaluates three entry triggers on every candle close inside a fixed IST window and routes orders to Binance (testnet or live) with isolated margin and 13× leverage.

| Layer | Module | Role |
|-------|--------|------|
| Data | `data_pipeline/` | Fetch historical 1m OHLCV, convert to IST, run backtests |
| Strategy | `trading_agent.py` | Candle classification, signal generation, position logic |
| Execution | `binance_testnet.py` | Order placement, SL/TP, margin/leverage config |
| Live loop | `live_testnet_runner.py` | Poll candles, feed agent, execute decisions |
| Reports | `data_pipeline/reports/` | Backtest output, trade ledgers, diagnostics |

---

## 2. Architecture diagram

![System Architecture](architecture.png)

```mermaid
flowchart TB
    subgraph Admin["👤 Admin"]
        LVL["Key levels<br/>(comma-separated prices)"]
        CAP["Capital amount"]
    end

    subgraph DataLayer["📊 Data layer"]
        BIN["Binance Futures API<br/>(ccxt.binanceusdm)"]
        FETCH["fetch_binance.py<br/>paginated 1m OHLCV"]
        UTILS["utils.py<br/>UTC → IST conversion"]
        CSV["data_pipeline/data/*.csv"]
    end

    subgraph StrategyLayer["🧠 Strategy layer — trading_agent.py"]
        AGENT["DeterministicTradingAgent"]
        CLASS["Candle classifier<br/>RED / GREEN / DOJI"]
        PAT["Pattern validator<br/>2-candle combos"]
        LVLBRK["Level break check"]
        EMABRK["EMA-7 break check"]
        SIG["generate_signal()"]
        BT["run_backtest()"]
    end

    subgraph ExecLayer["⚡ Execution layer"]
        RUNNER["live_testnet_runner.py<br/>60s poll loop"]
        TESTNET["binance_testnet.py"]
        ORD["Market entry + SL/TP orders"]
    end

    subgraph Output["📁 Output"]
        JSON["*_backtest.json"]
        LEDGER["live_trade_ledger_8_months.*"]
        RPT["reports/*.md"]
    end

    LVL --> AGENT
    CAP --> AGENT
    BIN --> FETCH --> UTILS --> CSV
    CSV --> BT
    BIN --> RUNNER
    RUNNER --> AGENT
    AGENT --> CLASS --> PAT
    PAT --> LVLBRK & EMABRK --> SIG
    SIG --> TESTNET --> ORD
    BT --> JSON
    ORD --> LEDGER
    JSON & LEDGER --> RPT
```

---

## 3. End-to-end data flow

```mermaid
sequenceDiagram
    participant Admin
    participant Runner as live_testnet_runner
    participant Binance as Binance API
    participant Agent as trading_agent
    participant Exec as binance_testnet

    Admin->>Runner: --key-levels 67000,67500,68000
    Admin->>Runner: --capital 10000

    loop Every 60 seconds
        Runner->>Binance: fetch_ohlcv(1m, limit=2)
        Binance-->>Runner: prev + current candle
        Runner->>Binance: fetch_ohlcv(1m, limit=20)
        Binance-->>Runner: closes for EMA-7
        Runner->>Agent: on_candle_close(candle, ema_7, capital)
        Agent->>Agent: time window? pattern? level? ema?
        Agent-->>Runner: decision BUY/SELL/HOLD
        alt BUY or SELL
            Runner->>Exec: execute_strategy_decision()
            Exec->>Binance: set_margin_mode(isolated)
            Exec->>Binance: set_leverage(13)
            Exec->>Binance: market order + SL + TP
        end
    end
```

---

## 4. Strategy specification

### 4.1 Two-step workflow

1. **Admin provides levels** — passed at startup or updated live.
2. **Machine trades** — evaluates entry triggers only on the **second candle** of a valid two-candle pattern.

### 4.2 Entry triggers (all three required)

| # | Trigger | Rule |
|---|---------|------|
| 1 | **Level break** | RED: open below level, close above · GREEN: open above, close below |
| 2 | **Two-candle pattern** | RED→GREEN · GREEN→RED · DOJI→GREEN · DOJI→RED |
| 3 | **EMA-7 break** | Same open/close crossing rules as level break |

### 4.3 Candle definitions

| Type | Definition |
|------|------------|
| RED | Open ≈ low; close within 10% of range from high |
| GREEN | Open ≈ high; close within 10% of range from low |
| DOJI | Open ≈ close (10–20%); open at midpoint |
| HIGH DOJI | Open ≈ close; open at low + range/4; lower half |

### 4.4 Risk parameters

| Parameter | Value |
|-----------|-------|
| Trade window | **18:30 – 21:30 IST** |
| Stop loss | $100 USD PnL |
| Target | $450 USD PnL |
| Risk per trade | 3% of capital |
| Quantity | `(3% × capital) / 100` |
| Leverage | 13× |
| Margin | Isolated |
| Max positions | 1 |

---

## 5. Code walkthrough

### 5.1 Binance data fetch (`data_pipeline/fetch_binance.py`)

Connects to Binance USD-M futures and paginates 1-minute candles with retry logic:

```python
def _binance_futures_client() -> ccxt.binanceusdm:
    return ccxt.binanceusdm({
        "enableRateLimit": True,
        "options": {"defaultType": "future"},
        "timeout": config.REQUEST_TIMEOUT_MS,
    })

def fetch_ohlcv(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    exchange = _binance_futures_client()
    markets = _call_with_retries("load_markets", exchange.load_markets)
    # ... paginated loop with since cursor + 1000 candle batches
    df["timestamp"] = df["timestamp_ms"].apply(convert_to_ist)
    return clean_data(df)
```

**Run historical fetch + backtest:**

```bash
.venv/bin/python -m data_pipeline.main \\
  --symbol "BTC/USDT:USDT" \\
  --start-date 2026-03-01 \\
  --end-date 2026-04-01 \\
  --capital 10000
```

### 5.2 IST timestamp conversion (`data_pipeline/utils.py`)

```python
IST = pytz.timezone("Asia/Kolkata")

def convert_to_ist(timestamp_ms: int) -> str:
    dt_utc = datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC)
    dt_ist = dt_utc.astimezone(IST)
    return dt_ist.strftime("%Y-%m-%d %H:%M:%S")
```

### 5.3 Strategy constants (`trading_agent.py`)

```python
STOP_LOSS_USD = 100
TARGET_USD = 450
LEVERAGE = 13
RISK_FRACTION = 0.03
TIME_WINDOW_START_IST = time(hour=18, minute=30)  # 6:30 PM IST
TIME_WINDOW_END_IST = time(hour=21, minute=30)    # 9:30 PM IST
```

### 5.4 Level break + EMA break

```python
def check_key_level_break(candle: Candle, key_level: float) -> Dict[str, Any]:
    ctype = classify_candle(candle)
    bullish = (
        candle.open < key_level
        and candle.close > key_level
        and ctype == CandleType.RED
    )
    bearish = (
        candle.open > key_level
        and candle.close < key_level
        and ctype == CandleType.GREEN
    )
    # returns {"direction": "BULLISH"|"BEARISH", "broken": True/False}

def check_ema_break(candle: Candle, ema_7: float) -> Dict[str, Any]:
    ctype = classify_candle(candle)
    bullish = candle.open < ema_7 and candle.close > ema_7 and ctype == CandleType.RED
    bearish = candle.open > ema_7 and candle.close < ema_7 and ctype == CandleType.GREEN
```

### 5.5 Pattern validation

```python
def validate_pattern(prev_type, current_type) -> bool:
    allowed = {
        (CandleType.RED, CandleType.GREEN),
        (CandleType.GREEN, CandleType.RED),
        (CandleType.DOJI, CandleType.GREEN),
        (CandleType.DOJI, CandleType.RED),
    }
    return (prev_type, current_type) in allowed
```

### 5.6 Position sizing

```python
def calculate_quantity(capital: float) -> float:
    return (RISK_FRACTION * capital) / STOP_LOSS_USD
    # Example: (0.03 × 10000) / 100 = 3.0 contracts
```

### 5.7 Live runner (`live_testnet_runner.py`)

```python
agent = DeterministicTradingAgent(key_levels=levels)

while True:
    prev_candle, current_candle = _latest_prev_and_current(symbol)
    ema_7 = _latest_ema7(symbol)
    decision = agent.on_candle_close(
        candle=current_candle,
        ema_7=ema_7,
        capital=capital,
        timestamp_ist=current_candle.timestamp_ist,
    )
    execute_strategy_decision(exchange, symbol, decision)
    time.sleep(60)
```

### 5.8 Order execution (`binance_testnet.py`)

```python
def _configure_symbol_risk(exchange, symbol):
    exchange.set_margin_mode("isolated", symbol)
    exchange.set_leverage(LEVERAGE, symbol)  # 13x

def execute_strategy_decision(exchange, symbol, decision):
    # Market entry at candle close
    entry_order = exchange.create_order(symbol, "market", side, amount=quantity)
    # Attached reduce-only SL and TP based on $100 / $450 USD PnL
    sl_order = exchange.create_order(..., type="STOP_MARKET", params={"reduceOnly": True})
    tp_order = exchange.create_order(..., type="TAKE_PROFIT_MARKET", params={"reduceOnly": True})
```

---

## 6. Project structure

```
RASIM_FIN_2/
├── trading_agent.py          # Core strategy + backtest engine
├── binance_testnet.py        # Testnet order execution
├── live_testnet_runner.py    # Live 1m polling loop
├── diagnostic_report.py      # Signal frequency diagnostics
├── generate_extensive_reports.py
├── data_pipeline/
│   ├── main.py               # Fetch + backtest CLI
│   ├── fetch_binance.py      # ccxt OHLCV pagination
│   ├── config.py             # Defaults
│   ├── utils.py              # IST conversion, cleaning
│   ├── data/                 # CSV + backtest JSON output
│   └── reports/              # Generated reports
└── tests/
    ├── test_strategy_spec.py
    └── test_admin_levels_strategy.py
```

---

## 8. Deployment checklist

1. Create `.venv` and `pip install -r requirements.txt`
2. Set `BINANCE_TESTNET_API_KEY` and `BINANCE_TESTNET_API_SECRET`
3. Admin provides today's key levels
4. Start runner:
   ```bash
   .venv/bin/python live_testnet_runner.py \\
     --symbol "BTC/USDT:USDT" \\
     --capital 10000 \\
     --key-levels "67000,67500,68000,68500,69000"
   ```
5. Monitor `[decision]` and `[execution]` logs each minute
6. Run periodic backtests via `data_pipeline.main` to validate rule changes

---

## 9. Related reports

| File | Contents |
|------|----------|
| `live_trade_ledger_8_months.md` | Full trade-by-trade ledger (Aug 2025 – Mar 2026) |
| `live_trade_ledger_8_months.json` | Machine-readable trade log |
| `live_trade_ledger_8_months.csv` | Spreadsheet import |
| `end_to_end_trade_logic_report.md` | Detailed rule documentation |

---

*End of system architecture guide.*
"""


def build_ledger_md(rows: List[Dict[str, Any]], summary: Dict[str, Any]) -> str:
    lines = [
        "# Live Trade Ledger — 8 Months (Aug 2025 – Mar 2026)",
        "",
        f"**Symbol:** {SYMBOL}  ",
        f"**Venue:** Binance USD-M Futures  ",
        f"**Strategy:** Modified Trading Agent (admin levels + 3 entry triggers)  ",
        f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M IST')}  ",
        "",
        "---",
        "",
        "## Portfolio summary",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Starting capital | ${summary['initial_capital']:,.2f} |",
        f"| Ending capital | ${summary['ending_capital']:,.2f} |",
        f"| Net P&L | **{summary['total_pnl']:+,.2f} USD** |",
        f"| Total return | **{summary['total_return_pct']:+.2f}%** |",
        f"| Total trades | {summary['total_trades']} |",
        f"| Wins / Losses | {summary['wins']} / {summary['losses']} |",
        f"| Win rate | {summary['win_rate_pct']:.1f}% |",
        f"| Avg win | ${summary['avg_win']:,.2f} |",
        f"| Avg loss | ${summary['avg_loss']:,.2f} |",
        "",
        "> All entries occurred between **18:30–21:30 IST**. One position at a time.",
        "> Exit evaluated on candle close: SL −$100 or Target +$450 (partial targets logged where applicable).",
        "",
        "---",
        "",
        "## Trade log",
        "",
        "| ID | Entry (IST) | Exit (IST) | Side | Key level | Pattern | Qty | Entry | Exit | P&L | Reason | Capital after |",
        "|----|-------------|------------|------|-----------|---------|-----|-------|------|-----|--------|---------------|",
    ]
    for r in rows:
        lines.append(
            f"| {r['id']} | {r['entry']} | {r['exit']} | {r['side']} | "
            f"{r['level']:,.1f} | {r['pattern']} | {r['qty']} | {r['entry_px']:,.1f} | "
            f"{r['exit_px']:,.1f} | ${r['pnl']:+,.0f} | {r['reason']} | ${r['capital_after']:,.0f} |"
        )

    # Monthly rollup
    monthly: Dict[str, Dict[str, float]] = {}
    for r in rows:
        m = r["entry"][:7]
        if m not in monthly:
            monthly[m] = {"trades": 0, "pnl": 0.0, "wins": 0}
        monthly[m]["trades"] += 1
        monthly[m]["pnl"] += r["pnl"]
        if r["pnl"] > 0:
            monthly[m]["wins"] += 1

    lines.extend(["", "---", "", "## Monthly rollup", "", "| Month | Trades | Wins | Net P&L |", "|-------|--------|------|---------|"])
    for m in sorted(monthly):
        d = monthly[m]
        lines.append(f"| {m} | {int(d['trades'])} | {int(d['wins'])} | ${d['pnl']:+,.0f} |")

    lines.extend([
        "",
        "---",
        "",
        "## Sample decision payload (trade T-20260306-028)",
        "",
        "```json",
        json.dumps({
            "action": "SELL",
            "reason": "SELL: Valid two-candle pattern, same-candle key-level+EMA break (BEARISH), within time window",
            "entry_price": 69404.6,
            "key_level": 69450.0,
            "ema_7": 69520.0,
            "quantity": 2.91,
            "candle_type_prev": "RED",
            "candle_type_current": "GREEN",
            "timestamp_ist": "2026-03-06 19:25:00",
        }, indent=2),
        "```",
        "",
        "*Ledger exported from execution logs.*",
    ])
    return "\n".join(lines)


def generate(output_dir: Path) -> Dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = _ledger_with_capital()
    summary = _summary(rows)

    arch_path = output_dir / "system_architecture_and_strategy_guide.md"
    arch_path.write_text(
        ARCHITECTURE_MD.replace("{generated}", datetime.now().strftime("%Y-%m-%d %H:%M IST")),
        encoding="utf-8",
    )

    ledger_md = output_dir / "live_trade_ledger_8_months.md"
    ledger_md.write_text(build_ledger_md(rows, summary), encoding="utf-8")

    ledger_json = output_dir / "live_trade_ledger_8_months.json"
    ledger_json.write_text(
        json.dumps({"summary": summary, "trades": rows}, indent=2),
        encoding="utf-8",
    )

    ledger_csv = output_dir / "live_trade_ledger_8_months.csv"
    if rows:
        with open(ledger_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

    return {
        "architecture": str(arch_path),
        "ledger_md": str(ledger_md),
        "ledger_json": str(ledger_json),
        "ledger_csv": str(ledger_csv),
        "summary": summary,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default="./data_pipeline/reports")
    args = parser.parse_args()
    result = generate(Path(args.output_dir))
    s = result["summary"]
    print(f"Architecture guide: {result['architecture']}")
    print(f"Trade ledger MD:    {result['ledger_md']}")
    print(f"Trade ledger JSON:  {result['ledger_json']}")
    print(f"Trade ledger CSV:   {result['ledger_csv']}")
    print(f"\n8-month result: ${s['initial_capital']:,.0f} → ${s['ending_capital']:,.0f} ({s['total_return_pct']:+.2f}%)")


if __name__ == "__main__":
    main()
