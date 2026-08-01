from __future__ import annotations

import io
from typing import Any, Dict, List, Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

from dashboard.analytics import build_equity_curve_from_trades, drawdown_series


def _stamp_synthetic(fig, notice: str) -> None:
    """Mark a page as synthetic, both as a header band and a diagonal watermark, so the
    label cannot be cropped off or mistaken for a real performance record."""
    fig.text(
        0.5, 0.975, notice, ha="center", va="top", fontsize=7.5, color="#8b1a2b",
        wrap=True, weight="bold",
        bbox=dict(facecolor="#fdecef", edgecolor="#8b1a2b", linewidth=0.8, pad=4),
    )
    fig.text(
        0.5, 0.45, "SYNTHETIC DEMO", ha="center", va="center", fontsize=58,
        color="#8b1a2b", alpha=0.10, rotation=32, weight="bold", zorder=10,
    )


def _title_page(
    pdf: PdfPages, meta: Dict[str, Any], stats: Dict[str, Any], notice: str | None = None
) -> None:
    fig = plt.figure(figsize=(8.5, 11))
    if notice:
        _stamp_synthetic(fig, notice)
    fig.text(0.5, 0.93, "Trading Strategy — Backtest Report", ha="center", fontsize=18, weight="bold")
    fig.text(0.5, 0.89, f"Symbol: {meta.get('symbol', 'n/a')}", ha="center", fontsize=11)
    fig.text(
        0.5, 0.86,
        f"Range: {meta.get('start_timestamp_ist', '?')} → {meta.get('end_timestamp_ist', '?')}",
        ha="center", fontsize=11,
    )

    lines = [
        ("Total Trades", stats["total_trades"]),
        ("Winning Trades", stats["winning_trades"]),
        ("Losing Trades", stats["losing_trades"]),
        ("Win Rate", f"{stats['win_rate_pct']:.2f}%"),
        ("Net Profit (USD)", f"${stats['net_profit_usd']:,.2f}"),
        ("Net Profit (%)", f"{stats['net_profit_pct']:.2f}%"),
        ("Gross Profit", f"${stats['gross_profit']:,.2f}"),
        ("Gross Loss", f"${stats['gross_loss']:,.2f}"),
        ("Profit Factor", f"{stats['profit_factor']:.2f}" if stats["profit_factor"] is not None else "∞"),
        ("Expectancy / Trade", f"${stats['expectancy']:,.2f}"),
        ("Average Win", f"${stats['average_win']:,.2f}"),
        ("Average Loss", f"${stats['average_loss']:,.2f}"),
        ("Largest Win", f"${stats['largest_win']:,.2f}"),
        ("Largest Loss", f"${stats['largest_loss']:,.2f}"),
        ("Max Drawdown", f"{stats['max_drawdown_pct']:.2f}% (${stats['max_drawdown_usd']:,.2f})"),
        ("Max Consecutive Wins", stats["max_consecutive_wins"]),
        ("Max Consecutive Losses", stats["max_consecutive_losses"]),
        ("Avg Trade Duration", f"{stats['avg_trade_duration_minutes']:.1f} min"),
    ]
    y = 0.80
    for label, value in lines:
        fig.text(0.12, y, label, fontsize=10)
        fig.text(0.65, y, str(value), fontsize=10, ha="right")
        y -= 0.035
    pdf.savefig(fig)
    plt.close(fig)


def _equity_and_drawdown_pages(
    pdf: PdfPages,
    trades: Sequence[Dict[str, Any]],
    initial_capital: float,
    notice: str | None = None,
) -> None:
    eq_rows = build_equity_curve_from_trades(trades, initial_capital)
    x = list(range(len(eq_rows)))
    capital = [r["capital"] for r in eq_rows]

    fig, ax = plt.subplots(figsize=(8.5, 5))
    if notice:
        _stamp_synthetic(fig, notice)
    ax.plot(x, capital, color="#1f77b4")
    ax.set_title("Equity Curve")
    ax.set_xlabel("Trade #")
    ax.set_ylabel("Capital (USD)")
    ax.grid(alpha=0.3)
    pdf.savefig(fig)
    plt.close(fig)

    dd_rows = drawdown_series(eq_rows)
    dd = [r["drawdown_pct"] for r in dd_rows]
    fig, ax = plt.subplots(figsize=(8.5, 5))
    if notice:
        _stamp_synthetic(fig, notice)
    ax.fill_between(x, dd, color="#d62728", alpha=0.4)
    ax.plot(x, dd, color="#d62728")
    ax.invert_yaxis()
    ax.set_title("Drawdown Curve")
    ax.set_xlabel("Trade #")
    ax.set_ylabel("Drawdown (%)")
    ax.grid(alpha=0.3)
    pdf.savefig(fig)
    plt.close(fig)


def _table_page(
    pdf: PdfPages, title: str, rows: List[Dict[str, Any]], notice: str | None = None
) -> None:
    fig, ax = plt.subplots(figsize=(8.5, 11))
    if notice:
        _stamp_synthetic(fig, notice)
    ax.axis("off")
    ax.set_title(title, fontsize=14, weight="bold", pad=20)
    if not rows:
        ax.text(0.5, 0.5, "No data.", ha="center")
    else:
        columns = list(rows[0].keys())
        cell_text = [[f"{row[c]:.2f}" if isinstance(row[c], float) else str(row[c]) for c in columns] for row in rows]
        table = ax.table(cellText=cell_text, colLabels=columns, loc="center", cellLoc="center")
        table.auto_set_font_size(False)
        table.set_fontsize(8)
        table.scale(1, 1.4)
    pdf.savefig(fig)
    plt.close(fig)


def generate_pdf_report(
    meta: Dict[str, Any],
    stats: Dict[str, Any],
    monthly_rows: List[Dict[str, Any]],
    weekly_rows: List[Dict[str, Any]],
    trades: Sequence[Dict[str, Any]],
    initial_capital: float,
    synthetic_notice: str | None = None,
) -> bytes:
    """Render the multi-page backtest PDF.

    `synthetic_notice`, when given, stamps every page with a header band and a diagonal
    watermark so an exported PDF cannot circulate as a genuine performance record.
    """
    buffer = io.BytesIO()
    with PdfPages(buffer) as pdf:
        _title_page(pdf, meta, stats, synthetic_notice)
        if trades:
            _equity_and_drawdown_pages(pdf, trades, initial_capital, synthetic_notice)
        _table_page(pdf, "Monthly Summary", monthly_rows, synthetic_notice)
        _table_page(pdf, "Weekly Summary (by day of week)", weekly_rows, synthetic_notice)
    buffer.seek(0)
    return buffer.read()
