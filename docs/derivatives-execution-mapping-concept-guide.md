# Derivatives Execution Mapping - Concept Guide

*Category: Execution*
*Depth: Balanced*
*Generated: 2026-03-08*

---

## Option Order Intent Layer

### What It Is
`framework/broker/options.py` adds a paper-safe mapping layer between strategy legs and broker-native orders:
- `OptionOrderIntent`
- `option_contract_from_intent(...)`
- `option_order_from_intent(...)`
- `strategy_position_to_option_intents(...)`
- `preview_option_orders(...)`

### How It Works
The module converts abstract position intent into:
1. IBKR option contract object
2. market/limit order object
without sending any order.

### The Intuition
Separating “build order” from “submit order” is a critical safety boundary for live systems.

---

## Strategy-to-Intent Translation

### What It Is
`strategy_position_to_option_intents(...)` maps a multi-leg strategy into actionable buy/sell intents.

### How It Works
- Signed leg quantities determine side (`BUY`/`SELL`).
- `action="open"` keeps direction.
- `action="close"` flips direction to flatten exposure.

### In the Code
```python
intents = strategy_position_to_option_intents(
    position,
    action="open",
    order_type="LMT",
    limit_price=1.25,
)
preview = preview_option_orders(intents)
```

---

## Risk and Validation Guards

### What It Is
The mapper validates key invariants:
- positive quantity
- valid limit price for `LMT`
- consistent contract field mapping (symbol/expiry/strike/right)

### Watch Out For
- This layer does not route combo orders yet; each leg is represented explicitly.
- Slippage/fill behavior is not simulated here; execution quality belongs in broker/fill analytics.

---

## Integration Point

The execution mapper is now exported in `framework/broker/__init__.py`, making it available to automation and runner layers for dry-run previews and eventual submit workflows.

