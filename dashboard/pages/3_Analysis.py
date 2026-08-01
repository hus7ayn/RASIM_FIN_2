from __future__ import annotations

import glob
import json
import os
import sys

import pandas as pd
import plotly.express as px
import streamlit as st

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from dashboard.analytics import (
    build_equity_curve_from_trades,
    daily_stats,
    drawdown_series,
    monthly_stats,
    overall_stats,
    weekly_stats,
)
from dashboard.trade_log import OPEN_STATUSES, load_trade_log
from dashboard.ui import demo_badge

DATA_DIR = os.path.join(_REPO_ROOT, "data_pipeline", "data")

st.set_page_config(page_title="Analysis", layout="wide")
st.title("Performance Analysis")


# --------------------------------------------------------------- data source
def _backtest_files() -> list[str]:
    return sorted(glob.glob(os.path.join(DATA_DIR, "*_backtest.json")), key=os.path.getmtime, reverse=True)


source = st.radio(
    "Source",
    ["Live trade log", "Backtest run"],
    horizontal=True,
    help="Analyse trades recorded live, or any saved backtest run.",
)

meta: dict = {}
if source == "Live trade log":
    rows = load_trade_log()
    closed = [r for r in rows if r.get("status") not in OPEN_STATUSES and r.get("pnl_usd") is not None]
    open_count = sum(1 for r in rows if r.get("status") in OPEN_STATUSES)
    if not closed:
        st.info(
            f"No closed live trades yet ({open_count} still open). "
            "Closed trades are needed to compute performance."
        )
        st.stop()
    trades = closed
    initial_capital = 10_000.0
    if any(r.get("synthetic") for r in closed):
        demo_badge()
    st.caption(
        f"{len(closed)} closed trade(s) from the live log"
        + (f"; {open_count} open trade(s) excluded from these metrics." if open_count else ".")
    )
else:
    files = _backtest_files()
    if not files:
        st.warning(f"No backtest JSON files in {DATA_DIR}.")
        st.stop()
    labels = [os.path.basename(f) for f in files]
    chosen = st.selectbox("Backtest run", labels)
    with open(files[labels.index(chosen)], "r", encoding="utf-8") as f:
        meta = json.load(f)
    trades = meta.get("trades", [])
    initial_capital = meta.get("initial_capital")
    if initial_capital is None:
        initial_capital = meta.get("ending_capital", 0.0) - meta.get("total_pnl_usd", 0.0)
    if meta.get("synthetic"):
        demo_badge()
    if not trades:
        st.info("This run produced no trades.")
        st.stop()

stats = overall_stats(trades, initial_capital)

# --------------------------------------------------------------- headline row
st.subheader("Key metrics")
k1, k2, k3, k4 = st.columns(4)
k1.metric("Net Profit", f"${stats['net_profit_usd']:,.2f}", f"{stats['net_profit_pct']:.2f}%")
k2.metric("Total Trades", stats["total_trades"])
k3.metric("Win Rate", f"{stats['win_rate_pct']:.1f}%")

avg_win = stats["average_win"]
avg_loss = abs(stats["average_loss"])
realized_rr = (avg_win / avg_loss) if avg_loss else None
k4.metric(
    "Risk : Reward",
    f"1 : {realized_rr:.2f}" if realized_rr else "—",
    help="Achieved ratio — average winning trade divided by average losing trade.",
)

k5, k6, k7, k8 = st.columns(4)
k5.metric("Avg Trade Duration", f"{stats['avg_trade_duration_minutes']:.1f} min")
k6.metric("Biggest Profit", f"${stats['largest_win']:,.2f}")
k7.metric("Biggest Loss", f"${stats['largest_loss']:,.2f}")
k8.metric("Avg P&L / Trade", f"${stats['average_trade']:,.2f}")

st.divider()
st.subheader("Supporting detail")
s1, s2, s3, s4 = st.columns(4)
s1.metric("Winning Trades", stats["winning_trades"])
s1.metric("Losing Trades", stats["losing_trades"])
s2.metric("Gross Profit", f"${stats['gross_profit']:,.2f}")
s2.metric("Gross Loss", f"${stats['gross_loss']:,.2f}")
s3.metric("Avg Win", f"${stats['average_win']:,.2f}")
s3.metric("Avg Loss", f"${stats['average_loss']:,.2f}")
s4.metric(
    "Profit Factor",
    f"{stats['profit_factor']:.2f}" if stats["profit_factor"] is not None else "∞",
)
s4.metric("Max Drawdown", f"{stats['max_drawdown_pct']:.2f}%", f"-${stats['max_drawdown_usd']:,.2f}")

t1, t2 = st.columns(2)
t1.metric("Max Consecutive Wins", stats["max_consecutive_wins"])
t2.metric("Max Consecutive Losses", stats["max_consecutive_losses"])

# --------------------------------------------------------------- charts
st.divider()
st.subheader("Performance summary")

trades_df = pd.DataFrame(trades)
trades_df["pnl_usd"] = pd.to_numeric(trades_df["pnl_usd"], errors="coerce")
trades_df = trades_df.dropna(subset=["pnl_usd"])
entry_col = "entry_timestamp_ist" if "entry_timestamp_ist" in trades_df else "entry_time"
exit_col = "exit_timestamp_ist" if "exit_timestamp_ist" in trades_df else "exit_time"
trades_df["entry_dt"] = pd.to_datetime(trades_df[entry_col], errors="coerce")
trades_df["exit_dt"] = pd.to_datetime(trades_df[exit_col], errors="coerce")
trades_df["duration_min"] = (trades_df["exit_dt"] - trades_df["entry_dt"]).dt.total_seconds() / 60.0
trades_df["outcome"] = trades_df["pnl_usd"].apply(lambda p: "Win" if p > 0 else "Loss")

eq_rows = build_equity_curve_from_trades(trades, initial_capital)
eq_df = pd.DataFrame(eq_rows)
eq_df["trade_index"] = range(len(eq_df))

c1, c2 = st.columns(2)
with c1:
    st.plotly_chart(
        px.line(eq_df, x="trade_index", y="capital", title="Equity Curve"),
        width="stretch", key="an_equity",
    )
    st.plotly_chart(
        px.histogram(trades_df, x="pnl_usd", nbins=30, title="P&L Distribution per Trade"),
        width="stretch", key="an_pnl_dist",
    )
    st.plotly_chart(
        px.pie(trades_df, names="outcome", title="Win / Loss Split", hole=0.45),
        width="stretch", key="an_winloss",
    )
with c2:
    dd_df = pd.DataFrame(drawdown_series(eq_rows))
    dd_df["trade_index"] = range(len(dd_df))
    fig_dd = px.area(dd_df, x="trade_index", y="drawdown_pct", title="Drawdown (%)")
    fig_dd.update_yaxes(autorange="reversed")
    st.plotly_chart(fig_dd, width="stretch", key="an_drawdown")

    st.plotly_chart(
        px.histogram(trades_df, x="duration_min", nbins=30, title="Trade Duration (minutes)"),
        width="stretch", key="an_duration",
    )
    monthly_df = pd.DataFrame(monthly_stats(trades, initial_capital))
    if not monthly_df.empty:
        st.plotly_chart(
            px.bar(monthly_df, x="month", y="net_profit_usd", title="Net Profit by Month"),
            width="stretch", key="an_monthly",
        )

w1, w2 = st.columns(2)
weekday_df = pd.DataFrame(weekly_stats(trades))
with w1:
    st.plotly_chart(
        px.bar(weekday_df, x="weekday", y="net_profit_usd", title="Net Profit by Day of Week"),
        width="stretch", key="an_weekday",
    )
with w2:
    daily_df = pd.DataFrame(daily_stats(trades))
    if not daily_df.empty:
        st.plotly_chart(
            px.bar(daily_df, x="date", y="net_profit_usd", title="Daily Net Profit"),
            width="stretch", key="an_daily",
        )

# --------------------------------------------------------------- tables + export
st.divider()
st.subheader("Breakdowns")
tab_m, tab_w = st.tabs(["Monthly", "By weekday"])
with tab_m:
    if monthly_df.empty:
        st.info("No monthly data.")
    else:
        st.dataframe(monthly_df, width="stretch", hide_index=True)
with tab_w:
    st.dataframe(weekday_df, width="stretch", hide_index=True)

export_payload = {
    # Kept as real JSON fields rather than a comment line so the file stays parseable.
    **({"synthetic": True, "disclaimer": meta.get("disclaimer")} if meta.get("synthetic") else {}),
    "source": source,
    **stats,
    "risk_reward_achieved": realized_rr,
}
st.download_button(
    "Export key metrics (JSON)",
    data=json.dumps(export_payload, indent=2),
    file_name=("SYNTHETIC_DEMO_analysis.json" if meta.get("synthetic") else "analysis_metrics.json"),
    mime="application/json",
)
