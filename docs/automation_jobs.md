# Automation Jobs

This repo includes an automation entrypoint:

- `scripts/automation_jobs.py`

## Jobs

- `nightly`: full research refresh
- `promotion`: promote active strategy set
- `execute`: run current active runner config

## Core Commands

```bash
python scripts/automation_jobs.py --job nightly
python scripts/automation_jobs.py --job promotion
python scripts/automation_jobs.py --job execute
python scripts/automation_jobs.py --job execute --execute-dry-run
```

## Multi-Book Setup (Aggressive + Defensive)

Use separate configs, generated outputs, and report dirs to keep books isolated.

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

## Reports

Reports are written to the configured `--report-dir`:

- `latest_nightly.md`
- `latest_promotion.md`
- `latest_execute.md`
- timestamped `.md` and `.json` files

## Notifications

Enabled by default and loaded from `--config` notifications settings.

Disable per run:

```bash
python scripts/automation_jobs.py --job nightly --no-notify
```

## Cron Examples (America/New_York)

```cron
CRON_TZ=America/New_York

# Aggressive: nightly research
15 20 * * 1-5 cd /home/trading/trading-strategies && . .venv/bin/activate && python scripts/automation_jobs.py --job nightly --config runner_config.aggressive.yaml --selected-output generated/aggressive/selected_strategies.yaml --resolved-config generated/aggressive/runner_config.auto.yaml --manual-override generated/aggressive/manual_override.yaml --report-dir logs/automation/aggressive --selection-mode per_symbol --top-n-per-symbol 1 --max-total-allocations 10 >> logs/automation/aggressive/nightly_cron.log 2>&1

# Aggressive: daily execution
35 9 * * 1-5 cd /home/trading/trading-strategies && . .venv/bin/activate && python scripts/automation_jobs.py --job execute --config runner_config.aggressive.yaml --resolved-config generated/aggressive/runner_config.auto.yaml --report-dir logs/automation/aggressive >> logs/automation/aggressive/execute_cron.log 2>&1

# Defensive: nightly research
20 20 * * 1-5 cd /home/trading/trading-strategies && . .venv/bin/activate && python scripts/automation_jobs.py --job nightly --config runner_config.defensive.yaml --selected-output generated/defensive/selected_strategies.yaml --resolved-config generated/defensive/runner_config.auto.yaml --manual-override generated/defensive/manual_override.yaml --report-dir logs/automation/defensive --selection-mode global --top-k-global 3 >> logs/automation/defensive/nightly_cron.log 2>&1

# Defensive: daily execution
40 9 * * 1-5 cd /home/trading/trading-strategies && . .venv/bin/activate && python scripts/automation_jobs.py --job execute --config runner_config.defensive.yaml --resolved-config generated/defensive/runner_config.auto.yaml --report-dir logs/automation/defensive >> logs/automation/defensive/execute_cron.log 2>&1
```
