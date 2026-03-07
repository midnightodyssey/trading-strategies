"""
runner/daily_runner.py
─────────────────────────────────────────────────────────────────────────────
Daily strategy runner — connects to IB Gateway, generates signals, manages
orders, and sends notifications. Designed to run as a cron job on a VPS.

Entry points:
    # CLI (cron job)
    python -m runner.daily_runner
    python -m runner.daily_runner --config /path/to/runner_config.yaml

    # Programmatic
    from runner import DailyRunner
    DailyRunner("runner_config.yaml").run()

Execution flow:
    1. Load config + setup logging
    2. Check market calendar (exit cleanly on weekends / holidays)
    3. Connect to IB Gateway
    4. Fetch account equity + sync existing positions to OMS
    5. For each symbol:
         a. Fetch historical OHLCV data
         b. Generate consensus signal from all configured strategies
         c. Compare signal against current IBKR position
         d. Close reversed/flattened positions; open new bracket orders
    6. Log session summary
    7. Send email / webhook notification
    8. Disconnect

Risk guards (abort new entries if triggered):
    - Drawdown > config.risk.max_drawdown_pct
    - Open positions ≥ config.risk.max_open_positions

Signal consensus:
    All strategies vote {-1, 0, +1} on the latest bar.
    Majority wins; ties resolve to 0 (flat).
    e.g. [+1, +1, -1] → +1   |   [+1, -1] → 0
"""

from __future__ import annotations

import argparse
import logging
import logging.handlers
import os
import sys
from datetime import date, datetime
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from framework.broker          import IBKRBroker, IBKRConnectionError
from framework.execution       import OMS
from framework.execution.sizing import fixed_fraction, vol_target
from framework.strategies      import (
    EMACrossover,
    SMACrossover,
    RSIMeanReversion,
    BollingerMeanReversion,
    PriceBreakout,
)
from framework.strategies.base import Strategy

from .notifier       import Notifier
from .runner_config  import RunnerConfig, SizingSettings, StrategySpec


# ─── STRATEGY REGISTRY ────────────────────────────────────────────────────────

_STRATEGY_REGISTRY: Dict[str, type] = {
    "EMACrossover":          EMACrossover,
    "SMACrossover":          SMACrossover,
    "RSIMeanReversion":      RSIMeanReversion,
    "BollingerMeanReversion": BollingerMeanReversion,
    "PriceBreakout":         PriceBreakout,
}


# ─── NYSE MARKET CALENDAR ─────────────────────────────────────────────────────

# Fixed-date NYSE holidays 2024 – 2027.
# Update this set each year (or switch to the exchange_calendars package).
_NYSE_HOLIDAYS: frozenset = frozenset({
    # 2024
    (2024,  1,  1), (2024,  1, 15), (2024,  2, 19), (2024,  3, 29),
    (2024,  5, 27), (2024,  6, 19), (2024,  7,  4), (2024,  9,  2),
    (2024, 11, 28), (2024, 12, 25),
    # 2025
    (2025,  1,  1), (2025,  1, 20), (2025,  2, 17), (2025,  4, 18),
    (2025,  5, 26), (2025,  6, 19), (2025,  7,  4), (2025,  9,  1),
    (2025, 11, 27), (2025, 12, 25),
    # 2026
    (2026,  1,  1), (2026,  1, 19), (2026,  2, 16), (2026,  4,  3),
    (2026,  5, 25), (2026,  6, 19), (2026,  7,  3), (2026,  9,  7),
    (2026, 11, 26), (2026, 12, 25),
    # 2027
    (2027,  1,  1), (2027,  1, 18), (2027,  2, 15), (2027,  3, 26),
    (2027,  5, 31), (2027,  6, 18), (2027,  7,  5), (2027,  9,  6),
    (2027, 11, 25), (2027, 12, 24),
})


def _is_trading_day(dt: date) -> bool:
    """Return True if NYSE is open on the given date."""
    if dt.weekday() >= 5:                           # Saturday=5, Sunday=6
        return False
    return (dt.year, dt.month, dt.day) not in _NYSE_HOLIDAYS


# ─── HELPER FUNCTIONS ─────────────────────────────────────────────────────────

def _build_strategies(specs: List[StrategySpec]) -> List[Strategy]:
    """Instantiate strategy objects from StrategySpec list."""
    strategies = []
    for spec in specs:
        cls = _STRATEGY_REGISTRY.get(spec.name)
        if cls is None:
            raise ValueError(
                f"Unknown strategy: {spec.name!r}. "
                f"Available: {sorted(_STRATEGY_REGISTRY)}"
            )
        strategies.append(cls(**spec.params))
    return strategies


def _consensus_signal(signals: List[float]) -> int:
    """
    Majority-vote consensus across multiple strategy signals.

    Returns:
        +1 if more strategies are long than short
        -1 if more strategies are short than long
         0 if tied or all flat
    """
    total = sum(float(s) for s in signals)
    if total > 0:
        return 1
    if total < 0:
        return -1
    return 0


def _calculate_quantity(
    cfg: SizingSettings,
    equity: float,
    price: float,
    returns_std: Optional[float] = None,
) -> int:
    """
    Calculate position size in shares using the configured sizing method.

    Args:
        cfg:         SizingSettings from RunnerConfig
        equity:      current account equity ($)
        price:       current asset price ($)
        returns_std: annualised volatility (for vol_target method only)

    Returns:
        Number of shares to trade (minimum 0)
    """
    if price <= 0:
        return 0

    if cfg.method == "vol_target" and returns_std and returns_std > 0:
        qty = vol_target(equity, cfg.target_vol, returns_std, price)
    else:
        qty = fixed_fraction(equity, cfg.risk_pct, cfg.stop_pct, price)

    # Hard cap: no single position > max_position_pct of equity
    max_qty = int((equity * cfg.max_position_pct) / price)
    return min(qty, max(0, max_qty))


def _estimate_annual_vol(df: pd.DataFrame, window: int = 20) -> float:
    """
    Estimate annualised return volatility from recent close prices.
    Uses the last `window` bars of daily returns × sqrt(252).
    """
    returns = df["Close"].pct_change().dropna()
    if len(returns) < window:
        return 0.20   # fallback: assume 20% if insufficient history
    return float(returns.tail(window).std() * (252 ** 0.5))


# ─── DAILY RUNNER ─────────────────────────────────────────────────────────────

class DailyRunner:
    """
    Orchestrates the daily signal → order lifecycle.

    Designed to be invoked once per trading day, typically by a cron job:
        35 14 * * 1-5  cd /opt/trading && python -m runner.daily_runner

    Args:
        config_path: path to runner_config.yaml
    """

    def __init__(self, config_path: str = "runner_config.yaml"):
        self.cfg       = RunnerConfig.from_yaml(config_path)
        self._logger   = _setup_logging(self.cfg.logging)
        self.strategies = _build_strategies(self.cfg.strategies)
        self._logger.info(
            "Runner initialised | mode=%s | symbols=%s | strategies=%s",
            self.cfg.mode,
            self.cfg.symbols,
            [s.name for s in self.strategies],
        )

    # ── PUBLIC ENTRY POINT ────────────────────────────────────────────────────

    def run(self) -> None:
        """
        Run a complete session: connect → signal → trade → notify → disconnect.

        Connection errors and unexpected exceptions are caught, logged, and
        forwarded as notifications. The process exits with code 1 on failure
        so that cron/systemd can detect the failure.
        """
        notifier = Notifier(self.cfg.notifications, self._logger)

        try:
            self._run_session(notifier)
        except IBKRConnectionError as exc:
            msg = f"IBKR connection failed — is IB Gateway running? {exc}"
            self._logger.error(msg)
            notifier.send_error(msg)
            sys.exit(1)
        except Exception as exc:
            msg = f"{type(exc).__name__}: {exc}"
            self._logger.error("Runner failed: %s", msg, exc_info=True)
            notifier.send_error(msg)
            sys.exit(1)

    # ── SESSION ───────────────────────────────────────────────────────────────

    def _run_session(self, notifier: Notifier) -> None:
        """Inner session body — runs inside the public run() error wrapper."""
        cfg = self.cfg
        tz  = ZoneInfo(cfg.schedule.timezone)

        # ── 1. Market calendar check ─────────────────────────────────────────
        today = datetime.now(tz).date()
        if not _is_trading_day(today):
            self._logger.info("Market closed on %s. Exiting.", today)
            return

        # ── 2. Connect to IB Gateway ─────────────────────────────────────────
        broker = IBKRBroker(
            paper=(cfg.mode == "paper"),
            host=cfg.connection.host,
            gateway=cfg.connection.gateway,
            client_id=cfg.connection.client_id,
            timeout=cfg.connection.timeout,
        )

        with broker:
            if cfg.mode == "live":
                broker.confirm_live_trading()

            self._logger.info("Connected to IB %s account", cfg.mode)

            # ── 3. Account snapshot ──────────────────────────────────────────
            account = broker.get_account_summary()
            equity  = account.get("net_liquidation", 0.0)
            self._logger.info("Account equity: $%s", f"{equity:,.2f}")

            # ── 4. Sync live positions into OMS ──────────────────────────────
            oms = OMS(starting_capital=equity)
            try:
                broker.sync_to_oms(oms)
            except Exception as exc:
                self._logger.warning("OMS sync warning: %s", exc)

            # ── 5. Drawdown guard ────────────────────────────────────────────
            current_dd = abs(oms.current_drawdown)
            if current_dd > cfg.risk.max_drawdown_pct:
                msg = (
                    f"Drawdown guard: {current_dd:.1%} > "
                    f"{cfg.risk.max_drawdown_pct:.1%} limit. "
                    "No new positions opened."
                )
                self._logger.warning(msg)
                notifier.send_error(msg)
                return

            # ── 6. Snapshot current IBKR positions and open orders ───────────
            positions_df = broker.get_positions()
            open_trades  = broker.get_open_orders()

            # {symbol: direction}  direction ∈ {1, -1}
            ibkr_positions: Dict[str, int] = {}
            if not positions_df.empty:
                for _, row in positions_df.iterrows():
                    ibkr_positions[row["symbol"]] = 1 if row["position"] > 0 else -1

            # Symbols that already have a pending order — skip them to avoid
            # double-entry or conflicting instructions
            pending_syms: set = {
                t.contract.symbol for t in open_trades
                if t.orderStatus.status not in ("Filled", "Cancelled", "Inactive")
            }

            self._logger.info(
                "Positions: %s | Pending orders: %s",
                dict(ibkr_positions),
                pending_syms,
            )

            # ── 7. Process each symbol ───────────────────────────────────────
            actions:    List[dict] = []
            open_count: int        = len(ibkr_positions)

            for symbol in cfg.symbols:
                try:
                    result = self._process_symbol(
                        symbol       = symbol,
                        broker       = broker,
                        equity       = equity,
                        ibkr_positions = ibkr_positions,
                        pending_syms = pending_syms,
                        open_count   = open_count,
                        open_trades  = open_trades,
                    )
                    if result:
                        actions.append(result)
                        if result["action"] in ("OPENED_LONG", "OPENED_SHORT"):
                            open_count += 1
                        elif result["action"] == "CLOSED":
                            open_count  = max(0, open_count - 1)
                except Exception as exc:
                    self._logger.warning(
                        "Error processing %s: %s", symbol, exc, exc_info=True
                    )

            # ── 8. Final OMS re-sync and summary ─────────────────────────────
            try:
                broker.sync_to_oms(oms)
            except Exception:
                pass

            summary = oms.summary()
            self._logger.info(
                "Session complete | equity=$%s | open=%s | realised=$%s",
                f"{summary['equity']:,.2f}",
                summary["open_positions"],
                f"{summary['realised_pnl']:+,.2f}",
            )

            # ── 9. Notify ────────────────────────────────────────────────────
            notifier.send_daily_summary(summary, actions, today)

    # ── PER-SYMBOL LOGIC ─────────────────────────────────────────────────────

    def _process_symbol(
        self,
        symbol:          str,
        broker:          IBKRBroker,
        equity:          float,
        ibkr_positions:  Dict[str, int],
        pending_syms:    set,
        open_count:      int,
        open_trades:     list,
    ) -> Optional[dict]:
        """
        Generate a signal for one symbol and place/close orders as needed.

        Returns a dict describing what happened (for the summary notification),
        or None if no action was taken.
        """
        cfg = self.cfg

        # Skip if there's already a pending order for this symbol
        if symbol in pending_syms:
            self._logger.debug("%s: pending order exists — skipping", symbol)
            return None

        # ── Fetch historical data ─────────────────────────────────────────────
        bars = cfg.schedule.lookback_bars
        df   = broker.get_historical_data(
            symbol,
            duration=f"{bars} D",
            bar_size="1 day",
        )
        if df.empty or len(df) < 5:
            self._logger.warning("%s: insufficient data (%d bars) — skipping", symbol, len(df))
            return None

        price      = float(df["Close"].iloc[-1])
        annual_vol = _estimate_annual_vol(df)

        # ── Generate consensus signal ─────────────────────────────────────────
        raw_signals = []
        for strat in self.strategies:
            try:
                sig = strat.generate_signals(df).iloc[-1]
                raw_signals.append(float(sig))
            except Exception as exc:
                self._logger.warning("%s / %s signal error: %s", symbol, strat.name, exc)
                raw_signals.append(0.0)

        signal = _consensus_signal(raw_signals)

        # Apply short restriction (most retail accounts can't short)
        if not cfg.sizing.allow_short and signal == -1:
            signal = 0

        current_dir = ibkr_positions.get(symbol, 0)   # 0 = no position

        self._logger.info(
            "%s  price=%.2f  signal=%+d  current=%+d  strategies=%s",
            symbol, price, signal, current_dir,
            [f"{v:+.0f}" for v in raw_signals],
        )

        # ── Nothing to do ─────────────────────────────────────────────────────
        if signal == current_dir:
            return None

        # ── Close existing position (signal reversed or went flat) ────────────
        if current_dir != 0:
            close_action = "SELL" if current_dir == 1 else "BUY"

            # Cancel any open linked orders first
            symbol_orders = [
                t for t in open_trades
                if t.contract.symbol == symbol
                and t.orderStatus.status not in ("Filled", "Cancelled", "Inactive")
            ]
            for t in symbol_orders:
                try:
                    broker.cancel_order(t)
                    self._logger.debug("%s: cancelled order ID=%s", symbol, t.order.orderId)
                except Exception:
                    pass
            if symbol_orders:
                broker._ib.sleep(1)

            # Close the position with a market order
            close_qty = abs(ibkr_positions.get(symbol, 1))
            broker.place_market_order(symbol, close_action, close_qty)
            broker._ib.sleep(2)
            self._logger.info("%s: closed %s %d @ ~%.2f", symbol, close_action, close_qty, price)

            if signal == 0:
                return {"symbol": symbol, "action": "CLOSED", "price": price, "signal": signal}

        # ── Open new position ─────────────────────────────────────────────────
        if signal != 0:
            # Respect open position cap
            if open_count >= cfg.risk.max_open_positions:
                self._logger.info(
                    "%s: max open positions reached (%d) — skipping",
                    symbol, cfg.risk.max_open_positions,
                )
                return None

            action = "BUY" if signal == 1 else "SELL"

            # Size the position
            qty = _calculate_quantity(cfg.sizing, equity, price, annual_vol)
            if qty <= 0:
                self._logger.warning(
                    "%s: calculated qty=0 (equity=%.0f price=%.2f) — skipping",
                    symbol, equity, price,
                )
                return None

            # TP / SL levels (symmetric around entry price)
            stop_dist = price * cfg.sizing.stop_pct
            tp_dist   = stop_dist * cfg.sizing.reward_ratio

            if signal == 1:    # long
                tp = round(price + tp_dist,   2)
                sl = round(price - stop_dist, 2)
            else:               # short
                tp = round(price - tp_dist,   2)
                sl = round(price + stop_dist, 2)

            # Place bracket order (entry + TP child + SL child)
            trades = broker.place_bracket_order(
                symbol,
                action,
                qty,
                limit_price=round(price, 2),
                take_profit=tp,
                stop_loss=sl,
            )
            broker._ib.sleep(2)

            parent  = trades[0]
            order_id = parent.order.orderId
            status   = parent.orderStatus.status

            self._logger.info(
                "%s: bracket %s  qty=%d  entry=%.2f  TP=%.2f  SL=%.2f  "
                "ID=%s  status=%s",
                symbol, action, qty, price, tp, sl, order_id, status,
            )

            action_label = "OPENED_LONG" if signal == 1 else "OPENED_SHORT"
            return {
                "symbol":   symbol,
                "action":   action_label,
                "qty":      qty,
                "price":    price,
                "tp":       tp,
                "sl":       sl,
                "order_id": order_id,
            }

        return None


# ─── LOGGING SETUP ────────────────────────────────────────────────────────────

def _setup_logging(cfg) -> logging.Logger:
    """
    Configure the root logger with both file and console handlers.

    Uses a rotating file handler (10 MB per file, 5 backups) so logs
    don't consume unlimited disk on a VPS.
    """
    level = getattr(logging, cfg.level.upper(), logging.INFO)

    # Ensure log directory exists
    log_dir = os.path.dirname(cfg.file)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)

    fmt     = "%(asctime)s  %(levelname)-8s  %(name)s  %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()

    # Console handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(level)
    ch.setFormatter(logging.Formatter(fmt, datefmt))
    root.addHandler(ch)

    # Rotating file handler
    fh = logging.handlers.RotatingFileHandler(
        cfg.file, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    fh.setLevel(level)
    fh.setFormatter(logging.Formatter(fmt, datefmt))
    root.addHandler(fh)

    return logging.getLogger("runner")


# ─── CLI ENTRY POINT ──────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="python -m runner.daily_runner",
        description="Daily strategy runner — connects to IB Gateway and manages orders.",
    )
    p.add_argument(
        "--config", "-c",
        default="runner_config.yaml",
        metavar="PATH",
        help="Path to runner_config.yaml (default: runner_config.yaml)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch data and generate signals but do NOT place any orders",
    )
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()

    if args.dry_run:
        # Dry run: monkeypatch order methods to no-ops
        print("DRY RUN — signals will be generated but no orders placed")
        IBKRBroker.place_market_order   = lambda *a, **kw: None   # type: ignore
        IBKRBroker.place_bracket_order  = lambda *a, **kw: []     # type: ignore
        IBKRBroker.cancel_order         = lambda *a, **kw: None   # type: ignore

    DailyRunner(config_path=args.config).run()
