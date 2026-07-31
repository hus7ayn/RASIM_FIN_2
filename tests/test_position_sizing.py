"""Tests for position sizing, P&L, and fees.

These pin the corrected risk model. The previous implementation sized positions as
`(3% x capital) / STOP_LOSS_USD`, which divides dollars by dollars and treats the result
as a quantity — 3.0 BTC on $10k of capital, roughly 29x leverage against a configured
13x — and computed P&L as `Δprice x quantity x LEVERAGE`, overstating every result
13-fold.
"""

import pytest

from trading_agent import (
    Action,
    LEVERAGE,
    RISK_FRACTION,
    STOP_DISTANCE_PCT,
    STOP_LOSS_USD,
    TAKER_FEE_RATE,
    TARGET_USD,
    _calculate_pnl_usd,
    _threshold_exit_price,
    calculate_quantity,
    entry_exit_fees_usd,
    risk_budget_usd,
    stop_distance,
)


def test_pnl_does_not_scale_with_leverage():
    """P&L is Δprice x quantity. Leverage funds the position; it does not multiply gains."""
    pnl = _calculate_pnl_usd(Action.BUY.value, 60_000.0, 60_012.0, 3.0)
    assert pnl == pytest.approx(36.0)  # not 36 * 13 = 468
    # The ignored `leverage` argument must not change the answer.
    assert _calculate_pnl_usd(Action.BUY.value, 60_000.0, 60_012.0, 3.0, LEVERAGE) == pytest.approx(36.0)


def test_pnl_sign_flips_for_sell():
    assert _calculate_pnl_usd(Action.SELL.value, 60_000.0, 59_900.0, 2.0) == pytest.approx(200.0)
    assert _calculate_pnl_usd(Action.SELL.value, 60_000.0, 60_100.0, 2.0) == pytest.approx(-200.0)


def test_stop_distance_is_a_fixed_fraction_of_price():
    assert stop_distance(86_492.0) == pytest.approx(86_492.0 * STOP_DISTANCE_PCT)
    # Scale-invariant: the same percentage at any price level.
    assert stop_distance(10_000.0) / 10_000.0 == pytest.approx(stop_distance(90_000.0) / 90_000.0)


def test_risk_budget_is_capped_by_fraction_of_capital():
    # Ample capital: the fixed dollar stop applies.
    assert risk_budget_usd(10_000.0) == pytest.approx(STOP_LOSS_USD)
    # Thin capital: the percentage cap binds instead, so the account is not over-risked.
    assert risk_budget_usd(1_000.0) == pytest.approx(RISK_FRACTION * 1_000.0)
    assert risk_budget_usd(500.0) == pytest.approx(RISK_FRACTION * 500.0)


@pytest.mark.parametrize("capital,price", [(10_000.0, 86_492.0), (10_000.0, 118_000.0), (25_000.0, 64_000.0)])
def test_stop_costs_exactly_the_risk_budget(capital, price):
    qty = calculate_quantity(capital, price)
    sl = _threshold_exit_price(Action.BUY.value, price, qty, pnl_usd=-risk_budget_usd(capital))
    assert _calculate_pnl_usd(Action.BUY.value, price, sl, qty) == pytest.approx(
        -risk_budget_usd(capital)
    )
    # And the stop sits at the intended distance, not somewhere derived from the quantity.
    assert (price - sl) / price == pytest.approx(STOP_DISTANCE_PCT)


def test_notional_never_exceeds_configured_leverage():
    """The old formula produced ~29x on $10k. Sizing is now clamped to LEVERAGE x capital."""
    for capital, price in [(10_000.0, 86_492.0), (1_000.0, 86_492.0), (100.0, 86_492.0)]:
        qty = calculate_quantity(capital, price)
        assert qty * price <= LEVERAGE * capital + 1e-6


def test_notional_stays_within_leverage_by_construction():
    """With these parameters the leverage clamp is a backstop that never has to fire.

    notional = (risk / stop_distance) x price = risk / STOP_DISTANCE_PCT, so it is
    400 x risk. Since risk is capped at RISK_FRACTION x capital, notional is at most
    0.03 x 400 = 12x capital, already inside the 13x ceiling. Asserted so that changing
    STOP_DISTANCE_PCT or RISK_FRACTION into a combination that breaches leverage fails
    here rather than at the exchange.
    """
    implied_max = RISK_FRACTION / STOP_DISTANCE_PCT
    assert implied_max <= LEVERAGE, (
        f"RISK_FRACTION/STOP_DISTANCE_PCT = {implied_max:.1f}x exceeds {LEVERAGE}x leverage"
    )
    for capital in (100.0, 1_000.0, 3_200.0, 10_000.0, 50_000.0):
        qty = calculate_quantity(capital, 86_492.0)
        assert (qty * 86_492.0) / capital <= LEVERAGE + 1e-9


def test_leverage_clamp_fires_when_stop_is_too_tight(monkeypatch):
    """If the stop distance is set very tight, sizing would blow past leverage — clamp it."""
    import trading_agent

    monkeypatch.setattr(trading_agent, "STOP_DISTANCE_PCT", 0.00002)
    capital, price = 10_000.0, 86_492.0
    qty = trading_agent.calculate_quantity(capital, price)
    assert qty * price == pytest.approx(LEVERAGE * capital)


def test_reward_to_risk_ratio_is_preserved():
    capital, price = 10_000.0, 86_492.0
    qty = calculate_quantity(capital, price)
    risk = risk_budget_usd(capital)
    sl = _threshold_exit_price(Action.BUY.value, price, qty, pnl_usd=-risk)
    tp = _threshold_exit_price(
        Action.BUY.value, price, qty, pnl_usd=risk * (TARGET_USD / STOP_LOSS_USD)
    )
    assert (tp - price) / (price - sl) == pytest.approx(TARGET_USD / STOP_LOSS_USD)


def test_fees_are_charged_on_both_sides_of_notional():
    fees = entry_exit_fees_usd(60_000.0, 60_500.0, 0.5, fee_rate=0.0005)
    assert fees == pytest.approx((60_000.0 + 60_500.0) * 0.5 * 0.0005)
    assert entry_exit_fees_usd(60_000.0, 60_500.0, 0.5, fee_rate=0.0) == 0.0


def test_fees_are_material_relative_to_the_risk_budget():
    """Sanity check that the fee model is on a plausible scale rather than negligible."""
    capital, price = 10_000.0, 86_492.0
    qty = calculate_quantity(capital, price)
    fees = entry_exit_fees_usd(price, price, qty, TAKER_FEE_RATE)
    # Round-trip cost lands in the tens of dollars against a $100 risk budget — meaningful,
    # not the order-of-magnitude-larger figure the old 29x sizing produced.
    assert 10.0 < fees < risk_budget_usd(capital)


def test_calculate_quantity_rejects_bad_inputs():
    with pytest.raises(ValueError):
        calculate_quantity(0.0, 86_492.0)
    with pytest.raises(ValueError):
        calculate_quantity(10_000.0, 0.0)


def test_threshold_price_rejects_zero_quantity():
    with pytest.raises(ValueError):
        _threshold_exit_price(Action.BUY.value, 100.0, 0.0, pnl_usd=-100.0)
