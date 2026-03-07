# Portfolio Backtesting — Concept Guide
*Source: `framework/portfolio.py`*
*Depth: Balanced*
*Generated: 2026-03-07*

---

## Why Portfolio Backtesting?

### What It Is
A single-strategy backtest tells you if one idea works in isolation. A portfolio backtest tells you whether multiple ideas *combine* well — and combination is where real risk-adjusted returns are built. `portfolio.py` provides the tools to run multiple strategies together, weight them intelligently, and measure the diversification benefit they provide each other.

### The Intuition
Diversification is often called the only free lunch in finance. Two uncorrelated strategies with identical Sharpe ratios, when combined equally, produce a portfolio with the same expected return but *lower* volatility — improving Sharpe by approximately √2. The portfolio module quantifies this benefit and ensures you're actually capturing it, rather than combining strategies that are secretly moving together.

---

## PortfolioResult (Data Container)

### What It Is
`PortfolioResult` is a dataclass that holds the complete output of a portfolio backtest — analogous to `BacktestResult` in `backtest.py`, but extended to capture multi-strategy information.

### How It Works
It holds six fields:
- `returns` — the combined daily portfolio return series (weighted sum of all strategies)
- `equity_curve` — cumulative compounded growth starting at 1.0
- `component_returns` — a DataFrame where each column is one strategy's daily net returns
- `weights` — the final normalised weights applied to each strategy
- `metrics` — portfolio-level risk/return statistics (Sharpe, Sortino, MDD, Calmar, DR)
- `correlation` — the pairwise correlation matrix of component strategy returns

### Watch Out For
- `weights` in the result are the *normalised* weights after any dropped strategies — they may differ slightly from the weights you passed in if a strategy had insufficient data.
- `component_returns` uses `0.0` for any NaN values (e.g. warmup periods). This is conservative — it assumes no position was held rather than interpolating returns.
- The `correlation` matrix is computed from the full backtest period. Rolling correlation would give a more dynamic picture of how relationships change over time.

---

## equal_weight — The 1/N Baseline

### What It Is
`equal_weight()` assigns the same fraction of capital to every strategy: `1 / N`. It's the simplest possible weighting scheme and, remarkably, one of the hardest to consistently beat out-of-sample.

### How It Works
The function takes a list of strategy names and returns a dict mapping each name to `1.0 / len(names)`. All weights sum to exactly 1.0.

### The Intuition
DeMiguel, Garlappi & Uppal (2009) studied 14 portfolio optimisation methods across 7 datasets and found that none consistently outperformed 1/N out-of-sample. The reason is estimation error — optimised weights require accurate estimates of expected returns and covariances, which are notoriously noisy. Equal weighting sidesteps the estimation problem entirely. Use it as your baseline: if a more sophisticated method can't beat 1/N on your backtest, it has no business being used in production.

### In the Code
```python
w = 1.0 / len(names)
return {name: w for name in names}
```

### Watch Out For
- Equal weight by strategy is not the same as equal risk. If one strategy has 20% annualised volatility and another has 5%, equal capital allocation means the high-vol strategy dominates portfolio risk. Use `vol_weight()` if equal risk contribution is the goal.
- Equal weight makes sense when strategies have roughly comparable volatility and Sharpe. If one strategy is dramatically better, you may want to over-weight it — but do so carefully and with OOS evidence.

---

## vol_weight — Inverse Volatility Weighting

### What It Is
`vol_weight()` allocates capital inversely proportional to each strategy's recent volatility, so that lower-volatility strategies receive larger allocations. The goal is for each strategy to contribute *equal risk* to the portfolio, not equal capital.

### How It Works
The function estimates each strategy's volatility from the last `lookback` bars of returns (default 60 trading days = ~3 months). It computes `inv_vol = 1 / volatility` for each strategy, then normalises so all weights sum to 1.0.

```
weight_i = (1/σᵢ) / Σ(1/σⱼ)
```

A strategy with 10% vol gets twice the weight of a strategy with 20% vol. A strategy with 5% vol gets four times the weight of one with 20% vol.

### The Intuition
If you hold a 30%-vol equity strategy and a 5%-vol fixed income strategy with equal capital, the equity strategy contributes 36× more variance to the portfolio than the fixed income strategy. Vol weighting normalises this — both strategies contribute equally to total portfolio risk, making the portfolio behaviour more predictable and the Sharpe more stable.

This is the industry standard for combining strategies in multi-asset CTA funds.

### In the Code
```python
tail    = component_returns.tail(lookback)
vols    = tail.std()
inv_vol = 1.0 / vols
total   = inv_vol.sum()
return {name: float(inv_vol[name] / total) for name in component_returns.columns}
```

### Watch Out For
- Vol estimates from 60 days are noisy. In a volatile period, weights will shift significantly. Consider using a longer lookback (120–252 days) for more stable weights.
- If any strategy has zero volatility (e.g. it was flat for the entire lookback period), the function falls back to equal weighting. Monitor for this edge case.
- Vol weighting does not account for correlations between strategies. Two low-vol strategies that are highly correlated can still concentrate risk. The Diversification Ratio (below) measures whether this is happening.

---

## run_portfolio_backtest — The Engine

### What It Is
`run_portfolio_backtest()` is the multi-strategy equivalent of `run_backtest()` from `backtest.py`. It takes a dict of signal series and price series (one per strategy), runs each strategy independently with realistic costs, then combines the net returns using the specified weights.

### How It Works
The function runs in five stages:

**Stage 1 — Per-strategy backtests.** For each strategy, signals are lagged by 1 bar (no look-ahead), multiplied by price returns to get gross P&L, and trading costs are deducted on position changes. This is identical to the single-strategy backtest in `backtest.py`.

**Stage 2 — Alignment.** All strategy return series are collected into a single DataFrame. Any date where *all* strategies have NaN is dropped; remaining NaNs (warmup periods) are filled with 0.0.

**Stage 3 — Weighted combination.** The weight Series is re-indexed to match the DataFrame columns and normalised (in case any strategies were dropped). Portfolio return = `(component_returns × weights).sum(axis=1)`.

**Stage 4 — Equity curve.** Computed as `(1 + portfolio_returns).cumprod()`.

**Stage 5 — Metrics.** Sharpe, Sortino, MDD, Calmar, annualised return/vol, correlation matrix, and diversification ratio are all computed and packaged into the result.

### The Intuition
The key insight is that each strategy runs independently — signals, prices, and costs are all strategy-specific. The portfolio is only formed at the returns level, by weighting and summing daily net returns. This means you can mix strategies trading completely different assets with no concern about cross-asset position management.

### In the Code
```python
# Per-strategy backtest (simplified)
pos         = sig.shift(1).fillna(0)          # 1-bar lag
net_ret     = pos * px.pct_change() - costs

# Weighted combination
w                 = weight_series / weight_series.sum()   # normalise
portfolio_returns = (component_df * w).sum(axis=1)
equity_curve      = (1 + portfolio_returns).cumprod()
```

### Watch Out For
- `signals_dict` and `prices_dict` must use the *same keys*. A mismatch raises a `ValueError` immediately.
- If strategies have different start dates (different warmup periods), the earliest common date is used for the portfolio — NaN returns before each strategy's warmup completes are filled with 0.0.
- The cost model applies independently per strategy — running 5 strategies doesn't mean you pay 5× the cost per bar; costs only accrue when each individual strategy changes its position.

---

## correlation_matrix — Strategy Correlation

### What It Is
`correlation_matrix()` computes the pairwise Pearson correlation between every pair of strategy return series. It's the most direct diagnostic for whether your strategies are genuinely diversified or secretly moving together.

### How It Works
The function calls pandas' `.corr()` on the component returns DataFrame, which computes pairwise Pearson correlation coefficients. The result is a symmetric N×N matrix where the diagonal is always 1.0 (each strategy is perfectly correlated with itself) and off-diagonal values range from -1 to +1.

### The Intuition
Correlation is the number that tells you how much diversification benefit you're actually getting. Two strategies with correlation 0.9 are almost redundant — you're essentially running the same strategy twice. Two strategies with correlation 0.0 provide maximum diversification. Negative correlation is the holy grail — one profits while the other loses, smoothing the combined equity curve.

The practical guide:
- |ρ| < 0.3 → good diversification candidate
- |ρ| < 0.6 → some overlap but still beneficial
- |ρ| ≥ 0.6 → strategies are too similar, reconsider

### Watch Out For
- Correlation is not static — it tends to spike toward 1.0 during market stress (the diversification you thought you had disappears exactly when you need it most). A full-period correlation matrix can mask dangerous regime-dependent correlation.
- Pearson correlation measures *linear* relationships. Two strategies can have low Pearson correlation but still blow up simultaneously during tail events (tail dependence). Consider looking at correlation during the worst 10% of market days specifically.
- With only 2–3 strategies, the correlation matrix is just a single number. Its value comes with larger portfolios (5+) where patterns of clustering become visible.

---

## diversification_ratio — Portfolio Efficiency

### What It Is
The Diversification Ratio (DR), introduced by Choueifaty & Coignard (2008), is a single number that summarises how efficiently your portfolio is diversified. It compares the weighted average of individual strategy volatilities to the actual portfolio volatility.

### How It Works
```
DR = Σ(wᵢ × σᵢ) / √(wᵀ Σ w)
```

- **Numerator** — the weighted average of individual strategy volatilities. This is what portfolio vol *would be* if all strategies were perfectly correlated.
- **Denominator** — the true portfolio volatility, accounting for covariances (how strategies move together).

Because correlation < 1 means strategies partially offset each other, the denominator is always ≤ the numerator, giving DR ≥ 1.0.

For N uncorrelated equal-vol strategies, DR = √N. With 4 uncorrelated strategies, DR = 2.0 — the portfolio is half as volatile as a naive bet on any single strategy.

### The Intuition
DR tells you: "How much volatility am I saving through diversification?" A DR of 1.5 means portfolio volatility is 33% lower than a simple weighted average of individual vols would suggest. A DR of 1.0 means you're getting zero diversification benefit — all strategies move together. Target DR > 1.3 for a well-diversified portfolio.

### In the Code
```python
w                = np.array([weights.get(c, 0.0) for c in cols])
vols             = component_returns.std().values
weighted_avg_vol = float(np.dot(w, vols))          # numerator
cov              = component_returns.cov().values
portfolio_var    = float(w @ cov @ w)              # denominator (squared)
return float(weighted_avg_vol / np.sqrt(portfolio_var))
```

### Watch Out For
- DR = 1.0 for a single strategy by definition — it requires at least two strategies to be meaningful.
- DR is computed from the full backtest covariance matrix. In live trading, use a rolling covariance estimate for more responsive weights.
- DR > √N is theoretically impossible for N uncorrelated strategies. If you see DR much higher than √N, check for data errors (e.g. near-zero vol strategies inflating the numerator).

---

## Concept Relationships

```
strategies/
    ├── EMACrossover.generate_signals()  ─┐
    ├── RSIMeanReversion.generate_signals() ─┤── signals_dict
    └── PriceBreakout.generate_signals()  ─┘
                          │
                          ▼
              run_portfolio_backtest(
                  signals_dict, prices_dict,
                  weights=vol_weight(...)
              )
                          │
                ┌─────────┼─────────┐
                │         │         │
         Per-strategy   Weighted   Portfolio
          backtests    combination  metrics
                │         │         │
                └─────────┴─────────┘
                          │
                          ▼
                  PortfolioResult
                          │
              ┌───────────┼───────────┐
              │           │           │
       correlation_    diversi-    risk metrics
          matrix      fication_   (Sharpe, MDD,
                        ratio       Calmar...)
                          │
                          ▼
                  stat_edge.py
              (is this edge real?)
```

**Weighting method comparison:**

| Method | Best For | Key Assumption | Key Risk |
|---|---|---|---|
| equal_weight | Default baseline, similar-vol strategies | All strategies equally valuable | High-vol strategies dominate risk |
| vol_weight | Mixed-vol strategies, institutional use | Lower vol = more reliable | Ignores correlations between strategies |

---

## Glossary

| Term | Definition |
|---|---|
| Portfolio backtest | Running multiple strategies together and measuring their combined performance |
| Diversification | Combining assets/strategies to reduce portfolio volatility below the average of individual volatilities |
| Equal weight (1/N) | Allocating the same fraction of capital to every strategy |
| Inverse volatility weighting | Allocating capital proportionally to 1/σ so each strategy contributes equal risk |
| Correlation (ρ) | Measure of how similarly two strategies move — ranges from -1 to +1 |
| Covariance matrix (Σ) | Matrix of pairwise covariances — captures both individual volatilities and cross-strategy relationships |
| Diversification Ratio (DR) | Weighted avg vol / portfolio vol — measures how much diversification is reducing portfolio risk |
| Component returns | The individual daily return series for each strategy within the portfolio |
| Weighted sum | Portfolio return = Σ(wᵢ × returnᵢ) — the fundamental combining operation |
| DeMiguel et al. (2009) | Paper showing 1/N outperforms most portfolio optimisation methods out-of-sample |
| Choueifaty & Coignard (2008) | Paper introducing the Diversification Ratio as a portfolio construction objective |
| Tail dependence | Tendency for strategies to become highly correlated during market stress, undermining diversification |

---

## Further Reading

- **"Efficiently Inefficient"** — Lasse Heje Pedersen. Chapters 13–15 cover multi-strategy portfolio construction, risk parity, and the theory behind volatility targeting.
- **DeMiguel, Garlappi & Uppal (2009)** — "Optimal Versus Naive Diversification". The paper proving 1/N outperforms optimised portfolios — freely available on SSRN.
- **Choueifaty & Coignard (2008)** — "Towards Maximum Diversification". The original Diversification Ratio paper, defining DR and the Maximum Diversification Portfolio.
- **"Quantitative Portfolio Management"** — Michael Isichenko. Practical guide to multi-strategy portfolio construction from a practitioner perspective.
