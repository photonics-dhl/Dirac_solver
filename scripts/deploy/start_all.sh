#!/usr/bin/env bash
# start_all.sh — Start all Dirac Solver services on Linux/cloud
# Usage: ./start_all.sh
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_DIR="$SCRIPT_DIR/.pids"
mkdir -p "$PID_DIR"

# Clean stale listeners before startup to avoid false-ready and port drift.
for _port in 3001 5173 8000 8001 8011 8101; do
    lsof -ti :"$_port" 2>/dev/null | xargs -r kill -9 2>/dev/null || true
done

NODE_BIN=""
NPM_CLI=""
if [ -x "$SCRIPT_DIR/node-v16.20.2-linux-x64/bin/node" ] && [ -f "$SCRIPT_DIR/node-v16.20.2-linux-x64/lib/node_modules/npm/bin/npm-cli.js" ]; then
    NODE_BIN="$SCRIPT_DIR/node-v16.20.2-linux-x64/bin/node"
    NPM_CLI="$SCRIPT_DIR/node-v16.20.2-linux-x64/lib/node_modules/npm/bin/npm-cli.js"
elif command -v node > /dev/null 2>&1 && command -v npm > /dev/null 2>&1; then
    NODE_BIN="$(command -v node)"
fi

if [ -z "$NODE_BIN" ]; then
    echo "✗ No usable Node.js runtime found."
    exit 1
fi

PYTHON_BIN=""
if [ -x "$HOME/miniconda3/bin/python3" ]; then
    PYTHON_BIN="$HOME/miniconda3/bin/python3"
elif command -v python3 > /dev/null 2>&1; then
    PYTHON_BIN="$(command -v python3)"
fi

echo "=== Dirac Solver — Starting Services ==="
mkdir -p "$SCRIPT_DIR/logs"

# Ensure outbound API calls (e.g. ZChat/OpenAI) can use manual tunnel proxy by default.
if [ -z "${GLOBAL_PROXY_URL:-}" ]; then
    GLOBAL_PROXY_URL="http://127.0.0.1:7890"
fi
export GLOBAL_PROXY_URL
export HTTP_PROXY="${HTTP_PROXY:-$GLOBAL_PROXY_URL}"
export HTTPS_PROXY="${HTTPS_PROXY:-$GLOBAL_PROXY_URL}"
export ALL_PROXY="${ALL_PROXY:-socks5h://127.0.0.1:7890}"
export NO_PROXY="${NO_PROXY:-127.0.0.1,localhost}"
export http_proxy="${http_proxy:-$HTTP_PROXY}"
export https_proxy="${https_proxy:-$HTTPS_PROXY}"
export all_proxy="${all_proxy:-$ALL_PROXY}"
export OCTOPUS_PBS_PRECHECK_FREE="${OCTOPUS_PBS_PRECHECK_FREE:-true}"
export OCTOPUS_PBS_BIND_FREE_NODE="${OCTOPUS_PBS_BIND_FREE_NODE:-true}"
export OCTOPUS_FP_HTTP_TIMEOUT_SECONDS="${OCTOPUS_FP_HTTP_TIMEOUT_SECONDS:-180}"
export OCTOPUS_FAST_SOLVE_TIMEOUT_MS="${OCTOPUS_FAST_SOLVE_TIMEOUT_MS:-120000}"
export OCTOPUS_FAST_MAX_SCF_ITERATIONS="${OCTOPUS_FAST_MAX_SCF_ITERATIONS:-80}"
export OCTOPUS_FAST_HPC_TIMEOUT_SECONDS="${OCTOPUS_FAST_HPC_TIMEOUT_SECONDS:-150}"
export OCTOPUS_FAST_PBS_NCPUS="${OCTOPUS_FAST_PBS_NCPUS:-8}"
export OCTOPUS_FAST_PBS_MPIPROCS="${OCTOPUS_FAST_PBS_MPIPROCS:-8}"
export OCTOPUS_FAST_PBS_POLL_INTERVAL="${OCTOPUS_FAST_PBS_POLL_INTERVAL:-2}"
export OCTOPUS_FAST_BOX_PADDING_BOHR="${OCTOPUS_FAST_BOX_PADDING_BOHR:-2.5}"
export OCTOPUS_FAST_SPACING_BOHR="${OCTOPUS_FAST_SPACING_BOHR:-0.5}"
export OCTOPUS_FAST_RADIUS_BOHR="${OCTOPUS_FAST_RADIUS_BOHR:-3.0}"
export OCTOPUS_PBS_CMD_TIMEOUT_SECONDS="${OCTOPUS_PBS_CMD_TIMEOUT_SECONDS:-180}"
export OCTOPUS_FAST_DIRECT_TIMEOUT_SECONDS="${OCTOPUS_FAST_DIRECT_TIMEOUT_SECONDS:-180}"
export DIRAC_API_BASE="${DIRAC_API_BASE:-http://127.0.0.1:3001}"
export DIRAC_HARNESS_FALLBACK_BASE="${DIRAC_HARNESS_FALLBACK_BASE:-http://127.0.0.1:8101}"
export DIRAC_DISPATCH_TIMEOUT_SECONDS="${DIRAC_DISPATCH_TIMEOUT_SECONDS:-1800}"
export DIRAC_EXEC_TIMEOUT_SECONDS="${DIRAC_EXEC_TIMEOUT_SECONDS:-1200}"

# ── 1. Octopus MCP container/runtime ─────────────────────────────
echo "[1/5] Starting Octopus MCP service..."
MCP_STARTED=0
if docker compose version > /dev/null 2>&1; then
    (
        cd "$SCRIPT_DIR/docker"
        docker compose up -d
    )
    MCP_STARTED=1
elif command -v docker-compose > /dev/null 2>&1; then
    (
        cd "$SCRIPT_DIR/docker"
        docker-compose up -d
    )
    MCP_STARTED=1
elif [ -x "$SCRIPT_DIR/start_octopus_udocker.sh" ] && { [ -x "$HOME/.local/bin/udocker" ] || command -v udocker > /dev/null 2>&1; }; then
    echo "      ⚠ Docker compose unavailable; trying udocker runtime"
    nohup "$SCRIPT_DIR/start_octopus_udocker.sh" > "$SCRIPT_DIR/logs/octopus_udocker.log" 2>&1 &
    echo $! > "$PID_DIR/octopus_mcp.pid"
    MCP_STARTED=1
else
    echo "      ⚠ Neither docker compose nor udocker is available — skip MCP service"
fi

# Wait for health (only if container start attempted)
if [ "$MCP_STARTED" -eq 1 ]; then
    echo "      Waiting for Octopus MCP health check..."
    for i in $(seq 1 20); do
        if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
            echo "      ✓ Octopus MCP ready"
            break
        fi
        sleep 2
    done
fi

# ── 2. Local Python backend engine (fallback solver) ─────────────
echo "[2/5] Starting local Python backend on port 8011..."
mkdir -p logs
if command -v python3 > /dev/null 2>&1; then
    if ! bash -lc "source ~/miniconda3/etc/profile.d/conda.sh >/dev/null 2>&1 || true; conda activate ai_agent >/dev/null 2>&1 || true; python3 -c 'import chromadb'" > /dev/null 2>&1; then
        echo "      ✗ Missing python dependency: chromadb (ai_agent env)"
        echo "      Suggestion: source ~/miniconda3/etc/profile.d/conda.sh && conda activate ai_agent && pip install chromadb"
        exit 1
    fi
    nohup bash -lc "source ~/miniconda3/etc/profile.d/conda.sh >/dev/null 2>&1 || true; conda activate ai_agent >/dev/null 2>&1 || true; cd '$SCRIPT_DIR'; python3 -m uvicorn backend_engine.main:app --host 0.0.0.0 --port 8011" > "$SCRIPT_DIR/logs/python_engine.log" 2>&1 &
    echo $! > "$PID_DIR/local_engine.pid"
    sleep 2
    echo "      ✓ Local engine PID: $(cat $PID_DIR/local_engine.pid)"
else
    echo "      ⚠ python3 not found; local backend unavailable"
fi

# ── 3. Node.js API server (src/server.ts) ─────────────────────────
echo "[3/5] Starting Node.js API server on port 3001..."
# Export .env vars into shell so process.env is populated regardless of dotenv version
mkdir -p logs
if [ -f "$SCRIPT_DIR/.env" ]; then
    set -a
    # Support CRLF .env files by stripping '\r' before sourcing
    # shellcheck disable=SC1091
    source <(tr -d '\r' < "$SCRIPT_DIR/.env")
    set +a
fi
export LOCAL_ENGINE_URL="http://localhost:8011"
export TS_NODE_CACHE="false"
if [ -f "$SCRIPT_DIR/node_modules/ts-node/dist/bin.js" ]; then
    nohup "$NODE_BIN" "$SCRIPT_DIR/node_modules/ts-node/dist/bin.js" src/server.ts > logs/node_api.log 2>&1 &
elif [ -n "$NPM_CLI" ]; then
    nohup "$NODE_BIN" "$NPM_CLI" exec --yes ts-node src/server.ts > logs/node_api.log 2>&1 &
else
    nohup npx ts-node src/server.ts > logs/node_api.log 2>&1 &
fi
echo $! > "$PID_DIR/node_api.pid"
sleep 2
echo "      ✓ Node API PID: $(cat $PID_DIR/node_api.pid)"

# ── 4. Vite frontend ──────────────────────────────────────────────
echo "[4/5] Starting Vite frontend on port 5173..."
# Prevent port drift to 517x by clearing stale frontend processes first.
pkill -f "frontend/node_modules/vite/bin/vite.js" >/dev/null 2>&1 || true
pkill -f "python3 -m http.server 5173" >/dev/null 2>&1 || true
sleep 1

cd "$SCRIPT_DIR/frontend"
if [ -f "$SCRIPT_DIR/frontend/node_modules/vite/bin/vite.js" ]; then
    nohup "$NODE_BIN" "$SCRIPT_DIR/frontend/node_modules/vite/bin/vite.js" --host 0.0.0.0 --port 5173 --strictPort > "$SCRIPT_DIR/logs/vite.log" 2>&1 &
elif [ -n "$NPM_CLI" ]; then
    nohup "$NODE_BIN" "$NPM_CLI" run dev -- --host 0.0.0.0 --port 5173 --strictPort > "$SCRIPT_DIR/logs/vite.log" 2>&1 &
else
    nohup npm run dev -- --host 0.0.0.0 --port 5173 --strictPort > "$SCRIPT_DIR/logs/vite.log" 2>&1 &
fi
echo $! > "$PID_DIR/vite.pid"
cd "$SCRIPT_DIR"
sleep 3

# Fallback: when Vite cannot run on old systems, serve prebuilt dist statically.
if ! curl -sf http://localhost:5173 > /dev/null 2>&1; then
    if [ -d "$SCRIPT_DIR/frontend/dist" ]; then
        echo "      ⚠ Vite unavailable; serving frontend/dist via python http.server"
        nohup python3 -m http.server 5173 --directory "$SCRIPT_DIR/frontend/dist" > "$SCRIPT_DIR/logs/static_frontend.log" 2>&1 &
        echo $! > "$PID_DIR/vite.pid"
        sleep 2
    fi
fi

echo "      ✓ Vite PID: $(cat $PID_DIR/vite.pid)"

# Resolve harness base for remote worker at runtime to avoid routed-only drift
# when primary 8001 is unavailable and emergency 8101 is active.
if [ -z "${DIRAC_HARNESS_BASE:-}" ]; then
    if curl -sf --max-time 2 http://127.0.0.1:8001/harness/case_registry > /dev/null 2>&1; then
        export DIRAC_HARNESS_BASE="http://127.0.0.1:8001"
    elif curl -sf --max-time 2 http://127.0.0.1:8101/harness/case_registry > /dev/null 2>&1; then
        export DIRAC_HARNESS_BASE="http://127.0.0.1:8101"
    else
        export DIRAC_HARNESS_BASE="http://127.0.0.1:8001"
    fi
fi

# ── 5. Dirac execution queue worker (persistent consumer) ─────────
echo "[5/5] Starting Dirac execution worker..."
if command -v bash > /dev/null 2>&1; then
    # Keep a single worker instance to avoid duplicate queue consumption/noisy state.
    pkill -f "scripts/run_dirac_exec_worker.sh" >/dev/null 2>&1 || true
    pkill -f "scripts/dirac_exec_worker.py" >/dev/null 2>&1 || true
    sleep 1
    echo "      Worker runtime: DIRAC_API_BASE=${DIRAC_API_BASE}, DIRAC_HARNESS_BASE=${DIRAC_HARNESS_BASE}, DIRAC_DISPATCH_TIMEOUT_SECONDS=${DIRAC_DISPATCH_TIMEOUT_SECONDS}"
    nohup bash "$SCRIPT_DIR/scripts/run_dirac_exec_worker.sh" > "$SCRIPT_DIR/logs/dirac_exec_worker.log" 2>&1 &
    echo $! > "$PID_DIR/dirac_exec_worker.pid"
    sleep 1
    echo "      ✓ Worker PID: $(cat $PID_DIR/dirac_exec_worker.pid)"
else
    echo "      ⚠ bash not found; Dirac execution worker not started"
fi

# ── 6. Persistent signal monitors (Feishu + 5173) ───────────────
echo "[6/6] Starting persistent signal monitors..."
if [ -n "$PYTHON_BIN" ]; then
    pkill -f "scripts/monitor_5173_health.py" >/dev/null 2>&1 || true
    pkill -f "scripts/monitor_feishu_signal.py" >/dev/null 2>&1 || true
    sleep 1

    nohup "$PYTHON_BIN" "$SCRIPT_DIR/scripts/monitor_5173_health.py" > "$SCRIPT_DIR/logs/monitor_5173_health.log" 2>&1 &
    echo $! > "$PID_DIR/monitor_5173_health.pid"

    nohup "$PYTHON_BIN" "$SCRIPT_DIR/scripts/monitor_feishu_signal.py" > "$SCRIPT_DIR/logs/monitor_feishu_signal.log" 2>&1 &
    echo $! > "$PID_DIR/monitor_feishu_signal.pid"

    sleep 1
    echo "      ✓ 5173 monitor PID: $(cat $PID_DIR/monitor_5173_health.pid)"
    echo "      ✓ Feishu signal monitor PID: $(cat $PID_DIR/monitor_feishu_signal.pid)"
else
    echo "      ⚠ python3 not found; signal monitors not started"
fi

echo ""
echo "=== All services started ==="
echo "  Octopus MCP : http://localhost:8000/health"
echo "  Node.js API : http://localhost:3001"
echo "  Frontend    : http://localhost:5173"
echo "  Exec worker : logs/dirac_exec_worker.log"
echo "  Monitor 5173: logs/monitor_5173_health.log"
echo "  Monitor Feishu signal: logs/monitor_feishu_signal.log"
echo ""
echo "To stop: ./stop_all.sh"
