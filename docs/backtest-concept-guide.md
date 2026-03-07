# Backtesting Engine — Concept Guide
*Source: `framework/backtest.py`*
*Depth: Balanced*
*Generated: 2026-03-07*

---

## BacktestResult (Data Container)

### What It Is
`BacktestResult` is a dataclass that bundles all outputs from a backtest into a single structured object. Rather than returning multiple separate variables, the engine packs everything into one container that can be passed around, stored, and compared cleanly.

### How It Works
A Python `@dataclass` automatically generates `__init__`, `__repr__`, and `__eq__` methods from the field declarations. The five fields it holds are:

- `returns` — net daily strategy returns after all costs
- `equity_curve` — cumulative compounded growth starting at 1.0
- `positions` — the lagged position series (what you actually held)
- `trades` — count of how many times the position changed
- `metrics` — dict of risk metrics from `risk_summary()`

### The Intuition
Think of `BacktestResult` as the envelope you hand to anyone who wants to evaluate the strategy — they don't need to know how it was computed, just what's inside.

### Watch Out For
- `returns` are *net* (after slippage and commission). Don't compare them against gross P&L figures.
- `equity_curve` starts at 1.0, so `iloc[-1]` gives you the growth multiple (e.g. 1.35 = 35% total return).
- `positions` is already lagged — it reflects what was *held* each day, not what was signalled.

---

## run_backtest — The Core Engine

### What It Is
`run_backtest()` is the heart of the framework. It takes a signal series and a price series and simulates what would have happened if you'd traded those signals historically — including realistic transaction costs. It returns a complete `BacktestResult`.

### How It Works
The function runs in seven sequential steps, all vectorised (no Python loops):

**Step 1 — Align indices.** `signals.align(prices, join="inner")` ensures both series share exactly the same dates. Any date present in one but not the other is dropped.

**Step 2 — Lag signals by 1 bar.** `signals.shift(1)` is the single most important line in the engine. It enforces the rule: a signal generated at the close of day T can only be acted on at the open of day T+1. Without this, the backtest uses tomorrow's signal to trade today — look-ahead bias.

**Step 3 — Gross daily returns.** Daily price returns (`pct_change()`) multiplied by the position gives raw P&L. A position of `1` on a day when price rises 0.5% gives +0.5% gross return. A position of `-1` gives -0.5% (short loses when price rises).

**Step 4 — Trading costs.** Every time the position changes, costs are deducted. `positions.diff().abs()` captures the magnitude of each change regardless of direction. The cost model is:

```
cost = |Δposition| × (2 × slippage + commission)
```

Slippage is charged twice (once in, once out). Net returns = gross returns − costs.

**Step 5 — Equity curve.** `(1 + net_returns).cumprod()` compounds daily returns into a running account value starting at 1.0.

**Step 6 — Trade count.** Counts bars where `position_changes > 0` — i.e. how many days involved an entry, exit, or size change.

**Step 7 — Risk metrics.** Passes cleaned net returns to `risk_summary()` from `risk.py` to compute the full suite of Sharpe, Sortino, MDD, Calmar, VaR, and CVaR.

### The Intuition
The engine converts "what I would have done" signals into "what would have happened to my money" — with the harsh reality of costs included. The 1-bar lag and cost model are what separate a realistic backtest from an overfit fantasy.

### In the Code
```python
signals, prices  = signals.align(prices, join="inner")
positions        = signals.shift(1).fillna(0)          # lag — critical
price_returns    = prices.pct_change()
gross_returns    = positions * price_returns
position_changes = positions.diff().abs().fillna(0)
trade_costs      = position_changes * (2 * slippage + commission)
net_returns      = gross_returns - trade_costs
equity_curve     = (1 + net_returns).cumprod()
```

### Watch Out For
- **Look-ahead bias** is the most common backtest mistake. Removing `.shift(1)` makes results look significantly better — and completely meaningless.
- The cost defaults (5 bps slippage, 10 bps commission) are reasonable for liquid futures. They will be too low for illiquid equities or crypto.
- `pct_change()` produces a `NaN` for the first bar. Combined with the lag, the first two bars of `net_returns` will always be `NaN` — this is expected and handled by `dropna()` before `risk_summary()`.
- Fractional signals (e.g. 0.5 for half-size) work correctly — the cost model scales with `|Δposition|` so partial entries are costed proportionally.

---

## Walk-Forward Validation

### What It Is
Walk-forward validation splits the full history into N windows and runs each backtest only on the *out-of-sample* (OOS) portion of each window — the data the strategy never "saw" during development. It's the closest proxy for live performance that historical data can provide.

### How It Works
The full date range is divided into `n_splits` equal-sized windows. For each window:

1. The first `train_pct` (default 70%) is the "training" period — where you'd optimise parameters in your strategy
2. The remaining 30% is the OOS test period
3. `run_backtest()` is called on the OOS slice only
4. The result is appended to a list

After all splits, you have `n_splits` independent `BacktestResult` objects, each covering a different OOS period.

### The Intuition
A single full-history backtest is like studying with the answer key — your strategy has implicitly been fitted to every regime in the data. Walk-forward forces you to prove the strategy works on data it has never touched. Prop firms care about OOS Sharpe, not in-sample Sharpe. If your OOS results are dramatically worse than in-sample, the strategy is overfit.

### In the Code
```python
window_size = n // n_splits
for i in range(n_splits):
    start     = i * window_size
    train_end = start + int(window_size * train_pct)
    end       = start + window_size   # (or n for the last split)

    test_signals = signals.iloc[train_end:end]   # OOS only
    test_prices  = prices.iloc[train_end:end]
    result = run_backtest(test_signals, test_prices, ...)
    results.append(result)
```

### Watch Out For
- **The training period is structurally skipped** — this engine defines the split but doesn't re-optimise parameters on the training data. You need to do that separately in your strategy layer.
- With `n_splits=5` and `train_pct=0.7`, each OOS window covers only 6% of total history. Short OOS windows produce unreliable statistics — consider fewer splits or longer data history.
- Walk-forward still suffers from distribution shift: market regimes change, and past OOS performance may not reflect future conditions.
- The last split uses `end = n` to ensure no data is wasted at the tail.

---

## summary_table — Reporting

### What It Is
A lightweight formatting function that converts a `BacktestResult` into a pandas `Series` suitable for display or side-by-side strategy comparison. It extends the standard risk metrics with two additional fields: trade count and terminal equity.

### How It Works
It starts with a copy of `result.metrics` (the dict from `risk_summary()`), then appends:
- `Trades` — how many position changes occurred
- `Final Equity` — the last value of the equity curve (e.g. 1.42 = 42% total return)

The result is a `pd.Series`, so multiple strategies can be compared via `pd.DataFrame([summary_table(r1), summary_table(r2)])`.

### The Intuition
`summary_table()` is the reporting layer — it doesn't compute anything new, it just presents what's already in the `BacktestResult` in a format that's easy to read and compare.

### Watch Out For
- `Final Equity` tells you total return but not annualised return — 42% over 10 years is very different from 42% over 1 year.
- High `Trades` with poor Sharpe is a red flag — churning costs are eating the edge.
- Always call `.dropna()` before reading `iloc[-1]` on the equity curve if there could be leading NaNs.

---

## Concept Relationships

```
indicators.py
    │
    └──► Strategy generates signals (pd.Series: -1, 0, 1)
                          │
                          ▼
              backtest.py: run_backtest()
                │
                ├── signals.shift(1)         ← Look-ahead prevention
                ├── positions × returns      ← P&L simulation
                ├── position_changes × cost  ← Realistic cost model
                └── (1 + net_returns).cumprod() ← Equity curve
                          │
                          ▼
                    risk.py: risk_summary()
                          │
                          ▼
                    BacktestResult
                    (returns, equity_curve,
                     positions, trades, metrics)
                          │
                          ├──► walk_forward()    — OOS validation
                          └──► summary_table()   — Reporting
```

The 1-bar signal lag is the critical handoff point between signal generation and position simulation — it's the line that makes the difference between a realistic backtest and an illusion.

---

## Glossary

| Term | Definition |
|---|---|
| Vectorised | Operations applied to entire arrays at once using pandas/numpy — no Python loops, much faster |
| Look-ahead bias | Using future data to make past trading decisions, producing unrealistically good backtest results |
| Signal lag | Shifting signals forward by 1 bar so today's signal only affects tomorrow's position |
| Gross return | P&L before deducting transaction costs |
| Net return | P&L after slippage and commission are deducted |
| Slippage | The difference between the expected trade price and the actual fill price |
| Commission | Broker fee per trade, expressed as a fraction of position size |
| Equity curve | Cumulative compounded growth of a £1 investment through the strategy |
| Out-of-sample (OOS) | Data the strategy was never shown during development — the honest test |
| In-sample | Data used to develop or fit the strategy — always looks better than OOS |
| Walk-forward | Validation method that tests a strategy on rolling OOS windows |
| Overfit | A strategy that performs well in-sample but fails OOS because it memorised historical noise |
| BacktestResult | Dataclass container holding all outputs from a single backtest run |
| pct_change() | pandas method that computes day-over-day percentage return |
| cumprod() | pandas method that compounds returns into a running equity curve |

---

## Further Reading

- **"Advances in Financial Machine Learning"** — Marcos López de Prado. Chapters 11–14 cover backtesting pitfalls, combinatorial purging, and walk-forward testing in depth.
- **"Evidence-Based Technical Analysis"** — David Aronson. Rigorous statistical framework for evaluating whether backtest results are genuine or noise.
- **pandas `shift()` documentation** — [pandas.pydata.org](https://pandas.pydata.org/docs/reference/api/pandas.Series.shift.html). Understanding shift is fundamental to avoiding look-ahead bias in any vectorised backtest.
