# runner — Daily strategy runner for IBKR paper and live accounts.
#
# Typical usage:
#   python -m runner.daily_runner                    # uses runner_config.yaml
#   python -m runner.daily_runner --config path.yaml # custom config path
#   python -m runner.daily_runner --dry-run          # signals only, no orders
#
# Programmatic usage:
#   from runner.daily_runner import DailyRunner
#   DailyRunner("runner_config.yaml").run()

# NOTE: DailyRunner is intentionally NOT imported here at package level.
# Importing runner.daily_runner eagerly via __init__ causes a RuntimeWarning
# when running with `python -m runner.daily_runner` because Python loads
# daily_runner once as part of the package __init__, then again as __main__.
# Import it directly instead: from runner.daily_runner import DailyRunner

from .runner_config import RunnerConfig, StrategySpec
from .notifier      import Notifier
