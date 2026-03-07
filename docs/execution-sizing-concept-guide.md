# Position Sizing — Concept Guide
*Source: `framework/execution/sizing.py`*
*Depth: Balanced*
*Generated: 2026-03-07*

---

## Position Sizing (Core Concept)

### What It Is
Position sizing answers the question that most traders ignore: not *what* to trade or *when* to trade it, but *how much* to trade. It's the function that converts a signal (long/short) into a concrete number of shares or contracts. Getting this wrong — oversizing — can bankrupt even a genuinely profitable strategy.

### The Intuition
Imagine a coin that lands heads 60% of the time. You have an edge. But if you bet your entire bankroll on each flip, a single loss wipes you out before the edge can compound. Position sizing is the mathematical framework for how much to bet so that the edge actually materialises over time without hitting ruin along the way.

### Watch Out For
- All three functions return an `int` (number of shares), not a fraction of capital. You need to supply the asset price to convert a capital allocation into a share count.
- Position sizing and stop-loss placement are inseparable. `fixed_fraction()` explicitly requires a stop distance — you must know your exit before sizing your entry.
- These functions give you the *maximum* sensible position for a single asset. In a multi-asset portfolio, you also need to think about correlation — two highly correlated positions sized individually can create combined risk that exceeds your limits.

---

## Fixed Fraction

### What It Is
Fixed Fraction sizing risks a fixed percentage of capital on every trade. If the stop is hit, you lose exactly `risk_pct × capital` — no more, no less. It's the default method for prop firm challenges because it's simple, transparent, and makes daily drawdown arithmetic trivial.

### How It Works
The formula runs in two steps:

1. **Risk amount** = `capital × risk_pct` — the maximum you're willing to lose on this trade in £/$ terms
2. **Stop distance** = `price × stop_pct` — the £/$ loss per share if the stop is hit
3. **Shares** = `risk_amount / stop_distance` — how many shares you can hold before the stop loss equals your risk amount

```
Example:
  capital = £100,000, risk_pct = 1% → risk £1,000
  price = £50, stop_pct = 2% → stop £1.00 below entry
  shares = £1,000 / £1.00 = 1,000 shares
  If stop hit: 1,000 × £1.00 = £1,000 loss = exactly 1% ✓
```

### The Intuition
With a 10% FTMO drawdown limit, risking 1% per trade means you'd need 10 consecutive losing trades to breach the limit. Risking 2% means only 5 losses. The percentage you choose reflects how many consecutive losses you expect in the worst case — and how much buffer you want between normal bad luck and failing the challenge.

### In the Code
```python
risk_amount   = capital * risk_pct
stop_distance = price * stop_pct
return int(risk_amount / stop_distance)
```

### Watch Out For
- `stop_pct` must reflect where you'll *actually* place your stop, not a wishful estimate. If you widen your stop after entry, your realised risk per trade exceeds the intended amount.
- The function floors the result with `int()` — you'll always trade slightly less than the maximum risk amount, which is the conservative and correct choice.
- Returns `0` if `stop_pct <= 0` or `price <= 0` — a defensive guard against division by zero. Always validate inputs before calling.
- For ATR-based stops (as used in `indicators.py`), convert the ATR value to a percentage: `stop_pct = atr_value / current_price`.

---

## Kelly Criterion

### What It Is
The Kelly Criterion is the mathematically optimal fraction of capital to risk per trade, given your historical win rate and average win/loss sizes. It maximises the long-run geometric growth rate of your capital — bet more than Kelly and you will eventually go broke; bet less and you grow more slowly than optimal.

### How It Works
The formula:

```
f* = win_rate / avg_loss − loss_rate / avg_win
```

Where `loss_rate = 1 − win_rate`. Breaking this down intuitively:
- `win_rate / avg_loss` = how much edge you gain per unit of loss-size from winning
- `loss_rate / avg_win` = how much edge you lose per unit of win-size from losing
- The difference = net edge per unit of bet

A positive `f*` means you have a positive-expectancy strategy. A negative `f*` means the strategy has negative expected value — don't trade it.

### The Intuition
Kelly is elegant but brutal in practice. Full Kelly produces enormous variance — drawdowns of 50% are mathematically expected even with a strong edge. Almost all practitioners use **half Kelly** (`f* / 2`), which retains roughly 75% of the maximum growth rate at dramatically lower risk. Think of it as buying insurance on the uncertainty in your win rate estimates.

### In the Code
```python
loss_rate = 1.0 - win_rate
return float(win_rate / avg_loss - loss_rate / avg_win)

# In practice, apply half Kelly:
fraction = kelly(win_rate, avg_win, avg_loss) / 2
shares   = fixed_fraction(capital, fraction, stop_pct, price)
```

### Watch Out For
- Kelly requires accurate estimates of `win_rate`, `avg_win`, and `avg_loss`. These come from your `OMS.trade_log()` — but they need a large sample (100+ trades) to be reliable. Kelly computed from 20 trades is dangerously noisy.
- If your win rate is below 50% but your average win is much larger than your average loss (e.g. 40% win rate, 3:1 win/loss ratio), Kelly can still be positive. Don't assume you need >50% winners to have an edge.
- Kelly returns a fraction, not shares. You still need to combine it with a stop distance (via `fixed_fraction`) or a price to get a share count.
- A Kelly output above 1.0 (bet more than 100% of capital) is theoretically valid but requires leverage. For prop firm accounts, cap the fraction at a sensible maximum (e.g. 0.25).

---

## Volatility Targeting

### What It Is
Volatility targeting sizes positions so that each asset contributes a consistent, pre-specified level of portfolio volatility — regardless of how volatile the asset itself is. It's the institutional standard used by every major CTA (Commodity Trading Advisor) fund including Man AHL, Winton, and Two Sigma.

### How It Works
The core insight is that a 20% volatile asset needs half the position size of a 10% volatile asset to contribute the same portfolio risk:

```
position_value = capital × (target_vol / asset_vol)
shares         = position_value / price
```

If you're targeting 10% annual portfolio vol and an asset has 20% annual vol, you allocate `£100,000 × (10% / 20%) = £50,000` to it. If the asset has 5% vol, you allocate `£100,000 × (10% / 5%) = £200,000`.

### The Intuition
Volatility targeting creates a portfolio where risk is consistent regardless of what you're trading. Without it, holding one position in a calm asset (e.g. treasury bonds) and one in a volatile asset (e.g. Bitcoin) creates massively uneven risk — the volatile asset dominates your P&L even if you hold equal capital in both. Vol targeting automatically scales down volatile assets and scales up calm ones.

### In the Code
```python
position_value = capital * (target_vol / asset_vol)
return int(position_value / price)
```

### Watch Out For
- `asset_vol` must be annualised (expressed as an annual percentage, e.g. 0.20 = 20%). Compute this from `indicators.py`'s ATR or from the rolling standard deviation of returns, then annualise by multiplying by `√252`.
- Vol targeting can produce very large position sizes for low-volatility assets (e.g. bonds). Always cap at a sensible maximum notional (e.g. 200% of capital) to avoid unintended leverage.
- Vol estimates change over time. Recompute `asset_vol` regularly (e.g. using a 20-day or 60-day rolling window) and rebalance positions accordingly — this is part of what makes vol targeting a dynamic system, not a one-time calculation.
- In a multi-asset portfolio, vol targeting handles individual asset risk but doesn't account for correlation. Two 10%-vol assets that are 90% correlated together contribute more risk than two uncorrelated assets. Proper portfolio-level vol targeting requires a covariance matrix.

---

## Concept Relationships

The three sizing methods form a hierarchy of sophistication, each suited to different contexts:

```
Strategy signal (long/short)
         │
         ▼
  Which sizing method?
         │
         ├── fixed_fraction()     ← Default: prop firm challenges, simple accounts
         │       │                   Inputs: capital, risk_pct, stop_pct, price
         │       │
         ├── kelly()              ← Optimisation: after accumulating 100+ trades
         │       │                   Feeds into fixed_fraction() as the risk_pct
         │       │                   Source: OMS.trade_log() win rate + avg P&L
         │       │
         └── vol_target()         ← Multi-asset / institutional: consistent risk
                 │                   Inputs: capital, target_vol, asset_vol, price
                 │                   asset_vol from: ATR or rolling std × √252
                 ▼
         quantity (int: shares/contracts)
                 │
                 ▼
         OMS.open_position(ticker, direction, quantity, price)
```

**Sizing method comparison:**

| Method | Best for | Key input | Complexity |
|---|---|---|---|
| Fixed Fraction | Prop firm challenges, beginners | Stop loss % | Low |
| Kelly Criterion | Optimising bet size after many trades | Win rate + avg P&L | Medium |
| Vol Targeting | Multi-asset portfolios, CTAs | Asset volatility | High |

---

## Glossary

| Term | Definition |
|---|---|
| Position sizing | Determining the quantity of an asset to trade given a signal |
| Fixed fraction | Risking a consistent % of capital on every trade |
| Risk amount | The maximum £/$ loss acceptable on a single trade |
| Stop distance | The £/$ per share lost if the stop is triggered |
| Kelly Criterion | Formula for the optimal betting fraction that maximises long-run geometric growth |
| Half Kelly | Kelly fraction divided by 2 — common practical adjustment for estimate uncertainty |
| Win rate | Fraction of trades with positive P&L |
| Expected value (EV) | Probability-weighted average outcome — positive EV required for Kelly > 0 |
| Volatility targeting | Sizing positions so each contributes a consistent level of portfolio risk |
| Annualised volatility | Daily return standard deviation × √252 — standardised for comparison |
| CTA | Commodity Trading Advisor — a fund that trades systematic futures strategies |
| Geometric growth | Compounding returns — what actually matters for long-run wealth, not arithmetic average |
| Ruin | Losing all capital — mathematically guaranteed if you consistently bet more than the Kelly fraction |

---

## Further Reading

- **"The Kelly Capital Growth Investment Criterion"** — MacLean, Thorp & Ziemba. The definitive academic treatment of Kelly betting, including why half Kelly is preferred in practice.
- **"Following the Trend"** — Andreas Clenow. Chapters 9–10 cover volatility targeting in detail as applied to CTA-style futures portfolios.
- **"Algorithmic Trading"** — Ernest Chan. Chapter 5 covers position sizing with worked examples in Python, including Kelly and volatility targeting.
- **Ed Thorp** — "Beat the Dealer" and his hedge fund writings. Thorp popularised Kelly in financial markets and his insights on half Kelly remain the practitioner standard.
