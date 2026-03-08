"""
scripts/select_strategies.py

Phase 2 selector: rank backtest strategies and export selected set to YAML.

Usage:
    python scripts/select_strategies.py
    python scripts/select_strategies.py --top-n 3 --min-sharpe 0.25
    python scripts/select_strategies.py --run-id 20260308_055045

Output:
    generated/selected_strategies.yaml
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

DEFAULT_ARTIFACTS_ROOT = Path("artifacts/backtests")
DEFAULT_RUNNER_CONFIG = Path("runner_config.yaml")
DEFAULT_OUTPUT_PATH = Path("generated/selected_strategies.yaml")


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="python scripts/select_strategies.py")
    p.add_argument("--artifacts-root", default=str(DEFAULT_ARTIFACTS_ROOT))
    p.add_argument("--run-id", default="", help="Specific backtest run id (folder name)")
    p.add_argument("--runner-config", default=str(DEFAULT_RUNNER_CONFIG))
    p.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH))

    p.add_argument("--top-n", type=int, default=3)
    p.add_argument("--min-symbols", type=int, default=5)
    p.add_argument("--min-sharpe", type=float, default=0.0)
    p.add_argument("--min-trades", type=float, default=50)
    p.add_argument("--max-drawdown-abs", type=float, default=0.35)

    return p.parse_args()


def _latest_run_dir(artifacts_root: Path, run_id: str) -> Path:
    if run_id:
        run_dir = artifacts_root / run_id
        if not run_dir.exists():
            raise FileNotFoundError(f"Run id not found: {run_dir}")
        return run_dir

    runs = sorted([d for d in artifacts_root.iterdir() if d.is_dir()])
    if not runs:
        raise FileNotFoundError(f"No run folders in {artifacts_root}")
    return runs[-1]


def _load_runner_strategy_params(runner_config_path: Path) -> dict[str, dict[str, Any]]:
    if not runner_config_path.exists():
        return {}

    raw = yaml.safe_load(runner_config_path.read_text(encoding="utf-8")) or {}
    items = raw.get("strategies", []) or []

    out: dict[str, dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if not name:
            continue
        out[str(name)] = dict(item.get("params", {}) or {})
    return out


def _safe_float(v: Any) -> float | None:
    try:
        if pd.isna(v):
            return None
        return float(v)
    except Exception:
        return None


def _score(df: pd.DataFrame) -> pd.DataFrame:
    scored = df.copy()

    # Higher is better for these.
    scored["score_sharpe"] = scored["mean_sharpe_ratio"].rank(pct=True, ascending=True)
    scored["score_sortino"] = scored["mean_sortino_ratio"].rank(pct=True, ascending=True)
    scored["score_calmar"] = scored["mean_calmar_ratio"].rank(pct=True, ascending=True)
    scored["score_equity"] = scored["mean_final_equity"].rank(pct=True, ascending=True)

    # Drawdown closer to 0 is better (less severe drawdown).
    scored["score_drawdown"] = scored["mean_max_drawdown"].rank(pct=True, ascending=True)

    scored["selection_score"] = (
        0.35 * scored["score_sharpe"]
        + 0.20 * scored["score_sortino"]
        + 0.15 * scored["score_calmar"]
        + 0.15 * scored["score_drawdown"]
        + 0.15 * scored["score_equity"]
    )

    return scored.sort_values("selection_score", ascending=False).reset_index(drop=True)


def main() -> None:
    args = _parse_args()

    artifacts_root = Path(args.artifacts_root)
    run_dir = _latest_run_dir(artifacts_root, args.run_id)
    summary_path = run_dir / "strategy_summary.csv"
    if not summary_path.exists():
        raise FileNotFoundError(f"Missing {summary_path}")

    df = pd.read_csv(summary_path)
    if df.empty:
        raise RuntimeError(f"No strategy rows in {summary_path}")

    scored = _score(df)

    filtered = scored[
        (scored["symbols_tested"] >= args.min_symbols)
        & (scored["mean_sharpe_ratio"] >= args.min_sharpe)
        & (scored["total_trades"] >= args.min_trades)
        & (scored["mean_max_drawdown"].abs() <= args.max_drawdown_abs)
    ].copy()

    selected = filtered.head(args.top_n).copy()
    if selected.empty:
        # Fallback to top-n by score if filters are too strict.
        selected = scored.head(args.top_n).copy()

    params_by_strategy = _load_runner_strategy_params(Path(args.runner_config))

    selected_items: list[dict[str, Any]] = []
    for _, row in selected.iterrows():
        name = str(row["strategy"])
        selected_items.append(
            {
                "name": name,
                "params": params_by_strategy.get(name, {}),
                "selection_score": round(float(row["selection_score"]), 6),
                "diagnostics": {
                    "symbols_tested": int(row["symbols_tested"]),
                    "mean_sharpe_ratio": _safe_float(row["mean_sharpe_ratio"]),
                    "mean_sortino_ratio": _safe_float(row["mean_sortino_ratio"]),
                    "mean_calmar_ratio": _safe_float(row["mean_calmar_ratio"]),
                    "mean_max_drawdown": _safe_float(row["mean_max_drawdown"]),
                    "mean_final_equity": _safe_float(row["mean_final_equity"]),
                    "total_trades": _safe_float(row["total_trades"]),
                },
            }
        )

    payload: dict[str, Any] = {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": {
            "run_id": run_dir.name,
            "run_dir": str(run_dir),
            "summary_csv": str(summary_path),
            "runner_config": args.runner_config,
        },
        "selection_rules": {
            "top_n": args.top_n,
            "min_symbols": args.min_symbols,
            "min_sharpe": args.min_sharpe,
            "min_trades": args.min_trades,
            "max_drawdown_abs": args.max_drawdown_abs,
            "fallback_to_top_n_if_empty": True,
        },
        "selected_strategies": selected_items,
        "ranked_table": [
            {
                "strategy": str(r["strategy"]),
                "selection_score": round(float(r["selection_score"]), 6),
                "mean_sharpe_ratio": _safe_float(r["mean_sharpe_ratio"]),
                "mean_sortino_ratio": _safe_float(r["mean_sortino_ratio"]),
                "mean_calmar_ratio": _safe_float(r["mean_calmar_ratio"]),
                "mean_max_drawdown": _safe_float(r["mean_max_drawdown"]),
                "mean_final_equity": _safe_float(r["mean_final_equity"]),
                "symbols_tested": int(r["symbols_tested"]),
                "total_trades": _safe_float(r["total_trades"]),
            }
            for _, r in scored.iterrows()
        ],
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    print(f"Loaded run: {run_dir.name}")
    print(f"Strategies ranked: {len(scored)}")
    print(f"Strategies selected: {len(selected_items)}")
    print(f"Wrote: {output_path}")


if __name__ == "__main__":
    main()
