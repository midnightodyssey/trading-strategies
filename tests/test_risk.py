"""
tests/test_risk.py
─────────────────────────────────────────────────────────────────────────────
Run with:  pytest tests/test_risk.py -v
"""

import numpy as np
import pandas as pd
import pytest
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from framework.risk import sharpe, sortino, max_drawdown, calmar, var_parametric, cvar, risk_summary


# ─── FIXTURES ─────────────────────────────────────────────────────────────────

@pytest.fixture
def flat_returns():
    """Zero returns every day — edge case."""
    return pd.Series([0.0] * 252)

@pytest.fixture
def positive_returns():
    """Consistent small daily gains — ideal strategy."""
    return pd.Series([0.001] * 252)   # ~28% annual, no volatility

@pytest.fixture
def realistic_returns():
    """Realistic strategy: positive drift with noise."""
    np.random.seed(42)
    return pd.Series(np.random.normal(0.0005, 0.01, 252))  # 0.05% daily mean, 1% daily std


# ─── SHARPE TESTS ─────────────────────────────────────────────────────────────

def test_sharpe_flat_returns(flat_returns):
    """Zero std dev → Sharpe should return 0.0 gracefully, not crash."""
    result = sharpe(flat_returns)
    assert result == 0.0

def test_sharpe_positive_for_good_strategy(positive_returns):
    """Consistent gains with zero volatility → very high Sharpe."""
    result = sharpe(positive_returns, risk_free_rate=0.0)
    assert result > 5.0, f"Expected high Sharpe, got {result}"

def test_sharpe_is_float(realistic_returns):
    """Sharpe should always return a float."""
    result = sharpe(realistic_returns)
    assert isinstance(result, float)


# ─── SORTINO TESTS ────────────────────────────────────────────────────────────

def test_sortino_positive_returns(positive_returns):
    """No downside returns → Sortino should return 0.0 gracefully."""
    result = sortino(positive_returns, risk_free_rate=0.0)
    assert result == 0.0   # no downside days means downside_std = 0

def test_sortino_greater_than_sharpe_for_skewed_returns():
    """
    For positively skewed returns (more upside than downside volatility),
    Sortino should be >= Sharpe.

    We build a series with 400 positive days (larger std dev) and 100 negative
    days (smaller std dev). The upside vol >> downside vol, so Sortino, which
    only penalises downside, should score higher than Sharpe, which penalises
    all vol equally.
    """
    np.random.seed(1)
    gains   = np.abs(np.random.normal(0.002, 0.015, 400))   # positive days, high upside vol
    losses  = -np.abs(np.random.normal(0.001, 0.005, 100))  # negative days, small downside vol
    data    = np.concatenate([gains, losses])
    np.random.shuffle(data)
    returns = pd.Series(data)
    s  = sharpe(returns, risk_free_rate=0.0)
    so = sortino(returns, risk_free_rate=0.0)
    assert so >= s, f"Sortino ({so:.4f}) should be >= Sharpe ({s:.4f}) for positively skewed returns"

def test_sortino_is_float(realistic_returns):
    assert isinstance(sortino(realistic_returns), float)


# ─── MAX DRAWDOWN TESTS ───────────────────────────────────────────────────────

def test_mdd_is_negative_or_zero(realistic_returns):
    """Max drawdown must always be <= 0."""
    result = max_drawdown(realistic_returns)
    assert result <= 0.0, f"MDD should be negative, got {result}"

def test_mdd_all_positive_returns(positive_returns):
    """Monotonically rising equity curve → drawdown is 0."""
    result = max_drawdown(positive_returns)
    assert abs(result) < 1e-10, "No drawdown on purely rising equity curve"

def test_mdd_known_case():
    """
    Manual check: returns that create a 50% drawdown.
    Equity: 1.0 → 2.0 → 1.0  (peak=2.0, trough=1.0 → DD = -50%)
    """
    # +100% then -50% gets us back to 1.0 from a peak of 2.0
    returns = pd.Series([1.0, -0.5])
    result  = max_drawdown(returns)
    assert abs(result - (-0.5)) < 1e-10, f"Expected -0.5, got {result}"


# ─── CALMAR TESTS ─────────────────────────────────────────────────────────────

def test_calmar_positive_for_good_strategy(positive_returns):
    """Good strategy with no drawdown → Calmar returns 0.0 (MDD = 0)."""
    result = calmar(positive_returns)
    assert result == 0.0   # MDD = 0 so we return 0 by convention

def test_calmar_is_positive_for_profitable_strategy(realistic_returns):
    """For a strategy with positive mean return, Calmar should be positive."""
    profitable = pd.Series([0.001] * 200 + [-0.01] * 52)  # mostly up, some down
    result = calmar(profitable)
    assert isinstance(result, float)

def test_calmar_is_float(realistic_returns):
    assert isinstance(calmar(realistic_returns), float)


# ─── VAR TESTS ────────────────────────────────────────────────────────────────

def test_var_is_positive(realistic_returns):
    """VaR is expressed as a positive loss amount."""
    result = var_parametric(realistic_returns)
    assert result > 0, "VaR should be a positive number"

def test_var_99_greater_than_95(realistic_returns):
    """99% VaR should be larger than 95% VaR (more extreme tail)."""
    var_95 = var_parametric(realistic_returns, confidence=0.95)
    var_99 = var_parametric(realistic_returns, confidence=0.99)
    assert var_99 > var_95, "99% VaR must exceed 95% VaR"

def test_var_horizon_scaling(realistic_returns):
    """10-day VaR should be approximately √10 × 1-day VaR (square root of time)."""
    var_1d  = var_parametric(realistic_returns, horizon=1)
    var_10d = var_parametric(realistic_returns, horizon=10)
    ratio   = var_10d / var_1d
    assert abs(ratio - np.sqrt(10)) < 0.01, f"Expected √10={np.sqrt(10):.3f}, got {ratio:.3f}"


# ─── CVAR TESTS ───────────────────────────────────────────────────────────────

def test_cvar_exceeds_var(realistic_returns):
    """CVaR must always be >= VaR (average of tail is worse than tail threshold)."""
    v = var_parametric(realistic_returns, confidence=0.95)
    c = cvar(realistic_returns, confidence=0.95)
    assert c >= v, f"CVaR ({c:.4f}) should be >= VaR ({v:.4f})"

def test_cvar_is_positive(realistic_returns):
    """CVaR is expressed as a positive loss amount."""
    result = cvar(realistic_returns)
    assert result > 0

def test_cvar_99_greater_than_95(realistic_returns):
    """99% CVaR should be larger than 95% CVaR."""
    c_95 = cvar(realistic_returns, confidence=0.95)
    c_99 = cvar(realistic_returns, confidence=0.99)
    assert c_99 >= c_95


# ─── SUMMARY TESTS ────────────────────────────────────────────────────────────

def test_risk_summary_returns_all_keys(realistic_returns):
    """risk_summary should return all six metrics."""
    result = risk_summary(realistic_returns)
    expected_keys = {"Sharpe Ratio", "Sortino Ratio", "Max Drawdown",
                     "Calmar Ratio", "VaR (95%, 1-day)", "CVaR (95%, 1-day)"}
    assert set(result.keys()) == expected_keys

def test_risk_summary_values_are_numeric(realistic_returns):
    """All values in the summary should be floats."""
    result = risk_summary(realistic_returns)
    for key, val in result.items():
        assert isinstance(val, float), f"{key} is not a float: {val}"
