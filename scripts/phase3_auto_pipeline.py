from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml


DEFAULT_BASE_CONFIG = Path('runner_config.yaml')
DEFAULT_SELECTED = Path('generated/selected_strategies.yaml')
DEFAULT_RESOLVED_CONFIG = Path('generated/runner_config.auto.yaml')
DEFAULT_PYTHON = sys.executable


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog='python scripts/phase3_auto_pipeline.py',
        description='Phase 3 orchestration: backtest -> selection -> runnable config -> optional run.',
    )

    p.add_argument('--python-bin', default=DEFAULT_PYTHON)
    p.add_argument('--base-config', default=str(DEFAULT_BASE_CONFIG))
    p.add_argument('--selected-output', default=str(DEFAULT_SELECTED))
    p.add_argument('--resolved-config', default=str(DEFAULT_RESOLVED_CONFIG))

    p.add_argument('--skip-backtest', action='store_true')
    p.add_argument('--skip-selection', action='store_true')

    p.add_argument(
        '--selection-only',
        action='store_true',
        help='Run selection + config generation only (skip backtest and runner).',
    )
    p.add_argument(
        '--runner-only',
        action='store_true',
        help='Run runner only using an existing resolved config (skip backtest and selection).',
    )

    p.add_argument('--run-runner', action='store_true')
    p.add_argument('--dry-run', action='store_true')

    p.add_argument('--top-n', type=int, default=3)
    p.add_argument('--min-symbols', type=int, default=5)
    p.add_argument('--min-sharpe', type=float, default=0.0)
    p.add_argument('--min-trades', type=float, default=50.0)
    p.add_argument('--max-drawdown-abs', type=float, default=0.35)

    p.add_argument(
        '--run-id',
        default='',
        help='Optional specific backtest run folder for selection. Empty uses latest.',
    )

    return p.parse_args()


def _run(cmd: list[str], label: str) -> None:
    print(f"\n[{label}] {' '.join(cmd)}")
    subprocess.run(cmd, check=True)


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f'File not found: {path}')
    data = yaml.safe_load(path.read_text(encoding='utf-8'))
    return data if isinstance(data, dict) else {}


def _build_resolved_config(base_cfg: dict[str, Any], selected_payload: dict[str, Any]) -> dict[str, Any]:
    selected = selected_payload.get('selected_strategies', [])
    if not isinstance(selected, list) or not selected:
        raise ValueError('selected_strategies is empty; nothing to run.')

    strategies: list[dict[str, Any]] = []
    for item in selected:
        if not isinstance(item, dict):
            continue
        name = item.get('name')
        if not name:
            continue
        params = item.get('params') or {}
        strategies.append({'name': str(name), 'params': dict(params)})

    if not strategies:
        raise ValueError('No valid strategies found in selected_strategies payload.')

    out = dict(base_cfg)
    out['strategies'] = strategies

    out['auto_selection'] = {
        'enabled': True,
        'source_run_id': selected_payload.get('source', {}).get('run_id'),
        'selection_rules': selected_payload.get('selection_rules', {}),
        'selected_count': len(strategies),
    }
    return out


def _resolve_execution(args: argparse.Namespace) -> tuple[bool, bool, bool]:
    if args.selection_only and args.runner_only:
        raise ValueError('Use either --selection-only or --runner-only, not both.')
    if args.selection_only and args.run_runner:
        raise ValueError('--selection-only cannot be combined with --run-runner.')

    if args.selection_only:
        return False, True, False
    if args.runner_only:
        return False, False, True

    do_backtest = not args.skip_backtest
    do_selection = not args.skip_selection
    do_runner = args.run_runner
    return do_backtest, do_selection, do_runner


def main() -> None:
    args = _parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    base_cfg_path = (repo_root / args.base_config).resolve()
    selected_path = (repo_root / args.selected_output).resolve()
    resolved_cfg_path = (repo_root / args.resolved_config).resolve()

    do_backtest, do_selection, do_runner = _resolve_execution(args)

    if do_backtest:
        _run(
            [args.python_bin, str(repo_root / 'scripts' / 'backtest_pipeline.py'), 'file'],
            'backtest',
        )

    if do_selection:
        cmd = [
            args.python_bin,
            str(repo_root / 'scripts' / 'select_strategies.py'),
            '--runner-config', str(base_cfg_path),
            '--output', str(selected_path),
            '--top-n', str(args.top_n),
            '--min-symbols', str(args.min_symbols),
            '--min-sharpe', str(args.min_sharpe),
            '--min-trades', str(args.min_trades),
            '--max-drawdown-abs', str(args.max_drawdown_abs),
        ]
        if args.run_id:
            cmd.extend(['--run-id', args.run_id])
        _run(cmd, 'selection')

    if do_selection or do_backtest:
        base_cfg = _load_yaml(base_cfg_path)
        selected_payload = _load_yaml(selected_path)
        resolved_cfg = _build_resolved_config(base_cfg, selected_payload)

        resolved_cfg_path.parent.mkdir(parents=True, exist_ok=True)
        resolved_cfg_path.write_text(
            yaml.safe_dump(resolved_cfg, sort_keys=False),
            encoding='utf-8',
        )
        print(f"\n[config] Wrote resolved runner config: {resolved_cfg_path}")

    if do_runner:
        if not resolved_cfg_path.exists():
            raise FileNotFoundError(
                f'Resolved config not found for --runner-only: {resolved_cfg_path}. '
                'Run without --runner-only first, or run with --selection-only to generate it.'
            )
        run_cmd = [
            args.python_bin,
            '-m',
            'runner.daily_runner',
            '--config',
            str(resolved_cfg_path),
        ]
        if args.dry_run:
            run_cmd.append('--dry-run')
        _run(run_cmd, 'runner')

    print('\nPhase 3 complete.')
    print(f'- Base config:      {base_cfg_path}')
    print(f'- Selection output: {selected_path}')
    print(f'- Resolved config:  {resolved_cfg_path}')


if __name__ == '__main__':
    main()
