# Derivatives Strategy and Backtest - Concept Guide

*Category: Strategies*
*Depth: Balanced*
*Generated: 2026-03-08*

---

## Strategy Primitives

### What It Is
`framework/derivatives_strategies.py` adds reusable position structures:
- `OptionLeg`
- `OptionStrategyPosition`
- builders: `covered_call`, `protective_put`, `bull_call_spread`

### How It Works
A strategy position is represented as:
- optional underlying share exposure
- one or more signed option legs (`+` long, `-` short)

### The Intuition
By making position structure explicit, payoff logic and mark-to-market logic become deterministic and testable.

---

## Valuation and Payoff

### What It Is
The module includes:
- `option_leg_value(...)`
- `strategy_mark_to_market(...)`
- `strategy_payoff_at_expiry(...)`

### How It Works
- MTM uses Black-Scholes values per leg plus underlying value.
- Expiry payoff uses intrinsic value only.

### In the Code
```python
pos = bull_call_spread("AAPL", 100, 110, expiry, contracts=1)
mtm = strategy_mark_to_market(pos, spot=104, as_of=today, volatility=0.24, risk_free_rate=0.03)
payoff = strategy_payoff_at_expiry(pos, terminal_spot=120)
```

---

## Option Strategy Backtesting

### What It Is
`framework/backtest.py` now includes `run_option_strategy_backtest(...)`.

### How It Works
1. Revalue full strategy each bar
2. Compute bar-to-bar PnL from MTM changes
3. Normalize by capital base
4. Build equity curve and risk metrics via `risk_summary(...)`

### Watch Out For
- This phase assumes fixed strategy definition through the backtest window.
- Volatility input can be constant or a daily series.
- Capital denominator selection materially changes reported return scale.

---

## Why This Matters

This layer bridges “options idea” and “portfolio-ready analytics” by making strategy-level return streams comparable with equity/futures strategy outputs already used in the framework.

