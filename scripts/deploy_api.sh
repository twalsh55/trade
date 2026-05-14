#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API_BASE_URL="${API_BASE_URL:-https://api.brivoly.com}"
RAILWAY_CMD=(npx @railway/cli@latest)

cd "${ROOT_DIR}"

log() {
  printf '\n[%s] %s\n' "$(date '+%H:%M:%S')" "$*"
}

if ! command -v npx >/dev/null 2>&1; then
  echo "Missing required command: npx" >&2
  exit 1
fi

log "Checking Railway authentication and linked project"
"${RAILWAY_CMD[@]}" whoami
"${RAILWAY_CMD[@]}" status

log "Deploying Brivoly API to Railway"
"${RAILWAY_CMD[@]}" up --ci

log "Smoke testing deployed API at ${API_BASE_URL}"
"${ROOT_DIR}/scripts/smoke_hosted.sh" "${API_BASE_URL}"
