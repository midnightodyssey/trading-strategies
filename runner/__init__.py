# runner — Daily strategy runner for IBKR paper and live accounts.
#
# Typical usage:
#   python -m runner.daily_runner                    # uses runner_config.yaml
#   python -m runner.daily_runner --config path.yaml # custom config path
#   python -m runner.daily_runner --dry-run          # signals only, no orders
#
# Programmatic usage:
#   from runner import DailyRunner
#   DailyRunner("runner_config.yaml").run()

from .daily_runner  import DailyRunner
from .runner_config import RunnerConfig, StrategySpec
from .notifier      import Notifier
