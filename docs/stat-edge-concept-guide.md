# Statistical Edge Testing — Concept Guide
*Source: `framework/stat_edge.py`*
*Depth: Balanced*
*Generated: 2026-03-07*

---

## The Central Problem: Edge vs Luck

### What It Is
`stat_edge.py` addresses the most important question in systematic trading: "Is this backtest result genuine edge, or did I just get lucky?" Every tool in this module is designed to quantify the probability that an observed performance metric is real and repeatable, rather than a statistical accident.

### The Intuition
A strategy with a Sharpe ratio of 1.5 from one year of daily data sounds compelling — but with ~252 observations, even a strategy with zero true edge produces an observed Sharpe in the range of ±0.6 about 30% of the time. The observed Sharpe is an *estimate* of the true underlying Sharpe, subject to substantial noise. The four tools in this module measure that noise and give you honest uncertainty bounds around your results.

### Watch Out For
- Statistical significance does not equal economic significance. A strategy can have a highly significant Sharpe of 0.3 — statistically above zero, but not worth trading after costs and the prop firm cut.
- All four tools assume you're testing a *pre-specified* strategy. If you've run 50 strategies and are now testing the best one, any significance result is inflated. The multiple testing problem (data snooping) is the most common source of overfit backtests.
- These tools are most useful *after* a backtest passes the basic sanity checks — they're the final layer of validation, not a substitute for sound strategy design.

---

## Bootstrap Confidence Intervals

### What It Is
`bootstrap_ci()` computes a confidence interval for *any* performance metric by repeatedly resampling the return series with replacement and computing the metric on each resample. It answers: "Given the noise in my sample, what range of values could the true metric plausibly take?"

### How It Works
The function uses numpy's `default_rng` to draw `n_trials` random samples (each the same length as the original series) from the return array *with replacement*. The metric function is applied to each resample, building a distribution of 1,000 metric estimates. The confidence interval is taken from the percentiles of this distribution — for a 95% CI, the 2.5th and 97.5th percentiles.

The metric function (`metric_fn`) is a callable — you pass in any function that takes a return Series and returns a float. This makes `bootstrap_ci` generic: it works for Sharpe, Sortino, Calmar, win rate, or any custom metric.

### The Intuition
Bootstrapping asks: "If I re-ran history with the same underlying distribution but different luck, what range of results would I see?" A wide CI means your metric estimate is highly uncertain. A narrow CI means the result is stable. The key test is whether the CI lower bound is comfortably above zero — if it is, you have genuine positive edge even in unlucky scenarios.

### In the Code
```python
for _ in range(n_trials):
    idx    = rng.integers(0, n, size=n)        # random indices with replacement
    sample = float(metric_fn(pd.Series(arr[idx])))
    samples.append(sample)

lower = float(np.percentile(samples, 100 * alpha / 2))
upper = float(np.percentile(samples, 100 * (1 - alpha / 2)))
```

### Watch Out For
- **Bootstrap assumes i.i.d. returns** — independent and identically distributed. Real returns have serial correlation (momentum effects, volatility clustering). Standard bootstrapping breaks this temporal structure by resampling individual days. Block bootstrapping (sampling consecutive chunks) is more appropriate but not implemented here.
- With `n_trials=1000`, results are fast but slightly noisy. Use `n_trials=5000` for publication-quality CIs.
- Always set `random_state` for reproducibility — the same return series should produce the same CI every time during development.

---

## Probabilistic Sharpe Ratio (PSR)

### What It Is
The Probabilistic Sharpe Ratio, introduced by Bailey & López de Prado (2012), is the probability that the *true* underlying Sharpe ratio exceeds a benchmark, given the observed returns. It adjusts for sample size, return skewness, and fat tails — all of which inflate or deflate the naive Sharpe estimate.

### How It Works
The PSR is built on the insight that the observed Sharpe ratio is a noisy estimator of the true Sharpe. The variance of this estimator depends on three factors:

1. **Sample size (T)** — more observations → lower variance → more reliable estimate
2. **Skewness (γ₃)** — negative skew (common in strategies that sell options or hold large positions) makes the Sharpe harder to sustain and inflates estimation variance
3. **Excess kurtosis (γ₄)** — fat tails (more extreme days than a normal distribution) add further noise to the estimate

The formula computes the variance of the Sharpe estimator (`sr_variance`), then converts the observed Sharpe into a z-score relative to the benchmark, and passes it through the normal CDF (`norm.cdf`) to get a probability.

```
σ²(SR) = [1 + 0.5×SR² - γ₃×SR + (γ₄/4)×SR²] / (T-1)
PSR    = Φ[(SR_observed - SR_benchmark) / √σ²(SR)]
```

### The Intuition
PSR > 0.95 means: "I am 95% confident that the true Sharpe exceeds the benchmark." It's a single number that answers the question a prop firm is really asking when they look at your backtest. A Sharpe of 2.0 from 6 months of data is far less convincing than a Sharpe of 1.5 from 3 years — PSR captures this distinction automatically.

### In the Code
```python
sr_variance = (
    1
    + 0.5   * sr_hat**2
    - skew  * sr_hat
    + (excess_kurt / 4) * sr_hat**2
) / max(T - 1, 1)

z = (sr_hat - sr_bench_d) / np.sqrt(sr_variance)
return float(norm.cdf(z))
```

### Watch Out For
- PSR uses the **daily** (un-annualised) Sharpe for the formula. The annualised benchmark is converted to daily via `sr_benchmark / √252` before the calculation — don't pass daily and annualised values inconsistently.
- PSR assumes the return distribution is characterised by its first four moments (mean, std, skew, kurtosis). If your strategy has more exotic tail behaviour, PSR may still underestimate uncertainty.
- A PSR of 0.95 is not a guarantee — it's a probability. You will occasionally see PSR > 0.95 for strategies with zero true edge, by chance. PSR reduces the false positive rate; it doesn't eliminate it.

---

## Minimum Track Record Length (MinTRL)

### What It Is
MinTRL answers the practical question: "How many months of live trading do I need before a prop firm or investor should believe my claimed Sharpe is genuine?" It's the inverse of PSR — instead of asking "what's the probability given this data?", it asks "how much data do I need to achieve a target probability?"

### How It Works
The formula derives from the PSR framework, solving for the number of observations `T` needed to achieve the target confidence level:

```
MinTRL (days) = 1 + σ²_factor × [Φ⁻¹(confidence) / (SR_daily - SR*_daily)]²
```

Where `σ²_factor` is the same variance multiplier from PSR (adjusted for skew and kurtosis), and `Φ⁻¹` is the inverse normal CDF. The result in trading days is divided by 21 to convert to months.

The typical results are sobering:
- Sharpe 2.0 → ~8 months needed
- Sharpe 1.5 → ~14 months needed
- Sharpe 1.0 → ~33 months needed (over 2.5 years)
- Sharpe 0.5 → ~130 months — essentially impossible to prove

### The Intuition
MinTRL explains why prop firms target Sharpe > 1.5. A Sharpe of 1.0 takes over two years of live trading to prove statistically — far longer than any prop firm challenge. A Sharpe of 2.0 can be proven in under a year. The bar isn't arbitrary; it's set by the mathematics of statistical inference.

### In the Code
```python
var_factor = (
    1
    + 0.5 * sr_d**2
    - skew * sr_d
    + (excess_kurt / 4) * sr_d**2
)
z        = norm.ppf(confidence)          # inverse normal CDF
min_days = 1 + var_factor * (z / (sr_d - sr_b_d)) ** 2
return float(min_days / 21)              # convert to months
```

### Watch Out For
- MinTRL assumes no parameter changes during the live period. If you adjust the strategy mid-track, the clock effectively resets.
- Negative skew *increases* MinTRL — a strategy that has occasional large losses requires more data to prove its edge because the Sharpe estimate is noisier. Strategies with positive skew require less time.
- MinTRL returns `float("inf")` if the claimed Sharpe is at or below the benchmark — you can never prove an edge that doesn't exceed the hurdle.

---

## Permutation Test

### What It Is
The permutation test is a non-parametric significance test that destroys the temporal structure of a return series to create a null distribution. It's best suited for metrics that depend on the *order* of returns — particularly Calmar ratio and maximum drawdown — where bootstrapping gives misleading results.

### How It Works
1. Compute the actual metric on the original return series
2. Shuffle the returns randomly `n_trials` times, completely destroying any sequential patterns
3. Compute the metric on each shuffled version — building a null distribution of "what the metric would look like if order didn't matter"
4. `p_value` = fraction of shuffled results that are greater than or equal to the actual result

A low p-value (< 0.05) means the actual result is unlikely to occur by chance under the null hypothesis that order doesn't matter — i.e., the strategy's temporal structure is genuinely contributing to performance.

### The Intuition
The permutation test asks: "Does the *sequence* of my returns matter?" A real Calmar ratio benefits from the strategy avoiding large consecutive losses — something a random shuffle will typically fail to do. If your actual Calmar beats 95%+ of shuffled versions, you have evidence that the strategy's timing is genuinely adding value, not just its average return.

**Important:** Sharpe ratio is *not* sequence-dependent — shuffling returns leaves the mean and standard deviation unchanged, and therefore leaves Sharpe unchanged. Use PSR for Sharpe significance; use the permutation test for Calmar and drawdown metrics.

### In the Code
```python
for _ in range(n_trials):
    shuffled = arr.copy()
    rng.shuffle(shuffled)                  # destroys temporal structure
    null.append(float(metric_fn(pd.Series(shuffled, index=returns.index))))

p_value = float((null >= actual).mean())  # fraction of shuffles that beat actual
```

### Watch Out For
- The permutation test for Calmar/MDD has low power with fewer than ~100 trading days — you need enough data for the null distribution to be meaningful.
- `p_value < 0.05` is significant at the 5% level; `p_value < 0.01` is significant at the 1% level. Both flags are returned in the output dict.
- The null hypothesis being tested is "order doesn't matter" — rejection means order *does* matter, which is evidence of genuine strategy timing ability. It doesn't tell you *why* order matters (could be momentum, regime detection, etc.).

---

## edge_summary — Full Report

### What It Is
`edge_summary()` runs all four major analyses in one call and returns a consolidated dict with Sharpe, PSR, bootstrap CI bounds, MinTRL, and a plain-English interpretation. It's the fastest way to assess whether a backtest result is trustworthy before presenting it.

### How It Works
It sequentially calls `sharpe_fn()`, `probabilistic_sharpe()`, `min_track_record()`, and `bootstrap_ci()`, passing consistent parameters throughout. The `Interpretation` field maps PSR to four plain-English labels:

- PSR > 0.95 → "Strong edge"
- PSR > 0.80 → "Moderate edge"
- PSR > 0.60 → "Weak edge"
- PSR ≤ 0.60 → "No evidence of edge"

### The Intuition
Run `edge_summary()` as the final step before presenting any strategy. If the interpretation says "Strong edge" with a CI lower bound above zero and a MinTRL under 12 months, you have a genuinely convincing result. If it says "No evidence of edge" with a CI straddling zero, no amount of Sharpe polishing will fix the underlying problem.

### Watch Out For
- `edge_summary()` uses `random_state=42` by default for reproducibility. Always use a fixed seed when including results in documentation or presentations.
- The permutation test is *not* included in `edge_summary()` — run it separately for Calmar/MDD analysis: `permutation_test(returns, lambda r: calmar(r))`.
- All inputs must be daily returns (not log returns, not monthly). Mixing return frequencies will produce incorrect PSR and MinTRL values.

---

## Concept Relationships

```
backtest.py → net_returns (daily)
                    │
                    ├──► bootstrap_ci(returns, metric_fn)
                    │         └── CI bounds on any metric
                    │
                    ├──► probabilistic_sharpe(returns)
                    │         └── P(true SR > benchmark)
                    │
                    ├──► min_track_record(sr, skew, kurt)
                    │         └── months needed to prove edge
                    │
                    └──► permutation_test(returns, metric_fn)
                              └── p-value for sequence-dependent metrics
                    │
                    ▼
             edge_summary()
                    │
                    ▼
        "Strong edge / Moderate edge /
         Weak edge / No evidence of edge"
```

The stat_edge module sits at the end of the pipeline — it takes the output of `backtest.py` and `risk.py` and answers whether those results are statistically credible, not just numerically large.

---

## Glossary

| Term | Definition |
|---|---|
| Bootstrap | Resampling a dataset with replacement to estimate the distribution of a statistic |
| Confidence interval (CI) | Range of values within which the true parameter likely falls at a given probability |
| Probabilistic Sharpe Ratio (PSR) | Probability that the true Sharpe exceeds a benchmark, adjusting for sample size and distribution shape |
| Minimum Track Record Length (MinTRL) | Months of live trading needed to statistically confirm a claimed Sharpe ratio |
| Permutation test | Non-parametric test that shuffles data to build a null distribution |
| p-value | Probability of observing a result as extreme as the actual result under the null hypothesis |
| Null hypothesis | The default assumption being tested (e.g. "order doesn't matter") |
| Skewness (γ₃) | Asymmetry of the return distribution — negative skew = occasional large losses |
| Excess kurtosis (γ₄) | Fat-tailedness — excess kurtosis > 0 means more extreme days than a normal distribution |
| i.i.d. | Independent and identically distributed — the assumption that each observation is drawn from the same distribution with no serial dependence |
| Data snooping | Running many strategies and testing only the best one — inflates false positive rate |
| Multiple testing | The statistical problem that arises when testing many hypotheses simultaneously |
| Norm.cdf / Φ | Cumulative distribution function of the standard normal — converts a z-score to a probability |

---

## Further Reading

- **Bailey & López de Prado (2012)** — "The Sharpe Ratio Efficient Frontier". The original PSR and MinTRL paper — freely available on SSRN.
- **"Advances in Financial Machine Learning"** — Marcos López de Prado. Chapters 8–10 cover backtest overfitting, the deflated Sharpe ratio, and multiple testing frameworks — essential reading for serious systematic traders.
- **"Evidence-Based Technical Analysis"** — David Aronson. Chapters 6–8 provide an accessible introduction to permutation testing and bootstrap methods for trading strategy evaluation.
