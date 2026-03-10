"""
framework/broker/ibkr.py
─────────────────────────────────────────────────────────────────────────────
Interactive Brokers integration via ib_insync.

ib_insync wraps the raw TWS API in a synchronous-feeling interface backed
by asyncio.  Key rule: always use self._ib.sleep() instead of time.sleep()
— ib_insync's event loop must keep running between calls to process incoming
fills, errors, and market data ticks.

Safety model:
    Live trading is disabled by default.  Any order method called while
    paper=False and _live_confirmed=False raises LiveTradingNotConfirmed.
    Call broker.confirm_live_trading() once per session to unlock live orders.
    Disconnecting resets the confirmation, so reconnecting to a live account
    always requires re-confirming.

TWS setup checklist (do once):
    1. Open TWS → Edit → Global Configuration → API → Settings
    2. Enable "Enable ActiveX and Socket Clients"
    3. Set Socket port to 7497 (paper) or 7496 (live)
    4. Uncheck "Read-Only API" if you want to place orders
    5. Add 127.0.0.1 to Trusted IP Addresses

Jupyter users:
    If using from a Jupyter notebook, call BEFORE constructing IBKRBroker:
        import nest_asyncio; nest_asyncio.apply()
    (Jupyter runs its own asyncio loop; ib_insync needs this patch.)

Build order: indicators → risk → backtest → data → strategies → execution → [broker]
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional

import pandas as pd

# ib_insync's eventkit dependency calls asyncio.get_event_loop() at module
# import time. Python 3.10+ no longer implicitly creates a loop, so we must
# ensure one exists before the import occurs.
try:
    asyncio.get_event_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

from ib_insync import IB, Stock, Forex, Contract, MarketOrder, LimitOrder, StopOrder, util

from .config import ConnectionConfig
from ..execution.oms import OMS


# ─── EXCEPTIONS ───────────────────────────────────────────────────────────────

class IBKRConnectionError(RuntimeError):
    """
    Raised when connect() fails or a method is called without an active connection.

    Common causes:
        - TWS / IB Gateway is not running
        - Wrong port (paper vs live mismatch — check paper=True/False)
        - Firewall blocking the port
        - Client ID already in use by another process (increment client_id)
    """


class LiveTradingNotConfirmed(RuntimeError):
    """
    Raised when an order method is called on a live account before
    confirm_live_trading() has been called in this session.

    This is the primary safety guard.  You must write:
        broker.confirm_live_trading()
    as an explicit, deliberate line in your trading script before any order
    will be sent to your live account.

    Re-connecting resets this flag — every new session requires re-confirmation.
    """


class PositionSyncError(ValueError):
    """
    Raised by sync_to_oms() when an IBKR position cannot be reliably mapped
    into the OMS — for example, if averageCost is zero (IBKR sometimes returns
    zero cost on the first connection before account data fully loads).
    """


# ─── BROKER CLASS ─────────────────────────────────────────────────────────────

class IBKRBroker:
    """
    High-level Interactive Brokers client built on ib_insync.

    Provides:
        - Automatic port selection (paper/live × TWS/Gateway)
        - Context manager: with IBKRBroker(paper=True) as broker: ...
        - Historical data in the same format as framework/data.py
        - Account summary and position inspection
        - Market, limit, stop, and bracket order placement
        - Live trading safety guard (confirm_live_trading())
        - OMS bridge: sync live IBKR positions into an OMS instance

    ─── Paper trading session ───────────────────────────────────────────────
        with IBKRBroker(paper=True) as broker:
            df      = broker.get_historical_data("AAPL", duration="1 Y")
            summary = broker.get_account_summary()
            trade   = broker.place_market_order("AAPL", "BUY", 100)

    ─── Live trading session ────────────────────────────────────────────────
        with IBKRBroker(paper=False) as broker:
            broker.confirm_live_trading()    # REQUIRED — explicit unlock
            trade = broker.place_limit_order("AAPL", "BUY", 100, 175.00)

    ─── Seed OMS from live positions ────────────────────────────────────────
        oms = OMS(starting_capital=100_000)
        with IBKRBroker(paper=True) as broker:
            broker.sync_to_oms(oms)          # seed with current account state
            print(oms.summary())

    Args:
        paper:     True → paper account (default). False → live account.
        host:      TWS hostname. Default "127.0.0.1" (local machine).
        port:      Override port. If None, auto-selected from paper/gateway.
        client_id: TWS client ID. Must be unique per simultaneous connection.
        gateway:   True → target IB Gateway. False → target TWS (default).
    """

    def __init__(
        self,
        paper:     bool = True,
        host:      str  = "127.0.0.1",
        port:      Optional[int] = None,
        client_id: int  = 1,
        gateway:   bool = False,
        timeout:   int  = 10,
    ) -> None:
        self._config          = ConnectionConfig(
            host=host, port=port, client_id=client_id,
            paper=paper, gateway=gateway, timeout=timeout,
        )
        self._ib              = IB()
        self._live_confirmed  = False
        self._logger          = logging.getLogger(__name__)

    # ── CONNECTION ────────────────────────────────────────────────────────────

    @property
    def is_connected(self) -> bool:
        """True if there is an active TWS connection."""
        return self._ib.isConnected()

    @property
    def is_paper(self) -> bool:
        """True if connected to a paper trading account."""
        return self._config.paper

    def connect(self) -> None:
        """
        Open a connection to TWS / IB Gateway.

        Uses the port from ConnectionConfig.resolved_port() (auto-selected
        unless overridden in the constructor).

        Raises:
            IBKRConnectionError: If TWS is unreachable, refuses the connection,
                                 or the client_id is already in use.

        Notes:
            - TWS must be running with API access enabled (see module docstring).
            - connect() is blocking — it waits for the TWS handshake.
            - From Jupyter: call nest_asyncio.apply() BEFORE this (see module docs).
        """
        if self.is_connected:
            return

        host      = self._config.host
        port      = self._config.resolved_port()
        client_id = self._config.client_id
        timeout   = self._config.timeout
        account   = "paper" if self._config.paper else "LIVE"

        try:
            self._ib.connect(host, port, clientId=client_id, timeout=timeout)
        except Exception as exc:
            raise IBKRConnectionError(
                f"Could not connect to {'TWS' if not self._config.gateway else 'IB Gateway'} "
                f"at {host}:{port} (client_id={client_id}). "
                f"Is TWS running with API enabled on port {port}? "
                f"Original error: {exc}"
            ) from exc

        if not self._ib.isConnected():
            raise IBKRConnectionError(
                f"connect() returned but IB.isConnected() is False. "
                f"Check {host}:{port} (client_id={client_id})."
            )

        self._logger.info(
            "Connected to IBKR [%s] at %s:%d client_id=%d",
            account, host, port, client_id,
        )

    def disconnect(self) -> None:
        """
        Gracefully close the TWS connection.

        Safe to call even if already disconnected.
        Resets the live trading confirmation so every new session requires
        an explicit confirm_live_trading() call.
        """
        if self._ib.isConnected():
            self._ib.disconnect()
            self._logger.info("Disconnected from IBKR.")

        # Reset confirmation so re-connecting to live requires re-confirming
        self._live_confirmed = False

    def __enter__(self) -> "IBKRBroker":
        """Connect and return self for use as a context manager."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        """Disconnect on context exit, regardless of exceptions."""
        try:
            self.disconnect()
        except Exception:
            pass   # don't mask the original exception
        return False   # always re-raise any exception from the with-block

    # ── SAFETY GUARDS ─────────────────────────────────────────────────────────

    def _require_connection(self) -> None:
        """Assert an active connection. Called at the start of all public methods."""
        if not self._ib.isConnected():
            raise IBKRConnectionError(
                "Not connected to TWS. Call broker.connect() or use "
                "'with IBKRBroker() as broker:' before calling this method."
            )

    def _require_live_confirmed(self) -> None:
        """
        Assert live trading has been confirmed. Called before every order method.

        No-op if this is a paper account.
        """
        if self._config.paper:
            return   # paper accounts have no restriction

        if not self._live_confirmed:
            raise LiveTradingNotConfirmed(
                "Live order placement requires explicit confirmation. "
                "Call broker.confirm_live_trading() before placing any order. "
                "This guard prevents accidental real-money orders."
            )

    def confirm_live_trading(self) -> None:
        """
        Unlock live order placement for this session.

        Must be called once per session before placing any order on a
        live account (paper=False).  This is intentionally a manual step —
        it forces you to write a visible, searchable line in your script
        that says 'I know this will send real orders.'

        Disconnecting resets this flag: every new connection to a live
        account requires re-calling confirm_live_trading().

        Raises:
            RuntimeError: If called on a paper account.  This prevents
                          false confidence (calling it on paper and then
                          switching to live without noticing).
        """
        if self._config.paper:
            raise RuntimeError(
                "confirm_live_trading() is only meaningful for live accounts. "
                "You are connected to a paper account — no confirmation needed."
            )

        self._live_confirmed = True
        warning = (
            "\n"
            "╔══════════════════════════════════════════════════════════╗\n"
            "║  ⚠️   LIVE TRADING ENABLED                               ║\n"
            "║  Real money orders will be sent to your IBKR account.   ║\n"
            "║  Double-check symbol, action, quantity before submitting.║\n"
            "╚══════════════════════════════════════════════════════════╝\n"
        )
        print(warning)
        self._logger.warning("Live trading confirmed at %s.", datetime.now().isoformat())

    # ── PRIVATE HELPERS ───────────────────────────────────────────────────────

    def _build_contract(
        self,
        symbol:   str,
        sec_type: str = "STK",
        exchange: str = "SMART",
        currency: str = "USD",
    ) -> Contract:
        """
        Build the appropriate ib_insync Contract object for a security type.

        Dispatches:
            "STK"  → Stock(symbol, exchange, currency)
            "CASH" → Forex(symbol)  e.g. symbol="EURUSD"
            others → generic Contract(...)

        Does NOT call qualifyContracts() — callers that need disambiguation
        (e.g. a stock listed on multiple exchanges) should call
        self._ib.qualifyContracts(contract) themselves after building.
        For most US equities on SMART routing, qualification is not needed.
        """
        sec_type = sec_type.upper()
        if sec_type == "STK":
            return Stock(symbol, exchange, currency)
        elif sec_type == "CASH":
            # ib_insync Forex() takes a 6-char pair e.g. "EURUSD"
            return Forex(symbol)
        else:
            return Contract(
                symbol=symbol,
                secType=sec_type,
                exchange=exchange,
                currency=currency,
            )

    def _safe_float(self, value: str) -> Optional[float]:
        """Cast an IBKR account tag value to float, returning None for N/A."""
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    # ── MARKET DATA ───────────────────────────────────────────────────────────

    def get_historical_data(
        self,
        symbol:       str,
        duration:     str  = "1 Y",
        bar_size:     str  = "1 day",
        sec_type:     str  = "STK",
        exchange:     str  = "SMART",
        currency:     str  = "USD",
        what_to_show: str  = "TRADES",
        use_rth:      bool = True,
    ) -> pd.DataFrame:
        """
        Fetch OHLCV historical bars from TWS.

        The returned DataFrame is structurally identical to the output of
        framework/data.fetch() + data.clean():
            - Columns: Open, High, Low, Close, Volume  (title-case)
            - Index:   tz-naive DatetimeIndex  (same as yfinance daily output)
            - Sorted:  ascending  (oldest row first)
            - No duplicate index rows

        This means the output can be passed directly into:
            strategy.generate_signals(df)
            run_backtest(signals, df["Close"], ...)
            data.add_features(df)    — feature engineering

        Args:
            symbol:       Ticker, e.g. "AAPL", "SPY", "EURUSD"
            duration:     IBKR duration string: "1 Y", "6 M", "30 D", "5 D"
                          Full list: https://interactivebrokers.github.io/tws-api/
            bar_size:     IBKR bar size: "1 day", "1 hour", "30 mins",
                          "15 mins", "5 mins", "1 min"
                          Note IBKR spelling: "mins" not "min" for sub-hourly.
            sec_type:     "STK" (stocks/ETFs), "CASH" (forex), "FUT" (futures)
            exchange:     "SMART" for IBKR auto-routing (default).
            currency:     ISO 4217 code, e.g. "USD", "GBP", "EUR"
            what_to_show: "TRADES" (last price), "MIDPOINT" (bid/ask mid),
                          "BID", "ASK".  Use "MIDPOINT" for forex.
            use_rth:      True → regular trading hours only (default).

        Returns:
            pd.DataFrame with columns [Open, High, Low, Close, Volume],
            tz-naive DatetimeIndex, sorted ascending.

        Raises:
            IBKRConnectionError: if not connected.
            ValueError: if TWS returns zero bars (wrong symbol, data
                        subscription missing, or market not open for live data).

        Notes:
            Historical data pacing: IBKR rate-limits requests to ~60 per
            10 minutes.  When fetching multiple symbols in a loop, add
            self._ib.sleep(0.5) between calls to stay within the limit.
            Hitting the limit (error 162) causes a 10-second forced wait.
        """
        self._require_connection()

        contract = self._build_contract(symbol, sec_type, exchange, currency)

        bars = self._ib.reqHistoricalData(
            contract,
            endDateTime="",
            durationStr=duration,
            barSizeSetting=bar_size,
            whatToShow=what_to_show,
            useRTH=use_rth,
            formatDate=1,
        )

        if not bars:
            raise ValueError(
                f"TWS returned zero bars for {symbol} ({duration}, {bar_size}). "
                f"Check the symbol is valid and you have a data subscription for it."
            )

        # Convert BarData list to DataFrame
        df = util.df(bars)

        # Rename lowercase ib_insync columns → title-case (data.py convention)
        rename_map = {
            "open":   "Open",
            "high":   "High",
            "low":    "Low",
            "close":  "Close",
            "volume": "Volume",
        }
        df = df.rename(columns=rename_map)

        # Set date as index
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date")

        # Strip timezone (IBKR returns US/Eastern; data.py uses tz-naive)
        # Use tz_localize(None) NOT tz_convert() — we want to remove the tz
        # info without shifting the timestamps.
        if df.index.tz is not None:
            df.index = df.index.tz_localize(None)

        # Keep only OHLCV — drop ib_insync extras (barCount, average, hasGaps)
        df = df[["Open", "High", "Low", "Close", "Volume"]]

        # Defensive sort + dedup (matches data.clean() behaviour)
        df = df.sort_index()
        df = df[~df.index.duplicated(keep="last")]

        self._logger.info(
            "Fetched %d bars for %s (%s, %s)", len(df), symbol, duration, bar_size
        )
        return df

    # ── ACCOUNT ───────────────────────────────────────────────────────────────

    def get_account_summary(self) -> dict:
        """
        Retrieve key account metrics from TWS.

        Returns:
            dict with keys:
                net_liquidation      : float — total account value
                cash_balance         : float — uninvested cash
                buying_power         : float — margin-adjusted available capital
                gross_position_value : float — abs sum of all position market values
                unrealised_pnl       : float — total floating P&L
                realised_pnl         : float — realised P&L for session
                currency             : str   — account base currency (e.g. "USD")
                account_id           : str   — IBKR account number

        Raises:
            IBKRConnectionError: if not connected.
        """
        self._require_connection()

        items   = self._ib.accountSummary()
        summary = {item.tag: item.value for item in items}

        tag_map = {
            "NetLiquidation":    "net_liquidation",
            "TotalCashValue":    "cash_balance",
            "BuyingPower":       "buying_power",
            "GrossPositionValue":"gross_position_value",
            "UnrealizedPnL":     "unrealised_pnl",
            "RealizedPnL":       "realised_pnl",
        }

        result: dict = {}
        for ibkr_tag, key in tag_map.items():
            result[key] = self._safe_float(summary.get(ibkr_tag, "N/A"))

        # Account ID — from the first item's account field
        result["account_id"] = items[0].account if items else "unknown"
        result["currency"]   = summary.get("BaseCurrency", "USD")

        return result

    def get_positions(self) -> pd.DataFrame:
        """
        Return all currently open positions as a DataFrame.

        Returns:
            pd.DataFrame with columns:
                symbol         : str   — ticker (e.g. "AAPL")
                sec_type       : str   — "STK", "CASH", "FUT", etc.
                exchange       : str   — primary exchange
                currency       : str   — position currency
                position       : float — signed size (+ long, − short)
                avg_cost       : float — average cost per share/unit
                market_price   : float — last TWS mark price
                market_value   : float — position × market_price
                unrealised_pnl : float — floating P&L

            Returns an empty DataFrame with correct columns if no positions.

        Raises:
            IBKRConnectionError: if not connected.
        """
        self._require_connection()

        COLUMNS = [
            "symbol", "sec_type", "exchange", "currency",
            "position", "avg_cost", "market_price", "market_value", "unrealised_pnl",
        ]

        portfolio = self._ib.portfolio()
        if not portfolio:
            return pd.DataFrame(columns=COLUMNS)

        rows = []
        for item in portfolio:
            rows.append({
                "symbol":         item.contract.symbol,
                "sec_type":       item.contract.secType,
                "exchange":       item.contract.primaryExch or item.contract.exchange,
                "currency":       item.contract.currency,
                "position":       item.position,
                "avg_cost":       item.averageCost,
                "market_price":   item.marketPrice,
                "market_value":   item.marketValue,
                "unrealised_pnl": item.unrealizedPNL,
            })

        return pd.DataFrame(rows, columns=COLUMNS)

    # ── ORDERS ────────────────────────────────────────────────────────────────

    def _validate_action(self, action: str) -> str:
        """Normalise and validate a BUY/SELL action string."""
        action = action.upper()
        if action not in {"BUY", "SELL"}:
            raise ValueError(
                f"action must be 'BUY' or 'SELL', got '{action}'."
            )
        return action

    def place_market_order(
        self,
        symbol:   str,
        action:   str,
        quantity: int,
        exchange: str = "SMART",
        currency: str = "USD",
        sec_type: str = "STK",
    ):
        """
        Place a market order for immediate execution at best available price.

        Args:
            symbol:   Ticker, e.g. "AAPL"
            action:   "BUY" or "SELL"
            quantity: Number of shares/contracts (positive integer)
            exchange: Routing exchange (default "SMART")
            currency: Instrument currency (default "USD")
            sec_type: Security type (default "STK")

        Returns:
            ib_insync Trade object.  Check trade.orderStatus.status for
            fill progress ("Submitted", "Filled", "Cancelled", etc.).

        Raises:
            IBKRConnectionError, LiveTradingNotConfirmed, ValueError.
        """
        self._require_connection()
        self._require_live_confirmed()
        action   = self._validate_action(action)

        contract = self._build_contract(symbol, sec_type, exchange, currency)
        order    = MarketOrder(action, quantity)
        trade    = self._ib.placeOrder(contract, order)

        # Pump event loop once: transitions PreSubmitted → Submitted
        self._ib.sleep(0)

        self._logger.info(
            "Market order placed: %s %d %s (orderId=%s)",
            action, quantity, symbol, trade.order.orderId,
        )
        return trade

    def place_limit_order(
        self,
        symbol:      str,
        action:      str,
        quantity:    int,
        limit_price: float,
        exchange:    str   = "SMART",
        currency:    str   = "USD",
        sec_type:    str   = "STK",
    ):
        """
        Place a limit order — fill only at limit_price or better.

        Args:
            symbol:      Ticker
            action:      "BUY" or "SELL"
            quantity:    Number of shares/contracts
            limit_price: Max price for BUY; min price for SELL. Must be > 0.
            exchange:    Routing exchange
            currency:    Instrument currency
            sec_type:    Security type

        Returns:
            ib_insync Trade object.

        Raises:
            IBKRConnectionError, LiveTradingNotConfirmed, ValueError.

        Notes:
            Limit prices are rounded to 2 decimal places (US equity tick size).
            Passing more decimal places will be silently rounded by IBKR anyway,
            but explicit rounding here prevents unexpected rejections.
        """
        self._require_connection()
        self._require_live_confirmed()
        action      = self._validate_action(action)
        if limit_price <= 0:
            raise ValueError(f"limit_price must be > 0, got {limit_price}.")

        # Round to 2dp — IBKR's minimum tick for most US equities
        limit_price = round(limit_price, 2)

        contract = self._build_contract(symbol, sec_type, exchange, currency)
        order    = LimitOrder(action, quantity, limit_price)
        trade    = self._ib.placeOrder(contract, order)
        self._ib.sleep(0)

        self._logger.info(
            "Limit order placed: %s %d %s @ %.2f (orderId=%s)",
            action, quantity, symbol, limit_price, trade.order.orderId,
        )
        return trade

    def place_stop_order(
        self,
        symbol:     str,
        action:     str,
        quantity:   int,
        stop_price: float,
        exchange:   str   = "SMART",
        currency:   str   = "USD",
        sec_type:   str   = "STK",
    ):
        """
        Place a stop order — triggers a market order when price crosses stop_price.

        Use for stop-losses on existing positions.

        Args:
            symbol:     Ticker
            action:     "SELL" (stop-loss on a long) or "BUY" (cover a short)
            quantity:   Number of shares/contracts
            stop_price: Trigger price. Must be > 0.
            exchange:   Routing exchange
            currency:   Instrument currency
            sec_type:   Security type

        Returns:
            ib_insync Trade object.

        Raises:
            IBKRConnectionError, LiveTradingNotConfirmed, ValueError.

        Notes:
            Stop orders become market orders when triggered.  In fast markets
            the fill may be significantly worse than stop_price (gap risk).
            Consider StopLimitOrder if slippage control matters more than
            guaranteed execution.
        """
        self._require_connection()
        self._require_live_confirmed()
        action = self._validate_action(action)
        if stop_price <= 0:
            raise ValueError(f"stop_price must be > 0, got {stop_price}.")

        contract = self._build_contract(symbol, sec_type, exchange, currency)
        order    = StopOrder(action, quantity, stop_price)
        trade    = self._ib.placeOrder(contract, order)
        self._ib.sleep(0)

        self._logger.info(
            "Stop order placed: %s %d %s @ %.2f (orderId=%s)",
            action, quantity, symbol, stop_price, trade.order.orderId,
        )
        return trade

    def place_bracket_order(
        self,
        symbol:      str,
        action:      str,
        quantity:    int,
        limit_price: float,
        take_profit: float,
        stop_loss:   float,
        exchange:    str   = "SMART",
        currency:    str   = "USD",
        sec_type:    str   = "STK",
    ) -> list:
        """
        Place a bracket order: parent limit entry + take-profit + stop-loss.

        A bracket is three linked orders submitted together:
            1. Parent:  limit order to enter the position
            2. Child 1: limit order to exit at take_profit (profit target)
            3. Child 2: stop  order to exit at stop_loss  (risk limit)

        Only one child can fill.  When either executes, IBKR automatically
        cancels the other (One-Cancels-All).

        Args:
            symbol:      Ticker
            action:      "BUY" for a long entry; "SELL" for a short entry
            quantity:    Number of shares/contracts
            limit_price: Entry price for the parent limit order
            take_profit: Price to take profit (Child 1 limit)
            stop_loss:   Price to stop out   (Child 2 stop)
            exchange:    Routing exchange
            currency:    Instrument currency
            sec_type:    Security type

        Returns:
            List of three ib_insync Trade objects:
            [parent_trade, take_profit_trade, stop_loss_trade]

        Raises:
            IBKRConnectionError, LiveTradingNotConfirmed, ValueError.

        Notes:
            Do NOT modify ocaGroup or ocaType on the returned orders.
            ib_insync's bracketOrder() manages the OCA linkage internally.
            Overriding it will break the automatic cancellation and may
            leave both children live after one fills.
        """
        self._require_connection()
        self._require_live_confirmed()
        action = self._validate_action(action)

        for name, price in [("limit_price", limit_price),
                             ("take_profit", take_profit),
                             ("stop_loss",   stop_loss)]:
            if price <= 0:
                raise ValueError(f"{name} must be > 0, got {price}.")

        limit_price = round(limit_price, 2)
        take_profit = round(take_profit, 2)
        stop_loss   = round(stop_loss,   2)

        contract = self._build_contract(symbol, sec_type, exchange, currency)

        # bracketOrder returns a list of 3 Order objects: [parent, tp, sl]
        bracket = self._ib.bracketOrder(
            action,
            quantity,
            limitPrice=limit_price,
            takeProfitPrice=take_profit,
            stopLossPrice=stop_loss,
        )

        trades = [self._ib.placeOrder(contract, order) for order in bracket]
        self._ib.sleep(0)

        order_ids = [t.order.orderId for t in trades]
        self._logger.info(
            "Bracket order placed: %s %d %s entry=%.2f tp=%.2f sl=%.2f "
            "(orderIds=%s)",
            action, quantity, symbol,
            limit_price, take_profit, stop_loss,
            order_ids,
        )
        return trades

    def cancel_order(self, trade) -> None:
        """
        Cancel a pending open order.

        Args:
            trade: ib_insync Trade object returned by a place_*_order method.

        Notes:
            Cancellation is asynchronous — the order status transitions to
            'Cancelled' after TWS acknowledges the request. Call
            self._ib.sleep(1) after this if you need to confirm cancellation
            before proceeding.
        """
        self._require_connection()
        self._ib.cancelOrder(trade.order)
        self._logger.info("Cancel requested for orderId=%s.", trade.order.orderId)

    def get_open_orders(self) -> list:
        """
        Return a list of all currently open orders as Trade objects.

        Returns:
            List of ib_insync Trade objects (status "Submitted", "PreSubmitted",
            or "PendingSubmit"). Each Trade carries .contract, .order, and
            .orderStatus so callers have full context. Empty list if none.
        """
        self._require_connection()
        return self._ib.openTrades()

    # ── OMS BRIDGE ────────────────────────────────────────────────────────────

    def sync_to_oms(self, oms: OMS) -> int:
        """
        Read live IBKR positions and push them into an OMS instance.

        This is the integration bridge between the live broker and the OMS
        paper trading tracker. Use at session start to seed an OMS with the
        real current state of your account, then use the OMS for P&L and
        drawdown monitoring throughout the session.

        Typical workflow:
            oms = OMS(starting_capital=100_000)
            with IBKRBroker(paper=True) as broker:
                broker.sync_to_oms(oms)
                # OMS now reflects current account positions
                print(oms.summary())

        Mapping from IBKR PortfolioItem → OMS:
            contract.symbol      → ticker
            position > 0         → direction = +1  (long)
            position < 0         → direction = -1  (short)
            int(abs(position))   → quantity
            averageCost          → entry_price (cost basis)
            marketPrice          → mark-to-market price (set immediately)

        Args:
            oms: An OMS instance to receive the positions.
                 Positions are added via oms.open_position() followed by
                 oms.mark_to_market() so unrealised_pnl is correct immediately.

        Returns:
            Number of positions synced (int).

        Raises:
            IBKRConnectionError: if not connected.
            PositionSyncError:   if any position's averageCost ≤ 0.
                                 IBKR sometimes reports cost=0 on first connect
                                 while account data loads — wait a few seconds
                                 and retry if you see this error.

        Notes:
            Fractional share positions (e.g. 0.5 AAPL) are skipped with a
            warning since OMS.quantity must be a whole number.
            Duplicate tickers (rare — can occur on advisor accounts) produce
            a warning; the last occurrence wins.
        """
        self._require_connection()

        portfolio = self._ib.portfolio()

        # Filter out fully closed positions (IBKR sometimes keeps 0-quantity items)
        active = [item for item in portfolio if item.position != 0]

        # Check for duplicate tickers — warn but don't crash
        seen_tickers: dict = {}
        for item in active:
            sym = item.contract.symbol
            if sym in seen_tickers:
                self._logger.warning(
                    "Duplicate ticker '%s' in IBKR portfolio. "
                    "The last entry will overwrite the first in OMS.", sym
                )
            seen_tickers[sym] = item

        synced = 0
        for item in seen_tickers.values():
            sym = item.contract.symbol

            # Guard: fractional shares can't be stored in OMS (int quantity)
            int_qty = int(abs(item.position))
            if int_qty == 0:
                self._logger.warning(
                    "Skipping '%s': fractional position %.4f cannot be represented "
                    "as an integer quantity in OMS.", sym, item.position
                )
                continue

            # Guard: zero/negative cost basis is unreliable for P&L calculation
            if item.averageCost <= 0:
                raise PositionSyncError(
                    f"Cannot sync '{sym}': averageCost={item.averageCost}. "
                    f"IBKR sometimes reports 0.0 cost on first connect. "
                    f"Wait a few seconds and retry sync_to_oms()."
                )

            direction = 1 if item.position > 0 else -1

            oms.open_position(
                ticker=sym,
                direction=direction,
                quantity=int_qty,
                price=item.averageCost,
            )
            # Immediately mark to current market price so unrealised_pnl is live
            oms.mark_to_market({sym: item.marketPrice})
            synced += 1

        self._logger.info("Synced %d position(s) from IBKR to OMS.", synced)
        return synced
