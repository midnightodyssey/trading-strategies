"""
tests/test_indicators.py
─────────────────────────────────────────────────────────────────────────────
Run with:  pytest tests/test_indicators.py -v

Each test checks a specific mathematical property of the indicator.
We don't test against a "magic number" — we test properties we know must hold.
"""

import numpy as np
import pandas as pd
import pytest
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from framework.indicators import sma, ema, wma, rsi, macd, bollinger_bands, atr


# ─── FIXTURES ─────────────────────────────────────────────────────────────────


@pytest.fixture
def flat_series():
    """A constant price series — useful for sanity checks."""
    return pd.Series([100.0] * 50)


@pytest.fixture
def rising_series():
    """Steadily rising prices: 1, 2, 3, ..., 50."""
    return pd.Series(np.arange(1.0, 51.0))


@pytest.fixture
def ohlc():
    """Simple OHLCV DataFrame for ATR tests."""
    np.random.seed(42)
    close = pd.Series(100 + np.cumsum(np.random.randn(100) * 0.5))
    high = close + np.abs(np.random.randn(100) * 0.3)
    low = close - np.abs(np.random.randn(100) * 0.3)
    return high, low, close


# ─── SMA TESTS ────────────────────────────────────────────────────────────────


def test_sma_flat_series(flat_series):
    """SMA of a constant series should equal that constant."""
    result = sma(flat_series, 10)
    assert result.dropna().eq(100.0).all(), "SMA of constant should be constant"


def test_sma_nan_prefix(rising_series):
    """First (period-1) values should be NaN."""
    period = 10
    result = sma(rising_series, period)
    assert result.iloc[: period - 1].isna().all(), "Should have NaN prefix"
    assert (
        result.iloc[period - 1 :].notna().all()
    ), "Values after warmup should be valid"


def test_sma_known_value(rising_series):
    """SMA(10) at index 9 should be mean of [1..10] = 5.5."""
    result = sma(rising_series, 10)
    assert abs(result.iloc[9] - 5.5) < 1e-10, f"Expected 5.5, got {result.iloc[9]}"


# ─── EMA TESTS ────────────────────────────────────────────────────────────────


def test_ema_flat_series(flat_series):
    """EMA of a constant series should equal that constant."""
    result = ema(flat_series, 10)
    assert (
        result.dropna().round(6).eq(100.0).all()
    ), "EMA of constant should be constant"


def test_ema_reacts_faster_than_sma(rising_series):
    """On a rising series, EMA should always be >= SMA (more weight to recent higher values)."""
    e = ema(rising_series, 10)
    s = sma(rising_series, 10)
    valid = e.notna() & s.notna()
    assert (e[valid] >= s[valid]).all(), "EMA should be >= SMA on a rising series"


# ─── WMA TESTS ────────────────────────────────────────────────────────────────


def test_wma_flat_series(flat_series):
    """WMA of a constant series should equal that constant."""
    result = wma(flat_series, 10)
    assert (
        result.dropna().round(6).eq(100.0).all()
    ), "WMA of constant should be constant"


def test_wma_nan_prefix(rising_series):
    """First (period-1) values should be NaN."""
    result = wma(rising_series, 10)
    assert result.iloc[:9].isna().all()


# ─── RSI TESTS ────────────────────────────────────────────────────────────────


def test_rsi_bounds(rising_series):
    """RSI must always be between 0 and 100."""
    result = rsi(rising_series, 14)
    valid = result.dropna()
    assert (valid >= 0).all() and (valid <= 100).all(), "RSI out of [0, 100] range"


def test_rsi_constant_series(flat_series):
    """RSI of a flat series: no gains, no losses → should handle division by zero gracefully."""
    result = rsi(flat_series, 14)
    # All values should be NaN (0/0) or a defined edge value — not raise an error
    assert isinstance(result, pd.Series), "Should return a Series"


def test_rsi_trending_up(rising_series):
    """On a purely rising series, RSI should be high (above 70)."""
    result = rsi(rising_series, 14)
    valid = result.dropna()
    assert (valid > 70).all(), "RSI should be high on a consistently rising series"


# ─── MACD TESTS ───────────────────────────────────────────────────────────────


def test_macd_returns_three_series():
    """macd() should return exactly three Series."""
    series = pd.Series(np.random.randn(100).cumsum() + 100)
    result = macd(series)
    assert len(result) == 3, "Should return (macd_line, signal_line, histogram)"


def test_macd_histogram_identity():
    """Histogram must always equal MACD line minus Signal line."""
    series = pd.Series(np.random.randn(100).cumsum() + 100)
    macd_line, signal_line, histogram = macd(series)
    diff = (macd_line - signal_line - histogram).dropna().abs()
    assert (diff < 1e-10).all(), "Histogram must equal MACD - Signal"


# ─── BOLLINGER BANDS TESTS ────────────────────────────────────────────────────


def test_bb_returns_three_series():
    """bollinger_bands() should return (upper, middle, lower)."""
    series = pd.Series(np.random.randn(100).cumsum() + 100)
    result = bollinger_bands(series)
    assert len(result) == 3


def test_bb_ordering(flat_series):
    """Upper must always be >= Middle, and Middle >= Lower."""
    upper, middle, lower = bollinger_bands(flat_series, 10)
    valid = upper.notna() & lower.notna()
    assert (upper[valid] >= middle[valid]).all(), "Upper band must be >= middle"
    assert (middle[valid] >= lower[valid]).all(), "Middle band must be >= lower"


def test_bb_flat_series_zero_width(flat_series):
    """On a constant series, std dev = 0, so all three bands should be equal."""
    upper, middle, lower = bollinger_bands(flat_series, 10)
    valid = upper.notna()
    assert (
        upper[valid].round(6).equals(lower[valid].round(6))
    ), "Bands should collapse on constant series"


# ─── ATR TESTS ────────────────────────────────────────────────────────────────


def test_atr_positive(ohlc):
    """ATR must always be positive — it's a range measure."""
    high, low, close = ohlc
    result = atr(high, low, close, 14)
    valid = result.dropna()
    assert (valid > 0).all(), "ATR must be positive"


def test_atr_wider_range_gives_higher_atr():
    """Doubling the high-low range should roughly double the ATR."""
    close = pd.Series([100.0] * 50)
    high1 = close + 1.0
    low1 = close - 1.0
    high2 = close + 2.0
    low2 = close - 2.0

    atr1 = atr(high1, low1, close, 14).dropna().mean()
    atr2 = atr(high2, low2, close, 14).dropna().mean()
    assert abs(atr2 / atr1 - 2.0) < 0.01, "Doubling range should double ATR"
