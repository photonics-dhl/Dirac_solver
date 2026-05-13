#!/usr/bin/env bash
# update_cloud.sh — Atomic cloud server update
# Usage: ./update_cloud.sh
# Shows exactly which files will change, then pulls and hot-reloads only what's needed.

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== Dirac Solver — Cloud Update ==="
echo ""

# ── 1. Fetch remote changes (no merge yet) ────────────────────────
git fetch origin main --quiet

LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse origin/main)

if [ "$LOCAL" = "$REMOTE" ]; then
    echo "✓ Already up to date ($(git rev-parse --short HEAD))"
    exit 0
fi

# ── 2. Show what will change ──────────────────────────────────────
echo "Updates available:"
git log HEAD..origin/main --oneline
echo ""
echo "Files that will change:"
git diff HEAD origin/main --name-only | sed 's/^/  /'
echo ""

CHANGED=$(git diff HEAD origin/main --name-only)

# ── 3. Pull ───────────────────────────────────────────────────────
git merge origin/main --ff-only
echo ""
echo "✓ Pulled to $(git rev-parse --short HEAD)"
echo ""

# ── 4. Selective hot-reload (only restart what actually changed) ──
NEED_NODE=false
NEED_VITE=false
NEED_DOCKER=false

echo "$CHANGED" | grep -qE '^src/|^package\.json|^tsconfig' && NEED_NODE=true
echo "$CHANGED" | grep -qE '^frontend/' && NEED_VITE=true
echo "$CHANGED" | grep -qE '^docker/' && NEED_DOCKER=true

echo "=== Reloading changed services ==="

if [ "$NEED_DOCKER" = "true" ]; then
    echo "[Docker] docker-compose.yml changed — rebuilding container..."
    cd "$SCRIPT_DIR/docker" && docker compose up -d --build
    cd "$SCRIPT_DIR"
    echo "  ✓ Docker done"
fi

if [ "$NEED_NODE" = "true" ] || [ "$NEED_DOCKER" = "true" ]; then
    echo "[Node]   src/ or package.json changed — restarting API server..."
    pkill -f "ts-node src/server" 2>/dev/null || true
    sleep 1
    # Install any new npm deps
    npm install --silent 2>/dev/null || true
    # Source .env so env vars are inherited by the new process
    set -a && source "$SCRIPT_DIR/.env" && set +a
    mkdir -p logs
    setsid bash -c "npx ts-node src/server.ts >> logs/node_api.log 2>&1" </dev/null &
    sleep 3
    ss -tlnp | grep ':3001' | grep -q 'LISTEN' && echo "  ✓ Node API restarted (port 3001)" || echo "  ✗ Node API failed to start!"
fi

if [ "$NEED_VITE" = "true" ]; then
    echo "[Vite]   frontend/ changed — Vite HMR will auto-update (no restart needed)"
    echo "  ✓ Vite: changes detected via file watch, browser will auto-update"
fi

if [ "$NEED_NODE" = "false" ] && [ "$NEED_VITE" = "false" ] && [ "$NEED_DOCKER" = "false" ]; then
    echo "  (config/docs changes only — no services restarted)"
fi

echo ""
echo "=== Update complete ==="
echo "  Commit : $(git rev-parse --short HEAD)"
echo "  Node   : $(ss -tlnp | grep ':3001' | grep -oP 'pid=\K[0-9]+' | head -1 | xargs -I{} echo "pid={}" 2>/dev/null || echo 'unknown')"
echo "  Vite   : $(ss -tlnp | grep ':5173' | grep -oP 'pid=\K[0-9]+' | head -1 | xargs -I{} echo "pid={}" 2>/dev/null || echo 'unknown')"
echo "  Docker : $(docker ps --format '{{.Names}} {{.Status}}' | grep dirac 2>/dev/null || echo 'unknown')"
