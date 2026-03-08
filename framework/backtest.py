"""
framework/backtest.py
â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
Vectorised backtesting engine.

Design principles:
  - No loops: every calculation is a pandas/numpy vectorised operation
  - Pure functions: same inputs always produce same outputs
  - Realistic costs: slippage + commission on every trade
  - Signal lag: signals are shifted by 1 bar to prevent look-ahead bias
  - Integrates with risk.py for full performance metrics

Build order: indicators â†’ risk â†’ [backtest] â†’ data â†’ strategies â†’ execution
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass

from .risk import risk_summary


TRADING_DAYS = 252


# â”€â”€â”€ RESULT CONTAINER â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


@dataclass
class BacktestResult:
    """
    Container for all backtest outputs.

    Why a dataclass?
        Keeps results structured â€” you can pass a BacktestResult to any
        reporting or plotting function without worrying about key names.

    Attributes:
        returns:      net daily strategy returns (after costs)
        equity_curve: cumulative equity curve starting at 1.0
        positions:    lagged position series (what you actually held each day)
        trades:       number of times position changed (entry or exit)
        metrics:      dict of risk metrics from risk_summary()
    """

    returns: pd.Series
    equity_curve: pd.Series
    positions: pd.Series
    trades: int
    metrics: dict


# â”€â”€â”€ CORE ENGINE â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def run_backtest(
    signals: pd.Series,
    prices: pd.Series,
    slippage: float = 0.0005,  # 5 bps per side (realistic for liquid futures)
    commission: float = 0.001,  # 10 bps round trip
    risk_free_rate: float = 0.05,
) -> BacktestResult:
    """
    Vectorised backtest engine.

    How it works:
        1. Align signals and prices to the same index
        2. Lag signals by 1 bar â€” prevents look-ahead bias
           (signal fires at close of day T â†’ position held from T to T+1)
        3. Compute gross returns: position Ã— next-day price return
        4. Identify position changes â†’ apply slippage + commission
        5. Build equity curve: cumulative product of (1 + net_return)
        6. Pass cleaned returns to risk_summary() for full metrics

    Signal convention:
         1  = long  (hold for the next bar)
         0  = flat  (no position)
        -1  = short (short for the next bar)
        Fractional values allowed, e.g. 0.5 = half-sized long.

    Cost model:
        Each time position changes by Î”, you pay:
            cost = Î” Ã— (2 Ã— slippage + commission)
        Costs are deducted from gross returns on the same bar.

    Args:
        signals:        pd.Series of position signals (âˆ’1 to 1), indexed by date
        prices:         pd.Series of asset prices, same index as signals
        slippage:       one-way slippage as fraction (default 0.05% = 5 bps)
        commission:     round-trip commission as fraction (default 0.1% = 10 bps)
        risk_free_rate: annual risk-free rate used in Sharpe/Sortino

    Returns:
        BacktestResult with returns, equity curve, positions, trade count, metrics
    """
    # â”€â”€ 1. Align index â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    signals, prices = signals.align(prices, join="inner")

    # â”€â”€ 2. Lag by 1 bar (no look-ahead bias) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    positions = signals.shift(1).fillna(0)

    # â”€â”€ 3. Gross daily returns â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    price_returns = prices.pct_change()  # daily % move of the asset
    gross_returns = positions * price_returns  # our P&L = position Ã— move

    # â”€â”€ 4. Trading costs â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    #    Every time the position changes, we incur slippage + commission.
    #    abs(diff) captures both entries and exits regardless of direction.
    position_changes = positions.diff().abs().fillna(0)
    trade_costs = position_changes * (2 * slippage + commission)
    net_returns = gross_returns - trade_costs

    # â”€â”€ 5. Equity curve â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    equity_curve = (1 + net_returns).cumprod()

    # â”€â”€ 6. Trade count â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    trades = int((position_changes > 0).sum())

    # â”€â”€ 7. Risk metrics â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    metrics = risk_summary(net_returns.dropna(), risk_free_rate)

    return BacktestResult(
        returns=net_returns,
        equity_curve=equity_curve,
        positions=positions,
        trades=trades,
        metrics=metrics,
    )


# â”€â”€â”€ WALK-FORWARD VALIDATION â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def walk_forward(
    signals: pd.Series,
    prices: pd.Series,
    n_splits: int = 5,
    train_pct: float = 0.7,
    slippage: float = 0.0005,
    commission: float = 0.001,
    risk_free_rate: float = 0.05,
) -> list:
    """
    Walk-forward validation â€” backtest on rolling out-of-sample windows.

    Why this matters:
        A single full-history backtest always looks good â€” you've implicitly
        fitted the strategy to all the data you're testing on. Walk-forward
        splits the data into N windows and only reports results on the TEST
        portion (the future that the strategy never "saw").

        This is the closest thing to live performance you can get from
        historical data. Prop firms care about OOS Sharpe, not in-sample.

    How it works:
        For each of N splits:
            1. Take a slice of size (total / N)
            2. The first train_pct of that slice is "training" (skipped here â€”
               use it to optimise parameters in your strategy)
            3. The remaining (1 - train_pct) is tested OOS
            4. Run a full backtest on the OOS slice

    Args:
        signals:    full signal series (all history)
        prices:     full price series (all history)
        n_splits:   number of train/test windows (default 5)
        train_pct:  fraction of each window used as training period (default 70%)
        slippage:   per-side slippage
        commission: round-trip commission
        risk_free_rate: annual risk-free rate

    Returns:
        List of BacktestResult â€” one per OOS test window
    """
    n = len(signals)
    window_size = n // n_splits
    results = []

    for i in range(n_splits):
        start = i * window_size
        end = start + window_size if i < n_splits - 1 else n
        train_end = start + int(window_size * train_pct)

        # Only test on the OOS portion
        test_signals = signals.iloc[train_end:end]
        test_prices = prices.iloc[train_end:end]

        if len(test_signals) < 2:
            continue

        result = run_backtest(
            test_signals, test_prices, slippage, commission, risk_free_rate
        )
        results.append(result)

    return results


# â”€â”€â”€ REPORTING â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def summary_table(result: BacktestResult) -> pd.Series:
    """
    Format a BacktestResult as a labelled pandas Series for display.

    Adds two extra fields beyond the standard risk metrics:
        Trades:       how many times position changed
        Final Equity: terminal value of Â£1 invested at the start

    Args:
        result: a BacktestResult from run_backtest()

    Returns:
        pd.Series â€” all metrics in one object, easy to compare side-by-side
    """
    data = dict(result.metrics)
    data["Trades"] = float(result.trades)
    data["Final Equity"] = round(float(result.equity_curve.dropna().iloc[-1]), 4)
    return pd.Series(data)


def run_option_strategy_backtest(
    underlying_prices: pd.Series,
    position,
    volatility: float | pd.Series,
    risk_free_rate: float = 0.05,
    dividend_yield: float = 0.0,
    capital_base: float | None = None,
) -> BacktestResult:
    """
    Mark-to-market backtest for a fixed options strategy position.

    Args:
        underlying_prices: Daily underlying close series (DatetimeIndex)
        position:          OptionStrategyPosition from derivatives_strategies.py
        volatility:        Constant vol or daily vol series (decimal, e.g. 0.25)
        risk_free_rate:    Annual risk-free rate for pricing + metrics
        dividend_yield:    Annual dividend yield used in option pricing
        capital_base:      Fixed denominator for return normalization.
                           If None, inferred from initial gross notional.

    Returns:
        BacktestResult with MTM-derived returns and risk metrics.
    """
    from .derivatives_strategies import strategy_mark_to_market

    if underlying_prices.empty:
        raise ValueError("underlying_prices must not be empty")

    prices = underlying_prices.sort_index().astype(float)

    if isinstance(volatility, pd.Series):
        vol_series = volatility.reindex(prices.index).ffill().bfill()
    else:
        vol_series = pd.Series(float(volatility), index=prices.index)

    mtm_values = []
    for dt, spot in prices.items():
        as_of = dt.date() if hasattr(dt, "date") else dt
        mtm = strategy_mark_to_market(
            position=position,
            spot=float(spot),
            as_of=as_of,
            volatility=float(vol_series.loc[dt]),
            risk_free_rate=risk_free_rate,
            dividend_yield=dividend_yield,
        )
        mtm_values.append(mtm)

    value = pd.Series(mtm_values, index=prices.index, name="strategy_value")
    pnl = value.diff().fillna(0.0)

    if capital_base is None:
        stock_notional = abs(float(position.underlying_shares) * float(prices.iloc[0]))
        option_notional = abs(float(value.iloc[0]))
        inferred = max(stock_notional, option_notional, 1.0)
        capital_base = inferred

    if capital_base <= 0:
        raise ValueError(f"capital_base must be > 0, got {capital_base}")

    returns = pnl / float(capital_base)
    equity_curve = (1.0 + returns).cumprod()

    metrics = risk_summary(returns.dropna(), risk_free_rate)

    positions = pd.Series(1.0, index=prices.index, name="position")
    trades = 1 if len(prices) > 0 else 0

    return BacktestResult(
        returns=returns,
        equity_curve=equity_curve,
        positions=positions,
        trades=trades,
        metrics=metrics,
    )
