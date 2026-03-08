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
DEFAULT_MANUAL_OVERRIDE = Path('generated/manual_override.yaml')
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
    p.add_argument('--manual-override', default=str(DEFAULT_MANUAL_OVERRIDE))
    p.add_argument('--ignore-manual-override', action='store_true')

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


def _validate_strategy_list(items: Any) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        return []

    out: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        name = item.get('name')
        if not name:
            continue
        params = item.get('params') or {}
        out.append({'name': str(name), 'params': dict(params)})
    return out


def _apply_manual_override(
    base_cfg: dict[str, Any],
    selected_payload: dict[str, Any],
    manual_override: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    auto_strategies = _validate_strategy_list(selected_payload.get('selected_strategies', []))
    if not auto_strategies:
        raise ValueError('selected_strategies is empty; nothing to run.')

    selected_allocations = selected_payload.get('selected_allocations', [])
    if not isinstance(selected_allocations, list):
        selected_allocations = []

    auto_meta = {
        'enabled': True,
        'source_run_id': selected_payload.get('source', {}).get('run_id'),
        'selection_rules': selected_payload.get('selection_rules', {}),
        'selection_mode': selected_payload.get('selection_mode'),
        'risk_budget': selected_payload.get('risk_budget', {}),
        'selected_count': len(auto_strategies),
    }

    override_meta = {
        'enabled': False,
        'applied': False,
        'mode': None,
        'source': None,
        'notes': None,
    }

    if not manual_override:
        return auto_strategies, auto_meta, override_meta

    enabled = bool(manual_override.get('enabled', False))
    if not enabled:
        return auto_strategies, auto_meta, override_meta

    mode = str(manual_override.get('mode', 'replace')).lower()
    manual_strategies = _validate_strategy_list(manual_override.get('strategies', []))

    if not manual_strategies:
        raise ValueError('manual override is enabled but contains no valid strategies.')

    if mode == 'append':
        seen = {s['name'] for s in auto_strategies}
        merged = list(auto_strategies)
        for s in manual_strategies:
            if s['name'] in seen:
                continue
            merged.append(s)
            seen.add(s['name'])
        final_strategies = merged
    else:
        mode = 'replace'
        final_strategies = manual_strategies

    manual_allocations = manual_override.get('selected_allocations', [])
    if isinstance(manual_allocations, list) and manual_allocations:
        selected_allocations = manual_allocations

    override_meta = {
        'enabled': True,
        'applied': True,
        'mode': mode,
        'source': str(manual_override.get('source', 'manual_override_file')),
        'notes': manual_override.get('notes'),
    }

    return final_strategies, auto_meta, {
        **override_meta,
        'selected_allocations': selected_allocations,
    }


def _build_resolved_config(
    base_cfg: dict[str, Any],
    selected_payload: dict[str, Any],
    manual_override: dict[str, Any] | None,
) -> dict[str, Any]:
    out = dict(base_cfg)

    final_strategies, auto_meta, override_meta = _apply_manual_override(
        base_cfg=base_cfg,
        selected_payload=selected_payload,
        manual_override=manual_override,
    )

    out['strategies'] = final_strategies

    selected_allocations = selected_payload.get('selected_allocations', [])
    if isinstance(override_meta, dict) and override_meta.get('selected_allocations'):
        selected_allocations = override_meta.get('selected_allocations')

    out['execution_plan'] = {
        'source': 'auto_selection',
        'generated_at_utc': selected_payload.get('generated_at_utc'),
        'selected_allocations': selected_allocations,
    }

    out['auto_selection'] = auto_meta
    out['manual_override'] = {
        'enabled': bool(override_meta.get('enabled', False)),
        'applied': bool(override_meta.get('applied', False)),
        'mode': override_meta.get('mode'),
        'source': override_meta.get('source'),
        'notes': override_meta.get('notes'),
    }

    return out


def _write_manual_override_template(path: Path) -> None:
    if path.exists():
        return

    template = {
        'enabled': False,
        'mode': 'replace',
        'source': 'manual',
        'notes': 'Set enabled=true to override auto-selected strategies.',
        'strategies': [
            {'name': 'EMACrossover', 'params': {'fast': 12, 'slow': 26}},
            {'name': 'MACDCrossover', 'params': {'fast': 12, 'slow': 26, 'signal_period': 9}},
        ],
        'selected_allocations': [],
    }

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(template, sort_keys=False), encoding='utf-8')


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
    manual_override_path = (repo_root / args.manual_override).resolve()

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

        _write_manual_override_template(manual_override_path)
        manual_override = None
        if not args.ignore_manual_override and manual_override_path.exists():
            manual_override = _load_yaml(manual_override_path)

        resolved_cfg = _build_resolved_config(
            base_cfg=base_cfg,
            selected_payload=selected_payload,
            manual_override=manual_override,
        )

        resolved_cfg_path.parent.mkdir(parents=True, exist_ok=True)
        resolved_cfg_path.write_text(
            yaml.safe_dump(resolved_cfg, sort_keys=False),
            encoding='utf-8',
        )
        print(f"\n[config] Wrote resolved runner config: {resolved_cfg_path}")
        print(f"[config] Manual override file: {manual_override_path}")

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
    print(f'- Manual override:  {manual_override_path}')


if __name__ == '__main__':
    main()
