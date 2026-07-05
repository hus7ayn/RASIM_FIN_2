from __future__ import annotations

import argparse
import json
import os
from typing import Any, Dict

import ccxt

from trading_agent import LEVERAGE, STOP_LOSS_USD, TARGET_USD


def build_testnet_exchange(api_key: str, api_secret: str) -> ccxt.binanceusdm:
    """
    Create Binance USD-M futures client in sandbox mode.
    """
    exchange = ccxt.binanceusdm(
        {
            "apiKey": api_key,
            "secret": api_secret,
            "enableRateLimit": True,
            "options": {
                "defaultType": "future",
                # Avoid SAPI currency lookup path that often rejects demo futures keys.
                "fetchCurrencies": False,
            },
            "timeout": 30000,
            "urls": {
                "api": {
                    "fapiPublic": "https://demo-fapi.binance.com/fapi/v1",
                    "fapiPrivate": "https://demo-fapi.binance.com/fapi/v1",
                    "fapiPrivateV2": "https://demo-fapi.binance.com/fapi/v2",
                    "fapiPrivateV3": "https://demo-fapi.binance.com/fapi/v3",
                }
            },
        }
    )
    return exchange


def check_connectivity(exchange: ccxt.binanceusdm, symbol: str) -> Dict[str, Any]:
    """
    Minimal safe connectivity check for testnet.
    """
    markets = exchange.load_markets()
    if symbol not in markets:
        raise ValueError(f"Symbol not found in testnet markets: {symbol}")
    ticker = exchange.fetch_ticker(symbol)
    balance = exchange.fetch_balance()
    return {
        "symbol": symbol,
        "last_price": ticker.get("last"),
        "quote_volume": ticker.get("quoteVolume"),
        "usdt_total": (balance.get("USDT") or {}).get("total"),
        "usdt_free": (balance.get("USDT") or {}).get("free"),
    }


def create_test_order(
    exchange: ccxt.binanceusdm,
    symbol: str,
    side: str,
    amount: float,
    validate_only: bool = True,
) -> Dict[str, Any]:
    """
    Creates a tiny market order on Binance futures testnet.
    Intended only for sandbox validation.
    """
    side_lower = side.lower()
    if side_lower not in {"buy", "sell"}:
        raise ValueError("side must be BUY or SELL")
    if amount <= 0:
        raise ValueError("amount must be > 0")

    order = exchange.create_order(
        symbol=symbol,
        type="market",
        side=side_lower,
        amount=amount,
        params={"test": validate_only},
    )
    return order


def _pnl_usd_to_price_distance(usd_value: float, quantity: float, leverage: int) -> float:
    if quantity <= 0:
        raise ValueError("quantity must be > 0 for price distance conversion.")
    return usd_value / (quantity * leverage)


def _configure_symbol_risk(exchange: ccxt.binanceusdm, symbol: str) -> None:
    try:
        exchange.set_margin_mode("isolated", symbol)
    except Exception as exc:  # noqa: BLE001
        # Common on Binance when margin mode is already locked due to open positions.
        if "-4048" not in str(exc):
            raise
    try:
        exchange.set_leverage(LEVERAGE, symbol)
    except Exception as exc:  # noqa: BLE001
        # Ignore "already set" style cases and continue.
        if "leverage not modified" not in str(exc).lower():
            raise


def execute_strategy_decision(
    exchange: ccxt.binanceusdm,
    symbol: str,
    decision: Dict[str, Any],
    validate_only: bool = True,
) -> Dict[str, Any]:
    """
    Execute strategy decision on Binance futures testnet.
    - HOLD: no-op
    - BUY/SELL: market entry + attached reduce-only TP/SL
    """
    action = str(decision.get("action", "HOLD")).upper()
    if action == "HOLD":
        return {"status": "skipped", "reason": decision.get("reason", "HOLD")}

    if action not in {"BUY", "SELL"}:
        raise ValueError(f"Unsupported decision action: {action}")

    quantity = float(decision.get("quantity") or 0.0)
    entry_price = float(decision.get("entry_price") or 0.0)
    if quantity <= 0 or entry_price <= 0:
        raise ValueError("Decision must include positive quantity and entry_price.")

    _configure_symbol_risk(exchange=exchange, symbol=symbol)

    entry_side = "buy" if action == "BUY" else "sell"
    exit_side = "sell" if action == "BUY" else "buy"
    entry_order = exchange.create_order(
        symbol=symbol,
        type="market",
        side=entry_side,
        amount=quantity,
        params={"test": validate_only},
    )

    sl_dist = _pnl_usd_to_price_distance(STOP_LOSS_USD, quantity, LEVERAGE)
    tp_dist = _pnl_usd_to_price_distance(TARGET_USD, quantity, LEVERAGE)
    if action == "BUY":
        sl_price = max(0.0, entry_price - sl_dist)
        tp_price = entry_price + tp_dist
    else:
        sl_price = entry_price + sl_dist
        tp_price = max(0.0, entry_price - tp_dist)

    sl_order = exchange.create_order(
        symbol=symbol,
        type="STOP_MARKET",
        side=exit_side,
        amount=quantity,
        params={
            "stopPrice": sl_price,
            "reduceOnly": True,
            "workingType": "MARK_PRICE",
            "test": validate_only,
        },
    )
    tp_order = exchange.create_order(
        symbol=symbol,
        type="TAKE_PROFIT_MARKET",
        side=exit_side,
        amount=quantity,
        params={
            "stopPrice": tp_price,
            "reduceOnly": True,
            "workingType": "MARK_PRICE",
            "test": validate_only,
        },
    )
    return {
        "status": "submitted",
        "action": action,
        "entry_order_id": entry_order.get("id"),
        "sl_order_id": sl_order.get("id"),
        "tp_order_id": tp_order.get("id"),
        "quantity": quantity,
        "entry_price": entry_price,
        "sl_price": sl_price,
        "tp_price": tp_price,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Binance Futures testnet validator")
    parser.add_argument("--symbol", default="BTC/USDT:USDT", help="Futures market symbol")
    parser.add_argument("--side", default="BUY", help="BUY or SELL")
    parser.add_argument("--amount", type=float, default=0.001, help="Order amount")
    parser.add_argument(
        "--place-order",
        action="store_true",
        help="If provided, submit a TEST order (no fill) unless --live-order is set",
    )
    parser.add_argument(
        "--live-order",
        action="store_true",
        help="Submit real order on exchange account (unsafe, use cautiously)",
    )
    parser.add_argument(
        "--decision-json",
        default="",
        help="Path to strategy decision JSON. If provided, executes that decision.",
    )
    args = parser.parse_args()

    api_key = os.getenv("BINANCE_TESTNET_API_KEY", "").strip()
    api_secret = os.getenv("BINANCE_TESTNET_API_SECRET", "").strip()
    if not api_key or not api_secret:
        raise RuntimeError(
            "Missing BINANCE_TESTNET_API_KEY / BINANCE_TESTNET_API_SECRET in environment."
        )

    exchange = build_testnet_exchange(api_key=api_key, api_secret=api_secret)

    info = check_connectivity(exchange=exchange, symbol=args.symbol)
    print("Connectivity OK:", info)

    if args.decision_json:
        with open(args.decision_json, "r", encoding="utf-8") as f:
            decision = json.load(f)
        result = execute_strategy_decision(
            exchange=exchange,
            symbol=args.symbol,
            decision=decision,
            validate_only=not args.live_order,
        )
        print("Strategy execution result:", result)
    elif args.place_order:
        order = create_test_order(
            exchange=exchange,
            symbol=args.symbol,
            side=args.side,
            amount=args.amount,
            validate_only=not args.live_order,
        )
        print("Testnet order placed:", order.get("id"), order.get("status"))
    else:
        print("Order placement skipped. Use --place-order to test execution.")


if __name__ == "__main__":
    main()
