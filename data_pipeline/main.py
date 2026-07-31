from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

from data_pipeline import config
from data_pipeline.fetch_binance import fetch_ohlcv
from data_pipeline.utils import ensure_output_dir, normalize_symbol_for_filename, parse_symbols
from strategies import get_strategy, list_strategies
from trading_agent import Candle, run_backtest


def _build_output_filename(symbol: str, start_date: str, end_date: str) -> str:
    normalized = normalize_symbol_for_filename(symbol)
    return f"{normalized}_1m_{start_date}_{end_date}.csv"


def _save_market_csv(df: pd.DataFrame, path: Path) -> None:
    # exact requested market data format
    df.to_csv(path, index=False, columns=["timestamp", "open", "high", "low", "close", "volume"])


def _prepare_backtest_inputs(df: pd.DataFrame) -> tuple[List[Candle], List[float]]:
    backtest_df = df.copy()
    backtest_df["ema_7"] = backtest_df["close"].ewm(span=7, adjust=False).mean()
    candles = [
        Candle(
            open=float(row.open),
            high=float(row.high),
            low=float(row.low),
            close=float(row.close),
            timestamp_ist=str(row.timestamp),
        )
        for row in backtest_df.itertuples(index=False)
    ]
    ema_values = [float(v) for v in backtest_df["ema_7"].tolist()]
    return candles, ema_values


def _run_symbol_pipeline(
    symbol: str,
    start_date: str,
    end_date: str,
    output_dir: Path,
    capital: float,
    key_levels: List[float],
    strategy: str = "admin_levels_reversal",
) -> Dict[str, Any]:
    print(f"[start] symbol={symbol} start={start_date} end={end_date} strategy={strategy}")
    df = fetch_ohlcv(symbol=symbol, start_date=start_date, end_date=end_date)
    if df.empty:
        return {
            "symbol": symbol,
            "status": "empty",
            "candles": 0,
            "csv_path": None,
            "backtest_path": None,
        }

    market_csv_name = _build_output_filename(symbol, start_date, end_date)
    market_csv_path = output_dir / market_csv_name
    _save_market_csv(df, market_csv_path)

    candles, ema_values = _prepare_backtest_inputs(df)
    agent = get_strategy(strategy, key_levels=key_levels)
    backtest_result = run_backtest(
        candles=candles,
        ema_values=ema_values,
        key_levels=key_levels,
        initial_capital=capital,
        agent=agent,
    )

    bt_json_name = market_csv_name.replace(".csv", "_backtest.json")
    bt_json_path = output_dir / bt_json_name
    with open(bt_json_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "symbol": symbol,
                "strategy": strategy,
                "candles": len(df),
                "start_timestamp_ist": str(df["timestamp"].iloc[0]),
                "end_timestamp_ist": str(df["timestamp"].iloc[-1]),
                "total_trades": backtest_result.total_trades,
                "wins": backtest_result.wins,
                "losses": backtest_result.losses,
                "total_pnl_usd": backtest_result.total_pnl_usd,
                "ending_capital": backtest_result.ending_capital,
                "trades": [t.__dict__ for t in backtest_result.trades],
            },
            f,
            indent=2,
        )

    print(
        f"[done] {symbol} candles={len(df)} range={df['timestamp'].iloc[0]} -> {df['timestamp'].iloc[-1]} "
        f"csv={market_csv_path} backtest={bt_json_path}"
    )
    return {
        "symbol": symbol,
        "status": "ok",
        "candles": len(df),
        "csv_path": str(market_csv_path),
        "backtest_path": str(bt_json_path),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Binance 1m data pipeline + backtest runner")
    parser.add_argument("--symbol", default=config.SYMBOL, help="Single symbol or comma-separated symbols")
    parser.add_argument("--start-date", default=config.START_DATE, help="YYYY-MM-DD")
    parser.add_argument("--end-date", default=config.END_DATE, help="YYYY-MM-DD")
    parser.add_argument("--output-dir", default=config.OUTPUT_DIR, help="Output directory")
    parser.add_argument("--capital", type=float, default=config.BACKTEST_CAPITAL, help="Backtest capital")
    parser.add_argument(
        "--key-levels",
        default="",
        help="Comma-separated key levels for backtest, e.g. 23500,23600",
    )
    parser.add_argument(
        "--strategy",
        default="admin_levels_reversal",
        choices=list_strategies(),
        help="Registered strategy name from strategies/.",
    )
    args = parser.parse_args()

    key_levels = (
        [float(x.strip()) for x in args.key_levels.split(",") if x.strip()]
        if args.key_levels
        else list(config.BACKTEST_KEY_LEVELS)
    )

    output_dir = ensure_output_dir(args.output_dir)
    symbols = parse_symbols(args.symbol)
    summaries = []
    for symbol in symbols:
        summary = _run_symbol_pipeline(
            symbol=symbol,
            start_date=args.start_date,
            end_date=args.end_date,
            output_dir=output_dir,
            capital=args.capital,
            key_levels=key_levels,
            strategy=args.strategy,
        )
        summaries.append(summary)

    print("\n=== Pipeline Summary ===")
    for s in summaries:
        print(s)


if __name__ == "__main__":
    main()