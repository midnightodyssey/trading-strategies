"""
framework/broker/config.py
─────────────────────────────────────────────────────────────────────────────
Connection constants and configuration for the Interactive Brokers integration.

Port reference:
    TWS Paper:      7497   ← most common for development
    TWS Live:       7496
    Gateway Paper:  4002   ← for headless / overnight automated running
    Gateway Live:   4001

TWS vs IB Gateway:
    TWS (Trader Workstation) is the full GUI application.  Use it while
    actively developing — you can see orders and positions in real-time.
    IB Gateway is the lightweight headless variant.  Lower memory footprint,
    no GUI, preferred for fully automated / scheduled overnight strategies.

Build order: indicators → risk → backtest → data → strategies → execution → [broker]
"""

from dataclasses import dataclass
from typing import Optional


# ─── PORT CONSTANTS ───────────────────────────────────────────────────────────

TWS_PAPER_PORT:      int = 7497
TWS_LIVE_PORT:       int = 7496
GATEWAY_PAPER_PORT:  int = 4002
GATEWAY_LIVE_PORT:   int = 4001

DEFAULT_HOST:        str = "127.0.0.1"
DEFAULT_CLIENT_ID:   int = 1


# ─── CONNECTION CONFIG ────────────────────────────────────────────────────────

@dataclass
class ConnectionConfig:
    """
    Immutable connection parameters for an IBKRBroker instance.

    Pass this to IBKRBroker if you want to share config across multiple
    broker instances, or just pass keyword args directly to IBKRBroker().

    Attributes:
        host:      IP address of the TWS / Gateway host.
                   "127.0.0.1" for local machine (standard).
                   Change only if running TWS on a remote machine.
        port:      TCP port. If None, auto-selected by resolved_port() based
                   on paper and gateway flags.
        client_id: Integer client ID sent to TWS. Must be unique per
                   simultaneous connection. Use 1 for a single automated
                   session; increment if running multiple scripts at once
                   against the same TWS instance (e.g. 1, 2, 3...).
        paper:     True → paper trading account (default).
                   False → live account.
        gateway:   True → targeting IB Gateway (headless).
                   False → targeting Trader Workstation (GUI).
        timeout:   Seconds to wait for TWS to respond during connect().
                   Default 10. Increase on slow networks or remote TWS.

    Examples:
        # Paper account on local TWS (most common for development):
        cfg = ConnectionConfig()                        # port=7497

        # Live account on local TWS:
        cfg = ConnectionConfig(paper=False)             # port=7496

        # Paper account on IB Gateway (automated overnight use):
        cfg = ConnectionConfig(gateway=True)            # port=4002

        # Custom port override (if TWS is configured non-standard):
        cfg = ConnectionConfig(port=7777)
    """
    host:      str          = DEFAULT_HOST
    port:      Optional[int] = None
    client_id: int          = DEFAULT_CLIENT_ID
    paper:     bool         = True
    gateway:   bool         = False
    timeout:   int          = 10

    def resolved_port(self) -> int:
        """
        Return the effective port, applying auto-selection if port is None.

        Auto-selection matrix:
            paper=True,  gateway=False → 7497  (TWS Paper)
            paper=False, gateway=False → 7496  (TWS Live)
            paper=True,  gateway=True  → 4002  (Gateway Paper)
            paper=False, gateway=True  → 4001  (Gateway Live)

        An explicit port override always takes precedence.

        Returns:
            int — port to pass to ib_insync IB.connect()
        """
        if self.port is not None:
            return self.port

        if self.gateway:
            return GATEWAY_PAPER_PORT if self.paper else GATEWAY_LIVE_PORT
        else:
            return TWS_PAPER_PORT if self.paper else TWS_LIVE_PORT
