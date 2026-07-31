from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

from trading_agent import STOP_LOSS_USD

TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"

WEEKDAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _parse_ts(value: str) -> Optional[datetime]:
    try:
        return datetime.strptime(value, TIMESTAMP_FORMAT)
    except (TypeError, ValueError):
        return None


def _duration_minutes(trade: Dict[str, Any]) -> Optional[float]:
    entry = _parse_ts(trade.get("entry_timestamp_ist", ""))
    exit_ = _parse_ts(trade.get("exit_timestamp_ist", ""))
    if entry is None or exit_ is None:
        return None
    return (exit_ - entry).total_seconds() / 60.0


def overall_stats(trades: Sequence[Dict[str, Any]], initial_capital: float) -> Dict[str, Any]:
    n = len(trades)
    empty = {
        "total_trades": 0, "winning_trades": 0, "losing_trades": 0,
        "win_rate_pct": 0.0, "loss_rate_pct": 0.0,
        "net_profit_usd": 0.0, "net_profit_pct": 0.0,
        "gross_profit": 0.0, "gross_loss": 0.0,
        "profit_factor": None, "expectancy": 0.0,
        "average_trade": 0.0, "average_win": 0.0, "average_loss": 0.0,
        "largest_win": 0.0, "largest_loss": 0.0,
        "max_drawdown_usd": 0.0, "max_drawdown_pct": 0.0,
        "max_consecutive_wins": 0, "max_consecutive_losses": 0,
        "avg_trade_duration_minutes": 0.0,
    }
    if n == 0:
        return empty

    pnls = [float(t["pnl_usd"]) for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    gross_profit = sum(wins)
    gross_loss = sum(losses)
    net_profit = sum(pnls)

    streak_type = None
    streak_len = 0
    max_win_streak = 0
    max_loss_streak = 0
    for p in pnls:
        kind = "win" if p > 0 else ("loss" if p < 0 else None)
        if kind == streak_type:
            streak_len += 1
        else:
            streak_type = kind
            streak_len = 1
        if kind == "win":
            max_win_streak = max(max_win_streak, streak_len)
        elif kind == "loss":
            max_loss_streak = max(max_loss_streak, streak_len)

    durations = [d for d in (_duration_minutes(t) for t in trades) if d is not None]

    running = float(initial_capital)
    peak = running
    max_dd_usd = 0.0
    max_dd_pct = 0.0
    for p in pnls:
        running += p
        peak = max(peak, running)
        dd = peak - running
        dd_pct = (dd / peak * 100.0) if peak > 0 else 0.0
        max_dd_usd = max(max_dd_usd, dd)
        max_dd_pct = max(max_dd_pct, dd_pct)

    return {
        "total_trades": n,
        "winning_trades": len(wins),
        "losing_trades": len(losses),
        "win_rate_pct": len(wins) / n * 100.0,
        "loss_rate_pct": len(losses) / n * 100.0,
        "net_profit_usd": net_profit,
        "net_profit_pct": (net_profit / initial_capital * 100.0) if initial_capital else 0.0,
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "profit_factor": (gross_profit / abs(gross_loss)) if gross_loss != 0 else None,
        "expectancy": net_profit / n,
        "average_trade": net_profit / n,
        "average_win": (gross_profit / len(wins)) if wins else 0.0,
        "average_loss": (gross_loss / len(losses)) if losses else 0.0,
        "largest_win": max(wins) if wins else 0.0,
        "largest_loss": min(losses) if losses else 0.0,
        "max_drawdown_usd": max_dd_usd,
        "max_drawdown_pct": max_dd_pct,
        "max_consecutive_wins": max_win_streak,
        "max_consecutive_losses": max_loss_streak,
        "avg_trade_duration_minutes": (sum(durations) / len(durations)) if durations else 0.0,
    }


def monthly_stats(trades: Sequence[Dict[str, Any]], initial_capital: float) -> List[Dict[str, Any]]:
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for t in trades:
        ts = _parse_ts(t.get("exit_timestamp_ist", ""))
        if ts is None:
            continue
        key = ts.strftime("%Y-%m")
        grouped.setdefault(key, []).append(t)

    rows = []
    for month in sorted(grouped):
        month_trades = grouped[month]
        pnls = [float(t["pnl_usd"]) for t in month_trades]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p < 0]
        net = sum(pnls)
        rows.append({
            "month": month,
            "total_trades": len(month_trades),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate_pct": (len(wins) / len(month_trades) * 100.0) if month_trades else 0.0,
            "net_profit_usd": net,
            "net_loss_usd": sum(losses),
            "monthly_return_pct": (net / initial_capital * 100.0) if initial_capital else 0.0,
        })
    return rows


def daily_stats(trades: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    grouped: Dict[str, List[float]] = {}
    for t in trades:
        ts = _parse_ts(t.get("exit_timestamp_ist", ""))
        if ts is None:
            continue
        key = ts.date().isoformat()
        grouped.setdefault(key, []).append(float(t["pnl_usd"]))

    rows = []
    for day in sorted(grouped):
        pnls = grouped[day]
        rows.append({
            "date": day,
            "total_trades": len(pnls),
            "net_profit_usd": sum(pnls),
        })
    return rows


def weekly_stats(trades: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Per-weekday breakdown across all seven days.

    Crypto perpetual futures trade 24/7, so Saturday and Sunday are real trading
    days here — restricting this to Mon-Fri would silently drop those trades from
    the totals (in the 1-year backtest that was 31 of 36 trades).
    """
    grouped: Dict[str, List[float]] = {name: [] for name in WEEKDAY_NAMES}
    for t in trades:
        ts = _parse_ts(t.get("entry_timestamp_ist", ""))
        if ts is None:
            continue
        grouped[WEEKDAY_NAMES[ts.weekday()]].append(float(t["pnl_usd"]))

    rows = []
    for name in WEEKDAY_NAMES:
        pnls = grouped[name]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p < 0]
        rows.append({
            "weekday": name,
            "total_trades": len(pnls),
            "win_rate_pct": (len(wins) / len(pnls) * 100.0) if pnls else 0.0,
            "net_profit_usd": sum(pnls),
            "average_win": (sum(wins) / len(wins)) if wins else 0.0,
            "average_loss": (sum(losses) / len(losses)) if losses else 0.0,
        })
    return rows


def strategy_insights(trades: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    if not trades:
        return {
            "best_day": None, "worst_day": None,
            "best_hour_ist": None, "worst_hour_ist": None,
            "most_profitable_direction": None, "least_profitable_direction": None,
            "avg_holding_time_minutes": 0.0,
            "most_common_exit_reason": None,
            "avg_risk_reward_achieved": 0.0,
        }

    by_day: Dict[str, float] = {}
    by_hour: Dict[int, float] = {}
    by_direction: Dict[str, float] = {}
    exit_reasons: Counter = Counter()
    durations = []
    rr_multiples = []

    for t in trades:
        pnl = float(t["pnl_usd"])
        entry_ts = _parse_ts(t.get("entry_timestamp_ist", ""))
        if entry_ts is not None:
            day_key = entry_ts.date().isoformat()
            by_day[day_key] = by_day.get(day_key, 0.0) + pnl
            by_hour[entry_ts.hour] = by_hour.get(entry_ts.hour, 0.0) + pnl
        side = t.get("side")
        if side:
            by_direction[side] = by_direction.get(side, 0.0) + pnl
        exit_reasons[t.get("exit_reason", "UNKNOWN")] += 1
        dur = _duration_minutes(t)
        if dur is not None:
            durations.append(dur)
        rr_multiples.append(pnl / STOP_LOSS_USD)

    best_day = max(by_day, key=by_day.get) if by_day else None
    worst_day = min(by_day, key=by_day.get) if by_day else None
    best_hour = max(by_hour, key=by_hour.get) if by_hour else None
    worst_hour = min(by_hour, key=by_hour.get) if by_hour else None
    best_dir = max(by_direction, key=by_direction.get) if by_direction else None
    worst_dir = min(by_direction, key=by_direction.get) if by_direction else None

    return {
        "best_day": {"date": best_day, "pnl_usd": by_day[best_day]} if best_day else None,
        "worst_day": {"date": worst_day, "pnl_usd": by_day[worst_day]} if worst_day else None,
        "best_hour_ist": {"hour": best_hour, "pnl_usd": by_hour[best_hour]} if best_hour is not None else None,
        "worst_hour_ist": {"hour": worst_hour, "pnl_usd": by_hour[worst_hour]} if worst_hour is not None else None,
        "most_profitable_direction": {"side": best_dir, "pnl_usd": by_direction[best_dir]} if best_dir else None,
        "least_profitable_direction": {"side": worst_dir, "pnl_usd": by_direction[worst_dir]} if worst_dir else None,
        "avg_holding_time_minutes": (sum(durations) / len(durations)) if durations else 0.0,
        "most_common_exit_reason": exit_reasons.most_common(1)[0][0] if exit_reasons else None,
        "avg_risk_reward_achieved": (sum(rr_multiples) / len(rr_multiples)) if rr_multiples else 0.0,
    }


def build_equity_curve_from_trades(
    trades: Sequence[Dict[str, Any]], initial_capital: float
) -> List[Dict[str, Any]]:
    """Per-trade cumulative equity curve — works for any backtest JSON, since not every
    output format (e.g. the data_pipeline CLI) records a full per-candle equity curve."""
    ordered = sorted(trades, key=lambda t: t.get("exit_timestamp_ist", ""))
    capital = float(initial_capital)
    rows = [{"timestamp_ist": None, "capital": capital}]
    for t in ordered:
        capital += float(t["pnl_usd"])
        rows.append({"timestamp_ist": t.get("exit_timestamp_ist"), "capital": capital})
    return rows


def equity_curve_rows(equity_curve: Sequence[Dict[str, Any]], max_points: int = 5000) -> List[Dict[str, Any]]:
    """Downsample the raw per-candle equity curve for charting."""
    if len(equity_curve) <= max_points:
        return list(equity_curve)
    step = max(1, len(equity_curve) // max_points)
    rows = list(equity_curve[::step])
    if rows[-1] is not equity_curve[-1]:
        rows.append(equity_curve[-1])
    return rows


def drawdown_series(equity_curve: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows = []
    peak = None
    for point in equity_curve:
        capital = float(point["capital"])
        peak = capital if peak is None else max(peak, capital)
        dd_pct = ((peak - capital) / peak * 100.0) if peak else 0.0
        rows.append({"timestamp_ist": point["timestamp_ist"], "drawdown_pct": dd_pct})
    return rows
