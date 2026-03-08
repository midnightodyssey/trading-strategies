"""
scripts/backtest_pipeline.py
─────────────────────────────────────────────────────────────────────────────
Multi-strategy, multi-asset backtest pipeline.

Fetches historical data, splits into in-sample / out-of-sample, runs every
strategy on the OOS test set, and prints a ranked comparison table.

Usage:
    python scripts/backtest_pipeline.py

Configuration:
    Edit the TICKERS, START, TRAIN_PCT, SLIPPAGE, and STRATEGIES sections
    below. No other changes needed.

Output:
    Per-ticker table  — Sharpe, Sortino, Max Drawdown, Calmar, Trades,
                        Final Equity for every strategy
    Summary table     — strategies ranked by mean OOS Sharpe across all tickers
"""

import os
import sys

import pandas as pd

# ── allow running from any working directory ──────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from framework.data import fetch, clean, train_test_split
from framework.backtest import summary_table
from framework.strategies import (
    ATRBreakout,
    BollingerMeanReversion,
    EMACrossover,
    MACDCrossover,
    PriceBreakout,
    RSIMeanReversion,
    SMACrossover,
    TrendFilteredRSI,
)


# ─── CONFIGURATION ────────────────────────────────────────────────────────────

# Asset universe — any Yahoo Finance tickers work here
TICKERS = ["SPY", "QQQ", "IWM", "GLD", "TLT"]

# History start date — more data = more stable OOS metrics
START = "2010-01-01"

# Proportion allocated to in-sample training (OOS = 1 - TRAIN_PCT)
TRAIN_PCT = 0.80

# Cost model — realistic for US equities/ETFs via IB
SLIPPAGE   = 0.0005   # 5 bps per side
COMMISSION = 0.001    # 10 bps round-trip
RISK_FREE  = 0.05     # 5% annual risk-free rate

# Strategies to compare — add, remove, or re-parameterise freely
STRATEGIES = [
    EMACrossover(),
    SMACrossover(),
    MACDCrossover(),
    PriceBreakout(),
    ATRBreakout(),
    RSIMeanReversion(),
    BollingerMeanReversion(),
    TrendFilteredRSI(),
]

# Metrics to show in the per-ticker table (must match risk_summary() keys
# plus "Trades" and "Final Equity" added by summary_table())
DISPLAY_COLS = [
    "Sharpe Ratio",
    "Sortino Ratio",
    "Max Drawdown",
    "Calmar Ratio",
    "Trades",
    "Final Equity",
]


# ─── PIPELINE ─────────────────────────────────────────────────────────────────

def run_pipeline() -> None:
    """
    Main pipeline loop: fetch → clean → split → backtest → report.

    Returns nothing — all output is printed to stdout.
    """
    all_results: dict[str, dict[str, pd.Series]] = {}

    for ticker in TICKERS:
        print(f"\n{'─' * 64}")
        print(f"  {ticker}")
        print(f"{'─' * 64}")

        # ── Fetch and clean ───────────────────────────────────────────────────
        try:
            df = clean(fetch(ticker, START))
        except Exception as exc:
            print(f"  [SKIP] Could not fetch {ticker}: {exc}")
            continue

        # ── Time-based split (never random — no look-ahead) ───────────────────
        _, test_df = train_test_split(df, TRAIN_PCT)

        split_bar = int(len(df) * TRAIN_PCT)
        train_end = df.index[split_bar - 1].date()
        test_start = test_df.index[0].date()
        test_end   = test_df.index[-1].date()

        print(f"  In-sample:  {df.index[0].date()} → {train_end}  ({split_bar} bars)")
        print(f"  OOS test:   {test_start} → {test_end}  ({len(test_df)} bars)\n")

        # ── Run every strategy on the OOS test set ────────────────────────────
        ticker_results: dict[str, pd.Series] = {}

        for strategy in STRATEGIES:
            try:
                result = strategy.run(
                    test_df,
                    slippage=SLIPPAGE,
                    commission=COMMISSION,
                    risk_free_rate=RISK_FREE,
                )
                ticker_results[strategy.name] = summary_table(result)
            except Exception as exc:
                print(f"  [ERROR] {strategy.name}: {exc}")

        if not ticker_results:
            print("  No results for this ticker.")
            continue

        all_results[ticker] = ticker_results

        # ── Per-ticker table ──────────────────────────────────────────────────
        table = pd.DataFrame(ticker_results).T
        cols  = [c for c in DISPLAY_COLS if c in table.columns]
        print(table[cols].to_string(float_format="{:.3f}".format))

    # ─── CROSS-ASSET SUMMARY ──────────────────────────────────────────────────
    if not all_results:
        print("\nNo results to summarise.")
        return

    print(f"\n\n{'═' * 64}")
    print("  SUMMARY — Mean OOS Sharpe Ratio across all tickers")
    print(f"{'═' * 64}")

    mean_sharpe: dict[str, float] = {}
    for strategy in STRATEGIES:
        name    = strategy.name
        sharpes = [
            all_results[t][name]["Sharpe Ratio"]
            for t in all_results
            if name in all_results[t]
        ]
        if sharpes:
            mean_sharpe[name] = sum(sharpes) / len(sharpes)

    ranked = pd.Series(mean_sharpe).sort_values(ascending=False)
    print(ranked.to_string(float_format="{:.3f}".format))
    print()

    # ─── FULL CROSS-ASSET MATRIX ──────────────────────────────────────────────
    print(f"\n{'═' * 64}")
    print("  FULL MATRIX — OOS Sharpe Ratio by Strategy × Ticker")
    print(f"{'═' * 64}")

    matrix_data: dict[str, dict[str, float]] = {}
    for strategy in STRATEGIES:
        name = strategy.name
        row: dict[str, float] = {}
        for ticker in all_results:
            if name in all_results[ticker]:
                row[ticker] = all_results[ticker][name]["Sharpe Ratio"]
            else:
                row[ticker] = float("nan")
        matrix_data[name] = row

    matrix = pd.DataFrame(matrix_data).T
    matrix["Mean"] = matrix.mean(axis=1)
    matrix = matrix.sort_values("Mean", ascending=False)
    print(matrix.to_string(float_format="{:.3f}".format))
    print()


if __name__ == "__main__":
    run_pipeline()
