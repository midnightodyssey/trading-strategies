"""
framework/strategies/momentum.py
─────────────────────────────────────────────────────────────────────────────
Momentum / breakout strategies — buy strength, sell weakness.

The core assumption: assets that have been moving strongly in one direction
tend to continue moving in that direction (trend persistence).

Unlike mean reversion, momentum strategies trade WITH the move, not against it.
They enter late (after the breakout) but ride the trend for its full duration.

Academically: the momentum premium is one of the most well-documented
anomalies in finance (Jegadeesh & Titman, 1993). It has persisted for 30+
years across every major asset class.
"""

import pandas as pd

from .base import Strategy
from ..indicators import atr


class PriceBreakout(Strategy):
    """
    Price Breakout Momentum — the Turtle Trading system.

    How it works:
        Long  (+1): today's close breaks ABOVE the N-day high
                    (price is at its strongest point in N days → upward momentum)
        Short (-1): today's close breaks BELOW the N-day low
                    (price is at its weakest point in N days → downward momentum)
        Flat  (0):  price is within its N-day range → no edge

    History:
        Richard Dennis and William Eckhardt ran the "Turtle Experiment" in
        1983 — they taught 23 ordinary people a simple breakout system and
        turned them into professional traders generating hundreds of millions.
        The core entry rule was a 20-day channel breakout. Exactly this.

    Why it works:
        Breakouts often signal genuine regime changes — a stock breaking to
        20-day highs often continues to new highs as momentum attracts buyers.
        The key is exiting quickly when the move fails (stop below entry range).

    Look-ahead note:
        We use shift(1) on the rolling high/low so we're comparing today's
        close to the range of the PREVIOUS N days. Without this, we'd be
        including today's price in the range we're trying to break — circular.

    Args:
        period: channel lookback in bars (default 20 — the Turtle system)
    """

    def __init__(self, period: int = 20):
        self.period = period

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        # Rolling high/low of the PREVIOUS `period` bars (shift to avoid look-ahead)
        rolling_high = df["Close"].shift(1).rolling(self.period).max()
        rolling_low  = df["Close"].shift(1).rolling(self.period).min()

        close  = df["Close"]
        signal = pd.Series(0.0, index=df.index)

        signal[close > rolling_high] =  1.0   # new N-day high → long
        signal[close < rolling_low]  = -1.0   # new N-day low  → short
        signal[rolling_high.isna()]  =  0.0   # no signal until warmup complete

        return signal


class ATRBreakout(Strategy):
    """
    ATR Breakout — Turtle Trading enhanced with a volatility filter.

    How it works:
        Same entry as PriceBreakout (N-day channel), but with an ATR gate:
        only enter when current ATR is above its own rolling average.

        Long  (+1): close breaks N-day high  AND  ATR > ATR rolling mean
        Short (-1): close breaks N-day low   AND  ATR > ATR rolling mean
        Flat  (0):  price inside channel  OR  ATR below average (quiet market)

    Why add an ATR filter?
        Breakouts in low-volatility regimes fail far more often than breakouts
        in high-volatility regimes. When the ATR is below its average, the
        market is compressing — often a precursor to a move, but the direction
        is unknown. By requiring ATR > its average, we insist that expansion
        is ALREADY happening before we commit.

        This eliminates the "false breakout" class: price ticks to a new N-day
        high in a dead, directionless market and immediately reverses. Those
        trades are unprofitable on average and are exactly what this filter
        removes.

    Typical improvement over PriceBreakout:
        Fewer trades, higher win rate per trade, similar or better Sharpe.
        The filter does reduce total profits in strong trending years — the
        trade-off is smoother equity curve vs maximum capture.

    Args:
        period:     channel lookback and ATR MA period (default 20)
        atr_period: ATR smoothing period (default 14)
    """

    def __init__(self, period: int = 20, atr_period: int = 14):
        self.period     = period
        self.atr_period = atr_period

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        # Channel breakout (shift to avoid look-ahead bias)
        rolling_high = df["Close"].shift(1).rolling(self.period).max()
        rolling_low  = df["Close"].shift(1).rolling(self.period).min()

        # ATR volatility filter: current ATR must be above its rolling average
        atr_vals = atr(df["High"], df["Low"], df["Close"], self.atr_period)
        atr_avg  = atr_vals.rolling(self.period).mean()
        high_vol = atr_vals > atr_avg   # True when market is more volatile than usual

        close  = df["Close"]
        signal = pd.Series(0.0, index=df.index)

        signal[(close > rolling_high) & high_vol] =  1.0   # breakout + expanding vol
        signal[(close < rolling_low)  & high_vol] = -1.0   # breakdown + expanding vol
        signal[rolling_high.isna() | atr_avg.isna()] = 0.0 # zero during warmup

        return signal
