"""Trading Framework package exports."""

from .backtest import run_option_strategy_backtest
from .derivatives import (
    Greeks,
    OptionContract,
    black_scholes_greeks,
    black_scholes_price,
    implied_volatility,
    year_fraction_to_expiry,
)
from .derivatives_data import OptionQuote, fetch_option_chain_yfinance, normalize_option_chain
from .derivatives_selection import (
    ContractSelectionRule,
    VerticalSpreadRule,
    select_contract_by_delta,
    select_vertical_spread_legs,
)
from .derivatives_strategies import (
    OptionLeg,
    OptionStrategyPosition,
    bull_call_spread,
    covered_call,
    protective_put,
    strategy_mark_to_market,
    strategy_payoff_at_expiry,
)

__all__ = [
    "Greeks",
    "OptionContract",
    "OptionQuote",
    "OptionLeg",
    "OptionStrategyPosition",
    "ContractSelectionRule",
    "VerticalSpreadRule",
    "black_scholes_greeks",
    "black_scholes_price",
    "implied_volatility",
    "year_fraction_to_expiry",
    "normalize_option_chain",
    "fetch_option_chain_yfinance",
    "select_contract_by_delta",
    "select_vertical_spread_legs",
    "covered_call",
    "protective_put",
    "bull_call_spread",
    "strategy_mark_to_market",
    "strategy_payoff_at_expiry",
    "run_option_strategy_backtest",
]
