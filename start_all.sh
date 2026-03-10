#!/usr/bin/env bash
# start_all.sh — Start all Dirac Solver services on Linux/cloud
# Usage: ./start_all.sh
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_DIR="$SCRIPT_DIR/.pids"
mkdir -p "$PID_DIR"

echo "=== Dirac Solver — Starting Services ==="

# ── 1. Octopus MCP Docker container ──────────────────────────────
echo "[1/3] Starting Octopus MCP container..."
cd "$SCRIPT_DIR/docker"
docker compose up -d
cd "$SCRIPT_DIR"

# Wait for health
echo "      Waiting for Octopus MCP health check..."
for i in $(seq 1 20); do
    if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
        echo "      ✓ Octopus MCP ready"
        break
    fi
    sleep 2
done

# ── 2. Node.js API server (src/server.ts) ─────────────────────────
echo "[2/3] Starting Node.js API server on port 3001..."
nohup npx ts-node src/server.ts > logs/node_api.log 2>&1 &
echo $! > "$PID_DIR/node_api.pid"
sleep 2
echo "      ✓ Node API PID: $(cat $PID_DIR/node_api.pid)"

# ── 3. Vite frontend ──────────────────────────────────────────────
echo "[3/3] Starting Vite frontend on port 5173..."
cd "$SCRIPT_DIR/frontend"
nohup npm run dev > "$SCRIPT_DIR/logs/vite.log" 2>&1 &
echo $! > "$PID_DIR/vite.pid"
cd "$SCRIPT_DIR"
sleep 3
echo "      ✓ Vite PID: $(cat $PID_DIR/vite.pid)"

echo ""
echo "=== All services started ==="
echo "  Octopus MCP : http://localhost:8000/health"
echo "  Node.js API : http://localhost:3001"
echo "  Frontend    : http://localhost:5173"
echo ""
echo "To stop: ./stop_all.sh"
