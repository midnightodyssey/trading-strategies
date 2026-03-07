# Technical Indicators — Concept Guide
*Source: `framework/indicators.py`*
*Depth: Balanced*
*Generated: 2026-03-07*

---

## Simple Moving Average (SMA)

### What It Is
The SMA is the most basic way to smooth out price data. It takes the last `n` closing prices, adds them up, and divides by `n` — producing a rolling average that filters out short-term noise and reveals the underlying trend direction.

### How It Works
At each bar, pandas' `rolling(period).mean()` computes the average of the prior `period` closes. The first `period - 1` bars return `NaN` because there isn't enough data yet. A 200-period SMA on daily data, for example, only starts outputting values from day 200 onwards.

The SMA treats every bar in the window equally — yesterday's close and the close from 50 days ago have identical weight.

### The Intuition
All moving averages are lag machines. The SMA lags the most — but that lag is also its strength on higher timeframes, filtering out the noise that causes false signals on faster averages.

### In the Code
```python
def sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(period).mean()
```

### Watch Out For
- SMA is slow to react to sudden price moves. In fast-moving markets, price can be 5–10% away before the SMA catches up.
- Longer periods (e.g. SMA 200) are reliable trend filters; shorter ones (e.g. SMA 5) produce noisy signals.
- Crossovers of two SMAs (e.g. 50 crosses above 200 = "golden cross") are lagging signals by definition.

---

## Exponential Moving Average (EMA)

### What It Is
The EMA is a smarter moving average that gives more weight to recent prices. Instead of treating all bars equally, it applies an exponentially decaying multiplier so that yesterday's close matters more than the close from a month ago.

### How It Works
The multiplier is `2 / (period + 1)`. Each new EMA value is computed as:

```
EMA = (current_price × multiplier) + (previous_EMA × (1 − multiplier))
```

This recursive formula means every prior price technically influences the EMA — but the influence decays exponentially with age. The `adjust=False` parameter in pandas' `ewm()` ensures this recursive approach is used (as opposed to a weighted average over the whole series).

### The Intuition
EMA reacts faster than SMA because recent prices dominate. This makes it better for signal generation, while the SMA's sluggishness makes it better for trend filtering. The 8/21 EMA crossover is a classic entry trigger for this reason.

### In the Code
```python
def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()
```

### Watch Out For
- EMA's responsiveness also means it produces more false signals in choppy, sideways markets.
- MACD is built entirely from EMAs, so any EMA quirks propagate into MACD signals.
- `adjust=True` vs `adjust=False` in pandas produces meaningfully different results — this code uses `False` (standard).

---

## Weighted Moving Average (WMA)

### What It Is
The WMA is a middle ground between SMA and EMA. It applies linearly increasing weights to bars within the window — the most recent bar gets weight `n`, the bar before that gets `n-1`, down to weight `1` for the oldest bar.

### How It Works
The code builds a weights array `[1, 2, 3, ..., period]` and computes a dot product between those weights and each rolling window of prices, then divides by the sum of the weights. The `raw=True` flag in `rolling().apply()` passes a NumPy array rather than a pandas Series, making the calculation faster.

### The Intuition
WMA gives you recency bias without EMA's exponential decay. Think of it as a "linear fade" — recent data matters more, but the relationship is proportional rather than exponential.

### Watch Out For
- WMA is less common than SMA/EMA in practice. If you're using it, be explicit about why.
- It appears in Hull Moving Average (HMA) calculations, which combine multiple WMAs to reduce lag.
- More computationally expensive than SMA or EMA due to the custom rolling function.

---

## Relative Strength Index (RSI)

### What It Is
RSI is a momentum oscillator that measures the speed and magnitude of price changes, expressed as a value between 0 and 100. It answers: "Are recent gains larger than recent losses, and by how much?" High RSI = recent up-moves dominated. Low RSI = recent down-moves dominated.

### How It Works
The calculation runs in five steps:
1. Compute day-to-day price changes (`series.diff()`)
2. Separate gains (positive changes) from losses (flipped to positive)
3. Smooth both over `period` bars using a rolling mean
4. Compute RS = avg_gain / avg_loss
5. RSI = 100 − (100 / (1 + RS))

When avg_loss → 0 (all gains), RSI approaches 100. When avg_gain → 0 (all losses), RSI approaches 0.

### The Intuition
RSI > 70 doesn't mean "sell now" — it means "price has moved a long way fast." In a strong trend, RSI can stay above 70 for weeks. The real power of RSI is *divergence*: if price makes a new high but RSI doesn't, momentum is fading — often a leading indicator of reversal.

### In the Code
```python
delta    = series.diff()
gain     = delta.clip(lower=0)
loss     = (-delta).clip(lower=0)
avg_gain = gain.rolling(period).mean()
avg_loss = loss.rolling(period).mean()
rs       = avg_gain / avg_loss
return 100 - (100 / (1 + rs))
```

### Watch Out For
- The 70/30 thresholds are guidelines, not rules. Adjust for the asset and timeframe.
- Rolling mean smoothing (used here) diverges slightly from Wilder's original exponential smoothing — this matters when comparing against published RSI values.
- Division by zero if `avg_loss` = 0 (all days were up). Pandas handles this with `inf`, but handle it in downstream logic.

---

## MACD (Moving Average Convergence Divergence)

### What It Is
MACD measures the relationship between two EMAs of different speeds, making it both a trend-following and momentum indicator. It returns three series: the MACD line, a signal line, and a histogram showing the difference between them.

### How It Works
- **MACD line** = EMA(12) − EMA(26): positive when fast EMA is above slow EMA (bullish momentum), negative when below
- **Signal line** = EMA(9) of the MACD line: a smoothed version used to trigger entries/exits
- **Histogram** = MACD line − Signal line: visualises momentum acceleration/deceleration

Default parameters (12, 26, 9) are Appel's original settings and remain the most widely used.

### The Intuition
MACD is a trend filter and a momentum indicator simultaneously. When the histogram crosses zero from below, momentum is shifting bullish. When MACD diverges from price (price makes a lower low but MACD doesn't), that's a potential reversal signal — and one of the most reliable setups in technical analysis.

### In the Code
```python
fast_ema    = ema(series, fast)       # 12-period
slow_ema    = ema(series, slow)       # 26-period
macd_line   = fast_ema - slow_ema
signal_line = macd_line.ewm(span=signal, adjust=False).mean()
histogram   = macd_line - signal_line
```

### Watch Out For
- MACD lags significantly at major reversals because it's built on EMAs (which themselves lag).
- The histogram crossing zero is a *slower* signal than the MACD/signal crossover.
- MACD values are price-denominated (not normalised), so you can't directly compare MACD values across assets with different price levels.

---

## Bollinger Bands

### What It Is
Bollinger Bands place a volatility envelope around a moving average. The upper and lower bands expand when markets are volatile and contract when markets are calm — making them a dynamic measure of "how far is too far."

### How It Works
The middle band is simply an SMA. The upper and lower bands are drawn at `std_dev` standard deviations above and below the middle:

```
Middle = SMA(20)
Upper  = Middle + 2 × rolling_std(20)
Lower  = Middle − 2 × rolling_std(20)
```

When volatility spikes, `rolling_std` increases, widening the bands. When markets are quiet, the bands squeeze together. Approximately 95% of price action should fall within 2σ bands under the normality assumption.

### The Intuition
Bollinger Bands don't tell you direction — they tell you *context*. A price touch of the upper band in a trending market is continuation. The same touch in a mean-reverting market is a fade. The most reliable signal is the **squeeze**: when bands narrow dramatically, a large move is imminent (direction unknown until the breakout).

### Watch Out For
- Touching a band is not a signal by itself. Context (trend, volume, other indicators) determines whether it's continuation or reversal.
- %B = (price − lower) / (upper − lower) normalises price position within the bands on a 0–1 scale.
- The 20-period, 2σ defaults are guidelines. Some traders use 10/1.5 for intraday or 50/2.5 for weekly charts.

---

## Average True Range (ATR)

### What It Is
ATR measures market volatility by accounting for overnight gaps — something a simple high-minus-low calculation misses. It captures the full range of price movement, including moves that occur between sessions.

### How It Works
For each bar, True Range is the largest of three values:
1. Today's high − today's low (the intraday range)
2. |Today's high − yesterday's close| (gap up scenario)
3. |Today's low − yesterday's close| (gap down scenario)

These three are computed using `pd.concat(...).max(axis=1)`, and the ATR is a rolling mean of True Range over the period (default 14).

### The Intuition
ATR is the right tool for stop placement. A 1.5× ATR stop adapts to current conditions — wider when markets are volatile (giving trades room to breathe), tighter when markets are calm (reducing risk). For a prop firm challenge, using ATR-based stops is how you stay within daily drawdown limits without getting stopped out by normal noise.

### In the Code
```python
prev_close = close.shift(1)
tr = pd.concat([
    high - low,
    (high - prev_close).abs(),
    (low  - prev_close).abs(),
], axis=1).max(axis=1)
return tr.rolling(period).mean()
```

### Watch Out For
- ATR is an absolute value (in price units), not a percentage. Use ATR/price for cross-asset comparisons.
- The first bar has no `prev_close`, so True Range for bar 1 is just the intraday range.
- Wilder's original ATR used exponential smoothing, not a simple rolling mean. Values diverge over time but signals are equivalent.

---

## Concept Relationships

```
Raw Price Data (OHLC)
       │
       ├──► SMA / EMA / WMA     →  Trend direction & crossover signals
       │         │
       │         └──► MACD      →  Momentum confirmation (built from EMAs)
       │
       ├──► RSI                 →  Overbought / oversold momentum
       │
       ├──► Bollinger Bands     →  Volatility context (squeeze / breakout)
       │         │
       │         └── uses SMA internally
       │
       └──► ATR                 →  Stop placement & position sizing
```

ATR is the output that feeds directly into risk management — it translates raw price volatility into a concrete number for setting stops and sizing positions.

---

## Glossary

| Term | Definition |
|---|---|
| SMA | Simple Moving Average — equal-weight rolling mean of closing prices |
| EMA | Exponential Moving Average — recent prices weighted more heavily |
| WMA | Weighted Moving Average — linearly increasing weights toward most recent bar |
| RSI | Relative Strength Index — momentum oscillator, 0–100 scale |
| MACD | Moving Average Convergence Divergence — trend + momentum indicator built from EMAs |
| Bollinger Bands | Volatility envelope: SMA ± n standard deviations |
| ATR | Average True Range — volatility measure accounting for overnight gaps |
| True Range | Largest of: high-low, \|high-prev_close\|, \|low-prev_close\| |
| Divergence | When price and an indicator move in opposite directions — often a leading reversal signal |
| Squeeze | When Bollinger Bands narrow significantly, signalling an impending large move |
| %B | (price − lower band) / (upper − lower) — normalised position within Bollinger Bands |

---

## Further Reading

- **"Technical Analysis of the Financial Markets"** — John Murphy. Chapters on RSI, MACD, and Bollinger Bands are the canonical reference.
- **"Bollinger on Bollinger Bands"** — John Bollinger. Direct from the inventor; covers %B and BandWidth applications in detail.
- **pandas `ewm()` documentation** — [pandas.pydata.org](https://pandas.pydata.org/docs/reference/api/pandas.Series.ewm.html). Essential for understanding `adjust=True` vs `adjust=False` and how EMA is actually computed.
