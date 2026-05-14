#!/usr/bin/env bash
set -euo pipefail

RETRIES="${RETRIES:-20}"
SLEEP_SECS="${SLEEP_SECS:-3}"
CURL_CONNECT_TIMEOUT="${CURL_CONNECT_TIMEOUT:-5}"
CURL_MAX_TIME="${CURL_MAX_TIME:-20}"

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 <api-base-url>" >&2
  echo "Example: $0 https://trade-api-production.up.railway.app" >&2
  exit 1
fi

base_url="${1%/}"

curl_with_retry() {
  local url="$1"
  local attempt

  for attempt in $(seq 1 "${RETRIES}"); do
    if curl \
      --fail \
      --silent \
      --show-error \
      --connect-timeout "${CURL_CONNECT_TIMEOUT}" \
      --max-time "${CURL_MAX_TIME}" \
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

echo "Checking ${base_url}/healthz"
curl_with_retry "${base_url}/healthz"

echo "Checking ${base_url}/readyz"
curl_with_retry "${base_url}/readyz"

echo "Checking ${base_url}/api/settings/bootstrap"
curl_with_retry "${base_url}/api/settings/bootstrap"
