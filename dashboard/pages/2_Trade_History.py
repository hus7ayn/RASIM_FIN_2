from __future__ import annotations

import os
import sys

import pandas as pd
import streamlit as st

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from dashboard.trade_log import OPEN_STATUSES, load_trade_log
from dashboard.ui import demo_badge

st.set_page_config(page_title="RASIM Trade History", layout="wide")
st.title("Trade History")
st.caption(
    "Every active and completed trade recorded by the live runner and by manual "
    "position actions. Backtest results live on the Backtest Analytics page."
)

rows = load_trade_log()
if not rows:
    st.info(
        "No live trades recorded yet. Run `live_testnet_runner.py`, or use the Live Monitor "
        "position controls, to start populating this log."
    )
    st.stop()

if any(r.get("synthetic") for r in rows):
    demo_badge()

df = pd.DataFrame(rows)
df["entry_dt"] = pd.to_datetime(df["entry_time"], errors="coerce")
df["exit_dt"] = pd.to_datetime(df["exit_time"], errors="coerce")
df["duration_min"] = (df["exit_dt"] - df["entry_dt"]).dt.total_seconds() / 60.0
df["is_open"] = df["status"].isin(OPEN_STATUSES)
df["partial_count"] = df["partial_exits"].apply(len)
df["tp_sl_edit_count"] = df["tp_sl_modifications"].apply(len)

# ------------------------------------------------------------------ filters
st.sidebar.subheader("Search & filter")
query = st.sidebar.text_input("Search", placeholder="symbol, side, reason, status…")

symbols = sorted(df["symbol"].dropna().unique().tolist())
symbol_filter = st.sidebar.multiselect("Symbol", symbols, default=symbols)

statuses = sorted(df["status"].dropna().unique().tolist())
status_filter = st.sidebar.multiselect("Status", statuses, default=statuses)

side_filter = st.sidebar.multiselect("Side", ["BUY", "SELL"], default=["BUY", "SELL"])

valid_dates = df["entry_dt"].dropna()
if not valid_dates.empty:
    min_d, max_d = valid_dates.min().date(), valid_dates.max().date()
    date_range = st.sidebar.date_input(
        "Entry date range", value=(min_d, max_d), min_value=min_d, max_value=max_d
    )
else:
    date_range = None

sort_field = st.sidebar.selectbox(
    "Sort by",
    ["trade_number", "entry_dt", "exit_dt", "pnl_usd", "duration_min", "symbol", "status"],
    index=0,
)
sort_desc = st.sidebar.toggle("Descending", value=True)

filtered = df.copy()
if symbol_filter:
    filtered = filtered[filtered["symbol"].isin(symbol_filter)]
if status_filter:
    filtered = filtered[filtered["status"].isin(status_filter)]
if side_filter:
    filtered = filtered[filtered["side"].isin(side_filter)]
if isinstance(date_range, tuple) and len(date_range) == 2:
    start, end = date_range
    mask = filtered["entry_dt"].dt.date.between(start, end)
    filtered = filtered[mask.fillna(False)]
if query.strip():
    q = query.strip().lower()
    searchable = ["symbol", "side", "status", "exit_reason"]
    hit = pd.Series(False, index=filtered.index)
    for col in searchable:
        hit |= filtered[col].astype(str).str.lower().str.contains(q, na=False)
    filtered = filtered[hit]

filtered = filtered.sort_values(sort_field, ascending=not sort_desc, na_position="last")

# ------------------------------------------------------------------ summary
closed = filtered[~filtered["is_open"]]
realized = pd.to_numeric(closed["pnl_usd"], errors="coerce").dropna()

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Trades shown", len(filtered))
c2.metric("Active", int(filtered["is_open"].sum()))
c3.metric("Closed", len(closed))
c4.metric("Realized P&L", f"${realized.sum():,.2f}" if not realized.empty else "—")
c5.metric(
    "Win rate",
    f"{(realized > 0).mean() * 100:.1f}%" if not realized.empty else "—",
)

# ------------------------------------------------------------------ table
DISPLAY_COLS = [
    "trade_number", "symbol", "side", "status",
    "entry_time", "exit_time", "entry_price", "exit_price",
    "original_quantity", "remaining_quantity",
    "stop_loss_price", "target_price",
    "pnl_usd", "pnl_pct", "duration_min",
    "partial_count", "tp_sl_edit_count", "exit_reason",
]

st.dataframe(
    filtered[DISPLAY_COLS],
    width="stretch",
    hide_index=True,
    column_config={
        "trade_number": st.column_config.NumberColumn("#", width="small"),
        "entry_price": st.column_config.NumberColumn("Entry", format="%.2f"),
        "exit_price": st.column_config.NumberColumn("Exit", format="%.2f"),
        "original_quantity": st.column_config.NumberColumn("Qty", format="%.5f"),
        "remaining_quantity": st.column_config.NumberColumn("Open qty", format="%.5f"),
        "stop_loss_price": st.column_config.NumberColumn("SL", format="%.2f"),
        "target_price": st.column_config.NumberColumn("TP", format="%.2f"),
        "pnl_usd": st.column_config.NumberColumn("P&L $", format="%.2f"),
        "pnl_pct": st.column_config.NumberColumn("P&L %", format="%.2f"),
        "duration_min": st.column_config.NumberColumn("Mins", format="%.1f"),
        "partial_count": st.column_config.NumberColumn("Partials", width="small"),
        "tp_sl_edit_count": st.column_config.NumberColumn("TP/SL edits", width="small"),
    },
)

st.download_button(
    "Export shown trades (CSV)",
    data=filtered[DISPLAY_COLS].to_csv(index=False),
    file_name="trade_history.csv",
    mime="text/csv",
)

# ------------------------------------------------------------------ detail
st.divider()
st.subheader("Trade detail")

if filtered.empty:
    st.info("No trades match the current filters.")
    st.stop()

numbers = filtered["trade_number"].tolist()
picked = st.selectbox(
    "Trade", numbers,
    format_func=lambda n: (
        f"#{n} — {df.loc[df['trade_number'] == n, 'side'].iloc[0]} "
        f"{df.loc[df['trade_number'] == n, 'symbol'].iloc[0]} "
        f"({df.loc[df['trade_number'] == n, 'status'].iloc[0]})"
    ),
)
trade = df.loc[df["trade_number"] == picked].iloc[0]

d1, d2, d3, d4 = st.columns(4)
d1.metric("Side", trade["side"])
d1.metric("Status", trade["status"])
d2.metric("Entry", f"{trade['entry_price']:,.2f}")
d2.metric("Exit", f"{trade['exit_price']:,.2f}" if pd.notna(trade["exit_price"]) else "—")
d3.metric("Stop loss", f"{trade['stop_loss_price']:,.2f}" if pd.notna(trade["stop_loss_price"]) else "—")
d3.metric("Target", f"{trade['target_price']:,.2f}" if pd.notna(trade["target_price"]) else "—")
d4.metric("Original qty", f"{trade['original_quantity']:.5f}")
d4.metric("Still open", f"{trade['remaining_quantity']:.5f}")

e1, e2, e3 = st.columns(3)
e1.metric("Realized P&L", f"${float(trade['realized_pnl_usd'] or 0):,.2f}")
e2.metric("Total P&L", f"${float(trade['pnl_usd']):,.2f}" if pd.notna(trade["pnl_usd"]) else "open")
e3.metric(
    "Duration",
    f"{trade['duration_min']:.1f} min" if pd.notna(trade["duration_min"]) else "running",
)

st.markdown("**Partial exits**")
if trade["partial_exits"]:
    pdf_ = pd.DataFrame(trade["partial_exits"])
    st.dataframe(
        pdf_, width="stretch", hide_index=True,
        column_config={
            "timestamp_ist": "Time (IST)",
            "quantity": st.column_config.NumberColumn("Qty booked", format="%.5f"),
            "exit_price": st.column_config.NumberColumn("Price", format="%.2f"),
            "pnl_usd": st.column_config.NumberColumn("Leg P&L $", format="%.2f"),
            "reason": "Reason",
        },
    )
else:
    st.caption("None — this position was never partially booked.")

st.markdown("**TP / SL modifications**")
if trade["tp_sl_modifications"]:
    mdf = pd.DataFrame(trade["tp_sl_modifications"])
    st.dataframe(
        mdf, width="stretch", hide_index=True,
        column_config={
            "timestamp_ist": "Time (IST)",
            "field": "Field",
            "old_value": st.column_config.NumberColumn("From", format="%.2f"),
            "new_value": st.column_config.NumberColumn("To", format="%.2f"),
        },
    )
else:
    st.caption("None — TP and SL were never changed after entry.")
