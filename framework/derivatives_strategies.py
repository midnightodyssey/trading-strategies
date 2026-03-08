"""
framework/derivatives_strategies.py

Options strategy primitives built on top of derivatives pricing.

Phase 2 scope:
- OptionLeg and OptionStrategyPosition dataclasses
- Strategy builders: covered call, protective put, bull call spread
- Mark-to-market helpers and expiry payoff calculator
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Iterable

from .derivatives import OptionContract, black_scholes_price, year_fraction_to_expiry


@dataclass(frozen=True)
class OptionLeg:
    """One option leg in a multi-leg structure."""

    contract: OptionContract
    quantity: int


@dataclass(frozen=True)
class OptionStrategyPosition:
    """Position container for underlying + options legs."""

    name: str
    symbol: str
    underlying_shares: float = 0.0
    option_legs: tuple[OptionLeg, ...] = field(default_factory=tuple)


def covered_call(
    symbol: str,
    strike: float,
    expiry: date,
    shares: int = 100,
    contracts: int = 1,
) -> OptionStrategyPosition:
    """Long stock + short call(s)."""
    call = OptionContract(symbol=symbol, option_type="call", strike=strike, expiry=expiry)
    return OptionStrategyPosition(
        name="CoveredCall",
        symbol=symbol,
        underlying_shares=float(shares),
        option_legs=(OptionLeg(contract=call, quantity=-int(contracts)),),
    )


def protective_put(
    symbol: str,
    strike: float,
    expiry: date,
    shares: int = 100,
    contracts: int = 1,
) -> OptionStrategyPosition:
    """Long stock + long put(s)."""
    put = OptionContract(symbol=symbol, option_type="put", strike=strike, expiry=expiry)
    return OptionStrategyPosition(
        name="ProtectivePut",
        symbol=symbol,
        underlying_shares=float(shares),
        option_legs=(OptionLeg(contract=put, quantity=int(contracts)),),
    )


def bull_call_spread(
    symbol: str,
    long_strike: float,
    short_strike: float,
    expiry: date,
    contracts: int = 1,
) -> OptionStrategyPosition:
    """Long lower-strike call + short higher-strike call."""
    if short_strike <= long_strike:
        raise ValueError(
            f"short_strike must be > long_strike for bull call spread, got {short_strike} <= {long_strike}"
        )

    c_long = OptionContract(symbol=symbol, option_type="call", strike=long_strike, expiry=expiry)
    c_short = OptionContract(symbol=symbol, option_type="call", strike=short_strike, expiry=expiry)

    return OptionStrategyPosition(
        name="BullCallSpread",
        symbol=symbol,
        underlying_shares=0.0,
        option_legs=(
            OptionLeg(contract=c_long, quantity=int(contracts)),
            OptionLeg(contract=c_short, quantity=-int(contracts)),
        ),
    )


def option_leg_value(
    leg: OptionLeg,
    spot: float,
    as_of: date,
    volatility: float,
    risk_free_rate: float,
    dividend_yield: float = 0.0,
) -> float:
    """Mark-to-market value of one option leg at a given date."""
    t = year_fraction_to_expiry(leg.contract.expiry, as_of=as_of)
    px = black_scholes_price(
        spot=spot,
        strike=leg.contract.strike,
        time_to_expiry_years=t,
        risk_free_rate=risk_free_rate,
        volatility=volatility,
        option_type=leg.contract.option_type,
        dividend_yield=dividend_yield,
    )
    return float(leg.quantity) * float(leg.contract.multiplier) * px


def strategy_mark_to_market(
    position: OptionStrategyPosition,
    spot: float,
    as_of: date,
    volatility: float,
    risk_free_rate: float,
    dividend_yield: float = 0.0,
) -> float:
    """Total MTM value: stock leg + all option legs."""
    stock_value = position.underlying_shares * float(spot)
    options_value = sum(
        option_leg_value(
            leg=leg,
            spot=spot,
            as_of=as_of,
            volatility=volatility,
            risk_free_rate=risk_free_rate,
            dividend_yield=dividend_yield,
        )
        for leg in position.option_legs
    )
    return float(stock_value + options_value)


def strategy_payoff_at_expiry(position: OptionStrategyPosition, terminal_spot: float) -> float:
    """Expiry payoff (intrinsic only) for full structure."""
    stock_payoff = position.underlying_shares * float(terminal_spot)

    option_payoff = 0.0
    for leg in position.option_legs:
        c = leg.contract
        if c.option_type == "call":
            intrinsic = max(float(terminal_spot) - c.strike, 0.0)
        else:
            intrinsic = max(c.strike - float(terminal_spot), 0.0)
        option_payoff += float(leg.quantity) * float(c.multiplier) * intrinsic

    return float(stock_payoff + option_payoff)


def iter_strikes(position: OptionStrategyPosition) -> Iterable[float]:
    """Convenience helper for diagnostics/visualizations."""
    return (leg.contract.strike for leg in position.option_legs)
