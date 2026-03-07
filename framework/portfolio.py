"""
framework/portfolio.py
─────────────────────────────────────────────────────────────────────────────
Multi-asset portfolio backtesting and risk analysis.

A single-strategy backtest tells you if one idea works in isolation.
A portfolio backtest tells you if your IDEAS COMBINE well — because correlation
is free diversification, and diversification is the only free lunch in finance.

Five tools in this module:

  equal_weight()            — simplest baseline weighting (1/N)
  vol_weight()              — inverse-volatility targeting (institutional default)
  run_portfolio_backtest()  — run N strategies together as one portfolio
  correlation_matrix()      — visualise how strategies move together
  diversification_ratio()   — single number summarising portfolio diversification

Build order: indicators → risk → backtest → data → strategies → execution →
             stat_edge → [portfolio]
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Dict, Optional

from .risk import sharpe, max_drawdown, calmar, sortino


TRADING_DAYS = 252


# ─── RESULT DATACLASS ─────────────────────────────────────────────────────────

@dataclass
class PortfolioResult:
    """
    Complete output of a multi-asset portfolio backtest.

    Attributes:
        returns:            combined daily portfolio return series
        equity_curve:       cumulative growth of £1 invested
        component_returns:  DataFrame — each column is one strategy's daily returns
        weights:            dict mapping strategy name → portfolio weight
        metrics:            dict of portfolio-level risk/return statistics
        correlation:        pairwise correlation matrix of component returns
    """
    returns:           pd.Series
    equity_curve:      pd.Series
    component_returns: pd.DataFrame
    weights:           Dict[str, float]
    metrics:           dict
    correlation:       pd.DataFrame


# ─── WEIGHTING SCHEMES ────────────────────────────────────────────────────────

def equal_weight(names: list) -> Dict[str, float]:
    """
    Equal (1/N) weighting — the surprisingly hard-to-beat baseline.

    Research (DeMiguel et al. 2009) shows 1/N outperforms most
    mean-variance optimisers out-of-sample because it doesn't overfit
    to historical covariances.

    Use this as your default unless you have strong reason to deviate.

    Args:
        names: list of strategy/asset names

    Returns:
        dict mapping name → weight (all weights sum to 1.0)
    """
    if not names:
        return {}
    w = 1.0 / len(names)
    return {name: w for name in names}


def vol_weight(
    component_returns: pd.DataFrame,
    lookback:          int = 60,
) -> Dict[str, float]:
    """
    Inverse-volatility weighting — give less weight to more volatile assets.

    The institutional standard when combining uncorrelated strategies.
    Assets with lower volatility get proportionally higher weight so that
    each asset contributes EQUAL RISK to the portfolio.

    How it works:
        1. Estimate each asset's recent volatility (rolling std of returns)
        2. Weight each asset inversely proportional to its volatility
        3. Normalise so weights sum to 1.0

    Why better than equal weight for mixed-vol assets?
        Equal weight on a 30%-vol equity strategy and a 5%-vol fixed income
        strategy means the equity dominates all the risk. Inverse vol ensures
        both contribute equally.

    Args:
        component_returns:  DataFrame where each column is a strategy's returns
        lookback:           trading days to estimate volatility (default 60 = 3 months)

    Returns:
        dict mapping strategy name → portfolio weight
    """
    if component_returns.empty:
        return {}

    # Use last `lookback` rows of returns for vol estimate
    tail = component_returns.tail(lookback)
    vols = tail.std()

    # Guard: if any vol is zero or NaN, fall back to equal weight
    if (vols <= 0).any() or vols.isna().any():
        return equal_weight(list(component_returns.columns))

    inv_vol = 1.0 / vols
    total   = inv_vol.sum()
    return {name: float(inv_vol[name] / total) for name in component_returns.columns}


# ─── PORTFOLIO BACKTEST ENGINE ────────────────────────────────────────────────

def run_portfolio_backtest(
    signals_dict:   Dict[str, pd.Series],
    prices_dict:    Dict[str, pd.Series],
    weights:        Optional[Dict[str, float]] = None,
    slippage:       float = 0.0005,
    commission:     float = 0.001,
    risk_free_rate: float = 0.05,
) -> PortfolioResult:
    """
    Run a multi-strategy portfolio backtest.

    Each strategy contributes a weighted daily return.  The portfolio return
    on any day is the weighted sum of individual strategy returns.

    Signal lag:
        signals.shift(1) is applied inside each per-strategy backtest —
        no look-ahead bias.  You generate today's signal using today's close,
        and the position is taken at tomorrow's open (approximated by
        tomorrow's close return).

    Cost model:
        Each position change incurs: 2 × slippage + commission
        (round-trip slippage + one-way commission).

    Args:
        signals_dict:   dict mapping strategy_name → pd.Series of signals (-1/0/1)
        prices_dict:    dict mapping strategy_name → pd.Series of prices (Close)
        weights:        dict mapping strategy_name → float weight.
                        If None, uses equal weighting.
        slippage:       one-way slippage per trade (default 0.05%)
        commission:     one-way commission per trade (default 0.10%)
        risk_free_rate: annual risk-free rate for Sharpe/Sortino

    Returns:
        PortfolioResult with combined returns, equity curve, and all diagnostics
    """
    if not signals_dict or not prices_dict:
        raise ValueError("signals_dict and prices_dict must not be empty")

    names = list(signals_dict.keys())

    # Default to equal weight if none provided
    if weights is None:
        weights = equal_weight(names)

    # Validate all names are in both dicts
    for name in names:
        if name not in prices_dict:
            raise ValueError(f"prices_dict missing entry for '{name}'")

    # ── Run each strategy independently ──────────────────────────────────────
    component_returns_dict: Dict[str, pd.Series] = {}

    for name in names:
        sig    = signals_dict[name]
        px     = prices_dict[name]

        # Align to common index
        sig, px = sig.align(px, join="inner")

        # Apply signal lag (position held on next bar's return)
        pos          = sig.shift(1).fillna(0)
        price_ret    = px.pct_change()
        gross_ret    = pos * price_ret
        changes      = pos.diff().abs().fillna(0)
        trade_costs  = changes * (2 * slippage + commission)
        net_ret      = gross_ret - trade_costs

        component_returns_dict[name] = net_ret

    # ── Combine into a DataFrame aligned on common dates ─────────────────────
    component_df = pd.DataFrame(component_returns_dict)

    # Fill all NaNs with 0 (first bar has NaN price_return; lagged position = 0
    # so the correct contribution is 0 — no position was held)
    component_df = component_df.fillna(0.0)

    # ── Weighted portfolio return ─────────────────────────────────────────────
    weight_series   = pd.Series(weights)
    # Only include strategies present in component_df
    w = weight_series.reindex(component_df.columns).fillna(0.0)
    # Re-normalise in case some strategies were dropped
    if w.sum() > 0:
        w = w / w.sum()

    portfolio_returns = (component_df * w).sum(axis=1)
    equity_curve      = (1 + portfolio_returns).cumprod()

    # ── Portfolio metrics ─────────────────────────────────────────────────────
    daily_rf = risk_free_rate / TRADING_DAYS
    sr       = sharpe(portfolio_returns, risk_free_rate)
    so       = sortino(portfolio_returns, risk_free_rate)
    mdd      = max_drawdown(portfolio_returns)
    cal      = calmar(portfolio_returns)

    ann_return = float(portfolio_returns.mean() * TRADING_DAYS)
    ann_vol    = float(portfolio_returns.std() * np.sqrt(TRADING_DAYS))

    corr = correlation_matrix(component_df)
    dr   = diversification_ratio(component_df, dict(w))

    metrics = {
        "annual_return":        round(ann_return, 4),
        "annual_vol":           round(ann_vol, 4),
        "sharpe":               round(sr, 4),
        "sortino":              round(so, 4),
        "max_drawdown":         round(mdd, 4),
        "calmar":               round(cal, 4),
        "diversification_ratio": round(dr, 4),
        "n_strategies":         len(names),
    }

    return PortfolioResult(
        returns=portfolio_returns,
        equity_curve=equity_curve,
        component_returns=component_df,
        weights=dict(w),
        metrics=metrics,
        correlation=corr,
    )


# ─── CORRELATION MATRIX ───────────────────────────────────────────────────────

def correlation_matrix(component_returns: pd.DataFrame) -> pd.DataFrame:
    """
    Pairwise Pearson correlation matrix of strategy returns.

    Why it matters:
        Two strategies with correlation 0.9 offer almost no diversification.
        Two strategies with correlation 0.0 halve your volatility when
        combined with equal weight (σ_portfolio ≈ σ_individual / √2).
        Negative correlation is the holy grail — profits from one offset
        losses from the other.

    Interpretation guide:
        |ρ| < 0.3   low correlation   — good diversification candidate
        |ρ| < 0.6   moderate          — some benefit but overlap exists
        |ρ| ≥ 0.6   high              — strategies are too similar

    Args:
        component_returns: DataFrame where each column is a strategy's returns

    Returns:
        Symmetric correlation matrix (DataFrame)
    """
    if component_returns.empty or component_returns.shape[1] < 2:
        return component_returns.corr()

    return component_returns.corr()


# ─── DIVERSIFICATION RATIO ────────────────────────────────────────────────────

def diversification_ratio(
    component_returns: pd.DataFrame,
    weights:           Dict[str, float],
) -> float:
    """
    Diversification Ratio (DR) — Choueifaty & Coignard (2008).

    DR = weighted average of individual vols / portfolio vol

    Interpretation:
        DR = 1.0   no diversification — all strategies perfectly correlated
        DR = √N    maximum diversification (N uncorrelated equal-vol strategies)
        DR > 1.0   diversification is adding value (portfolio vol < weighted avg)

    A DR of 1.5 means your portfolio is 33% less volatile than a naive sum
    of your individual strategies would suggest.  Prop firms love seeing DR
    above 1.3 — it means your strategies genuinely complement each other.

    Formula:
        Numerator:   Σ(wᵢ × σᵢ)              — weighted average of individual vols
        Denominator: √(wᵀ Σ w)               — true portfolio volatility
                     (where Σ is the covariance matrix)

    Args:
        component_returns:  DataFrame of per-strategy daily returns
        weights:            dict mapping strategy name → weight

    Returns:
        Diversification Ratio as a float ≥ 1.0.
        Returns 1.0 if portfolio has only one strategy or zero vol.
    """
    cols = component_returns.columns.tolist()
    if len(cols) < 2:
        return 1.0

    w  = np.array([weights.get(c, 0.0) for c in cols])
    vols = component_returns.std().values

    # Guard against zero-vol columns
    if (vols == 0).any():
        return 1.0

    weighted_avg_vol = float(np.dot(w, vols))

    cov = component_returns.cov().values
    portfolio_var = float(w @ cov @ w)

    if portfolio_var <= 0:
        return 1.0

    portfolio_vol = np.sqrt(portfolio_var)

    if portfolio_vol == 0:
        return 1.0

    return float(weighted_avg_vol / portfolio_vol)
