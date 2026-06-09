"""
Alpaca paper trading integration — thin wrapper around alpaca-py SDK.

All functions accept (key, secret) as explicit parameters so credentials
are never stored server-side. The frontend passes them per-request via
X-APCA-Key / X-APCA-Secret headers.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, List

from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, TimeInForce, AssetClass, OrderClass
from alpaca.trading.requests import (
    GetOrdersRequest,
    LimitOrderRequest,
    OptionLegRequest,
)


PAPER_URL = "https://paper-api.alpaca.markets"


def get_client(key: str, secret: str) -> TradingClient:
    """Return an Alpaca paper trading client."""
    return TradingClient(key, secret, paper=True)


def get_account(key: str, secret: str) -> Dict[str, Any]:
    """Return account summary: cash, buying_power, equity, portfolio_value."""
    client = get_client(key, secret)
    acct = client.get_account()
    return {
        "cash": float(acct.cash),
        "buying_power": float(acct.buying_power),
        "equity": float(acct.equity),
        "portfolio_value": float(acct.portfolio_value),
        "currency": acct.currency,
        "status": str(acct.status),
        "pattern_day_trader": acct.pattern_day_trader,
    }


def get_positions(key: str, secret: str) -> List[Dict[str, Any]]:
    """Return all open positions."""
    client = get_client(key, secret)
    positions = client.get_all_positions()
    result = []
    for p in positions:
        result.append({
            "symbol": p.symbol,
            "qty": float(p.qty),
            "side": str(p.side),
            "avg_entry_price": float(p.avg_entry_price),
            "current_price": float(p.current_price) if p.current_price else None,
            "market_value": float(p.market_value) if p.market_value else None,
            "unrealized_pl": float(p.unrealized_pl) if p.unrealized_pl else None,
            "unrealized_plpc": float(p.unrealized_plpc) if p.unrealized_plpc else None,
            "asset_class": str(p.asset_class),
        })
    return result


def get_orders(key: str, secret: str, limit: int = 20) -> List[Dict[str, Any]]:
    """Return recent orders (up to `limit`)."""
    client = get_client(key, secret)
    req = GetOrdersRequest(limit=limit)
    orders = client.get_orders(filter=req)
    result = []
    for o in orders:
        result.append({
            "id": str(o.id),
            "symbol": o.symbol,
            "side": str(o.side),
            "qty": float(o.qty) if o.qty else None,
            "type": str(o.type),
            "status": str(o.status),
            "limit_price": float(o.limit_price) if o.limit_price else None,
            "filled_avg_price": float(o.filled_avg_price) if o.filled_avg_price else None,
            "filled_at": o.filled_at.isoformat() if o.filled_at else None,
            "created_at": o.created_at.isoformat() if o.created_at else None,
            "asset_class": str(o.asset_class),
        })
    return result


def place_csp_order(
    key: str,
    secret: str,
    symbol: str,
    expiration: str,
    strike: float,
    limit_price: float,
    qty: int = 1,
) -> Dict[str, Any]:
    """
    Submit a cash-secured put (sell-to-open) limit order.

    Parameters
    ----------
    symbol      : underlying ticker, e.g. "AAPL"
    expiration  : ISO date string "YYYY-MM-DD"
    strike      : strike price as float, e.g. 280.0
    limit_price : limit price per share (mid-price), e.g. 2.50
    qty         : number of contracts (default 1)

    Returns dict with order id and status on success.
    Raises on API or validation error.
    """
    client = get_client(key, secret)

    # Build the OCC-style option symbol: e.g. AAPL260815P00280000
    exp = date.fromisoformat(expiration)
    exp_str = exp.strftime("%y%m%d")                          # "260815"
    strike_int = int(round(strike * 1000))                    # 280.0 → 280000
    option_symbol = f"{symbol}{exp_str}P{strike_int:08d}"    # "AAPL260815P00280000"

    order_req = LimitOrderRequest(
        symbol=option_symbol,
        qty=qty,
        side=OrderSide.SELL,
        type="limit",
        time_in_force=TimeInForce.DAY,
        limit_price=round(limit_price, 2),
    )

    order = client.submit_order(order_req)

    return {
        "id": str(order.id),
        "symbol": order.symbol,
        "status": str(order.status),
        "side": str(order.side),
        "qty": float(order.qty) if order.qty else qty,
        "limit_price": float(order.limit_price) if order.limit_price else limit_price,
        "created_at": order.created_at.isoformat() if order.created_at else None,
    }
