#!/usr/bin/env bash
# stop_all.sh — Stop all Dirac Solver services on Linux/cloud
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_DIR="$SCRIPT_DIR/.pids"

echo "=== Dirac Solver — Stopping Services ==="

# ── Kill Node.js API ──────────────────────────────────────────────
if [ -f "$PID_DIR/node_api.pid" ]; then
    PID=$(cat "$PID_DIR/node_api.pid")
    if kill -0 "$PID" 2>/dev/null; then
        kill "$PID" && echo "✓ Node.js API stopped (PID $PID)"
    fi
    rm -f "$PID_DIR/node_api.pid"
fi

# ── Kill Vite ──────────────────────────────────────────────────────
if [ -f "$PID_DIR/vite.pid" ]; then
    PID=$(cat "$PID_DIR/vite.pid")
    if kill -0 "$PID" 2>/dev/null; then
        kill "$PID" && echo "✓ Vite frontend stopped (PID $PID)"
    fi
    rm -f "$PID_DIR/vite.pid"
fi

# ── Docker ────────────────────────────────────────────────────────
echo "Stopping Docker container..."
cd "$SCRIPT_DIR/docker"
docker compose down
cd "$SCRIPT_DIR"

echo "=== All services stopped ==="
