"""
framework/strategies/base.py
─────────────────────────────────────────────────────────────────────────────
Abstract base class that every strategy must inherit from.

Why a base class?
    1. Enforces a consistent interface — every strategy MUST implement
       generate_signals(). If it doesn't, Python raises an error at
       instantiation time, not at runtime after hours of execution.
    2. Provides run() for free — one line of code runs a full backtest.
    3. Makes strategies composable — you can loop over a list of strategies,
       call .run() on each, and compare results without knowing the
       implementation details of any of them.
"""

from abc import ABC, abstractmethod
import pandas as pd

from ..backtest import run_backtest, BacktestResult


class Strategy(ABC):
    """
    Abstract base class for all trading strategies.

    Subclass this and implement generate_signals() to create a strategy.

    Example:
        class MyStrategy(Strategy):
            def generate_signals(self, df):
                # your logic here
                return pd.Series(...)

        result = MyStrategy().run(df)
    """

    @property
    def name(self) -> str:
        """Human-readable name — defaults to the class name."""
        return self.__class__.__name__

    @abstractmethod
    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        """
        Generate a position signal for every bar in the DataFrame.

        This is the ONLY method you must implement. Everything else
        (backtesting, metrics, reporting) is handled by the base class.

        Signal convention:
             1  = long  (hold for the next bar)
             0  = flat  (no position)
            -1  = short (hold short for the next bar)

        Rules:
            - Return a pd.Series with the same index as df
            - No NaN values (use 0 where there's insufficient history)
            - Only use information available up to and including bar t
              (no look-ahead — the backtest engine already applies a 1-bar
               lag, so your signal at bar t becomes a position at bar t+1)

        Args:
            df: OHLCV DataFrame with DatetimeIndex, as produced by data.py

        Returns:
            pd.Series of signals: values in {-1, 0, 1}
        """
        ...

    def run(
        self,
        df:             pd.DataFrame,
        slippage:       float = 0.0005,
        commission:     float = 0.001,
        risk_free_rate: float = 0.05,
    ) -> BacktestResult:
        """
        Generate signals and run a full backtest in one call.

        This is the main entry point for evaluating a strategy.

        Args:
            df:             OHLCV DataFrame (must have at least a "Close" column)
            slippage:       per-side slippage as a fraction (default 5 bps)
            commission:     round-trip commission (default 10 bps)
            risk_free_rate: annual risk-free rate for Sharpe/Sortino

        Returns:
            BacktestResult with equity curve, returns, and all six risk metrics
        """
        signals = self.generate_signals(df)
        return run_backtest(
            signals,
            df["Close"],
            slippage=slippage,
            commission=commission,
            risk_free_rate=risk_free_rate,
        )
