"""
scripts/backtest_pipeline.py
Backtest pipeline with file-first reporting plus structured artifacts.

Default behavior:
    - Run pipeline
    - Save text report to logs/backtest_pipeline_report.txt
    - Save structured artifacts to artifacts/backtests/<run_id>/
    - Print only a short completion message

Keyword modes:
    python scripts/backtest_pipeline.py terminal
    python scripts/backtest_pipeline.py console
    python scripts/backtest_pipeline.py stdout
These stream the full report to terminal while still writing files.
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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
ARTIFACTS_ROOT = Path("artifacts/backtests")

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
        help="Text report path (default: logs/backtest_pipeline_report.txt).",
    )
    p.add_argument(
        "--artifacts-dir",
        default=str(ARTIFACTS_ROOT),
        help="Artifacts root directory (default: artifacts/backtests).",
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


def _metric_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def _safe_number(value: Any) -> float | None:
    if pd.isna(value):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _write_artifacts(
    run_dir: Path,
    run_meta: dict[str, Any],
    records_df: pd.DataFrame,
    strategy_summary_df: pd.DataFrame,
    sharpe_matrix_df: pd.DataFrame,
) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)

    (run_dir / "run_meta.json").write_text(
        json.dumps(run_meta, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    records_df.to_csv(run_dir / "strategy_metrics_long.csv", index=False)
    strategy_summary_df.to_csv(run_dir / "strategy_summary.csv", index=False)
    sharpe_matrix_df.to_csv(run_dir / "sharpe_matrix.csv")

    payload = {
        "schema_version": 1,
        "run": run_meta,
        "records": records_df.to_dict(orient="records"),
    }
    (run_dir / "strategy_metrics_long.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def run_pipeline(stream_to_terminal: bool, output_path: Path, artifacts_root: Path) -> None:
    run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    generated_at_utc = datetime.now(timezone.utc).isoformat()

    all_results: dict[str, dict[str, pd.Series]] = {}
    metric_records: list[dict[str, Any]] = []
    report_lines: list[str] = []
    tickers = _resolve_tickers()

    _emit(report_lines, f"Run ID: {run_id}", stream_to_terminal)
    _emit(report_lines, f"Generated (UTC): {generated_at_utc}", stream_to_terminal)
    _emit(report_lines, f"Symbols: {len(tickers)}", stream_to_terminal)
    _emit(report_lines, f"Strategies: {len(STRATEGIES)}", stream_to_terminal)

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
                summary = summary_table(result)
                ticker_results[strategy.name] = summary

                record: dict[str, Any] = {
                    "run_id": run_id,
                    "generated_at_utc": generated_at_utc,
                    "symbol": ticker,
                    "strategy": strategy.name,
                    "start_date": str(test_start),
                    "end_date": str(test_end),
                    "oos_bars": int(len(test_df)),
                    "train_pct": float(TRAIN_PCT),
                    "slippage": float(SLIPPAGE),
                    "commission": float(COMMISSION),
                    "risk_free_rate": float(RISK_FREE),
                }
                for metric_name, metric_value in summary.items():
                    record[_metric_key(metric_name)] = _safe_number(metric_value)
                metric_records.append(record)
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

    records_df = pd.DataFrame(metric_records)

    if records_df.empty:
        _emit(report_lines, "\nNo results to summarise.", stream_to_terminal)
        strategy_summary_df = pd.DataFrame(columns=["strategy"])
        sharpe_matrix_df = pd.DataFrame()
    else:
        _emit(report_lines, "\n\n" + ("=" * 64), stream_to_terminal)
        _emit(report_lines, "  SUMMARY - Mean OOS Sharpe Ratio across all tickers", stream_to_terminal)
        _emit(report_lines, "=" * 64, stream_to_terminal)

        strategy_summary_df = (
            records_df.groupby("strategy", dropna=False)
            .agg(
                symbols_tested=("symbol", "nunique"),
                mean_sharpe_ratio=("sharpe_ratio", "mean"),
                median_sharpe_ratio=("sharpe_ratio", "median"),
                mean_sortino_ratio=("sortino_ratio", "mean"),
                mean_max_drawdown=("max_drawdown", "mean"),
                mean_calmar_ratio=("calmar_ratio", "mean"),
                mean_final_equity=("final_equity", "mean"),
                total_trades=("trades", "sum"),
            )
            .reset_index()
            .sort_values("mean_sharpe_ratio", ascending=False)
        )

        ranked = strategy_summary_df.set_index("strategy")["mean_sharpe_ratio"]
        _emit(report_lines, ranked.to_string(float_format="{:.3f}".format), stream_to_terminal)
        _emit(report_lines, "", stream_to_terminal)

        _emit(report_lines, "\n" + ("=" * 64), stream_to_terminal)
        _emit(report_lines, "  FULL MATRIX - OOS Sharpe Ratio by Strategy x Ticker", stream_to_terminal)
        _emit(report_lines, "=" * 64, stream_to_terminal)

        sharpe_matrix_df = records_df.pivot_table(
            index="strategy",
            columns="symbol",
            values="sharpe_ratio",
            aggfunc="mean",
        )
        sharpe_matrix_df["Mean"] = sharpe_matrix_df.mean(axis=1)
        sharpe_matrix_df = sharpe_matrix_df.sort_values("Mean", ascending=False)

        _emit(
            report_lines,
            sharpe_matrix_df.to_string(float_format="{:.3f}".format),
            stream_to_terminal,
        )
        _emit(report_lines, "", stream_to_terminal)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    run_dir = Path(artifacts_root) / run_id
    run_meta: dict[str, Any] = {
        "run_id": run_id,
        "generated_at_utc": generated_at_utc,
        "runner_config_path": RUNNER_CONFIG_PATH,
        "symbols": tickers,
        "strategy_names": [s.name for s in STRATEGIES],
        "start": START,
        "train_pct": TRAIN_PCT,
        "slippage": SLIPPAGE,
        "commission": COMMISSION,
        "risk_free_rate": RISK_FREE,
        "records_count": int(len(records_df)),
    }

    _write_artifacts(
        run_dir=run_dir,
        run_meta=run_meta,
        records_df=records_df,
        strategy_summary_df=strategy_summary_df,
        sharpe_matrix_df=sharpe_matrix_df,
    )

    print(f"Saved text report to: {output_path}")
    print(f"Saved structured artifacts to: {run_dir}")


if __name__ == "__main__":
    args = _parse_args()
    stream = args.mode in {"terminal", "console", "stdout"}
    run_pipeline(
        stream_to_terminal=stream,
        output_path=Path(args.output),
        artifacts_root=Path(args.artifacts_dir),
    )
