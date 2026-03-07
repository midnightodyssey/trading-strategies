"""
tests/test_backtest.py
─────────────────────────────────────────────────────────────────────────────
Run with:  pytest tests/test_backtest.py -v

Tests cover:
  - Output structure (correct types, fields, keys)
  - Return correctness (long on rising market → profit)
  - Cost model (costs reduce returns)
  - Signal lag (no look-ahead bias)
  - Trade counting
  - Walk-forward splitting
  - Summary table formatting
"""

import numpy as np
import pandas as pd
import pytest
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from framework.backtest import run_backtest, walk_forward, summary_table, BacktestResult


# ─── FIXTURES ─────────────────────────────────────────────────────────────────

@pytest.fixture
def rising_prices():
    """Steadily rising prices: 100 → 200 over 252 days."""
    return pd.Series(np.linspace(100, 200, 252))

@pytest.fixture
def flat_prices():
    """Constant prices — zero returns regardless of signal."""
    return pd.Series([100.0] * 252)

@pytest.fixture
def always_long(rising_prices):
    """Signal: hold long every day."""
    return pd.Series([1.0] * len(rising_prices), index=rising_prices.index)

@pytest.fixture
def always_flat(rising_prices):
    """Signal: never enter the market."""
    return pd.Series([0.0] * len(rising_prices), index=rising_prices.index)

@pytest.fixture
def alternating_signals(rising_prices):
    """Signal flips every bar — maximum trade count, maximum costs."""
    vals = [1.0 if i % 2 == 0 else -1.0 for i in range(len(rising_prices))]
    return pd.Series(vals, index=rising_prices.index)


# ─── STRUCTURE TESTS ──────────────────────────────────────────────────────────

def test_result_is_backtest_result(rising_prices, always_long):
    """run_backtest should return a BacktestResult dataclass."""
    result = run_backtest(always_long, rising_prices)
    assert isinstance(result, BacktestResult)

def test_result_has_all_fields(rising_prices, always_long):
    """BacktestResult must expose all five fields."""
    result = run_backtest(always_long, rising_prices)
    assert hasattr(result, "returns")
    assert hasattr(result, "equity_curve")
    assert hasattr(result, "positions")
    assert hasattr(result, "trades")
    assert hasattr(result, "metrics")

def test_metrics_has_all_six_keys(rising_prices, always_long):
    """Metrics dict should contain all six risk metrics from risk_summary()."""
    result = run_backtest(always_long, rising_prices)
    expected = {
        "Sharpe Ratio", "Sortino Ratio", "Max Drawdown",
        "Calmar Ratio", "VaR (95%, 1-day)", "CVaR (95%, 1-day)"
    }
    assert set(result.metrics.keys()) == expected


# ─── RETURN CORRECTNESS TESTS ─────────────────────────────────────────────────

def test_flat_signal_zero_gross_returns(flat_prices, always_flat):
    """
    Zero position on a flat price series → zero gross and net returns.
    (With slippage=0, commission=0 to isolate the position effect.)
    """
    result = run_backtest(always_flat, flat_prices, slippage=0, commission=0)
    assert result.returns.dropna().abs().sum() == 0.0

def test_long_signal_rising_prices_positive_equity(rising_prices, always_long):
    """Long on a steadily rising market → equity curve ends above 1.0."""
    result = run_backtest(always_long, rising_prices, slippage=0, commission=0)
    final  = result.equity_curve.dropna().iloc[-1]
    assert final > 1.0, f"Expected equity > 1.0, got {final:.4f}"

def test_short_signal_rising_prices_negative_equity(rising_prices):
    """Short on a rising market → equity curve ends below 1.0."""
    always_short = pd.Series([-1.0] * len(rising_prices), index=rising_prices.index)
    result = run_backtest(always_short, rising_prices, slippage=0, commission=0)
    final  = result.equity_curve.dropna().iloc[-1]
    assert final < 1.0, f"Expected equity < 1.0, got {final:.4f}"


# ─── COST MODEL TESTS ─────────────────────────────────────────────────────────

def test_costs_reduce_returns(rising_prices, always_long):
    """Final equity with costs must be less than or equal to without costs."""
    no_cost   = run_backtest(always_long, rising_prices, slippage=0,     commission=0)
    with_cost = run_backtest(always_long, rising_prices, slippage=0.001, commission=0.002)
    assert no_cost.equity_curve.dropna().iloc[-1] >= with_cost.equity_curve.dropna().iloc[-1]

def test_high_turnover_strategy_hurt_most_by_costs(rising_prices, alternating_signals):
    """
    A strategy that trades every day should be significantly worse
    with realistic costs than with zero costs.
    """
    no_cost   = run_backtest(alternating_signals, rising_prices, slippage=0,      commission=0)
    with_cost = run_backtest(alternating_signals, rising_prices, slippage=0.0005, commission=0.001)
    eq_no_cost   = no_cost.equity_curve.dropna().iloc[-1]
    eq_with_cost = with_cost.equity_curve.dropna().iloc[-1]
    assert eq_with_cost < eq_no_cost, "High-turnover strategy should suffer from costs"


# ─── SIGNAL LAG TESTS (NO LOOK-AHEAD BIAS) ───────────────────────────────────

def test_signal_lagged_by_one_bar(rising_prices):
    """
    Position on day T must equal signal on day T-1.
    On day 0 the position must be 0 (no signal before the start).
    On day 1 the position must equal signal[0].
    """
    signals = pd.Series([1.0] * len(rising_prices), index=rising_prices.index)
    result  = run_backtest(signals, rising_prices, slippage=0, commission=0)

    assert result.positions.iloc[0] == 0.0, "No position before first signal"
    assert result.positions.iloc[1] == signals.iloc[0], "Position[1] should mirror signal[0]"

def test_no_future_data_used(rising_prices):
    """
    Inject a huge spike on day 50. A signal fired on day 50 should NOT
    profit from that day's return — it can only be reflected in day 51's position.
    """
    prices = rising_prices.copy()
    prices.iloc[50] *= 2.0             # double the price on day 50

    # Signal fires ON day 50 (after the spike)
    signals = pd.Series(0.0, index=prices.index)
    signals.iloc[50] = 1.0             # buy signal on the spike day

    result = run_backtest(signals, prices, slippage=0, commission=0)

    # The return on day 50 itself should be zero (we weren't long yet)
    assert result.returns.iloc[50] == 0.0, "Should not profit on the same bar the signal fires"


# ─── EQUITY CURVE TESTS ───────────────────────────────────────────────────────

def test_equity_curve_same_length_as_prices(rising_prices, always_long):
    result = run_backtest(always_long, rising_prices)
    assert len(result.equity_curve) == len(rising_prices)

def test_equity_curve_first_valid_near_one(rising_prices, always_long):
    """First non-NaN equity value should be very close to 1.0."""
    result      = run_backtest(always_long, rising_prices)
    first_valid = result.equity_curve.dropna().iloc[0]
    assert abs(first_valid - 1.0) < 0.05, f"Expected ~1.0, got {first_valid:.4f}"


# ─── TRADE COUNT TESTS ────────────────────────────────────────────────────────

def test_always_long_one_trade(rising_prices, always_long):
    """Enter once and hold → exactly 1 trade (the initial entry)."""
    result = run_backtest(always_long, rising_prices)
    assert result.trades == 1

def test_always_flat_zero_trades(flat_prices, always_flat):
    """Never trading → zero trades."""
    result = run_backtest(always_flat, flat_prices)
    assert result.trades == 0

def test_alternating_many_trades(rising_prices, alternating_signals):
    """Flipping position daily → many trades (roughly 250)."""
    result = run_backtest(alternating_signals, rising_prices)
    assert result.trades > 100


# ─── WALK-FORWARD TESTS ───────────────────────────────────────────────────────

def test_walk_forward_returns_list(rising_prices, always_long):
    results = walk_forward(always_long, rising_prices, n_splits=3)
    assert isinstance(results, list)

def test_walk_forward_correct_split_count(rising_prices, always_long):
    results = walk_forward(always_long, rising_prices, n_splits=4)
    assert len(results) == 4

def test_walk_forward_results_are_backtest_results(rising_prices, always_long):
    results = walk_forward(always_long, rising_prices, n_splits=3)
    for r in results:
        assert isinstance(r, BacktestResult)

def test_walk_forward_oos_shorter_than_full(rising_prices, always_long):
    """Each OOS window must be shorter than the full series."""
    results = walk_forward(always_long, rising_prices, n_splits=3, train_pct=0.7)
    for r in results:
        assert len(r.returns) < len(rising_prices)


# ─── SUMMARY TABLE TESTS ──────────────────────────────────────────────────────

def test_summary_table_returns_series(rising_prices, always_long):
    result = run_backtest(always_long, rising_prices)
    table  = summary_table(result)
    assert isinstance(table, pd.Series)

def test_summary_table_has_trades_and_equity(rising_prices, always_long):
    result = run_backtest(always_long, rising_prices)
    table  = summary_table(result)
    assert "Trades"       in table.index
    assert "Final Equity" in table.index

def test_summary_table_all_numeric(rising_prices, always_long):
    result = run_backtest(always_long, rising_prices)
    table  = summary_table(result)
    for key, val in table.items():
        assert isinstance(val, float), f"{key} is not a float: {val}"
