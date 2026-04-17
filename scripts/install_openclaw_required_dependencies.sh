#!/usr/bin/env bash
set -euo pipefail

# Install minimum dependencies used by Dirac OpenClaw automation alignment.
# Safe to rerun.

if ! command -v npm >/dev/null 2>&1; then
  echo "[error] npm is required but not found in PATH"
  exit 1
fi

if ! command -v node >/dev/null 2>&1; then
  echo "[error] node is required but not found in PATH"
  exit 1
fi

echo "[step] install Playwright MCP"
npm install -g @playwright/mcp

echo "[step] ensure Chromium browser for Playwright"
npx playwright install chromium

echo "[step] verify openclaw CLI availability"
if command -v openclaw >/dev/null 2>&1; then
  openclaw --help >/dev/null 2>&1 || true
  echo "[ok] openclaw detected"
else
  echo "[warn] openclaw not found in PATH; install/open path before runtime validation"
fi

echo "[step] optional skill catalog check (non-fatal)"
if command -v openclaw >/dev/null 2>&1; then
  openclaw skills list || true
fi

echo "[done] dependency bootstrap completed"
