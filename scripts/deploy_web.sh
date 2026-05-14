#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WEB_BASE_URL="${WEB_BASE_URL:-https://www.brivoly.com}"
WEB_SESSION_URL="${WEB_SESSION_URL:-${WEB_BASE_URL%/}/api/session}"
RETRIES="${RETRIES:-20}"
SLEEP_SECS="${SLEEP_SECS:-3}"
CURL_CONNECT_TIMEOUT="${CURL_CONNECT_TIMEOUT:-5}"
CURL_MAX_TIME="${CURL_MAX_TIME:-20}"
VERCEL_CMD=(npx vercel)

cd "${ROOT_DIR}"

log() {
  printf '\n[%s] %s\n' "$(date '+%H:%M:%S')" "$*"
}

curl_with_retry() {
  local url="$1"
  shift
  local attempt

  for attempt in $(seq 1 "${RETRIES}"); do
    if curl \
      --fail \
      --silent \
      --show-error \
      --connect-timeout "${CURL_CONNECT_TIMEOUT}" \
      --max-time "${CURL_MAX_TIME}" \
      "$@" \
      "$url"; then
      echo
      return 0
    fi

    if [[ "${attempt}" -lt "${RETRIES}" ]]; then
      echo "Retry ${attempt}/${RETRIES} failed for ${url}; sleeping ${SLEEP_SECS}s..." >&2
      sleep "${SLEEP_SECS}"
    fi
  done

  echo "Smoke check failed after ${RETRIES} attempts: ${url}" >&2
  return 1
}

if ! command -v npx >/dev/null 2>&1; then
  echo "Missing required command: npx" >&2
  exit 1
fi

log "Checking Vercel authentication"
"${VERCEL_CMD[@]}" whoami

log "Deploying Next.js frontend from web/"
"${VERCEL_CMD[@]}" deploy --prod --yes --cwd web

log "Checking ${WEB_BASE_URL}"
curl_with_retry "${WEB_BASE_URL}" --head

log "Checking ${WEB_SESSION_URL}"
curl_with_retry "${WEB_SESSION_URL}"
