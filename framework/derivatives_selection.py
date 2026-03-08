"""
framework/derivatives_selection.py

Contract-selection rules for options workflows.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd

from .derivatives_data import days_to_expiry


@dataclass(frozen=True)
class ContractSelectionRule:
    option_type: str
    target_delta: float | None = None
    min_dte: int = 7
    max_dte: int = 90


@dataclass(frozen=True)
class VerticalSpreadRule:
    long_leg: ContractSelectionRule
    short_target_delta: float


def _filter_chain(chain: pd.DataFrame, rule: ContractSelectionRule, as_of: date | None = None) -> pd.DataFrame:
    if chain.empty:
        return chain

    df = chain.copy()
    df["option_type"] = df["option_type"].astype(str).str.lower()
    df = df[df["option_type"] == rule.option_type.lower()].copy()

    df["dte"] = pd.to_datetime(df["expiry"]).dt.date.map(lambda d: days_to_expiry(d, as_of=as_of))
    df = df[(df["dte"] >= int(rule.min_dte)) & (df["dte"] <= int(rule.max_dte))].copy()

    if "open_interest" in df.columns:
        df = df[df["open_interest"].fillna(0) >= 0]

    return df


def select_contract_by_delta(
    chain: pd.DataFrame,
    rule: ContractSelectionRule,
    as_of: date | None = None,
) -> pd.Series:
    """Pick the closest contract to target delta within tenor bounds."""
    df = _filter_chain(chain, rule, as_of=as_of)
    if df.empty:
        raise ValueError("No contracts after applying option_type/tenor filters")

    if rule.target_delta is None or "delta" not in df.columns or df["delta"].isna().all():
        # Fallback: near-ATM by minimal absolute (strike - median strike).
        mid_strike = float(df["strike"].median())
        df["score"] = (df["strike"] - mid_strike).abs()
        return df.sort_values(["score", "dte", "open_interest"], ascending=[True, True, False]).iloc[0]

    target = abs(float(rule.target_delta))

    # Normalize delta direction: compare absolute delta for matching closeness.
    df["abs_delta"] = df["delta"].abs()
    df["score"] = (df["abs_delta"] - target).abs()

    ranked = df.sort_values(["score", "dte", "open_interest"], ascending=[True, True, False])
    return ranked.iloc[0]


def select_vertical_spread_legs(
    chain: pd.DataFrame,
    rule: VerticalSpreadRule,
    as_of: date | None = None,
) -> tuple[pd.Series, pd.Series]:
    """Select long and short legs for a vertical spread from one chain."""
    long_leg = select_contract_by_delta(chain, rule.long_leg, as_of=as_of)

    short_rule = ContractSelectionRule(
        option_type=rule.long_leg.option_type,
        target_delta=rule.short_target_delta,
        min_dte=rule.long_leg.min_dte,
        max_dte=rule.long_leg.max_dte,
    )

    df = _filter_chain(chain, short_rule, as_of=as_of)
    if df.empty:
        raise ValueError("No short-leg candidates after filtering")

    short_leg = select_contract_by_delta(df, short_rule, as_of=as_of)

    # For calls: short strike should be above long strike for bull spread.
    # For puts: short strike should be below long strike for bear put spread.
    if short_rule.option_type == "call" and float(short_leg["strike"]) <= float(long_leg["strike"]):
        higher = df[df["strike"] > float(long_leg["strike"])]
        if not higher.empty:
            short_leg = select_contract_by_delta(higher, short_rule, as_of=as_of)
    elif short_rule.option_type == "put" and float(short_leg["strike"]) >= float(long_leg["strike"]):
        lower = df[df["strike"] < float(long_leg["strike"])]
        if not lower.empty:
            short_leg = select_contract_by_delta(lower, short_rule, as_of=as_of)

    return long_leg, short_leg
