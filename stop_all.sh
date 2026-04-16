#!/usr/bin/env bash
# stop_all.sh — Stop all Dirac Solver services on Linux/cloud
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_DIR="$SCRIPT_DIR/.pids"
mkdir -p "$PID_DIR"

echo "=== Dirac Solver — Stopping Services ==="

# ── Kill Node.js API ──────────────────────────────────────────────
if [ -f "$PID_DIR/node_api.pid" ]; then
    PID=$(cat "$PID_DIR/node_api.pid")
    if kill -0 "$PID" 2>/dev/null; then
        kill "$PID" && echo "✓ Node.js API stopped (PID $PID)"
    fi
    rm -f "$PID_DIR/node_api.pid"
fi

# ── Kill Octopus MCP runtime (udocker launcher) ──────────────────
if [ -f "$PID_DIR/octopus_mcp.pid" ]; then
    PID=$(cat "$PID_DIR/octopus_mcp.pid")
    if kill -0 "$PID" 2>/dev/null; then
        kill "$PID" && echo "✓ Octopus MCP launcher stopped (PID $PID)"
    fi
    rm -f "$PID_DIR/octopus_mcp.pid"
fi

# ── Kill local Python backend ─────────────────────────────────────
if [ -f "$PID_DIR/local_engine.pid" ]; then
    PID=$(cat "$PID_DIR/local_engine.pid")
    if kill -0 "$PID" 2>/dev/null; then
        kill "$PID" && echo "✓ Local Python backend stopped (PID $PID)"
    fi
    rm -f "$PID_DIR/local_engine.pid"
fi

# ── Kill Vite ──────────────────────────────────────────────────────
if [ -f "$PID_DIR/vite.pid" ]; then
    PID=$(cat "$PID_DIR/vite.pid")
    if kill -0 "$PID" 2>/dev/null; then
        kill "$PID" && echo "✓ Vite frontend stopped (PID $PID)"
    fi
    rm -f "$PID_DIR/vite.pid"
fi

# Cleanup any stale frontend processes from previous runs.
pkill -f "frontend/node_modules/vite/bin/vite.js" >/dev/null 2>&1 || true
pkill -f "python3 -m http.server 5173" >/dev/null 2>&1 || true

# ── Kill Dirac execution queue worker ─────────────────────────────
if [ -f "$PID_DIR/dirac_exec_worker.pid" ]; then
    PID=$(cat "$PID_DIR/dirac_exec_worker.pid")
    if kill -0 "$PID" 2>/dev/null; then
        kill "$PID" && echo "✓ Dirac execution worker stopped (PID $PID)"
    fi
    rm -f "$PID_DIR/dirac_exec_worker.pid"
fi

# ── Kill persistent monitors ─────────────────────────────────────
if [ -f "$PID_DIR/monitor_5173_health.pid" ]; then
    PID=$(cat "$PID_DIR/monitor_5173_health.pid")
    if kill -0 "$PID" 2>/dev/null; then
        kill "$PID" && echo "✓ 5173 monitor stopped (PID $PID)"
    fi
    rm -f "$PID_DIR/monitor_5173_health.pid"
fi

if [ -f "$PID_DIR/monitor_feishu_signal.pid" ]; then
    PID=$(cat "$PID_DIR/monitor_feishu_signal.pid")
    if kill -0 "$PID" 2>/dev/null; then
        kill "$PID" && echo "✓ Feishu signal monitor stopped (PID $PID)"
    fi
    rm -f "$PID_DIR/monitor_feishu_signal.pid"
fi

pkill -f "scripts/monitor_5173_health.py" >/dev/null 2>&1 || true
pkill -f "scripts/monitor_feishu_signal.py" >/dev/null 2>&1 || true

# ── Docker ────────────────────────────────────────────────────────
echo "Stopping Docker container..."
cd "$SCRIPT_DIR/docker"
if docker compose version > /dev/null 2>&1; then
    docker compose down || true
elif command -v docker-compose > /dev/null 2>&1; then
    docker-compose down || true
else
    echo "⚠ Docker compose not available; skip container shutdown"
fi
cd "$SCRIPT_DIR"

for _port in 3001 5173 8000 8001 8011 8101; do
    if lsof -ti :"$_port" >/dev/null 2>&1; then
        echo "⚠ Port $_port still in use after stop_all"
    else
        echo "✓ Port $_port released"
    fi
done

echo "=== All services stopped ==="
