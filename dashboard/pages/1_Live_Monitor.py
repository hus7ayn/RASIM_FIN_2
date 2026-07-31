from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import pandas as pd
import streamlit as st

from dashboard.live import get_live_snapshot
from dashboard.trade_log import current_open_trade
from strategies import describe_strategy, list_strategies

st.set_page_config(page_title="RASIM Live Monitor", layout="wide")
st.title("RASIM Trading Strategy — Live Monitor")

st.caption(
    "Reads live public market data and replays it through the selected strategy from "
    "the strategies/ registry — the same engine used for backtesting and live execution."
)

available_strategies = list_strategies()
strategy_name = st.selectbox(
    "Strategy", available_strategies, index=0,
    format_func=lambda n: n,
)
st.caption(describe_strategy(strategy_name))

col_a, col_b, col_c = st.columns(3)
symbol = col_a.text_input("Symbol", value="BTC/USDT:USDT")
capital = col_b.number_input("Capital (USD)", value=10000.0, step=500.0)
manual_levels_raw = col_c.text_input(
    "Manual key levels (comma-separated, optional)",
    value="",
    help="Leave blank to use auto-projected admin levels.",
)
refresh_seconds = st.slider("Auto-refresh interval (seconds)", min_value=30, max_value=180, value=60, step=15)

key_levels = None
if manual_levels_raw.strip():
    try:
        key_levels = [float(x.strip()) for x in manual_levels_raw.split(",") if x.strip()]
    except ValueError:
        st.error("Manual key levels must be comma-separated numbers.")
        st.stop()


@st.fragment(run_every=f"{refresh_seconds}s")
def render_live_panel() -> None:
    now_ist = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=5, minutes=30)
    st.caption(f"Last refreshed (IST): {now_ist.strftime('%Y-%m-%d %H:%M:%S')}")

    try:
        snap = get_live_snapshot(symbol=symbol, key_levels=key_levels, capital=capital, strategy_name=strategy_name)
    except Exception as exc:  # noqa: BLE001
        st.error(f"Failed to fetch live data: {exc}")
        return

    if "error" in snap:
        st.warning(snap["error"])
        return

    st.subheader("Session Information")
    s1, s2, s3, s4 = st.columns(4)
    s1.metric("Trading Date (IST)", snap["last_candle_ts_ist"][:10])
    s1.metric("Last Candle (IST)", snap["last_candle_ts_ist"][11:])
    s2.metric("Session Status", snap["session_status"])
    s2.metric("Levels Finalized", "Yes" if snap["levels_finalized"] else "No")
    s3.metric("Session High", f"{snap['session_high']:,.2f}" if snap["session_high"] else "—")
    s3.metric("Session Low", f"{snap['session_low']:,.2f}" if snap["session_low"] else "—")
    s4.metric("Session Range", f"{snap['session_range']:,.2f}" if snap["session_range"] else "—")
    s4.metric("Used Unconfirmed Fallback", "Yes" if snap["used_unconfirmed_fallback"] else "No")

    st.subheader("Fibonacci Levels")
    f1, f2, f3 = st.columns(3)
    f1.metric("fib0 (Session High)", f"{snap['fib0']:,.2f}" if snap["fib0"] else "pending")
    f2.metric("fib0.5 (Midpoint)", f"{snap['fib0_5']:,.2f}" if snap["fib0_5"] else "pending")
    f3.metric("fib1 (Session Low)", f"{snap['fib1']:,.2f}" if snap["fib1"] else "pending")

    st.subheader("Projected Levels")
    if snap["levels_up"] or snap["levels_down"]:
        current_price = snap["current_price"]
        rows = []
        anchor = snap["anchor_opening_level"]
        rows.append({"label": "Opening (Anchor)", "price": anchor, "direction": "ANCHOR", "index": 0})
        for lvl in snap["levels_up"]:
            rows.append({"label": f"Level +{lvl['index']}", "price": lvl["price"], "direction": "UP", "index": lvl["index"]})
        for lvl in snap["levels_down"]:
            rows.append({"label": f"Level -{lvl['index']}", "price": lvl["price"], "direction": "DOWN", "index": lvl["index"]})
        df = pd.DataFrame(rows).sort_values("price", ascending=False).reset_index(drop=True)
        nearest_price = snap["nearest_level"]["price"] if snap["nearest_level"] else None

        def _highlight(row):
            if row["direction"] == "ANCHOR":
                return ["background-color: #444"] * len(row)
            if nearest_price is not None and row["price"] == nearest_price:
                return ["background-color: #2e7d32; color: white"] * len(row)
            return [""] * len(row)

        st.caption(f"Current price: **{current_price:,.2f}** — highlighted row is the nearest level.")
        st.dataframe(df.style.apply(_highlight, axis=1), width="stretch", hide_index=True)
    else:
        st.info("No admin levels available yet for the current trading day (still tracking or fallback pending).")

    st.subheader("Market Status")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Current Price", f"{snap['current_price']:,.2f}")
    m1.metric("Current Bias", snap["bias"])
    m2.metric("Current Trend", snap["trend"])
    m2.metric("NY Session Active", "Yes" if snap["ny_session_active"] else "No")
    m3.metric("Active Signal", snap["active_signal"])
    m3.metric("Waiting for Confirmation", "Yes" if snap["waiting_for_confirmation"] else "No")
    m4.metric("Position Active", "Yes" if snap["position_active"] else "No")
    if snap["signal_reason"]:
        st.caption(f"Reason: {snap['signal_reason']}")

    st.subheader("Trade Execution Panel")
    open_trade = current_open_trade()
    if open_trade is None:
        st.info("No open trade recorded by live_testnet_runner.py right now.")
    else:
        t1, t2, t3, t4 = st.columns(4)
        t1.metric("Trade #", open_trade["trade_number"])
        t1.metric("Direction", open_trade["side"])
        t2.metric("Entry Price", f"{open_trade['entry_price']:,.2f}")
        t2.metric("Entry Time", open_trade["entry_time"])
        t3.metric("Stop Loss", f"{open_trade['stop_loss_price']:,.2f}")
        t3.metric("Target", f"{open_trade['target_price']:,.2f}")
        t4.metric("Risk:Reward", f"1:{open_trade['risk_reward_ratio']:.2f}")
        t4.metric("Status", open_trade["status"])
        st.caption(
            "This reflects the trade log written by live_testnet_runner.py — "
            "start that process separately for this panel to show live positions."
        )

    st.subheader("Distances")
    d1, d2, d3, d4 = st.columns(4)
    for col, label, key in [
        (d1, "From Session High", "distance_from_high"),
        (d2, "From Session Low", "distance_from_low"),
        (d3, "From Midpoint", "distance_from_mid"),
        (d4, "From Opening", "distance_from_opening"),
    ]:
        dist = snap[key]
        if dist is None:
            col.metric(label, "—")
        else:
            col.metric(label, f"{dist['price_diff']:+,.2f}", f"{dist['pct_diff']:+.3f}%")


render_live_panel()
