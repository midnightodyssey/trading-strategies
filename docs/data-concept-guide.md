# Data Pipeline â€” Concept Guide

*Category: Framework*
*Depth: Balanced*
*Generated: 2026-03-07*

---

## fetch â€” Data Acquisition

### What It Is
`fetch()` is the entry point for all market data in the framework. It downloads OHLCV (Open, High, Low, Close, Volume) price data from Yahoo Finance for a single ticker and returns it as a clean, date-indexed pandas DataFrame.

### How It Works
Under the hood it calls `yf.download()` with three important flags:

- `auto_adjust=True` â€” automatically adjusts historical prices for stock splits and dividend payments, so a 2-for-1 split doesn't create a fake 50% price drop in your data
- `progress=False` â€” suppresses the download progress bar (noise in scripts/notebooks)
- The result is validated immediately: if no data comes back, a descriptive `ValueError` is raised rather than silently returning an empty DataFrame

There's also a defensive column-flattening step: newer versions of yfinance sometimes return a `MultiIndex` column structure `(field, ticker)` even for single-ticker downloads. The code detects this and flattens it back to simple column names before returning.

### The Intuition
`fetch()` is the only place in the framework that talks to the outside world. Everything downstream assumes clean, adjusted, single-level column OHLCV data â€” so getting this right matters. For live trading, this function would be swapped for a broker API call, but the rest of the framework wouldn't change.

### In the Code
```python
raw = yf.download(ticker, start=start, end=end,
                  interval=interval, auto_adjust=True, progress=False)

if isinstance(raw.columns, pd.MultiIndex):
    raw.columns = [col[0] for col in raw.columns]

df = raw[["Open", "High", "Low", "Close", "Volume"]].copy()
```

### Watch Out For
- Yahoo Finance data quality varies by asset and age. Crypto and some international equities have gaps or errors â€” always inspect raw data before trusting it.
- `auto_adjust=True` adjusts for dividends *and* splits, which is correct for return calculations but means prices don't match what you'd have seen on a live chart at the time.
- Intraday intervals (e.g. `"1h"`, `"15m"`) are only available for recent history on Yahoo Finance â€” typically 60 days for hourly and 7 days for minute data.

---

## clean â€” Data Cleaning

### What It Is
`clean()` is a defensive post-processing step that should always be called immediately after `fetch()`. It handles the four most common data quality issues in raw market data: missing close prices, sporadic NaN gaps, duplicate dates, and out-of-order rows.

### How It Works
The function applies four operations in sequence:

1. **Drop rows with missing Close.** A bar with no close price is unusable â€” it's dropped entirely with `dropna(subset=["Close"])`.
2. **Forward-fill remaining NaNs.** Occasional gaps in Volume or other fields are filled using the prior day's value (`ffill()`). This preserves the calendar without introducing artificial zeroes.
3. **Remove duplicates.** Some data sources emit duplicate timestamps (e.g. two entries for the same date). `~df.index.duplicated(keep="last")` retains only the last occurrence.
4. **Sort ascending.** Ensures the index runs oldest-to-newest, which is required for all rolling window calculations downstream.

### The Intuition
Rolling windows, `pct_change()`, and `shift()` all silently misbehave on irregular or duplicated time series. Running `clean()` gives you a guarantee that the data is well-formed before any calculation touches it â€” like validating inputs at the door.

### In the Code
```python
df = df.dropna(subset=["Close"])
df = df.ffill()
df = df[~df.index.duplicated(keep="last")]
df = df.sort_index()
```

### Watch Out For
- Forward-filling is appropriate for occasional gaps but not for sustained missing periods. If an asset was halted or delisted for weeks, `ffill()` will silently create a flat line of stale prices â€” check for unusually long runs of identical closes.
- `keep="last"` for duplicates assumes the later entry is more accurate. For some data sources `keep="first"` may be more appropriate.
- `clean()` operates on a copy (`df.copy()`) to avoid mutating the input â€” this is intentional and correct.

---

## add_returns â€” Return Columns

### What It Is
`add_returns()` appends two return columns to the DataFrame: simple percentage returns and log returns. Both measure daily price change, but they have different mathematical properties that make each suited to different purposes.

### How It Works
- **Simple returns** (`pct_change()`): `(P_t - P_{t-1}) / P_{t-1}`. This is the actual P&L percentage â€” if you put Â£100 in and made 1.2%, you have Â£101.20. Used for all P&L calculations and risk metrics.
- **Log returns** (`log(P_t / P_{t-1})`): The natural logarithm of the price ratio. These are *additive* across time (you can sum daily log returns to get the period log return), more symmetric around zero, and closer to normally distributed than simple returns. Used for statistical modelling and some ML features.

### The Intuition
Simple returns answer "how much money did I make?" Log returns answer "what does the statistical distribution of price changes look like?" For backtesting, use simple returns. For building models or running regressions, use log returns.

### Watch Out For
- Both return types produce `NaN` for the first bar (no prior close to compare against). This propagates into any indicator or model that uses them â€” plan for it.
- Simple and log returns are approximately equal for small moves (< 2%), but diverge meaningfully for large moves. A 10% simple return = 9.53% log return. Never mix the two in the same calculation.

---

## add_features â€” Feature Engineering

### What It Is
`add_features()` extends the raw OHLCV data with a standard set of normalised, dimensionless features that most strategies and models can use directly. It calls `add_returns()` internally and adds four more derived columns.

### How It Works
Each feature is designed to be comparable across assets and time:

- **`range_pct`** â€” `(High - Low) / Close`: today's intraday price range as a fraction of the close. A value of 0.02 means the high-to-low range was 2% of the closing price. High values signal volatile sessions; low values signal quiet ones.

- **`gap_pct`** â€” `(Open - prev_Close) / prev_Close`: the overnight gap expressed as a fraction of the prior close. Positive = gapped up, negative = gapped down. Captures news/earnings reactions that occurred outside trading hours.

- **`volume_ma20`** â€” 20-day rolling mean of Volume. Establishes a baseline of "normal" volume for this asset. Used only as an intermediate calculation for `rel_volume`.

- **`rel_volume`** â€” `Volume / volume_ma20`: today's volume relative to its 20-day average. A value of 2.5 means volume was 2.5Ã— normal. Values above 2 often indicate institutional activity â€” breakouts with high `rel_volume` tend to be more sustained than those on average volume.

### The Intuition
Raw prices and volumes are not directly comparable across assets or time (a Â£50 stock and a Â£500 stock have very different raw volume numbers). Normalising everything into ratios and percentages makes features universally applicable â€” the same signal thresholds work for SPY, AAPL, and BTC-USD.

### Watch Out For
- `volume_ma20` produces `NaN` for the first 20 bars, and `rel_volume` inherits that NaN. Any strategy using `rel_volume` must account for the 20-bar warmup period.
- `gap_pct` uses `Close.shift(1)` which creates a 1-bar dependency â€” the first bar will always be `NaN`.
- All features are computed without knowledge of future data. There is no look-ahead bias here, but be careful when adding your own features â€” always use `.shift()` if referencing same-bar data that wouldn't be known at open.

---

## train_test_split â€” Time-Series Splitting

### What It Is
`train_test_split()` divides the full DataFrame into a training set (earlier data) and a test set (later data) by position, never randomly. It enforces the correct way to split time-series data for model evaluation.

### How It Works
Simple index arithmetic: `split_idx = int(n * train_pct)`. Everything before `split_idx` is train, everything from `split_idx` onwards is test. Both halves are returned as independent copies.

### The Intuition
Random splitting â€” which is correct for i.i.d. datasets like image classification â€” is catastrophically wrong for time-series. If you randomly assign a date from 2023 to training and the day before it to testing, your model has "seen the future." Always split by time: train on the past, test on the future.

### In the Code
```python
n         = len(df)
split_idx = int(n * train_pct)
train     = df.iloc[:split_idx].copy()
test      = df.iloc[split_idx:].copy()
return train, test
```

### Watch Out For
- With `train_pct=0.8` on 5 years of daily data (~1260 bars), the test set is only ~252 bars (1 year). That's a thin evaluation window â€” consider whether it covers enough market regimes.
- This function creates a single train/test split. For more robust evaluation, use `walk_forward()` in `backtest.py` which creates multiple rolling OOS windows.
- Both halves are deep copies â€” modifying `train` will not affect `test` or the original DataFrame.

---

## fetch_multiple â€” Multi-Asset Pipeline

### What It Is
`fetch_multiple()` is a convenience wrapper that runs the full `fetch â†’ clean â†’ add_features` pipeline for a list of tickers and returns a dictionary mapping each ticker to its processed DataFrame. Failed tickers are skipped gracefully rather than crashing the whole download.

### How It Works
It iterates over the ticker list, calling `fetch()`, `clean()`, and `add_features()` for each. If any step raises an exception (bad ticker, no data in range, network error), a warning is printed and execution continues to the next ticker. Successful results are stored in a dict keyed by ticker symbol.

### The Intuition
In practice, you're rarely backtesting a single asset. `fetch_multiple()` handles the boilerplate of downloading and processing a whole universe in one call, while being tolerant of the messy reality that some tickers will fail.

### In the Code
```python
for ticker in tickers:
    try:
        df = fetch(ticker, start, end, interval)
        df = clean(df)
        df = add_features(df)
        result[ticker] = df
    except Exception as e:
        print(f"Warning: skipping {ticker} â€” {e}")
return result
```

### Watch Out For
- The broad `except Exception` catches everything â€” including genuine bugs in your code, not just data issues. If development results are unexpected, narrow the exception handling temporarily to surface errors properly.
- Returned DataFrames may not all have the same date range if tickers were listed at different times or have different trading histories. Align indices explicitly before any cross-asset calculations.
- For large universes (100+ tickers), this runs sequentially and can be slow. Consider parallelising with `concurrent.futures.ThreadPoolExecutor` for production use.

---

## Concept Relationships

```
fetch(ticker, start, end)
        â”‚
        â–¼
clean(df)                          â† Always run after fetch
        â”‚
        â–¼
add_features(df)                   â† Returns + normalised features
  â”œâ”€â”€ add_returns()        â†’ "returns", "log_returns"
  â”œâ”€â”€ range_pct            â†’ intraday volatility proxy
  â”œâ”€â”€ gap_pct              â†’ overnight gap signal
  â””â”€â”€ rel_volume           â†’ volume anomaly detector
        â”‚
        â–¼
train_test_split(df)               â† Time-ordered split only
  â”œâ”€â”€ train_df  â†’ strategy parameter fitting
  â””â”€â”€ test_df   â†’ honest OOS evaluation
        â”‚
        â–¼
backtest.py: run_backtest(signals, prices)
```

`fetch_multiple()` runs the entire left side of this pipeline for N tickers in one call, returning a dict of ready-to-use DataFrames.

---

## Glossary

| Term | Definition |
|---|---|
| OHLCV | Open, High, Low, Close, Volume â€” the five standard fields in a price bar |
| Auto-adjust | Correcting historical prices for splits and dividends so returns are accurate |
| Forward-fill (ffill) | Propagating the last known value forward to fill gaps |
| DatetimeIndex | pandas index type for time series â€” enables date-based slicing and alignment |
| Simple return | (P_t âˆ’ P_{t-1}) / P_{t-1} â€” actual percentage P&L |
| Log return | ln(P_t / P_{t-1}) â€” additive, more normally distributed, used in modelling |
| range_pct | (High âˆ’ Low) / Close â€” intraday range as a fraction of closing price |
| gap_pct | (Open âˆ’ prev_Close) / prev_Close â€” overnight gap as a fraction |
| rel_volume | Volume / 20-day average volume â€” today's volume vs normal |
| Train/test split | Dividing data into a fitting period and an evaluation period |
| Look-ahead bias | Accidentally using future data in a past calculation â€” invalidates results |
| Universe | The full set of assets under consideration for a strategy |

---

## Further Reading

- **yfinance documentation** â€” [github.com/ranaroussi/yfinance](https://github.com/ranaroussi/yfinance). The `auto_adjust` and `MultiIndex` column behaviour is version-dependent â€” worth reviewing release notes.
- **"Python for Finance"** â€” Yves Hilpisch. Chapters 8â€“10 cover market data acquisition, cleaning, and feature engineering with pandas in depth.
- **pandas time series documentation** â€” [pandas.pydata.org](https://pandas.pydata.org/docs/user_guide/timeseries.html). Essential reference for DatetimeIndex operations, resampling, and alignment.

