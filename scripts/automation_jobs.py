from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from runner.notifier import Notifier
from runner.runner_config import RunnerConfig


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog='python scripts/automation_jobs.py',
        description='Automation jobs for nightly research, promotion cycles, and execution.',
    )
    p.add_argument('--job', choices=['nightly', 'promotion', 'execute'], required=True)
    p.add_argument('--python-bin', default=sys.executable)
    p.add_argument('--config', default='runner_config.yaml')
    p.add_argument('--phase3-script', default='scripts/phase3_auto_pipeline.py')
    p.add_argument('--report-dir', default='logs/automation')
    p.add_argument('--notify', action=argparse.BooleanOptionalAction, default=True)

    p.add_argument('--selected-output', default='generated/selected_strategies.yaml')
    p.add_argument('--resolved-config', default='generated/runner_config.auto.yaml')
    p.add_argument('--manual-override', default='generated/manual_override.yaml')

    p.add_argument('--promotion-runner', action='store_true', help='After promotion, run runner in dry-run as a verification step.')
    p.add_argument('--promotion-recompute-backtest', action='store_true', help='For promotion job, rerun backtest before selection.')
    p.add_argument('--execute-dry-run', action='store_true', help='For execute job, run runner with --dry-run (no live orders).')

    p.add_argument('--selection-mode', choices=['global', 'per_symbol'], default='global')
    p.add_argument('--top-n', type=int, default=3)
    p.add_argument('--top-k-global', type=int, default=None)
    p.add_argument('--top-n-per-symbol', type=int, default=1)
    p.add_argument('--max-total-allocations', type=int, default=30)
    p.add_argument('--corr-threshold', type=float, default=0.85)
    p.add_argument('--max-symbol-weight', type=float, default=0.30)
    p.add_argument('--max-strategy-weight', type=float, default=0.25)

    p.add_argument('--min-symbols', type=int, default=5)
    p.add_argument('--min-sharpe', type=float, default=0.0)
    p.add_argument('--min-trades', type=float, default=50.0)
    p.add_argument('--max-drawdown-abs', type=float, default=0.35)
    return p.parse_args()


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, text=True, capture_output=True)


def _common_selection_flags(args: argparse.Namespace) -> list[str]:
    top_k_global = args.top_k_global if args.top_k_global is not None else args.top_n
    return [
        '--selection-mode',
        str(args.selection_mode),
        '--top-n',
        str(args.top_n),
        '--top-k-global',
        str(top_k_global),
        '--top-n-per-symbol',
        str(args.top_n_per_symbol),
        '--max-total-allocations',
        str(args.max_total_allocations),
        '--corr-threshold',
        str(args.corr_threshold),
        '--max-symbol-weight',
        str(args.max_symbol_weight),
        '--max-strategy-weight',
        str(args.max_strategy_weight),
        '--min-symbols',
        str(args.min_symbols),
        '--min-sharpe',
        str(args.min_sharpe),
        '--min-trades',
        str(args.min_trades),
        '--max-drawdown-abs',
        str(args.max_drawdown_abs),
    ]


def _base_phase3_command(args: argparse.Namespace, repo_root: Path) -> list[str]:
    phase3 = str((repo_root / args.phase3_script).resolve())
    return [
        args.python_bin,
        phase3,
        '--base-config',
        str(args.config),
        '--selected-output',
        str(args.selected_output),
        '--resolved-config',
        str(args.resolved_config),
        '--manual-override',
        str(args.manual_override),
    ]


def _build_phase3_command(args: argparse.Namespace, repo_root: Path) -> list[str]:
    cmd = _base_phase3_command(args, repo_root)

    if args.job == 'nightly':
        cmd.extend(_common_selection_flags(args))
        return cmd

    if args.job == 'promotion':
        cmd.extend(_common_selection_flags(args))
        if not args.promotion_recompute_backtest:
            cmd.append('--selection-only')
        return cmd

    # execute job
    cmd.append('--runner-only')
    if args.execute_dry_run:
        cmd.append('--dry-run')
    return cmd


def _write_reports(report_dir: Path, payload: dict[str, Any], stdout: str, stderr: str) -> tuple[Path, Path]:
    report_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
    job = payload['job']

    json_path = report_dir / f'{job}_{ts}.json'
    md_path = report_dir / f'{job}_{ts}.md'
    latest_json = report_dir / f'latest_{job}.json'
    latest_md = report_dir / f'latest_{job}.md'

    json_path.write_text(json.dumps(payload, indent=2), encoding='utf-8')

    md_lines = [
        f"# Automation Job: {job}",
        '',
        f"- status: {'SUCCESS' if payload['success'] else 'FAILED'}",
        f"- started_utc: {payload['started_utc']}",
        f"- finished_utc: {payload['finished_utc']}",
        f"- duration_seconds: {payload['duration_seconds']:.2f}",
        f"- command: `{' '.join(payload['command'])}`",
        '',
        '## Stdout',
        '```text',
        stdout[-12000:] if stdout else '(no stdout)',
        '```',
        '',
        '## Stderr',
        '```text',
        stderr[-12000:] if stderr else '(no stderr)',
        '```',
    ]
    md_path.write_text('\n'.join(md_lines) + '\n', encoding='utf-8')

    latest_json.write_text(json_path.read_text(encoding='utf-8'), encoding='utf-8')
    latest_md.write_text(md_path.read_text(encoding='utf-8'), encoding='utf-8')

    return json_path, md_path


def _summarize_selection(selected_path: Path, max_rows: int = 8) -> str:
    if not selected_path.exists():
        return "Selection summary: (selected_strategies.yaml not found)"

    try:
        data = yaml.safe_load(selected_path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        return f"Selection summary: (failed to read {selected_path}: {exc})"

    lines: list[str] = []
    src = data.get("source", {}) or {}
    lines.append("Selection summary:")
    if src.get("run_id"):
        lines.append(f"  run_id: {src.get('run_id')}")
    if data.get("selection_mode"):
        lines.append(f"  mode: {data.get('selection_mode')}")

    rules = data.get("selection_rules", {}) or {}
    if rules:
        lines.append(
            "  rules: "
            f"top_k_global={rules.get('top_k_global')} "
            f"top_n_per_symbol={rules.get('top_n_per_symbol')} "
            f"min_sharpe={rules.get('min_sharpe')} "
            f"min_trades={rules.get('min_trades')} "
            f"max_drawdown_abs={rules.get('max_drawdown_abs')} "
            f"corr_threshold={rules.get('corr_threshold')}"
        )

    ranked = data.get("ranked_table_global", []) or []
    if ranked:
        lines.append("  top_strategies:")
        for row in ranked[:max_rows]:
            lines.append(
                "    - "
                f"{row.get('strategy')} | "
                f"score={row.get('selection_score')} "
                f"sharpe={row.get('mean_sharpe_ratio')} "
                f"sortino={row.get('mean_sortino_ratio')} "
                f"calmar={row.get('mean_calmar_ratio')} "
                f"mdd={row.get('mean_max_drawdown')} "
                f"trades={row.get('total_trades')}"
            )

    allocs = data.get("selected_allocations", []) or []
    if allocs:
        lines.append("  selected_allocations:")
        for a in allocs[:max_rows]:
            lines.append(
                "    - "
                f"{a.get('symbol')} | "
                f"{a.get('strategy')} | "
                f"weight={a.get('weight')} "
                f"score={a.get('selection_score')}"
            )
        if len(allocs) > max_rows:
            lines.append(f"    ... +{len(allocs) - max_rows} more")

    return "\n".join(lines)


def _notify(args: argparse.Namespace, repo_root: Path, payload: dict[str, Any], md_path: Path) -> None:
    if not args.notify:
        return

    cfg_path = (repo_root / args.config).resolve()
    cfg = RunnerConfig.from_yaml(str(cfg_path))
    notifier = Notifier(cfg.notifications)

    status = 'SUCCESS' if payload['success'] else 'FAILED'
    subject = f"[Automation] {args.job} {status}"
    body = (
        f"Job: {args.job}\n"
        f"Config: {args.config}\n"
        f"Status: {status}\n"
        f"Started (UTC): {payload['started_utc']}\n"
        f"Finished (UTC): {payload['finished_utc']}\n"
        f"Duration (s): {payload['duration_seconds']:.2f}\n"
        f"Report: {md_path}\n"
        f"Exit code: {payload['returncode']}\n"
    )

    if args.job in ("nightly", "promotion"):
        selected_path = (repo_root / args.selected_output).resolve()
        body += "\n" + _summarize_selection(selected_path) + "\n"

    notifier._dispatch(subject, body)  # noqa: SLF001


def main() -> None:
    args = _parse_args()
    repo_root = Path(__file__).resolve().parents[1]

    started = datetime.now(timezone.utc)
    primary_cmd = _build_phase3_command(args, repo_root)
    primary = _run(primary_cmd)

    extra_stdout = ''
    extra_stderr = ''
    returncode = primary.returncode

    if args.job == 'promotion' and args.promotion_runner and returncode == 0:
        check_cmd = _base_phase3_command(args, repo_root) + ['--runner-only', '--dry-run']
        check = _run(check_cmd)
        extra_stdout = f"\n\n[promotion_runner_check]\n{check.stdout}"
        extra_stderr = f"\n\n[promotion_runner_check]\n{check.stderr}"
        if check.returncode != 0:
            returncode = check.returncode

    finished = datetime.now(timezone.utc)

    payload = {
        'job': args.job,
        'success': returncode == 0,
        'returncode': returncode,
        'started_utc': started.isoformat(),
        'finished_utc': finished.isoformat(),
        'duration_seconds': (finished - started).total_seconds(),
        'command': primary_cmd,
        'settings': {
            'config': args.config,
            'selected_output': args.selected_output,
            'resolved_config': args.resolved_config,
            'manual_override': args.manual_override,
            'promotion_runner': args.promotion_runner,
            'promotion_recompute_backtest': args.promotion_recompute_backtest,
            'execute_dry_run': args.execute_dry_run,
            'notify': args.notify,
            'selection_mode': args.selection_mode,
            'top_n': args.top_n,
            'top_k_global': args.top_k_global,
            'top_n_per_symbol': args.top_n_per_symbol,
            'max_total_allocations': args.max_total_allocations,
            'corr_threshold': args.corr_threshold,
            'max_symbol_weight': args.max_symbol_weight,
            'max_strategy_weight': args.max_strategy_weight,
            'min_symbols': args.min_symbols,
            'min_sharpe': args.min_sharpe,
            'min_trades': args.min_trades,
            'max_drawdown_abs': args.max_drawdown_abs,
        },
    }

    report_dir = (repo_root / args.report_dir).resolve()
    json_path, md_path = _write_reports(
        report_dir,
        payload,
        primary.stdout + extra_stdout,
        primary.stderr + extra_stderr,
    )

    try:
        _notify(args, repo_root, payload, md_path)
    except Exception as exc:
        payload['notify_error'] = str(exc)
        json_path.write_text(json.dumps(payload, indent=2), encoding='utf-8')

    print(f"Job: {args.job}")
    print(f"Status: {'SUCCESS' if payload['success'] else 'FAILED'}")
    print(f"JSON report: {json_path}")
    print(f"Markdown report: {md_path}")

    if not payload['success']:
        raise SystemExit(returncode)


if __name__ == '__main__':
    main()
