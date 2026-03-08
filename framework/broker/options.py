"""
framework/broker/options.py

Paper-safe option order mapping for IBKR.

This module builds IBKR contract/order objects but does NOT submit them.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

from ib_insync import LimitOrder, MarketOrder, Option

from ..derivatives_strategies import OptionStrategyPosition

Action = Literal["BUY", "SELL"]
OrderType = Literal["MKT", "LMT"]


@dataclass(frozen=True)
class OptionOrderIntent:
    symbol: str
    expiry: date
    strike: float
    right: Literal["C", "P"]
    action: Action
    quantity: int
    order_type: OrderType = "LMT"
    limit_price: float | None = None
    exchange: str = "SMART"
    currency: str = "USD"


def option_contract_from_intent(intent: OptionOrderIntent):
    """Map OptionOrderIntent to ib_insync.Option contract."""
    return Option(
        symbol=intent.symbol,
        lastTradeDateOrContractMonth=intent.expiry.strftime("%Y%m%d"),
        strike=float(intent.strike),
        right=str(intent.right),
        exchange=intent.exchange,
        currency=intent.currency,
    )


def option_order_from_intent(intent: OptionOrderIntent):
    """Map OptionOrderIntent to ib_insync order object (not submitted)."""
    if intent.quantity <= 0:
        raise ValueError(f"quantity must be > 0, got {intent.quantity}")

    if intent.order_type == "MKT":
        return MarketOrder(intent.action, intent.quantity)

    if intent.limit_price is None or intent.limit_price <= 0:
        raise ValueError("limit_price must be provided and > 0 for LMT orders")
    return LimitOrder(intent.action, intent.quantity, float(intent.limit_price))


def strategy_position_to_option_intents(
    position: OptionStrategyPosition,
    action: Literal["open", "close"] = "open",
    contracts_scale: int = 1,
    order_type: OrderType = "LMT",
    limit_price: float | None = None,
) -> list[OptionOrderIntent]:
    """
    Convert strategy option legs into executable intents.

    `action="open"` uses leg quantity sign as-is.
    `action="close"` flips side to flatten existing leg exposure.
    """
    if contracts_scale <= 0:
        raise ValueError(f"contracts_scale must be > 0, got {contracts_scale}")

    intents: list[OptionOrderIntent] = []

    for leg in position.option_legs:
        qty_signed = int(leg.quantity) * int(contracts_scale)
        if qty_signed == 0:
            continue

        if action == "close":
            qty_signed = -qty_signed

        side: Action = "BUY" if qty_signed > 0 else "SELL"
        qty = abs(qty_signed)
        right = "C" if leg.contract.option_type.lower() == "call" else "P"

        intents.append(
            OptionOrderIntent(
                symbol=leg.contract.symbol,
                expiry=leg.contract.expiry,
                strike=float(leg.contract.strike),
                right=right,
                action=side,
                quantity=qty,
                order_type=order_type,
                limit_price=limit_price,
            )
        )

    return intents


def preview_option_orders(intents: list[OptionOrderIntent]) -> list[dict]:
    """Human-readable preview payload (safe for dry-run logging/UI)."""
    out = []
    for i in intents:
        out.append(
            {
                "symbol": i.symbol,
                "expiry": i.expiry.isoformat(),
                "strike": i.strike,
                "right": i.right,
                "action": i.action,
                "quantity": i.quantity,
                "order_type": i.order_type,
                "limit_price": i.limit_price,
                "exchange": i.exchange,
                "currency": i.currency,
            }
        )
    return out
