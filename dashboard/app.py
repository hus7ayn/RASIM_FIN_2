from __future__ import annotations

import glob
import json
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import pandas as pd
import plotly.express as px
import streamlit as st

from dashboard.analytics import (
    build_equity_curve_from_trades,
    daily_stats,
    drawdown_series,
    monthly_stats,
    overall_stats,
    strategy_insights,
    weekly_stats,
)
from dashboard.pdf_report import generate_pdf_report
from dashboard.ui import badge_hidden, demo_badge

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(REPO_ROOT, "data_pipeline", "data")

st.set_page_config(page_title="Strategy Dashboard", layout="wide")


@st.cache_data
def load_backtest(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def find_backtest_files() -> list[str]:
    pattern = os.path.join(DATA_DIR, "*_backtest.json")
    return sorted(glob.glob(pattern), key=os.path.getmtime, reverse=True)


st.title("Trading Strategy — Backtest Analytics")

files = find_backtest_files()
if not files:
    st.warning(f"No backtest JSON files found in {DATA_DIR}. Run the data pipeline or backtest CLI first.")
    st.stop()

labels = [os.path.basename(f) for f in files]
selected_label = st.sidebar.selectbox("Backtest file", labels)
selected_path = files[labels.index(selected_label)]

data = load_backtest(selected_path)
trades = data.get("trades", [])
initial_capital = data.get("initial_capital")
if initial_capital is None:
    initial_capital = data.get("ending_capital", 0.0) - data.get("total_pnl_usd", 0.0)

IS_SYNTHETIC = bool(data.get("synthetic"))
SYNTHETIC_NOTICE = data.get("disclaimer") or (
    "SYNTHETIC DEMO DATA - INVENTED FOR UI DEMONSTRATION ONLY. "
    "These trades never happened and do not represent strategy performance."
)

if IS_SYNTHETIC:
    demo_badge()
    if not badge_hidden():
        st.sidebar.caption("◆ Demo data file")


def _export_prefix() -> str:
    """Prepended to text exports so the synthetic label survives a download."""
    return f"# {SYNTHETIC_NOTICE}\n" if IS_SYNTHETIC else ""


st.sidebar.markdown(f"**Symbol:** {data.get('symbol', 'n/a')}")
st.sidebar.markdown(f"**Range:** {data.get('start_timestamp_ist', '?')} → {data.get('end_timestamp_ist', '?')}")
st.sidebar.markdown(f"**Candles:** {data.get('candles', '?'):,}" if isinstance(data.get("candles"), int) else "")
st.sidebar.markdown(f"**Initial capital:** ${initial_capital:,.2f}")

st.sidebar.divider()
st.sidebar.subheader("Trade log filters")
direction_filter = st.sidebar.multiselect("Direction", ["BUY", "SELL"], default=["BUY", "SELL"])
outcome_filter = st.sidebar.radio("Outcome", ["All", "Wins only", "Losses only"], index=0)

stats = overall_stats(trades, initial_capital)
monthly_rows = monthly_stats(trades, initial_capital)
weekly_rows = weekly_stats(trades)

tab_overview, tab_monthly, tab_weekly, tab_insights, tab_charts, tab_log = st.tabs(
    ["Overview", "Monthly", "Weekly", "Insights", "Charts", "Trade Log"]
)

# ---------------------------------------------------------------- Overview
with tab_overview:
    if stats["total_trades"] == 0:
        st.info("No trades in this backtest window.")
    else:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total Trades", stats["total_trades"])
        c1.metric("Win Rate", f"{stats['win_rate_pct']:.1f}%")
        c2.metric("Net Profit", f"${stats['net_profit_usd']:,.2f}", f"{stats['net_profit_pct']:.2f}%")
        c2.metric(
            "Profit Factor",
            f"{stats['profit_factor']:.2f}" if stats["profit_factor"] is not None else "∞",
        )
        c3.metric("Expectancy / Trade", f"${stats['expectancy']:,.2f}")
        c3.metric("Max Drawdown", f"{stats['max_drawdown_pct']:.2f}%", f"-${stats['max_drawdown_usd']:,.2f}")
        c4.metric("Max Win Streak", stats["max_consecutive_wins"])
        c4.metric("Max Loss Streak", stats["max_consecutive_losses"])

        st.divider()
        d1, d2, d3, d4 = st.columns(4)
        d1.metric("Gross Profit", f"${stats['gross_profit']:,.2f}")
        d2.metric("Gross Loss", f"${stats['gross_loss']:,.2f}")
        d3.metric("Largest Win", f"${stats['largest_win']:,.2f}")
        d4.metric("Largest Loss", f"${stats['largest_loss']:,.2f}")
        e1, e2, e3, e4 = st.columns(4)
        e1.metric("Avg Trade", f"${stats['average_trade']:,.2f}")
        e2.metric("Avg Win", f"${stats['average_win']:,.2f}")
        e3.metric("Avg Loss", f"${stats['average_loss']:,.2f}")
        e4.metric("Avg Duration", f"{stats['avg_trade_duration_minutes']:.1f} min")

        eq_rows = build_equity_curve_from_trades(trades, initial_capital)
        eq_df = pd.DataFrame(eq_rows)
        eq_df["trade_index"] = range(len(eq_df))

        st.subheader("Equity Curve")
        st.plotly_chart(px.line(eq_df, x="trade_index", y="capital"), width="stretch", key="equity_curve")

        st.subheader("Drawdown Curve")
        dd_df = pd.DataFrame(drawdown_series(eq_rows))
        dd_df["trade_index"] = range(len(dd_df))
        fig_dd = px.area(dd_df, x="trade_index", y="drawdown_pct")
        fig_dd.update_yaxes(autorange="reversed")
        st.plotly_chart(fig_dd, width="stretch", key="drawdown_curve")

        st.subheader("Export")
        ex1, ex2 = st.columns(2)
        stats_payload = dict(stats)
        if IS_SYNTHETIC:
            stats_payload = {"synthetic": True, "disclaimer": SYNTHETIC_NOTICE, **stats_payload}
        ex1.download_button(
            "Download performance stats (JSON)",
            data=json.dumps(stats_payload, indent=2),
            file_name=("SYNTHETIC_DEMO_performance_stats.json" if IS_SYNTHETIC else "performance_stats.json"),
            mime="application/json",
        )
        pdf_bytes = generate_pdf_report(
            meta=data,
            stats=stats,
            monthly_rows=monthly_rows,
            weekly_rows=weekly_rows,
            trades=trades,
            initial_capital=initial_capital,
            synthetic_notice=SYNTHETIC_NOTICE if IS_SYNTHETIC else None,
        )
        ex2.download_button(
            "Download full report (PDF)",
            data=pdf_bytes,
            file_name=("SYNTHETIC_DEMO_backtest_report.pdf" if IS_SYNTHETIC else "backtest_report.pdf"),
            mime="application/pdf",
        )

# ---------------------------------------------------------------- Monthly
with tab_monthly:
    m_rows = monthly_rows
    if not m_rows:
        st.info("No trades to summarize.")
    else:
        m_df = pd.DataFrame(m_rows)
        st.dataframe(m_df, width="stretch", hide_index=True)
        st.plotly_chart(
            px.bar(m_df, x="month", y="net_profit_usd", title="Monthly Net Profit"),
            width="stretch", key="monthly_net",
        )
        st.download_button(
            "Download monthly summary (CSV)",
            data=_export_prefix() + m_df.to_csv(index=False),
            file_name=("SYNTHETIC_DEMO_monthly_summary.csv" if IS_SYNTHETIC else "monthly_summary.csv"),
            mime="text/csv",
        )

# ---------------------------------------------------------------- Weekly
with tab_weekly:
    w_rows = weekly_rows
    w_df = pd.DataFrame(w_rows)
    st.dataframe(w_df, width="stretch", hide_index=True)
    st.plotly_chart(
        px.bar(w_df, x="weekday", y="net_profit_usd", title="Profit by Day of Week"),
        width="stretch", key="weekly_net",
    )

# ---------------------------------------------------------------- Insights
with tab_insights:
    insights = strategy_insights(trades)
    if stats["total_trades"] == 0:
        st.info("No trades to analyze.")
    else:
        i1, i2 = st.columns(2)
        with i1:
            st.markdown("**Best Day**")
            st.write(insights["best_day"])
            st.markdown("**Best Hour (IST, entry)**")
            st.write(insights["best_hour_ist"])
            st.markdown("**Most Profitable Direction**")
            st.write(insights["most_profitable_direction"])
        with i2:
            st.markdown("**Worst Day**")
            st.write(insights["worst_day"])
            st.markdown("**Worst Hour (IST, entry)**")
            st.write(insights["worst_hour_ist"])
            st.markdown("**Least Profitable Direction**")
            st.write(insights["least_profitable_direction"])
        st.divider()
        j1, j2, j3 = st.columns(3)
        j1.metric("Avg Holding Time", f"{insights['avg_holding_time_minutes']:.1f} min")
        j2.metric("Most Common Exit Reason", insights["most_common_exit_reason"] or "n/a")
        j3.metric("Avg R Achieved", f"{insights['avg_risk_reward_achieved']:.2f}R")

# ---------------------------------------------------------------- Charts
with tab_charts:
    if stats["total_trades"] == 0:
        st.info("No trades to chart.")
    else:
        trades_df = pd.DataFrame(trades)
        trades_df["pnl_usd"] = trades_df["pnl_usd"].astype(float)
        trades_df["outcome"] = trades_df["pnl_usd"].apply(lambda p: "Win" if p > 0 else "Loss")
        trades_df["entry_dt"] = pd.to_datetime(trades_df["entry_timestamp_ist"])
        trades_df["exit_dt"] = pd.to_datetime(trades_df["exit_timestamp_ist"])
        trades_df["duration_min"] = (trades_df["exit_dt"] - trades_df["entry_dt"]).dt.total_seconds() / 60.0
        trades_df["cumulative_pnl"] = trades_df.sort_values("exit_dt")["pnl_usd"].cumsum()

        col1, col2 = st.columns(2)
        with col1:
            st.plotly_chart(
                px.line(trades_df.sort_values("exit_dt"), x="exit_dt", y="cumulative_pnl", title="Cumulative Profit"),
                width="stretch", key="chart_cum_profit",
            )
            st.plotly_chart(
                px.pie(trades_df, names="outcome", title="Win/Loss Distribution"),
                width="stretch", key="chart_winloss_pie",
            )
            st.plotly_chart(
                px.histogram(trades_df, x="duration_min", title="Trade Duration Distribution (minutes)"),
                width="stretch", key="chart_duration_hist",
            )
        with col2:
            daily_df = pd.DataFrame(daily_stats(trades))
            if not daily_df.empty:
                st.plotly_chart(
                    px.bar(daily_df, x="date", y="net_profit_usd", title="Daily P&L"),
                    width="stretch", key="chart_daily_pnl",
                )
            trades_df["entry_hour"] = trades_df["entry_dt"].dt.hour
            hour_profit = trades_df.groupby("entry_hour")["pnl_usd"].sum().reset_index()
            st.plotly_chart(
                px.bar(hour_profit, x="entry_hour", y="pnl_usd", title="Profit by Hour of Day (IST)"),
                width="stretch", key="chart_hour_profit",
            )
            # Same underlying chart as the Weekly tab, so it needs its own key.
            weekday_df = pd.DataFrame(weekly_rows)
            st.plotly_chart(
                px.bar(weekday_df, x="weekday", y="net_profit_usd", title="Profit by Day of Week"),
                width="stretch", key="chart_weekday_profit",
            )

# ---------------------------------------------------------------- Trade Log
with tab_log:
    if not trades:
        st.info("No trades in this backtest window.")
    else:
        log_df = pd.DataFrame(trades)
        log_df["pnl_usd"] = log_df["pnl_usd"].astype(float)
        if direction_filter:
            log_df = log_df[log_df["side"].isin(direction_filter)]
        if outcome_filter == "Wins only":
            log_df = log_df[log_df["pnl_usd"] > 0]
        elif outcome_filter == "Losses only":
            log_df = log_df[log_df["pnl_usd"] < 0]

        log_df = log_df.sort_values("exit_timestamp_ist")
        st.dataframe(log_df, width="stretch", hide_index=True)
        st.download_button(
            "Download trade history (CSV)",
            data=_export_prefix() + log_df.to_csv(index=False),
            file_name=("SYNTHETIC_DEMO_trade_history.csv" if IS_SYNTHETIC else "trade_history.csv"),
            mime="text/csv",
        )
