#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────
# Bharat Climate Twin — local dev launcher.
# Starts the FastAPI backend (:8000) and the Next.js dashboard (:3000) together,
# wiring the frontend to the backend via NEXT_PUBLIC_API_BASE. Ctrl-C (or any
# exit) tears BOTH down via a trap.
#
#   ./scripts/dev.sh
#   → backend   http://localhost:8000  (docs at /docs)
#   → frontend  http://localhost:3000  (talks to the backend API)
# ──────────────────────────────────────────────────────────────────────────
set -euo pipefail

# Resolve repo root from this script's location (works from any CWD).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"
PYTHON="${PYTHON:-python3}"
export NEXT_PUBLIC_API_BASE="${NEXT_PUBLIC_API_BASE:-http://localhost:${BACKEND_PORT}/api}"

PIDS=()

cleanup() {
  echo ""
  echo "[dev] shutting down…"
  for pid in "${PIDS[@]}"; do
    # Kill the whole process group so child node/uvicorn workers die too.
    kill -- "-${pid}" 2>/dev/null || kill "${pid}" 2>/dev/null || true
  done
  wait 2>/dev/null || true
  echo "[dev] stopped."
}
trap cleanup EXIT INT TERM

echo "[dev] backend  → http://localhost:${BACKEND_PORT}  (FastAPI, docs at /docs)"
echo "[dev] frontend → http://localhost:${FRONTEND_PORT}  (NEXT_PUBLIC_API_BASE=${NEXT_PUBLIC_API_BASE})"
echo ""

# --- backend (its own process group via setsid so the trap can kill children) -
( cd "$ROOT/backend" && exec setsid "$PYTHON" -m uvicorn app.main:app --port "$BACKEND_PORT" ) &
PIDS+=("$!")

# --- frontend ----------------------------------------------------------------
( cd "$ROOT/frontend" && exec setsid npm run dev -- --port "$FRONTEND_PORT" ) &
PIDS+=("$!")

# Wait for either to exit; the trap then cleans up the other.
wait -n 2>/dev/null || wait
