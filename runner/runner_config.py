"""
runner/runner_config.py
─────────────────────────────────────────────────────────────────────────────
Configuration dataclasses for the daily strategy runner.

Load from YAML:
    config = RunnerConfig.from_yaml("runner_config.yaml")

Or build in code (useful for testing):
    config = RunnerConfig(mode="paper", symbols=["AAPL", "MSFT"])

Environment variable substitution is supported for secrets:
    password: "${IB_PASSWORD}"   →  reads os.environ["IB_PASSWORD"]

This means you can commit runner_config.yaml safely and keep credentials
in OS environment variables or a .env file (loaded externally).
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field, fields
from typing import Dict, List, Optional

import yaml


# ─── NESTED CONFIG SECTIONS ──────────────────────────────────────────────────

@dataclass
class ConnectionSettings:
    """
    IB Gateway / TWS connection parameters.

    Use gateway=True on a VPS (headless).
    Use gateway=False for local TWS development.
    client_id=10 avoids conflicts with manual TWS sessions (which use 1).
    """
    host:      str  = "127.0.0.1"
    gateway:   bool = True          # True = IB Gateway (headless, VPS-friendly)
    client_id: int  = 10            # Use 10+ to avoid clashing with manual sessions
    timeout:   int  = 30            # seconds to wait for connection


@dataclass
class ScheduleSettings:
    """
    Market timing and data parameters.

    data_source: where to fetch historical OHLCV bars.
                   "yahoo"  — Yahoo Finance via yfinance (default).
                              Free, no API key, no rate limits. Covers all
                              US equities, ETFs, indices. Adjust-split/dividend.
                              Ideal for any universe size.
                   "alpaca" — Alpaca Markets REST API.
                              Requires alpaca_api_key + alpaca_api_secret.
                              Free tier = 15-min delayed data. Paid = real-time.
                              pip install alpaca-py  before using.

    alpaca_api_key / alpaca_api_secret:
                   Alpaca credentials (only read when data_source: alpaca).
                   Store via env vars and reference with ${VAR} in the YAML:
                       alpaca_api_key:    "${ALPACA_API_KEY}"
                       alpaca_api_secret: "${ALPACA_API_SECRET}"

    lookback_bars: calendar days of OHLCV history to fetch per symbol.
                   Must be >= your slowest indicator period.
                   200 covers 6-month SMA/200-day EMA — plenty for all built-in strategies.

    ibkr_pacing_sleep: DEPRECATED — only applies when data_source was "ibkr"
                   (historical data fetched from IB Gateway directly).
                   Now that data comes from Yahoo/Alpaca this has no effect
                   and can be left at its default value.

    earnings_blackout_days: calendar days before a known earnings date during
                   which the runner will NOT open new positions on that symbol.
                   Existing positions are still closed as normal; this only
                   blocks new entries.
                   Set to 0 to disable the guard entirely.
                   ETFs and symbols with no yfinance earnings data are unaffected
                   (the guard is skipped when the date is unavailable).
    """
    timezone:                str   = "America/New_York"
    entry_time:              str   = "09:35"    # HH:MM local time — enter 5 min after open
    exit_time:               str   = "15:45"    # HH:MM local time — force-close all before close
    lookback_bars:           int   = 200        # calendar days of history to request
    data_source:             str   = "yahoo"    # "yahoo" | "alpaca"  — where to get OHLCV bars
    alpaca_api_key:          str   = ""         # Alpaca API key    (data_source: alpaca only)
    alpaca_api_secret:       str   = ""         # Alpaca API secret (use ${ALPACA_API_SECRET})
    ibkr_pacing_sleep:       float = 1.0        # legacy — no longer used; kept for config compat
    earnings_blackout_days:  int   = 5          # skip new entries within this many days of earnings


@dataclass
class SizingSettings:
    """
    Position sizing parameters.

    fixed_fraction (default):
        risk_pct % of equity is risked per trade.
        stop_pct % below entry is where the stop sits.
        shares = (equity * risk_pct) / (price * stop_pct)

    vol_target:
        Sizes positions so each contributes target_vol to portfolio vol.
        Requires asset_vol estimation (uses 20-day realised vol).

    reward_ratio:
        Take-profit distance = stop distance × reward_ratio.
        e.g. stop=2%, ratio=2 → take-profit at 4%.

    allow_short:
        Set False (default) for standard margin accounts that can't short equities.
        When False, signal=-1 is treated as signal=0 (close/flat only).
    """
    method:           str   = "fixed_fraction"  # fixed_fraction | vol_target
    risk_pct:         float = 0.01   # 1% of equity at risk per trade
    stop_pct:         float = 0.02   # 2% stop loss distance
    reward_ratio:     float = 2.0    # TP = stop_dist × reward_ratio
    target_vol:       float = 0.10   # annualised vol target (vol_target method only)
    max_position_pct: float = 0.10   # hard cap: max 10% of equity in any one symbol
    allow_short:      bool  = False  # most retail accounts cannot short equities


@dataclass
class RiskSettings:
    """
    Account-level risk guards evaluated before any new position is opened.

    max_drawdown_pct:  if current drawdown exceeds this, open no new positions.
    max_open_positions: cap on simultaneous open positions across all symbols.
    """
    max_drawdown_pct:   float = 0.05   # 5% drawdown → halt new entries
    max_open_positions: int   = 5      # maximum concurrent open positions


@dataclass
class LoggingSettings:
    level: str = "INFO"
    file:  str = "logs/daily_runner.log"   # relative to repo root


@dataclass
class EmailSettings:
    """
    SMTP email notifications (e.g. Gmail, SendGrid).

    For Gmail:
        smtp_host: smtp.gmail.com
        smtp_port: 587
        username:  your@gmail.com
        password:  app-specific password (not your main password)

    Store credentials via env vars:
        username: "${EMAIL_USER}"
        password: "${EMAIL_PASS}"
    """
    enabled:   bool = False
    smtp_host: str  = "smtp.gmail.com"
    smtp_port: int  = 587
    username:  str  = ""
    password:  str  = ""
    from_addr: str  = ""
    to_addr:   str  = ""


@dataclass
class WebhookSettings:
    """
    HTTP webhook notifications — works with Discord, Slack, Teams, or any POST endpoint.

    Discord:  https://discord.com/api/webhooks/{id}/{token}
    Slack:    https://hooks.slack.com/services/...
    Teams:    https://your-org.webhook.office.com/...
    """
    enabled: bool = False
    url:     str  = ""


@dataclass
class NotificationSettings:
    email:   EmailSettings   = field(default_factory=EmailSettings)
    webhook: WebhookSettings = field(default_factory=WebhookSettings)


@dataclass
class StrategySpec:
    """One strategy entry from the YAML config."""
    name:   str
    params: Dict = field(default_factory=dict)


# ─── TOP-LEVEL CONFIG ─────────────────────────────────────────────────────────

@dataclass
class RunnerConfig:
    """
    Complete configuration for the daily strategy runner.

    Attributes:
        mode:          "paper" or "live"
        connection:    IB Gateway / TWS connection settings
        schedule:      timing and data fetch settings
        symbols:       equity tickers to trade (e.g. ["AAPL", "MSFT", "SPY"])
        symbols_file:  optional path to a plain-text file of symbols (one per line,
                       # for comments). When set, overrides the inline symbols list.
                       Lets you maintain a large watchlist outside the YAML file.
        strategies:    one or more strategy specs (name + params)
        sizing:        position sizing parameters
        risk:          account-level risk guards
        logging:       log level and output file
        notifications: email and/or webhook alerts

    Example (code):
        from runner.runner_config import RunnerConfig, StrategySpec
        cfg = RunnerConfig(
            mode="paper",
            symbols=["AAPL", "MSFT"],
            strategies=[StrategySpec("EMACrossover", {"fast": 12, "slow": 26})],
        )

    Example (YAML):
        cfg = RunnerConfig.from_yaml("runner_config.yaml")
    """
    mode:          str                  = "paper"
    connection:    ConnectionSettings   = field(default_factory=ConnectionSettings)
    schedule:      ScheduleSettings     = field(default_factory=ScheduleSettings)
    symbols:       List[str]            = field(default_factory=lambda: ["AAPL", "MSFT", "SPY"])
    symbols_file:  Optional[str]        = None   # overrides symbols list when set
    strategies:    List[StrategySpec]   = field(default_factory=list)
    sizing:        SizingSettings       = field(default_factory=SizingSettings)
    risk:          RiskSettings         = field(default_factory=RiskSettings)
    logging:       LoggingSettings      = field(default_factory=LoggingSettings)
    notifications: NotificationSettings = field(default_factory=NotificationSettings)

    # ── VALIDATORS ────────────────────────────────────────────────────────────

    def __post_init__(self) -> None:
        if self.mode not in ("paper", "live"):
            raise ValueError(f"mode must be 'paper' or 'live', got: {self.mode!r}")
        if not self.symbols:
            raise ValueError("symbols list must not be empty")
        if not self.strategies:
            raise ValueError("at least one strategy must be specified")

    # ── YAML LOADER ───────────────────────────────────────────────────────────

    @classmethod
    def from_yaml(cls, path: str) -> "RunnerConfig":
        """
        Load configuration from a YAML file.

        Supports ${ENV_VAR} substitution anywhere in the file — useful for
        keeping credentials in environment variables rather than the config file.

        Args:
            path: path to runner_config.yaml

        Returns:
            RunnerConfig instance

        Raises:
            FileNotFoundError: if the config file does not exist
            ValueError: if required fields are missing or have invalid values
        """
        if not os.path.exists(path):
            raise FileNotFoundError(
                f"Config file not found: {path}\n"
                f"Copy runner_config.yaml to {path} and edit it."
            )

        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}

        raw = _substitute_env_vars(raw)
        return _parse_config(raw)


# ─── PRIVATE HELPERS ─────────────────────────────────────────────────────────

def _load_symbols_file(path: str) -> List[str]:
    """
    Load ticker symbols from a plain-text file.

    Format rules:
        - One symbol per line (auto-uppercased, whitespace stripped)
        - Lines starting with # are full-line comments and are ignored
        - Inline comments are supported: "SPY  # S&P 500 ETF" → "SPY"
        - Blank lines are ignored

    Example symbols.txt:
        # Sector ETFs
        SPY   # S&P 500
        QQQ   # Nasdaq 100
        IWM   # Russell 2000
        GLD   # Gold

        # Large-cap tech
        AAPL  # Apple
        MSFT  # Microsoft

    Args:
        path: path to the symbols file (relative to cwd or absolute)

    Returns:
        List of ticker strings

    Raises:
        FileNotFoundError: if the file does not exist
        ValueError:        if the file contains no valid symbols
    """
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"symbols_file not found: {path!r}\n"
            "Create the file or remove symbols_file from runner_config.yaml."
        )
    symbols: List[str] = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            # Strip inline comments first: "SPY  # S&P 500 ETF" → "SPY"
            line = line.split("#")[0].strip()
            if line:
                symbols.append(line.upper())
    if not symbols:
        raise ValueError(
            f"symbols_file {path!r} contains no valid symbols. "
            "Add at least one ticker (one per line)."
        )
    return symbols


def _substitute_env_vars(obj):
    """Recursively replace ${VAR_NAME} with os.environ.get('VAR_NAME', '${VAR_NAME}')."""
    if isinstance(obj, str):
        return re.sub(
            r"\$\{([^}]+)\}",
            lambda m: os.environ.get(m.group(1), m.group(0)),
            obj,
        )
    if isinstance(obj, dict):
        return {k: _substitute_env_vars(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_substitute_env_vars(i) for i in obj]
    return obj


def _dataclass_from_dict(cls, data: dict):
    """
    Construct a dataclass from a dict, ignoring unknown keys.
    Uses default values for any missing keys.
    """
    field_names = {f.name for f in fields(cls)}
    filtered = {k: v for k, v in data.items() if k in field_names}
    return cls(**filtered)


def _parse_config(raw: dict) -> RunnerConfig:
    """Convert a raw dict (from YAML) into a RunnerConfig."""

    conn_raw   = raw.get("connection",    {})
    sched_raw  = raw.get("schedule",      {})
    sizing_raw = raw.get("sizing",        {})
    risk_raw   = raw.get("risk",          {})
    log_raw    = raw.get("logging",       {})
    notif_raw  = raw.get("notifications", {})

    # Parse strategies list
    strategies: List[StrategySpec] = []
    for s in raw.get("strategies", []):
        strategies.append(StrategySpec(
            name=s["name"],
            params=s.get("params", {}),
        ))

    # Parse notifications (nested)
    email_raw   = notif_raw.get("email",   {})
    webhook_raw = notif_raw.get("webhook", {})

    # symbols_file takes precedence over the inline symbols list
    symbols_file = raw.get("symbols_file", None) or None   # treat "" as None
    if symbols_file:
        symbols = _load_symbols_file(symbols_file)
    else:
        symbols = raw.get("symbols", ["AAPL", "MSFT", "SPY"])

    return RunnerConfig(
        mode=raw.get("mode", "paper"),
        connection=_dataclass_from_dict(ConnectionSettings,   conn_raw),
        schedule=_dataclass_from_dict(ScheduleSettings,       sched_raw),
        symbols=symbols,
        symbols_file=symbols_file,
        strategies=strategies,
        sizing=_dataclass_from_dict(SizingSettings,           sizing_raw),
        risk=_dataclass_from_dict(RiskSettings,               risk_raw),
        logging=_dataclass_from_dict(LoggingSettings,         log_raw),
        notifications=NotificationSettings(
            email=_dataclass_from_dict(EmailSettings,         email_raw),
            webhook=_dataclass_from_dict(WebhookSettings,     webhook_raw),
        ),
    )
