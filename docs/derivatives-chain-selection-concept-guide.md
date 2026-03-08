# Derivatives Chain and Selection - Concept Guide

*Category: Framework*
*Depth: Balanced*
*Generated: 2026-03-08*

---

## Chain Normalization

### What It Is
`framework/derivatives_data.py` introduces:
- `OptionQuote`
- `normalize_option_chain(calls, puts, expiry)`
- `fetch_option_chain_yfinance(symbol, expiry=None)`
- `days_to_expiry(...)`

### How It Works
Raw call/put tables are merged into a single standardized schema with consistent column names:
- `option_type`, `strike`, `expiry`, `bid`, `ask`, `last`
- optional analytics columns (IV/Greeks/OI/volume)

### The Intuition
Selection logic should depend on one normalized contract table, not provider-specific field names.

---

## Contract Selection Rules

### What It Is
`framework/derivatives_selection.py` adds rule-based selection:
- `ContractSelectionRule`
- `VerticalSpreadRule`
- `select_contract_by_delta(...)`
- `select_vertical_spread_legs(...)`

### How It Works
Filtering pipeline:
1. Filter by option right (`call`/`put`)
2. Filter by tenor (`min_dte`/`max_dte`)
3. Rank by delta closeness to target
4. Tie-break by nearer tenor and stronger liquidity signal (open interest)

### In the Code
```python
rule = ContractSelectionRule(option_type="call", target_delta=0.5, min_dte=14, max_dte=60)
leg = select_contract_by_delta(chain_df, rule, as_of=today)
```

---

## Vertical Leg Construction

### What It Is
`select_vertical_spread_legs(...)` picks long and short legs from the same normalized chain.

### How It Works
- First select long leg by target delta.
- Then select short leg by its own target delta.
- Enforce strike ordering for valid vertical structure.

### Watch Out For
- Missing delta falls back to near-ATM strike logic.
- Sparse chains can fail rule constraints and should be handled upstream with graceful fallback.

