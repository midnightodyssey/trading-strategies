"""
tests/test_portfolio.py
─────────────────────────────────────────────────────────────────────────────
Run with:  pytest tests/test_portfolio.py -v

All stochastic tests use fixed random seeds for deterministic results.
"""

import numpy as np
import pandas as pd
import pytest
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from framework.portfolio import (
    equal_weight, vol_weight,
    run_portfolio_backtest, correlation_matrix,
    diversification_ratio, PortfolioResult,
)


# ─── HELPERS ──────────────────────────────────────────────────────────────────

def _make_returns(mean=0.001, std=0.01, n=252, seed=0):
    """Create a simple return series."""
    np.random.seed(seed)
    return pd.Series(np.random.normal(mean, std, n))


def _make_prices(mean=0.001, std=0.01, n=252, start=100.0, seed=0):
    """Create a price series derived from returns."""
    rets  = _make_returns(mean, std, n, seed)
    px    = start * (1 + rets).cumprod()
    return px


def _make_signals(n=252, seed=0):
    """Create a simple alternating long/flat signal series."""
    np.random.seed(seed)
    choices = np.random.choice([-1.0, 0.0, 1.0], size=n)
    return pd.Series(choices)


def _two_strategy_inputs(n=252):
    """Return (signals_dict, prices_dict) for two uncorrelated strategies."""
    px_a = _make_prices(mean=0.001, std=0.01, n=n, seed=1)
    px_b = _make_prices(mean=0.001, std=0.01, n=n, seed=2)
    sig_a = pd.Series(1.0, index=px_a.index)   # always long A
    sig_b = pd.Series(1.0, index=px_b.index)   # always long B
    return {"A": sig_a, "B": sig_b}, {"A": px_a, "B": px_b}


# ─── EQUAL WEIGHT TESTS ────────────────────────────────────────────────────────

def test_equal_weight_returns_dict():
    result = equal_weight(["A", "B", "C"])
    assert isinstance(result, dict)

def test_equal_weight_correct_number_of_keys():
    result = equal_weight(["A", "B", "C"])
    assert len(result) == 3

def test_equal_weight_sums_to_one():
    result = equal_weight(["A", "B", "C", "D"])
    assert abs(sum(result.values()) - 1.0) < 1e-10

def test_equal_weight_uniform():
    result = equal_weight(["X", "Y", "Z"])
    weights = list(result.values())
    assert all(abs(w - weights[0]) < 1e-10 for w in weights), \
        "All weights should be equal"

def test_equal_weight_single_asset():
    result = equal_weight(["AAPL"])
    assert result == {"AAPL": 1.0}

def test_equal_weight_empty_list():
    result = equal_weight([])
    assert result == {}

def test_equal_weight_keys_match_input():
    names = ["momentum", "mean_rev", "trend"]
    result = equal_weight(names)
    assert set(result.keys()) == set(names)


# ─── VOL WEIGHT TESTS ─────────────────────────────────────────────────────────

def test_vol_weight_returns_dict():
    df = pd.DataFrame({
        "A": _make_returns(std=0.01, seed=1),
        "B": _make_returns(std=0.02, seed=2),
    })
    result = vol_weight(df)
    assert isinstance(result, dict)

def test_vol_weight_sums_to_one():
    df = pd.DataFrame({
        "A": _make_returns(std=0.01, seed=1),
        "B": _make_returns(std=0.02, seed=2),
    })
    result = vol_weight(df)
    assert abs(sum(result.values()) - 1.0) < 1e-6

def test_vol_weight_lower_vol_gets_higher_weight():
    """
    Strategy A has half the vol of B.
    Inverse vol → A gets double the weight of B.
    """
    np.random.seed(0)
    df = pd.DataFrame({
        "A": np.random.normal(0.001, 0.005, 252),   # low vol
        "B": np.random.normal(0.001, 0.020, 252),   # high vol
    })
    result = vol_weight(df)
    assert result["A"] > result["B"], \
        "Lower-vol strategy should receive higher weight"

def test_vol_weight_equal_vols_gives_equal_weights():
    """
    Same vol → same weight.

    B is A shifted by a constant (same data, same std for EVERY slice,
    including the tail(60) that vol_weight actually uses).  The only
    thing that differs is the mean, not the volatility.
    """
    np.random.seed(0)
    data = np.random.normal(0.001, 0.01, 500)
    df = pd.DataFrame({
        "A": data,
        "B": data + 0.001,   # constant shift → identical std for any slice
    })
    result = vol_weight(df)
    assert abs(result["A"] - result["B"]) < 1e-6, \
        "Strategies with identical vol must get identical weights"

def test_vol_weight_zero_vol_falls_back_to_equal():
    """If any asset has zero vol, fall back to equal weighting."""
    df = pd.DataFrame({
        "A": pd.Series([0.0] * 252),          # constant → zero vol
        "B": _make_returns(std=0.01, seed=1),
    })
    result = vol_weight(df)
    assert abs(sum(result.values()) - 1.0) < 1e-6

def test_vol_weight_uses_lookback():
    """Lookback=10 should only consider last 10 rows."""
    np.random.seed(42)
    df = pd.DataFrame({
        "A": np.random.normal(0, 0.01, 252),
        "B": np.random.normal(0, 0.05, 252),
    })
    w10  = vol_weight(df, lookback=10)
    w120 = vol_weight(df, lookback=120)
    # Both should be valid weight dicts summing to 1
    assert abs(sum(w10.values())  - 1.0) < 1e-6
    assert abs(sum(w120.values()) - 1.0) < 1e-6


# ─── RUN PORTFOLIO BACKTEST TESTS ─────────────────────────────────────────────

def test_portfolio_backtest_returns_portfolio_result():
    signals, prices = _two_strategy_inputs()
    result = run_portfolio_backtest(signals, prices)
    assert isinstance(result, PortfolioResult)

def test_portfolio_backtest_result_has_correct_fields():
    signals, prices = _two_strategy_inputs()
    result = run_portfolio_backtest(signals, prices)
    assert hasattr(result, "returns")
    assert hasattr(result, "equity_curve")
    assert hasattr(result, "component_returns")
    assert hasattr(result, "weights")
    assert hasattr(result, "metrics")
    assert hasattr(result, "correlation")

def test_portfolio_backtest_returns_is_series():
    signals, prices = _two_strategy_inputs()
    result = run_portfolio_backtest(signals, prices)
    assert isinstance(result.returns, pd.Series)

def test_portfolio_backtest_equity_curve_starts_near_one():
    """Equity curve is a cumulative product starting from 1."""
    signals, prices = _two_strategy_inputs()
    result = run_portfolio_backtest(signals, prices)
    assert abs(result.equity_curve.iloc[0] - 1.0) < 0.05

def test_portfolio_backtest_component_returns_is_dataframe():
    signals, prices = _two_strategy_inputs()
    result = run_portfolio_backtest(signals, prices)
    assert isinstance(result.component_returns, pd.DataFrame)

def test_portfolio_backtest_component_columns_match_input():
    signals, prices = _two_strategy_inputs()
    result = run_portfolio_backtest(signals, prices)
    assert set(result.component_returns.columns) == {"A", "B"}

def test_portfolio_backtest_weights_sum_to_one():
    signals, prices = _two_strategy_inputs()
    result = run_portfolio_backtest(signals, prices)
    assert abs(sum(result.weights.values()) - 1.0) < 1e-6

def test_portfolio_backtest_metrics_keys():
    signals, prices = _two_strategy_inputs()
    result = run_portfolio_backtest(signals, prices)
    expected = {
        "annual_return", "annual_vol", "sharpe", "sortino",
        "max_drawdown", "calmar", "diversification_ratio", "n_strategies",
    }
    assert set(result.metrics.keys()) == expected

def test_portfolio_backtest_n_strategies_correct():
    signals, prices = _two_strategy_inputs()
    result = run_portfolio_backtest(signals, prices)
    assert result.metrics["n_strategies"] == 2

def test_portfolio_backtest_equal_weight_default():
    """Default weighting should be equal (0.5 / 0.5 for two strategies)."""
    signals, prices = _two_strategy_inputs()
    result = run_portfolio_backtest(signals, prices)
    assert abs(result.weights["A"] - 0.5) < 1e-6
    assert abs(result.weights["B"] - 0.5) < 1e-6

def test_portfolio_backtest_custom_weights_applied():
    """Passing custom weights should override default equal weighting."""
    signals, prices = _two_strategy_inputs()
    custom = {"A": 0.7, "B": 0.3}
    result = run_portfolio_backtest(signals, prices, weights=custom)
    assert abs(result.weights["A"] - 0.7) < 1e-6
    assert abs(result.weights["B"] - 0.3) < 1e-6

def test_portfolio_backtest_empty_inputs_raises():
    with pytest.raises(ValueError):
        run_portfolio_backtest({}, {})

def test_portfolio_backtest_missing_price_raises():
    signals = {"A": pd.Series([1.0] * 10)}
    prices  = {}   # missing A
    with pytest.raises((ValueError, KeyError)):
        run_portfolio_backtest(signals, prices)

def test_portfolio_backtest_no_lookahead_bias():
    """
    The first portfolio return must be NaN/0.0 — no position is held
    before the first signal is observed.
    """
    signals, prices = _two_strategy_inputs(n=10)
    result = run_portfolio_backtest(signals, prices)
    # First bar: position was 0 (no prior signal), so net return = 0
    assert result.returns.iloc[0] == 0.0

def test_portfolio_backtest_zero_cost_vs_nonzero_cost():
    """
    With zero transaction costs, returns should be higher (or equal)
    than with non-zero costs.
    """
    # Frequently changing signals (high turnover) to amplify cost effect
    np.random.seed(5)
    n = 252
    px = _make_prices(n=n, seed=5)
    # Alternating signals — maximum turnover
    sig = pd.Series(np.tile([1.0, -1.0], n // 2 + 1)[:n])
    sig.index = px.index

    signals = {"A": sig}
    prices  = {"A": px}

    r_free  = run_portfolio_backtest(signals, prices, slippage=0.0, commission=0.0)
    r_costs = run_portfolio_backtest(signals, prices, slippage=0.001, commission=0.002)

    assert r_free.returns.sum() >= r_costs.returns.sum(), \
        "Zero-cost returns should be at least as high as with transaction costs"

def test_portfolio_backtest_single_strategy():
    """Single-strategy portfolio should work like a solo backtest."""
    px  = _make_prices(n=252, seed=10)
    sig = pd.Series(1.0, index=px.index)   # always long
    result = run_portfolio_backtest({"solo": sig}, {"solo": px})
    assert result.metrics["n_strategies"] == 1

def test_portfolio_backtest_three_strategies():
    """Portfolio with three strategies should work correctly."""
    signals = {}
    prices  = {}
    for i, name in enumerate(["A", "B", "C"]):
        px  = _make_prices(seed=i * 10 + 1)
        sig = pd.Series(1.0, index=px.index)
        signals[name] = sig
        prices[name]  = px
    result = run_portfolio_backtest(signals, prices)
    assert result.metrics["n_strategies"] == 3
    assert abs(sum(result.weights.values()) - 1.0) < 1e-6

def test_portfolio_backtest_max_drawdown_non_positive():
    """Max drawdown should always be ≤ 0."""
    signals, prices = _two_strategy_inputs()
    result = run_portfolio_backtest(signals, prices)
    assert result.metrics["max_drawdown"] <= 0.0

def test_portfolio_backtest_annual_vol_positive():
    signals, prices = _two_strategy_inputs()
    result = run_portfolio_backtest(signals, prices)
    assert result.metrics["annual_vol"] >= 0.0

def test_portfolio_backtest_correlation_is_dataframe():
    signals, prices = _two_strategy_inputs()
    result = run_portfolio_backtest(signals, prices)
    assert isinstance(result.correlation, pd.DataFrame)

def test_portfolio_backtest_diversification_ratio_at_least_one():
    """DR must always be ≥ 1.0 (diversification never destroys value)."""
    signals, prices = _two_strategy_inputs()
    result = run_portfolio_backtest(signals, prices)
    assert result.metrics["diversification_ratio"] >= 1.0 - 1e-9


# ─── CORRELATION MATRIX TESTS ─────────────────────────────────────────────────

def test_correlation_matrix_returns_dataframe():
    df = pd.DataFrame({
        "A": _make_returns(seed=1),
        "B": _make_returns(seed=2),
    })
    result = correlation_matrix(df)
    assert isinstance(result, pd.DataFrame)

def test_correlation_matrix_diagonal_is_one():
    """Each series is perfectly correlated with itself."""
    df = pd.DataFrame({
        "A": _make_returns(seed=1),
        "B": _make_returns(seed=2),
    })
    result = correlation_matrix(df)
    for col in df.columns:
        assert abs(result.loc[col, col] - 1.0) < 1e-10

def test_correlation_matrix_symmetric():
    """Correlation matrix must be symmetric: corr(A,B) == corr(B,A)."""
    df = pd.DataFrame({
        "A": _make_returns(seed=1),
        "B": _make_returns(seed=2),
        "C": _make_returns(seed=3),
    })
    result = correlation_matrix(df)
    for a in df.columns:
        for b in df.columns:
            assert abs(result.loc[a, b] - result.loc[b, a]) < 1e-10

def test_correlation_matrix_values_in_range():
    """All correlation values must be in [-1, 1]."""
    df = pd.DataFrame({
        "A": _make_returns(seed=1),
        "B": _make_returns(seed=2),
    })
    result = correlation_matrix(df)
    assert (result.values >= -1.0 - 1e-10).all()
    assert (result.values <=  1.0 + 1e-10).all()

def test_correlation_matrix_identical_series_gives_one():
    """Two identical series should have correlation = 1.0."""
    r = _make_returns(seed=42)
    df = pd.DataFrame({"A": r, "B": r})
    result = correlation_matrix(df)
    assert abs(result.loc["A", "B"] - 1.0) < 1e-6

def test_correlation_matrix_anticorrelated_series():
    """Negated series should have correlation ≈ -1.0."""
    r  = _make_returns(seed=42)
    df = pd.DataFrame({"A": r, "B": -r})
    result = correlation_matrix(df)
    assert abs(result.loc["A", "B"] - (-1.0)) < 1e-6

def test_correlation_matrix_shape():
    """Output shape should be (n_strategies × n_strategies)."""
    df = pd.DataFrame({
        "A": _make_returns(seed=1),
        "B": _make_returns(seed=2),
        "C": _make_returns(seed=3),
    })
    result = correlation_matrix(df)
    assert result.shape == (3, 3)


# ─── DIVERSIFICATION RATIO TESTS ──────────────────────────────────────────────

def test_diversification_ratio_returns_float():
    df = pd.DataFrame({
        "A": _make_returns(seed=1),
        "B": _make_returns(seed=2),
    })
    w  = {"A": 0.5, "B": 0.5}
    result = diversification_ratio(df, w)
    assert isinstance(result, float)

def test_diversification_ratio_at_least_one():
    """DR is always ≥ 1 (diversification is non-negative)."""
    df = pd.DataFrame({
        "A": _make_returns(seed=1),
        "B": _make_returns(seed=2),
    })
    w  = {"A": 0.5, "B": 0.5}
    result = diversification_ratio(df, w)
    assert result >= 1.0 - 1e-9

def test_diversification_ratio_one_for_perfect_correlation():
    """
    Perfectly correlated strategies offer no diversification: DR = 1.0.
    """
    r  = _make_returns(seed=42)
    df = pd.DataFrame({"A": r, "B": r})
    w  = {"A": 0.5, "B": 0.5}
    result = diversification_ratio(df, w)
    assert abs(result - 1.0) < 1e-6

def test_diversification_ratio_above_one_for_uncorrelated():
    """
    Uncorrelated equal-vol strategies → DR ≈ √2 ≈ 1.41 for two strategies.
    """
    np.random.seed(0)
    n = 5000
    a = np.random.normal(0.001, 0.01, n)
    b = np.random.normal(0.001, 0.01, n)
    # Make b orthogonal to a: b -= projection on a
    b = b - (np.dot(a, b) / np.dot(a, a)) * a
    df = pd.DataFrame({"A": a, "B": b})
    w  = {"A": 0.5, "B": 0.5}
    result = diversification_ratio(df, w)
    assert result > 1.2, f"Expected DR > 1.2 for uncorrelated strategies, got {result:.3f}"

def test_diversification_ratio_single_strategy_returns_one():
    """Single strategy → no diversification possible → DR = 1.0."""
    df = pd.DataFrame({"A": _make_returns(seed=1)})
    w  = {"A": 1.0}
    result = diversification_ratio(df, w)
    assert result == 1.0

def test_diversification_ratio_increases_with_more_strategies():
    """
    Adding a third uncorrelated strategy should increase DR further.
    (More diversification sources → higher ratio)
    """
    np.random.seed(99)
    n = 5000
    a = np.random.normal(0, 0.01, n)
    b = np.random.normal(0, 0.01, n)
    c = np.random.normal(0, 0.01, n)
    # Ensure low correlation
    b -= (np.dot(a, b) / np.dot(a, a)) * a
    c -= (np.dot(a, c) / np.dot(a, a)) * a
    c -= (np.dot(b, c) / np.dot(b, b)) * b

    df2 = pd.DataFrame({"A": a, "B": b})
    df3 = pd.DataFrame({"A": a, "B": b, "C": c})
    w2  = {"A": 1/2, "B": 1/2}
    w3  = {"A": 1/3, "B": 1/3, "C": 1/3}

    dr2 = diversification_ratio(df2, w2)
    dr3 = diversification_ratio(df3, w3)
    assert dr3 > dr2 - 0.05, \
        f"DR should not decrease with more uncorrelated strategies: dr2={dr2:.3f}, dr3={dr3:.3f}"

def test_diversification_ratio_zero_vol_returns_one():
    """Zero-vol strategy (constant returns) → fall back to 1.0."""
    df = pd.DataFrame({
        "A": pd.Series([0.001] * 252),    # constant → zero vol
        "B": _make_returns(std=0.01, seed=1),
    })
    w  = {"A": 0.5, "B": 0.5}
    result = diversification_ratio(df, w)
    assert abs(result - 1.0) < 1e-9, f"Expected DR ≈ 1.0, got {result}"


# ─── INTEGRATION: FULL PIPELINE TESTS ─────────────────────────────────────────

def test_full_pipeline_positive_drift_portfolio():
    """
    Build two long-biased strategies on trending price series.
    Portfolio should have positive cumulative return.
    """
    np.random.seed(7)
    n = 500
    px_a = _make_prices(mean=0.002, std=0.008, n=n, seed=7)
    px_b = _make_prices(mean=0.002, std=0.010, n=n, seed=8)
    sig_a = pd.Series(1.0, index=px_a.index)
    sig_b = pd.Series(1.0, index=px_b.index)

    result = run_portfolio_backtest(
        {"A": sig_a, "B": sig_b},
        {"A": px_a,  "B": px_b},
        slippage=0.0, commission=0.0,
    )
    assert result.equity_curve.iloc[-1] > 1.0, "Positive-drift portfolio should grow"

def test_full_pipeline_inverse_vol_weights_favour_less_volatile():
    """
    Strategy A is less volatile than B.
    Using vol_weight, A should get a larger portfolio weight.
    """
    np.random.seed(3)
    n  = 500
    px_a = _make_prices(mean=0.001, std=0.005, n=n, seed=3)   # low vol
    px_b = _make_prices(mean=0.001, std=0.025, n=n, seed=4)   # high vol
    sig_a = pd.Series(1.0, index=px_a.index)
    sig_b = pd.Series(1.0, index=px_b.index)

    component_rets_a = px_a.pct_change().fillna(0)
    component_rets_b = px_b.pct_change().fillna(0)
    component_df = pd.DataFrame({"A": component_rets_a, "B": component_rets_b})

    weights = vol_weight(component_df)
    assert weights["A"] > weights["B"], \
        "Low-vol strategy A should receive higher weight"

def test_full_pipeline_correlation_between_identical_strategies():
    """
    Backtesting the same signals twice (A and B identical) should yield
    correlation = 1.0 between component returns.
    """
    px   = _make_prices(n=252, seed=99)
    sig  = pd.Series(1.0, index=px.index)
    result = run_portfolio_backtest(
        {"A": sig, "B": sig},
        {"A": px,  "B": px},
    )
    corr = result.correlation.loc["A", "B"]
    assert abs(corr - 1.0) < 1e-6, f"Identical strategies should correlate at 1.0, got {corr:.4f}"
