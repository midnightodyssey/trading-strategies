from datetime import date

import pandas as pd

from framework.backtest import BacktestResult, run_option_strategy_backtest
from framework.derivatives_strategies import (
    bull_call_spread,
    covered_call,
    protective_put,
    strategy_payoff_at_expiry,
)


def test_covered_call_caps_upside() -> None:
    pos = covered_call(symbol="AAPL", strike=100.0, expiry=date(2026, 12, 18), shares=100, contracts=1)
    stock_only = 140.0 * 100.0
    covered = strategy_payoff_at_expiry(pos, terminal_spot=140.0)
    assert covered < stock_only


def test_protective_put_has_floor() -> None:
    pos = protective_put(symbol="AAPL", strike=100.0, expiry=date(2026, 12, 18), shares=100, contracts=1)
    payoff = strategy_payoff_at_expiry(pos, terminal_spot=60.0)
    assert payoff == 100.0 * 100.0


def test_bull_call_spread_payoff_is_bounded() -> None:
    pos = bull_call_spread(
        symbol="AAPL",
        long_strike=100.0,
        short_strike=120.0,
        expiry=date(2026, 12, 18),
        contracts=1,
    )
    high = strategy_payoff_at_expiry(pos, terminal_spot=250.0)
    higher = strategy_payoff_at_expiry(pos, terminal_spot=350.0)
    assert high == higher


def test_option_strategy_backtest_returns_backtestresult() -> None:
    idx = pd.date_range("2026-01-01", periods=30, freq="D")
    prices = pd.Series([100 + 0.5 * i for i in range(30)], index=idx)

    pos = covered_call(symbol="AAPL", strike=110.0, expiry=date(2026, 2, 28), shares=100, contracts=1)

    result = run_option_strategy_backtest(
        underlying_prices=prices,
        position=pos,
        volatility=0.25,
        risk_free_rate=0.03,
        dividend_yield=0.0,
    )

    assert isinstance(result, BacktestResult)
    assert len(result.returns) == len(prices)
    assert len(result.equity_curve) == len(prices)
    assert result.trades == 1
