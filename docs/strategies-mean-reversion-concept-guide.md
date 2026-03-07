# Mean Reversion Strategies — Concept Guide
*Source: `framework/strategies/mean_reversion.py`*
*Depth: Balanced*
*Generated: 2026-03-07*

---

## Mean Reversion (Core Concept)

### What It Is
Mean reversion strategies bet that prices which have moved far from their historical average will return to it. The further and faster the deviation, the stronger the pull back toward the mean — and the better the entry opportunity. This is the philosophical opposite of trend following.

### How It Works
Both strategies in this file identify when price has reached an "extreme" — defined either by RSI (how fast it moved) or Bollinger Bands (how far it moved statistically). At extremes, the strategy fades the move: buying weakness, shorting strength.

### The Intuition
Mean reversion is grounded in the idea that markets overshoot. Panic selling pushes prices below fair value; euphoric buying pushes them above. The reversion happens not because buyers suddenly appear, but because the sellers (or buyers) who drove the extreme simply exhaust themselves. Mean reversion strategies try to be the liquidity provider on the other side of that exhaustion.

### Watch Out For
- Mean reversion and trend following are fundamentally incompatible assumptions. A trending market will destroy a mean reversion strategy. Always identify the market regime before applying these strategies.
- "Buying the dip" in a genuine bear market is the most common mean reversion failure — the RSI can stay below 30 for months in a sustained downtrend.
- Both strategies here are **always positioned** when outside the neutral zone — there's no size scaling based on signal strength. Adding position sizing based on RSI distance from threshold or band penetration depth would make these more robust.

---

## RSIMeanReversion

### What It Is
`RSIMeanReversion` goes long when RSI falls below the oversold threshold (default 30) and short when RSI rises above the overbought threshold (default 70). When RSI is between the thresholds, it holds flat — this is the key difference from trend-following strategies, which are always in the market.

### How It Works
The code computes RSI from `indicators.py`, then uses vectorised comparisons to assign signals. A clean three-zone structure:

```
RSI < 30  →  oversold  →  long  (+1)
RSI > 70  →  overbought →  short (-1)
30 ≤ RSI ≤ 70  →  neutral  →  flat (0)
```

The `0.0` fill for `NaN` values handles the 14-bar RSI warmup period.

### The Intuition
RSI measures the *velocity* of price change. An RSI below 30 doesn't mean price is cheap — it means price has fallen very fast recently. The bet is that this selling velocity is unsustainable and will slow, allowing price to recover. You're not predicting a reversal; you're betting on exhaustion.

### In the Code
```python
rsi_vals = rsi(df["Close"], self.period)

signal = pd.Series(0.0, index=df.index)
signal[rsi_vals <  self.oversold]   =  1.0   # oversold → long
signal[rsi_vals >  self.overbought] = -1.0   # overbought → short
signal[rsi_vals.isna()] = 0.0
```

### Watch Out For
- The 30/70 thresholds produce signals relatively frequently. For higher-conviction, lower-frequency signals, tighten to 20/80.
- RSI mean reversion has a well-documented tendency to work on short timeframes (1–5 days) but is less reliable as a longer-term hold. Consider adding an exit condition (e.g. RSI returning to 50) rather than holding until the opposite threshold is hit.
- RSI can be in oversold territory for extended periods during genuine bear markets. A long-only version (only taking the long signal, never shorting) often performs better on equity indices where there's a long-term upward drift.

---

## BollingerMeanReversion

### What It Is
`BollingerMeanReversion` goes long when price closes below the lower Bollinger Band and short when price closes above the upper band. It stays flat when price is inside the bands. The logic is that band touches are statistically rare events (~5% of bars) that should revert to the mean.

### How It Works
The strategy calls `bollinger_bands()` from `indicators.py` to get the upper, middle, and lower bands. It then compares the raw close price against the upper and lower bands directly — a price *outside* the band is the signal. The middle band (SMA) is not used for signal generation here, only the extremes.

```
Close < lower  →  statistically cheap  →  long  (+1)
Close > upper  →  statistically expensive  →  short (-1)
Inside bands   →  normal range  →  flat (0)
```

### The Intuition
If returns were truly normally distributed, only 5% of closes would fall outside a 2σ envelope. Each touch of the band is therefore a low-probability event. The bet is that the same force that creates the bands — mean reversion in volatility — will also pull price back toward the middle. You're essentially selling statistical outliers.

### In the Code
```python
upper, middle, lower = bollinger_bands(df["Close"], self.period, self.std_dev)
close = df["Close"]

signal = pd.Series(0.0, index=df.index)
signal[close < lower] =  1.0
signal[close > upper] = -1.0
signal[upper.isna()]  =  0.0
```

### Watch Out For
- **Bollinger himself warned against using band touches as standalone signals.** A close outside the upper band can be the *start* of a breakout, not a reversal. Context matters enormously — in trending markets, fading the bands destroys capital.
- This implementation has no exit logic — it holds until the opposite band is touched. In practice, you'd want to exit when price returns to the middle band (SMA), not wait for an extreme in the other direction.
- Consider combining with RSI: only take the long signal if RSI is also below 40, only take the short signal if RSI is also above 60. This dual-confirmation approach significantly reduces false entries.

---

## Concept Relationships

```
indicators.py
    ├── rsi()              ──►  RSIMeanReversion.generate_signals()
    └── bollinger_bands()  ──►  BollingerMeanReversion.generate_signals()
                                          │
                                          ▼
                                pd.Series of signals (-1, 0, 1)
                                          │
                                          ▼
                               Strategy.run() → run_backtest()
```

**RSI vs Bollinger mean reversion comparison:**

| Property | RSIMeanReversion | BollingerMeanReversion |
|---|---|---|
| Measures | Speed of price change | Distance from mean (in σ) |
| Signal frequency | Moderate | Low (only ~5% of bars) |
| Neutral zone | RSI 30–70 | Inside the bands |
| Key parameter | period, thresholds | period, std_dev |
| Weakness | Trending markets | Breakout / trending markets |

The two strategies often generate signals at similar times (an extreme RSI reading frequently coincides with a Bollinger Band touch), but they measure different things — combining both as a confirmation filter is a common enhancement.

---

## Glossary

| Term | Definition |
|---|---|
| Mean reversion | The tendency of prices to return to their historical average after an extreme deviation |
| Oversold | RSI below the lower threshold — price has fallen fast recently; potential long entry |
| Overbought | RSI above the upper threshold — price has risen fast recently; potential short entry |
| Band touch | When price closes at or beyond the Bollinger upper or lower band |
| Neutral zone | The range of RSI values (or band positions) where no signal is generated |
| Fade | Trading against a move — buying weakness or selling strength |
| Exhaustion | When the momentum behind a move runs out of participants, causing a reversal |
| Regime | The market environment (trending vs mean-reverting) that determines which strategy type is appropriate |

---

## Further Reading

- **"Mean Reversion Trading Systems"** — Howard Bandy. Dedicated treatment of quantitative mean reversion, including RSI and Bollinger Band systems with statistical validation.
- **"Bollinger on Bollinger Bands"** — John Bollinger. The definitive guide — particularly Chapter 8 on using %B and BandWidth to avoid false signals.
- **Jegadeesh & Titman (1993)** — "Returns to Buying Winners and Selling Losers". The academic paper establishing momentum as a premium, which implicitly defines when mean reversion *doesn't* work.
