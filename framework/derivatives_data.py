"""
framework/derivatives_data.py

Option-chain ingestion scaffolding and normalization utilities.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterable

import pandas as pd


REQUIRED_CHAIN_COLUMNS = [
    "symbol",
    "option_type",
    "strike",
    "expiry",
    "bid",
    "ask",
    "last",
    "implied_volatility",
    "delta",
    "gamma",
    "theta",
    "vega",
    "open_interest",
    "volume",
]


@dataclass(frozen=True)
class OptionQuote:
    symbol: str
    option_type: str
    strike: float
    expiry: date
    bid: float
    ask: float
    last: float
    implied_volatility: float | None = None
    delta: float | None = None
    gamma: float | None = None
    theta: float | None = None
    vega: float | None = None
    open_interest: int | None = None
    volume: int | None = None

    @property
    def mid(self) -> float:
        if self.bid > 0 and self.ask > 0:
            return 0.5 * (self.bid + self.ask)
        if self.last > 0:
            return self.last
        return 0.0


def _as_of_date(as_of: date | None) -> date:
    if as_of is not None:
        return as_of
    return datetime.utcnow().date()


def _clean_numeric(df: pd.DataFrame, cols: Iterable[str]) -> pd.DataFrame:
    out = df.copy()
    for c in cols:
        if c in out.columns:
            out[c] = pd.to_numeric(out[c], errors="coerce")
    return out


def normalize_option_chain(calls: pd.DataFrame, puts: pd.DataFrame, expiry: date) -> pd.DataFrame:
    """Normalize raw calls/puts into a single contract-level dataframe."""
    c = calls.copy()
    p = puts.copy()

    c["option_type"] = "call"
    p["option_type"] = "put"

    for frame in (c, p):
        frame["expiry"] = pd.to_datetime(expiry).date()
        frame.rename(
            columns={
                "impliedVolatility": "implied_volatility",
                "openInterest": "open_interest",
            },
            inplace=True,
        )

    df = pd.concat([c, p], ignore_index=True)

    if "contractSymbol" in df.columns:
        # yfinance contract symbol includes root + date + right + strike.
        # We keep root symbol separately and do not rely on this string for identity.
        pass

    if "symbol" not in df.columns:
        df["symbol"] = ""

    keep = [
        "symbol",
        "option_type",
        "strike",
        "expiry",
        "bid",
        "ask",
        "lastPrice",
        "implied_volatility",
        "delta",
        "gamma",
        "theta",
        "vega",
        "open_interest",
        "volume",
    ]

    for col in keep:
        if col not in df.columns:
            df[col] = pd.NA

    df = df[keep].rename(columns={"lastPrice": "last"})

    df = _clean_numeric(
        df,
        [
            "strike",
            "bid",
            "ask",
            "last",
            "implied_volatility",
            "delta",
            "gamma",
            "theta",
            "vega",
            "open_interest",
            "volume",
        ],
    )

    df["option_type"] = df["option_type"].astype(str).str.lower()
    return df.sort_values(["option_type", "strike"]).reset_index(drop=True)


def fetch_option_chain_yfinance(symbol: str, expiry: str | None = None) -> pd.DataFrame:
    """
    Fetch and normalize option chain from yfinance.

    Notes:
    - yfinance usually does not provide Greeks for all contracts.
    - If Greeks are absent, columns remain NaN and can be filled by model analytics later.
    """
    try:
        import yfinance as yf
    except ImportError as exc:
        raise ImportError("yfinance is required for fetch_option_chain_yfinance") from exc

    ticker = yf.Ticker(symbol)
    expiries = list(ticker.options or [])
    if not expiries:
        raise ValueError(f"No option expiries available for {symbol}")

    chosen = expiry or expiries[0]
    if chosen not in expiries:
        raise ValueError(f"Expiry {chosen} not in available expiries for {symbol}: {expiries[:10]}")

    chain = ticker.option_chain(chosen)
    exp_date = datetime.strptime(chosen, "%Y-%m-%d").date()

    df = normalize_option_chain(chain.calls, chain.puts, exp_date)
    df["symbol"] = symbol.upper()
    return df


def days_to_expiry(expiry: date, as_of: date | None = None) -> int:
    d0 = _as_of_date(as_of)
    return max(0, (expiry - d0).days)
