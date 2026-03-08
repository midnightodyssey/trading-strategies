# Automation Jobs
*Source: `scripts/automation_jobs.py`*
*Category: Automation*
*Depth: Balanced*
*Generated: 2026-03-08*

---

## Purpose

This document is the canonical runbook for scheduled jobs.

Use `scripts/automation_jobs.py` for all recurring tasks:

- `nightly` (research refresh)
- `promotion` (strategy-set promotion)
- `execute` (actual book execution)

---

## Runtime Guide

Estimated runtimes (depends on symbol count and VPS/network conditions):

- `nightly`: 5-25 minutes
- `promotion`: 30-180 seconds
- `execute`: 10-120 seconds

Recommendations:

- Keep at least 15 minutes between nightly jobs across books.
- Keep at least 5 minutes between execute jobs across books.
- Schedule promotion after nightly windows complete.

---

## Job Matrix

| Job | What it does | Typical use |
|---|---|---|
| `nightly` | Backtest + selection + auto config generation | Weeknights research refresh |
| `promotion` | Refresh selected strategy set from latest artifacts | Weekly governance update |
| `execute` | Runs `runner-only` using resolved config | Trading-day execution |

---

## Core Commands

```bash
python scripts/automation_jobs.py --job nightly
python scripts/automation_jobs.py --job promotion
python scripts/automation_jobs.py --job execute
python scripts/automation_jobs.py --job execute --execute-dry-run
```

---

## Multi-Book Configuration

Use isolated files per book so outputs never collide.

### Aggressive book

```bash
python scripts/automation_jobs.py --job nightly \
  --config runner_config.aggressive.yaml \
  --selected-output generated/aggressive/selected_strategies.yaml \
  --resolved-config generated/aggressive/runner_config.auto.yaml \
  --manual-override generated/aggressive/manual_override.yaml \
  --report-dir logs/automation/aggressive \
  --selection-mode per_symbol --top-n-per-symbol 1 --max-total-allocations 10
```

### Defensive book

```bash
python scripts/automation_jobs.py --job nightly \
  --config runner_config.defensive.yaml \
  --selected-output generated/defensive/selected_strategies.yaml \
  --resolved-config generated/defensive/runner_config.auto.yaml \
  --manual-override generated/defensive/manual_override.yaml \
  --report-dir logs/automation/defensive \
  --selection-mode global --top-k-global 3
```

---

## Reports and Notifications

Reports are written to `--report-dir`:

- `latest_nightly.md`
- `latest_promotion.md`
- `latest_execute.md`
- timestamped `.md` and `.json`

Notifications:

- Enabled by default
- Loaded from the selected `--config` file
- Disable with `--no-notify`

Example:

```bash
python scripts/automation_jobs.py --job nightly --no-notify
```

---

## Canonical Cron (America/New_York)

Paste this block into `crontab -e`:

```crontab -e
CRON_TZ=America/New_York

# Aggressive book — nightly research refresh at 8:15 PM ET (Mon-Fri)
15 20 * * 1-5 cd /home/trading/trading-strategies && . .venv/bin/activate && python scripts/automation_jobs.py --job nightly --config runner_config.aggressive.yaml --selected-output generated/aggressive/selected_strategies.yaml --resolved-config generated/aggressive/runner_config.auto.yaml --manual-override generated/aggressive/manual_override.yaml --report-dir logs/automation/aggressive --selection-mode per_symbol --top-n-per-symbol 1 --max-total-allocations 10 >> logs/automation/aggressive/nightly_cron.log 2>&1

# Defensive book — nightly research refresh at 9:20 PM ET (Mon-Fri)
20 21 * * 1-5 cd /home/trading/trading-strategies && . .venv/bin/activate && python scripts/automation_jobs.py --job nightly --config runner_config.defensive.yaml --selected-output generated/defensive/selected_strategies.yaml --resolved-config generated/defensive/runner_config.auto.yaml --manual-override generated/defensive/manual_override.yaml --report-dir logs/automation/defensive --selection-mode global --top-k-global 3 >> logs/automation/defensive/nightly_cron.log 2>&1

# Aggressive book — weekly promotion at 6:00 PM ET (Sunday)
0 18 * * 0 cd /home/trading/trading-strategies && . .venv/bin/activate && python scripts/automation_jobs.py --job promotion --config runner_config.aggressive.yaml --selected-output generated/aggressive/selected_strategies.yaml --resolved-config generated/aggressive/runner_config.auto.yaml --manual-override generated/aggressive/manual_override.yaml --report-dir logs/automation/aggressive --selection-mode per_symbol --top-n-per-symbol 1 --max-total-allocations 10 >> logs/automation/aggressive/promotion_cron.log 2>&1

# Defensive book — weekly promotion at 6:10 PM ET (Sunday)
10 18 * * 0 cd /home/trading/trading-strategies && . .venv/bin/activate && python scripts/automation_jobs.py --job promotion --config runner_config.defensive.yaml --selected-output generated/defensive/selected_strategies.yaml --resolved-config generated/defensive/runner_config.auto.yaml --manual-override generated/defensive/manual_override.yaml --report-dir logs/automation/defensive --selection-mode global --top-k-global 3 >> logs/automation/defensive/promotion_cron.log 2>&1

# Aggressive book — execution at 9:35 AM ET (Mon-Fri)
35 9 * * 1-5 cd /home/trading/trading-strategies && . .venv/bin/activate && python scripts/automation_jobs.py --job execute --config runner_config.aggressive.yaml --resolved-config generated/aggressive/runner_config.auto.yaml --report-dir logs/automation/aggressive >> logs/automation/aggressive/execute_cron.log 2>&1

# Defensive book — execution at 9:40 AM ET (Mon-Fri)
40 9 * * 1-5 cd /home/trading/trading-strategies && . .venv/bin/activate && python scripts/automation_jobs.py --job execute --config runner_config.defensive.yaml --resolved-config generated/defensive/runner_config.auto.yaml --report-dir logs/automation/defensive >> logs/automation/defensive/execute_cron.log 2>&1
```

---

## Validation Checklist

After any cron edit:

```bash
crontab -l
```

Smoke tests:

```bash
python scripts/automation_jobs.py --job promotion --config runner_config.aggressive.yaml --selected-output generated/aggressive/selected_strategies.yaml --resolved-config generated/aggressive/runner_config.auto.yaml --manual-override generated/aggressive/manual_override.yaml --report-dir logs/automation/aggressive --no-notify

python scripts/automation_jobs.py --job execute --config runner_config.aggressive.yaml --resolved-config generated/aggressive/runner_config.auto.yaml --report-dir logs/automation/aggressive --execute-dry-run --no-notify
```
