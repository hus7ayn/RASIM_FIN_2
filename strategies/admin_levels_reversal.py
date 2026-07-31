from __future__ import annotations

from typing import Optional, Sequence

from trading_agent import AdminLevelsConfig, DeterministicTradingAgent, _evaluate_exit_intrabar

from .registry import register_strategy


@register_strategy(
    "admin_levels_reversal",
    description=(
        "Deterministic RED/GREEN candle-reversal strategy against admin-projected "
        "(or manually-drawn) session key levels, EMA-7 confirmation, intrabar SL/target."
    ),
)
def create_admin_levels_reversal(
    key_levels: Optional[Sequence[float]] = None,
    admin_levels_config: Optional[AdminLevelsConfig] = None,
) -> DeterministicTradingAgent:
    return DeterministicTradingAgent(key_levels=key_levels, admin_levels_config=admin_levels_config)


# The exit-rule this strategy uses, exposed so the backtest engine / live runner can
# pass it explicitly via run_backtest(..., evaluate_exit=...) if ever running a mix
# of strategies that don't all share the same risk model.
evaluate_exit = _evaluate_exit_intrabar
