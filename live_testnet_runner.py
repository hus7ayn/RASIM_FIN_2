from __future__ import annotations

import argparse
import os
import time
from typing import Optional

import ccxt

from binance_testnet import build_testnet_exchange, execute_strategy_decision
from dashboard.trade_log import append_close_trade, append_open_trade
from strategies import get_strategy, list_strategies
from trading_agent import Action, Candle, _evaluate_exit_intrabar


def _build_market_data_exchange() -> ccxt.binanceusdm:
    # Public market data stream for candles/price.
    return ccxt.binanceusdm(
        {
            "enableRateLimit": True,
            "options": {"defaultType": "future"},
            "timeout": 30000,
            "urls": {
                "api": {
                    "fapiPublic": "https://demo-fapi.binance.com/fapi/v1",
                }
            },
        }
    )


def _to_candle(row: list) -> Candle:
    ts_ms = int(row[0])
    ts_ist = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(ts_ms / 1000 + 19800))
    return Candle(
        open=float(row[1]),
        high=float(row[2]),
        low=float(row[3]),
        close=float(row[4]),
        timestamp_ist=ts_ist,
    )


def _latest_prev_and_current(symbol: str) -> tuple[Optional[Candle], Optional[Candle]]:
    mdx = _build_market_data_exchange()
    rows = mdx.fetch_ohlcv(symbol=symbol, timeframe="3m", limit=2)
    if len(rows) < 2:
        return None, None
    return _to_candle(rows[-2]), _to_candle(rows[-1])


def _latest_ema7(symbol: str) -> Optional[float]:
    mdx = _build_market_data_exchange()
    rows = mdx.fetch_ohlcv(symbol=symbol, timeframe="3m", limit=20)
    if len(rows) < 7:
        return None
    closes = [float(r[4]) for r in rows]
    ema = closes[0]
    alpha = 2.0 / (7 + 1)
    for c in closes[1:]:
        ema = (c * alpha) + (ema * (1 - alpha))
    return ema


def main() -> None:
    parser = argparse.ArgumentParser(description="Live 1m strategy-to-testnet runner")
    parser.add_argument("--symbol", default="BTC/USDT:USDT")
    parser.add_argument("--capital", type=float, default=10000.0)
    parser.add_argument("--key-levels", required=True, help="Comma-separated levels")
    parser.add_argument("--loop-seconds", type=int, default=180)
    parser.add_argument(
        "--strategy",
        default="admin_levels_reversal",
        choices=list_strategies(),
        help="Registered strategy name from strategies/.",
    )
    args = parser.parse_args()

    api_key = os.getenv("BINANCE_TESTNET_API_KEY", "").strip()
    api_secret = os.getenv("BINANCE_TESTNET_API_SECRET", "").strip()
    if not api_key or not api_secret:
        raise RuntimeError("Set BINANCE_TESTNET_API_KEY and BINANCE_TESTNET_API_SECRET")

    testnet_exchange = build_testnet_exchange(api_key=api_key, api_secret=api_secret)
    levels = [float(x.strip()) for x in args.key_levels.split(",") if x.strip()]
    agent = get_strategy(args.strategy, key_levels=levels)

    print(f"[runner] Started symbol={args.symbol} strategy={args.strategy} levels={levels} loop={args.loop_seconds}s")
    while True:
        try:
            prev_candle, current_candle = _latest_prev_and_current(args.symbol)
            ema_7 = _latest_ema7(args.symbol)
            if prev_candle is None or current_candle is None:
                print("[runner] Not enough candles yet.")
                time.sleep(args.loop_seconds)
                continue

            agent.state.previous_candle = prev_candle
            capital_at_entry = args.capital
            decision = agent.on_candle_close(
                candle=current_candle,
                ema_7=ema_7,
                capital=capital_at_entry,
                timestamp_ist=current_candle.timestamp_ist,
            )
            print("[decision]", decision)

            if decision["action"] in (Action.BUY.value, Action.SELL.value):
                trade_number = append_open_trade(decision)
                print(f"[trade-log] Opened trade #{trade_number}")

            should_exit, pnl_usd, exit_reason, exit_price = _evaluate_exit_intrabar(
                agent.state.current_open_position, current_candle
            )
            if should_exit and pnl_usd is not None and exit_reason is not None:
                append_close_trade(
                    pnl_usd=pnl_usd,
                    exit_price=exit_price if exit_price is not None else current_candle.close,
                    exit_reason=exit_reason,
                    timestamp_ist=current_candle.timestamp_ist,
                    capital_at_entry=capital_at_entry,
                )
                agent.close_position()
                print(f"[trade-log] Closed trade: reason={exit_reason} pnl_usd={pnl_usd:.2f}")

            result = execute_strategy_decision(
                exchange=testnet_exchange,
                symbol=args.symbol,
                decision=decision,
                validate_only=True,
            )
            print("[execution]", result)
        except Exception as exc:  # noqa: BLE001
            print(f"[runner-error] {exc}")
        time.sleep(args.loop_seconds)


if __name__ == "__main__":
    main()
