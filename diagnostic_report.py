from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional

import pandas as pd

from trading_agent import (
    Candle,
    check_ema_break,
    check_key_level_break,
    classify_candle,
    validate_pattern,
    within_time_window,
)


@dataclass
class DiagnosticSummary:
    total_rows: int
    evaluated_rows_with_prev: int
    time_allowed: int
    pattern_valid: int
    ema_break: int
    key_level_aligned_with_ema: int
    final_buy_or_sell_candidates: int
    final_buy_candidates: int
    final_sell_candidates: int
    candle_type_distribution: Dict[str, int]


def _row_to_candle(row: pd.Series) -> Candle:
    return Candle(
        open=float(row["open"]),
        high=float(row["high"]),
        low=float(row["low"]),
        close=float(row["close"]),
        timestamp_ist=str(row["timestamp"]),
    )


def _load_market_csv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    required = {"timestamp", "open", "high", "low", "close", "volume"}
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(f"CSV missing required columns: {sorted(missing)}")
    df = df.sort_values("timestamp", ascending=True).reset_index(drop=True)
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["timestamp", "open", "high", "low", "close", "volume"])
    return df


def _ema7(series: pd.Series) -> pd.Series:
    return series.ewm(span=7, adjust=False).mean()


def generate_diagnostic_report(csv_path: str, key_levels: List[float]) -> Dict[str, Any]:
    df = _load_market_csv(csv_path)
    if df.empty:
        return {"error": "No rows in CSV after cleaning."}

    df["ema_7"] = _ema7(df["close"])

    total_rows = len(df)
    evaluated_rows_with_prev = max(total_rows - 1, 0)
    time_allowed = 0
    pattern_valid = 0
    ema_break = 0
    key_level_aligned_with_ema = 0
    final_buy_or_sell_candidates = 0
    final_buy_candidates = 0
    final_sell_candidates = 0
    ctype_counter: Counter[str] = Counter()

    for i in range(1, total_rows):
        prev = _row_to_candle(df.iloc[i - 1])
        curr = _row_to_candle(df.iloc[i])
        ema_7 = float(df.iloc[i]["ema_7"])

        prev_type = classify_candle(prev)
        curr_type = classify_candle(curr)
        if prev_type is not None:
            ctype_counter[prev_type.value] += 1
        if curr_type is not None:
            ctype_counter[curr_type.value] += 1

        if not within_time_window(curr.timestamp_ist):
            continue
        time_allowed += 1

        if not validate_pattern(prev_type, curr_type):
            continue
        pattern_valid += 1

        ema_info = check_ema_break(curr, ema_7)
        if not bool(ema_info["broken"]):
            continue
        ema_break += 1

        matched_direction: Optional[str] = None
        for level in key_levels:
            kinfo = check_key_level_break(curr, float(level))
            if bool(kinfo["broken"]) and kinfo["direction"] == ema_info["direction"]:
                matched_direction = str(kinfo["direction"])
                break
        if matched_direction is None:
            continue
        key_level_aligned_with_ema += 1

        final_buy_or_sell_candidates += 1
        if matched_direction == "BULLISH":
            final_buy_candidates += 1
        elif matched_direction == "BEARISH":
            final_sell_candidates += 1

    summary = DiagnosticSummary(
        total_rows=total_rows,
        evaluated_rows_with_prev=evaluated_rows_with_prev,
        time_allowed=time_allowed,
        pattern_valid=pattern_valid,
        ema_break=ema_break,
        key_level_aligned_with_ema=key_level_aligned_with_ema,
        final_buy_or_sell_candidates=final_buy_or_sell_candidates,
        final_buy_candidates=final_buy_candidates,
        final_sell_candidates=final_sell_candidates,
        candle_type_distribution=dict(ctype_counter),
    )
    return asdict(summary)


def main() -> None:
    parser = argparse.ArgumentParser(description="Strategy diagnostic frequency report")
    parser.add_argument("--csv", required=True, help="Path to fetched market data CSV")
    parser.add_argument(
        "--key-levels",
        required=True,
        help="Comma-separated key levels, e.g. 43000,43500,44000",
    )
    parser.add_argument("--output-json", default="", help="Optional output JSON path")
    args = parser.parse_args()

    levels = [float(x.strip()) for x in args.key_levels.split(",") if x.strip()]
    report = generate_diagnostic_report(args.csv, levels)
    print(json.dumps(report, indent=2))
    if args.output_json:
        with open(args.output_json, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)


if __name__ == "__main__":
    main()
