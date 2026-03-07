"""
framework/strategies/mean_reversion.py
─────────────────────────────────────────────────────────────────────────────
Mean reversion strategies — bet that extreme moves will snap back.

The core assumption: prices deviate temporarily from their mean, and the
deviation itself creates the force that pulls them back.

Works best in: range-bound markets, calm low-volatility regimes.
Fails badly in: strong trending markets (keeps buying a falling knife).
"""

import pandas as pd

from .base import Strategy
from ..indicators import rsi, bollinger_bands


class RSIMeanReversion(Strategy):
    """
    RSI Mean Reversion — buy oversold conditions, sell overbought conditions.

    How it works:
        RSI < oversold threshold  → asset has fallen too fast → go long
        RSI > overbought threshold → asset has risen too fast → go short
        RSI in between            → no edge, stay flat

    Classic thresholds:
        Wilder's original: 30 (oversold) / 70 (overbought)
        More aggressive:   20 / 80  (fewer trades, stronger signals)
        More aggressive:   25 / 75

    Why RSI works for mean reversion:
        RSI measures the SPEED of price change, not direction. A very low
        RSI means the market has been selling off relentlessly — sellers are
        exhausted. The bounce often comes not from new buyers but simply from
        the absence of continued selling.

    Risk:
        In a genuine downtrend, RSI < 30 can persist for weeks or months.
        Always combine with a higher-timeframe trend filter in live trading.

    Args:
        period:     RSI lookback (default 14 — Wilder's original)
        oversold:   buy threshold (default 30)
        overbought: sell threshold (default 70)
    """

    def __init__(
        self,
        period:     int   = 14,
        oversold:   float = 30.0,
        overbought: float = 70.0,
    ):
        self.period     = period
        self.oversold   = oversold
        self.overbought = overbought

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        rsi_vals = rsi(df["Close"], self.period)

        signal = pd.Series(0.0, index=df.index)
        signal[rsi_vals <  self.oversold]   =  1.0   # oversold → long
        signal[rsi_vals >  self.overbought] = -1.0   # overbought → short
        signal[rsi_vals.isna()] = 0.0

        return signal


class BollingerMeanReversion(Strategy):
    """
    Bollinger Band Mean Reversion — trade the edges of the volatility envelope.

    How it works:
        Price ≤ lower band → statistically cheap → go long
        Price ≥ upper band → statistically expensive → go short
        Price inside bands → no edge, stay flat

    The math behind it:
        The bands are set at ±2 standard deviations from the 20-day mean.
        By the normal distribution, ~95% of prices should fall inside the bands.
        A touch of the outer band is a statistically rare event → mean reversion.

    Important caveat:
        Bollinger himself said the bands are NOT buy/sell signals on their own.
        A close OUTSIDE the band can signal the START of a trend, not a reversal.
        The safest use is: bands contracting (squeeze) → breakout imminent.
        For mean reversion, add confirmation (RSI, volume) before entering.

    Args:
        period:  SMA lookback for the middle band (default 20)
        std_dev: number of standard deviations for the bands (default 2.0)
    """

    def __init__(self, period: int = 20, std_dev: float = 2.0):
        self.period  = period
        self.std_dev = std_dev

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        upper, middle, lower = bollinger_bands(df["Close"], self.period, self.std_dev)
        close = df["Close"]

        signal = pd.Series(0.0, index=df.index)
        signal[close < lower] =  1.0   # strictly below lower band → long
        signal[close > upper] = -1.0   # strictly above upper band → short
        signal[upper.isna()]  =  0.0   # no signal during warmup

        return signal
