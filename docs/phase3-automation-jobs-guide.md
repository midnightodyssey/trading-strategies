# Phase 3 Automation Jobs - Concept Guide

*Category: Automation*
*Depth: Balanced*
*Generated: 2026-03-08*

---

## Why Automation Layer Exists

### What It Is
The automation layer standardizes recurring research, promotion, and execution workflows behind one entrypoint.

### The Intuition
A single operator command surface reduces drift between manual and scheduled runs, and improves auditability through consistent reports.

---

## Job Types

### What It Is
`automation_jobs.py` supports:

- `nightly` - full research refresh
- `promotion` - update active strategy set
- `execute` - run active execution config

### In the Code
```bash
python scripts/automation_jobs.py --job nightly
python scripts/automation_jobs.py --job promotion
python scripts/automation_jobs.py --job execute
```

---

## Job Semantics

### Nightly
Runs backtest + selection + config generation.

### Promotion
By default uses latest artifacts and runs selection/config refresh.

Optional:

- `--promotion-recompute-backtest` for a fresh research pass
- `--promotion-runner` for post-promotion dry-run verification

### Execute
Runs `phase3_auto_pipeline.py --runner-only`.

Optional:

- `--execute-dry-run` for no-order safety testing

---

## Reporting and Notifications

### What It Is
Every job writes timestamped JSON + Markdown reports.

### Output Paths
- `logs/automation/latest_nightly.md`
- `logs/automation/latest_promotion.md`
- `logs/automation/latest_execute.md`
- timestamped `.json` and `.md` files

### Notifications
By default jobs notify via existing `runner_config.yaml` notification settings.

Disable per run with:

```bash
python scripts/automation_jobs.py --job nightly --no-notify
```

---

## Scheduling Pattern (Cron)

### What It Is
Typical cadence:

- Weeknights: research refresh
- Weekly/Monthly: promotion refresh
- Trading days at market open: execution

### Example
```cron
CRON_TZ=America/New_York
15 20 * * 1-5 cd /home/trading/trading-strategies && . .venv/bin/activate && python scripts/automation_jobs.py --job nightly --selection-mode global --top-k-global 3 >> logs/automation/nightly_cron.log 2>&1
0 18 * * 0 cd /home/trading/trading-strategies && . .venv/bin/activate && python scripts/automation_jobs.py --job promotion --selection-mode per_symbol --top-n-per-symbol 1 --max-total-allocations 12 >> logs/automation/promotion_cron.log 2>&1
35 9 * * 1-5 cd /home/trading/trading-strategies && . .venv/bin/activate && python scripts/automation_jobs.py --job execute >> logs/automation/execute_cron.log 2>&1
```

