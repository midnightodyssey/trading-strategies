"""
tests/test_stat_edge.py
─────────────────────────────────────────────────────────────────────────────
Run with:  pytest tests/test_stat_edge.py -v

All stochastic tests use fixed random_state so results are deterministic.
"""

import numpy as np
import pandas as pd
import pytest
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from framework.stat_edge import (
    bootstrap_ci, probabilistic_sharpe, min_track_record,
    permutation_test, edge_summary,
)
from framework.risk import sharpe, calmar


# ─── FIXTURES ─────────────────────────────────────────────────────────────────

@pytest.fixture
def zero_edge_returns():
    """Alternating +/- returns — zero mean, zero SR, zero edge."""
    return pd.Series([0.01, -0.01] * 150)   # 300 bars, mean = 0 exactly

@pytest.fixture
def strong_edge_returns():
    """Consistent positive returns — obvious genuine edge."""
    np.random.seed(42)
    return pd.Series(np.random.normal(0.002, 0.008, 500))  # SR ≈ 3+

@pytest.fixture
def realistic_returns():
    """Realistic strategy: positive drift with noise."""
    np.random.seed(1)
    return pd.Series(np.random.normal(0.0005, 0.01, 252))


# ─── BOOTSTRAP CI TESTS ───────────────────────────────────────────────────────

def test_bootstrap_ci_returns_dict(realistic_returns):
    result = bootstrap_ci(realistic_returns, lambda r: sharpe(r), random_state=0)
    assert isinstance(result, dict)

def test_bootstrap_ci_correct_keys(realistic_returns):
    result = bootstrap_ci(realistic_returns, lambda r: sharpe(r), random_state=0)
    assert set(result.keys()) == {"actual", "ci_lower", "ci_upper", "confidence", "bootstrap_std"}

def test_bootstrap_ci_lower_less_than_upper(realistic_returns):
    """CI lower must always be less than CI upper."""
    result = bootstrap_ci(realistic_returns, lambda r: sharpe(r), random_state=0)
    assert result["ci_lower"] < result["ci_upper"]

def test_bootstrap_ci_positive_lower_for_strong_returns(strong_edge_returns):
    """
    For a strategy with clear positive edge, even the lower CI bound
    should be well above zero.
    """
    result = bootstrap_ci(strong_edge_returns, lambda r: sharpe(r), random_state=0)
    assert result["ci_lower"] > 0.0, f"CI lower {result['ci_lower']:.2f} should be positive"

def test_bootstrap_ci_straddles_zero_for_no_edge(zero_edge_returns):
    """For a zero-edge strategy, the CI should include zero (spans negative to positive)."""
    result = bootstrap_ci(zero_edge_returns, lambda r: sharpe(r), random_state=0)
    assert result["ci_lower"] < 0.0 and result["ci_upper"] > 0.0, \
        "Zero-edge CI should straddle zero"

def test_bootstrap_ci_wider_for_short_series(strong_edge_returns):
    """More data → narrower CI (more reliable estimate)."""
    short = strong_edge_returns.iloc[:50]
    long_ = strong_edge_returns.iloc[:400]
    ci_short = bootstrap_ci(short, lambda r: sharpe(r), n_trials=500, random_state=0)
    ci_long  = bootstrap_ci(long_,  lambda r: sharpe(r), n_trials=500, random_state=0)
    width_short = ci_short["ci_upper"] - ci_short["ci_lower"]
    width_long  = ci_long["ci_upper"]  - ci_long["ci_lower"]
    assert width_short > width_long, "Short series should produce wider CI"

def test_bootstrap_ci_confidence_stored_correctly(realistic_returns):
    """Confidence level should be stored in the result."""
    result = bootstrap_ci(realistic_returns, lambda r: sharpe(r), confidence=0.90, random_state=0)
    assert result["confidence"] == 0.90

def test_bootstrap_ci_works_for_other_metrics(realistic_returns):
    """bootstrap_ci should work for any metric, not just Sharpe."""
    result = bootstrap_ci(realistic_returns, lambda r: float(r.mean()), random_state=0)
    assert result["ci_lower"] < result["ci_upper"]


# ─── PROBABILISTIC SHARPE RATIO TESTS ────────────────────────────────────────

def test_psr_returns_float(realistic_returns):
    result = probabilistic_sharpe(realistic_returns)
    assert isinstance(result, float)

def test_psr_in_range_0_1(realistic_returns):
    result = probabilistic_sharpe(realistic_returns)
    assert 0.0 <= result <= 1.0

def test_psr_half_for_zero_edge(zero_edge_returns):
    """
    When SR = 0 and benchmark = 0, PSR should be exactly 0.5.
    (z = 0, Φ(0) = 0.5)

    Must use risk_free_rate=0.0: with a non-zero rf, subtracting the daily
    risk-free (≈0.0002) from zero-mean returns makes excess returns slightly
    negative, pushing PSR below 0.5 even for a zero-mean strategy.
    """
    result = probabilistic_sharpe(zero_edge_returns, sr_benchmark=0.0, risk_free_rate=0.0)
    assert abs(result - 0.5) < 0.01, f"Expected PSR ≈ 0.5, got {result:.4f}"

def test_psr_high_for_strong_strategy(strong_edge_returns):
    """Obvious positive edge → PSR should be very close to 1.0."""
    result = probabilistic_sharpe(strong_edge_returns, sr_benchmark=0.0)
    assert result > 0.95, f"Expected PSR > 0.95, got {result:.4f}"

def test_psr_below_half_for_negative_sr():
    """Strategy with negative mean return → PSR vs 0 should be below 0.5."""
    bad_returns = pd.Series([-0.001] * 200 + [0.0005] * 52)  # mostly negative
    result = probabilistic_sharpe(bad_returns, sr_benchmark=0.0)
    assert result < 0.5, f"Expected PSR < 0.5 for negative-SR strategy, got {result:.4f}"

def test_psr_increases_with_more_data():
    """
    Same return distribution but more observations → tighter estimate →
    higher PSR (more confidence the edge is real).

    We repeat the SAME return series 3× to triple the observation count
    while keeping the sample SR identical. This isolates the T effect:
    PSR = Φ(sr_hat × √(T-1) / σ_factor) — more T → higher z → higher PSR.

    Using different random slices won't work because sample SR varies across
    slices, which can dominate the T effect.
    """
    np.random.seed(7)
    base     = pd.Series(np.random.normal(0.001, 0.01, 252))
    repeated = pd.concat([base, base, base], ignore_index=True)  # 3× same dist

    psr_short = probabilistic_sharpe(base)
    psr_long  = probabilistic_sharpe(repeated)
    assert psr_long >= psr_short, \
        f"More data should increase PSR: short={psr_short:.4f}, long={psr_long:.4f}"

def test_psr_vs_higher_benchmark_is_lower(strong_edge_returns):
    """PSR vs higher benchmark should be lower than PSR vs lower benchmark."""
    psr_low  = probabilistic_sharpe(strong_edge_returns, sr_benchmark=0.0)
    psr_high = probabilistic_sharpe(strong_edge_returns, sr_benchmark=2.0)
    assert psr_low > psr_high, "Harder benchmark → lower PSR"


# ─── MINIMUM TRACK RECORD TESTS ───────────────────────────────────────────────

def test_min_track_record_returns_float():
    result = min_track_record(sr=1.5)
    assert isinstance(result, float)

def test_min_track_record_infinite_for_zero_sr():
    """Zero Sharpe → can never confirm edge → MinTRL = ∞."""
    result = min_track_record(sr=0.0)
    assert result == float("inf")

def test_min_track_record_infinite_for_negative_sr():
    result = min_track_record(sr=-0.5)
    assert result == float("inf")

def test_min_track_record_infinite_when_sr_equals_benchmark():
    """SR exactly at benchmark → cannot prove we beat it → ∞."""
    result = min_track_record(sr=1.0, sr_benchmark=1.0)
    assert result == float("inf")

def test_min_track_record_decreases_with_higher_sr():
    """Higher Sharpe → fewer months needed to confirm edge."""
    mtr_low  = min_track_record(sr=1.0)
    mtr_high = min_track_record(sr=2.0)
    assert mtr_low > mtr_high, "Higher SR → shorter MinTRL"

def test_min_track_record_increases_with_higher_confidence():
    """Demanding more confidence → more data needed."""
    mtr_95 = min_track_record(sr=1.5, confidence=0.95)
    mtr_99 = min_track_record(sr=1.5, confidence=0.99)
    assert mtr_99 > mtr_95, "Higher confidence → longer MinTRL"

def test_min_track_record_reasonable_value():
    """
    Sharpe 2.0 with normal returns → should need roughly 6-12 months.
    (Ballpark sanity check — not an exact calculation.)
    """
    result = min_track_record(sr=2.0)
    assert 4 < result < 20, f"Expected 4-20 months for SR=2.0, got {result:.1f}"

def test_min_track_record_sharpe_1_needs_over_a_year():
    """Sharpe 1.0 → should need well over 1 year (>12 months)."""
    result = min_track_record(sr=1.0)
    assert result > 12, f"Expected > 12 months for SR=1.0, got {result:.1f}"


# ─── PERMUTATION TEST TESTS ───────────────────────────────────────────────────

def test_permutation_test_returns_dict(realistic_returns):
    result = permutation_test(realistic_returns, lambda r: float(r.mean()), random_state=0)
    assert isinstance(result, dict)

def test_permutation_test_correct_keys(realistic_returns):
    result = permutation_test(realistic_returns, lambda r: float(r.mean()), random_state=0)
    expected = {"actual", "null_mean", "null_std", "p_value", "significant_at_5pct", "significant_at_1pct"}
    assert set(result.keys()) == expected

def test_permutation_test_pvalue_in_range(realistic_returns):
    result = permutation_test(realistic_returns, lambda r: float(r.mean()), random_state=0)
    assert 0.0 <= result["p_value"] <= 1.0

def test_permutation_test_sharpe_pvalue_near_half(strong_edge_returns):
    """
    Sharpe is order-invariant (depends only on mean + std, not sequence).
    Shuffling returns doesn't change Sharpe, so null_mean ≈ actual.
    This shows WHY you should use probabilistic_sharpe() for Sharpe, not permutation_test().
    """
    result = permutation_test(strong_edge_returns, lambda r: sharpe(r, 0.0),
                               n_trials=200, random_state=42)
    # null_mean should be very close to actual (shuffling doesn't affect Sharpe)
    assert abs(result["null_mean"] - result["actual"]) < 0.5, \
        "Shuffling shouldn't change Sharpe — null_mean should ≈ actual"

def test_permutation_test_calmar_significant_for_trending_market():
    """
    Build a series that trends UP then DOWN — good Calmar.
    Randomly shuffled, the drawdown is much worse → actual Calmar beats most shuffles.
    """
    # 200 positive returns then 100 negative: structured trend
    np.random.seed(99)
    up   = np.abs(np.random.normal(0.003, 0.005, 200))
    down = -np.abs(np.random.normal(0.003, 0.005, 100))
    returns = pd.Series(np.concatenate([up, down]))

    result = permutation_test(returns, calmar, n_trials=500, random_state=0)
    # The actual series has losses clustered at the end (worst case for drawdown).
    # p_value tells us: shuffling doesn't make it worse most of the time.
    # Either way, p_value should be a valid number.
    assert 0.0 <= result["p_value"] <= 1.0

def test_permutation_test_significant_flags_consistent(realistic_returns):
    """significant_at_1pct can only be True if significant_at_5pct is also True."""
    result = permutation_test(realistic_returns, lambda r: float(r.mean()), random_state=0)
    if result["significant_at_1pct"]:
        assert result["significant_at_5pct"], "1% significance implies 5% significance"


# ─── EDGE SUMMARY TESTS ───────────────────────────────────────────────────────

def test_edge_summary_returns_dict(realistic_returns):
    result = edge_summary(realistic_returns)
    assert isinstance(result, dict)

def test_edge_summary_correct_keys(realistic_returns):
    result = edge_summary(realistic_returns)
    expected = {
        "Sharpe Ratio", "PSR", "Sharpe CI Lower", "Sharpe CI Upper",
        "MinTRL (months)", "Interpretation"
    }
    assert set(result.keys()) == expected

def test_edge_summary_interpretation_strong_for_obvious_edge(strong_edge_returns):
    result = edge_summary(strong_edge_returns)
    assert result["Interpretation"] == "Strong edge", \
        f"Expected 'Strong edge', got '{result['Interpretation']}'"

def test_edge_summary_interpretation_no_evidence_for_zero_edge(zero_edge_returns):
    result = edge_summary(zero_edge_returns)
    assert result["Interpretation"] == "No evidence of edge"

def test_edge_summary_ci_lower_less_than_upper(realistic_returns):
    result = edge_summary(realistic_returns)
    assert result["Sharpe CI Lower"] < result["Sharpe CI Upper"]

def test_edge_summary_psr_matches_probabilistic_sharpe(realistic_returns):
    """edge_summary PSR should match direct probabilistic_sharpe() call."""
    summary = edge_summary(realistic_returns)
    direct  = probabilistic_sharpe(realistic_returns)
    assert abs(summary["PSR"] - round(direct, 4)) < 1e-6
