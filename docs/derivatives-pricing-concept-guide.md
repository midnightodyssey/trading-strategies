# Derivatives Pricing - Concept Guide

*Category: Framework*
*Depth: Balanced*
*Generated: 2026-03-08*

---

## OptionContract and Greeks

### What It Is
`framework/derivatives.py` introduces the core option primitives:
- `OptionContract` for contract identity (symbol, right, strike, expiry, multiplier)
- `Greeks` for first-order risk measures (delta, gamma, theta, vega, rho)

### How It Works
The dataclasses are intentionally lightweight and immutable-friendly, so they can be passed through strategy, analytics, and execution layers without mutation side effects.

### The Intuition
This is the options equivalent of having a clean `Bar` schema in a data pipeline. If contract identity is inconsistent, every downstream metric becomes unreliable.

---

## Black-Scholes Pricing and Greeks

### What It Is
The pricing layer adds:
- `black_scholes_price(...)`
- `black_scholes_greeks(...)`
- `year_fraction_to_expiry(...)`

### How It Works
Given spot, strike, tenor, risk-free rate, volatility, and option type:
1. Compute `d1`, `d2`
2. Price call/put from closed-form equations
3. Compute Greeks from analytical derivatives

### In the Code
```python
price = black_scholes_price(
    spot=100,
    strike=105,
    time_to_expiry_years=0.5,
    risk_free_rate=0.03,
    volatility=0.25,
    option_type="call",
)
greeks = black_scholes_greeks(...)
```

### Watch Out For
- Time-to-expiry must be non-negative.
- Volatility must be strictly positive.
- Output is model value, not guaranteed executable fill.

---

## Implied Volatility Solver

### What It Is
`implied_volatility(...)` recovers sigma from observed option price using a robust bisection routine.

### How It Works
1. Bracket volatility bounds
2. Price option at midpoint
3. Narrow interval until tolerance reached

### The Intuition
IV is often the “market language” of options. Converting prices into IV lets you compare contracts across strikes/tenors on a normalized basis.

### Watch Out For
- If market price is inconsistent with no-arbitrage bounds, the solver raises.
- Deep ITM/OTM options can be numerically sensitive.

---

## Where It Fits

`derivatives.py` is now the base dependency for:
- strategy valuation (`derivatives_strategies.py`)
- chain selection workflows (`derivatives_selection.py`)
- execution intent construction (`broker/options.py`)

It should remain pure analytics (no broker/network side effects).

