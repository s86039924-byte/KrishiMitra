#!/usr/bin/env bash
# Convenience launcher for local development.
# Starts the FastAPI backend and Streamlit frontend together.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "▶ Starting backend on :8000 ..."
( cd "$ROOT/backend" && uvicorn app:app --port 8000 ) &
BACKEND_PID=$!

cleanup() { echo "Stopping backend ($BACKEND_PID)"; kill "$BACKEND_PID" 2>/dev/null || true; }
trap cleanup EXIT

sleep 2
echo "▶ Starting frontend on :8501 ..."
( cd "$ROOT/frontend" && streamlit run main.py )
