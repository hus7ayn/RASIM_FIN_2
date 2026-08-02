from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import pandas as pd
import streamlit as st

from dashboard import credentials
from dashboard.live import fetch_recent_candles, get_live_snapshot
from dashboard.position_manager import (
    amend_tp_sl,
    book_partial,
    compute_live_pnl,
    open_demo_trade,
    preflight_check,
    test_connection,
)
from dashboard.trade_log import current_open_trade
from dashboard.ui import demo_badge
from strategies import describe_strategy, list_strategies


def _now_ist_str() -> str:
    return (datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=5, minutes=30)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )

st.set_page_config(page_title="Live Monitor", layout="wide")
st.title("Trading Strategy — Live Monitor")

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


def _last_price(sym: str) -> float | None:
    try:
        candles = fetch_recent_candles(symbol=sym, limit=2)
        return candles[-1].close if candles else None
    except Exception:  # noqa: BLE001
        return None


# Deliberately a separate fragment with NO run_every: an auto-refresh tick would clear
# a half-typed TP/SL or partial-size entry. This panel reruns only on interaction.
@st.fragment
def render_position_panel() -> None:
    st.subheader("Open Position")

    trade = current_open_trade()
    if trade is None:
        st.info(
            "No open position in the trade log. Run `live_testnet_runner.py`, or open one "
            "via the strategy, and the live controls will appear here."
        )
        if st.button("Refresh position", key="pos_refresh_empty"):
            st.rerun()
        return

    if trade.get("synthetic"):
        demo_badge("Simulated position for demonstration — not a real position.")

    current_price = _last_price(symbol) or float(trade["entry_price"])
    remaining = float(trade["remaining_quantity"] or 0.0)
    pnl = compute_live_pnl(trade["side"], float(trade["entry_price"]), current_price, remaining)

    p1, p2, p3, p4 = st.columns(4)
    p1.metric("Trade #", trade["trade_number"])
    p1.metric("Direction", trade["side"])
    p2.metric("Entry Price", f"{trade['entry_price']:,.2f}")
    p2.metric("Current Price", f"{current_price:,.2f}")
    p3.metric(
        "Live P&L",
        f"${pnl['pnl_usd']:+,.2f}",
        f"{pnl['pnl_pct_of_notional']:+.4f}% of notional",
    )
    p3.metric("Position Size", f"{remaining:.5f}")
    p4.metric("Take Profit", f"{trade['target_price']:,.2f}")
    p4.metric("Stop Loss", f"{trade['stop_loss_price']:,.2f}")

    q1, q2, q3 = st.columns(3)
    q1.metric("Status", trade["status"])
    q2.metric("Booked so far", f"${float(trade['realized_pnl_usd'] or 0):+,.2f}")
    q3.metric(
        "P&L on engine basis",
        f"${pnl['pnl_usd_engine_basis']:+,.2f}",
        help=(
            "The strategy measures its $100 stop and $450 target against this figure, "
            "which multiplies P&L by leverage. It is 13x the textbook value shown above."
        ),
    )

    warnings = preflight_check(float(trade["entry_price"]), remaining, capital)
    for w in warnings:
        st.warning(w)

    live_writes = st.toggle(
        "Send changes to the exchange",
        value=False,
        key="pos_live_writes",
        help=(
            "Off: changes are recorded in the trade log only. On: real cancel/replace and "
            "reduce-only orders are submitted to the Binance demo futures endpoint."
        ),
    )
    if live_writes and not credentials.present():
        st.error(
            "No API credentials — connect a Binance testnet key in the Exchange connection "
            "panel below, or leave this off to record changes in the log only."
        )
        live_writes = False

    edit_col, book_col = st.columns(2)

    # ---------------------------------------------------------- TP / SL editing
    with edit_col:
        st.markdown("**Edit TP / SL**")
        with st.form("tp_sl_form", border=False):
            new_tp = st.number_input(
                "Take Profit", value=float(trade["target_price"]), step=1.0, format="%.2f",
            )
            new_sl = st.number_input(
                "Stop Loss", value=float(trade["stop_loss_price"]), step=1.0, format="%.2f",
            )
            if st.form_submit_button("Apply TP / SL"):
                try:
                    res = amend_tp_sl(
                        symbol=symbol,
                        new_target=new_tp,
                        new_stop=new_sl,
                        timestamp_ist=_now_ist_str(),
                        validate_only=not live_writes,
                    )
                    if res["exchange_applied"]:
                        st.success(
                            f"Applied on exchange — cancelled {len(res['cancelled_orders'])}, "
                            f"placed {len(res['placed_orders'])}."
                        )
                    else:
                        st.success("Recorded in trade log (not sent to exchange).")
                    st.rerun()
                except Exception as exc:  # noqa: BLE001
                    st.error(f"Could not update TP/SL: {exc}")

    # ---------------------------------------------------------- partial booking
    with book_col:
        st.markdown("**Partial position booking**")
        with st.form("partial_form", border=False):
            mode = st.radio("Book by", ["Percent", "Quantity"], horizontal=True)
            pct = st.slider("Percent of open size", 1, 100, 25, step=1)
            qty = st.number_input(
                "Quantity", value=round(remaining / 2, 5), min_value=0.0,
                max_value=float(remaining), step=0.001, format="%.5f",
            )
            preview_qty = remaining * pct / 100.0 if mode == "Percent" else qty
            st.caption(
                f"Books {preview_qty:.5f} of {remaining:.5f}, leaving "
                f"{max(remaining - preview_qty, 0):.5f} open."
            )
            if st.form_submit_button("Book partial"):
                try:
                    res = book_partial(
                        symbol=symbol,
                        fraction=(pct / 100.0) if mode == "Percent" else None,
                        quantity=None if mode == "Percent" else qty,
                        current_price=current_price,
                        timestamp_ist=_now_ist_str(),
                        validate_only=not live_writes,
                    )
                    st.success(
                        f"Booked {res['requested_quantity']:.5f} at {current_price:,.2f} — "
                        f"leg P&L ${res['leg_pnl_usd']:+,.2f}; "
                        f"{res['remaining_after']:.5f} still open ({res['status']})."
                        + ("" if res["exchange_applied"] else " Log only, no exchange order.")
                    )
                    st.rerun()
                except Exception as exc:  # noqa: BLE001
                    st.error(f"Could not book partial: {exc}")

    with st.expander("Partial exits and TP/SL history for this trade"):
        if trade["partial_exits"]:
            st.dataframe(pd.DataFrame(trade["partial_exits"]), width="stretch", hide_index=True)
        else:
            st.caption("No partial exits yet.")
        if trade["tp_sl_modifications"]:
            st.dataframe(pd.DataFrame(trade["tp_sl_modifications"]), width="stretch", hide_index=True)
        else:
            st.caption("TP and SL unchanged since entry.")


# Own fragment, no auto-refresh: a refresh tick mid-entry would clear a pasted key.
@st.fragment
def render_connection_panel() -> None:
    st.subheader("Exchange connection")

    src = credentials.source()
    if src:
        key, _ = credentials.resolve()
        st.success(f"Connected key {credentials.masked(key)} — from {src}.")
    else:
        st.info("No API credentials configured. The dashboard is read-only until you add one.")

    st.caption(
        "**Binance testnet keys only.** Every endpoint this app uses points at "
        "`demo-fapi.binance.com`, so a mainnet key cannot trade here — but it would still "
        "be sent to whatever host is serving this page. Keys are held in this browser "
        "session only: never written to disk, never logged, and gone when the session ends. "
        "On a hosted deployment, prefer `st.secrets` over typing them in."
    )

    with st.form("creds_form", border=False):
        c1, c2 = st.columns(2)
        api_key_in = c1.text_input("API key", type="password", autocomplete="off")
        api_secret_in = c2.text_input("API secret", type="password", autocomplete="off")
        save_col, test_col, clear_col = st.columns(3)
        saved = save_col.form_submit_button("Use these keys")
        tested = test_col.form_submit_button("Test connection")
        cleared = clear_col.form_submit_button("Forget keys")

        if cleared:
            credentials.clear()
            st.success("Keys cleared from this session.")

        if saved or tested:
            if api_key_in and api_secret_in:
                credentials.store(api_key_in, api_secret_in)
            if not credentials.present():
                st.error("Enter both an API key and secret.")
            elif tested:
                try:
                    info = test_connection(symbol)
                    st.success(
                        f"Connected to {info['endpoint']} — {info['symbol']} last "
                        f"{info['last_price']:,.2f}, USDT balance "
                        f"{info['usdt_total']}, {info['open_positions']} open position(s)."
                    )
                except Exception as exc:  # noqa: BLE001
                    st.error(f"Connection failed: {exc}")
            else:
                st.success("Keys stored for this session.")

    if not credentials.present():
        return

    st.markdown("**Place a trade**")
    st.caption(
        "Opens a position on the demo account, sized by the strategy's own risk model, "
        "with reduce-only stop and target attached. It then appears in the position panel "
        "above and in Trade History."
    )
    with st.form("demo_trade_form", border=False):
        d1, d2, d3 = st.columns(3)
        demo_side = d1.selectbox("Direction", ["BUY", "SELL"])
        demo_capital = d2.number_input(
            "Capital for sizing (USD)", value=float(capital), step=500.0, min_value=1.0
        )
        really_fill = d3.toggle(
            "Actually fill it",
            value=False,
            help=(
                "Off: the order is sent with Binance's test flag and does not fill — it "
                "validates that the exchange would accept it. On: a real order is placed "
                "against the demo account."
            ),
        )
        if st.form_submit_button("Open trade"):
            price = _last_price(symbol)
            if price is None:
                st.error("Could not fetch a current price — try again.")
            else:
                try:
                    res = open_demo_trade(
                        symbol=symbol,
                        side=demo_side,
                        capital=demo_capital,
                        current_price=price,
                        timestamp_ist=_now_ist_str(),
                        validate_only=not really_fill,
                    )
                    for w in res["warnings"]:
                        st.warning(w)
                    st.success(
                        f"Trade #{res['trade_number']} {res['side']} {res['quantity']:.5f} "
                        f"@ {res['entry_price']:,.2f} — notional ${res['notional_usd']:,.0f} "
                        f"({res['implied_leverage']:.1f}x), risking ${res['risk_usd']:,.2f}. "
                        f"SL {res['stop_price']:,.2f} / TP {res['target_price']:,.2f}."
                        + ("" if really_fill else " Validate-only: no fill.")
                    )
                    if res["placed_orders"]:
                        st.caption(
                            "Orders: "
                            + ", ".join(f"{o['role']}={o['id']}" for o in res["placed_orders"])
                        )
                except Exception as exc:  # noqa: BLE001
                    st.error(f"Could not open demo trade: {exc}")


render_live_panel()
st.divider()
render_position_panel()
st.divider()
render_connection_panel()
