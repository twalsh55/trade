#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "${ROOT_DIR}"

log() {
  printf '\n[%s] %s\n' "$(date '+%H:%M:%S')" "$*"
}

log "Deploying API first"
"${ROOT_DIR}/scripts/deploy_api.sh"

log "Deploying frontend second"
"${ROOT_DIR}/scripts/deploy_web.sh"
