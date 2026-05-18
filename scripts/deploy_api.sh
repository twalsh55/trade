#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API_BASE_URL="${API_BASE_URL:-https://api.brivoly.com}"
RAILWAY_CMD=(npx @railway/cli@latest)
RAILWAY_DEPLOY_RETRIES="${RAILWAY_DEPLOY_RETRIES:-3}"
RAILWAY_RETRY_DELAY_SECONDS="${RAILWAY_RETRY_DELAY_SECONDS:-5}"

cd "${ROOT_DIR}"

log() {
  printf '\n[%s] %s\n' "$(date '+%H:%M:%S')" "$*"
}

run_railway_checked() {
  local output_file
  output_file="$(mktemp)"
  if "${RAILWAY_CMD[@]}" "$@" >"${output_file}" 2>&1; then
    cat "${output_file}"
    rm -f "${output_file}"
    return 0
  fi

  cat "${output_file}" >&2
  if grep -qiE "Unauthorized|invalid_grant|railway login again" "${output_file}"; then
    rm -f "${output_file}"
    echo >&2
    echo "Railway CLI authentication is expired. Run \`npx @railway/cli@latest login\` and retry." >&2
    return 1
  fi

  rm -f "${output_file}"
  return 1
}

is_transient_railway_outage() {
  local output_file="$1"
  grep -qiE "RegionServices/ListRegions UNAVAILABLE|No connection established|GraphQL.*timed out|transport is closing|connection reset by peer" "${output_file}"
}

if ! command -v npx >/dev/null 2>&1; then
  echo "Missing required command: npx" >&2
  exit 1
fi

log "Checking Railway authentication and linked project"
run_railway_checked whoami
run_railway_checked status

log "Deploying Brivoly API to Railway"
attempt=1
while true; do
  output_file="$(mktemp)"
  if "${RAILWAY_CMD[@]}" up --ci >"${output_file}" 2>&1; then
    cat "${output_file}"
    rm -f "${output_file}"
    break
  fi

  cat "${output_file}" >&2
  if grep -qiE "Unauthorized|invalid_grant|railway login again" "${output_file}"; then
    rm -f "${output_file}"
    echo >&2
    echo "Railway CLI authentication is expired. Run \`npx @railway/cli@latest login\` and retry." >&2
    exit 1
  fi

  if is_transient_railway_outage "${output_file}" && [ "${attempt}" -lt "${RAILWAY_DEPLOY_RETRIES}" ]; then
    rm -f "${output_file}"
    log "Railway returned a transient control-plane error. Retrying deploy in ${RAILWAY_RETRY_DELAY_SECONDS}s (${attempt}/${RAILWAY_DEPLOY_RETRIES})"
    sleep "${RAILWAY_RETRY_DELAY_SECONDS}"
    attempt=$((attempt + 1))
    continue
  fi

  if is_transient_railway_outage "${output_file}"; then
    rm -f "${output_file}"
    echo >&2
    echo "Railway still looks unavailable after ${RAILWAY_DEPLOY_RETRIES} attempts." >&2
    echo "Retry in a minute or check Railway status before re-running this deploy." >&2
    exit 1
  fi

  rm -f "${output_file}"
  exit 1
done

log "Smoke testing deployed API at ${API_BASE_URL}"
"${ROOT_DIR}/scripts/smoke_hosted.sh" "${API_BASE_URL}"
