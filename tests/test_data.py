"""
tests/test_data.py
─────────────────────────────────────────────────────────────────────────────
Run with:  pytest tests/test_data.py -v

Key technique: unittest.mock.patch
    fetch() calls yfinance over the internet — we can't rely on network
    access in tests. Instead, we "mock" yf.download to return a fake
    DataFrame we control. This makes tests fast, deterministic, and offline.

    Tests for pure functions (clean, add_returns, add_features,
    train_test_split) don't need mocking — they only use pandas/numpy.
"""

import numpy as np
import pandas as pd
import pytest
from unittest.mock import patch
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from framework.data import fetch, clean, add_returns, add_features, train_test_split, fetch_multiple


# ─── HELPERS ──────────────────────────────────────────────────────────────────

def make_ohlcv(n: int = 100, seed: int = 42) -> pd.DataFrame:
    """Create a realistic synthetic OHLCV DataFrame for testing."""
    np.random.seed(seed)
    idx   = pd.date_range("2023-01-01", periods=n, freq="B")  # business days
    close = pd.Series(100 + np.cumsum(np.random.randn(n) * 0.5), index=idx)
    return pd.DataFrame({
        "Open":   close * 0.999,
        "High":   close * 1.005,
        "Low":    close * 0.995,
        "Close":  close,
        "Volume": np.random.randint(1_000_000, 10_000_000, n).astype(float),
    }, index=idx)


# ─── FETCH TESTS (mocked) ─────────────────────────────────────────────────────

def test_fetch_returns_dataframe():
    """fetch() should return a DataFrame with OHLCV columns."""
    mock_data = make_ohlcv()
    with patch("framework.data.yf.download", return_value=mock_data):
        result = fetch("FAKE", start="2023-01-01")
    assert isinstance(result, pd.DataFrame)
    assert set(result.columns) == {"Open", "High", "Low", "Close", "Volume"}

def test_fetch_raises_on_empty_response():
    """fetch() should raise ValueError when yfinance returns nothing."""
    with patch("framework.data.yf.download", return_value=pd.DataFrame()):
        with pytest.raises(ValueError, match="No data returned"):
            fetch("NOTREAL", start="2023-01-01")

def test_fetch_flattens_multiindex_columns():
    """
    Newer yfinance versions return MultiIndex columns — fetch() should flatten them.
    e.g. ('Close', 'AAPL') → 'Close'
    """
    mock_data = make_ohlcv()
    # Simulate MultiIndex columns as newer yfinance returns
    mock_data.columns = pd.MultiIndex.from_tuples(
        [(c, "FAKE") for c in mock_data.columns]
    )
    with patch("framework.data.yf.download", return_value=mock_data):
        result = fetch("FAKE", start="2023-01-01")
    # Columns should be simple strings, not tuples
    assert all(isinstance(c, str) for c in result.columns)


# ─── CLEAN TESTS ──────────────────────────────────────────────────────────────

def test_clean_drops_nan_close():
    """Rows with NaN Close should be removed."""
    df = make_ohlcv(50)
    df.loc[df.index[10], "Close"] = np.nan
    df.loc[df.index[20], "Close"] = np.nan
    result = clean(df)
    assert result["Close"].isna().sum() == 0

def test_clean_removes_duplicate_index():
    """Duplicate dates should be collapsed to a single row (keep last)."""
    df  = make_ohlcv(50)
    dup = pd.concat([df, df.iloc[[5]]])  # row 5 appears twice
    result = clean(dup)
    assert result.index.is_unique, "Index should be unique after clean()"

def test_clean_sorts_ascending():
    """Data should be in chronological order after clean()."""
    df      = make_ohlcv(50)
    shuffled = df.sample(frac=1, random_state=0)  # random order
    result  = clean(shuffled)
    assert result.index.is_monotonic_increasing, "Index should be sorted ascending"

def test_clean_preserves_row_count_when_no_issues():
    """Clean data should pass through unchanged (same row count)."""
    df     = make_ohlcv(100)
    result = clean(df)
    assert len(result) == len(df)

def test_clean_forward_fills_nan_volume():
    """NaN in non-Close columns (e.g. Volume) should be forward-filled."""
    df = make_ohlcv(50)
    df.loc[df.index[15], "Volume"] = np.nan
    result = clean(df)
    assert result["Volume"].isna().sum() == 0


# ─── ADD_RETURNS TESTS ────────────────────────────────────────────────────────

def test_add_returns_creates_both_columns():
    """add_returns() should add 'returns' and 'log_returns' columns."""
    df     = make_ohlcv(50)
    result = add_returns(df)
    assert "returns"     in result.columns
    assert "log_returns" in result.columns

def test_returns_match_pct_change():
    """Simple returns should equal pandas pct_change()."""
    df     = make_ohlcv(50)
    result = add_returns(df)
    expected = df["Close"].pct_change()
    pd.testing.assert_series_equal(result["returns"], expected, check_names=False)

def test_log_returns_correct_formula():
    """Log returns should equal ln(P_t / P_{t-1})."""
    df     = make_ohlcv(50)
    result = add_returns(df)
    expected = np.log(df["Close"] / df["Close"].shift(1))
    pd.testing.assert_series_equal(result["log_returns"], expected, check_names=False)

def test_add_returns_does_not_modify_original():
    """add_returns() should return a new DataFrame, not modify in place."""
    df     = make_ohlcv(50)
    orig_cols = list(df.columns)
    _      = add_returns(df)
    assert list(df.columns) == orig_cols, "Original DataFrame should be unchanged"


# ─── ADD_FEATURES TESTS ───────────────────────────────────────────────────────

def test_add_features_creates_all_columns():
    """All six feature columns should be present after add_features()."""
    df     = make_ohlcv(50)
    result = add_features(df)
    for col in ["returns", "log_returns", "range_pct", "gap_pct", "volume_ma20", "rel_volume"]:
        assert col in result.columns, f"Missing column: {col}"

def test_range_pct_is_non_negative():
    """(High - Low) / Close must always be >= 0."""
    df     = make_ohlcv(100)
    result = add_features(df)
    assert (result["range_pct"].dropna() >= 0).all(), "range_pct must be non-negative"

def test_rel_volume_nan_before_warmup():
    """rel_volume uses a 20-day MA — first 19 values should be NaN."""
    df     = make_ohlcv(100)
    result = add_features(df)
    assert result["rel_volume"].iloc[:19].isna().all(), "First 19 rel_volume should be NaN"

def test_rel_volume_near_one_on_average():
    """
    Over the full series, average relative volume should be close to 1.0
    (by definition: volume / its own moving average).
    """
    df     = make_ohlcv(200)
    result = add_features(df)
    mean_rv = result["rel_volume"].dropna().mean()
    assert abs(mean_rv - 1.0) < 0.2, f"Expected rel_volume mean ~1.0, got {mean_rv:.3f}"


# ─── TRAIN / TEST SPLIT TESTS ─────────────────────────────────────────────────

def test_split_sizes_correct():
    """Train should be ~80% of data, test should be ~20%."""
    df          = make_ohlcv(100)
    train, test = train_test_split(df, train_pct=0.8)
    assert len(train) == 80
    assert len(test)  == 20

def test_split_no_overlap():
    """Train and test indices must not share any dates."""
    df          = make_ohlcv(100)
    train, test = train_test_split(df)
    overlap = train.index.intersection(test.index)
    assert len(overlap) == 0, f"Train/test overlap: {overlap}"

def test_split_chronological():
    """All train dates must come before all test dates."""
    df          = make_ohlcv(100)
    train, test = train_test_split(df)
    assert train.index.max() < test.index.min(), "Train must end before test begins"

def test_split_covers_all_data():
    """Train + test combined should equal the full dataset."""
    df          = make_ohlcv(100)
    train, test = train_test_split(df)
    assert len(train) + len(test) == len(df)


# ─── FETCH_MULTIPLE TESTS (mocked) ────────────────────────────────────────────

def test_fetch_multiple_returns_dict():
    """fetch_multiple() should return a dict."""
    mock_data = make_ohlcv()
    with patch("framework.data.yf.download", return_value=mock_data):
        result = fetch_multiple(["A", "B"], start="2023-01-01")
    assert isinstance(result, dict)

def test_fetch_multiple_keys_are_tickers():
    """Dict keys should be the ticker symbols requested."""
    mock_data = make_ohlcv()
    with patch("framework.data.yf.download", return_value=mock_data):
        result = fetch_multiple(["SPY", "QQQ"], start="2023-01-01")
    assert "SPY" in result
    assert "QQQ" in result

def test_fetch_multiple_skips_failed_ticker(capsys):
    """
    If one ticker fails, it should be skipped and the rest returned.
    The failure should print a warning (not raise).
    """
    good_data = make_ohlcv()

    def mock_download(ticker, **kwargs):
        if ticker == "BAD":
            return pd.DataFrame()   # empty → triggers ValueError in fetch()
        return good_data

    with patch("framework.data.yf.download", side_effect=mock_download):
        result = fetch_multiple(["SPY", "BAD"], start="2023-01-01")

    assert "SPY" in result
    assert "BAD" not in result
    captured = capsys.readouterr()
    assert "Warning" in captured.out

def test_fetch_multiple_applies_features():
    """Each DataFrame in the result should have feature columns."""
    mock_data = make_ohlcv(100)
    with patch("framework.data.yf.download", return_value=mock_data):
        result = fetch_multiple(["SPY"], start="2023-01-01")
    df = result["SPY"]
    assert "returns"    in df.columns
    assert "range_pct"  in df.columns
    assert "rel_volume" in df.columns
