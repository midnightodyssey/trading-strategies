# Broker sub-package — Interactive Brokers integration via ib_insync
# Build order: indicators -> risk -> backtest -> data -> strategies -> execution -> [broker]

from .ibkr import (
    IBKRBroker,
    IBKRConnectionError,
    LiveTradingNotConfirmed,
    PositionSyncError,
)
from .config import (
    ConnectionConfig,
    TWS_PAPER_PORT,
    TWS_LIVE_PORT,
    GATEWAY_PAPER_PORT,
    GATEWAY_LIVE_PORT,
)
from .options import (
    OptionOrderIntent,
    option_contract_from_intent,
    option_order_from_intent,
    preview_option_orders,
    strategy_position_to_option_intents,
)
