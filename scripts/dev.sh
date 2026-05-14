#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API_HOST="${API_HOST:-127.0.0.1}"
API_PORT="${API_PORT:-8000}"
WEB_HOST="${WEB_HOST:-127.0.0.1}"
WEB_PORT="${WEB_PORT:-3000}"
TRADE_API_BASE_URL="${TRADE_API_BASE_URL:-http://${API_HOST}:${API_PORT}}"

cd "${ROOT_DIR}"

if ! command -v uv >/dev/null 2>&1; then
  echo "Missing required command: uv" >&2
  exit 1
fi

if ! command -v npm >/dev/null 2>&1; then
  echo "Missing required command: npm" >&2
  exit 1
fi

if [[ ! -d ".venv" ]]; then
  echo "Python environment not found. Running uv sync..."
  uv sync
fi

if [[ ! -d "web/node_modules" ]]; then
  echo "Frontend dependencies not found. Running npm install..."
  (
    cd web
    npm install
  )
fi

api_pid=""
web_pid=""
cleaned_up="0"

cleanup() {
  if [[ "${cleaned_up}" == "1" ]]; then
    return
  fi
  cleaned_up="1"

  if [[ -n "${api_pid}" ]] && kill -0 "${api_pid}" >/dev/null 2>&1; then
    kill "${api_pid}" >/dev/null 2>&1 || true
  fi

  if [[ -n "${web_pid}" ]] && kill -0 "${web_pid}" >/dev/null 2>&1; then
    kill "${web_pid}" >/dev/null 2>&1 || true
  fi

  wait >/dev/null 2>&1 || true
}

trap cleanup EXIT INT TERM

echo "Starting Python API on http://${API_HOST}:${API_PORT}"
uv run uvicorn src.adapters.api.app:app --reload --host "${API_HOST}" --port "${API_PORT}" &
api_pid="$!"

echo "Starting Next.js frontend on http://${WEB_HOST}:${WEB_PORT}"
(
  cd web
  TRADE_API_BASE_URL="${TRADE_API_BASE_URL}" npm run dev -- --hostname "${WEB_HOST}" --port "${WEB_PORT}"
) &
web_pid="$!"

echo ""
echo "Local development is starting:"
echo "  API:      http://${API_HOST}:${API_PORT}"
echo "  Frontend: http://${WEB_HOST}:${WEB_PORT}"
echo ""
echo "Press Ctrl+C to stop both services."

wait -n "${api_pid}" "${web_pid}"
