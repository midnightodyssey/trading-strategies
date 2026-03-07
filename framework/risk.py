"""
framework/risk.py
─────────────────────────────────────────────────────────────────────────────
Risk metrics for evaluating strategy performance.

All functions take a pandas Series of DAILY returns (e.g. 0.012 = 1.2% day).
All annualisation uses 252 trading days.

Build order:
  sharpe → sortino → max_drawdown → calmar → var_parametric → cvar
"""

import numpy as np
import pandas as pd
from scipy.stats import norm


TRADING_DAYS = 252  # annualisation constant


# ─── RETURN / RISK RATIOS ─────────────────────────────────────────────────────


def sharpe(returns: pd.Series, risk_free_rate: float = 0.05) -> float:
    """
    Sharpe Ratio — annualised excess return per unit of total volatility.

    Formula:
        Sharpe = (mean_daily_return - daily_rf) / std_daily_return × √252

    Where daily_rf = annual_rf / 252

    Why it matters:
        The universal benchmark for strategy quality. A Sharpe of 1.0 means
        you earn one unit of return for every unit of risk taken. Your prop
        firm target is ≥ 1.5 — demanding but achievable with a systematic edge.

    Weaknesses (know these for interviews):
        - Assumes returns are normally distributed (fat tails understated)
        - Penalises upside volatility the same as downside
        - Sensitive to the choice of risk-free rate
        - Can be gamed by smoothing returns (e.g. monthly reporting)

    Args:
        returns:        daily return series (e.g. 0.01 = 1%)
        risk_free_rate: annual risk-free rate (default 5% = 0.05)

    Returns:
        Annualised Sharpe ratio (float)
    """
    if returns.std() == 0:
        return 0.0
    daily_rf = risk_free_rate / TRADING_DAYS
    excess = returns - daily_rf
    return float(excess.mean() / excess.std() * np.sqrt(TRADING_DAYS))


def sortino(returns: pd.Series, risk_free_rate: float = 0.05) -> float:
    """
    Sortino Ratio — like Sharpe, but only penalises downside volatility.

    Formula:
        Sortino = (mean_annual_excess) / downside_deviation

    Where downside_deviation = std of returns BELOW the target (usually 0 or rf)
    and is annualised by × √252.

    Why it's better than Sharpe for traders:
        A strategy that makes 5% most days and occasionally makes 10% will
        look "volatile" to Sharpe — but that's good volatility. Sortino
        ignores it. Only losses count against you.

    Rule of thumb:
        Sortino > 2.0 = excellent
        Sortino > 1.0 = acceptable

    Args:
        returns:        daily return series
        risk_free_rate: annual risk-free rate (default 5%)

    Returns:
        Annualised Sortino ratio (float)
    """
    daily_rf = risk_free_rate / TRADING_DAYS
    excess = returns - daily_rf
    downside = excess[excess < 0]

    if len(downside) == 0 or downside.std() == 0:
        return 0.0

    downside_std = np.sqrt((downside**2).mean()) * np.sqrt(TRADING_DAYS)
    ann_excess = excess.mean() * TRADING_DAYS
    return float(ann_excess / downside_std)


def max_drawdown(returns: pd.Series) -> float:
    """
    Maximum Drawdown — largest peak-to-trough decline in the equity curve.

    How it works:
        1. Build the equity curve: (1 + r1)(1 + r2)...
        2. Track the running maximum (the "high water mark")
        3. Drawdown at each point = (current - peak) / peak
        4. MDD = the worst (most negative) drawdown ever

    Why it matters for prop firms:
        FTMO: 10% max drawdown hard limit. One bad week and you fail.
        Your strategy's historical MDD must be well below 10% to give
        you buffer for the inevitable bad runs.

    Args:
        returns: daily return series

    Returns:
        Max drawdown as a negative float (e.g. -0.15 = -15%)
    """
    equity_curve = (1 + returns).cumprod()
    rolling_peak = equity_curve.cummax()
    drawdown = (equity_curve - rolling_peak) / rolling_peak
    return float(drawdown.min())


def calmar(returns: pd.Series) -> float:
    """
    Calmar Ratio — annualised return divided by absolute max drawdown.

    Formula:
        Calmar = Annual Return / |Max Drawdown|

    Why it's the best metric for drawdown-constrained accounts:
        Sharpe tells you return vs volatility. Calmar tells you return
        vs your worst loss — which is exactly the constraint that matters
        for prop firm challenges and institutional mandates.

        A Calmar of 1.0 means you earn 10% annually and your worst
        historical drawdown was also 10%.

    Target: Calmar > 1.0 (ideally > 2.0 for prop firm viability)

    Args:
        returns: daily return series

    Returns:
        Calmar ratio (float). Returns 0.0 if MDD is zero.
    """
    mdd = abs(max_drawdown(returns))
    if mdd == 0:
        return 0.0
    annual_return = returns.mean() * TRADING_DAYS
    return float(annual_return / mdd)


# ─── TAIL RISK METRICS ────────────────────────────────────────────────────────


def var_parametric(
    returns: pd.Series,
    confidence: float = 0.95,
    horizon: int = 1,
) -> float:
    """
    Parametric Value at Risk — maximum expected loss at a confidence level.

    Assumes returns are normally distributed (parametric = model-based).

    Formula:
        VaR = -(μ + z × σ) × √horizon

    Where z = inverse normal CDF at (1 - confidence)
    e.g. z = -1.645 at 95%, z = -2.326 at 99%

    Interpretation:
        95% 1-day VaR = 2% means:
        "On 95% of days, losses will not exceed 2%"
        (equivalently: on 5% of days, losses WILL exceed 2%)

    Key limitation:
        Assumes normality — real returns have fat tails. Parametric VaR
        typically underestimates tail losses by 2–3× in crisis periods.
        This is why Basel III switched to CVaR (see below).

    Args:
        returns:    daily return series
        confidence: e.g. 0.95 for 95% VaR
        horizon:    holding period in days (default 1)

    Returns:
        VaR as a positive number (e.g. 0.02 = 2% loss)
    """
    mu = returns.mean()
    sigma = returns.std()
    z = norm.ppf(1 - confidence)  # negative number (left tail)
    var = -(mu + z * sigma) * np.sqrt(horizon)
    return float(var)


def cvar(
    returns: pd.Series,
    confidence: float = 0.95,
) -> float:
    """
    Conditional Value at Risk (Expected Shortfall) — average loss in the
    worst (1 - confidence)% of scenarios.

    CVaR fixes VaR's biggest flaw: VaR tells you the threshold but not
    what happens beyond it. CVaR tells you the expected loss when you DO
    breach the threshold.

    Formula:
        CVaR = -mean(returns where returns ≤ VaR_threshold)

    Interpretation:
        95% CVaR = 3.5% means:
        "On the worst 5% of days, the average loss is 3.5%"

    CVaR > VaR always (because it averages the tail beyond VaR).

    Why it matters:
        - Standard in Basel III for market risk capital requirements
        - Used by prime brokers to set margin haircuts
        - More honest representation of tail risk than VaR

    Args:
        returns:    daily return series
        confidence: e.g. 0.95 (looks at worst 5% of days)

    Returns:
        CVaR as a positive number (e.g. 0.035 = 3.5% average tail loss)
    """
    threshold = returns.quantile(1 - confidence)
    tail_losses = returns[returns <= threshold]

    if len(tail_losses) == 0:
        return 0.0

    return float(-tail_losses.mean())


# ─── SUMMARY ──────────────────────────────────────────────────────────────────


def risk_summary(returns: pd.Series, risk_free_rate: float = 0.05) -> dict:
    """
    Run all six risk metrics at once and return as a labelled dict.

    Useful for comparing strategies side-by-side or printing a quick report.

    Args:
        returns:        daily return series
        risk_free_rate: annual risk-free rate

    Returns:
        dict with all six metrics, values rounded to 4dp
    """
    return {
        "Sharpe Ratio": round(sharpe(returns, risk_free_rate), 4),
        "Sortino Ratio": round(sortino(returns, risk_free_rate), 4),
        "Max Drawdown": round(max_drawdown(returns), 4),
        "Calmar Ratio": round(calmar(returns), 4),
        "VaR (95%, 1-day)": round(var_parametric(returns, 0.95), 4),
        "CVaR (95%, 1-day)": round(cvar(returns, 0.95), 4),
    }
