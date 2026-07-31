from __future__ import annotations

import os
import sys

import pandas as pd
import streamlit as st

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from dashboard.trade_log import load_trade_log

st.set_page_config(page_title="RASIM Trade Log", layout="wide")
st.title("RASIM Trading Strategy — Historical Trade Log")
st.caption(
    "Trades recorded by live_testnet_runner.py (persisted to data_pipeline/data/live_trade_log.json). "
    "This is separate from backtest history, shown on the Backtest Analytics page."
)

rows = load_trade_log()
if not rows:
    st.info("No live trades recorded yet. Run live_testnet_runner.py to start populating this log.")
    st.stop()

df = pd.DataFrame(rows)
df["entry_dt"] = pd.to_datetime(df["entry_time"])

st.sidebar.subheader("Filters")
min_date, max_date = df["entry_dt"].min().date(), df["entry_dt"].max().date()
date_range = st.sidebar.date_input("Date range", value=(min_date, max_date), min_value=min_date, max_value=max_date)
month_options = sorted(df["entry_dt"].dt.strftime("%Y-%m").unique(), reverse=True)
month_filter = st.sidebar.multiselect("Month", month_options, default=month_options)
direction_filter = st.sidebar.multiselect("Direction", ["BUY", "SELL"], default=["BUY", "SELL"])
outcome_filter = st.sidebar.radio("Outcome", ["All", "Winning trades", "Losing trades"], index=0)

filtered = df.copy()
if isinstance(date_range, tuple) and len(date_range) == 2:
    start, end = date_range
    filtered = filtered[(filtered["entry_dt"].dt.date >= start) & (filtered["entry_dt"].dt.date <= end)]
filtered = filtered[filtered["entry_dt"].dt.strftime("%Y-%m").isin(month_filter)]
filtered = filtered[filtered["side"].isin(direction_filter)]
if outcome_filter == "Winning trades":
    filtered = filtered[filtered["pnl_usd"] > 0]
elif outcome_filter == "Losing trades":
    filtered = filtered[filtered["pnl_usd"] < 0]

c1, c2, c3, c4 = st.columns(4)
c1.metric("Trades (filtered)", len(filtered))
closed = filtered[filtered["pnl_usd"].notna()]
c2.metric("Wins", int((closed["pnl_usd"] > 0).sum()))
c3.metric("Losses", int((closed["pnl_usd"] < 0).sum()))
c4.metric("Net PnL (filtered)", f"${closed['pnl_usd'].sum():,.2f}")

display_cols = [
    "trade_number", "date", "entry_time", "exit_time", "side", "entry_price",
    "stop_loss_price", "target_price", "exit_price", "pnl_usd", "pnl_pct",
    "exit_reason", "status",
]
st.dataframe(filtered[display_cols].sort_values("trade_number", ascending=False), width="stretch", hide_index=True)

st.download_button(
    "Download trade log (CSV)",
    data=filtered[display_cols].to_csv(index=False),
    file_name="live_trade_log.csv",
    mime="text/csv",
)
