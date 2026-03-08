"""
scripts/backtest_pipeline.py
Backtest pipeline with file-first reporting.

Default behavior:
    - Run pipeline
    - Save full report to logs/backtest_pipeline_report.txt
    - Print only a short completion message

Keyword modes:
    python scripts/backtest_pipeline.py terminal
    python scripts/backtest_pipeline.py console
    python scripts/backtest_pipeline.py stdout
These stream the full report to terminal while still writing the file.
"""

import argparse
import os
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from framework.backtest import summary_table
from framework.data import clean, fetch, train_test_split
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
from runner.runner_config import RunnerConfig


RUNNER_CONFIG_PATH = "runner_config.yaml"
DEFAULT_TICKERS = ["SPY", "QQQ", "IWM", "GLD", "TLT"]
REPORT_PATH = Path("logs/backtest_pipeline_report.txt")

START = "2010-01-01"
TRAIN_PCT = 0.80
SLIPPAGE = 0.0005
COMMISSION = 0.001
RISK_FREE = 0.05

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

DISPLAY_COLS = [
    "Sharpe Ratio",
    "Sortino Ratio",
    "Max Drawdown",
    "Calmar Ratio",
    "Trades",
    "Final Equity",
]


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="python scripts/backtest_pipeline.py")
    p.add_argument(
        "mode",
        nargs="?",
        default="file",
        choices=["file", "terminal", "console", "stdout"],
        help="Output mode: file (default) or terminal/console/stdout.",
    )
    p.add_argument(
        "--output",
        default=str(REPORT_PATH),
        help="Report file path (default: logs/backtest_pipeline_report.txt).",
    )
    return p.parse_args()


def _resolve_tickers() -> list[str]:
    try:
        cfg = RunnerConfig.from_yaml(RUNNER_CONFIG_PATH)
        return cfg.symbols
    except Exception:
        return DEFAULT_TICKERS


def _emit(lines: list[str], text: str, stream: bool) -> None:
    lines.append(text)
    if stream:
        print(text)


def run_pipeline(stream_to_terminal: bool, output_path: Path) -> None:
    all_results: dict[str, dict[str, pd.Series]] = {}
    report_lines: list[str] = []
    tickers = _resolve_tickers()

    for ticker in tickers:
        _emit(report_lines, "\n" + ("-" * 64), stream_to_terminal)
        _emit(report_lines, f"  {ticker}", stream_to_terminal)
        _emit(report_lines, "-" * 64, stream_to_terminal)

        try:
            df = clean(fetch(ticker, START))
        except Exception as exc:
            _emit(report_lines, f"  [SKIP] Could not fetch {ticker}: {exc}", stream_to_terminal)
            continue

        _, test_df = train_test_split(df, TRAIN_PCT)
        split_bar = int(len(df) * TRAIN_PCT)
        train_end = df.index[split_bar - 1].date()
        test_start = test_df.index[0].date()
        test_end = test_df.index[-1].date()

        _emit(
            report_lines,
            f"  In-sample:  {df.index[0].date()} -> {train_end}  ({split_bar} bars)",
            stream_to_terminal,
        )
        _emit(
            report_lines,
            f"  OOS test:   {test_start} -> {test_end}  ({len(test_df)} bars)\n",
            stream_to_terminal,
        )

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
                _emit(report_lines, f"  [ERROR] {strategy.name}: {exc}", stream_to_terminal)

        if not ticker_results:
            _emit(report_lines, "  No results for this ticker.", stream_to_terminal)
            continue

        all_results[ticker] = ticker_results
        table = pd.DataFrame(ticker_results).T
        cols = [c for c in DISPLAY_COLS if c in table.columns]
        _emit(
            report_lines,
            table[cols].to_string(float_format="{:.3f}".format),
            stream_to_terminal,
        )

    if not all_results:
        _emit(report_lines, "\nNo results to summarise.", stream_to_terminal)
    else:
        _emit(report_lines, "\n\n" + ("=" * 64), stream_to_terminal)
        _emit(report_lines, "  SUMMARY - Mean OOS Sharpe Ratio across all tickers", stream_to_terminal)
        _emit(report_lines, "=" * 64, stream_to_terminal)

        mean_sharpe: dict[str, float] = {}
        for strategy in STRATEGIES:
            name = strategy.name
            sharpes = [
                all_results[t][name]["Sharpe Ratio"]
                for t in all_results
                if name in all_results[t]
            ]
            if sharpes:
                mean_sharpe[name] = sum(sharpes) / len(sharpes)

        ranked = pd.Series(mean_sharpe).sort_values(ascending=False)
        _emit(report_lines, ranked.to_string(float_format="{:.3f}".format), stream_to_terminal)
        _emit(report_lines, "", stream_to_terminal)

        _emit(report_lines, "\n" + ("=" * 64), stream_to_terminal)
        _emit(report_lines, "  FULL MATRIX - OOS Sharpe Ratio by Strategy x Ticker", stream_to_terminal)
        _emit(report_lines, "=" * 64, stream_to_terminal)

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
        _emit(report_lines, matrix.to_string(float_format="{:.3f}".format), stream_to_terminal)
        _emit(report_lines, "", stream_to_terminal)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    print(f"Saved report to: {output_path}")


if __name__ == "__main__":
    args = _parse_args()
    stream = args.mode in {"terminal", "console", "stdout"}
    run_pipeline(stream_to_terminal=stream, output_path=Path(args.output))
