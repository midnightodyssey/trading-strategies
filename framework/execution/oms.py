"""
framework/execution/oms.py
─────────────────────────────────────────────────────────────────────────────
Order Management System (OMS) — paper trading and live P&L tracking.

Use this during walk-forward testing or live paper trading to:
  - Track open positions and their unrealised P&L
  - Record closed trades and realised P&L
  - Monitor current drawdown against prop firm limits
  - Generate a trade log for post-session review

Workflow:
  oms = OMS(starting_capital=100_000)
  oms.open_position("AAPL", direction=1, quantity=100, price=150.0)
  oms.mark_to_market({"AAPL": 155.0})
  print(oms.unrealised_pnl)   # → 500.0
  oms.close_position("AAPL", price=155.0)
  print(oms.realised_pnl)     # → 500.0
"""

from dataclasses import dataclass, field
from typing import Optional
import pandas as pd


# ─── DATA CLASSES ─────────────────────────────────────────────────────────────

@dataclass
class Order:
    """
    Represents a single order instruction.

    In a live system this would be sent to a broker API.
    Here it's a record of intent.

    Attributes:
        ticker:    instrument symbol
        direction: 1 = long, -1 = short
        quantity:  number of shares/contracts
        price:     intended execution price
        timestamp: optional datetime string for logging
    """
    ticker:    str
    direction: int    # 1 = long, -1 = short
    quantity:  int
    price:     float
    timestamp: Optional[str] = None


@dataclass
class Position:
    """
    Represents a currently open position.

    Attributes:
        ticker:        instrument symbol
        direction:     1 = long, -1 = short
        quantity:      number of shares/contracts held
        entry_price:   average price we entered at
        current_price: last mark-to-market price
    """
    ticker:        str
    direction:     int
    quantity:      int
    entry_price:   float
    current_price: float

    @property
    def unrealised_pnl(self) -> float:
        """P&L if we closed at the current mark-to-market price."""
        return self.direction * self.quantity * (self.current_price - self.entry_price)

    @property
    def market_value(self) -> float:
        """Current notional value of the position."""
        return self.quantity * self.current_price


# ─── ORDER MANAGEMENT SYSTEM ──────────────────────────────────────────────────

class OMS:
    """
    Paper trading Order Management System.

    Tracks positions, P&L, drawdown, and trade history.
    Designed to mirror what a real OMS does without broker connectivity.

    Key concepts:
        Realised P&L:   locked-in profit/loss from closed trades
        Unrealised P&L: floating profit/loss on open positions
        Total P&L:      realised + unrealised
        Equity:         starting_capital + total_pnl
        Drawdown:       (equity - peak_equity) / peak_equity (always ≤ 0)

    Args:
        starting_capital: initial account size (default £100,000)
    """

    def __init__(self, starting_capital: float = 100_000.0):
        self.capital        = starting_capital
        self._positions:    dict  = {}       # ticker → Position
        self._realised_pnl: float = 0.0
        self._peak_equity:  float = starting_capital
        self._trade_log:    list  = []

    # ── READ-ONLY PROPERTIES ──────────────────────────────────────────────────

    @property
    def positions(self) -> dict:
        """Copy of current open positions {ticker: Position}."""
        return dict(self._positions)

    @property
    def realised_pnl(self) -> float:
        """Total P&L from all closed trades."""
        return self._realised_pnl

    @property
    def unrealised_pnl(self) -> float:
        """Total floating P&L across all open positions."""
        return sum(p.unrealised_pnl for p in self._positions.values())

    @property
    def total_pnl(self) -> float:
        """Realised + unrealised P&L."""
        return self._realised_pnl + self.unrealised_pnl

    @property
    def equity(self) -> float:
        """Current account equity = starting capital + total P&L."""
        return self.capital + self.total_pnl

    @property
    def current_drawdown(self) -> float:
        """
        Drawdown from the highest equity seen so far.

        Returns a negative number (e.g. -0.05 = 5% drawdown).
        Returns 0.0 if currently at or above previous peak.

        Use this to check against prop firm drawdown limits in real time.
        """
        self._peak_equity = max(self._peak_equity, self.equity)
        if self._peak_equity == 0:
            return 0.0
        return (self.equity - self._peak_equity) / self._peak_equity

    # ── TRADING OPERATIONS ────────────────────────────────────────────────────

    def open_position(
        self,
        ticker:    str,
        direction: int,
        quantity:  int,
        price:     float,
        timestamp: Optional[str] = None,
    ) -> None:
        """
        Open a new position (or replace an existing one for simplicity).

        Args:
            ticker:    instrument symbol
            direction: 1 = long, -1 = short
            quantity:  number of shares/contracts
            price:     entry price
            timestamp: optional log timestamp
        """
        self._positions[ticker] = Position(
            ticker=ticker,
            direction=direction,
            quantity=quantity,
            entry_price=price,
            current_price=price,
        )

    def close_position(
        self,
        ticker:    str,
        price:     float,
        timestamp: Optional[str] = None,
    ) -> float:
        """
        Close an open position and lock in P&L.

        Args:
            ticker: instrument to close
            price:  exit price
            timestamp: optional log timestamp

        Returns:
            Realised P&L from this trade (positive = profit, negative = loss)
        """
        if ticker not in self._positions:
            return 0.0

        pos               = self._positions.pop(ticker)
        pos.current_price = price
        realised          = pos.unrealised_pnl

        self._realised_pnl += realised
        self._trade_log.append({
            "ticker":    ticker,
            "direction": pos.direction,
            "quantity":  pos.quantity,
            "entry":     pos.entry_price,
            "exit":      price,
            "pnl":       realised,
            "timestamp": timestamp,
        })

        return realised

    def mark_to_market(self, prices: dict) -> None:
        """
        Update current prices for all open positions.

        Call this at the end of each bar/tick with the latest prices.
        Also updates the peak equity used for drawdown calculation.

        Args:
            prices: dict mapping ticker → current price
                    e.g. {"AAPL": 155.0, "MSFT": 420.0}
        """
        for ticker, price in prices.items():
            if ticker in self._positions:
                self._positions[ticker].current_price = price

        # Update peak after marking positions
        self._peak_equity = max(self._peak_equity, self.equity)

    # ── REPORTING ─────────────────────────────────────────────────────────────

    def trade_log(self) -> pd.DataFrame:
        """
        Return complete trade history as a DataFrame.

        Columns: ticker, direction, quantity, entry, exit, pnl, timestamp
        """
        if not self._trade_log:
            return pd.DataFrame(
                columns=["ticker", "direction", "quantity", "entry", "exit", "pnl", "timestamp"]
            )
        return pd.DataFrame(self._trade_log)

    def summary(self) -> dict:
        """
        Return a snapshot of current OMS state.

        Useful for printing to the console during a live session
        or logging to a database.
        """
        log      = self.trade_log()
        n_trades = len(log)
        win_rate = float((log["pnl"] > 0).mean()) if n_trades > 0 else 0.0

        return {
            "capital":         round(self.capital, 2),
            "equity":          round(self.equity, 2),
            "realised_pnl":    round(self.realised_pnl, 2),
            "unrealised_pnl":  round(self.unrealised_pnl, 2),
            "total_pnl":       round(self.total_pnl, 2),
            "current_drawdown": round(self.current_drawdown, 4),
            "open_positions":  len(self._positions),
            "total_trades":    n_trades,
            "win_rate":        round(win_rate, 4),
        }
