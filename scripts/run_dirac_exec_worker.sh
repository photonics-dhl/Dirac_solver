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
WORKFLOW_SPEC_PATH="$REPO_ROOT/orchestration/execution_wake_state_machine.json"
REPORTS_DIR="$REPO_ROOT/docs/harness_reports"
CLEANUP_SCRIPT="$REPO_ROOT/scripts/cleanup_harness_reports.py"

BREATHING_THRESHOLD="${DIRAC_REPORTS_BREATHING_THRESHOLD:-1200}"
BREATHING_CHECK_EVERY="${DIRAC_REPORTS_BREATHING_CHECK_EVERY:-30}"
BREATHING_KEEP_PER_CASE="${DIRAC_REPORTS_BREATHING_KEEP_PER_CASE:-1}"
BREATHING_KEEP_GLOBAL="${DIRAC_REPORTS_BREATHING_KEEP_GLOBAL:-3}"
BREATHING_POLL_COUNT=0

cd "$REPO_ROOT"
while true; do
    EXTRA_ARGS=()
    if [ -n "${DIRAC_RETRY_BACKOFF_SECONDS:-}" ]; then
        EXTRA_ARGS+=("--retry-backoff-seconds" "$DIRAC_RETRY_BACKOFF_SECONDS")
    fi
    if [ -n "${DIRAC_MAX_ATTEMPTS:-}" ]; then
        EXTRA_ARGS+=("--max-attempts" "$DIRAC_MAX_ATTEMPTS")
    fi
    if [ "${DIRAC_AUTO_SUBMIT_CODING:-0}" = "1" ]; then
        EXTRA_ARGS+=("--auto-submit-coding")
    fi
    if [ -n "${DIRAC_CODING_GATEWAY_CONFIG:-}" ]; then
        EXTRA_ARGS+=("--coding-gateway-config" "$DIRAC_CODING_GATEWAY_CONFIG")
    fi
    if [ -n "${DIRAC_CODING_GATEWAY_URL:-}" ]; then
        EXTRA_ARGS+=("--coding-gateway-url" "$DIRAC_CODING_GATEWAY_URL")
    fi
    BASE_CMD=(
        "$PYTHON_BIN" "$REPO_ROOT/scripts/dirac_exec_worker.py"
        --once
        --queue "$QUEUE_PATH"
        --bridge "$BRIDGE_PATH"
        --dispatch-script "$DISPATCH_PATH"
        --sync-state "$SYNC_PATH"
        --workflow-spec "$WORKFLOW_SPEC_PATH"
        --api-base "${DIRAC_API_BASE:-http://127.0.0.1:3001}"
        --harness-base "${DIRAC_HARNESS_BASE:-http://127.0.0.1:8001}"
        --dispatch-timeout-seconds "${DIRAC_DISPATCH_TIMEOUT_SECONDS:-1200}"
    )
    if [ "${#EXTRA_ARGS[@]}" -gt 0 ]; then
        BASE_CMD+=("${EXTRA_ARGS[@]}")
    fi
    "${BASE_CMD[@]}" || true

    BREATHING_POLL_COUNT=$((BREATHING_POLL_COUNT + 1))
    if [ "$BREATHING_CHECK_EVERY" -gt 0 ] && [ $((BREATHING_POLL_COUNT % BREATHING_CHECK_EVERY)) -eq 0 ]; then
        if [ -d "$REPORTS_DIR" ] && [ -f "$CLEANUP_SCRIPT" ]; then
            REPORT_COUNT=$(find "$REPORTS_DIR" -maxdepth 1 -type f \( -name "*.json" -o -name "*.md" \) | wc -l | tr -d ' ')
            if [ "${REPORT_COUNT:-0}" -gt "$BREATHING_THRESHOLD" ]; then
                "$PYTHON_BIN" "$CLEANUP_SCRIPT" \
                    --reports-dir "$REPORTS_DIR" \
                    --openclaw-sync-path "$SYNC_PATH" \
                    --keep-per-case "$BREATHING_KEEP_PER_CASE" \
                    --keep-global "$BREATHING_KEEP_GLOBAL" \
                    --breathing-file-threshold "$BREATHING_THRESHOLD" \
                    --trigger-reason "breathing_threshold" >> "$REPO_ROOT/logs/cleanup_harness_reports.log" 2>&1 || true
            fi
        fi
    fi

    sleep "${DIRAC_WORKER_POLL_SECONDS:-4}"
done
