"""
framework/strategies/crossover.py
─────────────────────────────────────────────────────────────────────────────
Moving average crossover strategies — the foundation of trend following.

Both strategies follow the same logic:
    Long  (+1): fast average is above slow average (uptrend)
    Short (-1): fast average is below slow average (downtrend)
    Flat  (0):  warmup period only (insufficient history)

The key difference: EMA reacts faster (more trades, more noise sensitivity),
SMA reacts slower (fewer trades, smoother signals).
"""

import pandas as pd

from .base import Strategy
from ..indicators import ema, sma


class EMACrossover(Strategy):
    """
    EMA Crossover — the most widely used trend-following entry system.

    How it works:
        The fast EMA tracks recent price action closely.
        The slow EMA tracks the longer-term trend.
        When fast crosses above slow → price is accelerating upward → long.
        When fast crosses below slow → price is accelerating downward → short.

    Why EMA over SMA?
        EMA weights recent prices more heavily, so it reacts faster to
        trend changes. You get earlier entries but more false signals.
        MACD (12/26) is literally just this crossover expressed differently.

    Default parameters (12/26):
        These are the MACD defaults — studied extensively and reasonably
        robust across asset classes. 9/21 is another common pairing.

    Weaknesses:
        - Whipsaws in range-bound markets (buys high, sells low repeatedly)
        - Always either long or short — no neutral position between crosses
        - Lagging by definition (can't know it's a trend until after the fact)

    Args:
        fast: fast EMA period (default 12)
        slow: slow EMA period (default 26)
    """

    def __init__(self, fast: int = 12, slow: int = 26):
        self.fast = fast
        self.slow = slow

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        fast_ema = ema(df["Close"], self.fast)
        slow_ema = ema(df["Close"], self.slow)

        signal = pd.Series(0.0, index=df.index)
        signal[fast_ema > slow_ema] =  1.0
        signal[fast_ema < slow_ema] = -1.0
        signal[fast_ema.isna() | slow_ema.isna()] = 0.0  # no signal during warmup

        return signal


class SMACrossover(Strategy):
    """
    SMA Crossover — slower and smoother than EMA, fewer false signals.

    Same logic as EMACrossover but uses simple (equal-weight) averages.
    Reacts more slowly to trend changes — better for higher timeframes.

    Classic pairs:
        20/50   — medium-term trend (popular on daily charts)
        50/200  — the "Golden Cross" / "Death Cross" (institutional benchmark)

    The Golden Cross (50 SMA crossing above 200 SMA) is watched by every
    institutional trader and often becomes a self-fulfilling prophecy.

    Args:
        fast: fast SMA period (default 20)
        slow: slow SMA period (default 50)
    """

    def __init__(self, fast: int = 20, slow: int = 50):
        self.fast = fast
        self.slow = slow

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        fast_sma = sma(df["Close"], self.fast)
        slow_sma = sma(df["Close"], self.slow)

        signal = pd.Series(0.0, index=df.index)
        signal[fast_sma > slow_sma] =  1.0
        signal[fast_sma < slow_sma] = -1.0
        signal[fast_sma.isna() | slow_sma.isna()] = 0.0  # no signal during warmup

        return signal
