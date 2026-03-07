# Momentum Strategy — Concept Guide
*Source: `framework/strategies/momentum.py`*
*Depth: Balanced*
*Generated: 2026-03-07*

---

## Momentum / Breakout (Core Concept)

### What It Is
Momentum strategies trade *with* strong price moves rather than against them. The core assumption is trend persistence: assets that have been moving powerfully in one direction tend to continue in that direction. You enter after a breakout and ride the trend for its full duration.

This is the philosophical opposite of mean reversion. Where mean reversion sells strength and buys weakness, momentum buys strength and sells weakness.

### The Intuition
Momentum is one of the most academically well-documented market anomalies. Jegadeesh & Titman (1993) showed that stocks performing well over the past 3–12 months tend to continue outperforming over the next 3–12 months. This premium has persisted for 30+ years across equities, futures, FX, and commodities. The explanation varies — underreaction to news, trend-chasing by institutional investors, slow diffusion of information — but the effect is real.

### Watch Out For
- Momentum strategies suffer sharp, sudden reversals — drawdowns tend to be abrupt rather than gradual. You need a clear stop-loss or exit rule.
- Transaction costs matter more for momentum strategies than for mean reversion, because you're entering *after* the move has started (chasing), not at the extreme (positioning).
- Momentum tends to perform badly during sharp macro reversals (e.g. crisis periods when everything correlates and reverses simultaneously).

---

## PriceBreakout

### What It Is
`PriceBreakout` is a direct implementation of the Turtle Trading system — one of the most famous systematic trading strategies in history. It goes long when today's close breaks above the N-day high and short when it breaks below the N-day low. When price is within its recent range, it holds flat.

### How It Works
The strategy computes the rolling maximum and minimum of the *previous* N closes using `.shift(1).rolling(period)`. The `.shift(1)` is critical — it ensures today's price is being compared against the range of the *prior* N days, not including today. Without this, a bar that opens, trades within the range, and then closes at a new high would be compared against a range that already includes that high — a form of circular look-ahead.

```
Close > N-day prior high  →  breakout up   →  long  (+1)
Close < N-day prior low   →  breakout down →  short (-1)
Close within range        →  no edge       →  flat  (0)
```

The warmup period is `period` bars — before that, `rolling_high` is `NaN` and the signal is forced to `0`.

### The Intuition
A close at the highest level in 20 days means every single person who bought in the past 20 days is profitable. There are no underwater sellers creating overhead resistance. This is a sign of genuine buying interest — not just a random fluctuation. The Turtle system bet that this kind of breakout would attract more buyers, continuing the move.

### In the Code
```python
# Shift by 1 to avoid including today's price in the comparison range
rolling_high = df["Close"].shift(1).rolling(self.period).max()
rolling_low  = df["Close"].shift(1).rolling(self.period).min()

signal = pd.Series(0.0, index=df.index)
signal[close > rolling_high] =  1.0
signal[close < rolling_low]  = -1.0
signal[rolling_high.isna()]  =  0.0
```

### Watch Out For
- **The `.shift(1)` is doing double duty here.** The backtest engine also applies a 1-bar lag via `signals.shift(1)` in `run_backtest()`. This means the total lag from signal generation to execution is effectively 2 bars — the breakout on day T is detected using data through T-1, and the position is entered on day T+1. This is realistic: you see the close, confirm the breakout after market hours, and execute at the next open.
- A 20-day breakout generates relatively infrequent signals. In quiet, range-bound markets, there may be weeks without any breakout — the strategy simply stays flat. This is correct behaviour.
- The original Turtle system used **two** channel lengths: 20-day for entries and 10-day for exits (a closer channel). This implementation has no explicit exit rule — it holds until a breakout in the opposite direction. Adding a shorter exit channel (e.g. `period // 2`) would reduce drawdowns significantly.
- Breakout strategies can look poor in backtests on clean price data because slippage on actual breakout bars tends to be higher — everyone sees the same level and the fill is worse than the close price.

---

## The Turtle Trading System (Historical Context)

### What It Is
In 1983, commodities trader Richard Dennis made a bet with his partner William Eckhardt: could ordinary people be taught to trade systematically and make money? He recruited 23 people — the "Turtles" — taught them a simple breakout system, and gave them real money to trade. The results were extraordinary: the Turtles generated hundreds of millions in profits over the following years.

### Why It Matters
The Turtle experiment is the most famous proof that systematic trading rules work — and that the rules themselves are less important than the discipline to follow them. The core entry rule (20-day channel breakout) is exactly what `PriceBreakout` implements. The key lessons from the experiment:

1. A simple, rules-based system beats discretionary trading for most people
2. Position sizing and risk management mattered more than entry signals
3. The strategy worked because it rode the big trends and cut losses quickly on false breakouts

### Watch Out For
- The Turtle rules were designed for futures markets with high leverage and deep liquidity. Performance on equities and crypto may differ significantly.
- The original system's edge has been partially arbitraged away as more traders adopted it. The 20-day breakout on major futures is now crowded; less common periods (e.g. 55-day) may have better edge.

---

## Concept Relationships

```
data.py → df["Close"]
               │
               ▼
   PriceBreakout.generate_signals()
               │
               ├── shift(1)          ← Prevents circular look-ahead
               ├── rolling(N).max()  ← N-day prior high
               ├── rolling(N).min()  ← N-day prior low
               │
               ▼
   pd.Series of signals (-1, 0, 1)
               │
               ▼
   Strategy.run() → run_backtest()
               │
               ▼
         BacktestResult
```

**Momentum vs Mean Reversion comparison:**

| Property | PriceBreakout (Momentum) | RSI/Bollinger (Mean Reversion) |
|---|---|---|
| Core assumption | Trend persistence | Price extremes revert to mean |
| Entry timing | After breakout (late) | At the extreme (early) |
| Best regime | Trending markets | Range-bound markets |
| Drawdown profile | Sharp, sudden | Gradual, grinding |
| Signal frequency | Low (breakouts are rare) | Moderate to low |
| Transaction costs | Higher (chasing) | Lower (positioning) |

---

## Glossary

| Term | Definition |
|---|---|
| Momentum | The tendency of strongly moving assets to continue in that direction |
| Breakout | When price closes beyond a prior significant high or low |
| Channel | The range defined by the rolling N-day high and low |
| N-day high | The maximum closing price over the prior N bars |
| Trend persistence | The statistical tendency for trends to continue once established |
| Turtle Trading | Famous 1983 experiment proving systematic breakout trading works at scale |
| Rolling max/min | pandas functions that compute the highest/lowest value in a sliding window |
| `.shift(1)` | Moves a series back by one bar — used here to exclude today's price from the comparison range |
| Overhead resistance | Sellers who bought at higher prices and want to break even — absent when making N-day highs |

---

## Further Reading

- **"The Complete TurtleTrader"** — Michael Covel. The full story of the Turtle experiment, including the actual rules (which were kept secret for years).
- **"Following the Trend"** — Andreas Clenow. Modern implementation of Turtle-style breakout systems across futures, with full backtest analysis.
- **Jegadeesh & Titman (1993)** — "Returns to Buying Winners and Selling Losers". The foundational academic paper on the momentum premium — freely available online.
