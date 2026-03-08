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
from ..indicators import rsi, bollinger_bands, sma


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


class TrendFilteredRSI(Strategy):
    """
    Trend-Filtered RSI — mean reversion entries only in the trend's direction.

    How it works:
        Apply RSI mean reversion, but only trade WITH the macro trend:

        Long  (+1): RSI < oversold   AND  close > SMA(trend_period)
                    (oversold dip inside a confirmed uptrend → buy the pullback)
        Short (-1): RSI > overbought AND  close < SMA(trend_period)
                    (overbought bounce inside a confirmed downtrend → sell the pop)
        Flat  (0):  RSI extreme but price is on the WRONG side of the trend
                    (don't buy oversold in a downtrend — that's a falling knife)

    Why filter by trend?
        Unfiltered RSI mean reversion is one of the most dangerous systems in
        bear markets. RSI can stay below 30 for months during a genuine selloff,
        generating repeated long signals that all lose money.

        The SMA(200) filter solves this. Price above SMA(200) = uptrend, so we
        only accept long (buy-dip) signals. Price below SMA(200) = downtrend,
        so we only accept short (sell-pop) signals.

        This is known as the "RSI pullback in trend" strategy — arguably the
        most widely taught RSI application among professional discretionary
        traders. Larry Connors documented the long-only version extensively.

    Typical behaviour:
        - Far fewer trades than raw RSI (most oversold signals are in downtrends
          and get filtered out, and vice versa)
        - Much higher win rate on the trades that do fire
        - Worst case: a strong trending market never reaches the RSI threshold,
          so the strategy stays flat and misses the move (opportunity cost only)

    Args:
        rsi_period:   RSI lookback (default 14 — Wilder's original)
        oversold:     long entry threshold (default 30)
        overbought:   short entry threshold (default 70)
        trend_period: SMA period for macro trend filter (default 200)
    """

    def __init__(
        self,
        rsi_period:   int   = 14,
        oversold:     float = 30.0,
        overbought:   float = 70.0,
        trend_period: int   = 200,
    ):
        self.rsi_period   = rsi_period
        self.oversold     = oversold
        self.overbought   = overbought
        self.trend_period = trend_period

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        rsi_vals = rsi(df["Close"], self.rsi_period)
        trend_ma = sma(df["Close"], self.trend_period)
        close    = df["Close"]

        signal = pd.Series(0.0, index=df.index)

        # Long: oversold dip in an uptrend
        signal[(rsi_vals < self.oversold)   & (close > trend_ma)] =  1.0

        # Short: overbought bounce in a downtrend
        signal[(rsi_vals > self.overbought) & (close < trend_ma)] = -1.0

        # Zero during warmup (whichever indicator needs more history)
        signal[rsi_vals.isna() | trend_ma.isna()] = 0.0

        return signal
