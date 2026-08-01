"""Live position operations: read the open position, amend TP/SL, book part of it.

Two things to understand before using this module.

**Nothing here places a filling order unless you pass `validate_only=False`.** The
default everywhere is validate-only, matching the rest of the codebase, which has never
submitted a live-filling order. Flipping that is a deliberate act.

**The strategy's current position sizing produces orders an exchange will reject.**
`calculate_quantity` returns 3.0 BTC for $10k of capital — roughly 29x leverage against
the configured 13x — and the resulting stop sits ~$2.56 from entry, far inside both the
spread and Binance's minimum stop distance. So `amend_tp_sl` and `book_partial` are
implemented and exercised against the log, but a live call will most likely be rejected
by the venue until sizing is fixed. `preflight_check` reports this explicitly rather
than letting it surface as an opaque exchange error.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from binance_testnet import build_testnet_exchange, execute_strategy_decision
from dashboard.trade_log import (
    append_open_trade,
    current_open_trade,
    record_partial_exit,
    record_tp_sl_change,
)
from trading_agent import (
    LEVERAGE,
    STOP_LOSS_USD,
    TARGET_USD,
    _threshold_exit_price,
    calculate_quantity,
    risk_budget_usd,
)

MAX_SANE_LEVERAGE = LEVERAGE  # configured ceiling; anything above is un-submittable


def credentials_present() -> bool:
    """True if usable credentials exist anywhere (session, st.secrets, or environment).

    Falls back to a bare environment check outside a Streamlit run, so this module stays
    importable and testable from a plain script.
    """
    try:
        from dashboard import credentials

        return credentials.present()
    except Exception:  # noqa: BLE001
        return bool(
            os.getenv("BINANCE_TESTNET_API_KEY", "").strip()
            and os.getenv("BINANCE_TESTNET_API_SECRET", "").strip()
        )


def _resolve_credentials() -> tuple[str, str]:
    try:
        from dashboard import credentials

        return credentials.resolve()
    except Exception:  # noqa: BLE001
        return (
            os.getenv("BINANCE_TESTNET_API_KEY", "").strip(),
            os.getenv("BINANCE_TESTNET_API_SECRET", "").strip(),
        )


def _exchange(api_key: str | None = None, api_secret: str | None = None):
    """Build a testnet client. Explicit credentials win; otherwise they are resolved.

    Every endpoint on this client points at Binance's demo futures host, so it cannot
    reach a mainnet account regardless of which key is supplied.
    """
    if api_key and api_secret:
        key, secret = api_key.strip(), api_secret.strip()
    else:
        key, secret = _resolve_credentials()
    if not key or not secret:
        raise RuntimeError(
            "No Binance testnet API credentials. Enter them in the dashboard's Exchange "
            "connection panel, set them in st.secrets, or export "
            "BINANCE_TESTNET_API_KEY / BINANCE_TESTNET_API_SECRET."
        )
    return build_testnet_exchange(api_key=key, api_secret=secret)


def test_connection(symbol: str, api_key: str | None = None, api_secret: str | None = None) -> Dict[str, Any]:
    """Read-only connectivity probe. Places no orders.

    Returns account and ticker facts so the operator can confirm the key works and is
    pointed at the demo account they expect.
    """
    exchange = _exchange(api_key, api_secret)
    markets = exchange.load_markets()
    if symbol not in markets:
        raise ValueError(f"Symbol not available on the testnet endpoint: {symbol}")
    ticker = exchange.fetch_ticker(symbol)
    balance = exchange.fetch_balance()
    usdt = balance.get("USDT") or {}
    positions = [p for p in exchange.fetch_positions([symbol]) if float(p.get("contracts") or 0)]
    return {
        "symbol": symbol,
        "last_price": ticker.get("last"),
        "usdt_total": usdt.get("total"),
        "usdt_free": usdt.get("free"),
        "open_positions": len(positions),
        "endpoint": "demo-fapi.binance.com",
    }


def fetch_live_position(symbol: str) -> Optional[Dict[str, Any]]:
    """Return the exchange's view of the open position, or None if flat.

    Read-only; safe to call without enabling live orders.
    """
    exchange = _exchange()
    positions = exchange.fetch_positions([symbol])
    for pos in positions:
        contracts = float(pos.get("contracts") or 0.0)
        if contracts == 0:
            continue
        return {
            "symbol": pos.get("symbol"),
            "side": (pos.get("side") or "").upper(),
            "quantity": contracts,
            "entry_price": float(pos.get("entryPrice") or 0.0),
            "mark_price": float(pos.get("markPrice") or 0.0),
            "unrealized_pnl": float(pos.get("unrealizedPnl") or 0.0),
            "leverage": float(pos.get("leverage") or 0.0),
            "liquidation_price": pos.get("liquidationPrice"),
        }
    return None


def compute_live_pnl(
    side: str, entry_price: float, current_price: float, quantity: float
) -> Dict[str, float]:
    """Unrealized P&L for an open position.

    Reported two ways on purpose. `pnl_usd` is textbook futures P&L
    (Δprice x quantity). `pnl_usd_engine_basis` additionally multiplies by leverage,
    which is what `trading_agent._calculate_pnl_usd` does and therefore what the
    strategy's $100/$450 thresholds are measured against. The two differ by 13x; the
    engine basis is the one that decides when a stop or target fires.
    """
    delta = current_price - entry_price
    if side.upper() in ("SELL", "SHORT"):
        delta = -delta
    notional = entry_price * quantity
    pnl = delta * quantity
    return {
        "price_delta": delta,
        "pnl_usd": pnl,
        "pnl_usd_engine_basis": pnl * LEVERAGE,
        "pnl_pct_of_notional": (pnl / notional * 100.0) if notional else 0.0,
        "notional": notional,
    }


def preflight_check(entry_price: float, quantity: float, capital: float) -> List[str]:
    """Warnings that would make a live order fail or behave unexpectedly."""
    problems: List[str] = []
    notional = entry_price * quantity
    if capital > 0:
        implied = notional / capital
        if implied > MAX_SANE_LEVERAGE:
            problems.append(
                f"Position notional ${notional:,.0f} on ${capital:,.0f} capital implies "
                f"{implied:.1f}x leverage, above the configured {MAX_SANE_LEVERAGE}x. "
                f"The exchange will reject this for insufficient margin."
            )
    if not credentials_present():
        problems.append(
            "BINANCE_TESTNET_API_KEY / _SECRET are not set, so live order calls cannot be made."
        )
    return problems


def open_demo_trade(
    symbol: str,
    side: str,
    capital: float,
    current_price: float,
    timestamp_ist: str,
    validate_only: bool = True,
    api_key: str | None = None,
    api_secret: str | None = None,
) -> Dict[str, Any]:
    """Open a position on the testnet with attached reduce-only stop and target.

    Sized by the strategy's own risk model, so what this demonstrates is the real
    sizing path rather than an arbitrary amount. With `validate_only=True` the order is
    sent with Binance's test flag and never fills; set it False to place a filling order
    against the demo account.

    Refuses to run while a trade is already open in the log, since the rest of the
    system assumes one position at a time.
    """
    side = side.upper()
    if side not in ("BUY", "SELL"):
        raise ValueError("side must be BUY or SELL.")
    if current_matched := current_open_trade():
        raise ValueError(
            f"Trade #{current_matched['trade_number']} is still open — close or book it "
            "out before opening another."
        )

    quantity = calculate_quantity(capital, current_price)
    risk_usd = risk_budget_usd(capital)
    reward_multiple = TARGET_USD / STOP_LOSS_USD if STOP_LOSS_USD else 1.0
    stop_price = _threshold_exit_price(side, current_price, quantity, pnl_usd=-risk_usd)
    target_price = _threshold_exit_price(
        side, current_price, quantity, pnl_usd=risk_usd * reward_multiple
    )

    result: Dict[str, Any] = {
        "symbol": symbol,
        "side": side,
        "quantity": quantity,
        "entry_price": current_price,
        "notional_usd": current_price * quantity,
        "implied_leverage": (current_price * quantity) / capital if capital else None,
        "risk_usd": risk_usd,
        "stop_price": stop_price,
        "target_price": target_price,
        "validate_only": validate_only,
        "placed_orders": [],
        "warnings": preflight_check(current_price, quantity, capital),
    }

    exchange = _exchange(api_key, api_secret)
    decision = {
        "action": side,
        "entry_price": current_price,
        "quantity": quantity,
        "timestamp_ist": timestamp_ist,
        "stop_price": stop_price,
        "target_price": target_price,
    }
    execution = execute_strategy_decision(
        exchange=exchange, symbol=symbol, decision=decision, validate_only=validate_only
    )
    result["execution"] = execution
    result["placed_orders"] = [
        {"role": role, "id": execution.get(f"{role}_order_id")}
        for role in ("entry", "sl", "tp")
        if execution.get(f"{role}_order_id")
    ]

    # Record it so the position panel, trade history and analysis all see it.
    trade_number = append_open_trade(decision, symbol=symbol)
    result["trade_number"] = trade_number
    return result


def _cancel_reduce_only_orders(exchange, symbol: str) -> List[str]:
    """Cancel existing stop/target orders so they can be replaced at new levels.

    Binance rejects a second reduce-only stop at a different trigger while the first is
    live, so amending means cancel-then-place rather than an in-place edit.
    """
    cancelled: List[str] = []
    for order in exchange.fetch_open_orders(symbol):
        otype = str(order.get("type") or "").upper()
        if "STOP" in otype or "TAKE_PROFIT" in otype:
            exchange.cancel_order(order["id"], symbol)
            cancelled.append(order["id"])
    return cancelled


def amend_tp_sl(
    symbol: str,
    new_target: Optional[float],
    new_stop: Optional[float],
    timestamp_ist: str,
    validate_only: bool = True,
) -> Dict[str, Any]:
    """Move the take-profit and/or stop-loss on the open position.

    The log is updated regardless so the audit trail records the operator's intent;
    `exchange_applied` reports whether the venue actually received new orders.
    """
    trade = current_open_trade()
    if trade is None:
        raise ValueError("No open trade to modify.")

    updated = record_tp_sl_change(
        timestamp_ist=timestamp_ist, new_target=new_target, new_stop=new_stop
    )

    result: Dict[str, Any] = {
        "trade_number": updated["trade_number"],
        "target_price": updated["target_price"],
        "stop_loss_price": updated["stop_loss_price"],
        "modifications": len(updated["tp_sl_modifications"]),
        "exchange_applied": False,
        "cancelled_orders": [],
        "placed_orders": [],
    }

    if validate_only:
        result["note"] = "validate_only=True — log updated, no exchange orders changed."
        return result

    exchange = _exchange()
    quantity = float(updated["remaining_quantity"] or 0.0)
    if quantity <= 0:
        raise ValueError("Open trade has no remaining quantity.")
    exit_side = "sell" if updated["side"] == "BUY" else "buy"

    result["cancelled_orders"] = _cancel_reduce_only_orders(exchange, symbol)
    for otype, price in (
        ("STOP_MARKET", updated["stop_loss_price"]),
        ("TAKE_PROFIT_MARKET", updated["target_price"]),
    ):
        if price is None:
            continue
        order = exchange.create_order(
            symbol=symbol,
            type=otype,
            side=exit_side,
            amount=quantity,
            params={
                "stopPrice": float(price),
                "reduceOnly": True,
                "workingType": "MARK_PRICE",
            },
        )
        result["placed_orders"].append({"type": otype, "id": order.get("id"), "stopPrice": price})
    result["exchange_applied"] = True
    return result


def book_partial(
    symbol: str,
    fraction: Optional[float],
    quantity: Optional[float],
    current_price: float,
    timestamp_ist: str,
    validate_only: bool = True,
) -> Dict[str, Any]:
    """Close part of the open position, leaving the remainder running.

    Pass either `fraction` (0-1 of the remaining size) or an absolute `quantity`.
    After booking, the reduce-only TP/SL are re-placed at the reduced size — otherwise
    the leftover stop would still be sized for the original position and would flip it
    short on trigger.
    """
    trade = current_open_trade()
    if trade is None:
        raise ValueError("No open trade to book against.")

    remaining = float(trade["remaining_quantity"] or 0.0)
    if quantity is None:
        if fraction is None:
            raise ValueError("Provide either fraction or quantity.")
        if not 0 < fraction <= 1:
            raise ValueError("fraction must be between 0 and 1.")
        quantity = remaining * fraction
    quantity = float(quantity)

    result: Dict[str, Any] = {
        "requested_quantity": quantity,
        "remaining_before": remaining,
        "exchange_applied": False,
        "placed_orders": [],
        "cancelled_orders": [],
    }

    if not validate_only:
        exchange = _exchange()
        close_side = "sell" if trade["side"] == "BUY" else "buy"
        order = exchange.create_order(
            symbol=symbol,
            type="market",
            side=close_side,
            amount=quantity,
            params={"reduceOnly": True},
        )
        result["placed_orders"].append({"type": "MARKET_REDUCE_ONLY", "id": order.get("id")})
        result["exchange_applied"] = True

    # Record the booked leg; this validates the quantity and updates remaining size.
    updated = record_partial_exit(
        quantity=quantity,
        exit_price=current_price,
        timestamp_ist=timestamp_ist,
        reason="PARTIAL_BOOK",
    )

    result["trade_number"] = updated["trade_number"]
    result["remaining_after"] = updated["remaining_quantity"]
    result["status"] = updated["status"]
    result["leg_pnl_usd"] = updated["partial_exits"][-1]["pnl_usd"]
    result["realized_pnl_usd"] = updated["realized_pnl_usd"]

    if not validate_only and updated["remaining_quantity"] > 0:
        exchange = _exchange()
        result["cancelled_orders"] = _cancel_reduce_only_orders(exchange, symbol)
        exit_side = "sell" if updated["side"] == "BUY" else "buy"
        for otype, price in (
            ("STOP_MARKET", updated["stop_loss_price"]),
            ("TAKE_PROFIT_MARKET", updated["target_price"]),
        ):
            if price is None:
                continue
            o = exchange.create_order(
                symbol=symbol,
                type=otype,
                side=exit_side,
                amount=updated["remaining_quantity"],
                params={
                    "stopPrice": float(price),
                    "reduceOnly": True,
                    "workingType": "MARK_PRICE",
                },
            )
            result["placed_orders"].append({"type": otype, "id": o.get("id"), "stopPrice": price})
    elif validate_only:
        result["note"] = "validate_only=True — log updated, no exchange orders placed."

    return result
