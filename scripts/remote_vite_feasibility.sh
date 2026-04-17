#!/usr/bin/env bash
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="${WORKSPACE_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"
FRONTEND="$ROOT/frontend"
NODE="$ROOT/node-v16.20.2-linux-x64/bin/node"
NPM_CLI="$ROOT/node-v16.20.2-linux-x64/lib/node_modules/npm/bin/npm-cli.js"

log() { echo "[feasibility] $*"; }

bounded_install() {
  local tag="$1"
  local registry="$2"
  local install_log="$ROOT/logs/npm-install-$tag.log"

  rm -f "$install_log"
  log "INSTALL($tag): start registry=$registry"

  "$NODE" "$NPM_CLI" install \
    --registry="$registry" \
    --prefer-online \
    --fetch-retries=6 \
    --fetch-retry-mintimeout=10000 \
    --fetch-retry-maxtimeout=120000 \
    --no-audit \
    --no-fund >"$install_log" 2>&1 &

  local pid=$!
  local start_ts
  start_ts=$(date +%s)
  local last_change_ts=$start_ts
  local last_lines=0
  local reason=""

  while kill -0 "$pid" 2>/dev/null; do
    local now_ts
    now_ts=$(date +%s)
    local lines
    lines=$(wc -l < "$install_log" 2>/dev/null || echo 0)

    if [ "$lines" -gt "$last_lines" ]; then
      last_lines=$lines
      last_change_ts=$now_ts
      log "INSTALL($tag): progress elapsed=$((now_ts-start_ts))s lines=$lines"
    fi

    if [ $((now_ts-last_change_ts)) -ge 600 ]; then
      reason="NO_PROGRESS_10MIN"
      kill "$pid" 2>/dev/null || true
      break
    fi

    if [ $((now_ts-start_ts)) -ge 1200 ]; then
      reason="TIME_LIMIT_20MIN"
      kill "$pid" 2>/dev/null || true
      break
    fi

    sleep 30
  done

  wait "$pid" 2>/dev/null
  local code=$?

  if [ -z "$reason" ]; then
    if [ "$code" -eq 0 ]; then
      reason="OK"
    else
      reason="FAILED"
    fi
  fi

  log "INSTALL($tag): result=$reason code=$code lines=$last_lines"
  tail -n 80 "$install_log" || true

  if [ "$reason" = "OK" ]; then
    return 0
  fi

  return 1
}

run_smoke() {
  local tag="$1"
  log "SMOKE($tag): vite --version"
  if ! "$NODE" "$FRONTEND/node_modules/vite/bin/vite.js" --version; then
    log "SMOKE($tag): vite --version failed"
    return 1
  fi

  log "SMOKE($tag): vite dev 10s"
  timeout 10s "$NODE" "$FRONTEND/node_modules/vite/bin/vite.js" --host 0.0.0.0 --port 5173 >"$ROOT/logs/vite-smoke-$tag.log" 2>&1 || true
  if grep -qi "You installed esbuild for another platform" "$ROOT/logs/vite-smoke-$tag.log"; then
    log "SMOKE($tag): esbuild platform mismatch"
    tail -n 40 "$ROOT/logs/vite-smoke-$tag.log"
    return 2
  fi
  if grep -qiE "ready in|Local:" "$ROOT/logs/vite-smoke-$tag.log"; then
    log "SMOKE($tag): vite dev started OK"
    tail -n 20 "$ROOT/logs/vite-smoke-$tag.log"
    return 0
  fi
  log "SMOKE($tag): inconclusive, last logs"
  tail -n 40 "$ROOT/logs/vite-smoke-$tag.log"
  return 3
}

show_esbuild() {
  log "@esbuild content"
  ls -1 "$FRONTEND/node_modules/@esbuild" 2>/dev/null || true
}

log "START"
cd "$FRONTEND" || exit 1
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY all_proxy

log "Toolchain"
"$NODE" -v
"$NODE" "$NPM_CLI" -v

# Method 1: clean install
log "Method1: clean npm install"
rm -rf node_modules package-lock.json
if bounded_install "m1-npmjs" "https://registry.npmjs.org"; then
  show_esbuild
  if run_smoke "m1"; then
    log "RESULT: FEASIBLE via method1"
    exit 0
  fi
else
  log "Method1 install failed"
fi

# Method 2: targeted esbuild repair
log "Method2: force esbuild linux package"
rm -rf node_modules/@esbuild/win32-x64 node_modules/esbuild
"$NODE" "$NPM_CLI" install --no-save esbuild@0.18.20 @esbuild/linux-x64@0.18.20 --prefer-online --no-audit --no-fund --registry=https://registry.npmjs.org || true
if [ ! -d "$FRONTEND/node_modules/@esbuild/linux-x64" ]; then
  log "Method2 fallback registry: npmmirror"
  "$NODE" "$NPM_CLI" install --no-save esbuild@0.18.20 @esbuild/linux-x64@0.18.20 --prefer-online --no-audit --no-fund --registry=https://registry.npmmirror.com || true
fi
show_esbuild
if run_smoke "m2"; then
  log "RESULT: FEASIBLE via method2"
  exit 0
fi

# Method 3: npm rebuild esbuild
log "Method3: npm rebuild esbuild"
"$NODE" "$NPM_CLI" rebuild esbuild --no-audit --no-fund || true
show_esbuild
if run_smoke "m3"; then
  log "RESULT: FEASIBLE via method3"
  exit 0
fi

log "RESULT: NOT FEASIBLE for native Vite in current remote environment"
exit 9
