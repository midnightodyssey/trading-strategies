"""
scripts/select_strategies.py

Phase 3 portfolio selector: rank strategies, enforce diversification,
and export machine-readable selection output.

Modes:
    - global: choose top K strategies across the universe
    - per_symbol: choose top N strategies per symbol

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

    p.add_argument(
        "--selection-mode",
        choices=["global", "per_symbol"],
        default="global",
        help="global=top K strategies overall; per_symbol=top N strategies per symbol",
    )

    p.add_argument("--top-k-global", type=int, default=3)
    p.add_argument("--top-n-per-symbol", type=int, default=1)

    # Backward-compatible alias from Phase 2.
    p.add_argument("--top-n", type=int, default=None, help="Alias for --top-k-global")

    p.add_argument("--min-symbols", type=int, default=5)
    p.add_argument("--min-sharpe", type=float, default=0.0)
    p.add_argument("--min-trades", type=float, default=50)
    p.add_argument("--max-drawdown-abs", type=float, default=0.35)

    p.add_argument("--diversify", action="store_true", default=True)
    p.add_argument("--corr-threshold", type=float, default=0.85)

    p.add_argument("--max-total-allocations", type=int, default=30)
    p.add_argument("--max-symbol-weight", type=float, default=0.30)
    p.add_argument("--max-strategy-weight", type=float, default=0.25)

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

    scored["score_sharpe"] = scored["mean_sharpe_ratio"].rank(pct=True, ascending=True)
    scored["score_sortino"] = scored["mean_sortino_ratio"].rank(pct=True, ascending=True)
    scored["score_calmar"] = scored["mean_calmar_ratio"].rank(pct=True, ascending=True)
    scored["score_equity"] = scored["mean_final_equity"].rank(pct=True, ascending=True)

    # Drawdown closer to 0 is better.
    scored["score_drawdown"] = scored["mean_max_drawdown"].rank(pct=True, ascending=True)

    scored["selection_score"] = (
        0.35 * scored["score_sharpe"]
        + 0.20 * scored["score_sortino"]
        + 0.15 * scored["score_calmar"]
        + 0.15 * scored["score_drawdown"]
        + 0.15 * scored["score_equity"]
    )

    return scored.sort_values("selection_score", ascending=False).reset_index(drop=True)


def _build_symbol_strategy_table(metrics_long: pd.DataFrame) -> pd.DataFrame:
    if metrics_long.empty:
        raise RuntimeError("No rows in strategy_metrics_long.csv")

    needed = {
        "symbol",
        "strategy",
        "sharpe_ratio",
        "sortino_ratio",
        "calmar_ratio",
        "max_drawdown",
        "final_equity",
        "trades",
    }
    missing = needed.difference(metrics_long.columns)
    if missing:
        raise ValueError(f"strategy_metrics_long.csv missing columns: {sorted(missing)}")

    grouped = (
        metrics_long.groupby(["symbol", "strategy"], dropna=False)
        .agg(
            symbols_tested=("symbol", "nunique"),
            mean_sharpe_ratio=("sharpe_ratio", "mean"),
            mean_sortino_ratio=("sortino_ratio", "mean"),
            mean_calmar_ratio=("calmar_ratio", "mean"),
            mean_max_drawdown=("max_drawdown", "mean"),
            mean_final_equity=("final_equity", "mean"),
            total_trades=("trades", "sum"),
        )
        .reset_index()
    )
    return grouped


def _apply_filters(df: pd.DataFrame, args: argparse.Namespace) -> pd.DataFrame:
    return df[
        (df["symbols_tested"] >= args.min_symbols)
        & (df["mean_sharpe_ratio"] >= args.min_sharpe)
        & (df["total_trades"] >= args.min_trades)
        & (df["mean_max_drawdown"].abs() <= args.max_drawdown_abs)
    ].copy()


def _strategy_corr_from_matrix(sharpe_matrix_df: pd.DataFrame) -> pd.DataFrame:
    if sharpe_matrix_df.empty:
        return pd.DataFrame()

    matrix = sharpe_matrix_df.copy()
    if "strategy" in matrix.columns:
        matrix = matrix.set_index("strategy")
    if "Mean" in matrix.columns:
        matrix = matrix.drop(columns=["Mean"])

    matrix = matrix.apply(pd.to_numeric, errors="coerce")
    matrix = matrix.dropna(axis=0, how="all").dropna(axis=1, how="all")
    if matrix.empty:
        return pd.DataFrame()

    matrix = matrix.fillna(matrix.mean(axis=0)).fillna(0.0)
    corr = matrix.T.corr()
    return corr


def _is_diversified(candidate_strategy: str, selected_strategies: list[str], corr: pd.DataFrame, threshold: float) -> bool:
    if corr.empty:
        return True
    if candidate_strategy not in corr.index:
        return True

    for s in selected_strategies:
        if s not in corr.columns:
            continue
        c = corr.loc[candidate_strategy, s]
        if pd.notna(c) and abs(float(c)) >= threshold:
            return False
    return True


def _cap_weights(allocations: list[dict[str, Any]], max_symbol_weight: float, max_strategy_weight: float) -> list[dict[str, Any]]:
    if not allocations:
        return allocations

    for a in allocations:
        a["weight"] = 1.0

    n = len(allocations)
    for a in allocations:
        a["weight"] /= n

    by_symbol: dict[str, list[dict[str, Any]]] = {}
    by_strategy: dict[str, list[dict[str, Any]]] = {}
    for a in allocations:
        by_symbol.setdefault(str(a["symbol"]), []).append(a)
        by_strategy.setdefault(str(a["strategy"]), []).append(a)

    for _, items in by_symbol.items():
        total = sum(i["weight"] for i in items)
        if total > max_symbol_weight and total > 0:
            scale = max_symbol_weight / total
            for i in items:
                i["weight"] *= scale

    for _, items in by_strategy.items():
        total = sum(i["weight"] for i in items)
        if total > max_strategy_weight and total > 0:
            scale = max_strategy_weight / total
            for i in items:
                i["weight"] *= scale

    total_w = sum(a["weight"] for a in allocations)
    if total_w <= 0:
        eq = 1.0 / len(allocations)
        for a in allocations:
            a["weight"] = eq
    else:
        for a in allocations:
            a["weight"] = a["weight"] / total_w

    for a in allocations:
        a["weight"] = round(float(a["weight"]), 6)

    return allocations


def main() -> None:
    args = _parse_args()
    if args.top_n is not None:
        args.top_k_global = args.top_n

    artifacts_root = Path(args.artifacts_root)
    run_dir = _latest_run_dir(artifacts_root, args.run_id)

    summary_path = run_dir / "strategy_summary.csv"
    long_path = run_dir / "strategy_metrics_long.csv"
    matrix_path = run_dir / "sharpe_matrix.csv"

    if not summary_path.exists():
        raise FileNotFoundError(f"Missing {summary_path}")
    if not long_path.exists():
        raise FileNotFoundError(f"Missing {long_path}")

    df_summary = pd.read_csv(summary_path)
    df_long = pd.read_csv(long_path)
    df_matrix = pd.read_csv(matrix_path) if matrix_path.exists() else pd.DataFrame()

    if df_summary.empty:
        raise RuntimeError(f"No strategy rows in {summary_path}")

    scored_global = _score(df_summary)
    filtered_global = _apply_filters(scored_global, args)

    symbol_strategy = _build_symbol_strategy_table(df_long)
    scored_symbol_strategy = _score(symbol_strategy)
    filtered_symbol_strategy = _apply_filters(scored_symbol_strategy, args)

    corr = _strategy_corr_from_matrix(df_matrix)

    selected_allocations: list[dict[str, Any]] = []
    selected_strategy_names: list[str] = []

    if args.selection_mode == "global":
        candidates = filtered_global if not filtered_global.empty else scored_global
        for _, row in candidates.iterrows():
            strategy = str(row["strategy"])
            if args.diversify and not _is_diversified(strategy, selected_strategy_names, corr, args.corr_threshold):
                continue

            # Allocate strategy across all symbols equally (strategy-level global mode).
            selected_strategy_names.append(strategy)
            selected_allocations.append(
                {
                    "symbol": "*",
                    "strategy": strategy,
                    "selection_score": round(float(row["selection_score"]), 6),
                    "source": "global",
                }
            )
            if len(selected_allocations) >= args.top_k_global:
                break

    else:
        candidates = filtered_symbol_strategy if not filtered_symbol_strategy.empty else scored_symbol_strategy
        if candidates.empty:
            raise RuntimeError("No candidates available for per_symbol mode")

        for symbol, grp in candidates.groupby("symbol", sort=True):
            picks_for_symbol = 0
            grp = grp.sort_values("selection_score", ascending=False)

            for _, row in grp.iterrows():
                strategy = str(row["strategy"])
                if args.diversify and not _is_diversified(strategy, selected_strategy_names, corr, args.corr_threshold):
                    continue

                selected_strategy_names.append(strategy)
                selected_allocations.append(
                    {
                        "symbol": str(symbol),
                        "strategy": strategy,
                        "selection_score": round(float(row["selection_score"]), 6),
                        "source": "per_symbol",
                    }
                )
                picks_for_symbol += 1
                if picks_for_symbol >= args.top_n_per_symbol:
                    break

                if len(selected_allocations) >= args.max_total_allocations:
                    break
            if len(selected_allocations) >= args.max_total_allocations:
                break

    if not selected_allocations:
        raise RuntimeError("No allocations selected after filters/diversification")

    if len(selected_allocations) > args.max_total_allocations:
        selected_allocations = selected_allocations[: args.max_total_allocations]

    selected_allocations = _cap_weights(
        selected_allocations,
        max_symbol_weight=args.max_symbol_weight,
        max_strategy_weight=args.max_strategy_weight,
    )

    params_by_strategy = _load_runner_strategy_params(Path(args.runner_config))

    unique_strategies = []
    seen = set()
    for alloc in selected_allocations:
        s = str(alloc["strategy"])
        if s in seen:
            continue
        seen.add(s)
        unique_strategies.append(
            {
                "name": s,
                "params": params_by_strategy.get(s, {}),
            }
        )

    payload: dict[str, Any] = {
        "schema_version": 2,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": {
            "run_id": run_dir.name,
            "run_dir": str(run_dir),
            "summary_csv": str(summary_path),
            "metrics_long_csv": str(long_path),
            "sharpe_matrix_csv": str(matrix_path),
            "runner_config": args.runner_config,
        },
        "selection_mode": args.selection_mode,
        "selection_rules": {
            "top_k_global": args.top_k_global,
            "top_n_per_symbol": args.top_n_per_symbol,
            "min_symbols": args.min_symbols,
            "min_sharpe": args.min_sharpe,
            "min_trades": args.min_trades,
            "max_drawdown_abs": args.max_drawdown_abs,
            "diversify": args.diversify,
            "corr_threshold": args.corr_threshold,
            "max_total_allocations": args.max_total_allocations,
            "fallback_to_unfiltered_if_empty": True,
        },
        "risk_budget": {
            "max_symbol_weight": args.max_symbol_weight,
            "max_strategy_weight": args.max_strategy_weight,
        },
        # Backward-compatible section consumed by existing phase3 config builder.
        "selected_strategies": unique_strategies,
        # New richer portfolio construction output.
        "selected_allocations": selected_allocations,
        "ranked_table_global": [
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
            for _, r in scored_global.iterrows()
        ],
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    print(f"Loaded run: {run_dir.name}")
    print(f"Selection mode: {args.selection_mode}")
    print(f"Allocations selected: {len(selected_allocations)}")
    print(f"Unique strategies selected: {len(unique_strategies)}")
    print(f"Wrote: {output_path}")


if __name__ == "__main__":
    main()
