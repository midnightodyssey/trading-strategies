"""
framework/data.py
─────────────────────────────────────────────────────────────────────────────
Market data acquisition, cleaning, and feature engineering.

All functions return clean pandas DataFrames with a DatetimeIndex.
Designed to feed directly into run_backtest() from backtest.py.

Build order: indicators → risk → backtest → [data] → strategies → execution
"""

import numpy as np
import pandas as pd
import yfinance as yf
from typing import Optional


# ─── ACQUISITION ──────────────────────────────────────────────────────────────


def fetch(
    ticker: str,
    start: str,
    end: Optional[str] = None,
    interval: str = "1d",
) -> pd.DataFrame:
    """
    Download OHLCV data from Yahoo Finance for a single ticker.

    Why Yahoo Finance?
        Free, reliable for daily data going back 20+ years, covers equities,
        ETFs, indices, FX, and crypto. Sufficient for strategy research.
        For live trading you'd replace this with a broker API (see execution/).

    Args:
        ticker:   Yahoo Finance symbol (e.g. "AAPL", "SPY", "BTC-USD")
        start:    start date as "YYYY-MM-DD"
        end:      end date as "YYYY-MM-DD" (default: today)
        interval: bar size — "1d", "1h", "15m", etc.

    Returns:
        DataFrame with columns: Open, High, Low, Close, Volume
        Indexed by date (DatetimeIndex)

    Raises:
        ValueError: if the ticker returns no data (bad symbol or date range)
    """
    raw = yf.download(
        ticker,
        start=start,
        end=end,
        interval=interval,
        auto_adjust=True,  # adjusts for splits/dividends automatically
        progress=False,  # suppress the download progress bar
    )

    if raw.empty:
        raise ValueError(
            f"No data returned for '{ticker}'. "
            "Check the ticker symbol and date range."
        )

    # yfinance sometimes returns MultiIndex columns (ticker, field) for
    # single-ticker downloads in newer versions — flatten to simple columns
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = [col[0] for col in raw.columns]

    # Keep only the standard OHLCV columns
    df = raw[["Open", "High", "Low", "Close", "Volume"]].copy()

    return df


# ─── CLEANING ─────────────────────────────────────────────────────────────────


def clean(df: pd.DataFrame) -> pd.DataFrame:
    """
    Clean raw OHLCV data — should always be run after fetch().

    Steps applied in order:
        1. Drop rows where Close is NaN (missing bars)
        2. Forward-fill any remaining NaNs (e.g. volume gaps)
        3. Remove duplicate index entries (keep the last occurrence)
        4. Sort index ascending (oldest first)

    Why forward-fill instead of drop?
        Dropping bars creates irregular time series that confuse rolling
        windows and index alignment. Forward-filling preserves the calendar
        while safely handling occasional missing values.

    Args:
        df: raw OHLCV DataFrame from fetch()

    Returns:
        Cleaned DataFrame — same columns, possibly fewer rows
    """
    df = df.copy()

    # 1. Must have a close price to be useful
    df = df.dropna(subset=["Close"])

    # 2. Fill remaining gaps (e.g. missing volume on some exchanges)
    df = df.ffill()

    # 3. Deduplicate — keep the last entry for any repeated date
    df = df[~df.index.duplicated(keep="last")]

    # 4. Ensure chronological order
    df = df.sort_index()

    return df


# ─── FEATURE ENGINEERING ──────────────────────────────────────────────────────


def add_returns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add daily return columns to a price DataFrame.

    Adds two types:
        returns:     simple percentage return — (P_t - P_{t-1}) / P_{t-1}
                     Use for: P&L calculations, risk metrics
        log_returns: natural log return — ln(P_t / P_{t-1})
                     Use for: statistical modelling (additive across time,
                     more normally distributed, symmetric for small values)

    Args:
        df: clean OHLCV DataFrame with a "Close" column

    Returns:
        DataFrame with two new columns appended
    """
    df = df.copy()
    df["returns"] = df["Close"].pct_change()
    df["log_returns"] = np.log(df["Close"] / df["Close"].shift(1))
    return df


def add_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add a standard set of features used by most strategies.

    All features are normalised (dimensionless ratios or percentages) so they
    work across different price levels and asset classes.

    Features added:
        returns:      simple daily return (from add_returns)
        log_returns:  log daily return (from add_returns)
        range_pct:    (High - Low) / Close — intraday range as % of price
                      Proxy for intraday volatility. High = volatile session.
        gap_pct:      (Open - prev_Close) / prev_Close — overnight gap
                      Captures news/earnings reactions between sessions.
        volume_ma20:  20-day moving average of Volume
                      Baseline for "normal" volume on this asset.
        rel_volume:   Volume / volume_ma20 — today's volume vs normal
                      rel_volume > 2 often signals institutional activity.

    Args:
        df: clean OHLCV DataFrame

    Returns:
        DataFrame with all original columns plus six new feature columns
    """
    df = add_returns(df)

    df["range_pct"] = (df["High"] - df["Low"]) / df["Close"]
    df["gap_pct"] = (df["Open"] - df["Close"].shift(1)) / df["Close"].shift(1)
    df["volume_ma20"] = df["Volume"].rolling(20).mean()
    df["rel_volume"] = df["Volume"] / df["volume_ma20"]

    return df


# ─── TRAIN / TEST SPLIT ───────────────────────────────────────────────────────


def train_test_split(
    df: pd.DataFrame,
    train_pct: float = 0.8,
) -> tuple:
    """
    Split a time-indexed DataFrame into train and test sets.

    CRITICAL: Always split by time, never randomly.

        Random splits leak future information into training — your model
        "learns" from data it would never have seen in real time. This is
        one of the most common and most damaging mistakes in financial ML.

        Time-based split: train on the past, test on the future.
        The test set simulates live deployment.

    Args:
        df:        time-indexed DataFrame (oldest first)
        train_pct: fraction allocated to training (default 80%)

    Returns:
        (train_df, test_df) — non-overlapping, chronologically ordered
    """
    n = len(df)
    split_idx = int(n * train_pct)
    train = df.iloc[:split_idx].copy()
    test = df.iloc[split_idx:].copy()
    return train, test


# ─── MULTI-ASSET ──────────────────────────────────────────────────────────────


def fetch_multiple(
    tickers: list,
    start: str,
    end: Optional[str] = None,
    interval: str = "1d",
) -> dict:
    """
    Fetch, clean, and feature-engineer data for a list of tickers.

    Failures are handled gracefully — if one ticker fails (delisted,
    bad symbol, no data in range), it is skipped with a printed warning
    and the rest are returned normally.

    Args:
        tickers:  list of ticker symbols e.g. ["SPY", "QQQ", "IWM"]
        start:    start date "YYYY-MM-DD"
        end:      end date "YYYY-MM-DD" (default: today)
        interval: bar size (default "1d")

    Returns:
        dict mapping ticker → cleaned DataFrame with features
        e.g. {"SPY": df_spy, "QQQ": df_qqq}
    """
    result = {}
    for ticker in tickers:
        try:
            df = fetch(ticker, start, end, interval)
            df = clean(df)
            df = add_features(df)
            result[ticker] = df
        except Exception as e:
            print(f"Warning: skipping {ticker} — {e}")
    return result
