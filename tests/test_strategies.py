"""
tests/test_strategies.py
─────────────────────────────────────────────────────────────────────────────
Run with:  pytest tests/test_strategies.py -v

Tests focus on mathematical properties and directional logic — not
magic numbers. Each test checks something that MUST be true by construction.
"""

import numpy as np
import pandas as pd
import pytest
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from framework.strategies import EMACrossover, SMACrossover, RSIMeanReversion, BollingerMeanReversion, PriceBreakout
from framework.strategies.base import Strategy
from framework.backtest import BacktestResult


# ─── HELPERS ──────────────────────────────────────────────────────────────────

def make_df(close: pd.Series) -> pd.DataFrame:
    """Wrap a Close series into a minimal OHLCV DataFrame."""
    return pd.DataFrame({
        "Open":   close * 0.999,
        "High":   close * 1.005,
        "Low":    close * 0.995,
        "Close":  close,
        "Volume": 1_000_000.0,
    })


# ─── FIXTURES ─────────────────────────────────────────────────────────────────

@pytest.fixture
def rising_df():
    """Steadily rising prices: 100 → 200 over 200 bars."""
    close = pd.Series(np.linspace(100, 200, 200))
    return make_df(close)

@pytest.fixture
def falling_df():
    """Steadily falling prices: 200 → 100 over 200 bars."""
    close = pd.Series(np.linspace(200, 100, 200))
    return make_df(close)

@pytest.fixture
def flat_df():
    """Constant prices — no trend, no momentum."""
    close = pd.Series([100.0] * 200)
    return make_df(close)

@pytest.fixture
def oscillating_df():
    """Sine wave prices — alternates between overbought and oversold."""
    t     = np.linspace(0, 4 * np.pi, 200)
    close = pd.Series(100 + 10 * np.sin(t))
    return make_df(close)

@pytest.fixture
def realistic_df():
    """Random walk with slight upward drift — realistic market behaviour."""
    np.random.seed(42)
    close = pd.Series(100 + np.cumsum(np.random.randn(300) * 0.5 + 0.05))
    return make_df(close)


# ─── BASE CLASS TESTS ─────────────────────────────────────────────────────────

def test_all_strategies_are_strategy_subclasses():
    """Every strategy must inherit from Strategy."""
    for cls in [EMACrossover, SMACrossover, RSIMeanReversion, BollingerMeanReversion, PriceBreakout]:
        assert issubclass(cls, Strategy), f"{cls.__name__} must subclass Strategy"

def test_strategy_names():
    """Strategy.name should return the class name by default."""
    assert EMACrossover().name          == "EMACrossover"
    assert SMACrossover().name          == "SMACrossover"
    assert RSIMeanReversion().name      == "RSIMeanReversion"
    assert BollingerMeanReversion().name == "BollingerMeanReversion"
    assert PriceBreakout().name         == "PriceBreakout"

def test_base_class_is_abstract():
    """Strategy cannot be instantiated directly — must subclass."""
    with pytest.raises(TypeError):
        Strategy()


# ─── SIGNAL CONTRACT TESTS ────────────────────────────────────────────────────
# Every strategy must produce signals that obey the same contract.

ALL_STRATEGIES = [
    EMACrossover(),
    SMACrossover(),
    RSIMeanReversion(),
    BollingerMeanReversion(),
    PriceBreakout(),
]

@pytest.mark.parametrize("strategy", ALL_STRATEGIES, ids=lambda s: s.name)
def test_signals_return_series(strategy, realistic_df):
    """generate_signals() must return a pd.Series."""
    signals = strategy.generate_signals(realistic_df)
    assert isinstance(signals, pd.Series), f"{strategy.name}: expected Series"

@pytest.mark.parametrize("strategy", ALL_STRATEGIES, ids=lambda s: s.name)
def test_signals_same_length_as_df(strategy, realistic_df):
    """Signal series must have the same length as the input DataFrame."""
    signals = strategy.generate_signals(realistic_df)
    assert len(signals) == len(realistic_df), f"{strategy.name}: length mismatch"

@pytest.mark.parametrize("strategy", ALL_STRATEGIES, ids=lambda s: s.name)
def test_signals_only_valid_values(strategy, realistic_df):
    """All signal values must be exactly -1, 0, or 1."""
    signals = strategy.generate_signals(realistic_df)
    invalid = ~signals.isin([-1.0, 0.0, 1.0])
    assert not invalid.any(), f"{strategy.name}: invalid values: {signals[invalid].unique()}"

@pytest.mark.parametrize("strategy", ALL_STRATEGIES, ids=lambda s: s.name)
def test_signals_no_nan(strategy, realistic_df):
    """Signal series must contain no NaN values."""
    signals = strategy.generate_signals(realistic_df)
    assert not signals.isna().any(), f"{strategy.name}: NaN values found in signals"

@pytest.mark.parametrize("strategy", ALL_STRATEGIES, ids=lambda s: s.name)
def test_run_returns_backtest_result(strategy, realistic_df):
    """run() must return a BacktestResult."""
    result = strategy.run(realistic_df)
    assert isinstance(result, BacktestResult), f"{strategy.name}: expected BacktestResult"

@pytest.mark.parametrize("strategy", ALL_STRATEGIES, ids=lambda s: s.name)
def test_run_metrics_are_floats(strategy, realistic_df):
    """All metrics in BacktestResult must be floats."""
    result = strategy.run(realistic_df)
    for key, val in result.metrics.items():
        assert isinstance(val, float), f"{strategy.name}: {key} is not a float"


# ─── DIRECTIONAL LOGIC TESTS ──────────────────────────────────────────────────

def test_ema_crossover_mostly_long_on_rising_market(rising_df):
    """
    On a steadily rising series, fast EMA > slow EMA most of the time
    → the majority of signals after warmup should be +1.
    """
    signals = EMACrossover(fast=5, slow=20).generate_signals(rising_df)
    warmed  = signals.iloc[20:]   # skip warmup
    assert (warmed == 1.0).mean() > 0.8, "Should be mostly long on rising prices"

def test_ema_crossover_mostly_short_on_falling_market(falling_df):
    """On a falling series, fast EMA < slow EMA → mostly short signals."""
    signals = EMACrossover(fast=5, slow=20).generate_signals(falling_df)
    warmed  = signals.iloc[20:]
    assert (warmed == -1.0).mean() > 0.8, "Should be mostly short on falling prices"

def test_sma_crossover_long_on_rising_market(rising_df):
    """SMA crossover should also be mostly long on a rising series."""
    signals = SMACrossover(fast=10, slow=30).generate_signals(rising_df)
    warmed  = signals.iloc[30:]
    assert (warmed == 1.0).mean() > 0.8

def test_rsi_mean_reversion_flat_series_no_extreme_signals(flat_df):
    """
    On a flat (constant) price series, RSI produces NaN (0/0 division).
    After handling, signals should all be 0 (no extreme readings).
    """
    signals = RSIMeanReversion().generate_signals(flat_df)
    assert (signals == 0.0).all(), "Flat series should produce no extreme RSI signals"

def test_rsi_mean_reversion_rising_is_overbought(rising_df):
    """
    On a consistently rising series, RSI should be high (>70) → short signals.
    After warmup, expect mostly -1 signals.
    """
    signals = RSIMeanReversion(period=5).generate_signals(rising_df)
    warmed  = signals.iloc[10:]
    short_pct = (warmed == -1.0).mean()
    assert short_pct > 0.5, f"Expected mostly overbought signals, got {short_pct:.1%} short"

def test_bollinger_flat_series_no_signals(flat_df):
    """
    On a constant series, std dev = 0, all three bands are equal,
    price is never strictly above upper or below lower → all signals are 0.
    """
    signals = BollingerMeanReversion().generate_signals(flat_df)
    warmed  = signals.iloc[20:]
    assert (warmed == 0.0).all(), "No signals expected on flat series (bands collapsed)"

def test_price_breakout_zero_signals_during_warmup(rising_df):
    """
    First `period` bars (indices 0 to period-1) should all be 0.

    After shift(1), the shifted series has NaN at index 0 and valid values
    from index 1 onwards. rolling(period) needs `period` non-NaN values,
    so the first valid rolling result is at index `period` (not period+1).
    Therefore the warmup window is indices 0 through period-1.
    """
    period  = 20
    signals = PriceBreakout(period=period).generate_signals(rising_df)
    warmup  = signals.iloc[:period]   # indices 0 to 19 — no history yet
    assert (warmup == 0.0).all(), "No signals expected during warmup"

def test_price_breakout_long_on_sustained_rise(rising_df):
    """On a steadily rising series, price keeps breaking to new N-day highs → long."""
    signals = PriceBreakout(period=5).generate_signals(rising_df)
    warmed  = signals.iloc[10:]
    long_pct = (warmed == 1.0).mean()
    assert long_pct > 0.8, f"Expected mostly long breakout signals, got {long_pct:.1%}"


# ─── PARAMETER SENSITIVITY TESTS ─────────────────────────────────────────────

def test_ema_crossover_faster_params_more_trades(realistic_df):
    """Faster parameters should generate more trades (more crossovers)."""
    fast_strategy = EMACrossover(fast=3,  slow=8)
    slow_strategy = EMACrossover(fast=20, slow=50)
    fast_result   = fast_strategy.run(realistic_df)
    slow_result   = slow_strategy.run(realistic_df)
    assert fast_result.trades >= slow_result.trades, "Faster params should generate >= trades"

def test_rsi_tighter_bands_more_signals(realistic_df):
    """
    Wider RSI thresholds (e.g. 40/60) should fire more signals
    than the classic narrow thresholds (30/70).
    """
    wide   = RSIMeanReversion(oversold=40, overbought=60).generate_signals(realistic_df)
    narrow = RSIMeanReversion(oversold=30, overbought=70).generate_signals(realistic_df)
    wide_active   = (wide   != 0).sum()
    narrow_active = (narrow != 0).sum()
    assert wide_active >= narrow_active, "Wider thresholds should produce more signals"

def test_bollinger_narrower_bands_more_signals(realistic_df):
    """
    Using 1 std dev bands instead of 2 should produce more signals
    (price touches the bands more often).
    """
    narrow = BollingerMeanReversion(std_dev=1.0).generate_signals(realistic_df)
    wide   = BollingerMeanReversion(std_dev=2.0).generate_signals(realistic_df)
    assert (narrow != 0).sum() >= (wide != 0).sum()
