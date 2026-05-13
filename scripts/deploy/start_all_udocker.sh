#!/bin/bash
# start_all_udocker.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ -x "$SCRIPT_DIR/node-v16.20.2-linux-x64/bin/node" ]; then
    export PATH="$SCRIPT_DIR/node-v16.20.2-linux-x64/bin:$PATH"
fi

cd "$SCRIPT_DIR"

# Log files
OCT_LOG="octopus_udocker.log"
BACK_LOG="node_backend.log"
FRONT_LOG="vite_frontend.log"

echo "=== Starting Dirac Solver with Udocker ==="

# 1. Start Octopus (Background)
echo "[1/3] Starting Octopus MCP..."
./start_octopus_udocker.sh > "$OCT_LOG" 2>&1 &
OCT_PID=$!
echo "      PID: $OCT_PID (Log: $OCT_LOG)"

# 2. Start Backend
echo "[2/3] Starting Node Backend..."
if [ ! -d "node_modules" ]; then
    echo "      Installing backend dependencies..."
    npm install > /dev/null 2>&1
fi
nohup npx ts-node src/server.ts > "$BACK_LOG" 2>&1 &
BACK_PID=$!
echo "      PID: $BACK_PID (Log: $BACK_LOG)"

# 3. Start Frontend
echo "[3/3] Starting Vite Frontend..."
cd frontend
if [ ! -d "node_modules" ]; then
    echo "      Installing frontend dependencies..."
    npm install > /dev/null 2>&1
fi
nohup npm run dev -- --host 0.0.0.0 > "../$FRONT_LOG" 2>&1 &
FRONT_PID=$!
cd ..
echo "      PID: $FRONT_PID (Log: $FRONT_LOG)"

echo "=== All services started ==="
echo "Backend: http://localhost:3001"
echo "Frontend: http://localhost:5173"
echo ""
echo "Press Ctrl+C to stop all services."

trap "echo 'Stopping all services...'; kill $OCT_PID $BACK_PID $FRONT_PID; exit" SIGINT SIGTERM

wait
