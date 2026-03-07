"""
framework/stat_edge.py
─────────────────────────────────────────────────────────────────────────────
Statistical significance testing for trading strategy edge.

The central question every prop firm ask about a backtest:
    "Is this result genuine edge, or did you just get lucky?"

Four tools to answer it:

  bootstrap_ci()          — confidence interval for ANY metric
  probabilistic_sharpe()  — P(true Sharpe > benchmark) [López de Prado 2012]
  min_track_record()      — months of live trading needed to confirm edge
  permutation_test()      — null hypothesis test for sequence-dependent metrics

Build order: indicators → risk → backtest → data → strategies → execution → [stat_edge]
"""

import numpy as np
import pandas as pd
from scipy.stats import norm

from .risk import sharpe as sharpe_fn

TRADING_DAYS = 252


# ─── BOOTSTRAP CONFIDENCE INTERVALS ──────────────────────────────────────────

def bootstrap_ci(
    returns:      pd.Series,
    metric_fn,
    n_trials:     int   = 1000,
    confidence:   float = 0.95,
    random_state: int   = None,
) -> dict:
    """
    Bootstrap confidence interval for any performance metric.

    Resamples the return series WITH REPLACEMENT N times, computes the
    metric on each resample, and reports the percentile-based CI.

    Why this matters:
        A backtest Sharpe of 1.5 from one year of data could easily be
        a noisy estimate of a true Sharpe anywhere from 0.3 to 2.7.
        The CI quantifies this uncertainty explicitly.

        If the CI lower bound is still positive → genuine positive edge.
        If the CI straddles zero → you can't rule out luck.

    How to use it:
        sharpe_ci = bootstrap_ci(returns, lambda r: sharpe(r))
        print(f"Sharpe: {sharpe_ci['actual']:.2f}  "
              f"95% CI: [{sharpe_ci['ci_lower']:.2f}, {sharpe_ci['ci_upper']:.2f}]")

    Limitation:
        Assumes i.i.d. returns. Real returns have serial correlation
        (momentum, mean-reversion). Block bootstrapping handles this
        but is beyond the scope of this module.

    Args:
        returns:      daily return series
        metric_fn:    callable, takes a pd.Series and returns a float
        n_trials:     number of bootstrap resamples (default 1000)
        confidence:   CI level (default 0.95 = 95% CI)
        random_state: integer seed for reproducibility

    Returns:
        dict with: actual, ci_lower, ci_upper, confidence, bootstrap_std
    """
    rng    = np.random.default_rng(random_state)
    actual = float(metric_fn(returns))
    n      = len(returns)
    arr    = returns.values

    samples = []
    for _ in range(n_trials):
        idx    = rng.integers(0, n, size=n)
        sample = float(metric_fn(pd.Series(arr[idx])))
        samples.append(sample)

    samples = np.array(samples)
    alpha   = 1 - confidence
    lower   = float(np.percentile(samples, 100 * alpha / 2))
    upper   = float(np.percentile(samples, 100 * (1 - alpha / 2)))

    return {
        "actual":        actual,
        "ci_lower":      lower,
        "ci_upper":      upper,
        "confidence":    confidence,
        "bootstrap_std": float(samples.std()),
    }


# ─── PROBABILISTIC SHARPE RATIO ───────────────────────────────────────────────

def probabilistic_sharpe(
    returns:        pd.Series,
    sr_benchmark:   float = 0.0,
    risk_free_rate: float = 0.05,
) -> float:
    """
    Probabilistic Sharpe Ratio (PSR) — López de Prado (2012).

    PSR(SR*) = Φ [ (SR_hat - SR*) × √(T-1) / σ_SR ]

    Returns: P(true Sharpe > sr_benchmark | observed returns)

    Why not just compare Sharpe to a threshold?
        The Sharpe ratio is an ESTIMATE. With 252 daily observations,
        even a strategy with zero true edge will have an observed Sharpe
        of ±0.6 about 30% of the time purely by luck.

        PSR accounts for:
          - Finite sample size (more data → more reliable estimate)
          - Return skewness (negative skew → Sharpe is harder to sustain)
          - Excess kurtosis / fat tails (adds estimation noise)

    Interpretation:
        PSR > 0.95  →  95% confident the true SR exceeds the benchmark
        PSR > 0.99  →  very strong evidence of genuine edge
        PSR ≈ 0.50  →  no confidence at all (could easily be luck)
        PSR < 0.50  →  evidence AGAINST having edge above the benchmark

    Formula reference:
        Bailey & López de Prado (2012), "The Sharpe Ratio Efficient Frontier"
        σ²(SR) = [1 + 0.5×SR² - γ₃×SR + (γ₄/4)×SR²] / (T-1)
        where γ₃ = skewness, γ₄ = excess kurtosis

    Args:
        returns:        daily return series
        sr_benchmark:   annualised benchmark Sharpe (default 0.0 = "above zero")
        risk_free_rate: annual risk-free rate

    Returns:
        Probability in [0, 1]
    """
    T = len(returns)
    if T < 3:
        return 0.5   # insufficient data

    daily_rf = risk_free_rate / TRADING_DAYS
    excess   = returns - daily_rf

    if excess.std() == 0:
        return 1.0 if excess.mean() > 0 else 0.0

    sr_hat       = float(excess.mean() / excess.std())           # daily SR (un-annualised)
    sr_bench_d   = sr_benchmark / np.sqrt(TRADING_DAYS)          # convert benchmark to daily

    skew         = float(returns.skew())
    excess_kurt  = float(returns.kurtosis())                     # pandas returns excess kurtosis

    # Variance of the daily Sharpe estimator (Mertens 2002)
    sr_variance = (
        1
        + 0.5   * sr_hat**2
        - skew  * sr_hat
        + (excess_kurt / 4) * sr_hat**2
    ) / max(T - 1, 1)

    if sr_variance <= 0:
        return 1.0 if sr_hat > sr_bench_d else 0.0

    z = (sr_hat - sr_bench_d) / np.sqrt(sr_variance)
    return float(norm.cdf(z))


# ─── MINIMUM TRACK RECORD LENGTH ─────────────────────────────────────────────

def min_track_record(
    sr:            float,
    skew:          float = 0.0,
    excess_kurt:   float = 0.0,
    confidence:    float = 0.95,
    sr_benchmark:  float = 0.0,
) -> float:
    """
    Minimum Track Record Length (MinTRL) — Bailey & López de Prado (2014).

    "How many months of live trading do I need before a prop firm /
    investor should believe my claimed Sharpe ratio is genuine?"

    Formula:
        MinTRL (days) = 1 + σ²_SR × [Φ⁻¹(confidence) / (SR_daily - SR*_daily)]²

        where σ²_SR = 1 + 0.5×SR_d² - skew×SR_d + (excess_kurt/4)×SR_d²

    Typical results:
        Sharpe 2.0 → ~8 months at 95% confidence
        Sharpe 1.5 → ~14 months at 95% confidence
        Sharpe 1.0 → ~33 months at 95% confidence  (needs 2.5+ years!)
        Sharpe 0.5 → ~130 months — essentially unprovable in practice

    This is why prop firms demand Sharpe > 1.5: below that, you can't
    convince anyone in a realistic timeframe.

    Args:
        sr:           annualised Sharpe ratio being claimed
        skew:         return skewness (default 0 = Gaussian)
        excess_kurt:  excess kurtosis (default 0 = Gaussian)
        confidence:   required confidence level (default 0.95)
        sr_benchmark: minimum acceptable Sharpe to prove (default 0)

    Returns:
        Minimum months of live trading needed (float). Returns inf if sr ≤ benchmark.
    """
    if sr <= sr_benchmark:
        return float("inf")

    sr_d   = sr           / np.sqrt(TRADING_DAYS)   # convert to daily
    sr_b_d = sr_benchmark / np.sqrt(TRADING_DAYS)

    # Variance factor (same as PSR denominator with T=1)
    var_factor = (
        1
        + 0.5 * sr_d**2
        - skew * sr_d
        + (excess_kurt / 4) * sr_d**2
    )

    z        = norm.ppf(confidence)
    min_days = 1 + var_factor * (z / (sr_d - sr_b_d)) ** 2

    return float(min_days / 21)   # trading days → months


# ─── PERMUTATION TEST ─────────────────────────────────────────────────────────

def permutation_test(
    returns:      pd.Series,
    metric_fn,
    n_trials:     int  = 1000,
    random_state: int  = None,
) -> dict:
    """
    Permutation (randomisation) test for sequence-dependent strategy metrics.

    Best for: Calmar ratio, max drawdown, drawdown recovery time, or any
    custom metric that depends on the ORDER of returns.

    ⚠️  Important: The Sharpe ratio depends only on mean and std, NOT on
    the order of returns — shuffling leaves Sharpe unchanged. For Sharpe
    significance, use probabilistic_sharpe() instead.

    How it works:
        1. Compute the actual metric on the original return series
        2. Shuffle returns randomly N times (destroys all temporal structure)
        3. Compute the metric on each shuffled version
        4. p_value = fraction of shuffled results >= actual result

    Intuition:
        A real Calmar ratio (return / max drawdown) comes partly from the
        strategy AVOIDING bad sequences. A randomly shuffled series will
        experience the same returns but in random order — drawdowns will be
        larger on average. So a good Calmar will beat most shuffled versions.

    Args:
        returns:      daily return series
        metric_fn:    callable, takes pd.Series → float
        n_trials:     number of shuffle trials (default 1000)
        random_state: integer seed for reproducibility

    Returns:
        dict with: actual, null_mean, null_std, p_value, significant_at_5pct, significant_at_1pct
    """
    rng    = np.random.default_rng(random_state)
    actual = float(metric_fn(returns))
    arr    = returns.values.copy()

    null = []
    for _ in range(n_trials):
        shuffled = arr.copy()
        rng.shuffle(shuffled)
        null.append(float(metric_fn(pd.Series(shuffled, index=returns.index))))

    null = np.array(null)
    p_value = float((null >= actual).mean())

    return {
        "actual":              actual,
        "null_mean":           float(null.mean()),
        "null_std":            float(null.std()),
        "p_value":             p_value,
        "significant_at_5pct": p_value < 0.05,
        "significant_at_1pct": p_value < 0.01,
    }


# ─── FULL REPORT ──────────────────────────────────────────────────────────────

def edge_summary(
    returns:        pd.Series,
    risk_free_rate: float = 0.05,
    sr_benchmark:   float = 0.0,
    n_bootstrap:    int   = 1000,
    random_state:   int   = 42,
) -> dict:
    """
    Full statistical edge report — run all analyses in one call.

    The fastest way to assess whether a backtest result is trustworthy.
    Run this before presenting any strategy to a prop firm or investor.

    Args:
        returns:        daily return series
        risk_free_rate: annual risk-free rate
        sr_benchmark:   benchmark Sharpe to test against (default 0)
        n_bootstrap:    bootstrap resamples for CI (default 1000)
        random_state:   seed for reproducibility

    Returns:
        dict with Sharpe, PSR, 95% CI, MinTRL, and plain-English interpretation
    """
    sr  = sharpe_fn(returns, risk_free_rate)
    psr = probabilistic_sharpe(returns, sr_benchmark, risk_free_rate)
    mtr = min_track_record(
        sr,
        skew=float(returns.skew()),
        excess_kurt=float(returns.kurtosis()),
        sr_benchmark=sr_benchmark,
    )

    ci = bootstrap_ci(
        returns,
        lambda r: sharpe_fn(r, risk_free_rate),
        n_trials=n_bootstrap,
        random_state=random_state,
    )

    interpretation = (
        "Strong edge"          if psr > 0.95 else
        "Moderate edge"        if psr > 0.80 else
        "Weak edge"            if psr > 0.60 else
        "No evidence of edge"
    )

    return {
        "Sharpe Ratio":      round(sr, 4),
        "PSR":               round(psr, 4),
        "Sharpe CI Lower":   round(ci["ci_lower"], 4),
        "Sharpe CI Upper":   round(ci["ci_upper"], 4),
        "MinTRL (months)":   round(mtr, 1) if mtr != float("inf") else float("inf"),
        "Interpretation":    interpretation,
    }
