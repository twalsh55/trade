#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 <api-base-url>" >&2
  echo "Example: $0 https://trade-api-production.up.railway.app" >&2
  exit 1
fi

base_url="${1%/}"

echo "Checking ${base_url}/healthz"
curl --fail --silent --show-error "${base_url}/healthz"
echo

echo "Checking ${base_url}/readyz"
curl --fail --silent --show-error "${base_url}/readyz"
echo

echo "Checking ${base_url}/api/settings/bootstrap"
curl --fail --silent --show-error "${base_url}/api/settings/bootstrap"
echo
