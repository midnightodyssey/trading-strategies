# Automation Jobs

This repo now includes an automation entrypoint:

- `scripts/automation_jobs.py`

## Jobs

- `nightly`: full research refresh
  - runs backtest + strategy selection + auto config generation
- `promotion`: promote active strategy set
  - by default uses latest backtest artifacts and re-generates selection/config
  - optionally can recompute backtest first
- `execute`: run the current active runner config
  - this is the actual trading execution job
  - supports dry-run safety mode

## Commands

```bash
# Nightly research refresh
python scripts/automation_jobs.py --job nightly --selection-mode global --top-k-global 3

# Weekly promotion from latest artifacts
python scripts/automation_jobs.py --job promotion --selection-mode per_symbol --top-n-per-symbol 1 --max-total-allocations 12

# Promotion with fresh backtest first
python scripts/automation_jobs.py --job promotion --promotion-recompute-backtest --selection-mode per_symbol --top-n-per-symbol 1 --max-total-allocations 12

# Actual execution (places orders if mode=live)
python scripts/automation_jobs.py --job execute

# Execution safety test (no orders)
python scripts/automation_jobs.py --job execute --execute-dry-run
```

## Reports

Reports are written to:

- `logs/automation/latest_nightly.md`
- `logs/automation/latest_promotion.md`
- `logs/automation/latest_execute.md`
- timestamped `.md` and `.json` files in `logs/automation/`

## Notifications

By default, notifications are enabled and use `runner_config.yaml` notification settings.

Disable notifications per run:

```bash
python scripts/automation_jobs.py --job nightly --no-notify
```

## Cron Examples (America/New_York)

```cron
CRON_TZ=America/New_York

# Nightly research (Mon-Fri) at 8:15 PM ET (global top-3)
15 20 * * 1-5 cd /home/trading/trading-strategies && . .venv/bin/activate && python scripts/automation_jobs.py --job nightly --selection-mode global --top-k-global 3 >> logs/automation/nightly_cron.log 2>&1

# Weekly promotion (Sunday) at 6:00 PM ET (per-symbol, 1 each, capped at 12)
0 18 * * 0 cd /home/trading/trading-strategies && . .venv/bin/activate && python scripts/automation_jobs.py --job promotion --selection-mode per_symbol --top-n-per-symbol 1 --max-total-allocations 12 >> logs/automation/promotion_cron.log 2>&1

# Monthly promotion (1st day of month) at 6:00 PM ET with fresh backtest
0 18 1 * * cd /home/trading/trading-strategies && . .venv/bin/activate && python scripts/automation_jobs.py --job promotion --promotion-recompute-backtest --selection-mode per_symbol --top-n-per-symbol 1 --max-total-allocations 12 >> logs/automation/promotion_monthly_cron.log 2>&1

# Daily execution (Mon-Fri) at 9:35 AM ET
35 9 * * 1-5 cd /home/trading/trading-strategies && . .venv/bin/activate && python scripts/automation_jobs.py --job execute >> logs/automation/execute_cron.log 2>&1
```
