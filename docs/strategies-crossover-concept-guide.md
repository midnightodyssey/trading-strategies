# Crossover Strategies — Concept Guide
*Source: `framework/strategies/crossover.py`*
*Depth: Balanced*
*Generated: 2026-03-07*

---

## Moving Average Crossover (Core Concept)

### What It Is
A crossover strategy generates signals based on the relationship between two moving averages of different speeds — a fast one (tracks recent price closely) and a slow one (tracks the longer-term trend). When the fast average rises above the slow, the trend is assumed to be bullish. When it falls below, bearish.

### How It Works
Both strategies in this file follow identical logic:

```
fast > slow  →  signal = +1  (long)
fast < slow  →  signal = -1  (short)
either NaN   →  signal =  0  (warmup, no position)
```

The difference between `EMACrossover` and `SMACrossover` is purely which averaging method is used — EMA (exponentially weighted, faster) vs SMA (equally weighted, slower). This single difference changes the number of signals generated, the timing of entries, and the sensitivity to noise.

### The Intuition
When a faster-moving average crosses above a slower one, it means recent price action is outpacing the longer-term average — the market is gaining upward momentum. The crossover is the moment the short-term trend begins to exceed the long-term trend. The strategy bets that this divergence will persist long enough to profit from.

### Watch Out For
- Both strategies are **always in the market** — either long or short, never flat (except during warmup). This means there's no "sitting out" of choppy, range-bound markets where crossover strategies repeatedly lose small amounts.
- Crossovers are **lagging signals by definition** — the fast average can only cross after a move has already begun. You will never buy the bottom or sell the top.
- The strategies produce binary signals (`+1` or `-1`). You could introduce a filter (e.g. only go long if above the 200 SMA) to avoid taking short signals in a bull market.

---

## EMACrossover

### What It Is
`EMACrossover` uses two Exponential Moving Averages — a fast EMA and a slow EMA — and goes long when the fast is above the slow, short when below. The default parameters (12/26) are the same periods used in MACD, making this one of the most widely studied entry systems in technical analysis.

### How It Works
The code calls `ema(df["Close"], fast)` and `ema(df["Close"], slow)` from `indicators.py`, then applies vectorised comparison operators to assign signals across the full Series at once. The `.isna()` check zeroes out the warmup period — before the slow EMA has enough history to compute, no position is taken.

### The Intuition
EMA's recency bias means it pivots faster than SMA — you get earlier entries when a trend begins, but also more false signals when price oscillates. The 12/26 pairing is the market standard because it balances responsiveness with noise resistance. It's essentially MACD expressed as a position rather than a value.

### In the Code
```python
fast_ema = ema(df["Close"], self.fast)   # default 12
slow_ema = ema(df["Close"], self.slow)   # default 26

signal = pd.Series(0.0, index=df.index)
signal[fast_ema > slow_ema] =  1.0
signal[fast_ema < slow_ema] = -1.0
signal[fast_ema.isna() | slow_ema.isna()] = 0.0
```

### Watch Out For
- The warmup period for the slow EMA is `slow - 1` bars. With default parameters, the first 25 bars produce no signal. This is small relative to a multi-year backtest but matters for short datasets.
- EMA crossovers generate significantly more trades than SMA crossovers with equivalent periods — more transaction costs. Always check `result.trades` vs Sharpe when evaluating.
- Consider 9/21 as an alternative to 12/26 for intraday or short-timeframe applications.

---

## SMACrossover

### What It Is
`SMACrossover` uses two Simple Moving Averages and applies the same crossover logic. The default parameters (20/50) target medium-term trends. The classic 50/200 pairing produces the famous "Golden Cross" and "Death Cross" signals watched by institutional traders globally.

### How It Works
Identical structure to `EMACrossover` — calls `sma()` instead of `ema()`, with different default periods. SMA's equal weighting means it responds more slowly to recent price changes, producing fewer but more decisive crossover signals.

### The Intuition
The 50/200 SMA crossover is one of the most self-reinforcing signals in markets. When the 50-day SMA crosses above the 200-day (Golden Cross), it's reported across financial media and triggers institutional buying — which itself drives the trend. The signal works partly because everyone is watching it.

### In the Code
```python
fast_sma = sma(df["Close"], self.fast)   # default 20
slow_sma = sma(df["Close"], self.slow)   # default 50

signal = pd.Series(0.0, index=df.index)
signal[fast_sma > slow_sma] =  1.0
signal[fast_sma < slow_sma] = -1.0
signal[fast_sma.isna() | slow_sma.isna()] = 0.0
```

### Watch Out For
- The 50/200 pairing requires 199 bars of warmup before generating any signal. On daily data that's almost a full year — ensure your backtest dataset is long enough.
- SMA crossovers react slowly to reversals. In a sharp selloff, the 50/200 death cross often signals *after* most of the damage has been done.
- The Golden/Death Cross is widely watched and therefore partially priced in — its edge on liquid large-cap equities has diminished over time. It tends to work better on less-followed assets.

---

## Concept Relationships

```
indicators.py
    ├── ema()  ──►  EMACrossover.generate_signals()
    └── sma()  ──►  SMACrossover.generate_signals()
                              │
                              ▼
                    pd.Series of signals (-1, 0, 1)
                              │
                              ▼
                   Strategy.run() → run_backtest()
```

Both strategies are interchangeable at the `run()` level — same input (OHLCV DataFrame), same output (`BacktestResult`). This is the benefit of the shared base class.

**EMA vs SMA crossover comparison:**

| Property | EMACrossover | SMACrossover |
|---|---|---|
| Reaction speed | Faster | Slower |
| False signals | More | Fewer |
| Typical trade count | Higher | Lower |
| Best timeframe | Intraday / Daily | Daily / Weekly |
| Classic parameters | 12/26 (MACD) | 50/200 (Golden Cross) |

---

## Glossary

| Term | Definition |
|---|---|
| Crossover | When a faster average crosses above or below a slower average — the signal trigger |
| Golden Cross | 50 SMA crossing above 200 SMA — widely watched bullish signal |
| Death Cross | 50 SMA crossing below 200 SMA — widely watched bearish signal |
| Whipsaw | Rapid back-and-forth crossovers in a choppy market that generate small losses repeatedly |
| Warmup period | Bars at the start of a dataset before the slow average has enough history to compute |
| Trend following | Trading in the direction of an established price trend, as opposed to mean reversion |

---

## Further Reading

- **"Following the Trend"** — Andreas Clenow. Practical guide to systematic trend following, with detailed treatment of moving average systems across futures markets.
- **"Trading for a Living"** — Alexander Elder. Covers the triple screen system which combines multiple timeframe MA crossovers with oscillator confirmation.
