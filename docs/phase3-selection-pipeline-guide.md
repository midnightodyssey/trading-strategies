# Phase 3 Selection Pipeline - Concept Guide

*Category: Analysis*
*Depth: Balanced*
*Generated: 2026-03-08*

---

## Pipeline Overview

### What It Is
The selection pipeline converts research outputs into an active strategy configuration.

### The Intuition
Separate research and execution concerns:

1. Generate comparable strategy evidence
2. Rank and constrain selection
3. Emit a clean config contract for the runner

---

## Stage 1 - Backtest Artifacts

### What It Is
`backtest_pipeline.py` creates text + structured artifacts for each run.

### How It Works
Artifacts are written to:

- `artifacts/backtests/<run_id>/strategy_summary.csv`
- `artifacts/backtests/<run_id>/strategy_metrics_long.csv`
- `artifacts/backtests/<run_id>/sharpe_matrix.csv`

### In the Code
```bash
python scripts/backtest_pipeline.py file
```

### Watch Out For
No backtest artifacts means promotion/selection-only jobs cannot run unless recompute mode is enabled.

---

## Stage 2 - Strategy Selection

### What It Is
`select_strategies.py` scores candidates, applies filters, applies diversification, and emits output.

### Key Controls
- selection mode and top counts
- min Sharpe/trades/symbol coverage
- diversification threshold
- allocation caps

### In the Code
```bash
python scripts/select_strategies.py --selection-mode global --top-k-global 3
```

### Watch Out For
Strict thresholds can collapse candidate count; fallback behavior still emits a valid set.

---

## Stage 3 - Config Materialization

### What It Is
`phase3_auto_pipeline.py` turns selection output into runner-consumable config.

### How It Works
Writes:

- `generated/selected_strategies.yaml`
- `generated/runner_config.auto.yaml`
- `generated/manual_override.yaml` (template)

### In the Code
```bash
python scripts/phase3_auto_pipeline.py --selection-only
python scripts/phase3_auto_pipeline.py --runner-only --dry-run
```

### Watch Out For
`--selection-only` and `--runner-only` are intentionally mutually exclusive.

---

## Operational Modes

### What It Is
Pipeline orchestration supports three practical modes:

- full refresh: backtest + select + config
- selection refresh: select + config
- execution only: run existing generated config

### In the Code
```bash
python scripts/phase3_auto_pipeline.py
python scripts/phase3_auto_pipeline.py --selection-only
python scripts/phase3_auto_pipeline.py --runner-only
```

