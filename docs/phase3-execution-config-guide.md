# Phase 3 Execution Config Output - Concept Guide

*Category: Execution*
*Depth: Balanced*
*Generated: 2026-03-08*

---

## Why Execution Config Exists

### What It Is
Execution config output is the bridge between research selection and live runner behavior.

### The Intuition
Keep selection logic and execution logic decoupled. The runner should consume a stable config contract, not raw research artifacts.

---

## Generated Files

### What It Is
Phase 3 writes three key files:

- `generated/selected_strategies.yaml`
- `generated/runner_config.auto.yaml`
- `generated/manual_override.yaml`

### How It Works
`runner_config.auto.yaml` is built from base config + selected strategies + metadata and is directly usable by `runner.daily_runner`.

### In the Code
```bash
python scripts/phase3_auto_pipeline.py --selection-only
```

---

## Runner Contract

### What It Is
The runner consumes `strategies` from generated config exactly like any manual config.

### Additional Metadata
Execution config also embeds:

- `execution_plan.selected_allocations`
- `auto_selection` (source run, rules, mode, risk budget)
- `manual_override` (state and mode)

### In the Code
```bash
python scripts/phase3_auto_pipeline.py --runner-only
```

---

## Manual Override Layer

### What It Is
A controlled override file for temporary discretionary control.

### How It Works
`generated/manual_override.yaml` supports:

- `enabled: true|false`
- `mode: replace|append`
- `strategies` list
- optional `selected_allocations`

### Watch Out For
`enabled: true` can supersede auto-selected output. Keep this explicit and audited.

---

## Safety and Validation

### Recommended Workflow
1. Materialize config (`--selection-only`)
2. Validate runner behavior (`--runner-only --dry-run`)
3. Switch to live execution only after dry-run checks pass

### In the Code
```bash
python scripts/phase3_auto_pipeline.py --selection-only
python scripts/phase3_auto_pipeline.py --runner-only --dry-run
```

