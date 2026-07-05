from __future__ import annotations

import time
from typing import List

import ccxt
import pandas as pd

from data_pipeline import config
from data_pipeline.utils import clean_data, convert_to_ist, date_to_milliseconds


def _binance_futures_client() -> ccxt.binanceusdm:
    return ccxt.binanceusdm(
        {
            "enableRateLimit": True,
            "options": {"defaultType": "future"},
            "timeout": config.REQUEST_TIMEOUT_MS,
        }
    )


def _call_with_retries(callable_name: str, func):
    for attempt in range(1, config.MAX_RETRIES + 1):
        try:
            return func()
        except Exception as exc:  # noqa: BLE001
            if attempt >= config.MAX_RETRIES:
                raise RuntimeError(f"{callable_name} failed after retries: {exc}") from exc
            sleep_for = config.RETRY_BACKOFF_SECONDS * attempt
            print(
                f"[retry] callable={callable_name} attempt={attempt} error={exc} "
                f"sleeping={sleep_for:.1f}s"
            )
            time.sleep(sleep_for)


def fetch_ohlcv(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    """
    Fetch paginated 1m OHLCV from Binance Futures for [start_date, end_date).
    """
    exchange = _binance_futures_client()
    markets = _call_with_retries("load_markets", exchange.load_markets)
    if symbol not in markets:
        raise ValueError(f"Symbol not found on Binance Futures: {symbol}")

    start_ms = date_to_milliseconds(start_date)
    end_ms = date_to_milliseconds(end_date)
    if end_ms <= start_ms:
        raise ValueError("END_DATE must be greater than START_DATE")

    timeframe_ms = exchange.parse_timeframe(config.TIMEFRAME) * 1000
    all_rows: List[list] = []
    since = start_ms
    batch_no = 0

    while since < end_ms:
        batch_no += 1
        print(f"[fetch] {symbol} batch={batch_no} since={since}")
        rows = _call_with_retries(
            "fetch_ohlcv",
            lambda: exchange.fetch_ohlcv(
                    symbol=symbol,
                    timeframe=config.TIMEFRAME,
                    since=since,
                    limit=config.BINANCE_LIMIT,
            ),
        )

        if not rows:
            print(f"[fetch] Empty response for {symbol} at since={since}. Stopping.")
            break

        # Keep only rows strictly before end timestamp.
        filtered = [r for r in rows if int(r[0]) < end_ms]
        if not filtered:
            break

        all_rows.extend(filtered)
        last_ts = int(filtered[-1][0])
        next_since = last_ts + timeframe_ms
        if next_since <= since:
            # safety guard against non-advancing cursor
            next_since = since + timeframe_ms
        since = next_since
        time.sleep(config.REQUEST_SLEEP_SECONDS)

    if not all_rows:
        return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

    df = pd.DataFrame(
        all_rows, columns=["timestamp_ms", "open", "high", "low", "close", "volume"]
    )
    df["timestamp"] = df["timestamp_ms"].astype("int64").apply(convert_to_ist)
    df = df[["timestamp", "open", "high", "low", "close", "volume"]]
    return clean_data(df)