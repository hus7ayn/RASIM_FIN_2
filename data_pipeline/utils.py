from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Iterable

import pandas as pd
import pytz


UTC = pytz.utc
IST = pytz.timezone("Asia/Kolkata")


def convert_to_ist(timestamp_ms: int) -> str:
    """Convert a UTC epoch-millisecond timestamp to IST string."""
    dt_utc = datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC)
    dt_ist = dt_utc.astimezone(IST)
    return dt_ist.strftime("%Y-%m-%d %H:%M:%S")


def date_to_milliseconds(date_str: str) -> int:
    """Convert YYYY-MM-DD (UTC midnight) to epoch milliseconds."""
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    dt_utc = UTC.localize(dt)
    return int(dt_utc.timestamp() * 1000)


def ensure_output_dir(path: str) -> Path:
    out = Path(path)
    out.mkdir(parents=True, exist_ok=True)
    return out


def normalize_symbol_for_filename(symbol: str) -> str:
    return symbol.replace("/", "").replace(":", "").upper()


def clean_data(df: pd.DataFrame) -> pd.DataFrame:
    """Clean OHLCV dataframe for deterministic backtest consumption."""
    if df.empty:
        return df

    expected_cols = ["timestamp", "open", "high", "low", "close", "volume"]
    for col in expected_cols:
        if col not in df.columns:
            raise ValueError(f"Missing required column: {col}")

    cleaned = df.copy()
    cleaned = cleaned.drop_duplicates(subset=["timestamp"], keep="first")
    cleaned = cleaned.sort_values("timestamp", ascending=True)
    cleaned = cleaned.dropna(subset=expected_cols)

    for col in ["open", "high", "low", "close", "volume"]:
        cleaned[col] = pd.to_numeric(cleaned[col], errors="coerce")
    cleaned = cleaned.dropna(subset=["open", "high", "low", "close", "volume"])

    cleaned = cleaned.reset_index(drop=True)
    return cleaned


def parse_symbols(symbol_input: str | Iterable[str]) -> list[str]:
    if isinstance(symbol_input, str):
        if "," in symbol_input:
            return [s.strip() for s in symbol_input.split(",") if s.strip()]
        return [symbol_input.strip()]
    return [s.strip() for s in symbol_input if s.strip()]
