# Strategy Base Class â€” Concept Guide

*Category: Strategies*
*Depth: Balanced*
*Generated: 2026-03-07*

---

## Abstract Base Class (ABC)

### What It Is
`Strategy` is an abstract base class â€” a template that every strategy in the framework must inherit from. It enforces a consistent interface across all strategies and provides shared functionality for free, without each strategy needing to re-implement it.

### How It Works
Python's `ABC` (Abstract Base Class) mechanism works via the `@abstractmethod` decorator. Any class that inherits from `Strategy` *must* implement `generate_signals()` â€” if it doesn't, Python raises a `TypeError` the moment you try to instantiate it. This catches missing implementations immediately, not silently at runtime.

The base class provides two things:
- A `name` property that returns the class name as a human-readable label (e.g. `"EMACrossover"`)
- A `run()` method that calls `generate_signals()` and passes the result straight into `run_backtest()` from `backtest.py`

### The Intuition
Think of `Strategy` as a contract. It says: "I don't care how you generate signals â€” that's your job. But you *must* give me a signal series, and in return I'll handle the backtest, costs, and metrics for you." This separation of concerns means you can add a new strategy in ~10 lines without touching any backtest or risk code.

### In the Code
```python
class Strategy(ABC):

    @abstractmethod
    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        ...   # subclasses MUST implement this

    def run(self, df, slippage=0.0005, commission=0.001, ...) -> BacktestResult:
        signals = self.generate_signals(df)
        return run_backtest(signals, df["Close"], ...)
```

### Watch Out For
- If you forget to implement `generate_signals()` in a subclass, the error appears at *instantiation* (`MyStrategy()`), not when you call `.run()`. This is intentional â€” fail early and clearly.
- `run()` always passes `df["Close"]` as the price series to `run_backtest()`. If your strategy needs to trade on something other than Close (e.g. VWAP), you'd need to override `run()`.
- The `name` property returns the class name. Override it in your subclass if you want a more descriptive label (e.g. `"EMA 12/26 Crossover"`).

---

## generate_signals â€” The Signal Contract

### What It Is
`generate_signals()` is the only method you must implement when writing a new strategy. It takes the full OHLCV DataFrame and returns a Series of position signals â€” one value per bar â€” telling the backtest engine what position to hold.

### How It Works
The signal convention is:
- `+1` = long (hold a full long position for the next bar)
- `0` = flat (no position)
- `-1` = short (hold a full short position for the next bar)

Fractional values are valid (e.g. `0.5` = half-sized long), but most strategies use the three discrete values.

The returned Series must share the same index as the input DataFrame. Where there's insufficient history (warmup period), return `0` â€” not `NaN`.

### The Intuition
The signal is what you *intend* to do. The backtest engine then applies a 1-bar lag (turning intention into execution), deducts costs on changes, and computes P&L. Your job in `generate_signals()` is purely to encode the trading logic â€” everything else is handled downstream.

### Watch Out For
- **No look-ahead.** Only use information available at bar `t` to generate the signal at bar `t`. The backtest applies a 1-bar execution lag, but it's still your responsibility not to use `df["Close"].iloc[t+1]` or future indicators in your logic.
- **No NaNs.** The backtest engine expects clean signals. Fill warmup periods with `0`, not `NaN`.
- The signal at the *last* bar of the DataFrame will never actually be traded (there's no next bar to execute it on). This is correct behaviour â€” don't try to handle it specially.

---

## run â€” The Entry Point

### What It Is
`run()` is a convenience method that wraps the entire evaluation pipeline into a single call: generate signals â†’ run backtest â†’ return results. It's the main interface for comparing strategies.

### How It Works
It calls `self.generate_signals(df)` to get the signal series, then passes that alongside `df["Close"]` and the cost parameters to `run_backtest()` from `backtest.py`. The `BacktestResult` that comes back contains the full equity curve, returns, trade count, and all six risk metrics.

### The Intuition
Without `run()`, every strategy evaluation would require the same boilerplate: call `generate_signals`, call `run_backtest`, pass the right columns. `run()` eliminates that. You can loop over 10 strategies and call `.run(df)` on each in a single line.

### In the Code
```python
# Evaluating a strategy is one line:
result = EMACrossover(fast=12, slow=26).run(df)
print(result.metrics)

# Comparing multiple strategies:
strategies = [EMACrossover(), SMACrossover(), RSIMeanReversion()]
results = [s.run(df) for s in strategies]
```

### Watch Out For
- Cost defaults (5 bps slippage, 10 bps commission) are shared across all strategies. Override them when calling `.run()` if you need asset-specific cost assumptions.
- `run()` passes `df["Close"]` as prices â€” ensure your DataFrame always has a `"Close"` column (guaranteed if you used `data.py`).

---

## Concept Relationships

```
data.py â†’ df (OHLCV DataFrame)
                â”‚
                â–¼
        Strategy (base class)
                â”‚
                â”œâ”€â”€ generate_signals(df)     â† YOU implement this
                â”‚        â”‚
                â”‚        â–¼
                â”‚   pd.Series of signals (-1, 0, 1)
                â”‚
                â””â”€â”€ run(df)                  â† provided for free
                         â”‚
                         â–¼
               backtest.py: run_backtest()
                         â”‚
                         â–¼
                   BacktestResult
```

The base class is the bridge between the data layer (`data.py`) and the execution layer (`backtest.py`). Each concrete strategy only needs to implement the signal logic â€” the rest of the pipeline is inherited.

---

## Glossary

| Term | Definition |
|---|---|
| Abstract Base Class (ABC) | A class that cannot be instantiated directly; exists to define a shared interface for subclasses |
| `@abstractmethod` | Decorator that forces subclasses to implement the decorated method |
| Signal | A value (-1, 0, 1) indicating the desired position for the next bar |
| Warmup period | The initial bars where there's insufficient history to compute an indicator â€” signals should be 0 here |
| Look-ahead bias | Using future data in signal generation â€” makes backtests unrealistically good |
| Inheritance | When a class (e.g. `EMACrossover`) derives behaviour and structure from a parent class (`Strategy`) |

---

## Further Reading

- **Python `abc` module documentation** â€” [docs.python.org/3/library/abc.html](https://docs.python.org/3/library/abc.html). Covers `ABC`, `abstractmethod`, and the full ABC mechanism.
- **"Design Patterns"** â€” Gang of Four. The Template Method pattern (which is exactly what this base class implements) is covered in Chapter 5.

