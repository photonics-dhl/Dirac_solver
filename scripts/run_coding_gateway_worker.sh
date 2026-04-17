#!/usr/bin/env bash
# run_coding_gateway_worker.sh
# Persistent coding gateway worker loop with production adapter.
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
        echo "python3 not found; cannot run coding gateway worker" >&2
        exit 1
    fi
fi

STATE_PATH="${DIRAC_CODING_GATEWAY_STATE:-$REPO_ROOT/state/coding_gateway_tasks.json}"
WORK_DIR="${DIRAC_CODING_WORK_DIR:-$REPO_ROOT/state/coding_gateway_work}"
POLL_SECONDS="${DIRAC_CODING_WORKER_POLL_SECONDS:-4}"
TIMEOUT_SECONDS="${DIRAC_CODING_ADAPTER_TIMEOUT_SECONDS:-1800}"
ADAPTER_CMD="${DIRAC_CODING_ADAPTER_CMD:-$PYTHON_BIN scripts/coding_execution_adapter.py --task-file {task_file}}"

cd "$REPO_ROOT"
while true; do
    "$PYTHON_BIN" "$REPO_ROOT/scripts/coding_gateway_worker.py" \
        --state "$STATE_PATH" \
        --work-dir "$WORK_DIR" \
        --timeout-seconds "$TIMEOUT_SECONDS" \
        --adapter-cmd "$ADAPTER_CMD" \
        --max-jobs 1 \
        || true
    sleep "$POLL_SECONDS"
done
