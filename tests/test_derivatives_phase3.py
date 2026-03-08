from datetime import date

import pandas as pd

from framework.broker.options import (
    option_contract_from_intent,
    option_order_from_intent,
    strategy_position_to_option_intents,
)
from framework.derivatives import OptionContract
from framework.derivatives_data import normalize_option_chain
from framework.derivatives_selection import (
    ContractSelectionRule,
    VerticalSpreadRule,
    select_contract_by_delta,
    select_vertical_spread_legs,
)
from framework.derivatives_strategies import OptionLeg, OptionStrategyPosition


def test_normalize_option_chain_expected_columns() -> None:
    calls = pd.DataFrame(
        {
            "strike": [100, 105],
            "bid": [2.2, 1.5],
            "ask": [2.4, 1.7],
            "lastPrice": [2.3, 1.6],
            "impliedVolatility": [0.21, 0.23],
            "openInterest": [1200, 950],
            "volume": [340, 220],
            "delta": [0.55, 0.42],
        }
    )
    puts = pd.DataFrame(
        {
            "strike": [95, 100],
            "bid": [1.1, 1.8],
            "ask": [1.3, 2.0],
            "lastPrice": [1.2, 1.9],
            "impliedVolatility": [0.24, 0.22],
            "openInterest": [700, 1100],
            "volume": [140, 260],
            "delta": [-0.28, -0.45],
        }
    )

    out = normalize_option_chain(calls, puts, expiry=date(2026, 12, 18))
    assert len(out) == 4
    assert "option_type" in out.columns
    assert "implied_volatility" in out.columns
    assert "open_interest" in out.columns
    assert set(out["option_type"].unique()) == {"call", "put"}


def test_select_contract_by_delta_and_vertical_legs() -> None:
    chain = pd.DataFrame(
        {
            "symbol": ["AAPL"] * 4,
            "option_type": ["call", "call", "call", "put"],
            "strike": [100.0, 105.0, 110.0, 95.0],
            "expiry": [date(2026, 12, 18)] * 4,
            "bid": [3.0, 2.1, 1.3, 1.2],
            "ask": [3.2, 2.3, 1.5, 1.4],
            "last": [3.1, 2.2, 1.4, 1.3],
            "implied_volatility": [0.25, 0.24, 0.23, 0.26],
            "delta": [0.62, 0.49, 0.35, -0.32],
            "gamma": [0.01, 0.01, 0.01, 0.01],
            "theta": [-0.02, -0.02, -0.02, -0.02],
            "vega": [0.12, 0.11, 0.1, 0.09],
            "open_interest": [500, 1200, 900, 450],
            "volume": [100, 230, 180, 75],
        }
    )

    rule = ContractSelectionRule(option_type="call", target_delta=0.5, min_dte=7, max_dte=365)
    selected = select_contract_by_delta(chain, rule, as_of=date(2026, 6, 1))
    assert float(selected["strike"]) == 105.0

    spread_rule = VerticalSpreadRule(long_leg=rule, short_target_delta=0.35)
    long_leg, short_leg = select_vertical_spread_legs(chain, spread_rule, as_of=date(2026, 6, 1))
    assert float(long_leg["strike"]) == 105.0
    assert float(short_leg["strike"]) > float(long_leg["strike"])


def test_option_order_intent_mapping_from_strategy_position() -> None:
    expiry = date(2026, 12, 18)
    long_call = OptionLeg(
        contract=OptionContract(symbol="AAPL", option_type="call", strike=100.0, expiry=expiry),
        quantity=1,
    )
    short_call = OptionLeg(
        contract=OptionContract(symbol="AAPL", option_type="call", strike=110.0, expiry=expiry),
        quantity=-1,
    )
    pos = OptionStrategyPosition(
        name="TestSpread",
        symbol="AAPL",
        underlying_shares=0,
        option_legs=(long_call, short_call),
    )

    intents = strategy_position_to_option_intents(pos, action="open", order_type="LMT", limit_price=1.25)
    assert len(intents) == 2
    assert {i.action for i in intents} == {"BUY", "SELL"}

    contract = option_contract_from_intent(intents[0])
    order = option_order_from_intent(intents[0])
    assert contract.symbol == "AAPL"
    assert hasattr(order, "orderType")
