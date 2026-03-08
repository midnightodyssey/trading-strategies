#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# scripts/update.sh — Pull latest code from git and verify the runner
# ─────────────────────────────────────────────────────────────────────────────
#
# Run this on the VPS whenever you want to deploy new code:
#   ./scripts/update.sh
#   bash /opt/trading/scripts/update.sh   # from any directory
#
# What it does:
#   1. git pull origin main
#   2. pip install any new requirements (quietly)
#   3. Parse runner_config.yaml and confirm it loads cleanly
#   4. Print a summary (symbols loaded, strategy, mode)
#   5. Exit 0 on success, 1 on any failure
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

# ── Resolve repo root (works regardless of where the script is called from) ──
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

SEP="════════════════════════════════════════════════════════════════"

echo "$SEP"
echo "  Trading Runner — Deploy"
echo "  $(date '+%Y-%m-%d %H:%M:%S %Z')"
echo "$SEP"
echo ""


# ── 1. Show what we're starting from ─────────────────────────────────────────
echo "▸ Current version:"
git log --oneline -1
echo ""


# ── 2. Pull ───────────────────────────────────────────────────────────────────
echo "▸ Pulling from origin..."
GIT_OUT=$(git pull 2>&1)
echo "  $GIT_OUT"
echo ""

echo "▸ New version:"
git log --oneline -1
echo ""


# ── 3. Show files that changed ────────────────────────────────────────────────
CHANGED=$(git diff HEAD@{1} HEAD --name-only 2>/dev/null || true)
if [ -n "$CHANGED" ]; then
    echo "▸ Files updated:"
    echo "$CHANGED" | sed 's/^/    /'
else
    echo "▸ No files changed (already up to date)."
fi
echo ""


# ── 4. Install any new dependencies ──────────────────────────────────────────
if [ -f "$REPO_DIR/requirements.txt" ]; then
    # Detect venv: prefer $REPO_DIR/venv, then fall back to activated env
    if [ -d "$REPO_DIR/venv" ]; then
        PYTHON="$REPO_DIR/venv/bin/python"
        PIP="$REPO_DIR/venv/bin/pip"
    elif command -v python3 &>/dev/null; then
        PYTHON="python3"
        PIP="pip3"
    else
        PYTHON="python"
        PIP="pip"
    fi

    echo "▸ Checking requirements..."
    $PIP install -q -r requirements.txt
    echo "  Dependencies OK"
    echo ""
fi


# ── 5. Verify config parses correctly ─────────────────────────────────────────
echo "▸ Verifying config..."

$PYTHON - <<'PYEOF'
import sys
sys.path.insert(0, ".")
try:
    from runner.runner_config import RunnerConfig
    cfg = RunnerConfig.from_yaml("runner_config.yaml")

    print(f"  Mode:             {cfg.mode}")
    print(f"  Data source:      {cfg.schedule.data_source}")
    print(f"  Symbols loaded:   {len(cfg.symbols)}")
    print(f"  First 5:          {cfg.symbols[:5]}")
    print(f"  Strategies:       {[s.name for s in cfg.strategies]}")
    print(f"  Max positions:    {cfg.risk.max_open_positions}")
    print(f"  Blackout days:    {cfg.schedule.earnings_blackout_days}")

    if cfg.mode == "live":
        print("  ⚠  Mode is LIVE — real money will be traded")
    else:
        print("  Config OK ✓")

except Exception as e:
    print(f"  ✗ Config error: {e}", file=sys.stderr)
    sys.exit(1)
PYEOF

echo ""
echo "$SEP"
echo "  Deploy complete ✓"
echo "$SEP"
