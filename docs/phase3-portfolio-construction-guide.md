# Phase 3 Portfolio Construction - Concept Guide

*Category: Analysis*
*Depth: Balanced*
*Generated: 2026-03-08*

---

## Why This Layer Exists

### What It Is
The portfolio construction layer turns raw backtest outcomes into a constrained, deployable strategy set. It decides what gets selected, how concentrated the final plan is allowed to be, and how strategy overlap is controlled.

### The Intuition
Ranking by Sharpe alone often over-concentrates into correlated ideas. This layer adds practical construction rules so output is not just high-scoring, but also diversified and budget-aware.

---

## Selection Mode

### What It Is
Two selection scopes are supported:

- `global`: top K strategies across the whole universe
- `per_symbol`: top N strategies within each symbol

### How It Works
Mode is controlled by `--selection-mode` and tuned by:

- `--top-k-global`
- `--top-n-per-symbol`
- `--max-total-allocations`

### In the Code
```bash
python scripts/select_strategies.py --selection-mode global --top-k-global 3
python scripts/select_strategies.py --selection-mode per_symbol --top-n-per-symbol 1
```

### Watch Out For
`per_symbol` can increase the number of unique strategies quickly; always pair it with `--max-total-allocations`.

---

## Diversification Filter

### What It Is
A correlation-based filter that avoids selecting tightly clustered strategies.

### How It Works
The selector computes strategy correlation from `sharpe_matrix.csv` and skips candidates above `--corr-threshold`.

### In the Code
```bash
python scripts/select_strategies.py --selection-mode global --top-k-global 5 --corr-threshold 0.75
```

### Watch Out For
The correlation proxy is based on cross-symbol Sharpe profiles, not full return covariance. It is a practical filter, not a full risk model.

---

## Risk Budget Constraints

### What It Is
Constraint layer for allocation concentration.

### How It Works
These caps are applied to generated allocation output:

- `--max-symbol-weight`
- `--max-strategy-weight`
- `--max-total-allocations`

Weights are re-normalized after caps.

### In the Code
```bash
python scripts/select_strategies.py \
  --selection-mode per_symbol \
  --top-n-per-symbol 1 \
  --max-total-allocations 12 \
  --max-symbol-weight 0.30 \
  --max-strategy-weight 0.25
```

### Watch Out For
If your filters are strict and candidates are sparse, fallback logic may still return lower-quality but valid selections.

---

## Output Contract

### What It Is
Portfolio construction writes machine-readable outputs used downstream.

### Output Fields
- `selection_mode`
- `selection_rules`
- `risk_budget`
- `selected_strategies`
- `selected_allocations`

### Artifact
`generated/selected_strategies.yaml`

