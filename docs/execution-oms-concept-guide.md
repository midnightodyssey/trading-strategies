# Order Management System (OMS) â€” Concept Guide

*Category: Execution*
*Depth: Balanced*
*Generated: 2026-03-07*

---

## Order and Position Dataclasses

### What They Are
`Order` and `Position` are dataclasses that represent the two fundamental units of trade tracking. `Order` is the instruction ("I want to buy X shares at Y price"). `Position` is the live state ("I currently hold X shares, entered at Y, now worth Z").

### How They Work
Both use Python's `@dataclass` decorator, which auto-generates `__init__`, `__repr__`, and comparison methods from the field declarations â€” less boilerplate than a regular class.

`Position` has two computed properties:

- **`unrealised_pnl`**: `direction Ã— quantity Ã— (current_price âˆ’ entry_price)`. The `direction` multiplier (1 or -1) ensures a long position profits when price rises and a short position profits when price falls.
- **`market_value`**: `quantity Ã— current_price` â€” the current notional exposure regardless of direction.

### The Intuition
Separating `Order` (intent) from `Position` (state) mirrors how real OMS systems work. An order gets submitted; a fill creates a position; the position is marked to market each bar until it's closed. The OMS class uses `Position` objects as its internal state, not `Order` objects â€” orders are transient, positions are persistent.

### In the Code
```python
@property
def unrealised_pnl(self) -> float:
    return self.direction * self.quantity * (self.current_price - self.entry_price)
```

### Watch Out For
- `direction` must be exactly `1` or `-1`. Fractional directions are not supported in the dataclass â€” use the sizing functions in `sizing.py` to set `quantity` instead.
- `Order` has an optional `timestamp` field for logging. If you're running live, always populate this â€” it's essential for post-session reconciliation.
- `current_price` on a `Position` starts equal to `entry_price` (no P&L at entry) and is updated by `mark_to_market()` each bar.

---

## OMS â€” The Order Management System

### What It Is
`OMS` is the paper trading engine that tracks everything you'd want to monitor during a live or simulated trading session: open positions, their floating P&L, locked-in P&L from closed trades, current drawdown, and a complete trade history. It's designed to mirror what a real OMS does without needing broker connectivity.

### How It Works
The OMS maintains four core pieces of state:

- `_positions` â€” a dict of `{ticker: Position}` for all currently open trades
- `_realised_pnl` â€” cumulative P&L from all closed trades (never decreases on a winning trade)
- `_peak_equity` â€” the highest equity level reached so far (used for drawdown calculation)
- `_trade_log` â€” a list of dicts recording every completed trade

The four computed properties derive everything else from this state:

```
equity           = starting_capital + realised_pnl + unrealised_pnl
current_drawdown = (equity - peak_equity) / peak_equity
```

### The Intuition
The OMS is your real-time dashboard. Where `risk.py` gives you historical analysis of a backtest, the OMS gives you live monitoring during execution. The key distinction between realised and unrealised P&L matters enormously for prop firm challenges â€” your drawdown limit is based on *equity* (which includes unrealised), not just realised P&L.

### Watch Out For
- `open_position()` replaces any existing position for the same ticker without averaging in. If you need position averaging (adding to a winner), you'd need to extend this method to compute a weighted average entry price.
- `current_drawdown` updates `_peak_equity` as a side effect when called. This means the property is not purely read-only â€” calling it repeatedly is safe but slightly unusual for a property.
- The OMS has no broker connectivity â€” it's paper trading only. For live execution, `open_position()` would need to be wired to a broker API (IBKR, Alpaca, etc.).

---

## open_position and close_position

### What They Are
`open_position()` and `close_position()` are the two primary trading operations. Opening creates a new `Position` object in `_positions`. Closing removes it, calculates realised P&L, and appends a record to the trade log.

### How It Works
**Opening**: Creates a `Position` with `current_price = entry_price` (zero unrealised P&L at entry). Stores it in `_positions` keyed by ticker.

**Closing**: Pops the position from `_positions` (removing it from the open book), sets `current_price` to the exit price, calls `pos.unrealised_pnl` to compute the trade result (which at exit equals the realised P&L), adds it to `_realised_pnl`, and appends a record to `_trade_log` with all relevant trade details.

### The Intuition
The moment you close a position, floating P&L becomes locked-in P&L. The `_realised_pnl` counter only moves when trades close. Between entry and exit, the P&L fluctuates in `unrealised_pnl` â€” this is the number that drives drawdown risk on a prop firm challenge.

### In the Code
```python
def close_position(self, ticker, price, timestamp=None) -> float:
    pos               = self._positions.pop(ticker)
    pos.current_price = price
    realised          = pos.unrealised_pnl       # at exit, unrealised = realised
    self._realised_pnl += realised
    self._trade_log.append({...})
    return realised
```

### Watch Out For
- `close_position()` silently returns `0.0` if the ticker isn't in `_positions`. This is a safe default but could mask bugs â€” consider logging a warning in production use.
- `close_position()` returns the trade P&L as a float, which can be used for immediate feedback (e.g. "Trade closed: +Â£250").
- There's no partial close support â€” the entire position is closed at once. Scaling out of a position would require multiple calls with quantity tracking added.

---

## mark_to_market

### What It Is
`mark_to_market()` updates the `current_price` on all open positions to reflect the latest market prices, and updates the peak equity used for drawdown calculations. It should be called once per bar (or tick) with a dict of current prices.

### How It Works
The function iterates over the provided `prices` dict and updates `current_price` on any matching open positions. It then updates `_peak_equity` to the higher of the current and previous peak. Positions not in the `prices` dict are left unchanged (stale price â€” fine if the asset didn't trade that bar).

### The Intuition
Mark-to-market is how unrealised P&L stays current. Without calling this, `unrealised_pnl` would be stuck at zero (since `current_price` starts equal to `entry_price`). In a live system, you'd call `mark_to_market()` with every tick or at the close of each bar.

### In the Code
```python
def mark_to_market(self, prices: dict) -> None:
    for ticker, price in prices.items():
        if ticker in self._positions:
            self._positions[ticker].current_price = price
    self._peak_equity = max(self._peak_equity, self.equity)
```

### Watch Out For
- Always call `mark_to_market()` before reading `current_drawdown` or `unrealised_pnl` â€” otherwise you're reading stale values.
- If a position is open but not included in the `prices` dict, it retains its last known price. This is intentional for assets that don't trade every bar.

---

## Drawdown Monitoring

### What It Is
`current_drawdown` is the OMS's real-time equivalent of `max_drawdown` from `risk.py`. It measures how far current equity has fallen from the highest equity level seen during the session â€” expressed as a negative fraction.

### How It Works
The property recomputes `_peak_equity` as the max of itself and current equity, then returns `(equity âˆ’ peak) / peak`. Because equity can only equal the peak or be below it, this is always â‰¤ 0.

### The Intuition
This is the number that gets you failed on a prop firm challenge. FTMO's 10% max drawdown is measured on *equity* (including unrealised P&L on open positions) from the *daily high water mark*. You don't need to close trades to breach the limit â€” a large open loss counts. Monitoring `current_drawdown` continuously lets you cut positions before the limit is hit.

### In the Code
```python
@property
def current_drawdown(self) -> float:
    self._peak_equity = max(self._peak_equity, self.equity)
    return (self.equity - self._peak_equity) / self._peak_equity
```

### Watch Out For
- FTMO tracks drawdown from the *daily* peak, not the all-time peak. You may need to reset `_peak_equity` at the start of each trading day in a live implementation.
- A drawdown of `-0.08` means you're 8% below your peak. If the limit is 10%, you have only 2% of capital remaining before the challenge fails â€” time to reduce exposure.
- `current_drawdown` returns `0.0` if `_peak_equity` is 0 (defensive guard against division by zero).

---

## summary and trade_log

### What They Are
`summary()` returns a snapshot dict of the current OMS state â€” equity, P&L, drawdown, trade count, and win rate. `trade_log()` returns the full history of closed trades as a pandas DataFrame, one row per trade.

### How They Work
`summary()` computes win rate as the fraction of rows in the trade log where `pnl > 0`. `trade_log()` converts `_trade_log` (a list of dicts) into a DataFrame. If no trades have been closed yet, it returns an empty DataFrame with the correct column names â€” preventing downstream errors if you try to analyse an empty log.

### The Intuition
`summary()` is your session dashboard â€” run it after each trade or at the end of each bar to see where you stand. `trade_log()` is your post-session review â€” use it to compute win rate, average win/loss, and feed the results into the Kelly criterion sizing function.

### Watch Out For
- Win rate in `summary()` is computed from *closed* trades only. Open positions are not included, even if they're currently profitable.
- The trade log `direction` column is `1` or `-1`. Remember this when analysing â€” a negative P&L on a short trade (`direction = -1`) means price rose after entry.

---

## Concept Relationships

```
sizing.py
    â””â”€â”€ fixed_fraction() / vol_target()
              â”‚
              â–¼  (quantity)
    OMS.open_position(ticker, direction, quantity, price)
              â”‚
              â–¼
    OMS._positions {ticker: Position}
              â”‚
    [each bar] OMS.mark_to_market(prices)
              â”‚
              â”œâ”€â”€ OMS.unrealised_pnl      â† floating P&L
              â”œâ”€â”€ OMS.equity              â† capital + total P&L
              â””â”€â”€ OMS.current_drawdown    â† live drawdown vs peak
              â”‚
    OMS.close_position(ticker, price)
              â”‚
              â”œâ”€â”€ OMS.realised_pnl        â† locked-in P&L
              â””â”€â”€ OMS.trade_log()         â† feeds kelly() in sizing.py
```

---

## Glossary

| Term | Definition |
|---|---|
| OMS | Order Management System â€” tracks positions, P&L, and trade history |
| Realised P&L | Locked-in profit or loss from closed trades |
| Unrealised P&L | Floating profit or loss on currently open positions |
| Mark-to-market | Updating open position values to reflect current market prices |
| High water mark | The peak equity level reached â€” the reference point for drawdown |
| Drawdown | (current equity âˆ’ peak equity) / peak equity â€” always â‰¤ 0 |
| Paper trading | Simulated trading with no real money â€” used to validate strategy before going live |
| Trade log | Record of all completed trades with entry, exit, and P&L details |
| Win rate | Fraction of closed trades with positive P&L |

---

## Further Reading

- **"Algorithmic Trading"** â€” Ernest Chan. Chapter 6 covers live execution infrastructure including OMS design, position tracking, and real-time risk monitoring.
- **FTMO Rules documentation** â€” ftmo.com. The exact drawdown rules for prop firm challenges â€” essential reading before deploying any live strategy.

