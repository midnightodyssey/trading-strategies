# Risk Metrics — Concept Guide
*Source: `framework/risk.py`*
*Depth: Balanced*
*Generated: 2026-03-07*

---

## Sharpe Ratio

### What It Is
The Sharpe Ratio is the most universal measure of risk-adjusted return. It asks: "For every unit of volatility I tolerate, how much excess return do I earn above the risk-free rate?" A higher Sharpe means you're being compensated more efficiently for the risk you're taking.

### How It Works
The code computes daily excess returns (daily return minus the daily equivalent of the annual risk-free rate), then divides mean excess return by its standard deviation, and annualises by multiplying by √252:

```
Sharpe = (mean_daily_excess / std_daily_excess) × √252
```

The `risk_free_rate` defaults to 5% (annualised), divided by 252 to get the daily equivalent.

### The Intuition
A Sharpe of 1.0 means you earn one unit of return per unit of volatility. The prop firm target of ≥1.5 is demanding. Professional hedge funds average around 0.7–1.0; achieving 1.5+ consistently typically requires either a genuine statistical edge or a low-volatility strategy.

### In the Code
```python
daily_rf = risk_free_rate / TRADING_DAYS
excess   = returns - daily_rf
return float(excess.mean() / excess.std() * np.sqrt(TRADING_DAYS))
```

### Watch Out For
- Sharpe penalises *all* volatility equally — upside and downside. A strategy that wins big most days can have a misleadingly high Sharpe right up until a blowup.
- Assumes normally distributed returns. Strategies with frequent small gains and rare large losses (e.g. short volatility) can look excellent on Sharpe until they don't.
- Can be gamed by smoothing returns (e.g. holding illiquid positions at stale valuations).

---

## Sortino Ratio

### What It Is
The Sortino Ratio is Sharpe's more honest cousin for traders. It only penalises *downside* volatility — days when you lose money. Large up-days don't count against you, making Sortino a better measure for strategies with asymmetric return profiles.

### How It Works
The code filters excess returns to keep only negative values (`excess[excess < 0]`), computes the RMS (root mean square) of those losses, annualises by ×√252, and divides annualised mean excess return by this downside deviation:

```
Sortino = (mean_annual_excess) / annualised_downside_std
```

### The Intuition
If your strategy has a high Sharpe but a much lower Sortino, your volatility is mostly downside-heavy — a warning sign. If Sortino > Sharpe, your volatility is mostly upside — a good sign. Target Sortino > 2.0 for a strategy you'd trade at scale.

### In the Code
```python
excess       = returns - daily_rf
downside     = excess[excess < 0]
downside_std = np.sqrt((downside ** 2).mean()) * np.sqrt(TRADING_DAYS)
ann_excess   = excess.mean() * TRADING_DAYS
return float(ann_excess / downside_std)
```

### Watch Out For
- Sortino can look artificially strong in short backtest periods with few losing days.
- Choosing a higher target return threshold (instead of the risk-free rate) produces a stricter, more conservative Sortino.
- Sortino > 2.0 is the common benchmark for "excellent," but a 2.0 with 300 trades is more meaningful than with 30.

---

## Maximum Drawdown

### What It Is
Maximum Drawdown (MDD) measures the largest peak-to-trough decline in equity over the backtest period. It answers: "If I had the worst possible timing, how much of my account would I have lost before recovering?"

### How It Works
1. Build the equity curve as a compounded product: `(1 + r1)(1 + r2)...`
2. Track the running maximum (high water mark) via `cummax()`
3. Drawdown at each point = (current equity − peak) / peak — always ≤ 0
4. MDD = `drawdown.min()` — the worst (most negative) value

The result is a negative float, e.g. `-0.12` = a 12% drawdown.

### The Intuition
MDD is the metric that gets you failed on a prop firm challenge. FTMO's 10% limit means your strategy's *historical* MDD must be well below 10% — because live performance will eventually be worse than the best historical period. A strategy with a 7% historical MDD is dangerously close to the limit.

### In the Code
```python
equity_curve = (1 + returns).cumprod()
rolling_peak = equity_curve.cummax()
drawdown     = (equity_curve - rolling_peak) / rolling_peak
return float(drawdown.min())
```

### Watch Out For
- MDD is path-dependent — the same returns in a different order could produce a very different MDD.
- Time-to-recovery (how long to get back to the peak) is as important as the depth. Some strategies have small but very long drawdowns.
- MDD from a short backtest will almost certainly understate the true worst-case — real trading surfaces scenarios the backtest didn't.

---

## Calmar Ratio

### What It Is
The Calmar Ratio measures annualised return relative to the worst historical drawdown. Where Sharpe divides by volatility, Calmar divides by the maximum loss — making it the most relevant metric for drawdown-constrained accounts like prop firm challenges.

### How It Works
```
Calmar = Annual Return / |Max Drawdown|
```

The code computes `returns.mean() × 252` for the annualised return and `abs(max_drawdown(returns))` for the denominator. A Calmar of 1.0 means: "If I earn 10% annually, my worst historical drawdown was also 10%."

### The Intuition
Calmar forces you to confront the real cost of drawdowns. Target Calmar > 2.0 for prop firm viability: earning twice your maximum historical drawdown annually means you can absorb a full repeat of your worst-ever loss and still hit your annual target.

### In the Code
```python
mdd           = abs(max_drawdown(returns))
annual_return = returns.mean() * TRADING_DAYS
return float(annual_return / mdd)
```

### Watch Out For
- Calmar is highly sensitive to the backtest length. A longer period is more likely to capture the strategy's true worst drawdown.
- A Calmar that looks great on a 6-month backtest should be treated with scepticism until tested over a full market cycle.
- Like all metrics here, Calmar uses historical MDD — live trading will inevitably see worse.

---

## Value at Risk (VaR) — Parametric

### What It Is
VaR answers: "What is the maximum loss I should expect on a given day, with X% confidence?" At 95% confidence, a 2% VaR means losses will exceed 2% on only 5% of trading days.

### How It Works
The parametric approach assumes returns follow a normal distribution. Using the mean (`μ`) and standard deviation (`σ`) of the return series, it computes the z-score for the desired confidence level via `norm.ppf(1 - confidence)` — the inverse normal CDF. For 95% confidence, z ≈ −1.645.

```
VaR = -(μ + z × σ) × √horizon
```

The √horizon scaling allows projection to multi-day holding periods (valid only under the normality assumption).

### The Intuition
VaR gives you a loss *threshold*, not a loss *magnitude*. It tells you when you'll breach the fence, not how far you'll fall on the other side. That's the key limitation — addressed by CVaR below.

### In the Code
```python
mu    = returns.mean()
sigma = returns.std()
z     = norm.ppf(1 - confidence)     # e.g. -1.645 at 95%
var   = -(mu + z * sigma) * np.sqrt(horizon)
return float(var)
```

### Watch Out For
- Real return distributions have fat tails. Parametric VaR will underestimate tail risk, potentially by 2–3× in crisis periods.
- VaR does not tell you what happens *beyond* the threshold — two portfolios with identical VaR can have very different tail risks.
- The √T scaling for multi-day VaR assumes daily returns are independent and identically distributed — often false in practice.

---

## Conditional Value at Risk (CVaR / Expected Shortfall)

### What It Is
CVaR fixes VaR's fundamental flaw. Rather than asking "what is the loss threshold at X% confidence?", CVaR asks "given that we've breached that threshold, what is the *average* loss?" It's the expected loss in the worst (1 − confidence)% of scenarios.

### How It Works
The code identifies returns at or below the VaR threshold using `returns.quantile(1 - confidence)`, then takes the mean of those tail losses (negated to give a positive number):

```
CVaR = -mean(returns where returns ≤ VaR_threshold)
```

For 95% confidence, this averages the worst 5% of daily returns.

### The Intuition
CVaR is always greater than VaR because it averages the tail beyond VaR. The gap between CVaR and VaR tells you how "fat" your left tail is — a large CVaR/VaR ratio means your bad days are very bad, even if infrequent. Basel III replaced VaR with CVaR (Expected Shortfall) for precisely this reason.

### In the Code
```python
threshold   = returns.quantile(1 - confidence)
tail_losses = returns[returns <= threshold]
return float(-tail_losses.mean())
```

### Watch Out For
- CVaR depends on having enough tail observations — a short backtest may have very few data points in the tail, making the estimate unreliable.
- Historical CVaR (used here) and parametric CVaR (assumes normality) will diverge for fat-tailed assets. Historical is more honest.
- CVaR is sensitive to outliers — a single catastrophic day can dominate the metric.

---

## Risk Summary Function

### What It Is
`risk_summary()` is a convenience wrapper that runs all six metrics at once and returns them as a labelled dictionary, rounded to 4 decimal places. Useful for comparing strategies side-by-side or generating a quick scorecard.

### In the Code
```python
def risk_summary(returns, risk_free_rate=0.05) -> dict:
    return {
        "Sharpe Ratio":      round(sharpe(returns, risk_free_rate), 4),
        "Sortino Ratio":     round(sortino(returns, risk_free_rate), 4),
        "Max Drawdown":      round(max_drawdown(returns), 4),
        "Calmar Ratio":      round(calmar(returns), 4),
        "VaR (95%, 1-day)":  round(var_parametric(returns, 0.95), 4),
        "CVaR (95%, 1-day)": round(cvar(returns, 0.95), 4),
    }
```

---

## Concept Relationships

The six metrics cover three distinct dimensions of strategy quality:

```
Daily Returns Series
         │
         ├──► Sharpe Ratio      ─┐
         │                       ├── Return efficiency
         ├──► Sortino Ratio     ─┘   (Sortino = downside-only version of Sharpe)
         │
         ├──► Max Drawdown      ─┐
         │                       ├── Drawdown risk
         ├──► Calmar Ratio      ─┘   (Calmar = return ÷ MDD)
         │
         ├──► VaR (Parametric)  ─┐
         │                       ├── Tail risk
         └──► CVaR              ─┘   (CVaR = average loss beyond VaR threshold)
```

For a prop firm challenge, **Calmar and MDD are the most operationally critical** — breaching the drawdown limit ends the challenge. Sharpe/Sortino tell you the quality of the edge; VaR/CVaR tell you how bad the worst days are likely to be.

---

## Glossary

| Term | Definition |
|---|---|
| Sharpe Ratio | Annualised excess return divided by total volatility |
| Sortino Ratio | Like Sharpe, but only penalises downside volatility |
| Max Drawdown | Largest peak-to-trough equity decline, expressed as a negative % |
| Calmar Ratio | Annualised return divided by absolute max drawdown |
| VaR | Value at Risk — maximum loss at a given confidence level |
| CVaR | Conditional VaR — average loss in the tail beyond the VaR threshold |
| Expected Shortfall | Another name for CVaR; the Basel III standard for market risk |
| Fat Tails | Return distributions with more extreme outcomes than a normal distribution predicts |
| High Water Mark | The running peak equity value; the reference point for drawdown calculation |
| TRADING_DAYS | 252 — standard annualisation constant for US/UK equity markets |
| Downside Deviation | Standard deviation computed using only negative (loss) days |
| Parametric VaR | VaR calculated using a normal distribution assumption |
| Historical CVaR | CVaR calculated directly from actual return observations |

---

## Further Reading

- **"Options, Futures and Other Derivatives"** — John Hull. Chapter on Value at Risk and CVaR is thorough and practitioner-focused.
- **"Active Portfolio Management"** — Grinold & Kahn. Deep treatment of Sharpe ratio theory and information ratios.
- **Basel III Expected Shortfall** — BIS working papers on the shift from VaR to CVaR in regulatory capital frameworks.
