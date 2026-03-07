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
