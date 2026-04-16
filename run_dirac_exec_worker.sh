#!/usr/bin/env bash
# run_dirac_exec_worker.sh
# Persistent queue consumer for Dirac execution bus.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-}"

if [ -z "$PYTHON_BIN" ]; then
    if [ -x "$HOME/miniconda3/bin/python3" ]; then
        PYTHON_BIN="$HOME/miniconda3/bin/python3"
    elif command -v python3 > /dev/null 2>&1; then
        PYTHON_BIN="$(command -v python3)"
    else
        echo "python3 not found; cannot run dirac_exec_worker" >&2
        exit 1
    fi
fi

QUEUE_PATH="$REPO_ROOT/state/dirac_exec_queue.json"
BRIDGE_PATH="$REPO_ROOT/state/copilot_openclaw_bridge.json"
DISPATCH_PATH="$REPO_ROOT/scripts/dispatch_dirac_task.py"
SYNC_PATH="$REPO_ROOT/state/dirac_solver_progress_sync.json"

# Claude Code 全局路径（供 OpenClaw exec 工具调用）
export CLAUDE_CODE_DIR="/data/home/zju321/Scholar/claude-code"
export PATH="$CLAUDE_CODE_DIR/bin:$PATH"

cd "$REPO_ROOT"
while true; do
    "$PYTHON_BIN" "$REPO_ROOT/scripts/dirac_exec_worker.py" \
        --once \
        --queue "$QUEUE_PATH" \
        --bridge "$BRIDGE_PATH" \
        --dispatch-script "$DISPATCH_PATH" \
        --sync-state "$SYNC_PATH" \
        --api-base "${DIRAC_API_BASE:-http://127.0.0.1:3001}" \
        --harness-base "${DIRAC_HARNESS_BASE:-http://127.0.0.1:8001}" \
        --dispatch-timeout-seconds "${DIRAC_DISPATCH_TIMEOUT_SECONDS:-1800}" \
        --retry-backoff-seconds "${DIRAC_RETRY_BACKOFF_SECONDS:-30}" \
        --max-attempts "${DIRAC_MAX_ATTEMPTS:-3}" \
        || true
    sleep "${DIRAC_WORKER_POLL_SECONDS:-4}"
done
