"""
framework/indicators.py
─────────────────────────────────────────────────────────────────────────────
All indicator functions follow the same contract:
  - Input:  pandas Series (or multiple Series for OHLC indicators)
  - Output: pandas Series aligned to the same index
  - No side effects — pure functions, nothing stored on disk

Build order:
  SMA → EMA → WMA → RSI → MACD → Bollinger Bands → ATR
"""

import pandas as pd
import numpy as np


# ─── MOVING AVERAGES ──────────────────────────────────────────────────────────


def sma(series: pd.Series, period: int) -> pd.Series:
    """
    Simple Moving Average — equal weight to every bar in the window.

    How it works:
        At each bar, sum the last `period` closing prices and divide by `period`.
        The first (period - 1) values are NaN because there aren't enough bars yet.

    When to use:
        Trend direction on higher timeframes. Slower to react than EMA,
        which makes it better for filtering noise on daily/weekly charts.

    Args:
        series: typically close prices
        period: lookback window (e.g. 20, 50, 200)

    Returns:
        Series of rolling means, NaN for the first (period-1) rows
    """
    return series.rolling(period).mean()


def ema(series: pd.Series, period: int) -> pd.Series:
    """
    Exponential Moving Average — more weight to recent bars.

    How it works:
        Each value = (current_price × multiplier) + (previous_EMA × (1 − multiplier))
        where multiplier = 2 / (period + 1)

        Because recent prices get higher weight, EMA reacts faster than SMA.
        adjust=False means we use the recursive formula above (standard approach).

    When to use:
        Signal generation on intraday/daily charts. The 8/21 EMA cross is a
        common trend-entry trigger. MACD is entirely built from EMAs.

    Args:
        series: typically close prices
        period: span of the EMA (e.g. 12, 26)

    Returns:
        Series of exponentially weighted means
    """
    return series.ewm(span=period, adjust=False).mean()


def wma(series: pd.Series, period: int) -> pd.Series:
    """
    Weighted Moving Average — linearly increasing weight toward the most recent bar.

    How it works:
        Weights = [1, 2, 3, ..., period]. Most recent bar gets weight `period`,
        oldest bar in the window gets weight 1. Then divide by sum of weights.

    When to use:
        Less common than SMA/EMA but useful when you want recency bias
        without the exponential decay of EMA. Sometimes used in Hull MA.

    Args:
        series: typically close prices
        period: lookback window

    Returns:
        Series of linearly weighted means, NaN for the first (period-1) rows
    """
    weights = np.arange(1, period + 1)  # [1, 2, 3, ..., period]
    return series.rolling(period).apply(
        lambda x: np.dot(x, weights) / weights.sum(),
        raw=True,  # raw=True passes a numpy array (faster)
    )


# ─── MOMENTUM INDICATORS ──────────────────────────────────────────────────────


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """
    Relative Strength Index — measures speed and magnitude of price changes.
    Oscillates between 0 and 100.

    How it works:
        1. Calculate daily change: delta = close - close.shift(1)
        2. Separate gains (positive deltas) from losses (negative deltas)
        3. Smooth both with a rolling mean over `period` bars
        4. RS = avg_gain / avg_loss
        5. RSI = 100 - (100 / (1 + RS))

    Interpretation:
        RSI > 70  →  overbought (potential short signal)
        RSI < 30  →  oversold  (potential long signal)
        RSI divergence from price = one of the strongest signals

    Args:
        series: close prices
        period: smoothing period (default 14, Wilder's original)

    Returns:
        Series oscillating 0–100
    """
    delta = series.diff()  # day-to-day change

    gain = delta.clip(lower=0)  # keep only positive moves
    loss = (-delta).clip(lower=0)  # keep only negative moves (made positive)

    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()

    rs = avg_gain / avg_loss  # relative strength
    return 100 - (100 / (1 + rs))


def macd(
    series: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """
    Moving Average Convergence Divergence.
    Returns three series: MACD line, Signal line, Histogram.

    How it works:
        MACD line   = EMA(fast) − EMA(slow)        (12 and 26 by default)
        Signal line = EMA(MACD line, signal)        (9-period EMA of MACD)
        Histogram   = MACD line − Signal line

    Interpretation:
        Histogram crosses zero       → momentum shift (common entry trigger)
        MACD line crosses Signal     → trend change signal
        Divergence vs price          → leading reversal indicator

    Args:
        series: close prices
        fast:   fast EMA period (default 12)
        slow:   slow EMA period (default 26)
        signal: signal line EMA period (default 9)

    Returns:
        (macd_line, signal_line, histogram) — all as pandas Series
    """
    fast_ema = ema(series, fast)
    slow_ema = ema(series, slow)
    macd_line = fast_ema - slow_ema
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


# ─── VOLATILITY INDICATORS ────────────────────────────────────────────────────


def bollinger_bands(
    series: pd.Series,
    period: int = 20,
    std_dev: float = 2.0,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """
    Bollinger Bands — volatility envelope around a moving average.
    Returns (upper, middle, lower) bands.

    How it works:
        Middle = SMA(period)
        Upper  = Middle + (std_dev × rolling std deviation)
        Lower  = Middle − (std_dev × rolling std deviation)

        When volatility expands, the bands widen.
        When volatility contracts (squeeze), the bands narrow — often
        precedes a large breakout move.

    Interpretation:
        Price touches upper band  → overbought in low-vol environments
        Price touches lower band  → oversold in low-vol environments
        Band squeeze + breakout   → momentum entry signal
        %B = (price - lower) / (upper - lower) → normalised position

    Args:
        series:  close prices
        period:  SMA lookback (default 20)
        std_dev: number of standard deviations (default 2)

    Returns:
        (upper_band, middle_band, lower_band) — all as pandas Series
    """
    middle = sma(series, period)
    sigma = series.rolling(period).std()  # rolling standard deviation
    upper = middle + std_dev * sigma
    lower = middle - std_dev * sigma
    return upper, middle, lower


def atr(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 14,
) -> pd.Series:
    """
    Average True Range — measures market volatility using full price range.

    How it works:
        True Range is the LARGEST of:
          1. High − Low                  (today's full range)
          2. |High − Previous Close|    (gap up scenario)
          3. |Low  − Previous Close|    (gap down scenario)

        ATR = rolling mean of True Range over `period` bars.

    Why this matters:
        ATR is the correct way to size stops. Instead of a fixed £ amount,
        set your stop at 1.5× or 2× ATR — this adapts to current volatility.
        High ATR = widen stops (volatile). Low ATR = tighten stops (quiet).

        On the prop firm challenge: use ATR to stay within daily DD limits.

    Args:
        high:   high prices
        low:    low prices
        close:  close prices
        period: smoothing period (default 14)

    Returns:
        Series of average true ranges
    """
    prev_close = close.shift(1)

    tr = pd.concat(
        [
            high - low,  # today's high-low range
            (high - prev_close).abs(),  # gap up: high vs prior close
            (low - prev_close).abs(),  # gap down: low vs prior close
        ],
        axis=1,
    ).max(
        axis=1
    )  # take the largest of the three

    return tr.rolling(period).mean()
