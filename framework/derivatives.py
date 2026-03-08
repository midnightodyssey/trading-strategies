"""
framework/derivatives.py

Core derivatives analytics for option pricing and risk.

Phase 1 scope:
- OptionContract dataclass
- Black-Scholes price (call/put)
- Closed-form Greeks (delta, gamma, vega, theta, rho)
- Implied volatility via bisection
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from math import erf, exp, log, pi, sqrt
from typing import Literal

OptionType = Literal["call", "put"]


@dataclass(frozen=True)
class OptionContract:
    """Simple option contract descriptor."""

    symbol: str
    option_type: OptionType
    strike: float
    expiry: date
    multiplier: int = 100


@dataclass(frozen=True)
class Greeks:
    """Option sensitivity bundle (per 1 contract unit)."""

    delta: float
    gamma: float
    vega: float
    theta: float
    rho: float


def _norm_pdf(x: float) -> float:
    return exp(-0.5 * x * x) / sqrt(2.0 * pi)


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + erf(x / sqrt(2.0)))


def _validate_inputs(
    spot: float,
    strike: float,
    time_to_expiry_years: float,
    volatility: float,
    option_type: OptionType,
) -> None:
    if spot <= 0:
        raise ValueError(f"spot must be > 0, got {spot}")
    if strike <= 0:
        raise ValueError(f"strike must be > 0, got {strike}")
    if time_to_expiry_years < 0:
        raise ValueError(f"time_to_expiry_years must be >= 0, got {time_to_expiry_years}")
    if volatility < 0:
        raise ValueError(f"volatility must be >= 0, got {volatility}")
    if option_type not in ("call", "put"):
        raise ValueError(f"option_type must be 'call' or 'put', got {option_type}")


def year_fraction_to_expiry(expiry: date, as_of: date | None = None, day_count: int = 365) -> float:
    """Convert expiry date into year fraction using ACT/day_count convention."""
    if as_of is None:
        as_of = datetime.utcnow().date()
    days = (expiry - as_of).days
    return max(0.0, days / float(day_count))


def _intrinsic_value(spot: float, strike: float, option_type: OptionType) -> float:
    if option_type == "call":
        return max(spot - strike, 0.0)
    return max(strike - spot, 0.0)


def _d1_d2(
    spot: float,
    strike: float,
    time_to_expiry_years: float,
    risk_free_rate: float,
    volatility: float,
    dividend_yield: float,
) -> tuple[float, float]:
    vt = volatility * sqrt(time_to_expiry_years)
    d1 = (
        log(spot / strike)
        + (risk_free_rate - dividend_yield + 0.5 * volatility * volatility) * time_to_expiry_years
    ) / vt
    d2 = d1 - vt
    return d1, d2


def black_scholes_price(
    spot: float,
    strike: float,
    time_to_expiry_years: float,
    risk_free_rate: float,
    volatility: float,
    option_type: OptionType,
    dividend_yield: float = 0.0,
) -> float:
    """Black-Scholes-Merton option price for European call/put."""
    _validate_inputs(spot, strike, time_to_expiry_years, volatility, option_type)

    if time_to_expiry_years == 0.0 or volatility == 0.0:
        return _intrinsic_value(spot, strike, option_type)

    d1, d2 = _d1_d2(spot, strike, time_to_expiry_years, risk_free_rate, volatility, dividend_yield)

    disc_q = exp(-dividend_yield * time_to_expiry_years)
    disc_r = exp(-risk_free_rate * time_to_expiry_years)

    if option_type == "call":
        return spot * disc_q * _norm_cdf(d1) - strike * disc_r * _norm_cdf(d2)
    return strike * disc_r * _norm_cdf(-d2) - spot * disc_q * _norm_cdf(-d1)


def black_scholes_greeks(
    spot: float,
    strike: float,
    time_to_expiry_years: float,
    risk_free_rate: float,
    volatility: float,
    option_type: OptionType,
    dividend_yield: float = 0.0,
) -> Greeks:
    """Closed-form Black-Scholes Greeks (annual theta, vega/rho per 1.00 move)."""
    _validate_inputs(spot, strike, time_to_expiry_years, volatility, option_type)

    if time_to_expiry_years == 0.0 or volatility == 0.0:
        return Greeks(delta=0.0, gamma=0.0, vega=0.0, theta=0.0, rho=0.0)

    d1, d2 = _d1_d2(spot, strike, time_to_expiry_years, risk_free_rate, volatility, dividend_yield)
    disc_q = exp(-dividend_yield * time_to_expiry_years)
    disc_r = exp(-risk_free_rate * time_to_expiry_years)

    pdf_d1 = _norm_pdf(d1)

    gamma = disc_q * pdf_d1 / (spot * volatility * sqrt(time_to_expiry_years))
    vega = spot * disc_q * pdf_d1 * sqrt(time_to_expiry_years)

    if option_type == "call":
        delta = disc_q * _norm_cdf(d1)
        theta = (
            -(spot * disc_q * pdf_d1 * volatility) / (2.0 * sqrt(time_to_expiry_years))
            - risk_free_rate * strike * disc_r * _norm_cdf(d2)
            + dividend_yield * spot * disc_q * _norm_cdf(d1)
        )
        rho = strike * time_to_expiry_years * disc_r * _norm_cdf(d2)
    else:
        delta = disc_q * (_norm_cdf(d1) - 1.0)
        theta = (
            -(spot * disc_q * pdf_d1 * volatility) / (2.0 * sqrt(time_to_expiry_years))
            + risk_free_rate * strike * disc_r * _norm_cdf(-d2)
            - dividend_yield * spot * disc_q * _norm_cdf(-d1)
        )
        rho = -strike * time_to_expiry_years * disc_r * _norm_cdf(-d2)

    return Greeks(delta=delta, gamma=gamma, vega=vega, theta=theta, rho=rho)


def implied_volatility(
    market_price: float,
    spot: float,
    strike: float,
    time_to_expiry_years: float,
    risk_free_rate: float,
    option_type: OptionType,
    dividend_yield: float = 0.0,
    low: float = 1e-6,
    high: float = 5.0,
    tol: float = 1e-6,
    max_iter: int = 200,
) -> float:
    """Solve implied volatility using bisection on Black-Scholes price."""
    _validate_inputs(spot, strike, time_to_expiry_years, 0.0, option_type)
    if market_price < 0:
        raise ValueError(f"market_price must be >= 0, got {market_price}")

    if time_to_expiry_years == 0.0:
        return 0.0

    lo = low
    hi = high

    plo = black_scholes_price(
        spot, strike, time_to_expiry_years, risk_free_rate, lo, option_type, dividend_yield
    )
    phi = black_scholes_price(
        spot, strike, time_to_expiry_years, risk_free_rate, hi, option_type, dividend_yield
    )

    if market_price < plo - tol or market_price > phi + tol:
        raise ValueError(
            "market_price is outside model bounds for provided inputs; "
            f"price={market_price}, bounds=[{plo}, {phi}]"
        )

    for _ in range(max_iter):
        mid = 0.5 * (lo + hi)
        pmid = black_scholes_price(
            spot, strike, time_to_expiry_years, risk_free_rate, mid, option_type, dividend_yield
        )
        err = pmid - market_price

        if abs(err) <= tol:
            return mid

        if err > 0:
            hi = mid
        else:
            lo = mid

    return 0.5 * (lo + hi)
